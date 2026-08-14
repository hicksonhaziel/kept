"""Diagnostics as values, not exceptions.

Real specifications contain prose, tables, and half-finished sentences. One
unparseable line must never prevent the other two hundred criteria from being
verified, so problems are collected and returned alongside results rather than
raised.

Every diagnostic carries a stable machine-readable code and a message phrased as
the corrective action to take, not merely the symptom observed (REQ-5.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from kept.ir import Span


class Severity(StrEnum):
    """Whether a diagnostic blocks understanding or merely warns."""

    ERROR = "error"
    WARNING = "warning"


# Single source of truth for every code the tool can emit. Codes are part of the
# public contract: consumers filter on them, so they never change meaning.
DIAGNOSTIC_CODES: dict[str, str] = {
    "E001": "criterion contains no recognisable modality and cannot be parsed",
    "E002": "clause keyword present with an empty body",
    "W001": "lower-case modality found and no upper-case modality present",
    "W002": "numbered item found with no requirement open, so it cannot be identified",
    "W003": "requirement heading carries no number; ordinal position assigned",
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One problem found while reading a specification."""

    code: str
    severity: Severity
    message: str
    span: Span | None = None

    def __post_init__(self) -> None:
        if self.code not in DIAGNOSTIC_CODES:
            msg = (
                f"unknown diagnostic code {self.code!r}; "
                f"register it in DIAGNOSTIC_CODES before use"
            )
            raise ValueError(msg)

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": str(self.severity),
            "message": self.message,
            "span": self.span.to_dict() if self.span is not None else None,
        }


def sort_key(diagnostic: Diagnostic) -> tuple[str, int, int, str]:
    """Deterministic ordering for diagnostics in output.

    Diagnostics are sorted by source, then position, then code, so that two runs
    over the same input serialise identically regardless of the order in which
    the scanner happened to discover the problems.
    """
    span = diagnostic.span
    if span is None:
        return ("", -1, -1, diagnostic.code)
    return (span.source, span.start, span.end, diagnostic.code)
