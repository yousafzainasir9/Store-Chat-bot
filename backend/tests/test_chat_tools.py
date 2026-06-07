"""Integration tests for the /chat tool path (orders, verification, stock)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _events(raw: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    event = "message"
    for line in raw.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            out.append((event, line.split(":", 1)[1].strip()))
    return out


def _text(raw: str) -> str:
    return " ".join(d for e, d in _events(raw) if e == "token")


def test_order_query_without_identity_asks_to_verify(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": "where is my order?"})
    body = _text(resp.text)
    assert "order number" in body.lower()
    assert "email" in body.lower()
    # It must NOT hand off or answer with order data.
    assert not any(e == "handoff" for e, _ in _events(resp.text))


def test_order_query_with_identity_returns_status(client: TestClient) -> None:
    resp = client.post(
        "/chat",
        json={"message": "status of my order #1001, email alice@example.com"},
    )
    body = _text(resp.text).lower()
    assert "paid" in body or "fulfill" in body
    assert any(e == "citations" for e, _ in _events(resp.text))


def test_wrong_email_blocks_lookup(client: TestClient) -> None:
    resp = client.post(
        "/chat",
        json={"message": "track order #1001 email eve@evil.com"},
    )
    body = _text(resp.text).lower()
    assert "verify" in body or "couldn't verify" in body
    assert "1z999" not in body  # tracking number never leaked


def test_stock_query_is_answered_live(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": "is the black dress in stock?"})
    body = _text(resp.text).lower()
    assert "stock" in body


def test_multiturn_verification(client: TestClient) -> None:
    # Order number in history, email in the new turn -> identity completes.
    resp = client.post(
        "/chat",
        json={
            "message": "my email is alice@example.com",
            "history": [{"role": "user", "content": "where is my order #1001"}],
        },
    )
    body = _text(resp.text).lower()
    assert "paid" in body or "fulfill" in body or "1z999" in body
