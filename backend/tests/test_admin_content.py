"""Tests for admin content CRUD + auth + re-indexing."""

from __future__ import annotations

import pytest
from app.config import Environment, Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_content_crud_and_reindex(client: TestClient) -> None:
    # Create a FAQ -> it should be answerable via /chat immediately.
    created = client.post(
        "/admin/content",
        json={
            "title": "Do you offer gift wrapping?",
            "body": "Yes, we offer gift wrapping at checkout for $4.95.",
            "category": "FAQ",
            "source": "FAQ",
        },
    )
    assert created.status_code == 201
    cid = created.json()["id"]

    answer = client.post("/chat", json={"message": "do you offer gift wrapping?"})
    body = " ".join(
        line[5:].strip() for line in answer.text.splitlines() if line.startswith("data:")
    ).lower()
    assert "gift wrapping" in body

    # Delete -> removed from listing.
    assert client.delete(f"/admin/content/{cid}").status_code == 200
    assert all(i["id"] != cid for i in client.get("/admin/content").json()["items"])


def test_admin_requires_token_when_configured() -> None:
    settings = Settings(environment=Environment.TEST, demo_mode=True, admin_api_key="adm1n")
    app = create_app(settings)
    with TestClient(app) as c:
        assert c.get("/admin/content").status_code == 401
        ok = c.get("/admin/content", headers={"Authorization": "Bearer adm1n"})
        assert ok.status_code == 200
        bad = c.get("/admin/content", headers={"Authorization": "Bearer wrong"})
        assert bad.status_code == 401


def test_production_requires_admin_key() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Settings(environment=Environment.PRODUCTION, admin_api_key=None)
