"""Shopify webhook verification + topic routing.

Every webhook is authenticated by verifying the ``X-Shopify-Hmac-Sha256`` header
against the raw request body using the app's webhook secret (constant-time
compare). Verified events are routed to catalog-sync actions and dispatched to
the job queue so the HTTP handler returns immediately (Shopify requires a fast
2xx; slow handlers get retried/disabled).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from enum import StrEnum


def verify_webhook(raw_body: bytes, hmac_header: str | None, secret: str) -> bool:
    """Constant-time verify a Shopify webhook HMAC (base64 of SHA-256)."""
    if not hmac_header or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, hmac_header)


class WebhookAction(StrEnum):
    """What a verified webhook should trigger."""

    REINDEX_PRODUCT = "reindex_product"
    DELETE_PRODUCT = "delete_product"
    REINDEX_BY_INVENTORY = "reindex_by_inventory"
    IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    """A routed webhook: the action and the product gid it concerns (if any)."""

    action: WebhookAction
    product_gid: str | None = None


def _gid(product_id: object) -> str | None:
    if product_id is None:
        return None
    pid = str(product_id)
    return pid if pid.startswith("gid://") else f"gid://shopify/Product/{pid}"


def route_topic(topic: str, payload: dict[str, object]) -> WebhookEvent:
    """Map a Shopify webhook topic + payload to a :class:`WebhookEvent`."""
    topic = topic.lower()
    if topic in {"products/create", "products/update"}:
        return WebhookEvent(WebhookAction.REINDEX_PRODUCT, _gid(payload.get("id")))
    if topic == "products/delete":
        return WebhookEvent(WebhookAction.DELETE_PRODUCT, _gid(payload.get("id")))
    if topic.startswith("inventory_levels/"):
        # Inventory webhooks carry inventory_item_id, not product id. The handler
        # resolves the owning product; here we just flag the action.
        return WebhookEvent(WebhookAction.REINDEX_BY_INVENTORY, None)
    return WebhookEvent(WebhookAction.IGNORE)
