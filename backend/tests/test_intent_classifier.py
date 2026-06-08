"""Soft-intent classifier: deterministic fallback + LLM path."""

from __future__ import annotations

import pytest
from app.core.intent_classifier import (
    HeuristicIntentClassifier,
    LLMIntentClassifier,
    heuristic_soft_intent,
)
from app.core.router import ToolIntent
from app.llm.base import ChatResult, Usage

# ----------------------------------------------------------------- heuristic


@pytest.mark.parametrize(
    "message,expected",
    [
        # Price ranges in any phrasing -> shopping.
        ("give product between 20 and 50 usd", ToolIntent.RECOMMEND),
        ("anything around $30", ToolIntent.RECOMMEND),
        ("show me dresses between 20 and 50 dollars", ToolIntent.RECOMMEND),
        ("a jacket under $50", ToolIntent.RECOMMEND),
        # Occasion / colour+category refinements -> shopping.
        ("a dress for a wedding", ToolIntent.RECOMMEND),
        ("a navy dress", ToolIntent.RECOMMEND),
        # Occasion/size words alone (no garment) are NOT shopping.
        ("how do refunds work", ToolIntent.NONE),
        ("what is the delivery date", ToolIntent.NONE),
        # Complete-the-look stays its own intent.
        ("what goes with these jeans", ToolIntent.COMPLETE_LOOK),
        # Bare catalogue / FAQ questions stay grounded (NONE).
        ("do you have any dresses", ToolIntent.NONE),
        ("how long does shipping take", ToolIntent.NONE),
        ("what is your return policy", ToolIntent.NONE),
        ("tell me about your brand", ToolIntent.NONE),
    ],
)
def test_heuristic_soft_intent(message: str, expected: ToolIntent) -> None:
    assert heuristic_soft_intent(message, []) is expected


@pytest.mark.asyncio
async def test_heuristic_classifier_wraps_function() -> None:
    clf = HeuristicIntentClassifier()
    assert await clf.classify("a dress under $40", []) is ToolIntent.RECOMMEND
    assert await clf.classify("where is your size guide", []) is ToolIntent.NONE


# ------------------------------------------------------------------- LLM path


class _StubProvider:
    """Minimal LLMProvider stub returning a canned label."""

    name = "stub"

    def __init__(self, reply: str, *, raise_exc: bool = False) -> None:
        self._reply = reply
        self._raise = raise_exc
        self.calls = 0

    async def chat(self, messages, *, model=None, temperature=0.2, max_tokens=None) -> ChatResult:
        self.calls += 1
        if self._raise:
            raise RuntimeError("boom")
        return ChatResult(text=self._reply, model="stub", usage=Usage())

    def stream(self, messages, *, model=None, temperature=0.2, max_tokens=None):  # pragma: no cover
        raise NotImplementedError

    async def embed(self, texts, *, model=None):  # pragma: no cover
        return [[0.0] for _ in texts]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply,expected",
    [
        ("SHOP", ToolIntent.RECOMMEND),
        ("LOOK", ToolIntent.COMPLETE_LOOK),
        ("OTHER", ToolIntent.NONE),
        ("shop\n", ToolIntent.RECOMMEND),  # tolerant of case/whitespace
    ],
)
async def test_llm_classifier_parses_labels(reply: str, expected: ToolIntent) -> None:
    clf = LLMIntentClassifier(_StubProvider(reply))
    assert await clf.classify("whatever the user said", []) is expected


@pytest.mark.asyncio
async def test_llm_classifier_falls_back_on_unparseable() -> None:
    # An offline/Fake provider returns prose, not a label -> deterministic fallback.
    clf = LLMIntentClassifier(_StubProvider("Based on our information: ..."))
    assert await clf.classify("a dress under $40", []) is ToolIntent.RECOMMEND
    assert await clf.classify("how do refunds work", []) is ToolIntent.NONE


@pytest.mark.asyncio
async def test_llm_classifier_falls_back_on_error() -> None:
    clf = LLMIntentClassifier(_StubProvider("", raise_exc=True))
    # Errors never break a turn; fall back to the heuristic.
    assert await clf.classify("a jacket around $30", []) is ToolIntent.RECOMMEND


@pytest.mark.asyncio
async def test_llm_classifier_uses_recent_history() -> None:
    provider = _StubProvider("SHOP")
    clf = LLMIntentClassifier(provider)
    assert await clf.classify("between 20 and 50", ["I need a gift"]) is ToolIntent.RECOMMEND
    assert provider.calls == 1
