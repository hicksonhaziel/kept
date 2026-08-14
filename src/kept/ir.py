"""The typed intermediate representation for parsed specifications.

Everything downstream of parsing consumes this module and nothing else, so the
IR is the tool's internal contract. It is immutable: all types are frozen and
slotted, and sequence fields are tuples so values stay hashable and ordering is
explicit rather than incidental.

This module performs no I/O and reads no clock. It imports only `kept.ids`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from kept.ids import (
    HASH_ALGORITHM,
    SCHEMA_VERSION,
    content_hash,
    criterion_id,
    normalise_text,
    requirement_id,
)


class EarsPattern(StrEnum):
    """The EARS pattern a criterion follows.

    Derived from the clause list after parsing rather than decided during it, so
    classification is a pure function that can be tested without a parser.
    """

    UBIQUITOUS = "ubiquitous"
    EVENT_DRIVEN = "event_driven"
    STATE_DRIVEN = "state_driven"
    UNWANTED_BEHAVIOUR = "unwanted_behaviour"
    OPTIONAL_FEATURE = "optional_feature"
    COMPLEX = "complex"


class ClauseKind(StrEnum):
    """What a leading clause contributes to the criterion."""

    TRIGGER = "trigger"  # WHEN
    STATE = "state"  # WHILE
    UNWANTED = "unwanted"  # IF
    FEATURE = "feature"  # WHERE


class Modality(StrEnum):
    """The obligation the criterion places on the implementation."""

    SHALL = "SHALL"
    SHALL_NOT = "SHALL NOT"
    SHOULD = "SHOULD"
    SHOULD_NOT = "SHOULD NOT"
    MAY = "MAY"
    MUST = "MUST"
    MUST_NOT = "MUST NOT"


class LogicalOperator(StrEnum):
    """The operator joining conjuncts within a clause body."""

    AND = "AND"
    OR = "OR"


#: Modalities that oblige the implementation, and therefore admit a verdict.
#: A criterion that does not oblige cannot fairly be called broken (REQ-2.10).
NORMATIVE_MODALITIES: frozenset[Modality] = frozenset(
    {Modality.SHALL, Modality.SHALL_NOT, Modality.MUST, Modality.MUST_NOT}
)

#: Which pattern a single leading clause implies.
_SINGLE_CLAUSE_PATTERNS: dict[ClauseKind, EarsPattern] = {
    ClauseKind.TRIGGER: EarsPattern.EVENT_DRIVEN,
    ClauseKind.STATE: EarsPattern.STATE_DRIVEN,
    ClauseKind.UNWANTED: EarsPattern.UNWANTED_BEHAVIOUR,
    ClauseKind.FEATURE: EarsPattern.OPTIONAL_FEATURE,
}


def is_normative(modality: Modality) -> bool:
    """Whether the modality obliges the implementation (REQ-2.9, REQ-2.10)."""
    return modality in NORMATIVE_MODALITIES


def classify_pattern(kinds: Sequence[ClauseKind]) -> EarsPattern:
    """Classify a criterion from its leading clause kinds alone.

    No clauses is ubiquitous, exactly one maps to that clause's pattern, and two
    or more is complex (REQ-2.1 through REQ-2.6).
    """
    if not kinds:
        return EarsPattern.UBIQUITOUS
    if len(kinds) == 1:
        return _SINGLE_CLAUSE_PATTERNS[kinds[0]]
    return EarsPattern.COMPLEX


@dataclass(frozen=True, slots=True, order=True)
class Span:
    """A character range in a source file.

    Offsets index into the source *file*, not into the extracted criterion text,
    so a report can point at the exact line of `requirements.md` that made the
    promise. `source` is always repository-relative with forward slashes, so a
    span produced on one machine compares cleanly against one produced on
    another.
    """

    source: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            msg = f"span start must be >= 0, got {self.start}"
            raise ValueError(msg)
        if self.end < self.start:
            msg = f"span end {self.end} precedes start {self.start}"
            raise ValueError(msg)

    def shift(self, delta: int) -> Span:
        """Rebase this span by `delta` characters.

        Used to lift spans produced against an extracted criterion string up
        into coordinates of the file the criterion came from.
        """
        return Span(source=self.source, start=self.start + delta, end=self.end + delta)

    def slice_of(self, text: str) -> str:
        """Extract this span's text from the full source contents."""
        return text[self.start : self.end]

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "start": self.start, "end": self.end}


