"""Deterministic tool-intent router.

For high-stakes, narrow intents (order status, tracking, fulfillment, live
stock, returns/exchanges) we detect intent with rules rather than letting the
LLM decide to call a tool. This is safer (immune to prompt-injection triggering a
refund), cheaper, and deterministic.

Crucially, a tool intent only fires when the request is **actionable / order-
specific** — it mentions an order number, refers to "my order", or is an
imperative action ("start a return"). Informational and policy questions
("what is your return policy", "how do refunds work") fall through to
``ToolIntent.NONE`` and are answered from the grounded knowledge base instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.core.verification import Identity, extract_identity


class ToolIntent(StrEnum):
    ORDER_STATUS = "order_status"
    TRACKING = "tracking"
    FULFILLMENT = "fulfillment"
    STOCK = "stock"
    RETURN = "return"
    EXCHANGE = "exchange"
    RECOMMEND = "recommend"
    COMPLETE_LOOK = "complete_look"
    NONE = "none"


# "This is about a specific order of mine" signals.
_PERSONAL_ORDER = re.compile(
    r"\b(my (order|package|parcel|delivery|shipment|return|refund|exchange)"
    r"|where('?s| is) my\b|track(ing)? (my|order|number|#))",
    re.I,
)
# Imperative actions on one's own order (not questions about policy).
_RETURN_ACTION = re.compile(
    r"\b(i (want|need|would like|'?d like) to return|start (a|my) return"
    r"|return (my|this) order|get a refund for|refund my)\b",
    re.I,
)
_EXCHANGE_ACTION = re.compile(
    r"\b(i (want|need|would like|'?d like) to exchange|exchange (my|this)|swap my)\b", re.I
)
# Informational/how-to phrasing — a policy question, not an action on an order.
_INFORMATIONAL = re.compile(r"\b(how (do|can|to|would|long|much)|what('?s| is| are)|why)\b", re.I)
# Topic words.
_TRACKING = re.compile(r"\b(track|tracking|where('?s| is) my|shipped|delivery status)\b", re.I)
_FULFILLMENT = re.compile(r"\b(fulfil?led|fulfillment|has it shipped|packed)\b", re.I)
_ORDER_STATUS = re.compile(r"\b(order status|status of (my )?order|how is my order)\b", re.I)
_COMPLETE_LOOK = re.compile(
    r"\b(complete (the|my) look|finish (the|my) look|what goes with|goes well with"
    r"|pair with|style (me|this)|outfit|shop the look)\b",
    re.I,
)
_RECOMMEND = re.compile(
    r"\b(recommend|suggest|what should i wear|help me (find|pick|choose)"
    r"|looking for something|any recommendations|what do you recommend)\b",
    re.I,
)
# Explicit stock phrasing only (avoids matching "do you have anything in linen").
_STOCK = re.compile(
    r"\b(in stock|out of stock|stock level|availability|available (in|now|size)"
    r"|do you have .*\bin stock)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """A routed intent plus any extracted identity signals."""

    intent: ToolIntent
    identity: Identity

    @property
    def needs_order(self) -> bool:
        """Whether this intent operates on a specific order (needs verification)."""
        return self.intent in {
            ToolIntent.ORDER_STATUS,
            ToolIntent.TRACKING,
            ToolIntent.FULFILLMENT,
            ToolIntent.RETURN,
            ToolIntent.EXCHANGE,
        }


def route(message: str) -> RouteDecision:
    """Classify a message into an actionable tool intent (or NONE)."""
    identity = extract_identity(message)
    has_order = identity.order_number is not None
    personal = has_order or bool(_PERSONAL_ORDER.search(message))

    informational = bool(_INFORMATIONAL.search(message)) and not has_order

    intent = ToolIntent.NONE
    # Return/exchange require an explicit action or an order reference — never a
    # bare policy/how-to question.
    if not informational and (
        _RETURN_ACTION.search(message)
        or (has_order and re.search(r"\b(return|refund)\b", message, re.I))
    ):
        intent = ToolIntent.RETURN
    elif not informational and (
        _EXCHANGE_ACTION.search(message)
        or (has_order and re.search(r"\bexchange\b", message, re.I))
    ):
        intent = ToolIntent.EXCHANGE
    elif personal and _TRACKING.search(message):
        intent = ToolIntent.TRACKING
    elif personal and _FULFILLMENT.search(message):
        intent = ToolIntent.FULFILLMENT
    elif personal and _ORDER_STATUS.search(message):
        intent = ToolIntent.ORDER_STATUS
    elif _COMPLETE_LOOK.search(message):
        intent = ToolIntent.COMPLETE_LOOK
    elif _RECOMMEND.search(message):
        intent = ToolIntent.RECOMMEND
    elif _STOCK.search(message):
        intent = ToolIntent.STOCK

    return RouteDecision(intent=intent, identity=identity)
