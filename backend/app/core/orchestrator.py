"""RAG + tool-calling answer orchestrator.

The loop (DEVELOPMENT_PLAN.md §2.2):

    guard -> route intent
        -> recommend path (recommend / complete-the-look): constraints + live stock
        -> tool path      (order/tracking/stock/return): verify identity -> live tool
        -> RAG path       (everything else): retrieve -> rerank -> confidence
        -> (answer | ask-to-verify | handoff)

RAG answers are grounded-only. Live tool facts (order status, tracking numbers,
stock counts) and recommendations are delivered from verified Shopify data, not
invented. Low confidence, out-of-scope, or detected injection routes to a human
handoff. The orchestrator depends only on interfaces, so swapping any backend is
configuration, not a code change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from app.core.confidence import assess
from app.core.guardrails import screen_input
from app.core.intent_classifier import IntentClassifier
from app.core.prompts import registry
from app.core.router import RouteDecision, ToolIntent, route
from app.core.verification import Identity, extract_identity
from app.handoff.base import HandoffProvider, HandoffReason, HandoffTicket
from app.llm.base import LLMProvider, Message, Role
from app.observability.logging import get_logger
from app.observability.metrics import metrics
from app.rag.models import ScoredChunk
from app.rag.retriever import Retriever
from app.recommendations.constraints import extract_constraints_from_history
from app.recommendations.service import Recommendation, RecommendationService
from app.shopify.orders import OrderService, ToolResult, ToolStatus

_log = get_logger("orchestrator")

# Appended to every assistant reply that is delivered to a customer.
AI_DISCLOSURE = "You're chatting with an AI assistant."

_ORDER_INTENTS = frozenset(
    {
        ToolIntent.ORDER_STATUS,
        ToolIntent.TRACKING,
        ToolIntent.FULFILLMENT,
        ToolIntent.STOCK,
        ToolIntent.RETURN,
        ToolIntent.EXCHANGE,
    }
)
_RECOMMEND_INTENTS = frozenset({ToolIntent.RECOMMEND, ToolIntent.COMPLETE_LOOK})

_VERIFY_PROMPT = (
    "I can help with that. To protect your account, please share your order "
    "number and the email address used on the order."
)


@dataclass(slots=True)
class AnswerEvent:
    """A streamed orchestration event surfaced to the transport (SSE)."""

    type: str  # "token" | "citations" | "handoff" | "done"
    text: str = ""
    citations: list[str] = field(default_factory=list)
    handoff_reason: str | None = None
    confidence: float = 0.0
    tokens: int = 0


def _build_context_block(chunks: Sequence[ScoredChunk]) -> str:
    """Render retrieved chunks as a fenced, citable context block."""
    return "\n".join(
        f"[{i}] ({sc.citation}) {sc.chunk.text}" for i, sc in enumerate(chunks, start=1)
    )


def _merge_identity(history: Sequence[Message], current: str) -> Identity:
    """Combine identity signals across the conversation (multi-turn verification)."""
    order_number: str | None = None
    email: str | None = None
    texts = [m.content for m in history if m.role is Role.USER]
    texts.append(current)
    for text in texts:
        ident = extract_identity(text)
        order_number = ident.order_number or order_number
        email = ident.email or email
    return Identity(order_number=order_number, email=email)


def _user_texts(history: Sequence[Message], current: str) -> list[str]:
    return [m.content for m in history if m.role is Role.USER] + [current]


class Orchestrator:
    """Coordinates routing, tools, recommendations, retrieval, and handoff."""

    def __init__(
        self,
        provider: LLMProvider,
        retriever: Retriever,
        handoff: HandoffProvider,
        *,
        order_service: OrderService | None = None,
        recommender: RecommendationService | None = None,
        intent_classifier: IntentClassifier | None = None,
        store_name: str = "our store",
        min_confidence: float = 0.15,
        require_verification: bool = True,
        model: str | None = None,
    ) -> None:
        self._provider = provider
        self._retriever = retriever
        self._handoff = handoff
        self._orders = order_service
        self._recommender = recommender
        self._intent_classifier = intent_classifier
        self._store_name = store_name
        self._min_confidence = min_confidence
        self._require_verification = require_verification
        self._model = model

    def _system_message(self) -> Message:
        text = registry.get("system").render(store_name=self._store_name)
        return Message(role=Role.SYSTEM, content=text)

    def _route_with_history(self, history: Sequence[Message], query: str) -> RouteDecision:
        """Route the current turn, continuing a prior order intent if needed."""
        decision = route(query)
        if decision.intent is not ToolIntent.NONE:
            return decision
        current_identity = extract_identity(query)
        if not (current_identity.order_number or current_identity.email):
            return decision
        for msg in reversed([m for m in history if m.role is Role.USER]):
            prior = route(msg.content)
            if prior.needs_order:
                return RouteDecision(intent=prior.intent, identity=current_identity)
        return decision

    async def answer(
        self,
        conversation_id: str,
        query: str,
        *,
        history: Sequence[Message] = (),
    ) -> AsyncIterator[AnswerEvent]:
        """Stream the answer (recommend, RAG, live tool, verify, or handoff)."""
        guard = screen_input(query)

        # Injection short-circuits everything (never run a tool on injected text).
        if guard.injection_detected:
            async for ev in self._handoff_flow(
                conversation_id, guard.sanitized, history, HandoffReason.INJECTION
            ):
                yield ev
            return

        decision = self._route_with_history(history, guard.sanitized)
        intent = decision.intent

        # Soft path: the deterministic rules cover high-stakes intents (orders,
        # returns, stock) and explicit recommend/complete-look verbs. For
        # everything they leave as NONE, an intent classifier decides whether
        # this is a product search ("anything around $30", "a navy dress for a
        # wedding") or a general/FAQ question — far more robust than regex.
        if (
            intent is ToolIntent.NONE
            and self._recommender is not None
            and self._intent_classifier is not None
        ):
            prior = [m.content for m in history if m.role is Role.USER]
            soft = await self._intent_classifier.classify(guard.sanitized, prior)
            if soft in _RECOMMEND_INTENTS:
                decision = RouteDecision(intent=soft, identity=decision.identity)
                intent = soft

        if self._recommender is not None and intent in _RECOMMEND_INTENTS:
            async for ev in self._recommend_flow(
                conversation_id, guard.sanitized, history, decision
            ):
                yield ev
            return

        if self._orders is not None and intent in _ORDER_INTENTS:
            async for ev in self._tool_flow(conversation_id, guard.sanitized, history, decision):
                yield ev
            return

        async for ev in self._rag_flow(conversation_id, guard.sanitized, history):
            yield ev

    # ----------------------------------------------------------- recommend

    async def _recommend_flow(
        self,
        conversation_id: str,
        query: str,
        history: Sequence[Message],
        decision: RouteDecision,
    ) -> AsyncIterator[AnswerEvent]:
        assert self._recommender is not None
        constraints = extract_constraints_from_history(_user_texts(history, query))

        if decision.intent is ToolIntent.COMPLETE_LOOK:
            seed = constraints.category
            if not seed:
                msg = "I'd love to help you complete the look — which item should I build around?"
                async for ev in self._emit_text(msg):
                    yield ev
                return
            recs = await self._recommender.complete_the_look(seed, constraints)
            intro = f"To complete the look with your {seed.lower()}, you might like:"
        else:
            recs = await self._recommender.recommend(query, constraints)
            intro = "Here are a few options I think you'll like:"

        metrics.incr(f"recommend_flow_total.{decision.intent.value}")
        if not recs:
            msg = (
                "I couldn't find an in-stock match within those preferences. "
                "Want me to widen the budget or try a different colour or size?"
            )
            async for ev in self._emit_text(msg):
                yield ev
            return

        text = intro + " " + " ".join(_format_rec(r) for r in recs)
        async for ev in self._emit_text(text, citations=[r.citation for r in recs]):
            yield ev

    # ------------------------------------------------------------------ tools

    async def _tool_flow(
        self,
        conversation_id: str,
        query: str,
        history: Sequence[Message],
        decision: RouteDecision,
    ) -> AsyncIterator[AnswerEvent]:
        assert self._orders is not None
        intent = decision.intent

        # Live stock needs no identity (no PII).
        if intent is ToolIntent.STOCK:
            result = await self._orders.check_stock(query)
            async for ev in self._emit_tool_result(result):
                yield ev
            return

        # Order-scoped intents require verified identity.
        identity = _merge_identity(history, query)
        if self._require_verification and not identity.is_complete:
            metrics.incr("verify_requested_total")
            async for ev in self._emit_text(_VERIFY_PROMPT):
                yield ev
            return

        order_no = identity.order_number or ""
        email = identity.email or ""
        if intent is ToolIntent.TRACKING:
            result = await self._orders.get_tracking(order_no, email)
        elif intent is ToolIntent.FULFILLMENT:
            result = await self._orders.get_fulfillment(order_no, email)
        elif intent is ToolIntent.RETURN:
            result = await self._orders.initiate_return(order_no, email, reason=query)
        elif intent is ToolIntent.EXCHANGE:
            result = await self._orders.initiate_exchange(order_no, email)
        else:  # ORDER_STATUS
            result = await self._orders.get_order_status(order_no, email)

        metrics.incr(f"tool_call_total.{intent.value}")
        if result.status is ToolStatus.DISABLED:
            async for ev in self._handoff_flow(
                conversation_id, query, history, HandoffReason.OUT_OF_SCOPE, message=result.summary
            ):
                yield ev
            return
        async for ev in self._emit_tool_result(result):
            yield ev

    async def _emit_tool_result(self, result: ToolResult) -> AsyncIterator[AnswerEvent]:
        """Stream a live-tool fact verbatim (no model paraphrase) + citation."""
        citations = [result.citation] if result.ok and result.citation else []
        async for ev in self._emit_text(result.summary, citations=citations, ok=result.ok):
            yield ev

    # -------------------------------------------------------------------- RAG

    async def _rag_flow(
        self, conversation_id: str, query: str, history: Sequence[Message]
    ) -> AsyncIterator[AnswerEvent]:
        with metrics.timer("retrieve_seconds"):
            chunks = await self._retriever.retrieve(query)
        decision = assess(chunks, min_score=self._min_confidence)

        if not decision.confident:
            async for ev in self._handoff_flow(
                conversation_id,
                query,
                history,
                HandoffReason.LOW_CONFIDENCE,
                confidence=decision.score,
            ):
                yield ev
            return

        context_block = _build_context_block(chunks)
        user_content = (
            f"Customer question: {query}\n\n"
            f"<context>\n{context_block}\n</context>\n\n"
            "Answer using only the context above. Cite sources by their label."
        )
        messages = [self._system_message(), *history, Message(role=Role.USER, content=user_content)]

        usage_total = 0
        async for chunk in self._provider.stream(messages, model=self._model):
            if chunk.delta:
                yield AnswerEvent(type="token", text=chunk.delta)
            if chunk.done and chunk.usage is not None:
                usage_total = chunk.usage.total_tokens

        citations = _dedupe([sc.citation for sc in chunks])
        metrics.incr("answers_total")
        metrics.observe("answer_tokens", usage_total)
        yield AnswerEvent(type="citations", citations=citations, confidence=decision.score)
        yield AnswerEvent(type="done", confidence=decision.score, tokens=usage_total)

    # --------------------------------------------------------------- helpers

    async def _emit_text(
        self, text: str, *, citations: list[str] | None = None, ok: bool = True
    ) -> AsyncIterator[AnswerEvent]:
        """Stream a prepared answer as token deltas, then citations + done."""
        for word in text.split(" "):
            yield AnswerEvent(type="token", text=word + " ")
        if citations:
            yield AnswerEvent(type="citations", citations=citations, confidence=1.0)
        yield AnswerEvent(type="done", confidence=1.0 if ok else 0.0)

    async def _handoff_flow(
        self,
        conversation_id: str,
        query: str,
        history: Sequence[Message],
        reason: HandoffReason,
        *,
        confidence: float = 0.0,
        message: str | None = None,
    ) -> AsyncIterator[AnswerEvent]:
        transcript = [*history, Message(role=Role.USER, content=query)]
        result = await self._handoff.create(
            HandoffTicket(
                conversation_id=conversation_id,
                reason=reason,
                transcript=transcript,
                context={"query": query, "reason": reason.value},
            )
        )
        metrics.incr(f"handoff_total.{reason.value}")
        _log.info(
            "handoff",
            conversation_id=conversation_id,
            reason=reason.value,
            ticket_id=result.ticket_id,
            confidence=round(confidence, 4),
        )
        yield AnswerEvent(
            type="handoff",
            text=message
            or (
                "I'm not fully sure about that, so I'm connecting you with a "
                "member of our team who can help."
            ),
            handoff_reason=reason.value,
            confidence=confidence,
        )
        yield AnswerEvent(type="done", confidence=confidence)


def _format_rec(rec: Recommendation) -> str:
    """One-line product blurb for a recommendation."""
    price = f"${rec.price:.0f}" if rec.price else ""
    bits = [b for b in (rec.title, price) if b]
    return f"{' — '.join(bits)} ({rec.reason})."


def _dedupe(items: Sequence[str]) -> list[str]:
    """Stable de-duplication preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out
