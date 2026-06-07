"""Tests for identity extraction + verification."""

from __future__ import annotations

from app.core.verification import emails_match, extract_identity


def test_extract_order_and_email() -> None:
    ident = extract_identity("Hi, where is order #1001? my email is alice@example.com")
    assert ident.order_number == "1001"
    assert ident.email == "alice@example.com"
    assert ident.is_complete


def test_extract_incomplete() -> None:
    ident = extract_identity("where is my order?")
    assert ident.order_number is None
    assert not ident.is_complete


def test_emails_match_case_insensitive() -> None:
    assert emails_match("Alice@Example.com ", "alice@example.com")
    assert not emails_match("eve@evil.com", "alice@example.com")
    assert not emails_match(None, "alice@example.com")
