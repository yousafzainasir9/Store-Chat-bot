"""Rerankers.

After vector search returns top-N candidates, a reranker re-scores them so the
*best* chunk wins, not merely a semantically close one — a real quality win for
near-identical fashion items (DEVELOPMENT_PLAN.md §2.4). Two implementations:

* :class:`OverlapReranker` — dependency-free lexical overlap (token F1). Offline
  default; cheap and deterministic.
* :class:`CrossEncoderReranker` — a sentence-transformers cross-encoder (lazy
  import) for production-grade precision.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from app.rag.models import ScoredChunk

_TOKEN = re.compile(r"[a-z0-9]+")

# Function words carry little topical signal; dropping them sharpens both
# overlap precision and out-of-scope rejection (a stopword-only "match" should
# not clear the confidence bar).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "could",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "should",
        "that",
        "the",
        "to",
        "us",
        "we",
        "what",
        "when",
        "where",
        "which",
        "will",
        "with",
        "you",
        "your",
    }
)


class Reranker(Protocol):
    """Re-scores candidate chunks against the query; returns top_k, best first."""

    async def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], *, top_k: int = 5
    ) -> list[ScoredChunk]: ...


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS}


class OverlapReranker:
    """Lexical overlap-coefficient reranker. Offline default.

    Scores ``|query ∩ doc| / min(|query|, |doc|)`` over content tokens
    (stopwords removed). This rewards a short user query being *contained* in a
    chunk without penalizing the chunk for being long — so a terse
    "show me jeans" scores well against a long product description, while
    off-topic queries (no content overlap) score ~0 and correctly route to
    handoff. A production cross-encoder replaces this for finer precision.
    """

    async def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], *, top_k: int = 5
    ) -> list[ScoredChunk]:
        q = _tokens(query)
        rescored: list[ScoredChunk] = []
        for cand in candidates:
            c = _tokens(cand.chunk.text)
            if not q or not c:
                score = 0.0
            else:
                overlap = len(q & c)
                score = overlap / min(len(q), len(c))
            rescored.append(ScoredChunk(chunk=cand.chunk, score=score))
        rescored.sort(key=lambda s: s.score, reverse=True)
        return rescored[:top_k]


class CrossEncoderReranker:
    """sentence-transformers cross-encoder reranker (lazy import)."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model_name = model_name
        self._model: object | None = None

    def _get_model(self) -> object:
        if self._model is None:
            from sentence_transformers import CrossEncoder  # lazy import

            self._model = CrossEncoder(self._model_name)
        return self._model

    async def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], *, top_k: int = 5
    ) -> list[ScoredChunk]:
        if not candidates:
            return []
        import asyncio

        model = self._get_model()
        pairs = [(query, c.chunk.text) for c in candidates]
        scores = await asyncio.to_thread(model.predict, pairs)  # type: ignore[attr-defined]
        rescored = [
            ScoredChunk(chunk=c.chunk, score=float(s))
            for c, s in zip(candidates, scores, strict=True)
        ]
        rescored.sort(key=lambda s: s.score, reverse=True)
        return rescored[:top_k]
