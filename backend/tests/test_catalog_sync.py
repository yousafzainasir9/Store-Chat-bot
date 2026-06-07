"""Integration tests for catalog sync over the offline Fake Shopify client."""

from __future__ import annotations

import pytest
from app.config import Environment, Settings
from app.rag.embeddings import HashingEmbedder
from app.rag.indexer import Indexer
from app.rag.vector_store import InMemoryVectorStore
from app.shopify.catalog_sync import CatalogSyncService
from app.shopify.fake import FakeShopifyClient

pytestmark = pytest.mark.asyncio


async def _service(n: int = 6) -> tuple[CatalogSyncService, InMemoryVectorStore, FakeShopifyClient]:
    store = InMemoryVectorStore()
    indexer = Indexer(HashingEmbedder(dimension=256), store)
    client = FakeShopifyClient(n_products=n)
    return CatalogSyncService(client, indexer, embed_batch_size=4), store, client


async def test_full_import_indexes_products() -> None:
    service, store, client = await _service(6)
    chunks = await service.full_import(lines=client.jsonl_lines)
    assert chunks >= 6
    assert await store.count() >= 6


async def test_reindex_replaces_single_product() -> None:
    service, store, client = await _service(4)
    await service.full_import(lines=client.jsonl_lines)
    before = await store.count()
    # Re-importing the same catalog must not duplicate (replace=True per doc id).
    await service.full_import(lines=client.jsonl_lines)
    assert await store.count() == before


async def test_filtered_retrieval_by_category(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.container import build_container

    settings = Settings(environment=Environment.TEST, demo_mode=True, log_json=True)
    container = build_container(settings)
    await container.bootstrap()
    # Retrieve with a category filter; every hit must match the filter.
    results = await container.retriever.retrieve("a nice top", filters={"category": "Dress"})
    assert results
    assert all(r.chunk.metadata.get("category") == "Dress" for r in results)
