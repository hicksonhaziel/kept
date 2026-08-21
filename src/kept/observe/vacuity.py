"""Detect oracles that assert nothing.

A test that runs code and checks no outcome cannot verify a promise, however
green it looks. This is a syntactic check on purpose: it reports what is provably
absent, never a judgement about whether an assertion is any good.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# Context managers that make a test's expectation explicit without an `assert`.
_ASSERTING_CONTEXTS = frozenset({"raises", "warns", "deprecated_call"})


@dataclass(frozen=True, slots=True)
class OracleShape:
    """What a test function's body provably contains."""

    qualname: str
    asserts: int
    raises: int
    assert_calls: int

    @property
    def has_assertion(self) -> bool:
        return bool(self.asserts or self.raises or self.assert_calls)


def scan_source(source: str, *, path: str) -> dict[str, OracleShape]:
    """Map `path::qualname` to the shape of each test function in `source`.

    A file that does not parse yields nothing rather than raising: kept must not
    fall over on a target project's syntax error.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    shapes: dict[str, OracleShape] = {}
    for node, qualname in _walk_functions(tree):
        if not _looks_like_a_test(qualname):
            continue
        shape = _shape_of(node, qualname)
        shapes[f"{path}::{qualname.replace('.', '::')}"] = shape
    return shapes


def scan_files(root: Path, relative_paths: set[str]) -> dict[str, OracleShape]:
    """Scan the given test files, keyed so lookups match pytest node IDs."""
    shapes: dict[str, OracleShape] = {}
    for relative in sorted(relative_paths):
        path = root / relative
        if not path.is_file():
            continue
        shapes.update(scan_source(path.read_text(encoding="utf-8"), path=relative))
    return shapes


def _walk_functions(
    tree: ast.Module,
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]]:
    """Collect functions with their qualified names, following class nesting."""
    found: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                found.append((child, f"{prefix}{child.name}"))

    visit(tree, "")
    return found


def _looks_like_a_test(qualname: str) -> bool:
    return qualname.rpartition(".")[2].startswith("test")


def _shape_of(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    qualname: str,
) -> OracleShape:
    asserts = 0
    raises = 0
    assert_calls = 0

    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            asserts += 1
        elif isinstance(child, ast.With | ast.AsyncWith):
            raises += sum(1 for item in child.items if _is_asserting_context(item.context_expr))
        elif isinstance(child, ast.Call) and _is_assertion_call(child.func):
            assert_calls += 1

    return OracleShape(
        qualname=qualname,
        asserts=asserts,
        raises=raises,
        assert_calls=assert_calls,
    )


def _is_asserting_context(expression: ast.expr) -> bool:
    if not isinstance(expression, ast.Call):
        return False
    return _tail_name(expression.func) in _ASSERTING_CONTEXTS


def _is_assertion_call(func: ast.expr) -> bool:
    """Catch unittest-style and helper assertions, such as `assertEqual`."""
    name = _tail_name(func)
    return name is not None and name.startswith("assert")


def _tail_name(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Attribute):
        return expression.attr
    if isinstance(expression, ast.Name):
        return expression.id
    return None
