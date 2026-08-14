"""The typed intermediate representation. Immutable, no I/O, no clock."""

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
    UBIQUITOUS = "ubiquitous"
    EVENT_DRIVEN = "event_driven"
    STATE_DRIVEN = "state_driven"
    UNWANTED_BEHAVIOUR = "unwanted_behaviour"
    OPTIONAL_FEATURE = "optional_feature"
    COMPLEX = "complex"


class ClauseKind(StrEnum):
    TRIGGER = "trigger"  # WHEN
    STATE = "state"  # WHILE
    UNWANTED = "unwanted"  # IF
    FEATURE = "feature"  # WHERE


class Modality(StrEnum):
    SHALL = "SHALL"
    SHALL_NOT = "SHALL NOT"
    SHOULD = "SHOULD"
    SHOULD_NOT = "SHOULD NOT"
    MAY = "MAY"
    MUST = "MUST"
    MUST_NOT = "MUST NOT"


class LogicalOperator(StrEnum):
    AND = "AND"
    OR = "OR"


# Only these oblige the implementation, so only these admit a verdict.
NORMATIVE_MODALITIES: frozenset[Modality] = frozenset(
    {Modality.SHALL, Modality.SHALL_NOT, Modality.MUST, Modality.MUST_NOT}
)

_SINGLE_CLAUSE_PATTERNS: dict[ClauseKind, EarsPattern] = {
    ClauseKind.TRIGGER: EarsPattern.EVENT_DRIVEN,
    ClauseKind.STATE: EarsPattern.STATE_DRIVEN,
    ClauseKind.UNWANTED: EarsPattern.UNWANTED_BEHAVIOUR,
    ClauseKind.FEATURE: EarsPattern.OPTIONAL_FEATURE,
}


def is_normative(modality: Modality) -> bool:
    return modality in NORMATIVE_MODALITIES


def classify_pattern(kinds: Sequence[ClauseKind]) -> EarsPattern:
    """Classify a criterion from its leading clause kinds alone."""
    if not kinds:
        return EarsPattern.UBIQUITOUS
    if len(kinds) == 1:
        return _SINGLE_CLAUSE_PATTERNS[kinds[0]]
    return EarsPattern.COMPLEX


@dataclass(frozen=True, slots=True, order=True)
class Span:
    """A character range in a source file.

    Offsets index into the source *file*, not into the extracted criterion text.
    `source` is always repository-relative with forward slashes.
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
        return Span(source=self.source, start=self.start + delta, end=self.end + delta)

    def slice_of(self, text: str) -> str:
        return text[self.start : self.end]

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "start": self.start, "end": self.end}


@dataclass(frozen=True, slots=True)
class Condition:
    """A clause body. `conjuncts` are the phrases joined by upper-case AND / OR."""

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
        """The criterion as a single line.

        `raw_text` stays the verbatim source slice because token offsets rebase
        onto it; tidying it would desynchronise every span.
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
    """Assemble a criterion, deriving its identifier, pattern, and hash together."""
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
    """Serialise deterministically: sorted keys, no timestamps."""
    return json.dumps(document.to_dict(), sort_keys=True, indent=2, ensure_ascii=False)
