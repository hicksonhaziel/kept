"""Markdown extraction: structure, continuations, spans, and what to ignore."""

from __future__ import annotations

import textwrap

from kept.markdown import extract

SOURCE = "spec.md"


def document(body: str) -> str:
    return textwrap.dedent(body).lstrip("\n")


class TestStructure:
    def test_extracts_a_numbered_requirement_with_its_criteria(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1: Refunds

                #### Acceptance Criteria

                1. THE system SHALL refund the order
                2. THE system SHALL record the refund
                """
            ),
            source=SOURCE,
        )
        assert len(result.requirements) == 1
        requirement = result.requirements[0]
        assert requirement.number == 1
        assert requirement.title == "Refunds"
        assert len(requirement.criteria) == 2

    def test_criterion_positions_are_one_based_and_scoped_to_the_requirement(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 4

                #### Acceptance Criteria

                1. THE system SHALL do the first thing
                2. THE system SHALL do the second thing
                """
            ),
            source=SOURCE,
        )
        criteria = result.requirements[0].criteria
        assert [c.position for c in criteria] == [1, 2]
        assert {c.requirement_number for c in criteria} == {4}

    def test_a_title_separated_by_a_dash_is_captured(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 2 - Invoicing

                #### Acceptance Criteria

                1. THE system SHALL issue an invoice
                """
            ),
            source=SOURCE,
        )
        assert result.requirements[0].title == "Invoicing"

    def test_a_requirement_without_a_title_records_none(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 7

                #### Acceptance Criteria

                1. THE system SHALL stop
                """
            ),
            source=SOURCE,
        )
        assert result.requirements[0].title is None

    def test_multiple_requirements_are_kept_separate(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL do one thing

                ### Requirement 2

                #### Acceptance Criteria

                1. THE system SHALL do another thing
                """
            ),
            source=SOURCE,
        )
        assert [r.number for r in result.requirements] == [1, 2]
        assert all(len(r.criteria) == 1 for r in result.requirements)


class TestUserStories:
    def test_a_user_story_is_recorded_as_prose(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                **User Story:** As a developer, I want traceability, so that I can trust the ledger.

                #### Acceptance Criteria

                1. THE system SHALL trace every criterion
                """
            ),
            source=SOURCE,
        )
        story = result.requirements[0].user_story
        assert story is not None
        assert story.startswith("As a developer")

    def test_a_user_story_is_not_treated_as_a_criterion(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                **User Story:** As a developer, I want things

                #### Acceptance Criteria

                1. THE system SHALL do one thing
                """
            ),
            source=SOURCE,
        )
        assert len(result.requirements[0].criteria) == 1


class TestContinuations:
    def test_an_indented_line_continues_the_previous_criterion(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. WHEN the cart is empty THEN the system SHALL
                   display a warning to the customer
                """
            ),
            source=SOURCE,
        )
        criteria = result.requirements[0].criteria
        assert len(criteria) == 1
        assert "display a warning" in criteria[0].text

    def test_a_blank_line_ends_a_criterion(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL stop

                   This indented prose is not part of the criterion.
                """
            ),
            source=SOURCE,
        )
        criteria = result.requirements[0].criteria
        assert len(criteria) == 1
        assert "indented prose" not in criteria[0].text

    def test_an_unindented_line_ends_a_criterion(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL stop
                Trailing prose at column zero.
                """
            ),
            source=SOURCE,
        )
        assert "Trailing prose" not in result.requirements[0].criteria[0].text


