"""Tests for the LLM fallback chain + rate-limit cooldown."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest
from app.llm.base import ChatChunk, ChatResult, Message, Role, Usage
from app.llm.fallback import (
    AllProvidersUnavailable,
    CooldownRegistry,
    FallbackLLMProvider,
    ProviderEntry,
    ProviderRateLimitError,
    is_rate_limit_error,
)


class _StubProvider:
    """A controllable provider: succeeds, rate-limits, or errors."""

    def __init__(self, name: str, *, mode: str = "ok") -> None:
        self.name = name
        self.mode = mode  # "ok" | "ratelimit" | "error" | "noembed"
        self.calls = 0

    async def chat(self, messages, *, model=None, temperature=0.2, max_tokens=None) -> ChatResult:
        self.calls += 1
        if self.mode == "ratelimit":
            raise ProviderRateLimitError("daily limit reached")
        if self.mode == "error":
            raise RuntimeError("boom")
        return ChatResult(text=f"hello from {self.name}", model=self.name, usage=Usage(1, 1))

    async def stream(
        self, messages, *, model=None, temperature=0.2, max_tokens=None
    ) -> AsyncIterator[ChatChunk]:
        self.calls += 1
        if self.mode == "ratelimit":
            raise ProviderRateLimitError("daily limit reached")
        yield ChatChunk(delta=f"hi-{self.name} ")
        yield ChatChunk(done=True, usage=Usage(1, 1))

    async def embed(self, texts: Sequence[str], *, model=None) -> list[list[float]]:
        if self.mode == "noembed":
            raise NotImplementedError("no embeddings")
        if self.mode == "ratelimit":
            raise ProviderRateLimitError("limit")
        return [[0.0] for _ in texts]


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _chain(*entries: ProviderEntry, clock=None, cooldown=86_400.0) -> FallbackLLMProvider:
    return FallbackLLMProvider(
        entries, cooldown_seconds=cooldown, registry=CooldownRegistry(clock=clock)
    )


def _entry(provider, *, id_: str, priority: int) -> ProviderEntry:
    return ProviderEntry(id=id_, label=id_, provider=provider, priority=priority)


def test_rate_limit_detection() -> None:
    assert is_rate_limit_error(ProviderRateLimitError("x"))
    assert is_rate_limit_error(RuntimeError("Rate limit exceeded"))
    assert is_rate_limit_error(RuntimeError("HTTP 429 Too Many Requests"))
    assert not is_rate_limit_error(RuntimeError("connection refused"))


async def test_priority_order_used_first() -> None:
    a, b = _StubProvider("a"), _StubProvider("b")
    chain = _chain(_entry(b, id_="b", priority=2), _entry(a, id_="a", priority=1))
    res = await chain.chat([Message(role=Role.USER, content="hi")])
    assert res.text == "hello from a"  # priority 1 wins
    assert b.calls == 0


async def test_failover_on_rate_limit_then_cooldown() -> None:
    clock = _Clock()
    g1 = _StubProvider("g1", mode="ratelimit")
    g2 = _StubProvider("g2", mode="ok")
    chain = _chain(
        _entry(g1, id_="g1", priority=1),
        _entry(g2, id_="g2", priority=2),
        clock=clock,
        cooldown=86_400.0,
    )
    # First call: g1 rate-limits → fails over to g2.
    res = await chain.chat([Message(role=Role.USER, content="hi")])
    assert res.text == "hello from g2"
    # g1 is now disabled for 24h: a second call skips it entirely.
    res2 = await chain.chat([Message(role=Role.USER, content="hi")])
    assert res2.text == "hello from g2"
    assert g1.calls == 1  # not retried while in cooldown


async def test_cooldown_recovers_after_window() -> None:
    clock = _Clock()
    g1 = _StubProvider("g1", mode="ratelimit")
    g2 = _StubProvider("g2", mode="ok")
    chain = _chain(
        _entry(g1, id_="g1", priority=1),
        _entry(g2, id_="g2", priority=2),
        clock=clock,
        cooldown=86_400.0,
    )
    await chain.chat([Message(role=Role.USER, content="hi")])  # disables g1
    g1.mode = "ok"  # the limit "refreshed"
    clock.t += 86_400.0 + 1  # 24h + 1s later
    res = await chain.chat([Message(role=Role.USER, content="hi")])
    assert res.text == "hello from g1"  # g1 is back and highest priority


async def test_all_unavailable_raises() -> None:
    g1 = _StubProvider("g1", mode="ratelimit")
    g2 = _StubProvider("g2", mode="error")
    chain = _chain(_entry(g1, id_="g1", priority=1), _entry(g2, id_="g2", priority=2))
    with pytest.raises(AllProvidersUnavailable):
        await chain.chat([Message(role=Role.USER, content="hi")])


async def test_stream_failover() -> None:
    g1 = _StubProvider("g1", mode="ratelimit")
    g2 = _StubProvider("g2", mode="ok")
    chain = _chain(_entry(g1, id_="g1", priority=1), _entry(g2, id_="g2", priority=2))
    chunks = [c async for c in chain.stream([Message(role=Role.USER, content="hi")])]
    text = "".join(c.delta for c in chunks)
    assert "hi-g2" in text


async def test_embed_skips_non_embedding_provider() -> None:
    groq = _StubProvider("groq", mode="noembed")
    openai = _StubProvider("openai", mode="ok")
    chain = _chain(_entry(groq, id_="groq", priority=1), _entry(openai, id_="openai", priority=2))
    vectors = await chain.embed(["a", "b"])
    assert len(vectors) == 2  # served by the embedding-capable provider


async def test_status_reports_availability() -> None:
    clock = _Clock()
    g1 = _StubProvider("g1", mode="ratelimit")
    g2 = _StubProvider("g2", mode="ok")
    chain = _chain(_entry(g1, id_="g1", priority=1), _entry(g2, id_="g2", priority=2), clock=clock)
    await chain.chat([Message(role=Role.USER, content="hi")])
    status = {s["id"]: s for s in chain.status()}
    assert status["g1"]["available"] is False
    assert status["g2"]["available"] is True
