"""In-memory per-client rate limiting for abuse protection (Phase 6).

A token-bucket limiter keyed by client IP, applied to the public chat and visual
endpoints so a single abuser (or an injection loop) can't run up cost or load.
In-memory is fine for a single instance; multi-instance deployments swap in a
Redis-backed bucket behind the same interface. Enforcement and limits are
config-driven (``RATE_LIMIT_*``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass
class _Bucket:
    tokens: float
    last: float


class RateLimiter:
    """Token-bucket limiter: ``per_minute`` requests, smoothed per second."""

    def __init__(self, per_minute: int, *, clock: object | None = None) -> None:
        self._capacity = float(per_minute)
        self._refill_per_s = per_minute / 60.0
        self._buckets: dict[str, _Bucket] = {}
        self._clock = clock or time.monotonic

    def allow(self, key: str) -> bool:
        now = float(self._clock())  # type: ignore[operator]
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = _Bucket(tokens=self._capacity - 1, last=now)
            return True
        elapsed = max(0.0, now - bucket.last)
        bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill_per_s)
        bucket.last = now
        if bucket.tokens < 1.0:
            return False
        bucket.tokens -= 1.0
        return True


def client_key(request: Request) -> str:
    """Best-effort client identity for limiting (proxy-aware)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 when the caller exceeds its budget."""
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    if not limiter.allow(client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests — please slow down.",
        )
