"""Tokenise criterion text.

The rule that matters, restated because everything depends on it: a structural
keyword is recognised **only when written entirely in upper case**, and a span
enclosed in backticks is always ordinary text. Together these let a
specification describe its own notation without the parser mistaking description
for use. See ADR-0001.

Pure: takes a string, returns tokens. No I/O.
"""

from __future__ import annotations

from kept.ears.tokens import (
    KEYWORDS,
    LOWERCASE_MODALITY_HINTS,
    MODALITY_OPENERS,
    Token,
    TokenKind,
)

_BACKTICK = "`"
_COMMA = ","

#: Punctuation stripped before comparing a word against the modality hints, so
#: that a trailing full stop does not hide an uncapitalised "shall."
_TRAILING_PUNCTUATION = ".,;:"


def lex(text: str) -> tuple[Token, ...]:
    """Tokenise `text`, returning tokens ending in exactly one EOF (REQ-1.6).

    Offsets are character indices into `text` (REQ-1.3). Callers that need file
    coordinates rebase the resulting spans; the lexer knows nothing about files.
    """
    tokens: list[Token] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char.isspace():
            index += 1
            continue

        if char == _COMMA:
            # A comma is its own separator rather than luggage on an adjacent
            # word, so clause bodies can contain lists (REQ-1.4).
            tokens.append(Token(TokenKind.COMMA, _COMMA, index, index + 1))
            index += 1
            continue

        if char == _BACKTICK:
            token, index = _lex_backtick_span(text, index)
            tokens.append(token)
            continue

        token, index = _lex_word(text, index)
        tokens.append(token)

    tokens.append(Token(TokenKind.EOF, "", length, length))
    return tuple(tokens)


def _lex_backtick_span(text: str, start: int) -> tuple[Token, int]:
    """Lex a backtick-delimited span as one WORD token (REQ-1.8).

    The enclosed text may contain spaces and upper-case keywords; neither makes
    it structural. An unterminated backtick degrades to an ordinary word rather
    than becoming an error, because a stray backtick in prose should not cost the
    author a criterion.
    """
    closing = text.find(_BACKTICK, start + 1)
    if closing == -1:
        return _lex_word(text, start)

    end = closing + 1
    return Token(TokenKind.WORD, text[start:end], start, end), end


def _lex_word(text: str, start: int) -> tuple[Token, int]:
    """Lex a run of non-space, non-comma characters.

    Trailing punctuation stays attached to the word. That is deliberate: the
    grammar never needs to see a full stop, and preserving it keeps `raw_text`
    and the token stream in agreement so spans stay trustworthy.
    """
    index = start
    length = len(text)
    while index < length and not text[index].isspace() and text[index] != _COMMA:
        # A backtick begins a quoted span, which is lexed separately. Stopping
        # here keeps `foo`bar` from swallowing the delimiter.
        if text[index] == _BACKTICK and index > start:
            break
        index += 1

    word = text[start:index]
    kind = KEYWORDS.get(word, TokenKind.WORD)
    return Token(kind, word, start, index), index


def has_upper_case_modality(tokens: tuple[Token, ...]) -> bool:
    """Whether any token is an upper-case modality keyword."""
    return any(token.kind in MODALITY_OPENERS for token in tokens)


def find_lowercase_modality(tokens: tuple[Token, ...]) -> Token | None:
    """Find the first word that looks like an uncapitalised modality.

    Used only to raise W001 when no real modality is present (REQ-1.7). The
    result never influences parsing: guessing at the author's intent would defeat
    the point of having an unambiguous grammar in the first place.
    """
    for token in tokens:
        if token.kind is not TokenKind.WORD:
            continue
        bare = token.text.strip(_TRAILING_PUNCTUATION).lower()
        if bare in LOWERCASE_MODALITY_HINTS:
            return token
    return None
