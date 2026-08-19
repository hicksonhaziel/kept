"""Render a ledger as an SVG badge. Pure: no network, no shields.io."""

from __future__ import annotations

from kept.ledger import Ledger
from kept.verdict import Verdict

_GREEN = "#2ea043"
_AMBER = "#d29922"
_RED = "#cf222e"
_GREY = "#6e7681"
_LABEL_BACKGROUND = "#3f4551"

#: Approximate advance width per character for the 11px font, used to size the
#: badge without measuring glyphs. Slightly generous, so text never clips.
_CHARACTER_WIDTH = 6.4
_PADDING = 10.0


def render(ledger: Ledger) -> str:
    """Build a self-contained badge. No external requests, so it works offline."""
    counts = ledger.counts
    message, colour = _status(ledger, counts)
    return _svg(label="promises kept", message=message, colour=colour)


def _status(ledger: Ledger, counts: dict[str, int]) -> tuple[str, str]:
    total = ledger.promises
    if total == 0:
        return "none found", _GREY

    kept = counts[str(Verdict.KEPT)]
    message = f"{kept}/{total}"

    if counts[str(Verdict.BROKEN)]:
        return f"{message} · {counts[str(Verdict.BROKEN)]} broken", _RED
    if kept == total:
        return message, _GREEN
    if counts[str(Verdict.WEAK)] or counts[str(Verdict.UNPROVEN)]:
        return message, _AMBER
    return message, _GREY


def _svg(*, label: str, message: str, colour: str) -> str:
    label_width = _text_width(label)
    message_width = _text_width(message)
    total = label_width + message_width

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total:.0f}" height="20" '
        f'role="img" aria-label="{label}: {message}">'
        f"<title>{label}: {message}</title>"
        f'<linearGradient id="s" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/>'
        f"</linearGradient>"
        f'<clipPath id="r"><rect width="{total:.0f}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)">'
        f'<rect width="{label_width:.0f}" height="20" fill="{_LABEL_BACKGROUND}"/>'
        f'<rect x="{label_width:.0f}" width="{message_width:.0f}" height="20" fill="{colour}"/>'
        f'<rect width="{total:.0f}" height="20" fill="url(#s)"/>'
        f"</g>"
        f'<g fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{label_width / 2:.0f}" y="14">{label}</text>'
        f'<text x="{label_width + message_width / 2:.0f}" y="14">{message}</text>'
        f"</g></svg>\n"
    )


def _text_width(text: str) -> float:
    return len(text) * _CHARACTER_WIDTH + 2 * _PADDING
