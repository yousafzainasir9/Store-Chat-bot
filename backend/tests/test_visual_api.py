"""Integration test for the /search/visual endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_visual_endpoint_returns_matches(client: TestClient) -> None:
    resp = client.post(
        "/search/visual",
        files={"image": ("query.txt", b"Black Dress", "text/plain")},
        data={"category": "Dress", "budget_max": "200"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert all("dress" in r["title"].lower() for r in body["results"])


def test_visual_endpoint_rejects_empty(client: TestClient) -> None:
    resp = client.post(
        "/search/visual",
        files={"image": ("query.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400
