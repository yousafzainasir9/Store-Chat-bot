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


def test_bare_number_with_category_is_price_ceiling() -> None:
    # "54 shirts" / "shirt for 54" -> shirts up to $54 (a common shopper phrasing).
    for q in ("give me 54 shirts options", "54 dollars shirt", "a shirt for 54"):
        c = extract_constraints(q)
        assert c.category == "Shirt"
        assert c.budget_max == 54.0


def test_numeric_size_is_not_treated_as_price() -> None:
    c = extract_constraints("size 10 shirt")
    assert c.budget_max is None


def test_bare_category_without_number_has_no_budget() -> None:
    c = extract_constraints("do you have any dresses")
    assert c.budget_max is None
