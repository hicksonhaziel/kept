"""Discovery, the path boundary, and end-to-end loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from kept.ir import to_json
from kept.loader import (
    SpecNotFoundError,
    discover_spec_files,
    load_all,
    load_document,
    relative_posix,
)

SPEC_BODY = textwrap.dedent(
    """
    # Requirements Document

    ## Requirements

    ### Requirement 1: Refunds

    **User Story:** As a customer, I want refunds, so that I trust the shop.

    #### Acceptance Criteria

    1. WHEN a refund is requested THEN the system SHALL credit the original method
    2. THE system SHALL NOT refund more than the amount paid
    3. THE system SHOULD notify the customer by email
    """
).lstrip("\n")


def write_spec(root: Path, name: str, body: str = SPEC_BODY) -> Path:
    directory = root / ".kiro" / "specs" / name
    directory.mkdir(parents=True)
    path = directory / "requirements.md"
    path.write_text(body, encoding="utf-8")
    return path


class TestDiscovery:
    def test_finds_requirements_files_beneath_spec_directories(self, tmp_path: Path) -> None:
        write_spec(tmp_path, "refunds")
        write_spec(tmp_path, "invoicing")
        found = discover_spec_files(tmp_path)
        assert [path.parent.name for path in found] == ["invoicing", "refunds"]

    def test_discovery_order_is_deterministic(self, tmp_path: Path) -> None:
        for name in ("zeta", "alpha", "mu"):
            write_spec(tmp_path, name)
        assert discover_spec_files(tmp_path) == discover_spec_files(tmp_path)
        assert [p.parent.name for p in discover_spec_files(tmp_path)] == [
            "alpha",
            "mu",
            "zeta",
        ]

    def test_returns_nothing_when_there_is_no_specs_directory(self, tmp_path: Path) -> None:
        assert discover_spec_files(tmp_path) == ()

    def test_ignores_a_spec_directory_with_no_requirements_file(self, tmp_path: Path) -> None:
        (tmp_path / ".kiro" / "specs" / "empty").mkdir(parents=True)
        assert discover_spec_files(tmp_path) == ()

    def test_does_not_recurse_below_a_spec_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / ".kiro" / "specs" / "outer" / "inner"
        nested.mkdir(parents=True)
        (nested / "requirements.md").write_text(SPEC_BODY, encoding="utf-8")
        assert discover_spec_files(tmp_path) == ()


class TestPathBoundary:
    def test_paths_are_repository_relative_with_forward_slashes(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        assert relative_posix(path, tmp_path) == ".kiro/specs/refunds/requirements.md"

    def test_a_path_outside_the_root_degrades_to_its_name(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "elsewhere.md"
        assert relative_posix(outside, tmp_path) == "elsewhere.md"

    def test_no_absolute_path_reaches_the_document(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        result = load_document(path, root=tmp_path)
        rendered = to_json(result.documents[0])
        assert str(tmp_path) not in rendered


class TestLoading:
    def test_loads_criteria_with_identifiers_and_patterns(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        result = load_document(path, root=tmp_path)
        criteria = result.criteria
        assert [criterion.id for criterion in criteria] == [
            "REQ-1.1",
            "REQ-1.2",
            "REQ-1.3",
        ]

    def test_specification_name_comes_from_the_containing_directory(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        result = load_document(path, root=tmp_path)
        assert result.documents[0].name == "refunds"

    def test_the_user_story_is_carried_through(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        result = load_document(path, root=tmp_path)
        story = result.documents[0].requirements[0].user_story
        assert story is not None
        assert story.startswith("As a customer")

    def test_advisory_criteria_are_kept_but_marked(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        result = load_document(path, root=tmp_path)
        advisory = [c for c in result.criteria if not c.is_normative]
        assert [c.id for c in advisory] == ["REQ-1.3"]

    def test_a_missing_document_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SpecNotFoundError):
            load_document(tmp_path / "nope.md", root=tmp_path)

    def test_load_all_orders_documents_by_path(self, tmp_path: Path) -> None:
        write_spec(tmp_path, "zeta")
        write_spec(tmp_path, "alpha")
        result = load_all(tmp_path)
        assert [document.name for document in result.documents] == ["alpha", "zeta"]

    def test_load_all_on_an_empty_repository_is_not_an_error(self, tmp_path: Path) -> None:
        result = load_all(tmp_path)
        assert result.documents == ()
        assert result.errors == ()


class TestRequirementOrdering:
    def test_requirements_are_ordered_by_number_not_by_appearance(self, tmp_path: Path) -> None:
        body = textwrap.dedent(
            """
            ### Requirement 2

            #### Acceptance Criteria

            1. THE system SHALL do the second thing

            ### Requirement 1

            #### Acceptance Criteria

            1. THE system SHALL do the first thing
            """
        ).lstrip("\n")
        path = write_spec(tmp_path, "ordering", body)
        result = load_document(path, root=tmp_path)
        assert [r.number for r in result.documents[0].requirements] == [1, 2]
        assert [c.id for c in result.criteria] == ["REQ-1.1", "REQ-2.1"]


class TestDiagnosticsPropagation:
    def test_an_unparseable_criterion_does_not_stop_the_others(self, tmp_path: Path) -> None:
        body = textwrap.dedent(
            """
            ### Requirement 1

            #### Acceptance Criteria

            1. THE system SHALL do the first thing
            2. this line has no modality at all
            3. THE system SHALL do the third thing
            """
        ).lstrip("\n")
        path = write_spec(tmp_path, "partial", body)
        result = load_document(path, root=tmp_path)
        assert [c.id for c in result.criteria] == ["REQ-1.1", "REQ-1.3"]
        assert [d.code for d in result.errors] == ["E001"]

    def test_diagnostics_are_sorted_by_position(self, tmp_path: Path) -> None:
        body = textwrap.dedent(
            """
            ### Requirement 1

            #### Acceptance Criteria

            1. no modality here
            2. nor any modality here
            """
        ).lstrip("\n")
        path = write_spec(tmp_path, "sorted", body)
        result = load_document(path, root=tmp_path)
        starts = [d.span.start for d in result.diagnostics if d.span is not None]
        assert starts == sorted(starts)


class TestDeterminism:
    def test_loading_twice_yields_equal_documents(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        first = load_document(path, root=tmp_path)
        second = load_document(path, root=tmp_path)
        assert first == second

    def test_loading_twice_yields_byte_identical_json(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        first = to_json(load_document(path, root=tmp_path).documents[0])
        second = to_json(load_document(path, root=tmp_path).documents[0])
        assert first == second


class TestSpanRoundTrip:
    def test_every_span_slices_back_to_its_criterion(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        text = path.read_text(encoding="utf-8")
        result = load_document(path, root=tmp_path)
        for criterion in result.criteria:
            assert criterion.span.slice_of(text) == criterion.raw_text

    def test_every_clause_span_slices_back_to_its_clause(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "refunds")
        text = path.read_text(encoding="utf-8")
        result = load_document(path, root=tmp_path)
        for criterion in result.criteria:
            for clause in criterion.clauses:
                recovered = clause.span.slice_of(text)
                assert recovered.startswith(("WHEN", "WHILE", "IF", "WHERE"))
