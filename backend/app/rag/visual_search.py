"""Visual / multimodal product search (DEVELOPMENT_PLAN.md Phase 5).

Two pieces over a *parallel image collection*:

* :class:`VisualIndexer` — back-indexes catalog product images into the image
  vector store. The image bytes come from a pluggable source: offline we derive
  a deterministic attribute descriptor from product metadata (no real images
  needed for demo/CI); in production we download each product's image URL.
* :class:`VisualSearchService` — "find me something like this photo": embed the
  customer's image, find nearest in-catalog products, apply the same constraint
  filters as text recommendations, verify stock **live**, and return ranked
  matches with citations.

Stock and price stay live (never trusted from the index); the image vector only
drives visual similarity.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from app.observability.logging import get_logger
from app.observability.metrics import metrics
from app.rag.image_embeddings import ImageEmbedder
from app.rag.models import Chunk, Document
from app.rag.vector_store import VectorRecord, VectorStore
from app.recommendations.constraints import Constraints
from app.recommendations.service import Recommendation, passes_constraints, to_recommendation
from app.shopify.orders import OrderService, ToolStatus

_log = get_logger("visual_search")

# Resolves product metadata -> image bytes (descriptor offline, download online).
ImageSource = Callable[[dict[str, str]], Awaitable[bytes | None]]


async def offline_descriptor_source(meta: dict[str, str]) -> bytes | None:
    """Offline image bytes: an attribute descriptor derived from metadata."""
    descriptor = " ".join(
        v for v in (meta.get("colors", ""), meta.get("category", ""), meta.get("title", "")) if v
    ).strip()
    return descriptor.encode("utf-8") if descriptor else None


class VisualIndexer:
    """Embeds catalog product images into the parallel image collection."""

    def __init__(
        self, embedder: ImageEmbedder, store: VectorStore, image_source: ImageSource
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._image_source = image_source

    async def index(self, documents: Sequence[Document]) -> int:
        """Back-index product images; returns the number of images indexed."""
        chunks: list[Chunk] = []
        payloads: list[bytes] = []
        for doc in documents:
            if doc.metadata.get("source") != "Product":
                continue
            image = await self._image_source(doc.metadata)
            if image is None:
                continue
            await self._store.delete_document(doc.id)
            chunks.append(
                Chunk(
                    id=f"{doc.id}::image",
                    document_id=doc.id,
                    text=doc.metadata.get("title", ""),
                    metadata=dict(doc.metadata),
                )
            )
            payloads.append(image)
        if not chunks:
            return 0
        vectors = await self._embedder.embed(payloads)
        await self._store.upsert(
            [VectorRecord(chunk=c, vector=v) for c, v in zip(chunks, vectors, strict=True)]
        )
        _log.info("visual_index", images=len(chunks))
        return len(chunks)


class VisualSearchService:
    """Image-query product search with constraint filtering + live stock check."""

    def __init__(
        self,
        embedder: ImageEmbedder,
        store: VectorStore,
        order_service: OrderService,
        *,
        candidate_k: int = 30,
        max_results: int = 5,
        verify_live_stock: bool = True,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._orders = order_service
        self._candidate_k = candidate_k
        self._max_results = max_results
        self._verify_live_stock = verify_live_stock

    async def search(
        self, image: bytes, constraints: Constraints | None = None
    ) -> list[Recommendation]:
        """Return up to ``max_results`` in-stock products similar to ``image``."""
        constraints = constraints or Constraints()
        vector = (await self._embedder.embed([image]))[0]
        filters: dict[str, str] = {}
        if constraints.gender and constraints.gender != "unisex":
            filters["gender"] = constraints.gender
        candidates = await self._store.search(
            vector, top_k=self._candidate_k, filters=filters or None
        )

        results: list[Recommendation] = []
        for sc in candidates:
            chunk = sc.chunk
            if not passes_constraints(chunk, constraints):
                continue
            if self._verify_live_stock and not await self._in_stock(chunk):
                continue
            results.append(to_recommendation(chunk, constraints))
            if len(results) >= self._max_results:
                break

        metrics.incr("visual_search_total")
        _log.info("visual_search", returned=len(results), candidates=len(candidates))
        return results

    async def _in_stock(self, chunk: Chunk) -> bool:
        title = chunk.metadata.get("title") or chunk.metadata.get("handle") or ""
        result = await self._orders.check_stock(title)
        return result.status is ToolStatus.OK and result.data.get("available") == "True"
