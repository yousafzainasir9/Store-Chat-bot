# Code structure

This document describes the repository layout, the architectural layering, the
composition root, and a **file-by-file reference** for the backend. Frontend
files are detailed in [FRONTEND.md](./FRONTEND.md).

## 1. Repository layout

```
store-chat-bot/
├── backend/                     # FastAPI backend (Python 3.12)
│   ├── app/                     # Application package (79 modules)
│   │   ├── main.py              # App factory + middleware/router wiring
│   │   ├── config.py            # Pydantic Settings (env-only, validated)
│   │   ├── api/                 # HTTP routes + deps (thin handlers)
│   │   ├── core/                # Orchestrator, guardrails, router, verification, prompts
│   │   ├── llm/                 # LLMProvider interface + adapters
│   │   ├── rag/                 # Chunk/embed/store/retrieve/rerank + visual search
│   │   ├── shopify/             # Client, bulk import, mapping, sync, orders, webhooks
│   │   ├── recommendations/     # Constraints + recommendation service
│   │   ├── handoff/             # Human-handoff interface + adapters
│   │   ├── repositories/        # Persistence interfaces + in-memory/SQL impls
│   │   ├── models/              # Framework-free domain dataclasses
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── services/            # Composition root + admin services + jobs + seed
│   │   ├── compliance/          # GDPR export/erasure/retention
│   │   ├── billing/             # Per-session token budget + anomaly alerts
│   │   └── observability/       # Logging, metrics, SLOs
│   ├── eval/                    # Evaluation harness + dataset (106 pairs)
│   ├── scripts/                 # Load-test script
│   ├── seed/                    # Seed KB content (FAQs, policies, size guide)
│   ├── tests/                   # 28 test files
│   ├── workers/                 # Arq tasks (re-index/reconcile) — reserved
│   ├── migrations/              # Alembic migrations — reserved
│   ├── Dockerfile
│   └── pyproject.toml           # Deps + ruff/black/mypy/pytest config
├── widget/                      # Embeddable Preact chat widget (Vite)
├── admin/                       # React admin dashboard (Vite)
├── shopify-app/                 # Theme app extension (app-embed block)
├── docs/                        # This documentation set
├── docker-compose.yml           # api + postgres + redis + qdrant (local)
├── .env.example                 # Documented env template
├── .github/workflows/ci.yml     # lint → format → type → test → eval → secret scan
├── .pre-commit-config.yaml
├── README.md
└── DEVELOPMENT_PLAN.md          # Master engineering plan
```

## 2. Architectural layering

The backend follows a strict dependency direction:

```
api  →  services / core  →  (llm | rag | shopify | recommendations | handoff)  →  repositories / models
```

- **`api/`** route handlers are *thin*: validate input (Pydantic), enforce auth
  dependencies, call a service/orchestrator, serialize the result. No business
  logic, no SQL.
- **`core/orchestrator.py`** depends only on *interfaces* (provider, retriever,
  handoff, order service, recommender) — never concrete SDKs.
- **`services/container.py`** is the **composition root**: the single place that
  binds interfaces to concrete implementations based on `Settings`.
- **`repositories/`** and **`models/`** are persistence; domain models are plain
  dataclasses so the domain stays framework-free.

### The composition root

`build_container(settings)` constructs the entire object graph and returns a
frozen `Container` dataclass. `create_app()` stores it on `app.state.container`
in the lifespan hook and `bootstrap()` indexes the seed KB (and, in demo mode, a
synthetic catalog + images). Swapping any backend is a one-line change here.

## 3. Backend file reference

> Line counts are approximate and indicate relative size.

### `app/` root

| File | Lines | Purpose |
|---|---:|---|
| `main.py` | 86 | FastAPI **app factory**. Configures logging, builds the container in the lifespan, registers middleware (request-context, security headers, CORS) and all routers. Exposes module-level `app` for `uvicorn app.main:app`. |
| `config.py` | 192 | **Pydantic `Settings`** — every config value, typed and validated, loaded from env/`.env`. Includes `Environment`/`SyncProfile` enums, production guards (no `DEBUG` in prod, `ADMIN_API_KEY` required), and `get_settings()` (cached). |

### `app/api/` — HTTP layer

| File | Lines | Purpose |
|---|---:|---|
| `chat.py` | 163 | `POST /chat` (SSE streaming, rate-limit + widget-token deps, budget enforcement, persistence) and `POST /feedback`. Serializes orchestrator `AnswerEvent`s into SSE frames. |
| `visual.py` | 80 | `POST /search/visual` — multipart image upload + optional constraints → visual product matches (JSON). |
| `webhooks.py` | 60 | `POST /webhooks/shopify` — HMAC-verify, route topic, dispatch re-index to the job queue (fast 2xx). |
| `admin.py` | 223 | All `/admin/*` routes (content CRUD, conversations, feedback, gaps, analytics, privacy/export/erase/purge, freshness). Admin-auth dependency on the whole router. |
| `widget.py` | 72 | `POST /widget/session` (issue signed token) + `verify_token`/`enforce_widget_token` helpers. |
| `health.py` | 78 | `GET /health`, `/ready`, `/metrics`, `/ops/freshness`. |
| `admin_auth.py` | 35 | `require_admin` dependency — constant-time bearer-token check; prod requires the key. |
| `ratelimit.py` | 65 | In-memory per-IP token-bucket limiter + `enforce_rate_limit` dependency (429 on exceed). |
| `security.py` | 33 | `SecurityHeadersMiddleware` (nosniff, frame-deny, referrer policy, CORP). |
| `middleware.py` | 51 | `RequestContextMiddleware` — request-id binding, latency timing, one structured access log. |
| `deps.py` | 17 | `get_app_settings(request)` — pulls settings from app state (testable). |

