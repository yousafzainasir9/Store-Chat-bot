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


# OpenAI-compatible providers and their default API base URLs. ``None`` means
# the SDK default (OpenAI) or "must be supplied via LLM_BASE_URL".
_OPENAI_COMPAT_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "groq": "https://api.groq.com/openai/v1",
    "grok": "https://api.x.ai/v1",
    "xai": "https://api.x.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "together": "https://api.together.xyz/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "ollama": "http://localhost:11434/v1",
    "vllm": None,
    "openai_compatible": None,
    "custom": None,
    "local": None,
}
_GEMINI_PROVIDERS = {"gemini", "google"}
_ANTHROPIC_PROVIDERS = {"anthropic", "claude"}
# Providers that need an explicit base URL (no public default).
_REQUIRE_BASE_URL = {"openai_compatible", "custom", "vllm"}
# Providers/endpoints that run locally and usually need no API key.
_KEYLESS_PROVIDERS = {"ollama", "vllm", "local"}
# Dedicated settings field holding each provider's key.
_PROVIDER_KEY_FIELDS = {
    "openai": "openai_api_key",
    "groq": "groq_api_key",
    "grok": "grok_api_key",
    "xai": "grok_api_key",
    "gemini": "gemini_api_key",
    "google": "gemini_api_key",
    "anthropic": "anthropic_api_key",
    "claude": "anthropic_api_key",
}


def _is_known_provider(provider: str) -> bool:
    return (
        provider in _OPENAI_COMPAT_BASE_URLS
        or provider in _GEMINI_PROVIDERS
        or provider in _ANTHROPIC_PROVIDERS
    )


def _clean(value: str | None) -> str | None:
    """Treat blank/whitespace-only env values as unset (common .env mistake)."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _resolve_base_url(provider: str, override: str | None) -> str | None:
    return _clean(override) or _OPENAI_COMPAT_BASE_URLS.get(provider)


def _keyless_ok(provider: str, base_url: str | None) -> bool:
    """Local model servers (Ollama/vLLM) accept any key; the SDK still needs a string."""
    if provider in _KEYLESS_PROVIDERS:
        return True
    return base_url is not None and ("localhost" in base_url or "127.0.0.1" in base_url)


def _make_provider(
    *, provider: str, key: str, model: str | None, name: str, base_url: str | None
) -> LLMProvider:
    """Construct the adapter for a (resolved) provider/model/key/base_url."""
    if provider in _GEMINI_PROVIDERS:
        from app.llm.gemini_provider import GeminiProvider

        return GeminiProvider(key, default_model=model or "gemini-2.5-flash")
    if provider in _ANTHROPIC_PROVIDERS:
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(key, default_model=model or "claude-3-5-sonnet-latest", name=name)
    if provider == "groq":
        from app.llm.groq_provider import GroqProvider

        return GroqProvider(key, default_model=model, base_url=base_url, name=name)
    # Everything else is OpenAI-compatible (openai, grok/xai, mistral, deepseek,
    # together, openrouter, fireworks, ollama, vllm, custom, ...).
    from app.llm.openai_provider import OpenAIProvider

    return OpenAIProvider(key, default_model=model or "gpt-4o-mini", base_url=base_url, name=name)


def _require_base_ok(provider: str, base_url: str | None) -> None:
    if provider in _REQUIRE_BASE_URL and not base_url:
        raise ProviderConfigError(
            f"Provider {provider!r} requires an endpoint; set LLM_BASE_URL "
            f"(or base_url in the chain entry)."
        )


def _resolve_chain_key(settings: Settings, cfg: LLMProviderConfig, base_url: str | None) -> str:
    provider = cfg.provider.lower()
    key = _clean(cfg.api_key) or _clean(
        os.environ.get(cfg.api_key_env) if cfg.api_key_env else None
    )
    if not key:
        field = _PROVIDER_KEY_FIELDS.get(provider)
        key = _clean(getattr(settings, field) if field else None) or _clean(settings.llm_api_key)
    if key:
        return key
    if _keyless_ok(provider, base_url):
        return "not-needed"
    raise ProviderConfigError(
        f"No API key for chain provider {cfg.name or provider!r} "
        f"(set api_key, api_key_env, the provider key, or LLM_API_KEY)"
    )


def _build_one(settings: Settings, cfg: LLMProviderConfig) -> LLMProvider:
    provider = cfg.provider.lower()
    if not _is_known_provider(provider) and not (cfg.base_url or settings.llm_base_url):
        raise ProviderConfigError(
            f"Unknown chain provider {provider!r}; set base_url for a custom "
            f"OpenAI-compatible endpoint."
        )
    base_url = _resolve_base_url(provider, cfg.base_url or settings.llm_base_url)
    _require_base_ok(provider, base_url)
    key = _resolve_chain_key(settings, cfg, base_url)
    return _make_provider(
        provider=provider,
        key=key,
        model=cfg.model,
        name=cfg.name or provider,
        base_url=base_url,
    )


def _single_key(settings: Settings, provider: str, base_url: str | None) -> str:
    field = _PROVIDER_KEY_FIELDS.get(provider)
    key = _clean(getattr(settings, field) if field else None) or _clean(settings.llm_api_key)
    if key:
        return key
    if _keyless_ok(provider, base_url):
        return "not-needed"
    hint = (field or "llm_api_key").upper()
    raise ProviderConfigError(f"No API key for provider {provider!r}: set {hint} or LLM_API_KEY")


def _build_single(settings: Settings) -> LLMProvider:
    provider = settings.llm_default_provider.lower()
    if not _is_known_provider(provider) and not settings.llm_base_url:
        raise ProviderConfigError(
            f"Unknown LLM provider {provider!r}; use a known provider name or set "
            f"LLM_BASE_URL for a custom OpenAI-compatible endpoint."
        )
    base_url = _resolve_base_url(provider, settings.llm_base_url)
    _require_base_ok(provider, base_url)
    key = _single_key(settings, provider, base_url)
    return _make_provider(
        provider=provider,
        key=key,
        model=settings.llm_default_model,
        name=provider,
        base_url=base_url,
    )


def real_llm_enabled(settings: Settings) -> bool:
    """Whether a real provider (not the Fake) should be built.

    True for any non-demo environment, and for demo mode when
    ``DEMO_USE_REAL_LLM`` is set (real chat over the offline catalog). Always
    False under the test environment so suites never reach a paid API.
    """
    if settings.environment is Environment.TEST:
        return False
    return (not settings.demo_mode) or settings.demo_use_real_llm


def build_provider(settings: Settings) -> LLMProvider:
    """Return the LLM provider implied by ``settings``."""
    if not real_llm_enabled(settings):
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
    return bool(settings.llm_chain) and real_llm_enabled(settings)
