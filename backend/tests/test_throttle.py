"""Tests for the cost-aware throttle (deterministic via injected clock)."""

from __future__ import annotations

import pytest
from app.shopify.throttle import CostThrottle

pytestmark = pytest.mark.asyncio


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


async def test_acquire_debits_available() -> None:
    clock = _Clock()
    throttle = CostThrottle(capacity=100, restore_rate=10, clock=clock)
    await throttle.acquire(40)
    # Immediately acquiring within capacity does not block.
    await throttle.acquire(40)


async def test_update_from_response_syncs_state() -> None:
    clock = _Clock()
    throttle = CostThrottle(capacity=1000, restore_rate=50, clock=clock)
    throttle.update_from_response(available=5.0, restore_rate=50)
    # Advance the clock so the bucket refills enough to grant the request.
    clock.t = 10.0
    await throttle.acquire(100)
