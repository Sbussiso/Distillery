"""Built-in safe tool executors.

These are the ONLY tools that may execute real logic (never arbitrary code).
The registry maps tool name -> pure function(dict) -> result string. A tool
with exec_policy="builtin" whose name is not in this registry is downgraded to
"simulate" by the distiller (never raised).

The calculator uses an AST allowlist walk — NO eval/exec/compile, NO attribute
access, NO calls, NO imports, NO filesystem/network. Only arithmetic nodes and
the constants pi/e/tau are permitted.
"""
from __future__ import annotations

import ast
import math
from typing import Any, Callable

BUILTIN_EXECUTORS: dict[str, Callable[[dict[str, Any]], str]] = {}


def register(name: str) -> Callable[[Callable[[dict[str, Any]], str]], Callable[[dict[str, Any]], str]]:
    def deco(fn: Callable[[dict[str, Any]], str]) -> Callable[[dict[str, Any]], str]:
        BUILTIN_EXECUTORS[name] = fn
        return fn

    return deco


_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


@register("calculator")
def calculator(args: dict[str, Any]) -> str:
    """Evaluate a safe arithmetic expression. Accepts expression/expr/equation."""
    expr = args.get("expression") or args.get("expr") or args.get("equation")
    if not isinstance(expr, str):
        return "[error: 'expression' must be a string]"
    if len(expr) > 512:
        return "[error: expression too long]"
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return "[error: syntax error]"

    def ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = ev(node.operand)
            return +v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp):
            l, r = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return l + r
            if isinstance(node.op, ast.Sub):
                return l - r
            if isinstance(node.op, ast.Mult):
                return l * r
            if isinstance(node.op, ast.Div):
                return l / r if r != 0 else float("inf")
            if isinstance(node.op, ast.FloorDiv):
                return l // r if r != 0 else float("inf")
            if isinstance(node.op, ast.Mod):
                return l % r if r != 0 else float("inf")
            if isinstance(node.op, ast.Pow):
                if abs(r) > 1e6:
                    raise ValueError("exponent too large")
                # Bound the RESULT size, not just the exponent. A prior allowed
                # Pow can produce an enormous int base, so a nested expression
                # like (2**999999)**999999 would otherwise pass the r-only check
                # and trigger catastrophic arbitrary-precision exponentiation
                # (hangs the worker, exhausts memory). Cap the estimated result
                # bit-length for int operands (~1M bits = ~125KB ceiling).
                if isinstance(l, int) and isinstance(r, int):
                    if l.bit_length() * abs(r) > 1_000_000:
                        raise ValueError("result too large")
                return l ** r
            raise ValueError(f"disallowed op: {type(node.op).__name__}")
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"disallowed node: {type(node).__name__}")

    try:
        return str(ev(tree))
    except (ValueError, ZeroDivisionError, TypeError, RecursionError) as e:
        return f"[error: {e}]"