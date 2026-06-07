"""Cost-aware token-bucket throttle for the Shopify Admin GraphQL API.

Shopify's GraphQL endpoint uses a leaky-bucket *query cost* model (a capacity
that refills at a fixed rate). We mirror it client-side so we pace requests
*before* hitting ``THROTTLED``, and back off when the server reports being
throttled anyway. One client, one throttle — all Shopify access goes through it
(DEVELOPMENT_PLAN.md §2.4).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    capacity: float
    available: float
    restore_rate: float  # cost points restored per second
    last: float


class CostThrottle:
    """Async cost-based leaky bucket with restore-aware waiting."""

    def __init__(
        self, *, capacity: float = 1000.0, restore_rate: float = 50.0, clock: object | None = None
    ) -> None:
        self._clock = clock or time.monotonic
        self._lock = asyncio.Lock()
        self._bucket = _Bucket(
            capacity=capacity,
            available=capacity,
            restore_rate=restore_rate,
            last=float(self._clock()),  # type: ignore[operator]
        )

    def _refill(self) -> None:
        now = float(self._clock())  # type: ignore[operator]
        elapsed = max(0.0, now - self._bucket.last)
        self._bucket.available = min(
            self._bucket.capacity,
            self._bucket.available + elapsed * self._bucket.restore_rate,
        )
        self._bucket.last = now

    async def acquire(self, cost: float) -> None:
        """Block until at least ``cost`` points are available, then debit them."""
        cost = min(cost, self._bucket.capacity)
        while True:
            async with self._lock:
                self._refill()
                if self._bucket.available >= cost:
                    self._bucket.available -= cost
                    return
                deficit = cost - self._bucket.available
                wait = deficit / self._bucket.restore_rate
            await asyncio.sleep(min(wait, 5.0))

    def update_from_response(self, *, available: float, restore_rate: float | None = None) -> None:
        """Sync local state to the server's reported throttle status."""
        self._bucket.available = available
        if restore_rate is not None:
            self._bucket.restore_rate = restore_rate
        self._bucket.last = float(self._clock())  # type: ignore[operator]
