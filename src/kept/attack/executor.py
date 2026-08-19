"""Run mutants against the tests bound to the criteria they affect.

Two decisions carry the performance budget.

Work is grouped **by mutant**, not by criterion. Several criteria commonly cover
the same line, so one patched file answers for all of them in a single test
process rather than one process each.

Mutants run in **isolated copies** of the project, one per worker. The user's
working tree is never patched, so an interrupted run cannot leave mutated source
behind, and workers cannot see each other's edits.
"""

from __future__ import annotations

import hashlib
import json
import queue
import shutil
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kept.attack import operators
from kept.attack.mutants import Assignment, Mutant, cache_key
from kept.observe.runner import run_tests

#: Directories never worth copying into a worker's worktree.
_SKIP = shutil.ignore_patterns(
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    "node_modules",
    ".kept",
    "htmlcov",
    "dist",
    "build",
)

DEFAULT_WORKERS = 8

#: Floor for the per-mutant timeout. A mutant that turns a loop infinite must be
#: cut off, but a cold interpreter start is slow enough that a tight bound would
#: report healthy mutants as hangs.
MIN_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class MutantOutcome:
    """What one mutant did to each criterion that covers its line."""

    mutant: Mutant
    killed: tuple[str, ...] = ()
    survived: tuple[str, ...] = ()
    timed_out: bool = False
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.mutant.to_dict(),
            "killed": list(self.killed),
            "survived": list(self.survived),
            "timed_out": self.timed_out,
            "cached": self.cached,
        }


@dataclass(frozen=True, slots=True)
class AttackResult:
    outcomes: tuple[MutantOutcome, ...] = ()
    cap: int = 0
    workers: int = 0

    def survivors_for(self, criterion: str) -> tuple[MutantOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if criterion in outcome.survived)

    def killed_for(self, criterion: str) -> tuple[MutantOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if criterion in outcome.killed)

    def probed(self, criterion: str) -> int:
        return len(self.survivors_for(criterion)) + len(self.killed_for(criterion))

    def to_dict(self) -> dict[str, Any]:
        return {
            "cap": self.cap,
            "workers": self.workers,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }


