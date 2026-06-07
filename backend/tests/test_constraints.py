"""Tests for recommendation constraint extraction."""

from __future__ import annotations

from app.recommendations.constraints import extract_constraints, extract_constraints_from_history


def test_budget_under() -> None:
    c = extract_constraints("a dress under $100")
    assert c.category == "Dress"
    assert c.budget_max == 100.0
    assert c.budget_min is None


def test_budget_range() -> None:
    c = extract_constraints("something between $50 and $80")
    assert c.budget_min == 50.0
    assert c.budget_max == 80.0


def test_size_and_color_and_gender() -> None:
    c = extract_constraints("men's navy sweater in size L")
    assert c.gender == "men"
    assert c.color == "Navy"
    assert c.size == "L"
    assert c.category == "Sweater"


def test_size_word() -> None:
    assert extract_constraints("a medium jacket").size == "M"


def test_history_accumulates_newer_wins() -> None:
    c = extract_constraints_from_history(["a dress under $100", "actually make it black", "size M"])
    assert c.category == "Dress"
    assert c.color == "Black"
    assert c.size == "M"
    assert c.budget_max == 100.0
