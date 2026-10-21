"""Chart generation (port of ``agent/chart-run.ps1``).

The Windows edition draws with ``System.Drawing``; on macOS the natural
equivalent is matplotlib (Agg backend, headless). Charts are written to
``<root>/outputs/charts`` and the path is returned so the chat can show them.

``function`` charts evaluate a user-supplied expression. To stay safe there is
no ``eval``: expressions are parsed with :mod:`ast` and only a whitelist of
operators/functions/names is accepted.
"""

from __future__ import annotations

import ast
import math
import operator
from pathlib import Path

from .paths import Paths

ALLOWED_NAMES = {
    "x": None, "pi": math.pi, "e": math.e, "tau": math.tau,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin,
    "acos": math.acos, "atan": math.atan, "sqrt": math.sqrt, "abs": abs,
    "exp": math.exp, "log": math.log, "log10": math.log10, "floor": math.floor,
    "ceil": math.ceil, "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
}

_BIN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
            ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
            ast.FloorDiv: operator.floordiv}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST, x: float) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, x)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id == "x":
            return x
        value = ALLOWED_NAMES.get(node.id)
        if callable(value):
            raise ValueError(f"'{node.id}' is a function; call it with parentheses.")
        if value is None:
            raise ValueError(f"unknown name: {node.id}")
        return float(value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left, x), _eval_node(node.right, x))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand, x))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_NAMES:
            raise ValueError("only allowed functions may be used.")
        fn = ALLOWED_NAMES[node.func.id]
        if not callable(fn):
            raise ValueError(f"'{node.func.id}' is not callable.")
        args = [_eval_node(a, x) for a in node.args]
        return float(fn(*args))
    raise ValueError("the expression contains a construct that is not allowed.")


def evaluate_expression(expression: str, x: float) -> float:
    tree = ast.parse(expression.replace("^", "**"), mode="eval")
    return _eval_node(tree, x)


def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def generate_chart(paths: Paths, request: dict) -> dict:
    """Render a chart. ``request`` mirrors the chat tool arguments."""
    kind = str(request.get("type") or request.get("chart_type") or "bar").lower()
    title = str(request.get("title") or "")
    plt = _matplotlib()
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)

    labels = request.get("labels") or []
    values = request.get("values") or []
    if kind in ("bar", "line", "pie", "scatter") and not values:
        return {"error": "'values' is required for a chart."}

    if kind == "bar":
        ax.bar([str(x) for x in labels] or range(len(values)), values)
        ax.set_ylabel(str(request.get("y_label") or ""))
    elif kind == "line":
        ax.plot(range(len(values)), values, marker="o")
        ax.set_xticks(range(len(values)))
        ax.set_xticklabels([str(x) for x in labels] or range(len(values)))
        ax.set_ylabel(str(request.get("y_label") or ""))
    elif kind == "scatter":
        xs = request.get("x") or list(range(len(values)))
        ax.scatter(xs, values)
        ax.set_xlabel(str(request.get("x_label") or ""))
        ax.set_ylabel(str(request.get("y_label") or ""))
    elif kind == "pie":
        ax.pie(values, labels=[str(x) for x in labels] or None, autopct="%1.1f%%")
        ax.axis("equal")
    elif kind == "function":
        expression = str(request.get("expression") or "")
        if not expression:
            return {"error": "'expression' is required for a function chart."}
        x_min = float(request.get("x_min", -10))
        x_max = float(request.get("x_max", 10))
        samples = int(request.get("samples", 400))
        xs, ys = [], []
        try:
            for i in range(samples + 1):
                xv = x_min + (x_max - x_min) * i / samples
                xs.append(xv)
                ys.append(evaluate_expression(expression, xv))
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
            return {"error": f"the expression could not be evaluated: {exc}"}
        ax.plot(xs, ys)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.axvline(0, color="black", linewidth=0.5)
        ax.set_xlabel("x")
    else:
        return {"error": f"unknown chart type: {kind}"}

    if title:
        ax.set_title(title)
    fig.tight_layout()

    out_dir = paths.output_dir("charts")
    out_dir.mkdir(parents=True, exist_ok=True)
    index = 1
    while (out_dir / f"grafik-{index}.png").exists():
        index += 1
    out_path = out_dir / f"grafik-{index}.png"
    fig.savefig(out_path)
    plt.close(fig)
    return {"path": str(out_path), "type": kind, "title": title}
