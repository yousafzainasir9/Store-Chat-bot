"""Fallback LLM provider chain with rate-limit cooldown.

Wraps an **ordered list** of providers (by priority) into one `LLMProvider`. On
each call it tries providers in priority order, skipping any that are currently
in cooldown. When a provider returns a rate-limit / quota error (e.g. a free-tier
daily limit), it is **disabled for a cooldown window** (default 24h, the assumed
refresh period) and the call fails over to the next provider. When every provider
is exhausted the chain raises :class:`AllProvidersUnavailable`.

This lets you stack, say, three Groq free-tier keys/models plus an OpenAI
fallback: traffic flows to the highest-priority available provider, and a
provider that hit its daily cap is parked until it refreshes.

State is in-memory per process. For a shared cooldown across replicas, back the
registry with Redis behind the same interface.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from app.llm.base import ChatChunk, ChatResult, LLMProvider, Message
from app.observability.logging import get_logger
from app.observability.metrics import metrics

_log = get_logger("llm.fallback")


class ProviderRateLimitError(Exception):
    """Raised by an adapter (or detected from the SDK) to signal a rate limit."""


class AllProvidersUnavailable(Exception):
    """Raised when every provider in the chain is in cooldown or failing."""


def is_rate_limit_error(exc: BaseException) -> bool:
    """Best-effort detection of a rate-limit / quota error across SDKs."""
    if isinstance(exc, ProviderRateLimitError):
        return True
    if "ratelimit" in type(exc).__name__.lower():
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 429:
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "rate limit",
            "rate_limit",
            "too many requests",
            "insufficient_quota",
            "quota",
            "429",
        )
    )


@dataclass(slots=True)
class ProviderEntry:
    """One provider in the chain, with its identity and priority."""

    id: str
    label: str
    provider: LLMProvider
    priority: int = 100


class CooldownRegistry:
    """Tracks which provider ids are disabled and until when (wall-clock)."""

    def __init__(self, clock: object | None = None) -> None:
        self._clock = clock or time.time
        self._disabled_until: dict[str, float] = {}

    def _now(self) -> float:
        return float(self._clock())  # type: ignore[operator]

    def available(self, provider_id: str) -> bool:
        until = self._disabled_until.get(provider_id)
        if until is None:
            return True
        if self._now() >= until:
            del self._disabled_until[provider_id]
            return True
        return False

    def disable(self, provider_id: str, seconds: float) -> float:
        until = self._now() + seconds
        self._disabled_until[provider_id] = until
        return until

    def disabled_until(self, provider_id: str) -> float | None:
        return self._disabled_until.get(provider_id)


# Generic (non-rate-limit) errors get a short cooldown so we don't hammer a
# flaky provider but recover quickly.
_GENERIC_COOLDOWN_SECONDS = 60.0


class FallbackLLMProvider(LLMProvider):
    """Priority-ordered provider chain with per-provider rate-limit cooldown."""

    def __init__(
        self,
        entries: Sequence[ProviderEntry],
        *,
        cooldown_seconds: float = 86_400.0,
        registry: CooldownRegistry | None = None,
    ) -> None:
        if not entries:
            raise ValueError("FallbackLLMProvider requires at least one provider")
        self.name = "fallback"
        self._entries = sorted(entries, key=lambda e: e.priority)
        self._cooldown_seconds = cooldown_seconds
        self._registry = registry or CooldownRegistry()

    # ------------------------------------------------------------------ helpers

    def _candidates(self) -> list[ProviderEntry]:
        return [e for e in self._entries if self._registry.available(e.id)]

    def _handle_failure(self, entry: ProviderEntry, exc: BaseException) -> None:
        rate_limited = is_rate_limit_error(exc)
        seconds = self._cooldown_seconds if rate_limited else _GENERIC_COOLDOWN_SECONDS
        until = self._registry.disable(entry.id, seconds)
        metrics.incr("llm_provider_cooldown_total." + ("rate_limit" if rate_limited else "error"))
        _log.warning(
            "llm_provider_disabled",
            provider=entry.label,
            provider_id=entry.id,
            reason="rate_limit" if rate_limited else "error",
            cooldown_seconds=seconds,
            disabled_until=until,
            error=str(exc)[:200],
        )

    # --------------------------------------------------------------------- chat

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        last_exc: BaseException | None = None
        for entry in self._candidates():
            try:
                result = await entry.provider.chat(
                    messages, model=model, temperature=temperature, max_tokens=max_tokens
                )
            except Exception as exc:
                self._handle_failure(entry, exc)
                last_exc = exc
                continue
            metrics.incr(f"llm_provider_used_total.{entry.id}")
            return result
        raise AllProvidersUnavailable("all LLM providers are in cooldown or failing") from last_exc

    # ------------------------------------------------------------------- stream

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        last_exc: BaseException | None = None
        for entry in self._candidates():
            agen = entry.provider.stream(
                messages, model=model, temperature=temperature, max_tokens=max_tokens
            )
            try:
                first = await agen.__anext__()
            except StopAsyncIteration:
                # Empty but successful stream.
                metrics.incr(f"llm_provider_used_total.{entry.id}")
                return
            except Exception as exc:
                self._handle_failure(entry, exc)
                last_exc = exc
                continue
            # First chunk succeeded → this provider is serving the response.
            metrics.incr(f"llm_provider_used_total.{entry.id}")
            yield first
            async for chunk in agen:
                yield chunk
            return
        raise AllProvidersUnavailable("all LLM providers are in cooldown or failing") from last_exc

    # -------------------------------------------------------------------- embed

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        last_exc: BaseException | None = None
        for entry in self._candidates():
            try:
                return await entry.provider.embed(texts, model=model)
            except NotImplementedError:
                # Provider can't embed (e.g. Groq) — skip without cooldown.
                continue
            except Exception as exc:
                self._handle_failure(entry, exc)
                last_exc = exc
                continue
        raise AllProvidersUnavailable(
            "no embedding-capable LLM provider is available"
        ) from last_exc

    # ------------------------------------------------------------------- status

    def status(self) -> list[dict[str, object]]:
        """Per-provider availability (for the admin/ops view; no secrets)."""
        out: list[dict[str, object]] = []
        for e in self._entries:
            until = self._registry.disabled_until(e.id)
            out.append(
                {
                    "id": e.id,
                    "label": e.label,
                    "provider": e.provider.name,
                    "priority": e.priority,
                    "available": self._registry.available(e.id),
                    "disabled_until": until,
                }
            )
        return out
