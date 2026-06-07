"""Tests for the visual search pipeline (offline image embedder)."""

from __future__ import annotations

import pytest
from app.rag.image_embeddings import FakeImageEmbedder
from app.rag.vector_store import InMemoryVectorStore
from app.rag.visual_search import VisualIndexer, VisualSearchService, offline_descriptor_source
from app.recommendations.constraints import Constraints
from app.shopify.bulk import group_jsonl_by_parent
from app.shopify.fake import FakeShopifyClient, generate_catalog_jsonl
from app.shopify.mapping import documents_from_products
from app.shopify.orders import OrderService, ToolResult, ToolStatus

pytestmark = pytest.mark.asyncio


async def _pipeline(*, stock_ok: bool = True):
    products = documents_from_products(group_jsonl_by_parent(generate_catalog_jsonl(24)))
    image_store = InMemoryVectorStore()
    embedder = FakeImageEmbedder(dimension=256)
    indexer = VisualIndexer(embedder, image_store, offline_descriptor_source)
    n = await indexer.index(products)

    orders = OrderService(FakeShopifyClient(n_products=1))
    if not stock_ok:

        async def _oos(query: str) -> ToolResult:
            return ToolResult(ToolStatus.OK, "out", data={"available": "False"})

        orders.check_stock = _oos  # type: ignore[method-assign]

    service = VisualSearchService(embedder, image_store, orders, max_results=3)
    return service, products, n


async def test_visual_index_covers_products() -> None:
    _, products, n = await _pipeline()
    assert n == len(products)


async def test_visual_search_matches_similar_attributes() -> None:
    service, _products, _ = await _pipeline()
    # Query "image" is an attribute descriptor for a black dress.
    results = await service.search(b"Black Dress", Constraints(category="Dress"))
    assert results
    assert all("dress" in r.title.lower() for r in results)


async def test_visual_search_excludes_out_of_stock() -> None:
    service, _, _ = await _pipeline(stock_ok=False)
    results = await service.search(b"Black Dress", Constraints(category="Dress"))
    assert results == []


async def test_visual_search_respects_budget() -> None:
    service, _, _ = await _pipeline()
    results = await service.search(b"Dress", Constraints(category="Dress", budget_max=40))
    assert all(r.price <= 40 for r in results)
