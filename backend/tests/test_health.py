"""Tests for the ops endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "store-chat-bot"
    assert body["environment"] == "test"
    assert body["demo_mode"] is True


def test_health_sets_request_id_header(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")


def test_ready_reports_checks(client: TestClient) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    checks = resp.json()["checks"]
    # Test settings configure no datastores → all False, but keys present.
    assert set(checks) == {"database", "redis", "qdrant"}
    assert all(v is False for v in checks.values())


def test_metrics_exposes_slos(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    slo_names = {s["name"] for s in body["slos"]}
    assert "chat_first_token_p95" in slo_names
    assert "metrics" in body
