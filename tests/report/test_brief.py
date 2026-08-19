"""The remediation brief is a pure renderer, so it is tested with built evidence.

Unbound on purpose: `kept prompt` has no acceptance criteria yet, and binding these
to a criterion they do not verify would be the misattribution kept exists to catch.
"""

from __future__ import annotations

import pytest

from kept.ids import content_hash
from kept.ir import Clause, ClauseKind, Condition, Criterion, Modality, Span, build_criterion
from kept.ledger import Ledger, Settings
from kept.report.brief import DISCLAIMER, UnknownCriterionError, render
from kept.verdict import Evidence, Missed, Ruling, Unproven, Verdict

SETTINGS = Settings(threshold=1.0, cap=12)


def _ledger(*rulings: Ruling, commit: str | None = "c0ffee") -> Ledger:
    return Ledger(kept_version="0.1.0", settings=SETTINGS, rulings=rulings, commit=commit)


def _criterion(
    text: str = "WHEN a refund exceeds the invoice total, the system SHALL reject it",
) -> Criterion:
    return build_criterion(
        requirement_number=2,
        position=1,
        clauses=(
            Clause(
                kind=ClauseKind.TRIGGER,
                condition=Condition(text="a refund exceeds the invoice total", conjuncts=()),
                span=Span(source="requirements.md", start=0, end=40),
            ),
        ),
        subject="the system",
        modality=Modality.SHALL,
        predicate="reject it",
        raw_text=text,
        span=Span(source="requirements.md", start=0, end=len(text)),
    )


def _weak() -> Ruling:
    return Ruling(
        criterion="REQ-2.1",
        content_hash=content_hash("whatever"),
        verdict=Verdict.WEAK,
        evidence=Evidence(
            oracles=(("test_refund.py::test_cap", "passed"),),
            covered=(("refund.py", (12, 13, 14, 18)),),
            probed=7,
            killed=6,
            discriminating=7,
            missed=(
                Missed(
                    path="refund.py",
                    line=14,
                    operator="comparison",
                    description="replaced > with >=",
                    caught_by=("REQ-2.4",),
                ),
            ),
        ),
        reason="1 of 7 detectable breakages went unnoticed by this promise's own oracles",
    )


def test_a_brief_names_the_promise_the_verdict_and_the_evidence_commit() -> None:
    brief = render(_ledger(_weak()), "REQ-2.1", criterion=_criterion())

    assert brief.startswith("# Remediation brief — REQ-2.1\n")
    assert "Verdict **weak**." in brief
    assert "Evidence gathered at commit `c0ffee`, kept 0.1.0." in brief
    assert "> WHEN a refund exceeds the invoice total, the system SHALL reject it" in brief


def test_a_weak_brief_lists_every_missed_breakage_with_the_oracle_that_noticed_it() -> None:
    brief = render(_ledger(_weak()), "REQ-2.1", criterion=_criterion())

    assert "1. `refund.py:14` — replaced > with >= (comparison)" in brief
    assert "Noticed by the oracles of: `REQ-2.4`" in brief
    assert "Lines under audit:" in brief
    assert "- `refund.py`: 12-14, 18" in brief


def test_a_brief_refuses_to_prescribe_binding_another_promises_test() -> None:
    brief = render(_ledger(_weak()), "REQ-2.1", criterion=_criterion())

    assert "Do not bind another promise's test to this one" in brief


def test_every_brief_says_it_is_a_suggestion_outside_the_verification_path() -> None:
    for ruling in (_weak(), Ruling("REQ-2.1", "abc", Verdict.KEPT)):
        brief = render(_ledger(ruling), "REQ-2.1")
        assert DISCLAIMER in brief
        assert "Only re-running `kept verify` can change a verdict." in brief


def test_a_kept_brief_asks_for_no_change_and_still_refuses_to_claim_proof() -> None:
    brief = render(_ledger(Ruling("REQ-2.1", "abc", Verdict.KEPT)), "REQ-2.1")

    assert "Nothing. Every breakage" in brief
    assert "This is evidence, not proof." in brief


def test_an_unbound_promise_is_told_how_to_bind_itself() -> None:
    ruling = Ruling("REQ-2.1", "abc", Verdict.UNPROVEN, reason=Unproven.NO_BINDING)

    brief = render(_ledger(ruling), "REQ-2.1")

    assert '@pytest.mark.verifies("REQ-2.1")' in brief
    assert ".kept/bindings.toml" in brief
    assert "No oracle is bound to this promise." in brief


def test_a_vacuous_oracle_is_told_to_assert_rather_than_to_be_deleted() -> None:
    ruling = Ruling("REQ-2.1", "abc", Verdict.UNPROVEN, reason=Unproven.NO_USABLE_ORACLE)

    brief = render(_ledger(ruling), "REQ-2.1")

    assert "asserts nothing" in brief
    assert "Add the assertion that would fail if the promise were broken" in brief


def test_a_broken_promise_is_told_not_to_skip_the_failing_oracle() -> None:
    ruling = Ruling(
        "REQ-2.1",
        "abc",
        Verdict.BROKEN,
        evidence=Evidence(
            oracles=(
                ("test_refund.py::test_cap", "failed"),
                ("test_refund.py::test_other", "passed"),
            )
        ),
        reason="bound oracle failed: test_refund.py::test_cap",
    )

    brief = render(_ledger(ruling), "REQ-2.1")

    assert "Do not delete or skip the oracle to clear the verdict" in brief
    assert "- `test_refund.py::test_cap`" in brief
    assert "- `test_refund.py::test_other`" not in brief.split("Failing oracles:")[1]


def test_an_unknown_criterion_raises_and_names_what_the_ledger_does_hold() -> None:
    with pytest.raises(UnknownCriterionError) as caught:
        render(_ledger(_weak()), "REQ-9.9")

    assert "REQ-9.9" in str(caught.value)
    assert "REQ-2.1" in str(caught.value)


def test_a_brief_warns_when_the_evidence_describes_a_different_commit() -> None:
    brief = render(_ledger(_weak()), "REQ-2.1", at_commit="deadbeef")

    assert "but you are on `deadbeef`" in brief
    assert "It may no longer apply." in brief


def test_a_brief_without_the_commit_it_is_read_at_makes_no_staleness_claim() -> None:
    brief = render(_ledger(_weak()), "REQ-2.1")

    assert "may no longer apply" not in brief


def test_a_missing_criterion_text_is_admitted_rather_than_invented() -> None:
    brief = render(_ledger(_weak()), "REQ-2.1")

    assert "The specification no longer defines this identifier" in brief


def test_the_brief_quotes_the_command_that_would_re_check_the_promise() -> None:
    brief = render(_ledger(_weak()), "REQ-2.1", command="kept verify --root . --write")

    assert "```bash\nkept verify --root . --write\n```" in brief


def test_two_renders_of_one_ledger_are_byte_identical() -> None:
    stored = _ledger(_weak())

    assert render(stored, "REQ-2.1", criterion=_criterion()) == render(
        stored, "REQ-2.1", criterion=_criterion()
    )
