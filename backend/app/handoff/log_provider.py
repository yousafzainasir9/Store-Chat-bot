"""Logging handoff provider: records the escalation and returns a ticket id.

The Phase-1 default. It guarantees handoff is never a dead end (we always have a
durable record), and gives the admin dashboard handoff-rate data to surface.
"""

from __future__ import annotations

import uuid

from app.core.guardrails import redact_pii
from app.handoff.base import HandoffProvider, HandoffResult, HandoffTicket
from app.observability.logging import get_logger

_log = get_logger("handoff")


class LoggingHandoffProvider(HandoffProvider):
    """Persists handoff intent to the structured log (PII-redacted)."""

    def __init__(self) -> None:
        self.name = "logging"

    async def create(self, ticket: HandoffTicket) -> HandoffResult:
        ticket_id = uuid.uuid4().hex
        _log.info(
            "handoff_created",
            ticket_id=ticket_id,
            conversation_id=ticket.conversation_id,
            reason=ticket.reason.value,
            turns=len(ticket.transcript),
            context={k: redact_pii(v) for k, v in ticket.context.items()},
        )
        return HandoffResult(accepted=True, ticket_id=ticket_id, detail="logged")
