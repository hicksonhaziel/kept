"""Token kinds for the EARS grammar.

The keyword sets below are the whole basis of the grammar's decidability: clause
openers and modalities are disjoint, so the parser needs exactly one token of
lookahead and never backtracks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TokenKind(StrEnum):
    """What a token is.

    Structural keywords are recognised only when written entirely in upper case;
    see ADR-0001 and `lexer.lex`.
    """

    # Clause openers
    WHEN = "WHEN"
    WHILE = "WHILE"
    IF = "IF"
    WHERE = "WHERE"

    # Response separator
    THEN = "THEN"

    # Modalities and negation
    SHALL = "SHALL"
    SHOULD = "SHOULD"
    MAY = "MAY"
    MUST = "MUST"
    NOT = "NOT"

    # Logical operators
    AND = "AND"
    OR = "OR"

    # Non-keyword tokens
    COMMA = "COMMA"
    WORD = "WORD"
    EOF = "EOF"


@dataclass(frozen=True, slots=True)
class Token:
    """One lexical token, with its offsets into the text it was lexed from.

    `text` preserves the original spelling exactly, without case normalisation,
    so reports can quote the source verbatim (REQ-1.5).
    """

    kind: TokenKind
    text: str
    start: int
    end: int


#: Upper-case spelling to token kind. Membership in this mapping is what makes a
#: word structural; anything else lexes as an ordinary WORD.
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

#: Keywords that may begin a leading clause.
CLAUSE_OPENERS: frozenset[TokenKind] = frozenset(
    {TokenKind.WHEN, TokenKind.WHILE, TokenKind.IF, TokenKind.WHERE}
)

#: Keywords that begin a modality. A following NOT extends it into a negation.
MODALITY_OPENERS: frozenset[TokenKind] = frozenset(
    {TokenKind.SHALL, TokenKind.SHOULD, TokenKind.MAY, TokenKind.MUST}
)

#: Keywords that join conjuncts inside a clause body.
LOGICAL_OPERATORS: frozenset[TokenKind] = frozenset({TokenKind.AND, TokenKind.OR})

#: Tokens that terminate a clause body. A clause runs until the next structural
#: keyword or end of input, which is why the lexer must complete before parsing
#: rather than tokenising lazily.
CLAUSE_TERMINATORS: frozenset[TokenKind] = (
    CLAUSE_OPENERS | MODALITY_OPENERS | {TokenKind.THEN, TokenKind.EOF}
)

#: Lower-case spellings that suggest the author meant a modality but did not
#: capitalise it. Used only to raise W001; never to parse.
LOWERCASE_MODALITY_HINTS: frozenset[str] = frozenset({"shall", "should", "must", "may"})
