"""Text chunking.

A simple, deterministic, paragraph-aware splitter with character budgeting and
overlap. Good enough for policies/FAQs/size guides (Phase 1); product-aware
chunking arrives with catalog sync (Phase 2). Kept dependency-free and pure so
it is trivially unit-testable.
"""

from __future__ import annotations

import re

from app.rag.models import Chunk, Document

_PARAGRAPH = re.compile(r"\n\s*\n")


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _PARAGRAPH.split(text) if p.strip()]


def chunk_document(doc: Document, *, max_chars: int = 800, overlap_chars: int = 100) -> list[Chunk]:
    """Split a document into overlapping, paragraph-aware chunks.

    Args:
        doc: The source document.
        max_chars: Soft maximum characters per chunk.
        overlap_chars: Characters of trailing context repeated into the next
            chunk to preserve continuity across a split.

    Returns:
        Ordered chunks with stable ids (``<doc-id>::<n>``) and inherited metadata.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be in [0, max_chars)")

    chunks: list[str] = []
    current = ""
    for para in _split_paragraphs(doc.text):
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}"
        else:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail}\n\n{para}".strip() if tail else para
    if current:
        chunks.append(current)

    # Hard-split any chunk that is still oversized (a single huge paragraph).
    bounded: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            bounded.append(c)
            continue
        step = max_chars - overlap_chars
        for start in range(0, len(c), step):
            bounded.append(c[start : start + max_chars])

    return [
        Chunk(
            id=f"{doc.id}::{i}",
            document_id=doc.id,
            text=text,
            metadata=dict(doc.metadata),
        )
        for i, text in enumerate(bounded)
    ]