class TestWhatIsIgnored:
    def test_a_numbered_list_inside_a_code_fence_is_not_a_criterion(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL stop

                ```
                1. THE system SHALL do something that is only sample text
                ```
                """
            ),
            source=SOURCE,
        )
        criteria = result.requirements[0].criteria
        assert len(criteria) == 1
        assert "sample text" not in criteria[0].text

    def test_a_tilde_fence_also_hides_its_contents(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL stop

                ~~~
                1. THE system SHALL be ignored
                ~~~
                """
            ),
            source=SOURCE,
        )
        assert len(result.requirements[0].criteria) == 1

    def test_prose_and_tables_outside_a_criteria_list_are_ignored(self) -> None:
        result = extract(
            document(
                """
                ## Introduction

                Some prose that mentions THE system SHALL do things.

                | column | column |
                |---|---|
                | a | b |

                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL stop
                """
            ),
            source=SOURCE,
        )
        assert len(result.requirements) == 1
        assert len(result.requirements[0].criteria) == 1

    def test_a_later_heading_closes_the_criteria_list(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL stop

                #### Notes

                1. This numbered item is not a criterion.
                """
            ),
            source=SOURCE,
        )
        assert len(result.requirements[0].criteria) == 1


class TestDiagnostics:
    def test_an_unnumbered_requirement_heading_gets_an_ordinal_and_w003(self) -> None:
        result = extract(
            document(
                """
                ### Requirement: Refunds

                #### Acceptance Criteria

                1. THE system SHALL refund
                """
            ),
            source=SOURCE,
        )
        assert result.requirements[0].number == 1
        assert [d.code for d in result.diagnostics] == ["W003"]

    def test_the_w003_message_tells_the_author_to_number_the_heading(self) -> None:
        result = extract(
            document(
                """
                ### Requirement: Refunds

                #### Acceptance Criteria

                1. THE system SHALL refund
                """
            ),
            source=SOURCE,
        )
        assert "Number the heading" in result.diagnostics[0].message

    def test_an_ordinal_does_not_collide_with_a_later_explicit_number(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL do one thing

                ### Requirement: Unnumbered

                #### Acceptance Criteria

                1. THE system SHALL do another thing
                """
            ),
            source=SOURCE,
        )
        assert [r.number for r in result.requirements] == [1, 2]

    def test_a_numbered_item_with_no_requirement_yields_w002(self) -> None:
        result = extract(
            document(
                """
                #### Acceptance Criteria

                1. THE system SHALL float free of any requirement
                """
            ),
            source=SOURCE,
        )
        # Reported rather than silently dropped: an item with no requirement
        # cannot be given a stable identifier.
        assert result.requirements == ()
        assert [d.code for d in result.diagnostics] == ["W002"]


class TestSpans:
    def test_a_span_slices_back_to_the_criterion_text(self) -> None:
        text = document(
            """
            ### Requirement 1

            #### Acceptance Criteria

            1. WHEN the cart is empty THEN the system SHALL warn
            2. THE system SHALL record the event
            """
        )
        result = extract(text, source=SOURCE)
        for criterion in result.requirements[0].criteria:
            assert criterion.span.slice_of(text) == criterion.text

    def test_a_span_excludes_the_list_marker(self) -> None:
        text = document(
            """
            ### Requirement 1

            #### Acceptance Criteria

            1. THE system SHALL stop
            """
        )
        result = extract(text, source=SOURCE)
        criterion = result.requirements[0].criteria[0]
        assert criterion.text == "THE system SHALL stop"
        assert not criterion.span.slice_of(text).startswith("1.")

    def test_a_multi_line_span_covers_every_continuation_line(self) -> None:
        text = document(
            """
            ### Requirement 1

            #### Acceptance Criteria

            1. WHEN the cart is empty THEN the system SHALL
               display a warning
            """
        )
        result = extract(text, source=SOURCE)
        criterion = result.requirements[0].criteria[0]
        assert criterion.span.slice_of(text) == criterion.text
        assert "\n" in criterion.text

    def test_every_span_carries_the_source_path(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1. THE system SHALL stop
                """
            ),
            source="a/b/spec.md",
        )
        assert result.requirements[0].criteria[0].span.source == "a/b/spec.md"


class TestParenthesisedMarkers:
    def test_a_closing_parenthesis_marker_is_accepted(self) -> None:
        result = extract(
            document(
                """
                ### Requirement 1

                #### Acceptance Criteria

                1) THE system SHALL stop
                """
            ),
            source=SOURCE,
        )
        assert len(result.requirements[0].criteria) == 1
