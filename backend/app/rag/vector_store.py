"""Vector store interface with an in-memory implementation (+ Qdrant adapter).

``VectorStore`` is the seam the retriever depends on.

* :class:`InMemoryVectorStore` — exact cosine search with payload filtering.
  Used in demo mode/CI and as a reference implementation. Fine for small
  catalogs; not for production scale.
* :class:`QdrantVectorStore` — the production store (lazy ``qdrant-client``
  import), with the same filtered-search contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.rag.models import Chunk, ScoredChunk


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """A chunk plus its embedding vector, ready to upsert."""

    chunk: Chunk
    vector: list[float]


class VectorStore(Protocol):
    """Filtered nearest-neighbour search over embedded chunks."""

    async def upsert(self, records: Sequence[VectorRecord]) -> None: ...

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int = 20,
        filters: Mapping[str, str] | None = None,
    ) -> list[ScoredChunk]: ...

    async def delete_document(self, document_id: str) -> None: ...

    async def count(self) -> int: ...


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    # Vectors are stored L2-normalized, so dot product == cosine similarity.
    return sum(x * y for x, y in zip(a, b, strict=True))


def _matches(chunk: Chunk, filters: Mapping[str, str] | None) -> bool:
    if not filters:
        return True
    return all(chunk.metadata.get(k) == v for k, v in filters.items())


class InMemoryVectorStore:
    """Exact cosine-similarity store backed by a dict. Reference + demo/CI."""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        for r in records:
            self._records[r.chunk.id] = r

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int = 20,
        filters: Mapping[str, str] | None = None,
    ) -> list[ScoredChunk]:
        scored = [
            ScoredChunk(chunk=r.chunk, score=_cosine(query_vector, r.vector))
            for r in self._records.values()
            if _matches(r.chunk, filters)
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]

    async def delete_document(self, document_id: str) -> None:
        self._records = {
            cid: r for cid, r in self._records.items() if r.chunk.document_id != document_id
        }

    async def count(self) -> int:
        return len(self._records)


class QdrantVectorStore:
    """Production vector store backed by Qdrant (lazy import)."""

    def __init__(self, url: str, *, collection: str, dimension: int, api_key: str | None = None):
        self._url = url
        self._collection = collection
        self._dimension = dimension
        self._api_key = api_key
        self._client: object | None = None

    def _get_client(self) -> object:
        if self._client is None:
            from qdrant_client import AsyncQdrantClient  # lazy import

            self._client = AsyncQdrantClient(url=self._url, api_key=self._api_key)
        return self._client

    async def ensure_collection(self) -> None:
        from qdrant_client import models as qm  # lazy import

        client = self._get_client()
        existing = await client.get_collections()  # type: ignore[attr-defined]
        names = {c.name for c in existing.collections}
        if self._collection not in names:
            await client.create_collection(  # type: ignore[attr-defined]
                collection_name=self._collection,
                vectors_config=qm.VectorParams(size=self._dimension, distance=qm.Distance.COSINE),
            )

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        from qdrant_client import models as qm  # lazy import

        client = self._get_client()
        points = [
            qm.PointStruct(
                id=abs(hash(r.chunk.id)) % (2**63),
                vector=r.vector,
                payload={
                    "chunk_id": r.chunk.id,
                    "document_id": r.chunk.document_id,
                    "text": r.chunk.text,
                    **r.chunk.metadata,
                },
            )
            for r in records
        ]
        await client.upsert(collection_name=self._collection, points=points)  # type: ignore[attr-defined]

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int = 20,
        filters: Mapping[str, str] | None = None,
    ) -> list[ScoredChunk]:
        from qdrant_client import models as qm  # lazy import

        client = self._get_client()
        flt = None
        if filters:
            flt = qm.Filter(
                must=[
                    qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
                    for k, v in filters.items()
                ]
            )
        hits = await client.search(  # type: ignore[attr-defined]
            collection_name=self._collection,
            query_vector=list(query_vector),
            limit=top_k,
            query_filter=flt,
        )
        out: list[ScoredChunk] = []
        for h in hits:
            payload = dict(h.payload or {})
            text = payload.pop("text", "")
            cid = payload.pop("chunk_id", "")
            did = payload.pop("document_id", "")
            out.append(
                ScoredChunk(
                    chunk=Chunk(id=cid, document_id=did, text=text, metadata=payload),
                    score=h.score,
                )
            )
        return out

    async def delete_document(self, document_id: str) -> None:
        from qdrant_client import models as qm  # lazy import

        client = self._get_client()
        await client.delete(  # type: ignore[attr-defined]
            collection_name=self._collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))
                    ]
                )
            ),
        )

    async def count(self) -> int:
        client = self._get_client()
        res = await client.count(collection_name=self._collection)  # type: ignore[attr-defined]
        return int(res.count)
