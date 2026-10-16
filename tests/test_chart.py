"""Chart generation: safe expression evaluation and rendering."""

from __future__ import annotations

import math

import pytest

from mamidlabs.core.chart import evaluate_expression


def test_basic_arithmetic():
    assert evaluate_expression("x^2", 3) == 9
    assert evaluate_expression("2*x + 1", 4) == 9
    assert evaluate_expression("x/2", 8) == 4


def test_functions_and_constants():
    assert evaluate_expression("sin(pi/2)", 0) == pytest.approx(1.0)
    assert evaluate_expression("sqrt(x)", 16) == pytest.approx(4.0)
    assert evaluate_expression("log(e)", 0) == pytest.approx(1.0)


def test_rejects_dunder_and_attributes():
    with pytest.raises((ValueError, SyntaxError)):
        evaluate_expression("__import__('os')", 1)
    with pytest.raises((ValueError, SyntaxError)):
        evaluate_expression("x.__class__", 1)


def test_rejects_unknown_name():
    with pytest.raises(ValueError):
        evaluate_expression("evil(x)", 1)
