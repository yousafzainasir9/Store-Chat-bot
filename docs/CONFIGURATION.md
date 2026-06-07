# Configuration

All configuration is **environment-driven** and validated at startup by
`app/config.py` (`Settings`, a Pydantic `BaseSettings`). Nothing is hardcoded;
secrets never live in the repo (`.env` is git-ignored). Copy `.env.example` to
`.env` for local use; in production inject values via the PaaS secret manager.

Validation guards at startup:
- `DEBUG=true` is **rejected** when `ENVIRONMENT=production`.
- `ADMIN_API_KEY` is **required** when `ENVIRONMENT=production`.
- Numeric/enum fields are range/enum validated; invalid reconcile intervals fail
  fast.

## Core

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` \| `staging` \| `production` \| `test`. |
| `DEBUG` | `false` | Must be false in production. |
| `APP_NAME` | `store-chat-bot` | |
| `APP_VERSION` | `0.1.0` | |
| `DEMO_MODE` | `true` | When true, all external deps use deterministic offline stand-ins. Set `false` in production. |

## HTTP server

| Variable | Default | Notes |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address (container). |
| `PORT` | `8000` | |
| `CORS_ORIGINS` | `*` | Comma-separated. **Lock to the storefront + admin origins in production.** |

## Logging / observability

| Variable | Default | Notes |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG`…`CRITICAL`. |
| `LOG_JSON` | `true` | JSON logs (deployed) vs. pretty console (dev). |
| `OTEL_ENABLED` | `false` | OpenTelemetry export. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | — | LLM tracing. |

## Datastores

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | Postgres async DSN (`postgresql+asyncpg://…`). Unset → in-memory store. |
| `REDIS_URL` | — | Cache / rate-limit / queue / budgets (scale-out). |
| `QDRANT_URL` | — | Vector DB. Unset → in-memory store. |
| `QDRANT_API_KEY` | — | |

## LLM providers (Phase 1)

