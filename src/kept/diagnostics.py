"""Diagnostics as values, so one bad line cannot abort a run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from kept.ir import Span


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


# Codes are part of the public contract: consumers filter on them, so they never
# change meaning. Register a code here before emitting it.
DIAGNOSTIC_CODES: dict[str, str] = {
    "E001": "criterion contains no recognisable modality and cannot be parsed",
    "E002": "clause keyword present with an empty body",
    "W001": "lower-case modality found and no upper-case modality present",
    "W002": "numbered item found with no requirement open, so it cannot be identified",
    "W003": "requirement heading carries no number; ordinal position assigned",
    "E003": "criterion identifier claimed by more than one specification",
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
            msg = f"unknown diagnostic code {self.code!r}; register it in DIAGNOSTIC_CODES"
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
    """Order by source, then position, then code, so output is deterministic."""
    span = diagnostic.span
    if span is None:
        return ("", -1, -1, diagnostic.code)
    return (span.source, span.start, span.end, diagnostic.code)
