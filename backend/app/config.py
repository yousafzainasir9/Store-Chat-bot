"""Application configuration.

All configuration comes from environment variables (or a local ``.env`` file in
development). Nothing is hardcoded. Settings are validated at startup via
Pydantic so a misconfigured deployment fails fast and loudly instead of
misbehaving at request time.

See ``.env.example`` at the repo root for the full, documented variable list.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class SyncProfile(StrEnum):
    """Catalog freshness preset (see DEVELOPMENT_PLAN.md §7)."""

    REALTIME = "realtime"
    BALANCED = "balanced"
    ECO = "eco"


class LLMProviderConfig(BaseModel):
    """One entry in the LLM fallback chain (see CONFIGURATION.md).

    Provided as a JSON list via ``LLM_CHAIN``. Lower ``priority`` is tried first.
    The API key is taken from ``api_key`` if set, else from the env var named by
    ``api_key_env``, else the provider's default env key.
    """

    # Any supported provider name (see app/llm/factory.py): openai, gemini,
    # groq, grok/xai, anthropic/claude, mistral, deepseek, together,
    # openrouter, fireworks, ollama, vllm, openai_compatible/custom/local.
    provider: str
    model: str | None = None
    name: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    priority: int = 100


class Settings(BaseSettings):
    """Typed, validated application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Core ----
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    app_name: str = "store-chat-bot"
    app_version: str = "0.1.0"

    # Demo mode lets Phases 2-4 be built/tested without touching a real store.
    # It keeps ALL infrastructure offline: synthetic catalog, in-memory vector
    # store + repository, hashing embedder, fake Shopify, and the Fake LLM.
    demo_mode: bool = True
    # Use a real LLM provider for chat *while keeping the rest of demo mode
    # offline*. Lets you test real model replies (and the LLM intent classifier)
    # against the synthetic catalog with no Shopify/Qdrant/Postgres. Ignored
    # unless demo_mode is true; has no effect in a full (non-demo) deployment.
    demo_use_real_llm: bool = False

    # ---- HTTP server ----
    host: str = "0.0.0.0"  # noqa: S104 — bind-all is intended inside a container
    port: int = Field(default=8000, ge=1, le=65535)
    # Comma-separated list of allowed CORS origins (the storefront origin in prod).
    cors_origins: str = "*"

    # ---- Logging / observability ----
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = True
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None

    # ---- Datastores (wired in later phases; optional in Phase 0) ----
    database_url: str | None = None
    redis_url: str | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None

    # ---- LLM providers (Phase 1) ----
    llm_default_provider: str = "openai"
    llm_default_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    grok_api_key: str | None = None  # xAI Grok (OpenAI-compatible)
    anthropic_api_key: str | None = None  # Anthropic Claude
    # Generic OpenAI-compatible endpoint + key. LLM_BASE_URL overrides the
    # provider's default URL (required for openai_compatible/custom/vllm).
    # LLM_API_KEY is the fallback key for providers without a dedicated field
    # (mistral, deepseek, together, openrouter, fireworks, ...).
    llm_base_url: str | None = None
    llm_api_key: str | None = None

    # ---- LLM fallback chain (priority-ordered failover with cooldown) ----
    # JSON list of provider entries, e.g.:
    #   LLM_CHAIN='[{"provider":"groq","model":"llama-3.1-8b-instant",
    #               "api_key_env":"GROQ_API_KEY_1","priority":1}]'
    llm_chain: list[LLMProviderConfig] = Field(default_factory=list)
    # Cooldown when a provider hits its rate limit (default 24h = assumed refresh).
    llm_cooldown_seconds: int = Field(default=86_400, ge=0)
    # Optional extra API keys referenced by api_key_env in the chain.
    groq_api_key: str | None = None
    # Which backend produces text embeddings for retrieval:
    #   auto     - provider embeddings if the chat provider supports them, else
    #              the offline hashing embedder. (Groq has no embeddings API, so
    #              a Groq-only setup transparently uses hashing.)
    #   provider - always use the chat provider's embeddings (OpenAI/Gemini).
    #   hashing  - always use the deterministic offline hashing embedder.
    embedding_backend: Literal["auto", "provider", "hashing"] = "auto"

    # ---- Shopify (Phase 2+) ----
    shopify_store_domain: str | None = None
    shopify_admin_api_token: str | None = None
    shopify_storefront_api_token: str | None = None
    shopify_api_version: str = "2025-01"
    shopify_webhook_secret: str | None = None

    # ---- Catalog freshness (Phase 2; see plan §7) ----
    sync_profile: SyncProfile = SyncProfile.BALANCED
    # Per-data-type source overrides ("live" volatile values never come from the
    # index). Defaults follow the active profile unless explicitly set here.
    stock_source: Literal["live", "webhook"] = "live"
    price_resolution: Literal["live", "indexed"] = "live"
    catalog_sync_mode: Literal["webhook", "poll"] = "webhook"
    reconcile_delta_interval: str = "1h"
    reconcile_full_interval: str = "24h"
    webhook_retry_max: int = Field(default=5, ge=0)
    stock_low_threshold: int = Field(default=3, ge=0)
    failsafe_on_api_error: bool = True
    # Catalog import / embedding throughput (tunes cost + rate-limit headroom).
    catalog_embed_batch_size: int = Field(default=128, ge=1, le=2048)
    catalog_import_concurrency: int = Field(default=4, ge=1, le=32)

    # ---- RAG / knowledge base (Phase 1) ----
    store_name: str = "our store"
    seed_dir: str = "seed"
    embedding_dimension: int = 512  # offline hashing embedder; providers set their own
    rag_candidate_k: int = Field(default=20, ge=1)
    rag_final_k: int = Field(default=5, ge=1)
    # Calibrated for the offline overlap-coefficient reranker; recalibrate when
    # swapping in a cross-encoder (its score scale differs).
    rag_min_confidence: float = Field(default=0.28, ge=0.0, le=1.0)

    # ---- Live tools / orders (Phase 3) ----
    # Return/exchange *initiation* writes to Shopify; keep off until the return
    # scopes are granted on the custom app.
    returns_enabled: bool = False
    exchanges_enabled: bool = False
    # Identity verification is mandatory before any order/PII or return action.
    require_identity_verification: bool = True
    # When retrieval is weak, let a real LLM answer GENERAL questions from its own
    # knowledge (styling, care, sizing) instead of always handing off. It still
    # refuses to invent store-specific facts (price/stock/policy/orders).
    assist_fallback_enabled: bool = True

    # ---- Human handoff (Phase 3) ----
    # Pluggable channel: "logging" (default) or "webhook" (Gorgias/Zendesk/email-relay).
    handoff_provider: Literal["logging", "webhook"] = "logging"
    handoff_webhook_url: str | None = None
    handoff_webhook_token: str | None = None

    # ---- Visual / multimodal search (Phase 5) ----
    visual_search_enabled: bool = True
    image_embedding_dimension: int = 512
    clip_model_name: str = "clip-ViT-B-32"

    # ---- Embeddable widget / abuse protection (Phase 6) ----
    widget_secret: str | None = None  # signs short-lived widget session tokens
    widget_token_ttl_seconds: int = Field(default=3600, ge=60)
    widget_require_token: bool = False  # enforce session token on /chat + /search/visual
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=60, ge=1)
    security_headers_enabled: bool = True

    # ---- Admin dashboard (Phase 7) ----
    admin_api_key: str | None = None  # bearer token for /admin/*; required in production

    # ---- Cost / abuse guards (Phase 8; defaults are safe upper bounds) ----
    per_session_token_budget: int = Field(default=200_000, ge=0)
    cost_anomaly_session_threshold: int = Field(default=50_000, ge=0)

    # ---- Data retention & compliance (Phase 8) ----
    data_retention_days: int = Field(default=365, ge=1)

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str, info: ValidationInfo) -> str:
        v = v.strip()
        # A wildcard origin combined with credentialed requests lets any website
        # call the API with the visitor's cookies. Refuse it in production; the
        # storefront origin(s) must be set explicitly there.
        if v == "*" and info.data.get("environment") == Environment.PRODUCTION:
            raise ValueError(
                "CORS_ORIGINS must list explicit storefront origins in production, not '*'"
            )
        return v

    @field_validator("debug")
    @classmethod
    def _no_debug_in_prod(cls, v: bool, info: ValidationInfo) -> bool:
        if v and info.data.get("environment") == Environment.PRODUCTION:
            raise ValueError("debug must be False in production")
        return v

    @field_validator("admin_api_key")
    @classmethod
    def _admin_key_in_prod(cls, v: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("environment") == Environment.PRODUCTION and not v:
            raise ValueError("ADMIN_API_KEY is required in production")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the comma-separated CORS origins into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached, validated settings singleton.

    Cached so the environment is parsed once per process. Tests can clear the
    cache via ``get_settings.cache_clear()`` after patching the environment.
    """
    return Settings()