@dataclass(frozen=True, slots=True)
class Condition:
    """The body of a leading clause, with logical structure exposed.

    `conjuncts` holds the phrases joined by an upper-case `AND` or `OR`. A body
    containing only lower-case conjunctions yields a single conjunct, because
    lower-case "and" is prose rather than grammar (ADR-0001).
    """

    text: str
    conjuncts: tuple[str, ...]
    operator: LogicalOperator | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "conjuncts": list(self.conjuncts),
            "operator": str(self.operator) if self.operator is not None else None,
        }


@dataclass(frozen=True, slots=True)
class Clause:
    """One leading clause of a criterion."""

    kind: ClauseKind
    condition: Condition
    span: Span

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "condition": self.condition.to_dict(),
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Criterion:
    """One acceptance criterion: a single promise the code must keep."""

    id: str
    pattern: EarsPattern
    clauses: tuple[Clause, ...]
    subject: str
    modality: Modality
    predicate: str
    raw_text: str
    content_hash: str
    span: Span
    hash_algorithm: str = field(default=HASH_ALGORITHM)

    @property
    def is_normative(self) -> bool:
        return is_normative(self.modality)

    @property
    def text(self) -> str:
        """The criterion as a single line, continuation lines joined (REQ-4.5).

        `raw_text` is the verbatim source slice, newlines and indentation
        included, because token offsets are rebased onto it and any tidying would
        desynchronise the spans. This property is the tidied view for display.
        """
        return normalise_text(self.raw_text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern": str(self.pattern),
            "clauses": [clause.to_dict() for clause in self.clauses],
            "subject": self.subject,
            "modality": str(self.modality),
            "predicate": self.predicate,
            "is_normative": self.is_normative,
            "text": self.text,
            "raw_text": self.raw_text,
            "content_hash": self.content_hash,
            "hash_algorithm": self.hash_algorithm,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Requirement:
    """A numbered requirement and the criteria beneath it."""

    id: str
    number: int
    criteria: tuple[Criterion, ...]
    title: str | None = None
    user_story: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "user_story": self.user_story,
            "criteria": [criterion.to_dict() for criterion in self.criteria],
        }


@dataclass(frozen=True, slots=True)
class SpecDocument:
    """One `requirements.md` file, parsed."""

    name: str
    path: str
    requirements: tuple[Requirement, ...]

    @property
    def criteria(self) -> tuple[Criterion, ...]:
        """Every criterion in the document, ordered by requirement then position.

        Requirements are already stored in order, so this only needs to flatten
        (REQ-6.2).
        """
        return tuple(
            criterion for requirement in self.requirements for criterion in requirement.criteria
        )

    def criterion_by_id(self, criterion_id_: str) -> Criterion | None:
        for criterion in self.criteria:
            if criterion.id == criterion_id_:
                return criterion
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "path": self.path,
            "requirements": [requirement.to_dict() for requirement in self.requirements],
        }


def build_criterion(
    *,
    requirement_number: int,
    position: int,
    clauses: tuple[Clause, ...],
    subject: str,
    modality: Modality,
    predicate: str,
    raw_text: str,
    span: Span,
) -> Criterion:
    """Assemble a criterion, deriving its identifier, pattern, and hash.

    Centralised so that identity and classification cannot drift apart from each
    other across call sites.
    """
    return Criterion(
        id=criterion_id(requirement_number, position),
        pattern=classify_pattern(tuple(clause.kind for clause in clauses)),
        clauses=clauses,
        subject=subject,
        modality=modality,
        predicate=predicate,
        raw_text=raw_text,
        content_hash=content_hash(raw_text),
        span=span,
    )


def build_requirement(
    *,
    number: int,
    criteria: tuple[Criterion, ...],
    title: str | None = None,
    user_story: str | None = None,
) -> Requirement:
    return Requirement(
        id=requirement_id(number),
        number=number,
        criteria=criteria,
        title=title,
        user_story=user_story,
    )


def to_json(document: SpecDocument) -> str:
    """Serialise deterministically: sorted keys, no timestamps (REQ-6.5, REQ-6.6)."""
    return json.dumps(document.to_dict(), sort_keys=True, indent=2, ensure_ascii=False)
