"""Chat + feedback API schemas (validated I/O boundary)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """A prior turn supplied by the client for conversational context."""

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    """Inbound chat message."""

    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=64)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class FeedbackValue(StrEnum):
    """Thumbs up/down on an assistant message."""

    UP = "up"
    DOWN = "down"


class FeedbackRequest(BaseModel):
    """Feedback on an assistant message (feeds the content-gap loop)."""

    conversation_id: str = Field(max_length=64)
    message_id: str = Field(max_length=64)
    value: FeedbackValue
    comment: str | None = Field(default=None, max_length=2000)
