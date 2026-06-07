"""Content repository (editable FAQs/policies)."""

from __future__ import annotations

from typing import Protocol

from app.models.content import ContentItem


class ContentRepository(Protocol):
    """Stores editable content items managed in the admin dashboard."""

    async def list(self) -> list[ContentItem]: ...

    async def get(self, content_id: str) -> ContentItem | None: ...

    async def upsert(self, item: ContentItem) -> None: ...

    async def delete(self, content_id: str) -> bool: ...


class InMemoryContentRepository:
    """Process-local content store (demo/CI/reference)."""

    def __init__(self) -> None:
        self._items: dict[str, ContentItem] = {}

    async def list(self) -> list[ContentItem]:
        return sorted(self._items.values(), key=lambda i: i.updated_at, reverse=True)

    async def get(self, content_id: str) -> ContentItem | None:
        return self._items.get(content_id)

    async def upsert(self, item: ContentItem) -> None:
        self._items[item.id] = item

    async def delete(self, content_id: str) -> bool:
        return self._items.pop(content_id, None) is not None
