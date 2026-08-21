"""Turn evidence into verdicts. Pure: no I/O, no clock, no randomness.

The rule that shapes everything here: a mutant is only evidence about a promise's
oracle if some bound oracle proved it detectable. A breakage nobody in the suite
notices says something about the code, not about this promise's test, so it is
reported separately as an unpinned line rather than counted against the promise.

That distinction removes the need for an arbitrary pass mark. See docs/adr/0004.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from kept.attack.executor import AttackResult, MutantOutcome
from kept.observation import CriterionObservation, ObservationSet, OracleStatus

#: A promise is KEPT only when its own oracles caught every detectable breakage.
#: Lowering this admits promises whose oracles are weaker than their siblings'.
DEFAULT_THRESHOLD = 1.0


class Verdict(StrEnum):
    KEPT = "kept"
    WEAK = "weak"
    UNPROVEN = "unproven"
    BROKEN = "broken"
    STALE = "stale"


#: Why a promise could not be given a verdict on the evidence available.
class Unproven(StrEnum):
    NO_BINDING = "no oracle claims to verify this promise"
    NO_USABLE_ORACLE = "every bound oracle was skipped, missing, or asserts nothing"
    NO_COVERAGE = "the bound oracles ran no code attributable to this promise"
    NO_MUTANTS = "no mutation could be generated on the covered lines"
    NOT_DISCRIMINATING = (
        "no breakage of the covered lines was detected by any bound oracle, "
        "so there is no evidence either way about this oracle's strength"
    )


@dataclass(frozen=True, slots=True)
class Missed:
    """A breakage this promise's oracle failed to notice, but another caught."""

    path: str
    line: int
    operator: str
    description: str
    caught_by: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "operator": self.operator,
            "description": self.description,
            "caught_by": list(self.caught_by),
        }


@dataclass(frozen=True, slots=True)
class Evidence:
    """The receipts behind one verdict."""

    oracles: tuple[tuple[str, str], ...] = ()
    covered: tuple[tuple[str, tuple[int, ...]], ...] = ()
    probed: int = 0
    killed: int = 0
    discriminating: int = 0
    missed: tuple[Missed, ...] = ()
    unpinned: int = 0

    @property
    def score(self) -> float | None:
        """Share of detectable breakages this promise's own oracles caught."""
        if self.discriminating == 0:
            return None
        return (self.discriminating - len(self.missed)) / self.discriminating

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracles": [{"nodeid": nodeid, "status": status} for nodeid, status in self.oracles],
            "covered": {path: list(lines) for path, lines in self.covered},
            "mutants": {
                "probed": self.probed,
                "killed": self.killed,
                "discriminating": self.discriminating,
                "unpinned": self.unpinned,
            },
            "score": self.score,
            "missed": [entry.to_dict() for entry in self.missed],
        }


@dataclass(frozen=True, slots=True)
class Ruling:
    """One promise, judged."""

    criterion: str
    content_hash: str
    verdict: Verdict
    evidence: Evidence = field(default_factory=Evidence)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "content_hash": self.content_hash,
            "verdict": str(self.verdict),
            "reason": self.reason,
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class UnpinnedLine:
    """A breakage no bound oracle anywhere noticed.

    Reported at suite level rather than charged to a promise: if nothing in the
    bound suite detects it, it is a gap in the tests as a whole, and blaming any
    one promise for it would be misattribution.
    """

    path: str
    line: int
    operator: str
    description: str
    covered_by: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "operator": self.operator,
            "description": self.description,
            "covered_by": list(self.covered_by),
        }


