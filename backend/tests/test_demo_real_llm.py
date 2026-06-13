"""DEMO_USE_REAL_LLM: real chat provider over the offline demo infrastructure."""

from __future__ import annotations

from app.config import Environment, Settings
from app.core.intent_classifier import HeuristicIntentClassifier, LLMIntentClassifier
from app.llm.factory import build_provider, real_llm_enabled
from app.llm.fake_provider import FakeLLMProvider
from app.rag.embeddings import HashingEmbedder
from app.services.container import _build_embedder, build_container


def _demo_real_settings() -> Settings:
    return Settings(
        demo_mode=True,
        demo_use_real_llm=True,
        llm_default_provider="groq",
        groq_api_key="test-key",
        llm_default_model="llama-3.1-8b-instant",
    )


def test_plain_demo_uses_fake_provider() -> None:
    s = Settings(demo_mode=True)
    assert real_llm_enabled(s) is False
    assert isinstance(build_provider(s), FakeLLMProvider)


def test_demo_use_real_llm_builds_real_provider() -> None:
    s = _demo_real_settings()
    assert real_llm_enabled(s) is True
    provider = build_provider(s)
    assert not isinstance(provider, FakeLLMProvider)
    assert provider.name == "groq"


def test_demo_real_keeps_offline_embedder() -> None:
    # Even with a real chat provider, demo mode keeps the offline hashing embedder
    # (Groq has no embeddings API), so retrieval needs no embeddings key.
    s = _demo_real_settings()
    provider = build_provider(s)
    assert isinstance(_build_embedder(s, provider), HashingEmbedder)


def test_test_environment_always_fake() -> None:
    # Test env never reaches a paid API even with the flag set.
    s = Settings(environment=Environment.TEST, demo_mode=True, demo_use_real_llm=True)
    assert real_llm_enabled(s) is False
    assert isinstance(build_provider(s), FakeLLMProvider)


def test_container_picks_llm_classifier_when_real() -> None:
    real = build_container(_demo_real_settings())
    assert isinstance(real.orchestrator._intent_classifier, LLMIntentClassifier)
    demo = build_container(Settings(demo_mode=True))
    assert isinstance(demo.orchestrator._intent_classifier, HeuristicIntentClassifier)
