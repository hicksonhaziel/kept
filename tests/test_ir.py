"""The IR: classification, normativity, spans, and deterministic serialisation."""

from __future__ import annotations

import json

import pytest

from kept.ir import (
    Clause,
    ClauseKind,
    Condition,
    EarsPattern,
    Modality,
    Span,
    SpecDocument,
    build_criterion,
    build_requirement,
    classify_pattern,
    is_normative,
    to_json,
)


def clause(kind: ClauseKind) -> Clause:
    return Clause(
        kind=kind,
        condition=Condition(text="x", conjuncts=("x",)),
        span=Span("spec.md", 0, 1),
    )


class TestClassification:
    """Tested as a pure function on clause kinds, with no parser involved."""

    @pytest.mark.verifies("REQ-2.1")
    def test_no_clauses_is_ubiquitous(self) -> None:
        assert classify_pattern(()) is EarsPattern.UBIQUITOUS

    def test_one_clause_maps_to_that_clauses_pattern(self) -> None:
        assert classify_pattern((ClauseKind.TRIGGER,)) is EarsPattern.EVENT_DRIVEN
        assert classify_pattern((ClauseKind.STATE,)) is EarsPattern.STATE_DRIVEN
        assert classify_pattern((ClauseKind.UNWANTED,)) is EarsPattern.UNWANTED_BEHAVIOUR
        assert classify_pattern((ClauseKind.FEATURE,)) is EarsPattern.OPTIONAL_FEATURE

    @pytest.mark.verifies("REQ-2.6")
    def test_two_or_more_clauses_is_complex(self) -> None:
        assert classify_pattern((ClauseKind.STATE, ClauseKind.TRIGGER)) is EarsPattern.COMPLEX

    def test_every_clause_kind_has_a_single_clause_pattern(self) -> None:
        # Guards against adding a clause kind and forgetting the mapping.
        for kind in ClauseKind:
            assert classify_pattern((kind,)) is not EarsPattern.COMPLEX


class TestNormativity:
    @pytest.mark.verifies("REQ-2.9")
    def test_shall_and_must_oblige_the_implementation(self) -> None:
        assert is_normative(Modality.SHALL)
        assert is_normative(Modality.SHALL_NOT)
        assert is_normative(Modality.MUST)
        assert is_normative(Modality.MUST_NOT)

    @pytest.mark.verifies("REQ-2.10")
    def test_should_and_may_do_not(self) -> None:
        assert not is_normative(Modality.SHOULD)
        assert not is_normative(Modality.SHOULD_NOT)
        assert not is_normative(Modality.MAY)

    @pytest.mark.verifies("REQ-2.8")
    def test_every_modality_is_classified(self) -> None:
        for modality in Modality:
            assert isinstance(is_normative(modality), bool)


class TestSpan:
    def test_rejects_a_negative_start(self) -> None:
        with pytest.raises(ValueError, match="start must be >= 0"):
            Span("spec.md", -1, 4)

    def test_rejects_an_end_before_its_start(self) -> None:
        with pytest.raises(ValueError, match="precedes start"):
            Span("spec.md", 10, 4)

    def test_shift_rebases_both_ends(self) -> None:
        assert Span("spec.md", 2, 5).shift(100) == Span("spec.md", 102, 105)

    def test_slice_of_extracts_the_described_text(self) -> None:
        assert Span("spec.md", 4, 9).slice_of("the quick brown fox") == "quick"

    def test_spans_are_ordered_for_deterministic_output(self) -> None:
        assert Span("a.md", 5, 6) < Span("b.md", 1, 2)
        assert Span("a.md", 1, 2) < Span("a.md", 5, 6)


class TestImmutability:
    def test_a_criterion_cannot_be_mutated(self) -> None:
        criterion = build_criterion(
            requirement_number=1,
            position=1,
            clauses=(),
            subject="THE system",
            modality=Modality.SHALL,
            predicate="stop",
            raw_text="THE system SHALL stop",
            span=Span("spec.md", 0, 21),
        )
        with pytest.raises(AttributeError):
            criterion.subject = "other"  # type: ignore[misc]


class TestSerialisation:
    def build_document(self) -> SpecDocument:
        criterion = build_criterion(
            requirement_number=1,
            position=1,
            clauses=(clause(ClauseKind.TRIGGER),),
            subject="the system",
            modality=Modality.SHALL,
            predicate="warn",
            raw_text="WHEN x THEN the system SHALL warn",
            span=Span("spec.md", 0, 33),
        )
        requirement = build_requirement(
            number=1,
            criteria=(criterion,),
            title="A title",
            user_story="As a developer, I want things",
        )
        return SpecDocument(name="demo", path="spec.md", requirements=(requirement,))

    @pytest.mark.verifies("REQ-6.5")
    def test_json_keys_are_sorted(self) -> None:
        rendered = to_json(self.build_document())
        payload = json.loads(rendered)
        assert list(payload) == sorted(payload)

    @pytest.mark.verifies("REQ-3.7")
    def test_json_carries_a_schema_version(self) -> None:
        payload = json.loads(to_json(self.build_document()))
        assert payload["schema_version"] >= 1

    @pytest.mark.verifies("REQ-6.6")
    def test_json_contains_no_timestamp(self) -> None:
        # A timestamp would make two identical parses appear different (REQ-6.6).
        rendered = to_json(self.build_document()).lower()
        for word in ("timestamp", "generated_at", "created_at"):
            assert word not in rendered

    @pytest.mark.verifies("REQ-6.1")
    def test_serialisation_is_byte_identical_across_runs(self) -> None:
        assert to_json(self.build_document()) == to_json(self.build_document())

    def test_enums_serialise_as_readable_strings(self) -> None:
        payload = json.loads(to_json(self.build_document()))
        criterion = payload["requirements"][0]["criteria"][0]
        assert criterion["modality"] == "SHALL"
        assert criterion["pattern"] == "event_driven"
        assert criterion["clauses"][0]["kind"] == "trigger"


class TestDocumentAccess:
    @pytest.mark.verifies("REQ-6.2")
    def test_criteria_flattens_in_requirement_then_position_order(self) -> None:
        def make(number: int, position: int) -> object:
            return build_criterion(
                requirement_number=number,
                position=position,
                clauses=(),
                subject="THE system",
                modality=Modality.SHALL,
                predicate="stop",
                raw_text="THE system SHALL stop",
                span=Span("spec.md", 0, 21),
            )

        document = SpecDocument(
            name="demo",
            path="spec.md",
            requirements=(
                build_requirement(number=1, criteria=(make(1, 1), make(1, 2))),  # type: ignore[arg-type]
                build_requirement(number=2, criteria=(make(2, 1),)),  # type: ignore[arg-type]
            ),
        )
        assert [c.id for c in document.criteria] == ["REQ-1.1", "REQ-1.2", "REQ-2.1"]

    def test_criterion_lookup_by_identifier(self) -> None:
        document = SpecDocument(
            name="demo",
            path="spec.md",
            requirements=(
                build_requirement(
                    number=1,
                    criteria=(
                        build_criterion(
                            requirement_number=1,
                            position=1,
                            clauses=(),
                            subject="THE system",
                            modality=Modality.SHALL,
                            predicate="stop",
                            raw_text="THE system SHALL stop",
                            span=Span("spec.md", 0, 21),
                        ),
                    ),
                ),
            ),
        )
        assert document.criterion_by_id("REQ-1.1") is not None
        assert document.criterion_by_id("REQ-9.9") is None
