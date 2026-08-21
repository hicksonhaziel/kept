"""Identity and change detection."""

from __future__ import annotations

import pytest

from kept.ids import (
    HASH_ALGORITHM,
    content_hash,
    criterion_id,
    display_hash,
    normalise_text,
    requirement_id,
)


class TestNormalisation:
    @pytest.mark.verifies("REQ-3.3")
    def test_collapses_whitespace_runs_to_single_spaces(self) -> None:
        assert normalise_text("a   b\n\n  c") == "a b c"

    @pytest.mark.verifies("REQ-3.3")
    def test_strips_leading_and_trailing_whitespace(self) -> None:
        assert normalise_text("\n  padded  \t") == "padded"

    @pytest.mark.verifies("REQ-3.5")
    def test_preserves_case_because_case_is_semantically_significant(self) -> None:
        # Lower-casing would erase the difference between the logical operator
        # AND and the prose word "and". See ADR-0001.
        assert normalise_text("empty AND anonymous") == "empty AND anonymous"


class TestContentHash:
    @pytest.mark.verifies("REQ-3.4")
    def test_criteria_differing_only_in_line_wrapping_hash_identically(self) -> None:
        wrapped = "WHEN the cart is empty\n   THEN the system SHALL warn"
        single_line = "WHEN the cart is empty THEN the system SHALL warn"
        assert content_hash(wrapped) == content_hash(single_line)

    @pytest.mark.verifies("REQ-3.5")
    def test_a_single_character_edit_changes_the_hash(self) -> None:
        before = content_hash("THE system SHALL refund the order")
        after = content_hash("THE system SHALL refund the orders")
        assert before != after

    @pytest.mark.verifies("REQ-3.5")
    def test_case_change_changes_the_hash(self) -> None:
        assert content_hash("a AND b") != content_hash("a and b")

    @pytest.mark.verifies("REQ-3.3")
    def test_hash_is_a_full_sha256_hex_digest(self) -> None:
        digest = content_hash("anything")
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")

    @pytest.mark.verifies("REQ-3.6")
    def test_algorithm_name_is_recorded_so_a_change_is_not_mistaken_for_meaning(
        self,
    ) -> None:
        assert HASH_ALGORITHM == "sha256"

    @pytest.mark.verifies("REQ-3.6")
    def test_display_hash_truncates_without_altering_the_stored_digest(self) -> None:
        digest = content_hash("anything")
        assert display_hash(digest) == digest[:12]


class TestIdentifiers:
    @pytest.mark.verifies("REQ-3.1")
    def test_requirement_identifier_format(self) -> None:
        assert requirement_id(3) == "REQ-3"

    @pytest.mark.verifies("REQ-3.1")
    def test_criterion_identifier_format(self) -> None:
        assert criterion_id(3, 2) == "REQ-3.2"

    @pytest.mark.verifies("REQ-3.1")
    def test_identifiers_are_one_based(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            requirement_id(0)
        with pytest.raises(ValueError, match="must be >= 1"):
            criterion_id(1, 0)

    @pytest.mark.verifies("REQ-3.2")
    def test_position_is_scoped_to_its_requirement(self) -> None:
        # Inserting a criterion in requirement 3 must not disturb requirement 4,
        # which is what makes evidence survive an edit elsewhere (REQ-3.2).
        assert criterion_id(4, 1) == "REQ-4.1"
        assert criterion_id(3, 99) == "REQ-3.99"
