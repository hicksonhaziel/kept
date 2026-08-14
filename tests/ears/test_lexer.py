"""The lexer, and the case rule the whole grammar rests on."""

from __future__ import annotations

from kept.ears.lexer import find_lowercase_modality, has_upper_case_modality, lex
from kept.ears.tokens import TokenKind


def kinds(text: str) -> list[TokenKind]:
    return [token.kind for token in lex(text)]


class TestKeywordRecognition:
    def test_upper_case_keywords_become_structural_tokens(self) -> None:
        assert kinds("WHEN WHILE IF WHERE THEN SHALL SHOULD MAY MUST NOT AND OR") == [
            TokenKind.WHEN,
            TokenKind.WHILE,
            TokenKind.IF,
            TokenKind.WHERE,
            TokenKind.THEN,
            TokenKind.SHALL,
            TokenKind.SHOULD,
            TokenKind.MAY,
            TokenKind.MUST,
            TokenKind.NOT,
            TokenKind.AND,
            TokenKind.OR,
            TokenKind.EOF,
        ]

    def test_lower_case_keywords_are_ordinary_words(self) -> None:
        assert kinds("when while if where then shall and or") == [TokenKind.WORD] * 8 + [
            TokenKind.EOF
        ]

    def test_mixed_case_keywords_are_ordinary_words(self) -> None:
        assert kinds("When Shall AnD") == [TokenKind.WORD] * 3 + [TokenKind.EOF]

    def test_uppercase_and_is_an_operator_but_lowercase_and_is_prose(self) -> None:
        # The distinction the whole grammar depends on. See ADR-0001.
        assert TokenKind.AND in kinds("empty AND anonymous")
        assert TokenKind.AND not in kinds("a name and email address")


class TestOffsetsAndSpelling:
    def test_every_token_records_its_character_offsets(self) -> None:
        text = "THE system SHALL refund"
        for token in lex(text):
            if token.kind is TokenKind.EOF:
                continue
            assert text[token.start : token.end] == token.text

    def test_original_spelling_is_preserved_without_case_normalisation(self) -> None:
        tokens = lex("The Refund Service")
        assert [token.text for token in tokens[:-1]] == ["The", "Refund", "Service"]

    def test_eof_offsets_sit_at_the_end_of_the_input(self) -> None:
        text = "THE system SHALL stop"
        eof = lex(text)[-1]
        assert eof.start == eof.end == len(text)


class TestSeparators:
    def test_a_comma_is_its_own_token_not_luggage_on_a_word(self) -> None:
        tokens = lex("empty, anonymous")
        assert [token.kind for token in tokens] == [
            TokenKind.WORD,
            TokenKind.COMMA,
            TokenKind.WORD,
            TokenKind.EOF,
        ]
        assert tokens[0].text == "empty"

    def test_exactly_one_end_of_input_token_is_emitted(self) -> None:
        assert [token.kind for token in lex("a b c")].count(TokenKind.EOF) == 1

    def test_empty_input_yields_only_end_of_input(self) -> None:
        assert kinds("") == [TokenKind.EOF]

    def test_whitespace_only_input_yields_only_end_of_input(self) -> None:
        assert kinds("   \n\t ") == [TokenKind.EOF]


class TestBacktickSpans:
    def test_a_backticked_keyword_is_an_ordinary_word(self) -> None:
        # This is the case that this component's own requirements document
        # exposed: a criterion describing WHEN was parsed as one using WHEN.
        tokens = lex("begins with a `WHEN` clause")
        assert TokenKind.WHEN not in [token.kind for token in tokens]

    def test_a_backticked_span_may_contain_spaces(self) -> None:
        tokens = lex("the modality is `SHALL NOT` here")
        texts = [token.text for token in tokens]
        assert "`SHALL NOT`" in texts
        assert TokenKind.NOT not in [token.kind for token in tokens]

    def test_backtick_span_offsets_cover_the_delimiters(self) -> None:
        text = "quoting `SHALL` here"
        quoted = next(token for token in lex(text) if token.text.startswith("`"))
        assert text[quoted.start : quoted.end] == "`SHALL`"

    def test_an_unterminated_backtick_degrades_to_an_ordinary_word(self) -> None:
        # A stray backtick in prose should not cost the author a criterion.
        tokens = lex("a `stray backtick")
        assert [token.kind for token in tokens] == [TokenKind.WORD] * 3 + [TokenKind.EOF]

    def test_a_backtick_span_is_not_swallowed_by_a_preceding_word(self) -> None:
        texts = [token.text for token in lex("see`WHEN`now")]
        assert texts[:-1] == ["see", "`WHEN`", "now"]


class TestModalityHelpers:
    def test_detects_an_upper_case_modality(self) -> None:
        assert has_upper_case_modality(lex("THE system SHALL stop"))
        assert not has_upper_case_modality(lex("the system shall stop"))

    def test_finds_an_uncapitalised_modality_for_the_warning(self) -> None:
        found = find_lowercase_modality(lex("the system shall stop"))
        assert found is not None
        assert found.text == "shall"

    def test_finds_an_uncapitalised_modality_despite_trailing_punctuation(self) -> None:
        found = find_lowercase_modality(lex("the system must, always, stop"))
        assert found is not None
        assert found.text == "must"

    def test_returns_none_when_no_modality_is_suggested(self) -> None:
        assert find_lowercase_modality(lex("nothing here at all")) is None
