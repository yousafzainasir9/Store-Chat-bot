"""Tests for per-session token budget enforcement."""

from __future__ import annotations

from app.billing.budget import SessionBudget
from app.config import Environment, Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_budget_exceeded_and_anomaly() -> None:
    b = SessionBudget(budget=100, anomaly_threshold=50)
    assert b.exceeded("c") is False
    b.record("c", 60)  # crosses anomaly threshold
    assert b.exceeded("c") is False
    b.record("c", 60)  # now over budget
    assert b.exceeded("c") is True
    assert b.usage("c") == 120


def test_chat_hands_off_when_budget_exhausted() -> None:
    settings = Settings(environment=Environment.TEST, demo_mode=True, per_session_token_budget=1)
    app = create_app(settings)
    with TestClient(app) as c:
        first = c.post("/chat", json={"message": "How long does shipping take?"})
        cid = None
        for line in first.text.splitlines():
            if line.startswith("data:") and "conversation_id" in line:
                import json

                cid = json.loads(line[5:].strip())["conversation_id"]
                break
        assert cid
        # The first turn already spent > 1 token, so the next turn hands off.
        second = c.post("/chat", json={"message": "And returns?", "conversation_id": cid})
        assert "event: handoff" in second.text
        assert '"reason": "budget"' in second.text