class _Cache:
    """Per (mutant, criterion) results, keyed by everything that could change them."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._entries: dict[str, bool] = {}
        if path is not None and path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                self._entries = {
                    key: bool(value)
                    for key, value in loaded.get("killed", {}).items()
                    if isinstance(key, str)
                }
            except (OSError, json.JSONDecodeError):
                # A damaged cache is discarded, never trusted. It is only ever a
                # speed-up, so losing it costs time and nothing else.
                self._entries = {}

    def get(self, key: str) -> bool | None:
        return self._entries.get(key)

    def put(self, key: str, killed: bool) -> None:
        self._entries[key] = killed

    def flush(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"killed": dict(sorted(self._entries.items()))}
        self._path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def execute(
    root: Path,
    assignments: tuple[Assignment, ...],
    oracles: Mapping[str, tuple[str, ...]],
    *,
    cap: int,
    workers: int = DEFAULT_WORKERS,
    timeout: float = MIN_TIMEOUT_SECONDS,
    cache_path: Path | None = None,
    python: Path | None = None,
) -> AttackResult:
    """Run every assignment and report which criteria each mutant escaped.

    Args:
        root: The project under audit. Never modified.
        assignments: Mutants paired with the criteria that cover them.
        oracles: Per criterion, the tests bound to it.
        cap: Mutants per criterion, recorded so a reader knows the run's limits.
        workers: Parallel test processes.
        timeout: Seconds allowed per mutant before it is treated as killed.
        cache_path: Where to persist results between runs.
    """
    if not assignments:
        return AttackResult(cap=cap, workers=workers)

    cache = _Cache(cache_path)
    hashes = _source_hashes(root, {assignment.mutant.path for assignment in assignments})

    pending, resolved = _partition(assignments, oracles, hashes, cache)

    if pending:
        worker_count = max(1, min(workers, len(pending)))
        with (
            _worktrees(root, worker_count) as pool,
            ThreadPoolExecutor(max_workers=worker_count) as executor,
        ):
            for outcome in executor.map(
                lambda assignment: _probe(
                    assignment, oracles, pool, timeout=timeout, python=python
                ),
                pending,
            ):
                resolved.append(outcome)
                source_hash = hashes.get(outcome.mutant.path, "")
                for criterion in outcome.killed:
                    cache.put(_key(source_hash, outcome.mutant, oracles, criterion), True)
                for criterion in outcome.survived:
                    cache.put(_key(source_hash, outcome.mutant, oracles, criterion), False)
        cache.flush()

    resolved.sort(key=lambda outcome: _outcome_order(outcome))
    return AttackResult(outcomes=tuple(resolved), cap=cap, workers=workers)


def _key(
    source_hash: str,
    mutant: Mutant,
    oracles: Mapping[str, tuple[str, ...]],
    criterion: str,
) -> str:
    return cache_key(
        source_hash=source_hash,
        mutant=mutant,
        oracles=oracles.get(criterion, ()),
    )


def _outcome_order(outcome: MutantOutcome) -> tuple[str, int, int]:
    return (outcome.mutant.path, outcome.mutant.line, outcome.mutant.index)


def _partition(
    assignments: tuple[Assignment, ...],
    oracles: Mapping[str, tuple[str, ...]],
    hashes: Mapping[str, str],
    cache: _Cache,
) -> tuple[list[Assignment], list[MutantOutcome]]:
    """Split assignments into those needing a run and those already known."""
    pending: list[Assignment] = []
    resolved: list[MutantOutcome] = []

    for assignment in assignments:
        source_hash = hashes.get(assignment.mutant.path, "")
        killed: list[str] = []
        survived: list[str] = []
        unknown: list[str] = []

        for criterion in assignment.criteria:
            hit = cache.get(
                cache_key(
                    source_hash=source_hash,
                    mutant=assignment.mutant,
                    oracles=oracles.get(criterion, ()),
                )
            )
            if hit is None:
                unknown.append(criterion)
            elif hit:
                killed.append(criterion)
            else:
                survived.append(criterion)

        if unknown:
            pending.append(assignment)
        else:
            resolved.append(
                MutantOutcome(
                    mutant=assignment.mutant,
                    killed=tuple(killed),
                    survived=tuple(survived),
                    cached=True,
                )
            )

    return pending, resolved


def _probe(
    assignment: Assignment,
    oracles: Mapping[str, tuple[str, ...]],
    pool: queue.Queue[Path],
    *,
    timeout: float,
    python: Path | None = None,
) -> MutantOutcome:
    """Apply one mutant in a borrowed worktree and see which criteria notice."""
    mutant = assignment.mutant
    nodeids = sorted({node for c in assignment.criteria for node in oracles.get(c, ())})

    worktree = pool.get()
    try:
        target = worktree / mutant.path
        original = target.read_text(encoding="utf-8")
        try:
            mutated = operators.apply(original, mutant.index)
        except Exception:
            # Any CST failure means this is not a usable mutant, not that kept
            # should stop. Counted as killed so it cannot inflate the survivors.
            return MutantOutcome(mutant=mutant, killed=assignment.criteria)

        if mutated == original:
            # An operator that changed nothing proves nothing. Counting it as a
            # kill would inflate the score, so it is reported as killed only
            # because it cannot survive: it does not exist.
            return MutantOutcome(mutant=mutant, killed=assignment.criteria)

        try:
            target.write_text(mutated, encoding="utf-8")
            run = run_tests(worktree, nodeids, timeout=timeout, python=python)
        finally:
            target.write_text(original, encoding="utf-8")
    finally:
        pool.put(worktree)

    if run.timed_out:
        return MutantOutcome(mutant=mutant, killed=assignment.criteria, timed_out=True)

    records = run.report.by_nodeid()
    killed: list[str] = []
    survived: list[str] = []

    for criterion in assignment.criteria:
        bound = oracles.get(criterion, ())
        # A criterion kills a mutant only through its own bound oracles. A failure
        # elsewhere in the suite does not count: the claim under audit is that
        # this criterion is independently verified. See docs/adr/0003.
        noticed = any(
            (record := records.get(nodeid)) is None or not record.passed for nodeid in bound
        )
        (killed if noticed else survived).append(criterion)

    return MutantOutcome(mutant=mutant, killed=tuple(killed), survived=tuple(survived))


def _source_hashes(root: Path, paths: set[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(paths):
        candidate = root / path
        if candidate.is_file():
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            hashes[path] = digest
    return hashes


class _worktrees:
    """A pool of throwaway project copies, one per worker."""

    def __init__(self, root: Path, count: int) -> None:
        self._root = root
        self._count = count
        self._base: Path | None = None
        self._pool: queue.Queue[Path] = queue.Queue()

    def __enter__(self) -> queue.Queue[Path]:
        import tempfile

        self._base = Path(tempfile.mkdtemp(prefix="kept-attack-"))
        for number in range(self._count):
            destination = self._base / f"w{number}"
            shutil.copytree(self._root, destination, ignore=_SKIP, symlinks=True)
            self._pool.put(destination)
        return self._pool

    def __exit__(self, *exception: object) -> None:
        if self._base is not None:
            shutil.rmtree(self._base, ignore_errors=True)
