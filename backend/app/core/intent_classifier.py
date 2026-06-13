"""Soft-intent classification for the shopping vs. FAQ decision.

High-stakes intents (order status, tracking, fulfillment, live stock, returns,
exchanges) are classified by deterministic rules in :mod:`app.core.router` —
never by an LLM, so a prompt injection can't trigger a refund. This module
covers only the *soft* decision the rules deliberately leave open:

    "Is the customer trying to browse/search for products (and how), or is this
     a general/policy/FAQ question?"

Natural-language phrasing here is effectively unbounded ("anything around 30
bucks", "stuff from 20 to 50", "what can I get for under 40", "a navy dress for
a wedding"), so an LLM classifier is the right tool — not an ever-growing pile
of regexes.

Design: an LLM classifier with a deterministic fallback. The fallback is used
in offline demo mode, when no real provider is configured, and whenever the
model's output is unparseable. It infers shopping intent from the *structured
constraints* the catalogue already understands (budget/range, colour, size,
occasion) rather than from surface wording — so price ranges work in any
phrasing without bespoke patterns. A bare category mention with no filter
("do you have any dresses") stays a grounded catalogue answer by design.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.router import ToolIntent
from app.llm.base import LLMProvider, Message, Role
from app.observability.logging import get_logger
from app.recommendations.constraints import extract_constraints_from_history

_log = get_logger("intent")

# Cap the classification call so a slow/rate-limited provider never stalls a
# turn; on timeout we fall back to the deterministic heuristic.
_CLASSIFY_TIMEOUT_S = 6.0

# "Complete the look" is a distinct, easily-recognised ask; keep it cheap.
_COMPLETE_LOOK = re.compile(
    r"\b(complete (the|my) look|finish (the|my) look|what goes with|goes well with"
    r"|pair with|style (me|this)|outfit|shop the look)\b",
    re.I,
)
# Explicit recommendation verbs — a clear fast-path that needs no model.
_RECOMMEND = re.compile(
    r"\b(recommend|suggest|what should i wear|help me (find|pick|choose)"
    r"|looking for something|any recommendations|what do you recommend)\b",
    re.I,
)


@runtime_checkable
class IntentClassifier(Protocol):
    """Decides the soft intent of a message that the rules left as NONE."""

    async def classify(self, message: str, history: Sequence[str]) -> ToolIntent:
        """Return RECOMMEND, COMPLETE_LOOK, or NONE for ``message``."""
        ...


def heuristic_soft_intent(message: str, history: Sequence[str]) -> ToolIntent:
    """Deterministic soft-intent inference (no model call).

    Used as the offline/demo classifier and as the fallback when the LLM output
    can't be parsed. Shopping intent is inferred from *structured filters* the
    catalogue understands, so any phrasing of a price range, colour, size, or
    occasion is caught — while a filter-less catalogue question stays grounded.
    """
    if _COMPLETE_LOOK.search(message):
        return ToolIntent.COMPLETE_LOOK
    if _RECOMMEND.search(message):
        return ToolIntent.RECOMMEND
    c = extract_constraints_from_history([*history, message])
    has_price = c.budget_min is not None or c.budget_max is not None
    # A budget/price range is an unambiguous shopping signal on its own.
    # Colour/size/occasion words are ambiguous in isolation ("how refunds *work*",
    # "delivery *date*"), so they only count as shopping when attached to an
    # actual garment category ("a navy *dress*", "a *jacket* for a wedding").
    refined_garment = c.category is not None and bool(c.color or c.size or c.occasion)
    if has_price or refined_garment:
        return ToolIntent.RECOMMEND
    return ToolIntent.NONE


class HeuristicIntentClassifier:
    """Wraps :func:`heuristic_soft_intent` as an :class:`IntentClassifier`."""

    async def classify(self, message: str, history: Sequence[str]) -> ToolIntent:
        return heuristic_soft_intent(message, history)


_CLASSIFY_SYSTEM = (
    "You label a retail customer's latest message with exactly one token:\n"
    "SHOP  - they want to browse, search, or get product recommendations "
    "(may include budget, price range, size, colour, or occasion).\n"
    "LOOK  - they want to complete or style an outfit / what pairs with an item.\n"
    "OTHER - anything else: shipping, returns, sizing-policy, order status, "
    "store info, greetings, or unclear.\n"
    "Reply with only SHOP, LOOK, or OTHER — no punctuation, no explanation."
)

_LABEL_TO_INTENT = {
    "SHOP": ToolIntent.RECOMMEND,
    "LOOK": ToolIntent.COMPLETE_LOOK,
    "OTHER": ToolIntent.NONE,
}


class LLMIntentClassifier:
    """LLM-backed soft-intent classifier with a deterministic fallback.

    One short, low-temperature completion per soft message. Any failure — an
    error, an empty reply, or an unrecognised label (e.g. the offline Fake
    provider) — falls back to :func:`heuristic_soft_intent`, so the system is
    never worse than the deterministic path.
    """

    def __init__(self, provider: LLMProvider, *, model: str | None = None) -> None:
        self._provider = provider
        self._model = model

    async def classify(self, message: str, history: Sequence[str]) -> ToolIntent:
        recent = [h for h in history if h][-4:]
        convo = "\n".join(f"- {h}" for h in recent)
        user = message if not convo else f"Recent turns:\n{convo}\n\nLatest message:\n{message}"
        messages = [
            Message(role=Role.SYSTEM, content=_CLASSIFY_SYSTEM),
            Message(role=Role.USER, content=user),
        ]
        try:
            result = await asyncio.wait_for(
                self._provider.chat(messages, model=self._model, temperature=0.0, max_tokens=4),
                timeout=_CLASSIFY_TIMEOUT_S,
            )
        except Exception as exc:
            _log.warning("intent_classify_failed", error=str(exc))
            return heuristic_soft_intent(message, history)

        intent = _parse_label(result.text)
        if intent is None:
            # Unparseable (e.g. offline Fake provider) — fall back deterministically.
            return heuristic_soft_intent(message, history)
        return intent


def _parse_label(text: str) -> ToolIntent | None:
    """Map a model reply to a soft intent, tolerating extra tokens/casing."""
    upper = text.upper()
    for label, intent in _LABEL_TO_INTENT.items():
        if re.search(rf"\b{label}\b", upper):
            return intent
    return None
