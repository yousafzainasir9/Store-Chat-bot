"""Webhook handoff provider.

POSTs the handoff ticket (transcript + context + reason) to a configurable URL.
One adapter covers Gorgias, Zendesk, an email-relay, or any internal endpoint —
the destination is just a URL + optional bearer token in config. ``httpx`` is
imported lazily so the offline default (logging provider) needs no network stack.

PII in the context map is redacted before transmission, consistent with the
logging adapter and the plan's privacy posture.
"""

from __future__ import annotations

import uuid

from app.core.guardrails import redact_pii
from app.handoff.base import HandoffProvider, HandoffResult, HandoffTicket
from app.llm.base import Role
from app.observability.logging import get_logger

_log = get_logger("handoff.webhook")


class WebhookHandoffProvider(HandoffProvider):
    """Delivers handoff tickets to an external help-desk via HTTP POST."""

    def __init__(self, url: str, *, token: str | None = None, timeout_s: float = 10.0) -> None:
        if not url:
            raise ValueError("handoff webhook url is required")
        self.name = "webhook"
        self._url = url
        self._token = token
        self._timeout_s = timeout_s

    async def create(self, ticket: HandoffTicket) -> HandoffResult:
        import httpx  # lazy import

        ticket_id = uuid.uuid4().hex
        payload = {
            "ticket_id": ticket_id,
            "conversation_id": ticket.conversation_id,
            "reason": ticket.reason.value,
            "transcript": [
                {"role": m.role.value, "content": _redact_for_role(m.role, m.content)}
                for m in ticket.transcript
            ],
            "context": {k: redact_pii(v) for k, v in ticket.context.items()},
        }
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.post(self._url, json=payload, headers=headers)
                resp.raise_for_status()
        except Exception as exc:  # never lose a handoff: log and report failure
            _log.error("handoff_webhook_failed", ticket_id=ticket_id, error=str(exc))
            return HandoffResult(accepted=False, ticket_id=ticket_id, detail=str(exc))
        _log.info(
            "handoff_webhook_sent", ticket_id=ticket_id, conversation_id=ticket.conversation_id
        )
        return HandoffResult(accepted=True, ticket_id=ticket_id, detail="webhook")


def _redact_for_role(role: Role, content: str) -> str:
    """Redact PII from customer-authored turns before sending off-platform."""
    return redact_pii(content) if role is Role.USER else content
