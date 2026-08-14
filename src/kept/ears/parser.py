"""Recursive-descent parser for EARS acceptance criteria.

    criterion   ::= clause_list? response
    clause_list ::= clause ( ","? clause )*
    clause      ::= ( "WHEN" | "WHILE" | "IF" | "WHERE" ) condition
    condition   ::= conjunct ( ( "AND" | "OR" ) conjunct )*
    conjunct    ::= ( WORD | COMMA )+
    response    ::= "THEN"? subject modality predicate
    subject     ::= ( WORD | COMMA )*
    modality    ::= ( "SHALL" | "SHOULD" | "MAY" | "MUST" ) "NOT"?
    predicate   ::= token*

One token of lookahead, no backtracking: clause openers and modality openers are
disjoint, so every production is decidable from the current token.
"""

from __future__ import annotations

from dataclasses import dataclass

from kept.diagnostics import Diagnostic
from kept.ears import errors
from kept.ears.lexer import find_lowercase_modality, has_upper_case_modality, lex
from kept.ears.tokens import (
    CLAUSE_OPENERS,
    CLAUSE_TERMINATORS,
    LOGICAL_OPERATORS,
    MODALITY_OPENERS,
    Token,
    TokenKind,
)
from kept.ids import normalise_text
from kept.ir import (
    Clause,
    ClauseKind,
    Condition,
    Criterion,
    LogicalOperator,
    Modality,
    Span,
    build_criterion,
)

_CLAUSE_KINDS: dict[TokenKind, ClauseKind] = {
    TokenKind.WHEN: ClauseKind.TRIGGER,
    TokenKind.WHILE: ClauseKind.STATE,
    TokenKind.IF: ClauseKind.UNWANTED,
    TokenKind.WHERE: ClauseKind.FEATURE,
}

# `MAY NOT` maps to MAY on purpose: in requirements prose it is ambiguous between
# prohibition and absence of obligation, so the negation is left in the predicate
# rather than guessed at.
_MODALITIES: dict[tuple[TokenKind, bool], Modality] = {
    (TokenKind.SHALL, False): Modality.SHALL,
    (TokenKind.SHALL, True): Modality.SHALL_NOT,
    (TokenKind.SHOULD, False): Modality.SHOULD,
    (TokenKind.SHOULD, True): Modality.SHOULD_NOT,
    (TokenKind.MAY, False): Modality.MAY,
    (TokenKind.MAY, True): Modality.MAY,
    (TokenKind.MUST, False): Modality.MUST,
    (TokenKind.MUST, True): Modality.MUST_NOT,
}


@dataclass(frozen=True, slots=True)
class ParseResult:
    """`criterion` is None only when nothing usable could be recovered."""

    criterion: Criterion | None
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def has_errors(self) -> bool:
        return any(diagnostic.is_error for diagnostic in self.diagnostics)


class _Cursor:
    """A position in the token stream with one token of lookahead."""

    __slots__ = ("_index", "_tokens")

    def __init__(self, tokens: tuple[Token, ...]) -> None:
        self._tokens = tokens
        self._index = 0

    @property
    def current(self) -> Token:
        return self._tokens[self._index]

    @property
    def at_end(self) -> bool:
        return self.current.kind is TokenKind.EOF

    def advance(self) -> Token:
        token = self._tokens[self._index]
        if token.kind is not TokenKind.EOF:
            self._index += 1
        return token

    def accept(self, kind: TokenKind) -> Token | None:
        if self.current.kind is kind:
            return self.advance()
        return None

    def take_until(self, terminators: frozenset[TokenKind]) -> tuple[Token, ...]:
        collected: list[Token] = []
        while self.current.kind not in terminators and not self.at_end:
            collected.append(self.advance())
        return tuple(collected)


