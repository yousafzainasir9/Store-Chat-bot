"""Deterministic, offline LLM provider for demo mode and tests.

No network, no API key. It produces a *grounded extractive* answer: it stitches
together the context the orchestrator already injected into the system/user
messages, so groundedness and citation behaviour can be exercised end-to-end in
CI. Embeddings use a hashing vectorizer (see ``rag.embeddings``) via a small
local import to keep token-overlap similarity meaningful offline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from app.llm.base import ChatChunk, ChatResult, LLMProvider, Message, Role, Usage

_DISCLAIMER = "I'm not certain from our information"


def _approx_tokens(text: str) -> int:
    """Rough token count (~4 chars/token) for offline cost metering."""
    return max(1, len(text) // 4)


def _compose_answer(messages: Sequence[Message]) -> str:
    """Build a deterministic answer from the most recent user turn + context.

    The orchestrator passes retrieved context inside a user message fenced by
    ``<context>`` tags. If present, we echo a grounded sentence; otherwise we
    return the low-confidence disclaimer so handoff logic can trigger.
    """
    last_user = next(
        (m.content for m in reversed(messages) if m.role is Role.USER),
        "",
    )
    if "<context>" in last_user and "</context>" in last_user:
        ctx = last_user.split("<context>", 1)[1].split("</context>", 1)[0].strip()
        if ctx:
            # A faithful deterministic stand-in for a grounded LLM: answer from
            # the retrieved context verbatim (capped), so the reply is provably
            # supported by — and traceable to — the sources the orchestrator fed.
            grounded = ctx[:1500].strip()
            return f"Based on our information: {grounded}"
    return f"{_DISCLAIMER}. Let me connect you with a human who can help."


class FakeLLMProvider(LLMProvider):
    """A deterministic provider that never calls the network."""

    def __init__(self, model: str = "fake-1") -> None:
        self.name = "fake"
        self._model = model

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        text = _compose_answer(messages)
        usage = Usage(
            input_tokens=sum(_approx_tokens(m.content) for m in messages),
            output_tokens=_approx_tokens(text),
        )
        return ChatResult(text=text, model=model or self._model, usage=usage)

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        result = await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        for word in result.text.split(" "):
            yield ChatChunk(delta=word + " ")
        yield ChatChunk(done=True, usage=result.usage)

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        # Local import avoids a cycle and keeps the offline embedder in one place.
        from app.rag.embeddings import HashingEmbedder

        return await HashingEmbedder().embed(list(texts))
