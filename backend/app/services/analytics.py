"""Admin analytics (DEVELOPMENT_PLAN.md §8.3, Phase 7).

Computes operational metrics from persisted conversations + the in-process metric
registry: volume, deflection vs. handoff rate, average confidence, feedback
split, latency, and an estimated token cost per conversation. Costs use a
configurable price so the dashboard reflects the active model.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.conversation import MessageRole
from app.observability.metrics import metrics
from app.repositories.base import ConversationRepository

# Default blended price (USD per 1M tokens) ~ gpt-4o-mini; tune per deployment.
_DEFAULT_PRICE_PER_M = 0.30


@dataclass
class Analytics:
    """A snapshot of operational metrics for the dashboard."""

    conversations: int
    customer_messages: int
    assistant_messages: int
    handoffs: int
    handoff_rate: float
    deflection_rate: float
    avg_confidence: float
    feedback_up: int
    feedback_down: int
    est_total_tokens: int
    est_cost_usd: float
    est_cost_per_conversation_usd: float
    p50_latency_ms: float
    p95_latency_ms: float


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[idx] * 1000.0  # seconds -> ms


class AnalyticsService:
    """Aggregates conversation + metric data into a dashboard snapshot."""

    def __init__(
        self, repo: ConversationRepository, *, price_per_million: float = _DEFAULT_PRICE_PER_M
    ) -> None:
        self._repo = repo
        self._price_per_million = price_per_million

    async def summary(self, *, limit: int = 1000) -> Analytics:
        conversations = await self._repo.list_conversations(limit=limit)
        feedback = await self._repo.list_feedback()

        customer = assistant = handoffs = tokens = 0
        confidences: list[float] = []
        for conv in conversations:
            for msg in conv.messages:
                if msg.role is MessageRole.USER:
                    customer += 1
                else:
                    assistant += 1
                    tokens += msg.token_count
                    if msg.handoff_reason:
                        handoffs += 1
                    else:
                        confidences.append(msg.confidence)

        up = sum(1 for f in feedback if f.value == "up")
        down = sum(1 for f in feedback if f.value == "down")
        answered = assistant - handoffs
        cost = tokens / 1_000_000 * self._price_per_million

        # Latency from the in-process histogram (best-effort; OTel in production).
        snap = metrics.snapshot()
        hist = snap.get("histograms", {})
        http = hist.get("http_request_seconds", {}) if isinstance(hist, dict) else {}
        # Histogram stores count+sum only here; expose mean as both p50/p95 proxy.
        mean_s = (http.get("sum", 0.0) / http["count"]) if http.get("count") else 0.0

        return Analytics(
            conversations=len(conversations),
            customer_messages=customer,
            assistant_messages=assistant,
            handoffs=handoffs,
            handoff_rate=round(handoffs / assistant, 4) if assistant else 0.0,
            deflection_rate=round(answered / assistant, 4) if assistant else 0.0,
            avg_confidence=round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            feedback_up=up,
            feedback_down=down,
            est_total_tokens=tokens,
            est_cost_usd=round(cost, 4),
            est_cost_per_conversation_usd=(
                round(cost / len(conversations), 4) if conversations else 0.0
            ),
            p50_latency_ms=round(mean_s * 1000.0, 2),
            p95_latency_ms=round(_percentile([mean_s], 95), 2),
        )
