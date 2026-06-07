"""Provider factory: resolve the configured :class:`LLMProvider` from settings.

Selection order:
1. ``demo_mode`` (or environment == test) -> always the offline Fake provider,
   so nothing reaches a paid API by accident in dev/CI.
2. otherwise the provider named by ``LLM_DEFAULT_PROVIDER``.
"""

from __future__ import annotations

from app.config import Environment, Settings
from app.llm.base import LLMProvider
from app.llm.fake_provider import FakeLLMProvider


class ProviderConfigError(Exception):
    """Raised when the requested provider is missing required configuration."""


def build_provider(settings: Settings) -> LLMProvider:
    """Return the LLM provider implied by ``settings``."""
    if settings.demo_mode or settings.environment is Environment.TEST:
        return FakeLLMProvider(model=settings.llm_default_model)

    provider = settings.llm_default_provider.lower()
    if provider == "openai":
        if not settings.openai_api_key:
            raise ProviderConfigError("OPENAI_API_KEY is not set")
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(settings.openai_api_key, default_model=settings.llm_default_model)
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ProviderConfigError("GEMINI_API_KEY is not set")
        from app.llm.gemini_provider import GeminiProvider

        return GeminiProvider(settings.gemini_api_key, default_model=settings.llm_default_model)

    raise ProviderConfigError(f"Unknown LLM provider: {settings.llm_default_provider!r}")
