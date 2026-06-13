"""General-assist tier: answer general questions before handing off (real LLM only)."""

from __future__ import annotations

import pytest
from app.core.orchestrator import AnswerEvent, Orchestrator
from app.handoff.log_provider import LoggingHandoffProvider
from app.llm.base import ChatResult, Usage


class _Provider:
    """Stub LLM that returns a fixed assist reply (and a name != 'fake')."""

    def __init__(self, reply: str, name: str = "groq") -> None:
        self.name = name
        self._reply = reply

    async def chat(self, messages, *, model=None, temperature=0.2, max_tokens=None) -> ChatResult:
        return ChatResult(text=self._reply, model="stub", usage=Usage())

    def stream(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    async def embed(self, texts, *, model=None):  # pragma: no cover
        return [[0.0] for _ in texts]


class _EmptyRetriever:
    async def retrieve(self, query: str):  # low confidence: nothing relevant
        return []


def _orch(reply: str, *, allow: bool, name: str = "groq") -> Orchestrator:
    return Orchestrator(
        _Provider(reply, name=name),
        _EmptyRetriever(),  # type: ignore[arg-type]
        LoggingHandoffProvider(),
        allow_general_fallback=allow,
    )


async def _collect(orch: Orchestrator, q: str) -> list[AnswerEvent]:
    return [ev async for ev in orch.answer("c1", q)]


@pytest.mark.asyncio
async def test_general_question_answered_instead_of_handoff() -> None:
    orch = _orch("Linen wrinkles easily; iron it damp on medium heat.", allow=True)
    evs = await _collect(orch, "how do I get wrinkles out of linen?")
    assert any(e.type == "token" for e in evs)
    assert not any(e.type == "handoff" for e in evs)


@pytest.mark.asyncio
async def test_assist_emits_handoff_sentinel_routes_to_human() -> None:
    # The model decides it needs store-specific data it lacks -> HANDOFF.
    orch = _orch("HANDOFF", allow=True)
    evs = await _collect(orch, "what's the price of your blue jacket?")
    assert any(e.type == "handoff" for e in evs)


@pytest.mark.asyncio
async def test_fallback_disabled_always_hands_off() -> None:
    orch = _orch("Some general answer.", allow=False)
    evs = await _collect(orch, "how do I get wrinkles out of linen?")
    assert any(e.type == "handoff" for e in evs)


@pytest.mark.asyncio
async def test_fake_provider_never_assists() -> None:
    # Even if enabled, the offline Fake provider must hand off (deterministic demo).
    orch = _orch("Some general answer.", allow=True, name="fake")
    evs = await _collect(orch, "how do I get wrinkles out of linen?")
    assert any(e.type == "handoff" for e in evs)


@pytest.mark.asyncio
async def test_ambiguous_message_gets_clarifying_question() -> None:
    # Vague input -> the model asks a clarifying question (streamed, not a handoff).
    orch = _orch("Sure! What kind of item or occasion did you have in mind?", allow=True)
    evs = await _collect(orch, "i need something")
    text = "".join(e.text for e in evs if e.type == "token")
    assert "?" in text
    assert not any(e.type == "handoff" for e in evs)
