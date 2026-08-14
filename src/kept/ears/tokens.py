"""Token kinds for the EARS grammar."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TokenKind(StrEnum):
    WHEN = "WHEN"
    WHILE = "WHILE"
    IF = "IF"
    WHERE = "WHERE"
    THEN = "THEN"
    SHALL = "SHALL"
    SHOULD = "SHOULD"
    MAY = "MAY"
    MUST = "MUST"
    NOT = "NOT"
    AND = "AND"
    OR = "OR"
    COMMA = "COMMA"
    WORD = "WORD"
    EOF = "EOF"


@dataclass(frozen=True, slots=True)
class Token:
    """One token. `text` preserves the original spelling, case included."""

    kind: TokenKind
    text: str
    start: int
    end: int


# Membership here is what makes a word structural. Upper case only; see
# docs/adr/0001-uppercase-keywords.md.
KEYWORDS: dict[str, TokenKind] = {
    "WHEN": TokenKind.WHEN,
    "WHILE": TokenKind.WHILE,
    "IF": TokenKind.IF,
    "WHERE": TokenKind.WHERE,
    "THEN": TokenKind.THEN,
    "SHALL": TokenKind.SHALL,
    "SHOULD": TokenKind.SHOULD,
    "MAY": TokenKind.MAY,
    "MUST": TokenKind.MUST,
    "NOT": TokenKind.NOT,
    "AND": TokenKind.AND,
    "OR": TokenKind.OR,
}

CLAUSE_OPENERS: frozenset[TokenKind] = frozenset(
    {TokenKind.WHEN, TokenKind.WHILE, TokenKind.IF, TokenKind.WHERE}
)

MODALITY_OPENERS: frozenset[TokenKind] = frozenset(
    {TokenKind.SHALL, TokenKind.SHOULD, TokenKind.MAY, TokenKind.MUST}
)

LOGICAL_OPERATORS: frozenset[TokenKind] = frozenset({TokenKind.AND, TokenKind.OR})

# A clause body runs until the next structural keyword, which is why the lexer
# must complete before parsing rather than tokenising lazily.
CLAUSE_TERMINATORS: frozenset[TokenKind] = (
    CLAUSE_OPENERS | MODALITY_OPENERS | {TokenKind.THEN, TokenKind.EOF}
)

# Used only to raise W001, never to parse.
LOWERCASE_MODALITY_HINTS: frozenset[str] = frozenset({"shall", "should", "must", "may"})
