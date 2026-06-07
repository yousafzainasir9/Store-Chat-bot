"""Tests for chunking."""

from __future__ import annotations

import pytest
from app.rag.chunking import chunk_document
from app.rag.models import Document


def test_chunks_inherit_metadata_and_stable_ids() -> None:
    doc = Document(id="d1", text="Para one.\n\nPara two.", metadata={"source": "FAQ"})
    chunks = chunk_document(doc, max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].id == "d1::0"
    assert chunks[0].metadata["source"] == "FAQ"


def test_oversized_paragraph_is_hard_split() -> None:
    doc = Document(id="d2", text="x" * 2500)
    chunks = chunk_document(doc, max_chars=800, overlap_chars=100)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 800 for c in chunks)


def test_invalid_overlap_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_document(Document(id="d", text="hi"), max_chars=100, overlap_chars=100)
