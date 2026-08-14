"""Extract acceptance criteria from a `requirements.md` document.

A line-oriented scanner holding a small explicit state machine, tracking the
character offset of every line so that spans stay accurate.

Deliberately **not** a general Markdown parser. The grammar of a requirements
document is narrow, a real Markdown dependency would pull in an AST this tool
does not need, and character-accurate offsets are far easier to guarantee with a
line scanner than to recover from a syntax tree afterwards.

Pure: takes the document text and a path, returns data. No I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto

from kept.diagnostics import Diagnostic, Severity
from kept.ir import Span

#: An ATX heading: leading hashes, then the heading text.
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

#: "Requirement 3", "Requirement 3: Title", "Requirement 3 - Title".
_REQUIREMENT_HEADING = re.compile(
    # The en and em dashes are deliberate, not typos: authors and editors really
    # do separate a heading title with them, and refusing to match would cost the
    # author every criterion beneath the heading.
    r"^requirement\s+(\d+)\s*(?:[:.\-–—]\s*(?P<title>.*))?$",  # noqa: RUF001
    re.IGNORECASE,
)

#: A heading that names a requirement but carries no number.
_UNNUMBERED_REQUIREMENT_HEADING = re.compile(r"^requirement\b\s*(?P<title>.*)$", re.IGNORECASE)

#: The heading that opens a list of criteria. Matched at any depth.
_CRITERIA_HEADING = re.compile(r"^acceptance\s+criteria\b", re.IGNORECASE)

#: A numbered list item: "1. text" or "1) text", optionally indented.
_NUMBERED_ITEM = re.compile(r"^(?P<indent>\s*)(?P<marker>\d+[.)])\s+(?P<body>.*)$")

#: "**User Story:** As a …" in any of the usual spellings.
_USER_STORY = re.compile(r"^\**\s*user\s+story\s*:?\**\s*(?P<body>.*)$", re.IGNORECASE)

#: A fenced code block delimiter: three or more backticks or tildes.
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


class _State(Enum):
    """Where the scanner is in the document."""

    SEEKING_REQUIREMENT = auto()
    IN_REQUIREMENT = auto()
    IN_CRITERIA = auto()


@dataclass(frozen=True, slots=True)
class RawCriterion:
    """One criterion as extracted, before the grammar sees it.

    `text` is the verbatim source slice described by `span`, continuation lines
    and their indentation included, so that token offsets rebase cleanly onto
    file coordinates.
    """

    text: str
    span: Span
    requirement_number: int
    position: int


@dataclass(frozen=True, slots=True)
class RawRequirement:
    """One requirement heading and the criteria beneath it."""

    number: int
    title: str | None
    user_story: str | None
    criteria: tuple[RawCriterion, ...]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Everything recovered from one document, plus what went wrong."""

    requirements: tuple[RawRequirement, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(slots=True)
class _RequirementBuilder:
    """Mutable accumulator for a requirement while the scanner is inside it."""

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
    """A criterion being accumulated across continuation lines."""

    start: int
    end: int
    indent: int
    position: int


def extract(text: str, *, source: str) -> ExtractionResult:
    """Extract raw criteria from a requirements document.

    Args:
        text: The full contents of the document.
        source: The document's repository-relative path, recorded in every span.
    """
    scanner = _Scanner(text=text, source=source)
    return scanner.run()


class _Scanner:
    """The line scanner. Kept as a class purely to avoid threading nine locals."""

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
            stripped = line.rstrip("\r\n")
            self._handle_line(stripped, offset)
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
            marker = fence.group(1)
            if self._in_fence:
                # Only a matching delimiter closes the fence, so a tilde fence
                # inside a backtick fence cannot end it early.
                if marker[0] == self._fence_marker[0]:
                    self._in_fence = False
                    self._fence_marker = ""
            else:
                self._in_fence = True
                self._fence_marker = marker
            self._flush_pending()
            return

        if self._in_fence:
            # A numbered list inside a code fence is sample text, never a
            # criterion (REQ-4.9).
            return

        heading = _HEADING.match(line)
        if heading is not None:
            self._handle_heading(heading.group(2), offset, len(line))
            return

        if self._state is _State.IN_CRITERIA:
            self._handle_criteria_line(line, offset)
            return

        if self._state is _State.IN_REQUIREMENT:
            self._handle_requirement_body(line)

    def _handle_heading(self, heading_text: str, offset: int, line_length: int) -> None:
        self._flush_pending()

        if _CRITERIA_HEADING.match(heading_text):
            # Entered even with no requirement open, so that stray items are
            # reported as W002 rather than silently vanishing.
            self._state = _State.IN_CRITERIA
            return

        numbered = _REQUIREMENT_HEADING.match(heading_text)
        if numbered is not None:
            self._begin_requirement(
                number=int(numbered.group(1)),
                title=_clean_title(numbered.group("title")),
            )
            return

        unnumbered = _UNNUMBERED_REQUIREMENT_HEADING.match(heading_text)
        if unnumbered is not None:
            number = self._next_ordinal
            self._begin_requirement(
                number=number,
                title=_clean_title(unnumbered.group("title")),
            )
            self._diagnostics.append(
                Diagnostic(
                    code="W003",
                    severity=Severity.WARNING,
                    message=(
                        f"Requirement heading carries no number; assigned "
                        f"ordinal position {number}. Number the heading "
                        f"explicitly, as 'Requirement {number}', so that "
                        f"criterion identifiers survive reordering."
                    ),
                    span=Span(self._source, offset, offset + line_length),
                )
            )
            return

        # Any other heading ends the criteria list but leaves the requirement
        # open, so a "Notes" subsection cannot swallow subsequent numbered items.
        if self._state is _State.IN_CRITERIA:
            self._state = _State.IN_REQUIREMENT

    def _begin_requirement(self, *, number: int, title: str | None) -> None:
        self._flush_requirement()
        self._builder = _RequirementBuilder(number=number, title=title)
        self._state = _State.IN_REQUIREMENT
        self._next_ordinal = max(self._next_ordinal, number) + 1

    def _handle_requirement_body(self, line: str) -> None:
        if self._builder is None or self._builder.user_story is not None:
            return
        story = _USER_STORY.match(line.strip())
        if story is not None:
            # Recorded as prose; never handed to the grammar (REQ-4.7).
            body = story.group("body").strip().strip("*").strip()
            self._builder.user_story = body or None

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
                            "Numbered item found outside any requirement. Place "
                            "it beneath a 'Requirement <number>' heading so it "
                            "can be given a stable identifier."
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
            # A blank line ends a criterion. Anything after it that is not a
            # numbered item is prose, not a continuation.
            self._flush_pending()
            return

        indent = len(line) - len(line.lstrip())
        if indent > self._pending.indent:
            # An indented, non-blank, non-item line continues the criterion
            # (REQ-4.5). The span is extended rather than the text being
            # concatenated, so offsets stay exact.
            self._pending.end = offset + len(line.rstrip())
            return

        self._flush_pending()

    def _flush_pending(self) -> None:
        if self._pending is None or self._builder is None:
            self._pending = None
            return

        pending = self._pending
        self._pending = None
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


def _clean_title(title: str | None) -> str | None:
    if title is None:
        return None
    cleaned = title.strip().strip("*").strip()
    return cleaned or None
