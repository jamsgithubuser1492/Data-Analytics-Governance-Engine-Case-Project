"""Safe arithmetic expression evaluator for agent value-add metrics.

Allowed: numbers, short string literals, whitelisted field names, + - * / ** unary minus,
comparisons, and the functions min, max, abs, round, div(a, b, default). Everything else
(attribute access, subscripts, imports, comprehensions, lambdas, other calls) is rejected
at parse time. Division by zero yields None (shown as "n/a"), never an exception.
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable, Dict, Iterable, Optional

MAX_LENGTH = 200
MAX_NODES = 60
MAX_DEPTH = 8
MAX_POWER = 6


class ExprError(ValueError):
    """Raised when an expression is not allowed or cannot be parsed."""


def _div(a: Any, b: Any, default: Any = 0) -> Any:
    try:
        return default if b == 0 else a / b
    except TypeError:
        return None


FUNCS: Dict[str, Callable[..., Any]] = {"min": min, "max": max, "abs": abs, "round": round, "div": _div}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}
_CMP = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Eq: operator.eq, ast.NotEq: operator.ne}


def parse(expression: str, allowed_names: Iterable[str]) -> ast.Expression:
    """Parse and validate an expression; raises ExprError with a plain language reason."""
    if not isinstance(expression, str) or not expression.strip():
        raise ExprError("Expression is empty.")
    if len(expression) > MAX_LENGTH:
        raise ExprError(f"Expression is longer than {MAX_LENGTH} characters.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"Not a valid expression: {exc.msg}.") from exc
    names, count = set(allowed_names), 0

    def check(node: ast.AST, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_NODES:
            raise ExprError("Expression is too complex.")
        if depth > MAX_DEPTH:
            raise ExprError("Expression is nested too deeply.")
        if isinstance(node, ast.Expression):
            check(node.body, depth)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float, str)):
                raise ExprError("Only numbers and text are allowed as constants.")
            if isinstance(node.value, str) and len(node.value) > 80:
                raise ExprError("Text constants are limited to 80 characters.")
        elif isinstance(node, ast.Name):
            if node.id not in names:
                raise ExprError(f"Unknown field '{node.id}'.")
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            if isinstance(node.op, ast.Pow) and not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, int)
                                                      and 0 <= node.right.value <= MAX_POWER):
                raise ExprError(f"Powers must use a whole number exponent from 0 to {MAX_POWER}.")
            check(node.left, depth + 1), check(node.right, depth + 1)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            check(node.operand, depth + 1)
        elif isinstance(node, ast.Compare) and all(type(o) in _CMP for o in node.ops):
            check(node.left, depth + 1)
            for c in node.comparators:
                check(c, depth + 1)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS or node.keywords:
                raise ExprError("Only min, max, abs, round and div(a, b, default) can be called.")
            for a in node.args:
                check(a, depth + 1)
        else:
            raise ExprError(f"'{type(node).__name__}' is not allowed in expressions.")

    check(tree, 0)
    return tree


def evaluate(expression: str, values: Dict[str, Any], allowed_names: Optional[Iterable[str]] = None) -> Any:
    """Evaluate an expression against ``values``. Returns None for undefined or NaN results."""
    tree = parse(expression, allowed_names if allowed_names is not None else values.keys())

    def ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return values.get(node.id)
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if a is None or b is None or isinstance(a, str) or isinstance(b, str):
                return None
            try:
                return _BIN[type(node.op)](a, b)
            except (ZeroDivisionError, OverflowError, ValueError):
                return None
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            return None if v is None or isinstance(v, str) else (-v if isinstance(node.op, ast.USub) else +v)
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = ev(comp)
                if left is None or right is None or not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            args = [ev(a) for a in node.args]
            fn = node.func.id
            if fn != "div" and any(a is None for a in args):
                return None
            try:
                return FUNCS[fn](*args)
            except (TypeError, ValueError):
                return None
        return None

    out = ev(tree)
    if isinstance(out, float) and (math.isnan(out) or math.isinf(out)):
        return None
    return out
