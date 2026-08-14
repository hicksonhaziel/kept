"""Shared test helpers.

Deliberately thin. The front end is pure, so almost every test constructs its
input inline rather than reaching for a fixture on disk.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from kept.ears.parser import ParseResult, parse_criterion
from kept.ir import Criterion, Span

#: The repository root, derived from this file's location so the suite works from
#: any working directory.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Every test span starts here rather than at zero. If it started at zero,
#: `span.start + token.start` would equal `token.start` and a missing rebase
#: would pass unnoticed.
BASE_OFFSET = 1000


def make_span(text: str, *, source: str = "spec.md", start: int = BASE_OFFSET) -> Span:
    """A span describing `text` as if it sat at `start` in `source`."""
    return Span(source=source, start=start, end=start + len(text))


@pytest.fixture
def parse() -> Callable[[str], ParseResult]:
    """Parse one criterion at requirement 1, position 1."""

    def _parse(text: str) -> ParseResult:
        return parse_criterion(
            text,
            requirement_number=1,
            position=1,
            span=make_span(text),
        )

    return _parse


@pytest.fixture
def parsed() -> Callable[[str], Criterion]:
    """Parse one criterion and assert it was understood, returning the IR.

    For the many tests that care about a parsed field rather than about failure
    handling.
    """

    def _parsed(text: str) -> Criterion:
        result = parse_criterion(
            text,
            requirement_number=1,
            position=1,
            span=make_span(text),
        )
        assert result.criterion is not None, (
            f"expected {text!r} to parse; diagnostics: "
            f"{[d.message for d in result.diagnostics]}"
        )
        return result.criterion

    return _parsed


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT
