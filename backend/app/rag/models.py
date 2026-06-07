"""Core RAG data types shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Document:
    """A source document to be ingested (FAQ, policy, size guide, product...)."""

    id: str
    text: str
    # Free-form metadata used for filtering + citations (source, category, url...).
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    """A chunk of a document, the unit that gets embedded and retrieved."""

    id: str
    document_id: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A chunk with a relevance score from retrieval or reranking."""

    chunk: Chunk
    score: float

    @property
    def citation(self) -> str:
        """A short human-readable source label for grounding."""
        meta = self.chunk.metadata
        return meta.get("source") or meta.get("title") or self.chunk.document_id