| Variable | Default | Notes |
|---|---|---|
| `LLM_DEFAULT_PROVIDER` | `openai` | `openai` \| `gemini` \| `groq` (single-provider mode). |
| `LLM_DEFAULT_MODEL` | `gpt-4o-mini` | |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY` / `GROK_API_KEY` | — | |
| `LLM_CHAIN` | `[]` | JSON list of providers for **priority-ordered failover** (see [LLM_FALLBACK.md](./LLM_FALLBACK.md)). When set, overrides single-provider mode. |
| `LLM_COOLDOWN_SECONDS` | `86400` | How long a rate-limited provider stays disabled (24h). |
| `GROQ_API_KEY_1` / `_2` / `_3` | — | Extra keys referenced by `api_key_env` in `LLM_CHAIN`. |

## RAG / knowledge base (Phase 1)

| Variable | Default | Notes |
|---|---|---|
| `STORE_NAME` | `our store` | Rendered into the system prompt. |
| `SEED_DIR` | `seed` | Seed KB directory. |
| `EMBEDDING_DIMENSION` | `512` | Offline hashing-embedder dimension (providers set their own). |
| `RAG_CANDIDATE_K` | `20` | Vector search top-N before rerank. |
| `RAG_FINAL_K` | `5` | Reranked top-k used to answer. |
| `RAG_MIN_CONFIDENCE` | `0.28` | **Calibrated for the offline overlap reranker** — recalibrate when swapping in a cross-encoder. Below this → handoff. |

## Shopify (Phase 2+)

| Variable | Default | Notes |
|---|---|---|
| `SHOPIFY_STORE_DOMAIN` | — | `your-store.myshopify.com`. |
| `SHOPIFY_ADMIN_API_TOKEN` | — | Custom-app Admin API token. |
| `SHOPIFY_STOREFRONT_API_TOKEN` | — | Optional. |
| `SHOPIFY_API_VERSION` | `2025-01` | |
| `SHOPIFY_WEBHOOK_SECRET` | — | Verifies webhook HMAC. |

## Catalog freshness (Phase 2, plan §7)

| Variable | Default | Notes |
|---|---|---|
| `SYNC_PROFILE` | `balanced` | `realtime` \| `balanced` \| `eco`. |
| `STOCK_SOURCE` | `live` | Keep `live`; quantity is volatile. |
| `PRICE_RESOLUTION` | `live` | Final price resolved live. |
| `CATALOG_SYNC_MODE` | `webhook` | `webhook` \| `poll`. |
| `RECONCILE_DELTA_INTERVAL` | `1h` | `15m`/`30m`/`1h`/`6h`/`12h`/`24h`. |
| `RECONCILE_FULL_INTERVAL` | `24h` | Full audit cadence. |
| `WEBHOOK_RETRY_MAX` | `5` | Re-index retry attempts. |
| `STOCK_LOW_THRESHOLD` | `3` | Force a live stock check at/below this qty. |
| `FAILSAFE_ON_API_ERROR` | `true` | On Shopify outage: decline + handoff, never guess. |
| `CATALOG_EMBED_BATCH_SIZE` | `128` | Embedding batch size for import. |
| `CATALOG_IMPORT_CONCURRENCY` | `4` | Import concurrency. |

## Live tools / orders (Phase 3)

| Variable | Default | Notes |
|---|---|---|
| `RETURNS_ENABLED` | `false` | Enable return *initiation* (needs return scopes). |
| `EXCHANGES_ENABLED` | `false` | Enable exchange initiation. |
| `REQUIRE_IDENTITY_VERIFICATION` | `true` | Email must match the order before any PII/return action. |

## Human handoff (Phase 3)

| Variable | Default | Notes |
|---|---|---|
| `HANDOFF_PROVIDER` | `logging` | `logging` \| `webhook`. |
| `HANDOFF_WEBHOOK_URL` | — | Gorgias/Zendesk/email-relay endpoint. |
| `HANDOFF_WEBHOOK_TOKEN` | — | Optional bearer for the webhook. |

## Visual / multimodal search (Phase 5)

| Variable | Default | Notes |
|---|---|---|
| `VISUAL_SEARCH_ENABLED` | `true` | Enables `/search/visual` + the image collection. |
| `IMAGE_EMBEDDING_DIMENSION` | `512` | Must match the image model; never mix with text dims. |
| `CLIP_MODEL_NAME` | `clip-ViT-B-32` | Used only when `DEMO_MODE=false` (needs the `ml` extra). |

## Widget / abuse protection (Phase 6)

| Variable | Default | Notes |
|---|---|---|
| `WIDGET_SECRET` | — | Set to enable signed widget session tokens. |
| `WIDGET_TOKEN_TTL_SECONDS` | `3600` | Token lifetime. |
| `WIDGET_REQUIRE_TOKEN` | `false` | Enforce the token on `/chat` + `/search/visual`. |
| `RATE_LIMIT_ENABLED` | `true` | Per-IP token-bucket limiter. |
| `RATE_LIMIT_PER_MINUTE` | `60` | Requests/min per client. |
| `SECURITY_HEADERS_ENABLED` | `true` | Adds standard security headers. |

## Admin (Phase 7)

| Variable | Default | Notes |
|---|---|---|
| `ADMIN_API_KEY` | — | Bearer token for `/admin/*`. **Required in production.** |

## Cost guards + compliance (Phase 8)

| Variable | Default | Notes |
|---|---|---|
| `PER_SESSION_TOKEN_BUDGET` | `200000` | Hard cap; over-budget sessions hand off. |
| `COST_ANOMALY_SESSION_THRESHOLD` | `50000` | Soft threshold that emits a `cost_anomaly` alert. |
| `DATA_RETENTION_DAYS` | `365` | Conversations older than this are purged by the retention sweep. |

## Optional Python extras

```bash
pip install ".[dev]"                  # lint/type/test toolchain
pip install ".[providers]"            # openai + google-generativeai
pip install ".[vector]"               # qdrant-client
pip install ".[ml]"                   # sentence-transformers + pillow (cross-encoder + CLIP)
```
