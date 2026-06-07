"""Conversation domain models.

Plain, framework-free dataclasses used across services and repositories. The
SQLAlchemy ORM mapping lives in ``app.repositories.sql`` so the domain stays
persistence-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class StoredMessage:
    """A single persisted message within a conversation."""

    id: str
    conversation_id: str
    role: MessageRole
    content: str
    citations: list[str] = field(default_factory=list)
    handoff_reason: str | None = None
    confidence: float = 0.0
    token_count: int = 0
    created_at: datetime = field(default_factory=_now)


@dataclass(slots=True)
class Conversation:
    """A customer conversation."""

    id: str
    locale: str = "en"
    created_at: datetime = field(default_factory=_now)
    messages: list[StoredMessage] = field(default_factory=list)


@dataclass(slots=True)
class Feedback:
    """Thumbs up/down feedback on an assistant message."""

    id: str
    conversation_id: str
    message_id: str
    value: str
    comment: str | None = None
    created_at: datetime = field(default_factory=_now)
