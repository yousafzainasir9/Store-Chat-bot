"""Tests that the factory builds a fallback chain from settings."""

from __future__ import annotations

from app.config import Environment, LLMProviderConfig, Settings
from app.llm.factory import build_provider, uses_chain
from app.llm.fallback import FallbackLLMProvider


def test_demo_mode_ignores_chain() -> None:
    settings = Settings(
        environment=Environment.TEST,
        demo_mode=True,
        llm_chain=[LLMProviderConfig(provider="groq", api_key="k", model="m", priority=1)],
    )
    assert uses_chain(settings) is False
    # Demo → fake provider, never the chain.
    assert build_provider(settings).name == "fake"


def test_chain_built_from_config() -> None:
    settings = Settings(
        environment=Environment.STAGING,
        demo_mode=False,
        llm_chain=[
            LLMProviderConfig(
                provider="groq", name="groq-1", api_key="k1", model="llama", priority=1
            ),
            LLMProviderConfig(
                provider="groq", name="groq-2", api_key="k2", model="llama", priority=2
            ),
            LLMProviderConfig(
                provider="openai", name="oai", api_key="k3", model="gpt-4o-mini", priority=3
            ),
        ],
    )
    assert uses_chain(settings) is True
    provider = build_provider(settings)
    assert isinstance(provider, FallbackLLMProvider)
    labels = [s["label"] for s in provider.status()]
    assert labels == ["groq-1", "groq-2", "oai"]
