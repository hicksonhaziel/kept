"""The recursive-descent parser: patterns, modalities, conditions, diagnostics."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from kept.ears.parser import ParseResult
from kept.ir import ClauseKind, Criterion, EarsPattern, LogicalOperator, Modality
from tests.conftest import BASE_OFFSET

Parsed = Callable[[str], Criterion]
Parse = Callable[[str], ParseResult]


class TestPatternClassification:
    @pytest.mark.verifies("REQ-2.1")
    def test_no_leading_clause_is_ubiquitous(self, parsed: Parsed) -> None:
        criterion = parsed("THE lexer SHALL record the start offset of every token")
        assert criterion.pattern is EarsPattern.UBIQUITOUS
        assert criterion.clauses == ()

    @pytest.mark.verifies("REQ-2.2")
    def test_a_when_clause_is_event_driven_and_records_a_trigger(self, parsed: Parsed) -> None:
        criterion = parsed("WHEN the cart is empty THEN the system SHALL display a warning")
        assert criterion.pattern is EarsPattern.EVENT_DRIVEN
        assert [clause.kind for clause in criterion.clauses] == [ClauseKind.TRIGGER]
        assert criterion.clauses[0].condition.text == "the cart is empty"

    @pytest.mark.verifies("REQ-2.3")
    def test_a_while_clause_is_state_driven_and_records_a_state(self, parsed: Parsed) -> None:
        criterion = parsed("WHILE a refund is pending THE system SHALL reject a second refund")
        assert criterion.pattern is EarsPattern.STATE_DRIVEN
        assert criterion.clauses[0].kind is ClauseKind.STATE

    @pytest.mark.verifies("REQ-2.4")
    def test_an_if_clause_is_unwanted_behaviour(self, parsed: Parsed) -> None:
        criterion = parsed("IF the payment is declined THEN the system SHALL void the invoice")
        assert criterion.pattern is EarsPattern.UNWANTED_BEHAVIOUR
        assert criterion.clauses[0].kind is ClauseKind.UNWANTED

    @pytest.mark.verifies("REQ-2.5")
    def test_a_where_clause_is_an_optional_feature(self, parsed: Parsed) -> None:
        criterion = parsed("WHERE partial refunds are enabled THE system SHALL prorate the tax")
        assert criterion.pattern is EarsPattern.OPTIONAL_FEATURE
        assert criterion.clauses[0].kind is ClauseKind.FEATURE

    @pytest.mark.verifies("REQ-2.6")
    def test_two_or_more_clauses_are_complex_and_keep_source_order(self, parsed: Parsed) -> None:
        criterion = parsed(
            "WHILE the session is active, WHEN the user clicks save, "
            "THEN the system SHALL persist the draft"
        )
        assert criterion.pattern is EarsPattern.COMPLEX
        assert [clause.kind for clause in criterion.clauses] == [
            ClauseKind.STATE,
            ClauseKind.TRIGGER,
        ]

    @pytest.mark.verifies("REQ-1.4")
    def test_clause_bodies_do_not_keep_the_separating_comma(self, parsed: Parsed) -> None:
        criterion = parsed(
            "WHILE the session is active, WHEN the user clicks save, "
            "THEN the system SHALL persist the draft"
        )
        assert criterion.clauses[0].condition.text == "the session is active"
        assert criterion.clauses[1].condition.text == "the user clicks save"

    @pytest.mark.verifies("REQ-1.4")
    def test_a_comma_inside_a_clause_body_is_retained(self, parsed: Parsed) -> None:
        criterion = parsed(
            "WHEN the totals for tax, freight, and duty are known "
            "THEN the system SHALL issue the invoice"
        )
        assert criterion.clauses[0].condition.text == (
            "the totals for tax, freight, and duty are known"
        )


class TestResponse:
    @pytest.mark.verifies("REQ-2.7")
    def test_then_is_a_separator_and_is_excluded_from_the_response(self, parsed: Parsed) -> None:
        criterion = parsed("WHEN the cart is empty THEN the system SHALL display a warning")
        assert criterion.subject == "the system"
        assert criterion.predicate == "display a warning"
        assert "THEN" not in criterion.subject
        assert "THEN" not in criterion.predicate

    @pytest.mark.verifies("REQ-2.7")
    def test_without_then_the_clause_absorbs_the_subject(self, parsed: Parsed) -> None:
        # With no THEN there is no marker separating the condition from the
        # subject, so the boundary is genuinely undecidable. The parser reads the
        # clause body up to the modality rather than guessing where the subject
        # starts. The response is still recovered, and the criterion still gets a
        # stable identity and hash.
        criterion = parsed("WHEN the cart is empty the system SHALL display a warning")
        assert criterion.clauses[0].condition.text == "the cart is empty the system"
        assert criterion.subject == ""
        assert criterion.predicate == "display a warning"

    @pytest.mark.verifies("REQ-2.7")
    def test_then_is_not_required_when_no_clause_precedes_the_subject(self, parsed: Parsed) -> None:
        criterion = parsed("THE system SHALL display a warning")
        assert criterion.subject == "THE system"
        assert criterion.predicate == "display a warning"

    def test_the_is_not_a_keyword_so_any_subject_spelling_works(self, parsed: Parsed) -> None:
        assert parsed("THE system SHALL stop").subject == "THE system"
        assert parsed("the system SHALL stop").subject == "the system"
        assert parsed("the Refund Service SHALL stop").subject == "the Refund Service"

    def test_predicate_punctuation_spacing_is_faithful_to_the_source(self, parsed: Parsed) -> None:
        # Text is recovered by slicing the source, not by rejoining tokens, which
        # would produce "token , because".
        criterion = parsed("THE system SHALL emit a word token, because prose is not grammar")
        assert criterion.predicate == "emit a word token, because prose is not grammar"


class TestModality:
    @pytest.mark.verifies("REQ-2.8")
    def test_all_modalities_are_recognised(self, parsed: Parsed) -> None:
        cases = {
            "THE system SHALL stop": Modality.SHALL,
            "THE system SHALL NOT stop": Modality.SHALL_NOT,
            "THE system SHOULD stop": Modality.SHOULD,
            "THE system SHOULD NOT stop": Modality.SHOULD_NOT,
            "THE system MAY stop": Modality.MAY,
            "THE system MUST stop": Modality.MUST,
            "THE system MUST NOT stop": Modality.MUST_NOT,
        }
        for text, expected in cases.items():
            assert parsed(text).modality is expected, text

    @pytest.mark.verifies("REQ-2.8")
    def test_negation_is_not_left_in_the_predicate(self, parsed: Parsed) -> None:
        criterion = parsed("THE system SHALL NOT log the card number")
        assert criterion.predicate == "log the card number"

    @pytest.mark.verifies("REQ-2.9")
    def test_shall_and_must_are_normative(self, parsed: Parsed) -> None:
        for text in (
            "THE system SHALL stop",
            "THE system SHALL NOT stop",
            "THE system MUST stop",
            "THE system MUST NOT stop",
        ):
            assert parsed(text).is_normative, text

    @pytest.mark.verifies("REQ-2.10")
    def test_should_and_may_are_advisory(self, parsed: Parsed) -> None:
        # A criterion that does not oblige the implementation cannot fairly be
        # held to a verdict (REQ-2.10).
        for text in (
            "THE system SHOULD stop",
            "THE system SHOULD NOT stop",
            "THE system MAY stop",
        ):
            assert not parsed(text).is_normative, text

    @pytest.mark.verifies("REQ-2.8")
    def test_the_first_modality_wins_when_the_predicate_contains_another(
        self, parsed: Parsed
    ) -> None:
        criterion = parsed("THE system SHALL classify the pattern and SHALL record the clause")
        assert criterion.modality is Modality.SHALL
        assert criterion.predicate == "classify the pattern and SHALL record the clause"


class TestConditions:
    @pytest.mark.verifies("REQ-2.11")
    def test_upper_case_and_splits_the_body_into_conjuncts(self, parsed: Parsed) -> None:
        criterion = parsed(
            "WHEN the cart is empty AND the user is anonymous "
            "THEN the system SHALL redirect to the catalogue"
        )
        condition = criterion.clauses[0].condition
        assert condition.operator is LogicalOperator.AND
        assert condition.conjuncts == ("the cart is empty", "the user is anonymous")

    @pytest.mark.verifies("REQ-2.11")
    def test_upper_case_or_splits_the_body_into_conjuncts(self, parsed: Parsed) -> None:
        criterion = parsed(
            "WHEN the order is cancelled OR the order is expired "
            "THEN the system SHALL release the hold"
        )
        condition = criterion.clauses[0].condition
        assert condition.operator is LogicalOperator.OR
        assert len(condition.conjuncts) == 2

    @pytest.mark.verifies("REQ-2.12")
    def test_lower_case_and_is_prose_and_yields_one_conjunct(self, parsed: Parsed) -> None:
        criterion = parsed(
            "WHEN the user submits a name and email address "
            "THEN the system SHALL validate both fields"
        )
        condition = criterion.clauses[0].condition
        assert condition.operator is None
        assert condition.conjuncts == ("the user submits a name and email address",)

    @pytest.mark.verifies("REQ-2.11")
    def test_mixed_operators_are_left_unsplit_rather_than_guessed(self, parsed: Parsed) -> None:
        # Precedence is genuinely ambiguous here, so the parser refuses to invent
        # a structure the author did not write.
        criterion = parsed("WHEN a is set OR b is set AND c is set THEN the system SHALL halt")
        condition = criterion.clauses[0].condition
        assert condition.operator is None
        assert condition.conjuncts == ("a is set OR b is set AND c is set",)

    @pytest.mark.verifies("REQ-2.11")
    def test_a_backticked_operator_does_not_split_the_body(self, parsed: Parsed) -> None:
        criterion = parsed(
            "WHEN a clause body contains an upper-case `AND` or `OR` "
            "THEN the system SHALL record the conjuncts"
        )
        assert criterion.clauses[0].condition.operator is None


class TestSpans:
    def test_the_criterion_span_is_the_span_it_was_given(self, parse: Parse) -> None:
        text = "THE system SHALL stop"
        criterion = parse(text).criterion
        assert criterion is not None
        assert criterion.span.start == BASE_OFFSET
        assert criterion.span.end == BASE_OFFSET + len(text)

    @pytest.mark.verifies("REQ-2.15")
    def test_clause_spans_are_rebased_into_file_coordinates(self, parsed: Parsed) -> None:
        text = "WHEN the cart is empty THEN the system SHALL warn"
        criterion = parsed(text)
        clause_span = criterion.clauses[0].span
        assert clause_span.start == BASE_OFFSET + text.index("WHEN")
        assert clause_span.end == BASE_OFFSET + text.index(" THEN")

    @pytest.mark.verifies("REQ-2.15")
    def test_clause_spans_slice_back_to_the_clause_text(self, parsed: Parsed) -> None:
        text = "WHEN the cart is empty THEN the system SHALL warn"
        criterion = parsed(text)
        clause_span = criterion.clauses[0].span
        recovered = text[clause_span.start - BASE_OFFSET : clause_span.end - BASE_OFFSET]
        assert recovered == "WHEN the cart is empty"

    @pytest.mark.verifies("REQ-2.15")
    def test_clause_spans_carry_the_source_path(self, parsed: Parsed) -> None:
        criterion = parsed("WHEN a happens THEN the system SHALL react")
        assert criterion.clauses[0].span.source == "spec.md"


class TestMultiLineCriteria:
    @pytest.mark.verifies("REQ-4.5")
    def test_raw_text_is_kept_verbatim_so_offsets_stay_exact(self, parsed: Parsed) -> None:
        text = "WHEN the cart is empty\n   THEN the system SHALL warn"
        assert parsed(text).raw_text == text

    @pytest.mark.verifies("REQ-4.5")
    def test_text_property_joins_continuation_lines(self, parsed: Parsed) -> None:
        text = "WHEN the cart is empty\n   THEN the system SHALL warn"
        assert parsed(text).text == "WHEN the cart is empty THEN the system SHALL warn"

    @pytest.mark.verifies("REQ-3.4")
    def test_a_wrapped_criterion_parses_identically_to_a_single_line_one(
        self, parsed: Parsed
    ) -> None:
        wrapped = parsed("WHEN the cart is empty\n   THEN the system SHALL warn")
        single = parsed("WHEN the cart is empty THEN the system SHALL warn")
        assert wrapped.content_hash == single.content_hash
        assert wrapped.clauses[0].condition == single.clauses[0].condition
        assert wrapped.predicate == single.predicate


class TestDiagnostics:
    @pytest.mark.verifies("REQ-2.13")
    @pytest.mark.verifies("REQ-5.2")
    def test_no_modality_yields_e001_and_no_criterion(self, parse: Parse) -> None:
        result = parse("The system does something vague")
        assert result.criterion is None
        assert [d.code for d in result.diagnostics] == ["E001"]
        assert result.has_errors

    @pytest.mark.verifies("REQ-1.7")
    def test_a_lower_case_modality_also_yields_w001(self, parse: Parse) -> None:
        result = parse("the system shall refund the order")
        codes = [d.code for d in result.diagnostics]
        assert codes == ["E001", "W001"]

    @pytest.mark.verifies("REQ-5.4")
    def test_the_w001_message_tells_the_author_what_to_change(self, parse: Parse) -> None:
        result = parse("the system shall refund the order")
        warning = next(d for d in result.diagnostics if d.code == "W001")
        assert "'SHALL'" in warning.message

    def test_no_w001_when_a_real_modality_is_present(self, parse: Parse) -> None:
        result = parse("THE system SHALL refund when the customer should ask")
        assert result.diagnostics == ()

    @pytest.mark.verifies("REQ-2.14")
    def test_an_empty_clause_body_yields_e002(self, parse: Parse) -> None:
        result = parse("WHEN THEN the system SHALL stop")
        assert [d.code for d in result.diagnostics] == ["E002"]

    @pytest.mark.verifies("REQ-5.5")
    def test_a_partially_understood_criterion_is_still_emitted(self, parse: Parse) -> None:
        # Its identity must stay stable across the fix (REQ-5.5).
        result = parse("WHEN THEN the system SHALL stop")
        assert result.criterion is not None
        assert result.criterion.id == "REQ-1.1"
        assert result.criterion.clauses == ()

    @pytest.mark.verifies("REQ-2.14")
    @pytest.mark.verifies("REQ-5.4")
    def test_the_e002_message_mentions_the_backtick_escape_hatch(self, parse: Parse) -> None:
        result = parse("WHEN THEN the system SHALL stop")
        assert "backticks" in result.diagnostics[0].message

    @pytest.mark.verifies("REQ-5.3")
    def test_diagnostic_spans_point_into_file_coordinates(self, parse: Parse) -> None:
        result = parse("WHEN THEN the system SHALL stop")
        span = result.diagnostics[0].span
        assert span is not None
        assert span.start == BASE_OFFSET


class TestIdentity:
    @pytest.mark.verifies("REQ-3.1")
    def test_the_criterion_carries_its_structural_identifier(self, parsed: Parsed) -> None:
        assert parsed("THE system SHALL stop").id == "REQ-1.1"

    @pytest.mark.verifies("REQ-3.3")
    def test_the_content_hash_covers_the_whole_criterion(self, parsed: Parsed) -> None:
        first = parsed("THE system SHALL stop")
        second = parsed("THE system SHALL halt")
        assert first.content_hash != second.content_hash

    @pytest.mark.verifies("REQ-3.6")
    def test_the_hash_algorithm_is_recorded(self, parsed: Parsed) -> None:
        assert parsed("THE system SHALL stop").hash_algorithm == "sha256"
