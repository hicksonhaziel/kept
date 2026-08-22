"""Wire the stages together: parse, bind, observe, attack, rule.

Thin orchestration. Every decision lives in the pure modules it belongs to; this
only decides what to call and in what order.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kept import __version__, attack, observation, verdict
from kept import ledger as ledger_module
from kept.bindings import Binding, BindingSet, Origin
from kept.bindings import bindings_path as _bindings_path
from kept.bindings import load as _load_bindings
from kept.bindings import merge as _merge_bindings
from kept.diagnostics import Diagnostic
from kept.ir import Criterion
from kept.loader import load as load_specs
from kept.observe import Report, collect, resolve_interpreter, run, scan_files
from kept.report import html as html_report


@dataclass(frozen=True, slots=True)
class BindStage:
    criteria: tuple[Criterion, ...]
    bindings: BindingSet
    report: Report
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.is_error)

    @property
    def promises(self) -> tuple[Criterion, ...]:
        """Normative criteria only. An advisory criterion carries no verdict."""
        return tuple(criterion for criterion in self.criteria if criterion.is_normative)

    @property
    def promise_ids(self) -> tuple[str, ...]:
        return tuple(criterion.id for criterion in self.promises)

    @property
    def unbound(self) -> tuple[str, ...]:
        return self.bindings.unbound(self.promise_ids)

    @property
    def orphaned(self) -> tuple[str, ...]:
        return self.bindings.orphaned(criterion.id for criterion in self.criteria)


@dataclass(frozen=True, slots=True)
class ObserveStage:
    bind: BindStage
    observations: observation.ObservationSet
    exit_code: int
    output: str

    def covered_by_criterion(self) -> dict[str, dict[str, tuple[int, ...]]]:
        """Lines under audit per criterion, from oracles that actually prove something."""
        return {
            entry.criterion: dict(entry.covered)
            for entry in self.observations.criteria
            if entry.covered
        }

    def oracles_by_criterion(self) -> dict[str, tuple[str, ...]]:
        """Only usable oracles. A failing test would 'notice' every mutant."""
        return {
            entry.criterion: tuple(sorted(oracle.nodeid for oracle in entry.usable))
            for entry in self.observations.criteria
            if entry.usable
        }


@dataclass(frozen=True, slots=True)
class AttackStage:
    observe: ObserveStage
    result: attack.AttackResult
    mutants_available: int


@dataclass(frozen=True, slots=True)
class VerifyStage:
    attack: AttackStage
    judgement: verdict.Judgement
    ledger: ledger_module.Ledger
    stored: ledger_module.Ledger | None
    drift: ledger_module.Drift
    regressions: tuple[ledger_module.Regression, ...]


def bind(
    root: Path,
    *,
    tests: str | None = None,
    python: Path | None = None,
    specs: Sequence[Path] | None = None,
) -> BindStage:
    """Parse the specification and resolve which oracles claim each criterion."""
    spec = load_specs(root, specs=specs)
    report = collect(root, tests=tests, python=python)
    manual = _load_bindings(_bindings_path(root))

    discovered = BindingSet(
        bindings=tuple(_binding(criterion, oracles) for criterion, oracles in report.bindings)
    )
    merged = _merge_bindings(discovered, manual.human_authored())
    return BindStage(
        criteria=spec.criteria,
        bindings=merged,
        report=report,
        diagnostics=spec.diagnostics,
    )


def observe(
    root: Path,
    *,
    tests: str | None = None,
    source: str = ".",
    python: Path | None = None,
    specs: Sequence[Path] | None = None,
) -> ObserveStage:
    """Run the suite under coverage and gather per-criterion evidence."""
    spec = load_specs(root, specs=specs)
    result = run(root, tests=tests, source=source, python=python)
    manual = _load_bindings(_bindings_path(root))

    discovered = BindingSet(
        bindings=tuple(
            _binding(criterion, oracles) for criterion, oracles in result.report.bindings
        )
    )
    merged = _merge_bindings(discovered, manual.human_authored())
    stage = BindStage(
        criteria=spec.criteria,
        bindings=merged,
        report=result.report,
        diagnostics=spec.diagnostics,
    )

    test_files = frozenset(record.nodeid.partition("::")[0] for record in result.report.tests)
    shapes = scan_files(root, set(test_files))

    observations = observation.build(
        criteria=stage.promise_ids,
        bindings=merged,
        report=result.report,
        coverage=result.coverage.lines,
        shapes=shapes,
        test_files=test_files,
    )

    return ObserveStage(
        bind=stage,
        observations=observations,
        exit_code=result.exit_code,
        output=result.output,
    )


def attack_project(
    root: Path,
    *,
    tests: str | None = None,
    source: str = ".",
    cap: int = attack.DEFAULT_CAP,
    workers: int = attack.DEFAULT_WORKERS,
    timeout: float = attack.MIN_TIMEOUT_SECONDS,
    use_cache: bool = True,
    python: Path | None = None,
    specs: Sequence[Path] | None = None,
) -> AttackStage:
    """Observe, then break the covered lines and see which oracles notice."""
    stage = observe(root, tests=tests, source=source, python=python, specs=specs)
    covered = stage.covered_by_criterion()
    oracles = stage.oracles_by_criterion()

    paths = sorted({path for per_path in covered.values() for path in per_path})
    mutants_by_path: dict[str, tuple[attack.Mutant, ...]] = {}
    available = 0

    for path in paths:
        candidate = root / path
        if not candidate.is_file():
            continue
        try:
            mutations = attack.collect(candidate.read_text(encoding="utf-8"))
        except Exception:
            # A target kept cannot parse is skipped, never fatal. It will show up
            # as a criterion with nothing probed rather than as a crash.
            continue
        mutants_by_path[path] = attack.from_mutations(path, mutations)
        available += len(mutations)

    assignments = attack.select(mutants_by_path, covered, cap=cap)
    cache_path = root / ".kept" / "cache" / "mutants.json" if use_cache else None

    result = attack.execute(
        root,
        assignments,
        oracles,
        cap=cap,
        workers=workers,
        timeout=timeout,
        cache_path=cache_path,
        python=resolve_interpreter(root, python),
    )
    return AttackStage(observe=stage, result=result, mutants_available=available)


def verify(
    root: Path,
    *,
    tests: str | None = None,
    source: str = ".",
    cap: int = attack.DEFAULT_CAP,
    workers: int = attack.DEFAULT_WORKERS,
    timeout: float = attack.MIN_TIMEOUT_SECONDS,
    use_cache: bool = True,
    python: Path | None = None,
    threshold: float = verdict.DEFAULT_THRESHOLD,
    specs: Sequence[Path] | None = None,
) -> VerifyStage:
    """The whole pipeline: parse, bind, observe, attack, rule, ledger."""
    stage = attack_project(
        root,
        tests=tests,
        source=source,
        cap=cap,
        workers=workers,
        timeout=timeout,
        use_cache=use_cache,
        python=python,
        specs=specs,
    )

    criteria = {c.id: c.content_hash for c in stage.observe.bind.promises}
    judged = verdict.judge(
        observations=stage.observe.observations,
        attack=stage.result,
        hashes=criteria,
        threshold=threshold,
    )

    covered = stage.observe.covered_by_criterion()
    paths = {path for per_path in covered.values() for path in per_path}
    sources = ledger_module.source_hashes(root, paths)

    fresh = ledger_module.build(
        judged,
        kept_version=__version__,
        settings=ledger_module.Settings(threshold=threshold, cap=cap),
        sources=sources,
        commit=ledger_module.current_commit(root),
    )

    stored = ledger_module.load(ledger_module.ledger_path(root))
    return VerifyStage(
        attack=stage,
        judgement=judged,
        ledger=fresh,
        stored=stored,
        drift=(
            ledger_module.drift(stored, hashes=criteria, sources=sources)
            if stored is not None
            else ledger_module.Drift()
        ),
        regressions=(ledger_module.regressions(stored, fresh) if stored is not None else ()),
    )


def mutation_diffs(
    root: Path, stored: ledger_module.Ledger
) -> dict[tuple[str, int, str, str], html_report.MutationDiff]:
    """Recompute the line each recorded mutant changed, for the HTML report.

    The ledger records what changed and where, not the text: storing source lines
    would put a copy of the code in an artefact that already records its hash. So
    the mutation is regenerated from the file — deterministically, by the same
    operators — and only when the file still hashes to what the ledger judged. A
    source that has moved gets no diff rather than a plausible one.
    """
    recorded = dict(stored.sources)
    wanted: dict[str, list[tuple[str, int, str, str]]] = {}
    for ruling in stored.rulings:
        for missed in ruling.evidence.missed:
            key = (missed.path, missed.line, missed.operator, missed.description)
            wanted.setdefault(missed.path, []).append(key)

    diffs: dict[tuple[str, int, str, str], html_report.MutationDiff] = {}

    for path, keys in wanted.items():
        candidate = root / path
        source = candidate.read_text(encoding="utf-8") if candidate.is_file() else None
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.is_file() else None
        fresh = source is not None and digest == recorded.get(path)

        if not fresh:
            for key in keys:
                diffs[key] = html_report.MutationDiff(*key, stale=True)
            continue

        assert source is not None
        original = source.splitlines()
        try:
            mutations = attack.collect(source)
        except Exception:
            mutations = ()

        index_of = {
            (mutation.line, mutation.operator, mutation.description): position
            for position, mutation in reversed(list(enumerate(mutations)))
        }

        for key in keys:
            _, line, operator, description = key
            position = index_of.get((line, operator, description))
            if position is None:
                diffs[key] = html_report.MutationDiff(*key, stale=True)
                continue
            try:
                mutated = attack.apply(source, position).splitlines()
            except Exception:
                diffs[key] = html_report.MutationDiff(*key, stale=True)
                continue
            if not (0 < line <= len(original) and line <= len(mutated)):
                diffs[key] = html_report.MutationDiff(*key, stale=True)
                continue
            diffs[key] = html_report.MutationDiff(
                *key,
                before=original[line - 1].rstrip(),
                after=mutated[line - 1].rstrip(),
            )

    return diffs


def _binding(criterion: str, oracles: tuple[str, ...]) -> Binding:
    return Binding(criterion=criterion, oracles=oracles, origin=Origin.ANNOTATION)
