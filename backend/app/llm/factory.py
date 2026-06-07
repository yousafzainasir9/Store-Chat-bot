"""Provider factory: resolve the configured :class:`LLMProvider` from settings.

Selection order:
1. ``demo_mode`` (or environment == test) -> the offline Fake provider, so
   nothing reaches a paid API by accident in dev/CI.
2. a non-empty ``LLM_CHAIN`` -> a :class:`FallbackLLMProvider` chaining the
   configured providers by priority (with rate-limit cooldown failover).
3. otherwise the single provider named by ``LLM_DEFAULT_PROVIDER``.
"""

from __future__ import annotations

import os

from app.config import Environment, LLMProviderConfig, Settings
from app.llm.base import LLMProvider
from app.llm.fake_provider import FakeLLMProvider
from app.llm.fallback import FallbackLLMProvider, ProviderEntry
from app.observability.logging import get_logger

_log = get_logger("llm.factory")


class ProviderConfigError(Exception):
    """Raised when a requested provider is missing required configuration."""


def _default_key(settings: Settings, provider: str) -> str | None:
    return {
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
        "groq": settings.groq_api_key,
    }.get(provider)


def _resolve_key(settings: Settings, cfg: LLMProviderConfig) -> str:
    key = cfg.api_key or (os.environ.get(cfg.api_key_env) if cfg.api_key_env else None)
    key = key or _default_key(settings, cfg.provider)
    if not key:
        raise ProviderConfigError(
            f"No API key for chain provider {cfg.name or cfg.provider!r} "
            f"(set api_key, api_key_env, or the provider default env var)"
        )
    return key


def _build_one(settings: Settings, cfg: LLMProviderConfig) -> LLMProvider:
    key = _resolve_key(settings, cfg)
    label = cfg.name or cfg.provider
    if cfg.provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            key,
            default_model=cfg.model or settings.llm_default_model,
            base_url=cfg.base_url,
            name=label,
        )
    if cfg.provider == "groq":
        from app.llm.groq_provider import GroqProvider

        return GroqProvider(key, default_model=cfg.model, base_url=cfg.base_url, name=label)
    if cfg.provider == "gemini":
        from app.llm.gemini_provider import GeminiProvider

        return GeminiProvider(key, default_model=cfg.model or "gemini-2.5-flash")
    raise ProviderConfigError(f"Unknown chain provider: {cfg.provider!r}")


def _build_single(settings: Settings) -> LLMProvider:
    provider = settings.llm_default_provider.lower()
    if provider == "openai":
        if not settings.openai_api_key:
            raise ProviderConfigError("OPENAI_API_KEY is not set")
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(settings.openai_api_key, default_model=settings.llm_default_model)
    if provider == "groq":
        if not settings.groq_api_key:
            raise ProviderConfigError("GROQ_API_KEY is not set")
        from app.llm.groq_provider import GroqProvider

        return GroqProvider(settings.groq_api_key, default_model=settings.llm_default_model)
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ProviderConfigError("GEMINI_API_KEY is not set")
        from app.llm.gemini_provider import GeminiProvider

        return GeminiProvider(settings.gemini_api_key, default_model=settings.llm_default_model)
    raise ProviderConfigError(f"Unknown LLM provider: {settings.llm_default_provider!r}")


def build_provider(settings: Settings) -> LLMProvider:
    """Return the LLM provider implied by ``settings``."""
    if settings.demo_mode or settings.environment is Environment.TEST:
        return FakeLLMProvider(model=settings.llm_default_model)

    if settings.llm_chain:
        entries = [
            ProviderEntry(
                id=f"{(cfg.name or cfg.provider)}-{i}",
                label=cfg.name or f"{cfg.provider}:{cfg.model or 'default'}",
                provider=_build_one(settings, cfg),
                priority=cfg.priority,
            )
            for i, cfg in enumerate(settings.llm_chain)
        ]
        _log.info("llm_chain_built", providers=[e.label for e in entries])
        return FallbackLLMProvider(entries, cooldown_seconds=settings.llm_cooldown_seconds)

    return _build_single(settings)


def uses_chain(settings: Settings) -> bool:
    """True when a fallback chain is configured (each provider keeps its model)."""
    return bool(settings.llm_chain) and not (
        settings.demo_mode or settings.environment is Environment.TEST
    )
