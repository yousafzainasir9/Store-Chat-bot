"""Compliance service: data export, deletion, and retention (Phase 8).

Implements the data-subject rights and retention controls from the plan
(DEVELOPMENT_PLAN.md §6): export a conversation's stored data, delete it on
request, and purge conversations older than the configured retention window.
Conversations are not keyed to a customer identity (the bot is anonymous unless
a customer verifies an order), so subject requests operate on conversation ids.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.observability.logging import get_logger
from app.repositories.base import ConversationRepository

_log = get_logger("compliance")


class ComplianceService:
    """Export / delete / retention operations over stored conversations."""

    def __init__(self, repo: ConversationRepository, *, retention_days: int = 365) -> None:
        self._repo = repo
        self._retention_days = retention_days

    async def export_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """Return a machine-readable export of a conversation's stored data."""
        conv = await self._repo.get(conversation_id)
        if conv is None:
            return None
        return {
            "conversation_id": conv.id,
            "locale": conv.locale,
            "created_at": conv.created_at.isoformat(),
            "messages": [
                {
                    "role": m.role.value,
                    "content": m.content,
                    "citations": m.citations,
                    "handoff_reason": m.handoff_reason,
                    "created_at": m.created_at.isoformat(),
                }
                for m in conv.messages
            ],
        }

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Erase a conversation and its feedback (right to erasure)."""
        deleted = await self._repo.delete_conversation(conversation_id)
        _log.info("compliance_delete", conversation_id=conversation_id, deleted=deleted)
        return deleted

    async def purge_expired(self) -> int:
        """Delete conversations older than the retention window."""
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        purged = await self._repo.purge_older_than(cutoff)
        _log.info("compliance_purge", purged=purged, retention_days=self._retention_days)
        return purged
