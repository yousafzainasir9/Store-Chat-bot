"""Retriever: embed the query, search the vector store, then rerank.

Encapsulates the retrieve→rerank step so the orchestrator stays declarative. The
two-stage default (vector top-N -> reranked top-k) is the precision win from the
plan; reranking only the shortlist keeps the added latency/cost small.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.rag.embeddings import Embedder
from app.rag.models import ScoredChunk
from app.rag.reranker import Reranker
from app.rag.vector_store import VectorStore


class Retriever:
    """Two-stage retrieval: dense search followed by reranking."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        reranker: Reranker,
        *,
        candidate_k: int = 20,
        final_k: int = 5,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._reranker = reranker
        self._candidate_k = candidate_k
        self._final_k = final_k

    async def retrieve(
        self, query: str, *, filters: Mapping[str, str] | None = None
    ) -> list[ScoredChunk]:
        """Return the reranked top-k chunks for ``query``."""
        if not query.strip():
            return []
        query_vector = (await self._embedder.embed([query]))[0]
        candidates = await self._store.search(
            query_vector, top_k=self._candidate_k, filters=filters
        )
        if not candidates:
            return []
        return await self._reranker.rerank(query, candidates, top_k=self._final_k)
