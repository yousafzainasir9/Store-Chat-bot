"""Embedding interfaces and an offline embedder.

``Embedder`` is the seam the retriever depends on. Two implementations:

* :class:`HashingEmbedder` — deterministic, dependency-free bag-of-tokens vectors
  hashed into a fixed dimension and L2-normalized. Cosine similarity then tracks
  token overlap, which makes retrieval *meaningfully functional offline* (demo
  mode + CI) without any API call.
* :class:`ProviderEmbedder` — delegates to an :class:`LLMProvider` (OpenAI/Gemini)
  for real semantic embeddings in deployed environments.

One model per index — never mix dimensions in a single collection.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.llm.base import LLMProvider

_TOKEN = re.compile(r"[a-z0-9]+")


@runtime_checkable
class Embedder(Protocol):
    """Turns text into vectors. One model per index."""

    dimension: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input text."""
        ...


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


class HashingEmbedder:
    """Deterministic hashing vectorizer; no network, stable across runs."""

    def __init__(self, dimension: int = 512) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for tok in _tokenize(text):
            h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "big") % self.dimension
            sign = 1.0 if h[4] & 1 else -1.0
            vec[idx] += sign
        return _l2_normalize(vec)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class ProviderEmbedder:
    """Embedder backed by an :class:`LLMProvider` (real semantic embeddings)."""

    def __init__(self, provider: LLMProvider, *, dimension: int, model: str | None = None) -> None:
        self._provider = provider
        self._model = model
        self.dimension = dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._provider.embed(texts, model=self._model)
