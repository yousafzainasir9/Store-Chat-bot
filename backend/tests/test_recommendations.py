"""Tests for the recommendation service (constraints, budget, live stock)."""

from __future__ import annotations

import pytest
from app.rag.embeddings import HashingEmbedder
from app.rag.indexer import Indexer
from app.rag.vector_store import InMemoryVectorStore
from app.recommendations.constraints import Constraints
from app.recommendations.service import RecommendationService
from app.shopify.bulk import group_jsonl_by_parent
from app.shopify.fake import FakeShopifyClient, generate_catalog_jsonl
from app.shopify.mapping import documents_from_products
from app.shopify.orders import OrderService, ToolResult, ToolStatus

pytestmark = pytest.mark.asyncio


async def _service(*, verify_stock: bool = True, stock_ok: bool = True) -> RecommendationService:
    store = InMemoryVectorStore()
    embedder = HashingEmbedder(dimension=256)
    docs = documents_from_products(group_jsonl_by_parent(generate_catalog_jsonl(24)))
    await Indexer(embedder, store).index(docs)

    orders = OrderService(FakeShopifyClient(n_products=1))
    if not stock_ok:

        async def _always_oos(query: str) -> ToolResult:
            return ToolResult(ToolStatus.OK, "out", data={"available": "False"})

        orders.check_stock = _always_oos  # type: ignore[method-assign]
    return RecommendationService(
        embedder, store, orders, max_results=3, verify_live_stock=verify_stock
    )


async def test_recommend_respects_category_and_budget() -> None:
    svc = await _service()
    recs = await svc.recommend("a dress", Constraints(category="Dress", budget_max=60))
    assert recs
    assert all(r.price <= 60 for r in recs)
    assert all("dress" in r.title.lower() for r in recs)


async def test_recommend_excludes_out_of_stock() -> None:
    svc = await _service(stock_ok=False)
    recs = await svc.recommend("a dress", Constraints(category="Dress"))
    assert recs == []  # nothing suggested when everything is out of stock


async def test_complete_the_look_returns_complements() -> None:
    svc = await _service()
    recs = await svc.complete_the_look("Jeans", Constraints())
    # Complements of Jeans are Shirt/Sweater/Jacket — never another pair of jeans.
    assert recs
    assert all("jean" not in r.title.lower() for r in recs)
