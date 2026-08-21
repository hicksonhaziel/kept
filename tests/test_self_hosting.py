"""kept parses its own specification.

The spec is the parser's first fixture. If the tool cannot read the document that
defines it, it has no business reading anyone else's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kept.ir import to_json
from kept.loader import load_all, load_document

#: Criteria per requirement in `.kiro/specs/ears-parser/requirements.md`.
#: Asserted exactly, so that adding a criterion without updating the tests is a
#: visible event rather than a silent drift.
EXPECTED_COUNTS = {1: 8, 2: 15, 3: 7, 4: 9, 5: 6, 6: 6}


def spec_path(repo_root: Path) -> Path:
    return repo_root / ".kiro" / "specs" / "ears-parser" / "requirements.md"


class TestOwnSpecification:
    @pytest.mark.verifies("REQ-5.1")
    def test_the_specification_parses_with_no_errors(self, repo_root: Path) -> None:
        result = load_document(spec_path(repo_root), root=repo_root)
        assert [d.message for d in result.errors] == []

    def test_every_requirement_has_the_expected_number_of_criteria(self, repo_root: Path) -> None:
        result = load_document(spec_path(repo_root), root=repo_root)
        counts = {r.number: len(r.criteria) for r in result.documents[0].requirements}
        assert counts == EXPECTED_COUNTS

    def test_all_own_criteria_are_normative(self, repo_root: Path) -> None:
        # Every promise kept makes about itself obliges the implementation.
        result = load_document(spec_path(repo_root), root=repo_root)
        advisory = [c.id for c in result.criteria if not c.is_normative]
        assert advisory == []

    def test_every_ears_pattern_appears_in_the_specification(self, repo_root: Path) -> None:
        # A grammar claiming five patterns should exercise them on itself.
        result = load_document(spec_path(repo_root), root=repo_root)
        patterns = {str(c.pattern) for c in result.criteria}
        assert {"ubiquitous", "event_driven", "unwanted_behaviour", "optional_feature"} <= (
            patterns
        )

    @pytest.mark.verifies("REQ-4.6")
    def test_every_span_slices_back_to_its_criterion(self, repo_root: Path) -> None:
        path = spec_path(repo_root)
        text = path.read_text(encoding="utf-8")
        result = load_document(path, root=repo_root)
        for criterion in result.criteria:
            assert criterion.span.slice_of(text) == criterion.raw_text

    @pytest.mark.verifies("REQ-3.1")
    def test_identifiers_are_unique(self, repo_root: Path) -> None:
        result = load_document(spec_path(repo_root), root=repo_root)
        ids = [c.id for c in result.criteria]
        assert len(ids) == len(set(ids))


class TestDeterminism:
    @pytest.mark.verifies("REQ-6.1")
    def test_parsing_the_repository_twice_is_byte_identical(self, repo_root: Path) -> None:
        first = [to_json(d) for d in load_all(repo_root).documents]
        second = [to_json(d) for d in load_all(repo_root).documents]
        assert first == second

    @pytest.mark.verifies("REQ-4.1")
    def test_load_all_finds_the_specification(self, repo_root: Path) -> None:
        result = load_all(repo_root)
        assert "ears-parser" in {document.name for document in result.documents}
