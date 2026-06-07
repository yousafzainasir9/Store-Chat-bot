"""Offline Shopify test doubles: a fake client and a synthetic catalog.

Lets the entire catalog-sync pipeline (bulk export -> map -> index -> retrieve)
run and be load-tested with no network and no real store. The generator produces
deterministic fashion products so tests are stable.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

_COLORS = ["Black", "White", "Navy", "Olive", "Burgundy", "Beige"]
_SIZES = ["XS", "S", "M", "L", "XL"]
_TYPES = ["Dress", "Shirt", "Jeans", "Sweater", "Jacket", "Skirt"]
_MATERIALS = ["100% cotton", "merino wool", "organic linen", "recycled polyester"]


def generate_catalog_jsonl(n_products: int = 50) -> list[str]:
    """Return ``n_products`` synthetic products as Shopify bulk JSONL lines."""
    lines: list[str] = []
    for i in range(n_products):
        ptype = _TYPES[i % len(_TYPES)]
        color = _COLORS[i % len(_COLORS)]
        material = _MATERIALS[i % len(_MATERIALS)]
        pid = f"gid://shopify/Product/{1000 + i}"
        price = 19.0 + (i % 40) * 5
        lines.append(
            json.dumps(
                {
                    "id": pid,
                    "title": f"{color} {material.split()[-1].title()} {ptype} {i}",
                    "handle": f"{ptype.lower()}-{i}",
                    "descriptionHtml": (
                        f"<p>A {color.lower()} {ptype.lower()} in {material}. "
                        f"Machine wash cold. Relaxed fit.</p>"
                    ),
                    "productType": ptype,
                    "vendor": "Acme Threads",
                    "tags": ["fashion", ptype.lower(), color.lower()],
                    "status": "ACTIVE",
                    "onlineStoreUrl": f"https://example.com/products/{ptype.lower()}-{i}",
                    "featuredImage": {"url": f"https://img.example.com/{ptype.lower()}-{i}.jpg"},
                    "priceRangeV2": {
                        "minVariantPrice": {"amount": f"{price:.2f}", "currencyCode": "USD"},
                        "maxVariantPrice": {"amount": f"{price + 10:.2f}", "currencyCode": "USD"},
                    },
                    "options": [
                        {"name": "Size", "values": _SIZES},
                        {"name": "Color", "values": [color]},
                    ],
                    "variants": [],
                }
            )
        )
        for s_idx, size in enumerate(_SIZES):
            lines.append(
                json.dumps(
                    {
                        "id": f"gid://shopify/ProductVariant/{(1000 + i) * 10 + s_idx}",
                        "__parentId": pid,
                        "title": f"{size} / {color}",
                        "sku": f"SKU-{i}-{size}",
                        "price": f"{price:.2f}",
                        "availableForSale": s_idx % 4 != 0,
                        "selectedOptions": [
                            {"name": "Size", "value": size},
                            {"name": "Color", "value": color},
                        ],
                    }
                )
            )
    return lines


class FakeShopifyClient:
    """In-memory Shopify client returning a synthetic catalog via bulk ops."""

    def __init__(self, n_products: int = 50) -> None:
        self._lines = generate_catalog_jsonl(n_products)
        self._poll_count = 0

    @property
    def jsonl_lines(self) -> list[str]:
        return self._lines

    # Synthetic orders for offline order-tool tests. Keyed by order number.
    _ORDERS: ClassVar[dict[str, dict[str, Any]]] = {
        "1001": {
            "id": "gid://shopify/Order/1001",
            "name": "#1001",
            "email": "alice@example.com",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "FULFILLED",
            "fulfillments": [
                {
                    "status": "SUCCESS",
                    "trackingInfo": [
                        {
                            "number": "1Z999AA10123456784",
                            "company": "UPS",
                            "url": "https://ups.com/track",
                        }
                    ],
                }
            ],
        },
        "1002": {
            "id": "gid://shopify/Order/1002",
            "name": "#1002",
            "email": "bob@example.com",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "UNFULFILLED",
            "fulfillments": [],
        },
    }

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        if "orders(" in query:
            q = str(variables.get("query", ""))
            number = q.split("name:#", 1)[1].strip() if "name:#" in q else ""
            order = self._ORDERS.get(number)
            edges = [{"node": order}] if order else []
            return {"orders": {"edges": edges}}
        if "productVariants(" in query:
            q = str(variables.get("query", "")).lower()
            in_stock = "out" not in q
            return {
                "productVariants": {
                    "edges": [
                        {
                            "node": {
                                "id": "gid://shopify/ProductVariant/1",
                                "title": "M / Black",
                                "sku": "SKU-DEMO-M",
                                "inventoryQuantity": 7 if in_stock else 0,
                                "availableForSale": in_stock,
                                "product": {"title": "Black Cotton Dress"},
                            }
                        }
                    ]
                }
            }
        if "bulkOperationRunQuery" in query:
            return {
                "bulkOperationRunQuery": {
                    "bulkOperation": {"id": "gid://shopify/BulkOperation/1", "status": "CREATED"},
                    "userErrors": [],
                }
            }
        if "currentBulkOperation" in query:
            # Report COMPLETED immediately; URL is a sentinel handled by the test sync.
            return {
                "currentBulkOperation": {
                    "id": "gid://shopify/BulkOperation/1",
                    "status": "COMPLETED",
                    "errorCode": None,
                    "objectCount": len(self._lines),
                    "url": "memory://bulk.jsonl",
                }
            }
        return {}