### `app/core/` — orchestration & safety

| File | Lines | Purpose |
|---|---:|---|
| `orchestrator.py` | 380 | The central **decision loop**. `answer()` streams `AnswerEvent`s; private flows: `_recommend_flow`, `_tool_flow`, `_rag_flow`, `_handoff_flow`, `_emit_text`. History-aware routing for multi-turn verification. |
| `router.py` | 128 | **Deterministic intent router**. Regex-based classification into order/tracking/fulfillment/stock/return/exchange/recommend/complete-look/NONE, with actionable-vs-informational guards and identity extraction. |
| `verification.py` | 55 | Customer **identity** extraction (order #, email) + constant-time email match. |
| `guardrails.py` | 61 | `redact_pii` (email/phone/card) and `screen_input` (prompt-injection detection). |
| `confidence.py` | 32 | `assess(chunks, min_score)` → confident/score/reason decision used to gate RAG answers. |
| `prompts/__init__.py` | 110 | **Versioned, eval-gated prompt registry** (`PromptTemplate`, `PromptRegistry`) seeded with the grounded-only system prompt. |

### `app/llm/` — provider abstraction

| File | Lines | Purpose |
|---|---:|---|
| `base.py` | 95 | `LLMProvider` Protocol + message/result/chunk/usage dataclasses (`Role`, `Message`, `ChatResult`, `ChatChunk`, `Usage`). |
| `openai_provider.py` | 99 | OpenAI adapter (chat/stream/embed; lazy SDK import; usage capture). |
| `gemini_provider.py` | 116 | Google Gemini adapter (sync SDK bridged to async via threads). |
| `fake_provider.py` | 87 | Deterministic offline provider — grounds answers from injected context; offline embeddings via the hashing embedder. |
| `factory.py` | 39 | `build_provider(settings)` — Fake in demo/test, else the configured provider. |

### `app/rag/` — retrieval pipeline

| File | Lines | Purpose |
|---|---:|---|
| `models.py` | 39 | `Document`, `Chunk`, `ScoredChunk` core types. |
| `chunking.py` | 71 | Paragraph-aware, overlap-budgeted chunker with stable chunk ids. |
| `embeddings.py` | 80 | `Embedder` Protocol; `HashingEmbedder` (offline, token-overlap) + `ProviderEmbedder`. |
| `vector_store.py` | 196 | `VectorStore` Protocol; `InMemoryVectorStore` (exact cosine + payload filters) + `QdrantVectorStore` (filtered search, lazy client). |
| `reranker.py` | 139 | `Reranker` Protocol; `OverlapReranker` (offline overlap-coefficient) + `CrossEncoderReranker` (lazy sentence-transformers). |
| `retriever.py` | 48 | Two-stage retrieval: embed query → vector search top-N → rerank top-k. |
| `indexer.py` | 59 | Chunk → embed → upsert; per-document replace; `delete_document`. |
| `image_embeddings.py` | 90 | `ImageEmbedder` Protocol; `FakeImageEmbedder` (descriptor-based) + `CLIPImageEmbedder`. |
| `visual_search.py` | 136 | `VisualIndexer` (back-index product images) + `VisualSearchService` (image query → constraint filter → live stock → ranked matches). |

### `app/shopify/` — Shopify integration

| File | Lines | Purpose |
|---|---:|---|
| `client.py` | 129 | `ShopifyClient` Protocol + `AdminGraphQLClient` (cost-aware throttle, backoff on 429/THROTTLED, lazy httpx). |
| `throttle.py` | 67 | `CostThrottle` — async cost-based leaky bucket mirroring Shopify's GraphQL query-cost model. |
| `bulk.py` | 147 | **Bulk Operations** import: start export, poll, download JSONL, and `group_jsonl_by_parent` (reassemble products + variants). |
| `mapping.py` | 152 | Pure mapper: Shopify product node → one `Document` with variant/size/color/price-band/gender/image metadata. |
| `catalog_sync.py` | 112 | `CatalogSyncService` — full bulk import (batched), single-product reindex/delete. |
| `orders.py` | 234 | `OrderService` — live `get_order_status`/`get_tracking`/`get_fulfillment`/`check_stock`/`initiate_return`/`initiate_exchange`, all identity-gated; flag-gated writes. |
| `webhooks.py` | 63 | `verify_webhook` (HMAC) + `route_topic` → `WebhookEvent`. |
| `freshness.py` | 79 | `resolve_posture(settings)` — SyncProfile preset → concrete freshness posture (what's live vs. indexed). |
| `fake.py` | 163 | `FakeShopifyClient` + synthetic catalog/orders generators for offline runs. |

### `app/recommendations/`

| File | Lines | Purpose |
|---|---:|---|
| `constraints.py` | 117 | Extract budget/size/color/gender/category/occasion from a turn; accumulate across history. |
| `service.py` | 192 | `RecommendationService` — candidates → constraint filter → live in-stock verify → ranked `Recommendation`s; `complete_the_look` via complementary-category map. Public `passes_constraints`/`to_recommendation` reused by visual search. |

### `app/handoff/`

| File | Lines | Purpose |
|---|---:|---|
| `base.py` | 53 | `HandoffProvider` Protocol + `HandoffReason`, `HandoffTicket`, `HandoffResult`. |
| `log_provider.py` | 34 | Logging adapter (PII-redacted) — the safe default. |
| `webhook_provider.py` | 65 | Webhook adapter — POSTs the ticket to Gorgias/Zendesk/email-relay. |

### `app/repositories/` & `app/models/`

| File | Lines | Purpose |
|---|---:|---|
| `repositories/base.py` | 33 | `ConversationRepository` Protocol (get/create/add message/feedback, list, delete, purge). |
| `repositories/memory.py` | 50 | In-memory conversation repository (demo/CI). |
| `repositories/sql.py` | 205 | Async SQLAlchemy conversation repository + ORM tables (Postgres). |
| `repositories/content.py` | 38 | `ContentRepository` Protocol + in-memory impl (editable FAQs/policies). |
| `models/conversation.py` | 58 | `Conversation`, `StoredMessage`, `Feedback`, `MessageRole` domain dataclasses. |
| `models/content.py` | 24 | `ContentItem` domain dataclass. |
| `schemas/chat.py` | 38 | Pydantic `ChatRequest`, `ChatTurn`, `FeedbackRequest`, `FeedbackValue`. |

### `app/services/`

| File | Lines | Purpose |
|---|---:|---|
| `container.py` | 294 | **Composition root** — builds the whole object graph + `bootstrap()`. |
| `content_service.py` | 102 | Content CRUD that (de)indexes editable FAQs/policies into the text store on write. |
| `analytics.py` | 105 | `AnalyticsService` — volume, deflection, handoff rate, confidence, token cost, latency. |
| `gaps.py` | 131 | `ContentGapService` — cluster handoff/low-confidence questions into ranked content gaps. |
| `jobs.py` | 36 | `JobQueue` Protocol + `InlineJobQueue` (demo) for webhook-driven re-index. |
| `seed.py` | 68 | Load seed KB markdown (front-matter + section split) into `Document`s. |

### `app/compliance/`, `app/billing/`, `app/observability/`

| File | Lines | Purpose |
|---|---:|---|
| `compliance/service.py` | 60 | `ComplianceService` — conversation export, erasure, retention purge (GDPR/CCPA). |
| `billing/budget.py` | 49 | `SessionBudget` — per-conversation token accounting, hard cap, anomaly alert. |
| `observability/logging.py` | 93 | structlog config, request-id context var, `redact` helper. |
| `observability/metrics.py` | 73 | In-process counters/histograms/timer + declared `SLOS`. |

### Non-`app` backend

| Path | Purpose |
|---|---|
| `eval/run_eval.py` | Offline eval harness — recall@k/MRR (vector vs. rerank), answer/refusal accuracy, with CLI gate thresholds. |
| `eval/dataset.jsonl` | 106 labeled Q/A pairs across all intents. |
| `scripts/loadtest.py` | Async load test reporting latency percentiles vs. the p95 SLO. |
| `seed/*.md` | Seed knowledge base: `faqs.md`, `shipping_returns.md`, `size_guide.md`. |
| `Dockerfile` | Multi-stage, non-root runtime image. |
| `pyproject.toml` | Dependencies, optional extras (`dev`/`providers`/`vector`/`ml`), and tool config (ruff/black/mypy/pytest). |

## 4. Coding standards

Enforced by pre-commit + CI (not aspirational):

- **Python**: full type hints, `mypy --strict`; Pydantic at I/O boundaries;
  ruff (lint + import sort) + black (format); async for all I/O; thin route
  handlers; dependency inversion at boundaries.
- **No magic values**: all config via env, validated at startup.
- **Errors are handled values**: typed exceptions; timeouts + backoff + a defined
  failure mode on every external call (e.g. `FAILSAFE_ON_API_ERROR`).
- **Prompts as code**: versioned and eval-gated before deploy.
- **Tests**: unit + integration; the eval gate is itself a unit test
  (`tests/test_eval_gate.py`).

See [TESTING.md](./TESTING.md) for the test/eval/CI details.
