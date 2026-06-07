"""Tests for admin conversations, gaps, analytics, feedback."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _drive_traffic(client: TestClient) -> None:
    # A grounded answer, a handoff (out of scope), and feedback.
    client.post("/chat", json={"message": "How long does shipping take?"})
    oos = client.post("/chat", json={"message": "What is the capital of France?"})
    # find conversation/message id from meta
    convo = None
    for line in oos.text.splitlines():
        if line.startswith("data:") and "conversation_id" in line:
            import json

            convo = json.loads(line[5:].strip())
            break
    if convo:
        client.post(
            "/feedback",
            json={
                "conversation_id": convo["conversation_id"],
                "message_id": convo["message_id"],
                "value": "down",
            },
        )


def test_conversations_listed_and_fetchable(client: TestClient) -> None:
    _drive_traffic(client)
    items = client.get("/admin/conversations").json()["items"]
    assert items
    detail = client.get(f"/admin/conversations/{items[0]['id']}")
    assert detail.status_code == 200
    assert "messages" in detail.json()


def test_gaps_surface_unanswered_questions(client: TestClient) -> None:
    # Two similar out-of-scope questions should cluster into one gap.
    client.post("/chat", json={"message": "Who is the president of France?"})
    client.post("/chat", json={"message": "Who is the president of France today?"})
    gaps = client.get("/admin/gaps").json()["items"]
    assert gaps
    assert gaps[0]["count"] >= 2


def test_create_faq_from_gap_then_answered(client: TestClient) -> None:
    client.post(
        "/admin/gaps/create-faq",
        json={
            "title": "Do you price match?",
            "body": "Yes, we match any identical in-stock item from a major retailer in 14 days.",
        },
    )
    ans = client.post("/chat", json={"message": "do you price match?"})
    text = " ".join(
        line[5:].strip() for line in ans.text.splitlines() if line.startswith("data:")
    ).lower()
    assert "price match" in text


def test_analytics_summary(client: TestClient) -> None:
    _drive_traffic(client)
    a = client.get("/admin/analytics").json()
    assert a["conversations"] >= 1
    assert a["assistant_messages"] >= 1
    assert 0.0 <= a["handoff_rate"] <= 1.0
    assert "est_cost_per_conversation_usd" in a
