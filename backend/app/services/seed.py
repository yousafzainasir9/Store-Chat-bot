"""Load seed knowledge-base documents from the ``seed/`` directory.

Each ``.md`` file may begin with a simple ``---`` front-matter block of
``key: value`` metadata (source, category). Headed sections (``##``) become
individual documents so retrieval and citations are granular. This is the
Phase-1 content source; Phase 2 adds the Shopify catalog through the same
:class:`Document` shape.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.rag.models import Document

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, text[match.end() :]


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, content) by level-2 headings."""
    sections: list[tuple[str, str]] = []
    current_title = "Overview"
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return [(t, c) for t, c in sections if c]


def load_seed_documents(seed_dir: Path) -> list[Document]:
    """Read every ``.md`` file under ``seed_dir`` into granular documents."""
    documents: list[Document] = []
    for path in sorted(seed_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(raw)
        for idx, (title, content) in enumerate(_split_sections(body)):
            documents.append(
                Document(
                    id=f"{path.stem}::{idx}",
                    text=f"{title}\n{content}",
                    metadata={
                        **meta,
                        "title": title,
                        "file": path.name,
                    },
                )
            )
    return documents
