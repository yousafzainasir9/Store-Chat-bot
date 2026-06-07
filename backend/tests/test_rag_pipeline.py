"""Tests for the offline RAG pipeline (embed -> store -> retrieve -> rerank)."""

from __future__ import annotations

import pytest
from app.rag.embeddings import HashingEmbedder
from app.rag.indexer import Indexer
from app.rag.models import Document
from app.rag.reranker import OverlapReranker
from app.rag.retriever import Retriever
from app.rag.vector_store import InMemoryVectorStore

pytestmark = pytest.mark.asyncio


async def _build() -> Retriever:
    embedder = HashingEmbedder(dimension=256)
    store = InMemoryVectorStore()
    docs = [
        Document(
            id="ship",
            text="Standard shipping takes 3 to 5 business days.",
            metadata={"source": "Shipping"},
        ),
        Document(
            id="ret",
            text="Returns are accepted within 30 days of delivery.",
            metadata={"source": "Returns"},
        ),
        Document(id="size", text="Size M fits a 36 to 37 inch bust.", metadata={"source": "Size"}),
    ]
    await Indexer(embedder, store).index(docs)
    return Retriever(embedder, store, OverlapReranker(), candidate_k=10, final_k=2)


async def test_retrieval_finds_relevant_source() -> None:
    retriever = await _build()
    results = await retriever.retrieve("how long does shipping take")
    assert results
    assert results[0].citation == "Shipping"


async def test_reindex_replaces_old_chunks() -> None:
    embedder = HashingEmbedder(dimension=128)
    store = InMemoryVectorStore()
    indexer = Indexer(embedder, store)
    await indexer.index([Document(id="x", text="old shipping text", metadata={})])
    await indexer.index([Document(id="x", text="new shipping text", metadata={})])
    assert await store.count() == 1


async def test_empty_query_returns_nothing() -> None:
    retriever = await _build()
    assert await retriever.retrieve("   ") == []
