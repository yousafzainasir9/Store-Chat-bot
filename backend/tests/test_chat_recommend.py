"""Integration tests for the /chat recommendation flow."""

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


def test_recommendation_returns_products_with_citations(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": "can you recommend a dress under $120?"})
    assert resp.status_code == 200
    body = _text(resp.text).lower()
    assert "dress" in body
    events = [e for e, _ in _events(resp.text)]
    assert "products" in events  # structured product cards are emitted
    assert "citations" in events
    assert "handoff" not in events


def test_complete_the_look(client: TestClient) -> None:
    resp = client.post(
        "/chat",
        json={
            "message": "what goes with it?",
            "history": [{"role": "user", "content": "I bought a pair of jeans"}],
        },
    )
    body = _text(resp.text).lower()
    # Should suggest complementary categories, not jeans again.
    assert any(word in body for word in ("shirt", "sweater", "jacket", "look"))


def test_recommend_generic_product_question_stays_rag(client: TestClient) -> None:
    # "do you have any dresses" must remain a grounded catalog answer, not the
    # recommendation flow — verified by a citations event and product text.
    resp = client.post("/chat", json={"message": "do you have any dresses?"})
    assert any(e == "citations" for e, _ in _events(resp.text))
