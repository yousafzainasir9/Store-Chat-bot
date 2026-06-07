"""LLM provider abstraction.

The orchestrator depends only on :class:`LLMProvider` — never on a concrete SDK.
Adding a provider is implementing this Protocol and registering it in the
factory; no orchestrator code changes. Streaming, tool-calling (Phase 3), and
embeddings all live behind this one seam so cost logging and swapping stay in
our control (see DEVELOPMENT_PLAN.md §2.3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Role(StrEnum):
    """Chat message role."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class Message:
    """A single chat message."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage for one completion (drives cost metering)."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ChatResult:
    """A non-streamed chat completion."""

    text: str
    model: str
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True, slots=True)
class ChatChunk:
    """A streamed delta. ``done`` marks the terminal chunk and carries usage."""

    delta: str = ""
    done: bool = False
    usage: Usage | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Interface every LLM backend implements."""

    name: str

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """Return a full completion for ``messages``."""
        ...

    def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Yield completion deltas for ``messages`` as they are produced."""
        ...

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...
