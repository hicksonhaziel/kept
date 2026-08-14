"""Grammar diagnostic factories, so each code is worded identically everywhere."""

from __future__ import annotations

from kept.diagnostics import Diagnostic, Severity
from kept.ir import Span

_QUOTE_LIMIT = 60


def _quote(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _QUOTE_LIMIT:
        return collapsed
    return collapsed[: _QUOTE_LIMIT - 1] + "…"


def no_modality(text: str, span: Span) -> Diagnostic:
    return Diagnostic(
        code="E001",
        severity=Severity.ERROR,
        message=(
            f"Criterion has no recognisable modality: {_quote(text)!r}. "
            f"Rewrite it so the obligation is explicit and upper case, for example "
            f"'THE system SHALL …' or 'WHEN <trigger> THEN the system SHALL …'."
        ),
        span=span,
    )


def empty_clause_body(keyword: str, span: Span) -> Diagnostic:
    return Diagnostic(
        code="E002",
        severity=Severity.ERROR,
        message=(
            f"The {keyword} clause has an empty body. Give {keyword} a condition, or "
            f"remove the keyword. If you are quoting the word {keyword} rather than "
            f"using it, enclose it in backticks so it is read as ordinary text."
        ),
        span=span,
    )


def lowercase_modality(word: str, span: Span) -> Diagnostic:
    return Diagnostic(
        code="W001",
        severity=Severity.WARNING,
        message=(
            f"Found the lower-case word {word!r} where a modality was expected. "
            f"EARS modalities are written in upper case; change it to "
            f"{word.upper()!r} so the criterion can be parsed."
        ),
        span=span,
    )
