"""Exact arithmetic, so the model does not have to guess at sums."""

import ast
import math
import operator
from collections.abc import Callable

from pydantic import Field

from zeno.agent.tools.base import Risk, ToolArgs, tool

Number = int | float

_BINARY: dict[type[ast.operator], Callable[[Number, Number], Number]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[Number], Number]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
MAX_DIGITS = 100


class CalcArgs(ToolArgs):
    expression: str = Field(
        min_length=1,
        max_length=200,
        description="Arithmetic with numbers, parentheses and + - * / // % ** only.",
    )


@tool(risk=Risk.READ_ONLY, timeout=2.0)
async def calculate(args: CalcArgs) -> str:
    """Evaluate an arithmetic expression exactly, e.g. "(17.5 * 3) / 4"."""
    try:
        tree = ast.parse(args.expression, mode="eval")
    except SyntaxError:
        raise ValueError("That is not an arithmetic expression.") from None
    try:
        return str(_evaluate(tree.body))
    except (ZeroDivisionError, OverflowError) as error:
        raise ValueError(f"Cannot calculate that: {error}.") from None


def _evaluate(node: ast.expr) -> Number:
    """Walks the syntax tree itself; nothing is ever passed to eval()."""
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return _checked(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _checked(_UNARY[type(node.op)](_evaluate(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow):
            _check_power(left, right)
        return _checked(_BINARY[type(node.op)](left, right))
    raise ValueError("Only numbers, parentheses and + - * / // % ** are allowed.")


def _check_power(base: Number, exponent: Number) -> None:
    # Refuse before computing: 2 ** 2 ** 2 ** 2 ** 2 would take ages and memory.
    if abs(exponent) > 1000 or (
        abs(base) > 1 and abs(exponent) * math.log10(abs(base)) > MAX_DIGITS
    ):
        raise ValueError("That number is too large.")


def _checked(value: object) -> Number:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("The result is not a real number.")  # e.g. (-8) ** 0.5
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("The result is too large.")
    if isinstance(value, int) and abs(value) >= 10**MAX_DIGITS:
        raise ValueError("That number is too large.")
    return value
