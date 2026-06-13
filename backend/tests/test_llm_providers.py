"""Multi-provider single-mode building: OpenAI-compatible, Grok, local, Anthropic.

These assert the factory wiring (which adapter, base URL, key resolution) without
importing any provider SDK or making network calls.
"""

from __future__ import annotations

import pytest
from app.config import Settings
from app.llm.factory import ProviderConfigError, _build_single


def _s(**kw: object) -> Settings:
    # demo_use_real_llm so the factory builds a real adapter, not the Fake.
    base = {"demo_mode": True, "demo_use_real_llm": True}
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


def test_grok_uses_xai_base_url_and_grok_key() -> None:
    p = _build_single(_s(llm_default_provider="grok", grok_api_key="xai-key"))
    assert p.name == "grok"
    assert p._base_url == "https://api.x.ai/v1"  # type: ignore[attr-defined]
    assert p._api_key == "xai-key"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "provider,expected_base",
    [
        ("mistral", "https://api.mistral.ai/v1"),
        ("deepseek", "https://api.deepseek.com/v1"),
        ("together", "https://api.together.xyz/v1"),
        ("openrouter", "https://openrouter.ai/api/v1"),
        ("fireworks", "https://api.fireworks.ai/inference/v1"),
    ],
)
def test_openai_compatible_presets(provider: str, expected_base: str) -> None:
    p = _build_single(_s(llm_default_provider=provider, llm_api_key="k"))
    assert p._base_url == expected_base  # type: ignore[attr-defined]
    assert p._api_key == "k"  # type: ignore[attr-defined]


def test_custom_endpoint_requires_base_url() -> None:
    with pytest.raises(ProviderConfigError):
        _build_single(_s(llm_default_provider="openai_compatible", llm_api_key="k"))
    p = _build_single(
        _s(
            llm_default_provider="openai_compatible",
            llm_base_url="https://my.host/v1",
            llm_api_key="k",
        )
    )
    assert p._base_url == "https://my.host/v1"  # type: ignore[attr-defined]


def test_local_ollama_needs_no_key() -> None:
    # Local model servers accept any key; the SDK still needs a non-empty string.
    p = _build_single(_s(llm_default_provider="ollama", llm_default_model="llama3"))
    assert p._base_url == "http://localhost:11434/v1"  # type: ignore[attr-defined]
    assert p._api_key  # a placeholder is supplied  # type: ignore[attr-defined]


def test_base_url_override_points_anywhere() -> None:
    p = _build_single(_s(llm_default_provider="openai", llm_base_url="http://localhost:8001/v1"))
    # localhost override => no key required
    assert p._base_url == "http://localhost:8001/v1"  # type: ignore[attr-defined]


def test_unknown_provider_without_base_url_raises() -> None:
    with pytest.raises(ProviderConfigError):
        _build_single(_s(llm_default_provider="banana", llm_api_key="k"))


def test_anthropic_builds_claude_adapter() -> None:
    p = _build_single(_s(llm_default_provider="anthropic", anthropic_api_key="sk-ant"))
    assert p.name == "anthropic"
    assert type(p).__name__ == "AnthropicProvider"


def test_claude_alias_and_default_model() -> None:
    p = _build_single(
        _s(llm_default_provider="claude", anthropic_api_key="sk-ant", llm_default_model="claude-x")
    )
    assert type(p).__name__ == "AnthropicProvider"
