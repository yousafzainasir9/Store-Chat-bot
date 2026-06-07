"""Catalog synchronization service.

Coordinates the catalog lifecycle on top of the Shopify client + bulk import +
mapper + indexer:

* :meth:`full_import` — Bulk Operations export of the whole catalog (scales to
  large stores), mapped to one-doc-per-product and indexed in batches.
* :meth:`reindex_product` / :meth:`delete_product` — incremental updates driven
  by webhooks (Phase 2 §3) so steady-state cost stays trivial.

Volatile values (stock quantity, final price) are intentionally *not* indexed;
they are resolved live at answer time (Phase 3). Descriptive availability
(a product *has* an XL) is indexed for filtering.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.observability.logging import get_logger
from app.observability.metrics import metrics
from app.rag.indexer import Indexer
from app.rag.models import Document
from app.shopify import bulk
from app.shopify.client import ShopifyClient
from app.shopify.mapping import documents_from_products, product_to_document

_log = get_logger("catalog_sync")

# Single-product fetch for incremental webhook re-index.
_PRODUCT_QUERY = """
query($id: ID!) {
  product(id: $id) {
    id title handle descriptionHtml productType vendor tags status onlineStoreUrl
    priceRangeV2 { minVariantPrice { amount currencyCode } maxVariantPrice { amount currencyCode } }
    options { name values }
    variants(first: 100) {
      edges { node { id title sku price availableForSale selectedOptions { name value } } }
    }
  }
}
"""


def _flatten_variants(product: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GraphQL product (edges/nodes) into the flat bulk shape."""
    variants = [e["node"] for e in (product.get("variants") or {}).get("edges", [])]
    return {**product, "variants": variants}


class CatalogSyncService:
    """Imports and incrementally maintains the product index."""

    def __init__(
        self,
        client: ShopifyClient,
        indexer: Indexer,
        *,
        embed_batch_size: int = 128,
        jsonl_source: AsyncIterator[str] | None = None,
    ) -> None:
        self._client = client
        self._indexer = indexer
        self._embed_batch_size = embed_batch_size
        # Test seam: a pre-supplied JSONL line source bypasses the network.
        self._jsonl_source = jsonl_source

    async def _bulk_lines(self) -> list[str]:
        await bulk.start_bulk_export(self._client)
        url = await bulk.poll_until_complete(self._client)
        if url is None:
            return []
        if self._jsonl_source is not None:
            return [line async for line in self._jsonl_source]
        return [line async for line in bulk.download_jsonl_lines(url)]

    async def full_import(self, *, lines: list[str] | None = None) -> int:
        """Full catalog import via Bulk Operations; returns chunks indexed."""
        raw_lines = lines if lines is not None else await self._bulk_lines()
        products = bulk.group_jsonl_by_parent(raw_lines)
        documents = documents_from_products(products)
        total = await self._index_in_batches(documents)
        metrics.incr("catalog_full_import_total")
        _log.info("full_import", products=len(products), chunks=total)
        return total

    async def _index_in_batches(self, documents: list[Document]) -> int:
        total = 0
        for start in range(0, len(documents), self._embed_batch_size):
            batch = documents[start : start + self._embed_batch_size]
            total += await self._indexer.index(batch)
        return total

    async def reindex_product(self, product_gid: str) -> int:
        """Re-index a single product (webhook-driven incremental update)."""
        data = await self._client.graphql(_PRODUCT_QUERY, {"id": product_gid})
        product = data.get("product")
        if not product or (product.get("status") or "ACTIVE").upper() != "ACTIVE":
            await self.delete_product(product_gid)
            return 0
        doc = product_to_document(_flatten_variants(product))
        count = await self._indexer.index([doc])
        metrics.incr("catalog_product_reindex_total")
        _log.info("reindex_product", product_id=product_gid, chunks=count)
        return count

    async def delete_product(self, product_gid: str) -> None:
        """Remove a product's chunks from the index (webhook delete)."""
        await self._indexer.delete_document(product_gid)
        metrics.incr("catalog_product_delete_total")
        _log.info("delete_product", product_id=product_gid)
