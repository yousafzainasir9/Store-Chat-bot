"""End-to-end webhook endpoint test: signed delete removes a product."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from app.config import Environment, Settings
from app.main import create_app
from fastapi.testclient import TestClient

_SECRET = "test-webhook-secret"


@pytest.fixture
def webhook_client() -> TestClient:
    settings = Settings(
        environment=Environment.TEST,
        demo_mode=True,
        log_json=True,
        shopify_webhook_secret=_SECRET,
    )
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(_SECRET.encode(), body, hashlib.sha256).digest()).decode()


def test_unverified_webhook_rejected(webhook_client: TestClient) -> None:
    resp = webhook_client.post(
        "/webhooks/shopify",
        content=b'{"id": 1000}',
        headers={"X-Shopify-Topic": "products/update", "X-Shopify-Hmac-Sha256": "bad"},
    )
    assert resp.status_code == 401


def test_signed_delete_removes_product(webhook_client: TestClient) -> None:
    # The demo catalog uses product ids gid://shopify/Product/1000+
    gid = "gid://shopify/Product/1000"
    body = json.dumps({"id": gid}).encode()
    resp = webhook_client.post(
        "/webhooks/shopify",
        content=body,
        headers={
            "X-Shopify-Topic": "products/delete",
            "X-Shopify-Hmac-Sha256": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "delete_product"


def test_freshness_posture_endpoint(webhook_client: TestClient) -> None:
    resp = webhook_client.get("/ops/freshness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stock_source"] == "live"  # volatile values never indexed
    assert body["profile"] == "balanced"
