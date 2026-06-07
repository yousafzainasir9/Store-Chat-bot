"""Tests for webhook HMAC verification and topic routing."""

from __future__ import annotations

import base64
import hashlib
import hmac

from app.shopify.webhooks import WebhookAction, route_topic, verify_webhook

_SECRET = "shh-secret"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_verify_accepts_valid_signature() -> None:
    body = b'{"id": 123}'
    assert verify_webhook(body, _sign(body), _SECRET) is True


def test_verify_rejects_tampered_body() -> None:
    body = b'{"id": 123}'
    assert verify_webhook(b'{"id": 999}', _sign(body), _SECRET) is False


def test_verify_rejects_missing_header() -> None:
    assert verify_webhook(b"x", None, _SECRET) is False


def test_route_product_update() -> None:
    ev = route_topic("products/update", {"id": 55})
    assert ev.action is WebhookAction.REINDEX_PRODUCT
    assert ev.product_gid == "gid://shopify/Product/55"


def test_route_product_delete() -> None:
    ev = route_topic("products/delete", {"id": "gid://shopify/Product/7"})
    assert ev.action is WebhookAction.DELETE_PRODUCT
    assert ev.product_gid == "gid://shopify/Product/7"


def test_route_unknown_topic_ignored() -> None:
    assert route_topic("orders/paid", {}).action is WebhookAction.IGNORE
