"""Admin dashboard API (Phase 7).

All routes are mounted under ``/admin`` and protected by :func:`require_admin`.
They power the React dashboard: content CRUD (which re-indexes), conversation
review, feedback, the content-gap loop, and analytics. Handlers stay thin —
business logic lives in the services.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.admin_auth import require_admin
from app.models.conversation import Conversation
from app.services.container import Container

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _c(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


# ----------------------------------------------------------------- schemas


class ContentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    category: str = Field(default="FAQ", max_length=64)
    source: str = Field(default="FAQ", max_length=120)
    locale: str = Field(default="en", max_length=10)


class ContentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=20000)
    category: str | None = Field(default=None, max_length=64)


class CreateFaqFromGap(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


# ----------------------------------------------------------------- content


@router.get("/content")
async def list_content(request: Request) -> dict[str, Any]:
    items = await _c(request).content.list()
    return {"items": [_content_dto(i) for i in items]}


@router.post("/content", status_code=status.HTTP_201_CREATED)
async def create_content(request: Request, body: ContentCreate) -> dict[str, Any]:
    item = await _c(request).content.create(
        title=body.title,
        body=body.body,
        category=body.category,
        source=body.source,
        locale=body.locale,
    )
    return _content_dto(item)


@router.patch("/content/{content_id}")
async def update_content(request: Request, content_id: str, body: ContentUpdate) -> dict[str, Any]:
    item = await _c(request).content.update(
        content_id, title=body.title, body=body.body, category=body.category
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found.")
    return _content_dto(item)


@router.delete("/content/{content_id}")
async def delete_content(request: Request, content_id: str) -> dict[str, Any]:
    if not await _c(request).content.delete(content_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found.")
    return {"status": "deleted", "id": content_id}


# ------------------------------------------------------------ conversations


@router.get("/conversations")
async def list_conversations(request: Request, limit: int = 100) -> dict[str, Any]:
    convs = await _c(request).repository.list_conversations(limit=limit)
    return {"items": [_conversation_summary(c) for c in convs]}


@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str) -> dict[str, Any]:
    conv = await _c(request).repository.get(conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return {
        "id": conv.id,
        "locale": conv.locale,
        "created_at": conv.created_at.isoformat(),
        "messages": [
            {
                "id": m.id,
                "role": m.role.value,
                "content": m.content,
                "citations": m.citations,
                "handoff_reason": m.handoff_reason,
                "confidence": m.confidence,
                "created_at": m.created_at.isoformat(),
            }
            for m in conv.messages
        ],
    }


# ---------------------------------------------------------------- feedback


@router.get("/feedback")
async def list_feedback(request: Request) -> dict[str, Any]:
    items = await _c(request).repository.list_feedback()
    return {
        "items": [
            {
                "id": f.id,
                "conversation_id": f.conversation_id,
                "message_id": f.message_id,
                "value": f.value,
                "comment": f.comment,
                "created_at": f.created_at.isoformat(),
            }
            for f in items
        ]
    }


# -------------------------------------------------------------------- gaps


@router.get("/gaps")
async def list_gaps(request: Request) -> dict[str, Any]:
    gaps = await _c(request).gaps.compute()
    return {
        "items": [
            {"suggested_title": g.suggested_title, "count": g.count, "examples": g.examples}
            for g in gaps
        ]
    }


@router.post("/gaps/create-faq", status_code=status.HTTP_201_CREATED)
async def create_faq_from_gap(request: Request, body: CreateFaqFromGap) -> dict[str, Any]:
    """One-click: turn a content gap into an indexed FAQ."""
    item = await _c(request).content.create(title=body.title, body=body.body, category="FAQ")
    return _content_dto(item)


# --------------------------------------------------------------- analytics


@router.get("/analytics")
async def analytics(request: Request) -> dict[str, Any]:
    data = await _c(request).analytics.summary()
    return data.__dict__


@router.get("/privacy/export/{conversation_id}", summary="Export a conversation (GDPR)")
async def export_conversation(request: Request, conversation_id: str) -> dict[str, Any]:
    data = await _c(request).compliance.export_conversation(conversation_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return data


@router.delete("/privacy/conversation/{conversation_id}", summary="Erase a conversation (GDPR)")
async def erase_conversation(request: Request, conversation_id: str) -> dict[str, Any]:
    deleted = await _c(request).compliance.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return {"status": "deleted", "id": conversation_id}


@router.post("/privacy/purge-expired", summary="Purge conversations past the retention window")
async def purge_expired(request: Request) -> dict[str, Any]:
    purged = await _c(request).compliance.purge_expired()
    return {"status": "ok", "purged": purged}


@router.get("/llm", summary="LLM fallback chain status")
async def llm_status(request: Request) -> dict[str, Any]:
    """Per-provider availability of the LLM fallback chain (no secrets)."""
    provider = _c(request).provider
    status_fn = getattr(provider, "status", None)
    if callable(status_fn):
        return {"chain": True, "providers": status_fn()}
    return {"chain": False, "provider": getattr(provider, "name", "unknown")}


@router.get("/freshness")
async def freshness(request: Request) -> dict[str, Any]:
    p = _c(request).freshness
    return p.__dict__


# ----------------------------------------------------------------- helpers


def _content_dto(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "body": item.body,
        "category": item.category,
        "source": item.source,
        "locale": item.locale,
        "updated_at": item.updated_at.isoformat(),
    }


def _conversation_summary(conv: Conversation) -> dict[str, Any]:
    last = conv.messages[-1].content if conv.messages else ""
    handed_off = any(m.handoff_reason for m in conv.messages)
    return {
        "id": conv.id,
        "created_at": conv.created_at.isoformat(),
        "message_count": len(conv.messages),
        "handed_off": handed_off,
        "preview": last[:120],
    }
