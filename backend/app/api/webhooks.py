"""Shopify webhook receiver.

Verifies the HMAC on the raw body, routes the topic to a catalog action, and
dispatches the work to the job queue so we return a fast 2xx (Shopify retries
slow/failed deliveries and will disable a flaky endpoint). Unverified requests
get 401; ignored topics get a 200 no-op.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, Request, Response, status

from app.observability.logging import get_logger
from app.services.container import Container
from app.shopify.webhooks import WebhookAction, route_topic, verify_webhook

router = APIRouter(tags=["webhooks"])
_log = get_logger("webhooks")


def _container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


@router.post("/webhooks/shopify", summary="Receive a verified Shopify webhook")
async def shopify_webhook(
    request: Request,
    response: Response,
    x_shopify_topic: str = Header(default=""),
    x_shopify_hmac_sha256: str | None = Header(default=None),
) -> dict[str, Any]:
    """Authenticate, route, and dispatch a Shopify webhook."""
    container = _container(request)
    secret = container.settings.shopify_webhook_secret or ""
    raw = await request.body()

    if not verify_webhook(raw, x_shopify_hmac_sha256, secret):
        _log.warning("webhook_unverified", topic=x_shopify_topic)
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"status": "unauthorized"}

    payload = json.loads(raw or b"{}")
    event = route_topic(x_shopify_topic, payload)

    if event.action is WebhookAction.REINDEX_PRODUCT and event.product_gid:
        await container.job_queue.enqueue("reindex_product", product_gid=event.product_gid)
    elif event.action is WebhookAction.DELETE_PRODUCT and event.product_gid:
        await container.job_queue.enqueue("delete_product", product_gid=event.product_gid)
    elif event.action is WebhookAction.REINDEX_BY_INVENTORY:
        # Inventory-level change: descriptive availability may have shifted.
        # Resolving the owning product happens here in a fuller build; for now we
        # acknowledge so Shopify does not retry. Quantity itself is always live.
        _log.info("webhook_inventory_ack", topic=x_shopify_topic)
    else:
        _log.info("webhook_ignored", topic=x_shopify_topic)

    return {"status": "ok", "action": event.action.value}
