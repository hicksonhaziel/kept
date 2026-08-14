"""Tokenise criterion text. Pure: string in, tokens out.

Structural keywords are recognised only in upper case, and a backtick-delimited
span is always ordinary text. See docs/adr/0001-uppercase-keywords.md.
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
_TRAILING_PUNCTUATION = ".,;:"


def lex(text: str) -> tuple[Token, ...]:
    """Tokenise `text`. Offsets are character indices into `text`."""
    tokens: list[Token] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char.isspace():
            index += 1
            continue

        if char == _COMMA:
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
    """Lex a backtick-delimited span as one WORD, spaces and keywords included.

    An unterminated backtick degrades to an ordinary word rather than erroring,
    so a stray backtick in prose cannot cost the author a criterion.
    """
    closing = text.find(_BACKTICK, start + 1)
    if closing == -1:
        return _lex_word(text, start)

    end = closing + 1
    return Token(TokenKind.WORD, text[start:end], start, end), end


def _lex_word(text: str, start: int) -> tuple[Token, int]:
    """Lex a run of non-space, non-comma characters.

    Trailing punctuation stays attached: the grammar never needs to see a full
    stop, and keeping it holds `raw_text` and the token stream in agreement.
    """
    index = start
    length = len(text)
    while index < length and not text[index].isspace() and text[index] != _COMMA:
        if text[index] == _BACKTICK and index > start:
            break
        index += 1

    word = text[start:index]
    return Token(KEYWORDS.get(word, TokenKind.WORD), word, start, index), index


def has_upper_case_modality(tokens: tuple[Token, ...]) -> bool:
    return any(token.kind in MODALITY_OPENERS for token in tokens)


def find_lowercase_modality(tokens: tuple[Token, ...]) -> Token | None:
    """Find the first word that looks like an uncapitalised modality, for W001."""
    for token in tokens:
        if token.kind is not TokenKind.WORD:
            continue
        if token.text.strip(_TRAILING_PUNCTUATION).lower() in LOWERCASE_MODALITY_HINTS:
            return token
    return None