def parse_criterion(
    text: str,
    *,
    requirement_number: int,
    position: int,
    span: Span,
) -> ParseResult:
    """Parse one acceptance criterion into the IR.

    Args:
        text: The criterion verbatim, including internal newlines. It must be the
            exact slice described by `span`, because token offsets are rebased
            onto `span.start`.
        requirement_number: One-based number of the enclosing requirement.
        position: One-based position of this criterion within that requirement.
        span: Where this criterion lives in its source file.
    """
    tokens = lex(text)
    diagnostics: list[Diagnostic] = []

    cursor = _Cursor(tokens)
    clauses = _parse_clause_list(cursor, text, span, diagnostics)
    cursor.accept(TokenKind.THEN)

    response = _parse_response(cursor, text)
    if response is None:
        diagnostics.append(errors.no_modality(text, span))
        if not has_upper_case_modality(tokens):
            hint = find_lowercase_modality(tokens)
            if hint is not None:
                diagnostics.append(errors.lowercase_modality(hint.text, _rebase(hint, span)))
        return ParseResult(criterion=None, diagnostics=tuple(diagnostics))

    subject, modality, predicate = response
    criterion = build_criterion(
        requirement_number=requirement_number,
        position=position,
        clauses=clauses,
        subject=subject,
        modality=modality,
        predicate=predicate,
        raw_text=text,
        span=span,
    )
    return ParseResult(criterion=criterion, diagnostics=tuple(diagnostics))


def _parse_clause_list(
    cursor: _Cursor,
    text: str,
    span: Span,
    diagnostics: list[Diagnostic],
) -> tuple[Clause, ...]:
    clauses: list[Clause] = []

    while cursor.current.kind in CLAUSE_OPENERS:
        opener = cursor.advance()
        body = _strip_commas(cursor.take_until(CLAUSE_TERMINATORS))

        if not body:
            diagnostics.append(errors.empty_clause_body(opener.text, _rebase(opener, span)))
            continue

        clauses.append(
            Clause(
                kind=_CLAUSE_KINDS[opener.kind],
                condition=_build_condition(body, text),
                span=Span(
                    source=span.source,
                    start=span.start + opener.start,
                    end=span.start + body[-1].end,
                ),
            )
        )

    return tuple(clauses)


def _parse_response(cursor: _Cursor, text: str) -> tuple[str, Modality, str] | None:
    """Parse subject, modality, and predicate. None when no modality is present."""
    subject_tokens = cursor.take_until(MODALITY_OPENERS)
    if cursor.current.kind not in MODALITY_OPENERS:
        return None

    modality_token = cursor.advance()
    negated = cursor.accept(TokenKind.NOT) is not None
    modality = _MODALITIES[(modality_token.kind, negated)]
    predicate_tokens = cursor.take_until(frozenset({TokenKind.EOF}))

    return _slice_text(subject_tokens, text), modality, _slice_text(predicate_tokens, text)


def _build_condition(body: tuple[Token, ...], text: str) -> Condition:
    """Split a clause body on upper-case AND / OR only.

    A body mixing AND and OR has genuinely ambiguous precedence, so it is recorded
    as one conjunct rather than given a structure the author did not write.
    """
    operator_tokens = [token for token in body if token.kind in LOGICAL_OPERATORS]
    body_text = normalise_text(_slice_text(body, text))

    if not operator_tokens or len({token.kind for token in operator_tokens}) > 1:
        return Condition(text=body_text, conjuncts=(body_text,), operator=None)

    conjuncts: list[str] = []
    segment: list[Token] = []
    for token in body:
        if token.kind in LOGICAL_OPERATORS:
            conjuncts.append(normalise_text(_slice_text(tuple(segment), text)))
            segment = []
        else:
            segment.append(token)
    conjuncts.append(normalise_text(_slice_text(tuple(segment), text)))

    return Condition(
        text=body_text,
        conjuncts=tuple(part for part in conjuncts if part),
        operator=LogicalOperator(operator_tokens[0].text),
    )


def _strip_commas(tokens: tuple[Token, ...]) -> tuple[Token, ...]:
    start = 0
    end = len(tokens)
    while start < end and tokens[start].kind is TokenKind.COMMA:
        start += 1
    while end > start and tokens[end - 1].kind is TokenKind.COMMA:
        end -= 1
    return tokens[start:end]


def _slice_text(tokens: tuple[Token, ...], text: str) -> str:
    """Recover the original text spanned by `tokens`.

    Slicing rather than rejoining token text keeps punctuation spacing faithful to
    the source and stops spans drifting from the text they describe.
    """
    if not tokens:
        return ""
    return normalise_text(text[tokens[0].start : tokens[-1].end])


def _rebase(token: Token, span: Span) -> Span:
    """Lift a token's offsets into coordinates of the source file."""
    return Span(source=span.source, start=span.start + token.start, end=span.start + token.end)
