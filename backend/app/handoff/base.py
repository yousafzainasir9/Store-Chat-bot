"""Human-handoff abstraction.

Handoff is a first-class flow, not a dead-end message (DEVELOPMENT_PLAN.md §8.1).
The orchestrator transfers the transcript + context + detected intent to whatever
channel is configured. Phase 1 ships the logging adapter; Gorgias/Zendesk/Inbox
adapters implement the same interface in later phases.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from app.llm.base import Message


class HandoffReason(StrEnum):
    """Why a conversation was escalated (tracked as a KPI)."""

    LOW_CONFIDENCE = "low_confidence"
    OUT_OF_SCOPE = "out_of_scope"
    USER_REQUEST = "user_request"
    INJECTION = "injection"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class HandoffTicket:
    """The package handed to a human agent."""

    conversation_id: str
    reason: HandoffReason
    transcript: Sequence[Message]
    context: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HandoffResult:
    """Outcome of a handoff attempt."""

    accepted: bool
    ticket_id: str | None = None
    detail: str = ""


class HandoffProvider(Protocol):
    """Routes a :class:`HandoffTicket` to a human channel."""

    name: str

    async def create(self, ticket: HandoffTicket) -> HandoffResult: ...
