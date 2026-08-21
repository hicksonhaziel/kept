"""The rule engine, tested with constructed evidence and no I/O.

Unbound on purpose: the verdict rules have no acceptance criteria of their own yet.
The ears-parser specification says nothing about verdicts, and binding these tests
to one of its criteria would be the misattribution kept exists to catch.
"""

from __future__ import annotations

from pathlib import Path

from kept.attack.executor import AttackResult, MutantOutcome, _import_roots
from kept.attack.mutants import Mutant
from kept.observation import CriterionObservation, ObservationSet, OracleObservation, OracleStatus
from kept.verdict import Unproven, Verdict, judge

CRITERION = "REQ-1.1"
HASHES = {CRITERION: "abc123"}


def _oracle(
    nodeid: str = "tests/test_thing.py::test_it",
    status: OracleStatus = OracleStatus.PASSED,
    *,
    has_assertion: bool = True,
) -> OracleObservation:
    return OracleObservation(nodeid=nodeid, status=status, has_assertion=has_assertion)


def _observation(
    *oracles: OracleObservation,
    covered: tuple[tuple[str, tuple[int, ...]], ...] = (("thing.py", (1, 2)),),
) -> ObservationSet:
    return ObservationSet(
        criteria=(
            CriterionObservation(
                criterion=CRITERION,
                oracles=oracles or (_oracle(),),
                covered=covered,
            ),
        )
    )


def _mutant(index: int = 0, line: int = 1) -> Mutant:
    return Mutant(
        path="thing.py",
        line=line,
        index=index,
        operator="comparison",
        description="< to <=",
    )


def _verdict_of(observations: ObservationSet, attack: AttackResult) -> tuple[Verdict, str | None]:
    ruling = judge(observations=observations, attack=attack, hashes=HASHES).rulings[0]
    return ruling.verdict, (str(ruling.reason) if ruling.reason else None)


def test_a_promise_whose_own_oracles_killed_every_detectable_breakage_is_kept() -> None:
    attack = AttackResult(outcomes=(MutantOutcome(mutant=_mutant(), killed=(CRITERION,)),))

    assert _verdict_of(_observation(), attack)[0] is Verdict.KEPT


def test_a_survivor_another_promise_caught_makes_this_promise_weak() -> None:
    attack = AttackResult(
        outcomes=(
            MutantOutcome(mutant=_mutant(0), killed=(CRITERION,)),
            MutantOutcome(mutant=_mutant(1), survived=(CRITERION,), killed=("REQ-2.1",)),
        )
    )

    verdict, reason = _verdict_of(_observation(), attack)

    assert verdict is Verdict.WEAK
    assert reason == "1 of 2 detectable breakages went unnoticed by this promise's own oracles"


def test_a_mutant_that_was_never_run_cannot_manufacture_a_kept_verdict() -> None:
    """Regression: mutants that failed to build, or changed nothing, were recorded
    as killed. A promise whose every mutant was a no-op scored 1.0 and reported
    KEPT on an empty probe — the exact vacuous evidence kept exists to expose."""
    attack = AttackResult(
        outcomes=(
            MutantOutcome(mutant=_mutant(0), executed=False),
            MutantOutcome(mutant=_mutant(1), executed=False),
        )
    )

    verdict, reason = _verdict_of(_observation(), attack)

    assert verdict is Verdict.UNPROVEN
    assert reason == str(Unproven.NO_MUTANTS)


def test_a_breakage_no_bound_oracle_anywhere_noticed_is_charged_to_the_suite() -> None:
    attack = AttackResult(outcomes=(MutantOutcome(mutant=_mutant(), survived=(CRITERION,)),))

    judgement = judge(observations=_observation(), attack=attack, hashes=HASHES)
    ruling = judgement.rulings[0]

    assert ruling.verdict is Verdict.UNPROVEN
    assert str(ruling.reason) == str(Unproven.NOT_DISCRIMINATING)
    assert ruling.evidence.unpinned == 1
    assert len(judgement.unpinned) == 1
    assert judgement.unpinned[0].covered_by == (CRITERION,)


def test_a_timed_out_mutant_counts_as_noticed() -> None:
    attack = AttackResult(
        outcomes=(MutantOutcome(mutant=_mutant(), killed=(CRITERION,), timed_out=True),)
    )

    assert _verdict_of(_observation(), attack)[0] is Verdict.KEPT


def test_a_failing_bound_oracle_is_broken_and_names_the_oracle() -> None:
    observations = _observation(_oracle(status=OracleStatus.FAILED))

    verdict, reason = _verdict_of(observations, AttackResult())

    assert verdict is Verdict.BROKEN
    assert reason == "bound oracle failed: tests/test_thing.py::test_it"


def test_an_erroring_oracle_is_broken_and_says_errored_rather_than_failed() -> None:
    observations = _observation(_oracle(status=OracleStatus.ERROR))

    assert _verdict_of(observations, AttackResult())[1] == (
        "bound oracle errored: tests/test_thing.py::test_it"
    )


def test_a_promise_with_no_oracle_is_unproven_not_broken() -> None:
    observations = ObservationSet(
        criteria=(CriterionObservation(criterion=CRITERION, oracles=(), covered=()),)
    )

    verdict, reason = _verdict_of(observations, AttackResult())

    assert verdict is Verdict.UNPROVEN
    assert reason == str(Unproven.NO_BINDING)


def test_an_oracle_that_asserts_nothing_proves_nothing() -> None:
    observations = _observation(_oracle(has_assertion=False))

    verdict, reason = _verdict_of(observations, AttackResult())

    assert verdict is Verdict.UNPROVEN
    assert reason == str(Unproven.NO_USABLE_ORACLE)


def test_a_passing_oracle_that_covers_no_line_is_unproven() -> None:
    observations = _observation(covered=())

    verdict, reason = _verdict_of(observations, AttackResult())

    assert verdict is Verdict.UNPROVEN
    assert reason == str(Unproven.NO_COVERAGE)


def test_the_threshold_is_recorded_and_applied_as_given() -> None:
    attack = AttackResult(
        outcomes=(
            MutantOutcome(mutant=_mutant(0), killed=(CRITERION,)),
            MutantOutcome(mutant=_mutant(1), survived=(CRITERION,), killed=("REQ-2.1",)),
        )
    )

    lenient = judge(
        observations=_observation(), attack=attack, hashes=HASHES, threshold=0.5
    ).rulings[0]
    strict = judge(observations=_observation(), attack=attack, hashes=HASHES).rulings[0]

    assert lenient.verdict is Verdict.KEPT
    assert strict.verdict is Verdict.WEAK


def test_the_ruling_records_the_content_hash_it_judged() -> None:
    ruling = judge(observations=_observation(), attack=AttackResult(), hashes=HASHES).rulings[0]

    assert ruling.content_hash == "abc123"


def test_a_src_layout_package_is_imported_from_the_worktree_not_the_environment(
    tmp_path: Path,
) -> None:
    """The mutated copy has to win over an installed distribution of the same name."""
    package = tmp_path / "src" / "thing"
    package.mkdir(parents=True)
    (package / "__init__.py").touch()
    (package / "core.py").touch()

    assert _import_roots(tmp_path, "src/thing/core.py") == (tmp_path / "src",)


def test_a_flat_module_is_imported_from_the_worktree_root(tmp_path: Path) -> None:
    (tmp_path / "thing.py").touch()

    assert _import_roots(tmp_path, "thing.py") == (tmp_path,)
