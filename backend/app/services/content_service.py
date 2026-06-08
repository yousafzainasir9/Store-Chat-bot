"""Content service: editable FAQs/policies kept in sync with the search index.

Every create/update re-indexes the item into the text vector store; every delete
removes it. This is the write side of the Phase-7 admin: an edited FAQ is
reflected in answers immediately (DEVELOPMENT_PLAN.md §8.2). Content items use a
stable document id (``content::<id>``) so re-indexing replaces cleanly and never
collides with seed or catalog documents.
"""

from __future__ import annotations

import uuid

from app.models.content import ContentItem, _now
from app.observability.logging import get_logger
from app.rag.indexer import Indexer
from app.rag.models import Document
from app.repositories.content import ContentRepository

_log = get_logger("content_service")

_DOC_PREFIX = "content::"


def _to_document(item: ContentItem) -> Document:
    return Document(
        id=f"{_DOC_PREFIX}{item.id}",
        text=f"{item.title}\n{item.body}",
        metadata={
            "source": item.source,
            "title": item.title,
            "category": item.category,
            "content_id": item.id,
            "locale": item.locale,
        },
    )


class ContentService:
    """CRUD for content with automatic (de)indexing into the text store."""

    def __init__(self, repo: ContentRepository, indexer: Indexer) -> None:
        self._repo = repo
        self._indexer = indexer

    async def list_all(self) -> list[ContentItem]:
        return await self._repo.list()

    async def get(self, content_id: str) -> ContentItem | None:
        return await self._repo.get(content_id)

    async def create(
        self,
        *,
        title: str,
        body: str,
        category: str = "FAQ",
        source: str = "FAQ",
        locale: str = "en",
    ) -> ContentItem:
        item = ContentItem(
            id=uuid.uuid4().hex,
            title=title,
            body=body,
            category=category,
            source=source,
            locale=locale,
        )
        await self._repo.upsert(item)
        await self._indexer.index([_to_document(item)])
        _log.info("content_created", content_id=item.id, title=title)
        return item

    async def create_many(self, items: list[tuple[str, str, str]]) -> list[ContentItem]:
        """Create + index multiple content items; returns the created items.

        Each tuple is ``(title, body, category)``. Used by the FAQ-document
        import so a whole uploaded document becomes answerable at once.
        """
        created: list[ContentItem] = []
        for title, body, category in items:
            created.append(await self.create(title=title, body=body, category=category))
        return created

    async def update(
        self,
        content_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        category: str | None = None,
    ) -> ContentItem | None:
        item = await self._repo.get(content_id)
        if item is None:
            return None
        if title is not None:
            item.title = title
        if body is not None:
            item.body = body
        if category is not None:
            item.category = category
        item.updated_at = _now()
        await self._repo.upsert(item)
        await self._indexer.index([_to_document(item)])  # replace=True re-indexes
        _log.info("content_updated", content_id=content_id)
        return item

    async def delete(self, content_id: str) -> bool:
        deleted = await self._repo.delete(content_id)
        if deleted:
            await self._indexer.delete_document(f"{_DOC_PREFIX}{content_id}")
            _log.info("content_deleted", content_id=content_id)
        return deleted
