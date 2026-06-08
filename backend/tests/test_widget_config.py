"""Tests for the merchant-managed widget configuration."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_public_widget_config_defaults(client: TestClient) -> None:
    resp = client.get("/widget/config")
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["position"] in {"left", "right"}
    assert cfg["primary_color"].startswith("#")
    assert "store_name" in cfg
    assert cfg["show_image_upload"] is True


def test_admin_updates_apply_to_public_config(client: TestClient) -> None:
    upd = client.put(
        "/admin/widget-config",
        json={
            "store_name": "Acme Threads",
            "primary_color": "#10b981",
            "position": "left",
            "locale": "es",
            "greeting": "Hi! How can I help?",
            "show_image_upload": False,
        },
    )
    assert upd.status_code == 200
    # The public endpoint the widget reads reflects the change immediately.
    cfg = client.get("/widget/config").json()
    assert cfg["store_name"] == "Acme Threads"
    assert cfg["primary_color"] == "#10b981"
    assert cfg["position"] == "left"
    assert cfg["locale"] == "es"
    assert cfg["greeting"] == "Hi! How can I help?"
    assert cfg["show_image_upload"] is False


def test_invalid_color_rejected(client: TestClient) -> None:
    resp = client.put("/admin/widget-config", json={"primary_color": "blue"})
    assert resp.status_code == 422  # pattern validation


def test_invalid_position_rejected(client: TestClient) -> None:
    resp = client.put("/admin/widget-config", json={"position": "middle"})
    assert resp.status_code == 422