@dataclass(frozen=True, slots=True)
class Judgement:
    rulings: tuple[Ruling, ...] = ()
    unpinned: tuple[UnpinnedLine, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()
    threshold: float = DEFAULT_THRESHOLD

    def counts(self) -> dict[str, int]:
        tally = {str(verdict): 0 for verdict in Verdict}
        for ruling in self.rulings:
            tally[str(ruling.verdict)] += 1
        return tally

    def of(self, verdict: Verdict) -> tuple[Ruling, ...]:
        return tuple(ruling for ruling in self.rulings if ruling.verdict is verdict)

    def get(self, criterion: str) -> Ruling | None:
        for ruling in self.rulings:
            if ruling.criterion == criterion:
                return ruling
        return None


def judge(
    *,
    observations: ObservationSet,
    attack: AttackResult,
    hashes: Mapping[str, str],
    threshold: float = DEFAULT_THRESHOLD,
) -> Judgement:
    """Reach a verdict for every observed promise.

    Args:
        observations: What each promise's oracles did and covered.
        attack: Which breakages each promise noticed.
        hashes: Content hash per criterion, so a ruling records what it judged.
        threshold: Share of detectable breakages required for KEPT.
    """
    rulings: list[Ruling] = []
    excluded: list[tuple[str, str]] = []

    for observation in observations.criteria:
        if observation.excluded_reason is not None:
            excluded.append((observation.criterion, observation.excluded_reason))
            continue
        rulings.append(
            _rule(
                observation,
                attack,
                content_hash=hashes.get(observation.criterion, ""),
                threshold=threshold,
            )
        )

    return Judgement(
        rulings=tuple(rulings),
        unpinned=_unpinned(attack),
        excluded=tuple(sorted(excluded)),
        threshold=threshold,
    )


def _rule(
    observation: CriterionObservation,
    attack: AttackResult,
    *,
    content_hash: str,
    threshold: float,
) -> Ruling:
    criterion = observation.criterion

    if not observation.has_oracle:
        return Ruling(criterion, content_hash, Verdict.UNPROVEN, reason=Unproven.NO_BINDING)

    if observation.failing:
        return Ruling(
            criterion,
            content_hash,
            Verdict.BROKEN,
            evidence=_evidence(observation, attack),
            reason=_broken_reason(observation),
        )

    if not observation.usable:
        return Ruling(criterion, content_hash, Verdict.UNPROVEN, reason=Unproven.NO_USABLE_ORACLE)

    if not observation.covered:
        return Ruling(criterion, content_hash, Verdict.UNPROVEN, reason=Unproven.NO_COVERAGE)

    evidence = _evidence(observation, attack)

    if evidence.probed == 0:
        return Ruling(
            criterion, content_hash, Verdict.UNPROVEN, evidence=evidence, reason=Unproven.NO_MUTANTS
        )

    score = evidence.score
    if score is None:
        return Ruling(
            criterion,
            content_hash,
            Verdict.UNPROVEN,
            evidence=evidence,
            reason=Unproven.NOT_DISCRIMINATING,
        )

    if score >= threshold:
        return Ruling(criterion, content_hash, Verdict.KEPT, evidence=evidence)

    return Ruling(
        criterion,
        content_hash,
        Verdict.WEAK,
        evidence=evidence,
        reason=(
            f"{len(evidence.missed)} of {evidence.discriminating} detectable breakages "
            f"went unnoticed by this promise's own oracles"
        ),
    )


def _evidence(observation: CriterionObservation, attack: AttackResult) -> Evidence:
    criterion = observation.criterion
    killed = attack.killed_for(criterion)
    survived = attack.survivors_for(criterion)

    missed: list[Missed] = []
    unpinned = 0
    for outcome in survived:
        if outcome.killed:
            missed.append(
                Missed(
                    path=outcome.mutant.path,
                    line=outcome.mutant.line,
                    operator=outcome.mutant.operator,
                    description=outcome.mutant.description,
                    caught_by=outcome.killed,
                )
            )
        else:
            unpinned += 1

    return Evidence(
        oracles=tuple((oracle.nodeid, str(oracle.status)) for oracle in observation.oracles),
        covered=observation.covered,
        probed=len(killed) + len(survived),
        killed=len(killed),
        discriminating=len(killed) + len(missed),
        missed=tuple(missed),
        unpinned=unpinned,
    )


def _broken_reason(observation: CriterionObservation) -> str:
    failures = observation.failing
    names = ", ".join(oracle.nodeid for oracle in failures[:3])
    more = "" if len(failures) <= 3 else f" and {len(failures) - 3} more"
    errored = any(oracle.status is OracleStatus.ERROR for oracle in failures)
    verb = "errored" if errored else "failed"
    return f"bound oracle {verb}: {names}{more}"


def _unpinned(attack: AttackResult) -> tuple[UnpinnedLine, ...]:
    """Breakages that survived every promise that probed them."""
    return tuple(
        UnpinnedLine(
            path=outcome.mutant.path,
            line=outcome.mutant.line,
            operator=outcome.mutant.operator,
            description=outcome.mutant.description,
            covered_by=outcome.survived,
        )
        for outcome in attack.outcomes
        if _is_unpinned(outcome)
    )


def _is_unpinned(outcome: MutantOutcome) -> bool:
    return bool(outcome.survived) and not outcome.killed
