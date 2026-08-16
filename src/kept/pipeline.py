"""Wire the stages together: parse, bind, observe.

Thin orchestration. Every decision lives in the pure modules it belongs to; this
only decides what to call and in what order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kept import observation
from kept.bindings import Binding, BindingSet, Origin
from kept.bindings import bindings_path as _bindings_path
from kept.bindings import load as _load_bindings
from kept.bindings import merge as _merge_bindings
from kept.ir import Criterion
from kept.loader import load_all
from kept.observe import Report, collect, run, scan_files


@dataclass(frozen=True, slots=True)
class BindStage:
    criteria: tuple[Criterion, ...]
    bindings: BindingSet
    report: Report

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


def bind(root: Path, *, tests: str | None = None) -> BindStage:
    """Parse the specification and resolve which oracles claim each criterion."""
    spec = load_all(root)
    report = collect(root, tests=tests)
    manual = _load_bindings(_bindings_path(root))

    discovered = BindingSet(
        bindings=tuple(
            _binding(criterion, oracles) for criterion, oracles in report.bindings
        )
    )
    merged = _merge_bindings(discovered, manual.human_authored())
    return BindStage(criteria=spec.criteria, bindings=merged, report=report)


def observe(root: Path, *, tests: str | None = None, source: str = ".") -> ObserveStage:
    """Run the suite under coverage and gather per-criterion evidence."""
    spec = load_all(root)
    result = run(root, tests=tests, source=source)
    manual = _load_bindings(_bindings_path(root))

    discovered = BindingSet(
        bindings=tuple(
            _binding(criterion, oracles) for criterion, oracles in result.report.bindings
        )
    )
    merged = _merge_bindings(discovered, manual.human_authored())
    stage = BindStage(criteria=spec.criteria, bindings=merged, report=result.report)

    test_files = frozenset(
        record.nodeid.partition("::")[0] for record in result.report.tests
    )
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


def _binding(criterion: str, oracles: tuple[str, ...]) -> Binding:
    return Binding(criterion=criterion, oracles=oracles, origin=Origin.ANNOTATION)
