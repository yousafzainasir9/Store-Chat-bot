"""Chat + feedback endpoints.

``POST /chat``      — stream a grounded answer over Server-Sent Events.
``POST /feedback``  — record thumbs up/down (feeds the Phase-7 content-gap loop).

The route is a thin transport: it validates input, delegates orchestration to the
container's :class:`Orchestrator`, persists the turn, and serializes events as
SSE. No business logic lives here.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.api.ratelimit import enforce_rate_limit
from app.api.widget import enforce_widget_token
from app.core.orchestrator import AI_DISCLOSURE
from app.llm.base import Message, Role
from app.models.conversation import Feedback, MessageRole, StoredMessage
from app.observability.logging import get_logger
from app.schemas.chat import ChatRequest, ChatTurn, FeedbackRequest
from app.services.container import Container

router = APIRouter(tags=["chat"])
_log = get_logger("chat")


def _container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


def _to_messages(turns: list[ChatTurn]) -> list[Message]:
    out: list[Message] = []
    for t in turns:
        role = Role.USER if t.role == "user" else Role.ASSISTANT
        out.append(Message(role=role, content=t.content))
    return out


@router.post(
    "/chat",
    summary="Stream a grounded answer (SSE)",
    dependencies=[Depends(enforce_rate_limit), Depends(enforce_widget_token)],
)
async def chat(request: Request, body: ChatRequest) -> EventSourceResponse:
    """Stream the assistant's grounded answer for one user turn."""
    container = _container(request)
    conversation_id = body.conversation_id or uuid.uuid4().hex
    assistant_message_id = uuid.uuid4().hex
    history = _to_messages(body.history)

    await container.repository.get_or_create(conversation_id)
    await container.repository.add_message(
        StoredMessage(
            id=uuid.uuid4().hex,
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=body.message,
        )
    )

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        # Announce identifiers + AI disclosure before any tokens.
        yield {
            "event": "meta",
            "data": json.dumps(
                {
                    "conversation_id": conversation_id,
                    "message_id": assistant_message_id,
                    "disclosure": AI_DISCLOSURE,
                }
            ),
        }
        answer_parts: list[str] = []
        citations: list[str] = []
        handoff_reason: str | None = None
        confidence = 0.0
        tokens = 0

        # Cost-runaway protection: a session that has spent its token budget is
        # handed off instead of invoking the model again.
        if container.budget.exceeded(conversation_id):
            msg = "Let me bring in a member of our team to continue helping you."
            yield {"event": "handoff", "data": json.dumps({"text": msg, "reason": "budget"})}
            yield {"event": "done", "data": json.dumps({"message_id": assistant_message_id})}
            await container.repository.add_message(
                StoredMessage(
                    id=assistant_message_id,
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=msg,
                    handoff_reason="budget",
                )
            )
            return

        async for ev in container.orchestrator.answer(
            conversation_id, body.message, history=history
        ):
            if ev.type == "token":
                answer_parts.append(ev.text)
                yield {"event": "token", "data": ev.text}
            elif ev.type == "handoff":
                handoff_reason = ev.handoff_reason
                confidence = ev.confidence
                answer_parts.append(ev.text)
                yield {
                    "event": "handoff",
                    "data": json.dumps({"text": ev.text, "reason": ev.handoff_reason}),
                }
            elif ev.type == "citations":
                citations = ev.citations
                confidence = ev.confidence
                yield {"event": "citations", "data": json.dumps(ev.citations)}
            elif ev.type == "done":
                confidence = ev.confidence or confidence
                tokens = ev.tokens or tokens

        # Record token spend against the session budget (anomaly alerting).
        container.budget.record(conversation_id, tokens)

        # Persist the assistant turn after the stream completes.
        await container.repository.add_message(
            StoredMessage(
                id=assistant_message_id,
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content="".join(answer_parts).strip(),
                citations=citations,
                handoff_reason=handoff_reason,
                confidence=confidence,
                token_count=tokens,
            )
        )
        yield {
            "event": "done",
            "data": json.dumps(
                {"message_id": assistant_message_id, "confidence": round(confidence, 4)}
            ),
        }

    return EventSourceResponse(event_stream())


@router.post("/feedback", summary="Record thumbs up/down on a reply")
async def feedback(request: Request, body: FeedbackRequest) -> dict[str, str]:
    """Persist feedback used by the Phase-7 content-gap loop."""
    container = _container(request)
    fb = Feedback(
        id=uuid.uuid4().hex,
        conversation_id=body.conversation_id,
        message_id=body.message_id,
        value=body.value.value,
        comment=body.comment,
    )
    await container.repository.add_feedback(fb)
    _log.info("feedback", conversation_id=body.conversation_id, value=body.value.value)
    return {"status": "ok", "feedback_id": fb.id}
