"""Repository interfaces.

Services depend on these Protocols, never on a concrete datastore. The in-memory
implementation backs demo mode/CI; the SQLAlchemy implementation backs Postgres
in deployed environments — selected in the composition root by config.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.models.conversation import Conversation, Feedback, StoredMessage


class ConversationRepository(Protocol):
    """Stores conversations, their messages, and feedback."""

    async def get_or_create(self, conversation_id: str, *, locale: str = "en") -> Conversation: ...

    async def add_message(self, message: StoredMessage) -> None: ...

    async def get(self, conversation_id: str) -> Conversation | None: ...

    async def list_conversations(self, *, limit: int = 100) -> list[Conversation]: ...

    async def delete_conversation(self, conversation_id: str) -> bool: ...

    async def purge_older_than(self, cutoff: datetime) -> int: ...

    async def add_feedback(self, feedback: Feedback) -> None: ...

    async def list_feedback(self) -> list[Feedback]: ...
