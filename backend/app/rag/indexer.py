"""Indexer: ingest documents (chunk -> embed -> upsert).

The single entry point used by both the seed loader (Phase 1) and the
webhook-driven re-index worker (Phase 2). Re-indexing a document deletes its
prior chunks first so stale content never lingers.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.observability.logging import get_logger
from app.rag.chunking import chunk_document
from app.rag.embeddings import Embedder
from app.rag.models import Document
from app.rag.vector_store import VectorRecord, VectorStore

_log = get_logger("indexer")


class Indexer:
    """Turns documents into embedded, searchable chunks."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        *,
        max_chars: int = 800,
        overlap_chars: int = 100,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars

    async def index(self, documents: Sequence[Document], *, replace: bool = True) -> int:
        """Index ``documents``; returns the number of chunks written."""
        total = 0
        for doc in documents:
            if replace:
                await self._store.delete_document(doc.id)
            chunks = chunk_document(
                doc, max_chars=self._max_chars, overlap_chars=self._overlap_chars
            )
            if not chunks:
                continue
            vectors = await self._embedder.embed([c.text for c in chunks])
            records = [
                VectorRecord(chunk=c, vector=v) for c, v in zip(chunks, vectors, strict=True)
            ]
            await self._store.upsert(records)
            total += len(records)
        _log.info("indexed", documents=len(documents), chunks=total)
        return total

    async def delete_document(self, document_id: str) -> None:
        """Remove a document's chunks from the index (used by incremental sync)."""
        await self._store.delete_document(document_id)
