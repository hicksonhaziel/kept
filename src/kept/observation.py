"""Assemble raw observations into per-criterion evidence. Pure: no I/O."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from kept.bindings import BindingSet
from kept.observe.runner import Report, TestRecord
from kept.observe.vacuity import OracleShape, shape_for


class OracleStatus(StrEnum):
    """What happened when an oracle ran."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    NOT_RUN = "notrun"
    MISSING = "missing"  # bound to a test that does not exist


@dataclass(frozen=True, slots=True)
class OracleObservation:
    """One test, as evidence for one criterion."""

    nodeid: str
    status: OracleStatus
    has_assertion: bool
    covered: tuple[tuple[str, tuple[int, ...]], ...] = ()

    @property
    def is_vacuous(self) -> bool:
        """Passed, but provably asserts nothing, so it constrains nothing."""
        return self.status is OracleStatus.PASSED and not self.has_assertion

    @property
    def counts_as_evidence(self) -> bool:
        return self.status is OracleStatus.PASSED and self.has_assertion

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeid": self.nodeid,
            "status": str(self.status),
            "has_assertion": self.has_assertion,
            "is_vacuous": self.is_vacuous,
            "covered": {path: list(lines) for path, lines in self.covered},
        }


@dataclass(frozen=True, slots=True)
class CriterionObservation:
    """Everything observed about one criterion, before any verdict is reached."""

    criterion: str
    oracles: tuple[OracleObservation, ...] = ()
    covered: tuple[tuple[str, tuple[int, ...]], ...] = ()
    excluded_reason: str | None = None

    @property
    def has_oracle(self) -> bool:
        return bool(self.oracles)

    @property
    def failing(self) -> tuple[OracleObservation, ...]:
        return tuple(
            oracle
            for oracle in self.oracles
            if oracle.status in {OracleStatus.FAILED, OracleStatus.ERROR}
        )

    @property
    def usable(self) -> tuple[OracleObservation, ...]:
        """Oracles that passed and assert something. Only these prove anything."""
        return tuple(oracle for oracle in self.oracles if oracle.counts_as_evidence)

    @property
    def vacuous(self) -> tuple[OracleObservation, ...]:
        return tuple(oracle for oracle in self.oracles if oracle.is_vacuous)

    @property
    def covered_line_count(self) -> int:
        return sum(len(lines) for _, lines in self.covered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "excluded_reason": self.excluded_reason,
            "oracles": [oracle.to_dict() for oracle in self.oracles],
            "covered": {path: list(lines) for path, lines in self.covered},
            "covered_line_count": self.covered_line_count,
        }


@dataclass(frozen=True, slots=True)
class ObservationSet:
    criteria: tuple[CriterionObservation, ...] = ()

    def get(self, criterion: str) -> CriterionObservation | None:
        for observation in self.criteria:
            if observation.criterion == criterion:
                return observation
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"criteria": [observation.to_dict() for observation in self.criteria]}


def build(
    *,
    criteria: Iterable[str],
    bindings: BindingSet,
    report: Report,
    coverage: Mapping[str, Mapping[str, tuple[int, ...]]],
    shapes: Mapping[str, OracleShape],
    test_files: frozenset[str],
) -> ObservationSet:
    """Combine bindings, test outcomes, coverage, and oracle shapes.

    Args:
        criteria: Criterion identifiers to observe, in the order to report them.
        bindings: The merged criterion-to-oracle map.
        report: What the pytest plugin recorded.
        coverage: Per-context, per-file executed line numbers.
        shapes: Per-oracle syntactic shape, keyed by node ID.
        test_files: Repository-relative test file paths, excluded from covered
            lines because mutating a test proves nothing about the code.
    """
    records = report.by_nodeid()
    observations: list[CriterionObservation] = []

    for criterion in criteria:
        if bindings.is_unverifiable(criterion):
            reason = next(
                entry.reason for entry in bindings.unverifiable if entry.criterion == criterion
            )
            observations.append(CriterionObservation(criterion=criterion, excluded_reason=reason))
            continue

        oracles = tuple(
            _observe_oracle(nodeid, records, coverage, shapes, test_files)
            for bound in bindings.oracles_for(criterion)
            for nodeid in _resolve(bound, records)
        )

        observations.append(
            CriterionObservation(
                criterion=criterion,
                oracles=oracles,
                covered=_union(oracle.covered for oracle in oracles if oracle.counts_as_evidence),
            )
        )

    return ObservationSet(criteria=tuple(observations))


def _resolve(bound: str, records: Mapping[str, TestRecord]) -> tuple[str, ...]:
    """Expand a bound node ID to the tests it names.

    A bare node ID covers every parametrisation of that test, which is what
    `pytest path::test_it` already means. Without this, binding a parametrised
    test required naming each variant, and naming the function reported the
    oracle as missing. See docs/adr/0007.
    """
    if bound in records:
        return (bound,)
    variants = tuple(sorted(n for n in records if n.startswith(f"{bound}[")))
    return variants or (bound,)


def _observe_oracle(
    nodeid: str,
    records: Mapping[str, TestRecord],
    coverage: Mapping[str, Mapping[str, tuple[int, ...]]],
    shapes: Mapping[str, OracleShape],
    test_files: frozenset[str],
) -> OracleObservation:
    record = records.get(nodeid)
    if record is None:
        # Bound to a test that no longer exists. Reported, never ignored.
        return OracleObservation(
            nodeid=nodeid,
            status=OracleStatus.MISSING,
            has_assertion=False,
        )

    shape = shape_for(shapes, nodeid)
    covered: tuple[tuple[str, tuple[int, ...]], ...] = ()
    if record.context is not None:
        per_file = coverage.get(record.context, {})
        covered = tuple(
            (path, lines) for path, lines in sorted(per_file.items()) if path not in test_files
        )

    return OracleObservation(
        nodeid=nodeid,
        status=OracleStatus(record.outcome),
        # An oracle kept cannot find in the source is treated as asserting
        # nothing, because an unverifiable claim is not evidence.
        has_assertion=shape.has_assertion if shape is not None else False,
        covered=covered,
    )


def _union(
    groups: Iterable[tuple[tuple[str, tuple[int, ...]], ...]],
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    merged: dict[str, set[int]] = {}
    for group in groups:
        for path, lines in group:
            merged.setdefault(path, set()).update(lines)
    return tuple((path, tuple(sorted(lines))) for path, lines in sorted(merged.items()))
