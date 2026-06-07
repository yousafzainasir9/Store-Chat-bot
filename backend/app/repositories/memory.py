"""In-memory conversation repository (demo mode / CI / reference)."""

from __future__ import annotations

from datetime import datetime

from app.models.conversation import Conversation, Feedback, StoredMessage


class InMemoryConversationRepository:
    """Thread-unsafe, process-local store. Not for production."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._feedback: list[Feedback] = []

    async def get_or_create(self, conversation_id: str, *, locale: str = "en") -> Conversation:
        conv = self._conversations.get(conversation_id)
        if conv is None:
            conv = Conversation(id=conversation_id, locale=locale)
            self._conversations[conversation_id] = conv
        return conv

    async def add_message(self, message: StoredMessage) -> None:
        conv = await self.get_or_create(message.conversation_id)
        conv.messages.append(message)

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    async def list_conversations(self, *, limit: int = 100) -> list[Conversation]:
        items = sorted(self._conversations.values(), key=lambda c: c.created_at, reverse=True)
        return items[:limit]

    async def delete_conversation(self, conversation_id: str) -> bool:
        existed = self._conversations.pop(conversation_id, None) is not None
        self._feedback = [f for f in self._feedback if f.conversation_id != conversation_id]
        return existed

    async def purge_older_than(self, cutoff: datetime) -> int:
        stale = [cid for cid, c in self._conversations.items() if c.created_at < cutoff]
        for cid in stale:
            await self.delete_conversation(cid)
        return len(stale)

    async def add_feedback(self, feedback: Feedback) -> None:
        self._feedback.append(feedback)

    async def list_feedback(self) -> list[Feedback]:
        return list(self._feedback)
