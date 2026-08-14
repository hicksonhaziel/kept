"""The EARS front end: lexer, recursive-descent parser, and grammar diagnostics.

Nothing in this package reads a file. It receives strings and returns data, which
is what lets the grammar be tested with no fixtures on disk.
"""

from __future__ import annotations

from kept.ears.lexer import lex
from kept.ears.parser import ParseResult, parse_criterion

__all__ = ["ParseResult", "lex", "parse_criterion"]
