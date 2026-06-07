"""Image embedding interfaces and an offline embedder.

Visual search runs on a *separate* embedding model and vector collection from the
text index — image vectors and text vectors have different semantics and
dimensions and must never be mixed (DEVELOPMENT_PLAN.md §2.3).

* :class:`FakeImageEmbedder` — deterministic, dependency-free. It decodes the
  image bytes as a short descriptor (in demo/CI we back-index and query with
  attribute descriptors like ``"navy dress"``) and embeds that via the text
  hashing embedder, so visual similarity tracks attribute overlap offline with
  no model. Non-text bytes fall back to a stable hash token.
* :class:`CLIPImageEmbedder` — a real CLIP-class encoder (lazy import) that
  embeds actual image bytes for production visual search.

The same embedder must encode both the catalog images (at index time) and the
customer's query image (at search time).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.rag.embeddings import HashingEmbedder


@runtime_checkable
class ImageEmbedder(Protocol):
    """Turns raw image bytes into vectors. One model per image collection."""

    dimension: int

    async def embed(self, images: Sequence[bytes]) -> list[list[float]]:
        """Return one vector per input image."""
        ...


class FakeImageEmbedder:
    """Deterministic offline image embedder (descriptor-based)."""

    def __init__(self, dimension: int = 512) -> None:
        self.dimension = dimension
        self._text = HashingEmbedder(dimension=dimension)

    @staticmethod
    def _to_descriptor(data: bytes) -> str:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return hashlib.blake2b(data, digest_size=8).hexdigest()
        # Treat readable payloads as attribute descriptors; hash binary-ish blobs
        # so identical images still collide deterministically.
        if text.isprintable():
            return text
        return hashlib.blake2b(data, digest_size=8).hexdigest()

    async def embed(self, images: Sequence[bytes]) -> list[list[float]]:
        return await self._text.embed([self._to_descriptor(b) for b in images])


class CLIPImageEmbedder:
    """Real CLIP-class image embedder (lazy ``sentence-transformers`` import)."""

    def __init__(self, model_name: str = "clip-ViT-B-32", *, dimension: int = 512) -> None:
        self.dimension = dimension
        self._model_name = model_name
        self._model: object | None = None

    def _get_model(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # lazy import

            self._model = SentenceTransformer(self._model_name)
        return self._model

    async def embed(self, images: Sequence[bytes]) -> list[list[float]]:
        import asyncio
        import io

        from PIL import Image  # lazy import

        model = self._get_model()

        def _encode() -> list[list[float]]:
            pil_images = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
            vectors = model.encode(pil_images, normalize_embeddings=True)  # type: ignore[attr-defined]
            return [list(map(float, v)) for v in vectors]

        return await asyncio.to_thread(_encode)
