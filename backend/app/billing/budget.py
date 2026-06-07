"""Per-session token budget meter + cost-runaway protection (Phase 8).

Tracks cumulative tokens per conversation. When a session exceeds its budget the
chat layer stops invoking the model and hands off — so an abusive client or a
prompt-injection loop cannot run up unbounded cost. Crossing a softer anomaly
threshold emits a structured alert for the cost dashboard. In-memory per
instance; back with Redis for a shared budget across instances.
"""

from __future__ import annotations

from app.observability.logging import get_logger
from app.observability.metrics import metrics

_log = get_logger("billing")


class SessionBudget:
    """Accumulates per-conversation token usage and enforces a hard cap."""

    def __init__(self, *, budget: int, anomaly_threshold: int) -> None:
        self._budget = budget
        self._anomaly_threshold = anomaly_threshold
        self._usage: dict[str, int] = {}

    def record(self, conversation_id: str, tokens: int) -> None:
        """Add ``tokens`` to a conversation's running total; alert on anomaly."""
        if tokens <= 0:
            return
        total = self._usage.get(conversation_id, 0) + tokens
        self._usage[conversation_id] = total
        metrics.observe("session_tokens", tokens)
        if self._anomaly_threshold and total >= self._anomaly_threshold:
            metrics.incr("cost_anomaly_total")
            _log.warning(
                "cost_anomaly",
                conversation_id=conversation_id,
                total_tokens=total,
                threshold=self._anomaly_threshold,
            )

    def exceeded(self, conversation_id: str) -> bool:
        """True when the conversation has spent its entire token budget."""
        if self._budget <= 0:
            return False
        return self._usage.get(conversation_id, 0) >= self._budget

    def usage(self, conversation_id: str) -> int:
        return self._usage.get(conversation_id, 0)
