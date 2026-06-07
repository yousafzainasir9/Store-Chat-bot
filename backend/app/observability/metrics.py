"""Lightweight in-process metrics + SLO target definitions.

This is the Phase-0 baseline: a tiny, dependency-free counter/histogram store
plus the SLO targets the system commits to. In later phases these feed an
OpenTelemetry/Langfuse exporter, but the SLO definitions live here from day one
so the team has a single source of truth to load-test against.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class SLO:
    """A single service-level objective."""

    name: str
    description: str
    target: str


# Targets from DEVELOPMENT_PLAN.md §8.3 — tune with real traffic.
SLOS: tuple[SLO, ...] = (
    SLO("chat_first_token_p95", "Time to first streamed token (chat)", "< 2.5s"),
    SLO("answer_availability", "Successful chat responses", ">= 99.5%"),
    SLO("groundedness", "Answers traceable to a source/tool result", ">= target"),
    SLO("handoff_rate", "Conversations escalated to a human", "within band"),
)


class _MetricsRegistry:
    """Thread-safe, in-memory metrics. Replaced by OTel exporter at scale."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def incr(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms[name].append(value)

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        """Context manager that records elapsed seconds into a histogram."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - start)

    def snapshot(self) -> dict[str, object]:
        """Return a copy of current metric values (for /metrics)."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "histograms": {
                    k: {"count": len(v), "sum": sum(v)} for k, v in self._histograms.items()
                },
            }


metrics = _MetricsRegistry()
