"""Editable knowledge-base content (FAQs / policies) managed via the admin UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ContentItem:
    """An editable FAQ/policy entry that is indexed for retrieval."""

    id: str
    title: str
    body: str
    category: str = "FAQ"
    source: str = "FAQ"
    locale: str = "en"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
