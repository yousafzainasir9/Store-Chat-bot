"""Shopify Bulk Operations import.

The correct tool for syncing a large catalog: one ``bulkOperationRunQuery`` asks
Shopify to export the whole product graph to a JSONL file server-side; we poll
for completion, download the file, and stream it line by line. This avoids
thousands of paginated, rate-limited calls and scales to very large catalogs.

JSONL note: Shopify emits parent objects (products) and child objects (variants)
as separate lines linked by ``__parentId``. :func:`group_jsonl_by_parent`
reassembles each product with its variants for the mapper.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from typing import Any

from app.observability.logging import get_logger
from app.shopify.client import ShopifyClient

_log = get_logger("shopify.bulk")

# Products + variants + selected metafields; one doc per product downstream.
PRODUCTS_BULK_QUERY = """
{
  products {
    edges {
      node {
        id
        title
        handle
        descriptionHtml
        productType
        vendor
        tags
        status
        onlineStoreUrl
        featuredImage { url }
        priceRangeV2 {
          minVariantPrice { amount currencyCode }
          maxVariantPrice { amount currencyCode }
        }
        options { name values }
        variants {
          edges {
            node {
              id
              title
              sku
              price
              availableForSale
              selectedOptions { name value }
            }
          }
        }
      }
    }
  }
}
"""

_RUN_BULK = """
mutation {
  bulkOperationRunQuery(query: \"\"\"%s\"\"\") {
    bulkOperation { id status }
    userErrors { field message }
  }
}
"""

_POLL = """
{
  currentBulkOperation {
    id
    status
    errorCode
    objectCount
    url
  }
}
"""


async def start_bulk_export(client: ShopifyClient, query: str = PRODUCTS_BULK_QUERY) -> str:
    """Kick off a bulk export; return the bulk operation id."""
    data = await client.graphql(_RUN_BULK % query.strip())
    result = data["bulkOperationRunQuery"]
    errors = result.get("userErrors") or []
    if errors:
        raise RuntimeError(f"bulkOperationRunQuery userErrors: {errors}")
    op_id: str = result["bulkOperation"]["id"]
    return op_id


async def poll_until_complete(
    client: ShopifyClient, *, interval_s: float = 2.0, max_polls: int = 600
) -> str | None:
    """Poll the current bulk operation until done; return the JSONL URL (or None)."""
    for _ in range(max_polls):
        data = await client.graphql(_POLL)
        op = data.get("currentBulkOperation") or {}
        status = op.get("status")
        if status == "COMPLETED":
            url = op.get("url")
            return url if isinstance(url, str) else None
        if status in {"FAILED", "CANCELED", "EXPIRED"}:
            raise RuntimeError(f"Bulk operation {status}: {op.get('errorCode')}")
        await asyncio.sleep(interval_s)
    raise TimeoutError("Bulk operation did not complete in time")


def group_jsonl_by_parent(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Reassemble Shopify bulk JSONL into product objects with nested variants.

    Lines without ``__parentId`` are parents (products); lines with it are
    children (variants) appended to their parent under ``variants``.
    """
    parents: dict[str, dict[str, Any]] = {}
    children: list[dict[str, Any]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        obj = json.loads(raw)
        if obj.get("__parentId"):
            children.append(obj)
        else:
            obj.setdefault("variants", [])
            parents[obj["id"]] = obj
    for child in children:
        parent = parents.get(child["__parentId"])
        if parent is not None:
            parent["variants"].append(child)
    return list(parents.values())


async def download_jsonl_lines(url: str) -> AsyncIterator[str]:
    """Stream a completed bulk-operation JSONL file line by line."""
    import httpx  # lazy import

    async with httpx.AsyncClient(timeout=120.0) as client, client.stream("GET", url) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if line:
                yield line
