"""Extract acceptance criteria from a `requirements.md` document.

A line scanner rather than a real Markdown parser: the document grammar is narrow,
and character-accurate offsets are easier to guarantee here than to recover from a
syntax tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto

from kept.diagnostics import Diagnostic, Severity
from kept.ir import Span

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

# The en and em dashes are deliberate: authors really do separate a heading title
# with them, and refusing to match would drop every criterion beneath the heading.
_REQUIREMENT_HEADING = re.compile(
    r"^requirement\s+(\d+)\s*(?:[:.\-–—]\s*(?P<title>.*))?$",  # noqa: RUF001
    re.IGNORECASE,
)
_UNNUMBERED_REQUIREMENT_HEADING = re.compile(r"^requirement\b\s*(?P<title>.*)$", re.IGNORECASE)
_CRITERIA_HEADING = re.compile(r"^acceptance\s+criteria\b", re.IGNORECASE)
_NUMBERED_ITEM = re.compile(r"^(?P<indent>\s*)(?P<marker>\d+[.)])\s+(?P<body>.*)$")
_USER_STORY = re.compile(r"^\**\s*user\s+story\s*:?\**\s*(?P<body>.*)$", re.IGNORECASE)
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


class _State(Enum):
    SEEKING_REQUIREMENT = auto()
    IN_REQUIREMENT = auto()
    IN_CRITERIA = auto()


@dataclass(frozen=True, slots=True)
class RawCriterion:
    """One criterion as extracted. `text` is the verbatim slice `span` describes."""

    text: str
    span: Span
    requirement_number: int
    position: int


@dataclass(frozen=True, slots=True)
class RawRequirement:
    number: int
    title: str | None
    user_story: str | None
    criteria: tuple[RawCriterion, ...]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    requirements: tuple[RawRequirement, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(slots=True)
class _RequirementBuilder:
    number: int
    title: str | None
    user_story: str | None = None
    criteria: list[RawCriterion] = field(default_factory=list)

    def build(self) -> RawRequirement:
        return RawRequirement(
            number=self.number,
            title=self.title,
            user_story=self.user_story,
            criteria=tuple(self.criteria),
        )


@dataclass(slots=True)
class _PendingCriterion:
    start: int
    end: int
    indent: int
    position: int


def extract(text: str, *, source: str) -> ExtractionResult:
    """Extract raw criteria. `source` is the repository-relative path for spans."""
    return _Scanner(text=text, source=source).run()


class _Scanner:
    __slots__ = (
        "_builder",
        "_diagnostics",
        "_fence_marker",
        "_in_fence",
        "_next_ordinal",
        "_pending",
        "_requirements",
        "_source",
        "_state",
        "_text",
    )

    def __init__(self, *, text: str, source: str) -> None:
        self._text = text
        self._source = source
        self._state = _State.SEEKING_REQUIREMENT
        self._requirements: list[RawRequirement] = []
        self._builder: _RequirementBuilder | None = None
        self._pending: _PendingCriterion | None = None
        self._diagnostics: list[Diagnostic] = []
        self._in_fence = False
        self._fence_marker = ""
        self._next_ordinal = 1

    def run(self) -> ExtractionResult:
        offset = 0
        for line in self._text.splitlines(keepends=True):
            self._handle_line(line.rstrip("\r\n"), offset)
            offset += len(line)

        self._flush_pending()
        self._flush_requirement()
        return ExtractionResult(
            requirements=tuple(self._requirements),
            diagnostics=tuple(self._diagnostics),
        )

    def _handle_line(self, line: str, offset: int) -> None:
        fence = _FENCE.match(line)
        if fence is not None:
            self._toggle_fence(fence.group(1))
            self._flush_pending()
            return

        if self._in_fence:
            return

        heading = _HEADING.match(line)
        if heading is not None:
            self._handle_heading(heading.group(2), offset, len(line))
            return

        if self._state is _State.IN_CRITERIA:
            self._handle_criteria_line(line, offset)
        elif self._state is _State.IN_REQUIREMENT:
            self._handle_requirement_body(line)

    def _toggle_fence(self, marker: str) -> None:
        if not self._in_fence:
            self._in_fence = True
            self._fence_marker = marker
        elif marker[0] == self._fence_marker[0]:
            # Only a matching delimiter closes the fence, so a tilde run inside a
            # backtick fence cannot end it early.
            self._in_fence = False
            self._fence_marker = ""

    def _handle_heading(self, heading_text: str, offset: int, line_length: int) -> None:
        self._flush_pending()

        if _CRITERIA_HEADING.match(heading_text):
            # Entered even with no requirement open, so stray items become W002
            # rather than vanishing.
            self._state = _State.IN_CRITERIA
            return

        numbered = _REQUIREMENT_HEADING.match(heading_text)
        if numbered is not None:
            self._begin_requirement(int(numbered.group(1)), _clean(numbered.group("title")))
            return

        unnumbered = _UNNUMBERED_REQUIREMENT_HEADING.match(heading_text)
        if unnumbered is not None:
            number = self._next_ordinal
            self._begin_requirement(number, _clean(unnumbered.group("title")))
            self._diagnostics.append(
                Diagnostic(
                    code="W003",
                    severity=Severity.WARNING,
                    message=(
                        f"Requirement heading carries no number; assigned ordinal "
                        f"position {number}. Number the heading explicitly, as "
                        f"'Requirement {number}', so criterion identifiers survive "
                        f"reordering."
                    ),
                    span=Span(self._source, offset, offset + line_length),
                )
            )
            return

        # Any other heading closes the criteria list but leaves the requirement
        # open, so a "Notes" subsection cannot swallow later numbered items.
        if self._state is _State.IN_CRITERIA:
            self._state = _State.IN_REQUIREMENT

    def _begin_requirement(self, number: int, title: str | None) -> None:
        self._flush_requirement()
        self._builder = _RequirementBuilder(number=number, title=title)
        self._state = _State.IN_REQUIREMENT
        self._next_ordinal = max(self._next_ordinal, number) + 1

    def _handle_requirement_body(self, line: str) -> None:
        if self._builder is None or self._builder.user_story is not None:
            return
        story = _USER_STORY.match(line.strip())
        if story is not None:
            self._builder.user_story = _clean(story.group("body"))

    def _handle_criteria_line(self, line: str, offset: int) -> None:
        item = _NUMBERED_ITEM.match(line)
        if item is not None:
            self._flush_pending()
            if self._builder is None:
                self._diagnostics.append(
                    Diagnostic(
                        code="W002",
                        severity=Severity.WARNING,
                        message=(
                            "Numbered item found outside any requirement. Place it "
                            "beneath a 'Requirement <number>' heading so it can be "
                            "given a stable identifier."
                        ),
                        span=Span(self._source, offset, offset + len(line)),
                    )
                )
                return

            body_start = offset + item.start("body")
            self._pending = _PendingCriterion(
                start=body_start,
                end=body_start + len(item.group("body")),
                indent=len(item.group("indent")),
                position=len(self._builder.criteria) + 1,
            )
            return

        if self._pending is None:
            return

        if not line.strip():
            self._flush_pending()
            return

        if len(line) - len(line.lstrip()) > self._pending.indent:
            # An indented continuation extends the span rather than concatenating
            # text, so offsets stay exact.
            self._pending.end = offset + len(line.rstrip())
            return

        self._flush_pending()

    def _flush_pending(self) -> None:
        pending, self._pending = self._pending, None
        if pending is None or self._builder is None:
            return

        raw = self._text[pending.start : pending.end]
        if not raw.strip():
            return

        self._builder.criteria.append(
            RawCriterion(
                text=raw,
                span=Span(self._source, pending.start, pending.end),
                requirement_number=self._builder.number,
                position=pending.position,
            )
        )

    def _flush_requirement(self) -> None:
        if self._builder is not None:
            self._requirements.append(self._builder.build())
            self._builder = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().strip("*").strip() or None
