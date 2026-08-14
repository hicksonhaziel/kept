"""Grammar diagnostics.

Factory functions rather than raw `Diagnostic` construction, so that every
message for a given code is worded identically wherever it is raised, and so the
wording lives in one place when it needs improving.

Messages state the corrective action, not merely the symptom (REQ-5.4).
"""

from __future__ import annotations

from kept.diagnostics import Diagnostic, Severity
from kept.ir import Span

#: Truncation length for quoting offending text back to the author. Long enough
#: to identify the line, short enough not to flood a terminal.
_QUOTE_LIMIT = 60


def _quote(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _QUOTE_LIMIT:
        return collapsed
    return collapsed[: _QUOTE_LIMIT - 1] + "…"


def no_modality(text: str, span: Span) -> Diagnostic:
    """E001 — the criterion has no upper-case modality, so it cannot be parsed."""
    return Diagnostic(
        code="E001",
        severity=Severity.ERROR,
        message=(
            f"Criterion has no recognisable modality: {_quote(text)!r}. "
            f"Rewrite it so the obligation is explicit and upper case, "
            f"for example 'THE system SHALL …' or "
            f"'WHEN <trigger> THEN the system SHALL …'."
        ),
        span=span,
    )


def empty_clause_body(keyword: str, span: Span) -> Diagnostic:
    """E002 — a clause opener with nothing between it and the next keyword."""
    return Diagnostic(
        code="E002",
        severity=Severity.ERROR,
        message=(
            f"The {keyword} clause has an empty body. "
            f"Give {keyword} a condition, or remove the keyword. "
            f"If you are quoting the word {keyword} rather than using it, "
            f"enclose it in backticks so it is read as ordinary text."
        ),
        span=span,
    )


def lowercase_modality(word: str, span: Span) -> Diagnostic:
    """W001 — a lower-case modality with no upper-case modality anywhere."""
    return Diagnostic(
        code="W001",
        severity=Severity.WARNING,
        message=(
            f"Found the lower-case word {word!r} where a modality was expected. "
            f"EARS modalities are written in upper case; "
            f"change it to {word.upper()!r} so the criterion can be parsed."
        ),
        span=span,
    )
