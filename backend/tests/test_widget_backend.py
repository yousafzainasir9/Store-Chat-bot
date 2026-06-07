"""Tests for widget session tokens, rate limiting, and security headers."""

from __future__ import annotations

from app.api.ratelimit import RateLimiter
from app.api.widget import issue_token, verify_token
from app.config import Environment, Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_token_roundtrip() -> None:
    token, exp = issue_token("secret", ttl_seconds=3600)
    assert verify_token(token, "secret")
    assert not verify_token(token, "other-secret")
    assert exp > 0


def test_expired_token_rejected() -> None:
    token, _ = issue_token("secret", ttl_seconds=-1)
    assert not verify_token(token, "secret")


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_rate_limiter_blocks_after_capacity() -> None:
    clock = _Clock()
    limiter = RateLimiter(per_minute=2, clock=clock)
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is False  # capacity exhausted
    clock.t = 60.0  # refill a full minute later
    assert limiter.allow("ip") is True


def test_security_headers_present(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_widget_session_without_secret_is_noop(client: TestClient) -> None:
    resp = client.post("/widget/session")
    assert resp.status_code == 200
    assert resp.json()["required"] is False


def test_widget_token_enforced_when_configured() -> None:
    settings = Settings(
        environment=Environment.TEST,
        demo_mode=True,
        widget_secret="s3cret",
        widget_require_token=True,
    )
    app = create_app(settings)
    with TestClient(app) as c:
        # Missing token -> 401
        assert c.post("/chat", json={"message": "hi"}).status_code == 401
        # Valid token -> allowed
        token = c.post("/widget/session").json()["token"]
        ok = c.post(
            "/chat",
            json={"message": "How long does shipping take?"},
            headers={"X-Widget-Token": token},
        )
        assert ok.status_code == 200


def test_chat_rate_limited() -> None:
    settings = Settings(environment=Environment.TEST, demo_mode=True, rate_limit_per_minute=1)
    app = create_app(settings)
    with TestClient(app) as c:
        first = c.post("/chat", json={"message": "How long does shipping take?"})
        second = c.post("/chat", json={"message": "How long does shipping take?"})
        assert first.status_code == 200
        assert second.status_code == 429
