"""Mutation operators over a concrete syntax tree.

Sites are enumerated in a fixed traversal order and addressed by index, so
generating the list of mutations and applying one of them are the same walk done
twice. Determinism comes from that, not from sorting afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import libcst as cst
from libcst.metadata import PositionProvider

# Arithmetic and bitwise swaps. Each maps to the operator most likely to change
# behaviour while keeping the expression valid.
_BINARY: dict[type[cst.BaseBinaryOp], type[cst.BaseBinaryOp]] = {
    cst.Add: cst.Subtract,
    cst.Subtract: cst.Add,
    cst.Multiply: cst.Divide,
    cst.Divide: cst.Multiply,
    cst.FloorDivide: cst.Multiply,
    cst.Modulo: cst.Multiply,
}

_COMPARISON: dict[type[cst.BaseCompOp], tuple[type[cst.BaseCompOp], ...]] = {
    cst.LessThan: (cst.LessThanEqual, cst.GreaterThan),
    cst.LessThanEqual: (cst.LessThan, cst.GreaterThanEqual),
    cst.GreaterThan: (cst.GreaterThanEqual, cst.LessThan),
    cst.GreaterThanEqual: (cst.GreaterThan, cst.LessThanEqual),
    cst.Equal: (cst.NotEqual,),
    cst.NotEqual: (cst.Equal,),
}

_BOOLEAN: dict[type[cst.BaseBooleanOp], type[cst.BaseBooleanOp]] = {
    cst.And: cst.Or,
    cst.Or: cst.And,
}

_SYMBOL: dict[type[Any], str] = {
    cst.Add: "+",
    cst.Subtract: "-",
    cst.Multiply: "*",
    cst.Divide: "/",
    cst.FloorDivide: "//",
    cst.Modulo: "%",
    cst.LessThan: "<",
    cst.LessThanEqual: "<=",
    cst.GreaterThan: ">",
    cst.GreaterThanEqual: ">=",
    cst.Equal: "==",
    cst.NotEqual: "!=",
    cst.And: "and",
    cst.Or: "or",
}


@dataclass(frozen=True, slots=True)
class Mutation:
    """One available change to the source."""

    index: int
    line: int
    operator: str
    description: str


class MutationPass(cst.CSTTransformer):
    """Enumerates mutation sites, and applies one when `target` names it.

    With `target=None` the pass only collects. With `target=n` it also replaces
    site `n`. Both modes count sites identically up to `n`, which is what keeps
    an index meaning the same thing across the two calls.
    """

    METADATA_DEPENDENCIES: ClassVar[tuple[type[PositionProvider]]] = (PositionProvider,)

    def __init__(self, target: int | None = None) -> None:
        super().__init__()
        self.mutations: list[Mutation] = []
        self._target = target
        self._next = 0

    # --- site bookkeeping ------------------------------------------------

    def _site(self, node: cst.CSTNode, operator: str, description: str) -> bool:
        """Record a site and report whether it is the one to mutate."""
        index = self._next
        self._next += 1
        position = self.get_metadata(PositionProvider, node)
        self.mutations.append(
            Mutation(
                index=index,
                line=position.start.line,
                operator=operator,
                description=description,
            )
        )
        return self._target == index

    # --- operators ------------------------------------------------------

    def leave_BinaryOperation(
        self, original_node: cst.BinaryOperation, updated_node: cst.BinaryOperation
    ) -> cst.BaseExpression:
        replacement = _BINARY.get(type(original_node.operator))
        if replacement is None:
            return updated_node
        described = f"{_symbol(original_node.operator)} to {_symbol(replacement())}"
        if self._site(original_node, "arithmetic", described):
            return updated_node.with_changes(operator=replacement())
        return updated_node

    def leave_Comparison(
        self, original_node: cst.Comparison, updated_node: cst.Comparison
    ) -> cst.BaseExpression:
        if len(original_node.comparisons) != 1:
            # Chained comparisons such as `a < b < c` are left alone: swapping one
            # link changes the expression in ways that are hard to describe honestly.
            return updated_node

        target = original_node.comparisons[0]
        for replacement in _COMPARISON.get(type(target.operator), ()):
            described = f"{_symbol(target.operator)} to {_symbol(replacement())}"
            if self._site(original_node, "comparison", described):
                return updated_node.with_changes(
                    comparisons=[updated_node.comparisons[0].with_changes(operator=replacement())]
                )
        return updated_node

    def leave_BooleanOperation(
        self, original_node: cst.BooleanOperation, updated_node: cst.BooleanOperation
    ) -> cst.BaseExpression:
        replacement = _BOOLEAN.get(type(original_node.operator))
        if replacement is None:
            return updated_node
        described = f"{_symbol(original_node.operator)} to {_symbol(replacement())}"
        if self._site(original_node, "boolean", described):
            return updated_node.with_changes(operator=replacement())
        return updated_node

    def leave_UnaryOperation(
        self, original_node: cst.UnaryOperation, updated_node: cst.UnaryOperation
    ) -> cst.BaseExpression:
        if not isinstance(original_node.operator, cst.Not):
            return updated_node
        if self._site(original_node, "negation", "remove not"):
            return updated_node.expression
        return updated_node

    def leave_Integer(
        self, original_node: cst.Integer, updated_node: cst.Integer
    ) -> cst.BaseExpression:
        try:
            value = int(original_node.value, 0)
        except ValueError:
            return updated_node

        for replacement in _integer_variants(value):
            described = f"{value} to {replacement}"
            if self._site(original_node, "literal", described):
                return cst.Integer(value=str(replacement))
        return updated_node

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.BaseExpression:
        flipped = {"True": "False", "False": "True"}.get(original_node.value)
        if flipped is None:
            return updated_node
        if self._site(original_node, "literal", f"{original_node.value} to {flipped}"):
            return cst.Name(value=flipped)
        return updated_node

    def leave_Return(
        self, original_node: cst.Return, updated_node: cst.Return
    ) -> cst.BaseSmallStatement:
        value = original_node.value
        if value is None or (isinstance(value, cst.Name) and value.value == "None"):
            return updated_node
        if self._site(original_node, "return", "return None instead"):
            return updated_node.with_changes(value=cst.Name("None"))
        return updated_node

    def leave_If(self, original_node: cst.If, updated_node: cst.If) -> Any:
        for literal in ("True", "False"):
            if self._site(original_node, "guard", f"condition forced to {literal}"):
                return updated_node.with_changes(test=cst.Name(literal))
        return updated_node

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.BaseStatement:
        """Replace a whole body with `return None`.

        The stub detector. A surviving stub means the criterion's tests never
        check what this function produces, only that calling it does not explode.
        """
        first = _first_body_statement(original_node)
        if first is None or _is_trivial_body(original_node):
            return updated_node

        if self._site(first, "stub", f"body of {original_node.name.value} replaced by return None"):
            return updated_node.with_changes(
                body=cst.IndentedBlock(
                    body=[cst.SimpleStatementLine(body=[cst.Return(value=cst.Name("None"))])]
                )
            )
        return updated_node


def collect(source: str) -> tuple[Mutation, ...]:
    """List every mutation available in `source`."""
    wrapper = cst.MetadataWrapper(cst.parse_module(source))
    walk = MutationPass()
    wrapper.visit(walk)
    return tuple(walk.mutations)


def apply(source: str, index: int) -> str:
    """Return `source` with mutation `index` applied."""
    wrapper = cst.MetadataWrapper(cst.parse_module(source))
    walk = MutationPass(target=index)
    mutated = wrapper.visit(walk)
    return mutated.code


def _integer_variants(value: int) -> tuple[int, ...]:
    """Variants that are guaranteed to differ from the original."""
    candidates = (0, 1, value + 1)
    seen: list[int] = []
    for candidate in candidates:
        if candidate != value and candidate not in seen:
            seen.append(candidate)
    return tuple(seen)


def _symbol(operator: Any) -> str:
    return _SYMBOL.get(type(operator), type(operator).__name__)


def _first_body_statement(node: cst.FunctionDef) -> cst.CSTNode | None:
    """The first statement inside the body.

    Used as the mutation's line rather than the `def` line, because `def` executes
    at import time and so never appears in a test's coverage context.
    """
    body = node.body
    if isinstance(body, cst.IndentedBlock) and body.body:
        return body.body[0]
    if isinstance(body, cst.SimpleStatementSuite) and body.body:
        return body.body[0]
    return None


def _is_trivial_body(node: cst.FunctionDef) -> bool:
    """Whether stubbing this body would produce an identical function."""
    body = node.body
    if not isinstance(body, cst.IndentedBlock) or len(body.body) != 1:
        return False

    only = body.body[0]
    if not isinstance(only, cst.SimpleStatementLine) or len(only.body) != 1:
        return False

    statement = only.body[0]
    if isinstance(statement, cst.Pass):
        return True
    return isinstance(statement, cst.Return) and (
        statement.value is None
        or (isinstance(statement.value, cst.Name) and statement.value.value == "None")
    )
