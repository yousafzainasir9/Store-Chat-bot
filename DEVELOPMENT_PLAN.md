# Development Plan — Fashion & Clothing AI Support Chatbot (Shopify)

**Status:** Draft v2 · **Date:** 2026-06-07 · **Owner:** yousafzainasir9

This is the master engineering plan: recommended architecture, the key decisions behind it, a phase-by-phase delivery roadmap, the cross-cutting designs (handoff, feedback loop, compliance, cost guards, SLOs), coding standards, security posture, testing/evaluation strategy, and a cost estimate per 1,000 conversations. Code is delivered phase by phase — this document defines *what* we build and *how*, not the full source.

**v2 changes:** added human-handoff design, retrieval reranking, visual/multimodal search, returns/exchange initiation, the feedback→content loop, data-retention/compliance/AI-disclosure, cost/abuse runaway protection, dev/staging setup, SLOs, eval-gated prompt versioning, and multilingual support — all designed up front.

---

## 1. Scope locked from kickoff answers

| Decision | Choice | Implication |
|---|---|---|
| AI provider | Multi-LLM, swappable (OpenAI, Gemini, Grok, others) | Hard provider abstraction is a first-class requirement, not an afterthought |
| Hosting | Managed PaaS | Render / Railway / Fly.io + managed Postgres; Docker-based, cloud-portable |
| Scale | Large catalog / high traffic | Dedicated vector DB (Qdrant), async workers, caching, rate-limit discipline |
| Shopify app type | Custom app | Single store, no App Store review; simpler OAuth, faster to ship |
| Visual search | **In scope** (Phase 5) | Default models are multimodal; design image ingestion + query path now |
| Returns/exchange | **Initiation in scope** (Phase 3) | Not just policy answers — actually start returns via Shopify, with verification |

---

## 2. Recommended architecture

### 2.1 One-paragraph summary

A **FastAPI** backend exposes a streaming chat endpoint and admin APIs. Customer messages run through a **RAG + tool-calling orchestrator**: grounded content (catalog text, size guides, policies, FAQs) is retrieved from **Qdrant**, then **reranked** by a cross-encoder before answering; live data (order status, tracking, fulfillment, real-time stock) is fetched on demand via **Shopify Admin/Storefront API tool calls** — never cached in the vector store. An **LLM provider abstraction** routes to OpenAI, Gemini, or Grok behind one interface, and the same multimodal models power **visual product search**. When confidence is low or the request is out of scope, the bot performs a **structured human handoff**. **Postgres** stores conversations, feedback, content, and analytics. Shopify **webhooks** trigger an async **re-indexing worker** with a **configurable freshness model**. The frontend is an **embeddable theme-app-extension chat widget** plus a **React admin dashboard** that closes the **feedback→content loop**.

### 2.2 Component diagram (text)

```
                         ┌──────────────────────────────┐
   Shopify Storefront    │  Chat Widget (Theme App Ext)  │
   (app embed block) ───▶│  text + image input, stream   │
                         └───────────────┬───────────────┘
                                         │ HTTPS (SSE stream)
                                         ▼
┌───────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend (PaaS)                        │
│  /chat (SSE)  /admin/*  /webhooks/shopify  /handoff  /health /metrics│
│      │            │            │              │                     │
│      ▼            ▼            ▼              ▼                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              RAG + Tool-Calling Orchestrator                  │  │
│  │  guard → retrieve → rerank → decide tools → provider →       │  │
│  │  ground+cite → confidence check → (answer | handoff)         │  │
│  └──┬────────┬────────┬─────────┬──────────┬──────────┬─────────┘  │
│     ▼        ▼        ▼         ▼          ▼          ▼            │
│  LLM      Retriever Reranker  Shopify    Guardrails  Handoff       │
│ Provider  +Visual   (cross-   Tools      (PII/inj/   Service       │
│ (abstr.)  Search    encoder)  (live)     moderation) (ticket)      │
│     │        │                   │                                  │
└─────┼────────┼───────────────────┼──────────────────────────────────┘
      ▼        ▼                   ▼
 OpenAI/    ┌─────────┐      Shopify Admin + Storefront API
 Gemini/    │ Qdrant  │      (orders, tracking, stock, returns)
 Grok       │ (text + │              ▲
            │  image) │              │ webhooks (products/inventory/orders/discounts)
            └─────────┘     ┌────────┴───────────┐
                            │ Async Worker        │
                            │ (re-index, sweep)   │
                            └────────────────────┘
 Postgres (conversations, feedback, content/FAQs, analytics, retention)
 Redis (cache + semantic cache, rate-limit, job queue, cost budgets)
 Handoff target (Shopify Inbox / Gorgias / Zendesk / email)
 Observability (logs, traces, cost meter, SLOs) — Langfuse + OTel
```

### 2.3 Recommended stack

| Layer | Recommendation | Why (and the trade-off) |
|---|---|---|
| Backend framework | **FastAPI** (Python 3.12) | Async-native (streaming + concurrent Shopify calls), Pydantic typing, OpenAPI free. GIL → scale horizontally with workers. |
| LLM abstraction | **Custom `LLMProvider` Protocol** + adapters; LiteLLM optional underneath | `chat()`/`stream()`/`embed()`/`vision()`. Adding a provider is config, not code. Keeps streaming, tool-calling, and cost logging in our control. |
| Default chat model | **gpt-4o-mini**, fallback **Gemini 2.5 Flash** | Cheap, fast, strong tool-calling and multimodal. Swappable per environment. |
| Text embeddings | **text-embedding-3-small** (1536-d) | Cheapest quality embedding; one model per index, never mix dimensions. |
| Image embeddings | **CLIP-class multimodal embedding** (provider or open `open-clip`) | Powers visual search; image vectors live in a parallel Qdrant collection. Trade-off: separate model + collection to maintain. |
| **Reranker** | **Cross-encoder** (e.g., `bge-reranker` / Cohere Rerank) | Re-scores top-N vector hits for precision — big quality win for near-identical fashion items. Trade-off: small added latency/cost; mitigated by reranking only top 20→5. |
| Vector DB | **Qdrant** (managed) | High-traffic filtered search; rich payload filters (gender, category, size, color, price, in-stock). Pinecone is the serverless alternative. |
| Relational DB | **Postgres** (managed) | Conversations, feedback, editable content, analytics, retention. |
| Cache / queue | **Redis** | Semantic response cache, rate-limit buckets, job queue, per-session cost budgets. |
| Async jobs | **Arq** (async, Redis-backed) | Webhook-driven re-index + reconciliation sweeps without blocking requests. |
| Handoff integration | **Pluggable adapter** (Shopify Inbox / Gorgias / Zendesk / email) | One `HandoffProvider` interface; channel chosen by config. |
| Frontend widget | **Preact + Vite**, single embeddable script (<40 KB) | Footprint matters on a storefront; text + image input; mounts in a theme-app-extension block. |
| Admin dashboard | **React + Vite + TS + Tailwind + shadcn/ui** | Fast to build; tables/charts for analytics and the feedback loop. |
| Observability | **JSON logs + OpenTelemetry + Langfuse** | Per-query: chunks, rerank scores, latency, token cost, provider, feedback. |
| Auth (admin) | **OAuth2 / JWT**, sessions in Redis | Role-based access. |
| Container | **Docker + compose** | Cloud-portable; same image on Render/Railway/Fly. |

### 2.4 Key decisions, justified

**Live data is never vectorized.** Orders, tracking, fulfillment, and real-time stock are fetched through Shopify tool calls at answer time. Descriptive stock metadata (a product *has* an XL) is indexed for retrieval/filtering; quantity on hand is always live. Avoids the most damaging hallucination — a false "in stock."

**Grounded-only answering with citations + reranking.** Vector search returns candidates; a cross-encoder reranks them so the *best* chunk wins, not merely a semantically close one. Every factual claim traces to a reranked chunk or a tool result. Low confidence or out-of-scope → human handoff, never a guess.

**Multimodal by design.** Because the default models are multimodal, we build the chat path to accept images from day one (Phase 6 widget enables the UI), and Phase 5 adds true **visual product search** via a parallel image-embedding collection: "find me something like this photo" → nearest in-catalog items, filtered by size/price/in-stock.

**Returns are actionable, not just explained.** The tool layer includes return/exchange *initiation* (Phase 3) behind identity verification — the bot can start the process via Shopify, not only quote the policy.

**Human handoff is a first-class flow, not a dead-end message** (see §8.1).

**Custom Shopify app, not public.** Single store → no App Store review, simpler token auth, faster. We still honor OAuth scopes, webhook HMAC, and rate limits, so the path to a public app stays short.

**Rate-limit discipline from day one.** All Shopify access goes through one client with token-bucket throttling, backoff on `429`/`THROTTLED`, and cost-aware GraphQL batching.

---

## 3. Phased delivery plan

Build incrementally; each phase is shippable and independently testable. We confirm scope before generating large code volumes per phase.

### Phase 0 — Foundations
- Repo structure, Docker/compose, `.env.example`, pre-commit (ruff/black/mypy/isort), CI (lint→type→test), secret scanning.
- FastAPI app, Pydantic Settings, structured logging, **observability + SLO baseline** (OTel + Langfuse wired), `/health`.
- **Dev/staging setup**: Shopify development store, seed catalog, **demo mode** so Phases 2–4 build without touching production.
- **Prompt-versioning scaffolding** (versioned templates + eval hook).
- **Deliverable:** README of design choices + this plan + green CI on a correct skeleton.

### Phase 1 — RAG MVP (FAQs, policies, size guides) ★ first real value
- LLM provider abstraction + OpenAI & Gemini adapters.
- Ingestion for policies/FAQs/size guides; chunking, embedding, Qdrant upsert.
- Retriever **+ cross-encoder reranker**; grounded-only prompt, citations, confidence scoring.
- **Basic human-handoff escalation** (transcript + context handed off) and **AI-disclosure** notice.
- `/chat` streaming endpoint; conversations + feedback persisted.
- Eval set (≥30 pairs) + retrieval/accuracy script.
- **Acceptance:** grounded, cited answers; reranking improves recall@k vs. baseline; no hallucinated policies; low-confidence routes to handoff; streaming + logging work.

### Phase 2 — Shopify catalog sync + product Q&A
- Custom app setup, scopes, secure token storage.
- Catalog ingestion (Admin GraphQL): titles, descriptions, materials, care, price, variants/sizes, colors, inventory metadata → chunked + tagged + indexed.
- Webhook receivers (products/inventory/discounts) with HMAC → Arq re-index jobs.
- **Configurable freshness model** (see §7): strategies, cadence, profiles.
- Centralized rate-limited Shopify client.
- **Acceptance:** product questions answered from catalog; edits re-index per configured cadence; filtered retrieval (size/color/category) works.

### Phase 3 — Live order tracking, tools & returns
- Tool/function layer: `get_order_status`, `get_tracking`, `get_fulfillment`, `check_stock`, **`initiate_return`/`initiate_exchange`**.
- Customer identity verification (email + order #) before any PII or return action.
- **Handoff ticket creation** via the configured channel adapter.
- **Acceptance:** live verified order/tracking data; stock always real-time; returns can be started end-to-end; unauthorized lookups blocked.

### Phase 4 — Fashion product recommendations
- Recommendation service: semantic similarity + metadata filters (size availability, price band, category, color, gender, occasion), in-stock verified live before suggesting.
- "Complete the look" / complementary items; respects budget + size from the conversation.
- **Acceptance:** recommendations are in-stock, on-budget, size-available, relevant; never suggests out-of-stock.

### Phase 5 — Visual / multimodal search
- Image-embedding model + parallel Qdrant image collection; back-index catalog images.
- Image-query path: customer photo → nearest in-catalog matches, filtered by size/price/in-stock; "shop the look" from an image.
- **Acceptance:** uploading a garment photo returns visually similar, available products with citations.

### Phase 6 — Embeddable storefront widget
- Theme-app-extension app-embed block; brand-themeable (colors, logo, position).
- Streaming UI, typing indicator, history, **image upload**, mobile-first responsive.
- **Accessibility (ARIA/keyboard) and i18n/multilingual are explicit acceptance criteria.**
- CORS/CSP hardening, widget auth token, abuse rate-limiting.
- **Acceptance:** merchant enables the block; works mobile + desktop; themable; accessible; multilingual; image input works; no console errors.

### Phase 7 — Admin dashboard + feedback loop
- Content CRUD (FAQs/policies → triggers re-index), conversation review/search, feedback review.
- **Feedback→content loop:** thumbs-down + low-confidence queries auto-surface content gaps ("23 asked X, no source") for one-click FAQ creation.
- Analytics: volume, deflection, handoff rate, latency, **token cost/conversation**, top intents, low-confidence queries; **read-only freshness posture** view.
- Role-based auth.
- **Acceptance:** edit an FAQ → reflected in answers; gaps surface from real feedback; analytics reflect live traffic.

### Phase 8 — Hardening, compliance, eval, launch
- Expand eval set (≥100 pairs across all intents); **CI gate** on retrieval relevance + answer faithfulness; **eval-gated prompt deploys**.
- Prompt-injection red-teaming; **data-retention + GDPR/CCPA deletion/export**; AI-disclosure audit.
- **Cost/abuse runaway protection** (per-session token budgets, anomaly alerts); load test to target QPS against **defined SLOs**.
- Cost dashboards + alerts, runbook, deploy docs, backups.
- **Acceptance:** eval thresholds met in CI; SLO load target sustained; security + compliance checklist signed off.

---

## 4. Repository structure

```
store-chat-bot/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory
│   │   ├── config.py               # Pydantic Settings (env only)
│   │   ├── api/
│   │   │   ├── chat.py             # /chat SSE
│   │   │   ├── handoff.py          # escalation endpoints
│   │   │   ├── admin/              # content, conversations, analytics
│   │   │   └── webhooks.py         # Shopify webhooks (HMAC)
│   │   ├── core/
│   │   │   ├── orchestrator.py     # RAG + tool-calling loop
│   │   │   ├── guardrails.py       # PII, injection, moderation
│   │   │   └── prompts/            # versioned, eval-gated templates
│   │   ├── llm/
│   │   │   ├── base.py             # LLMProvider Protocol (chat/stream/embed/vision)
│   │   │   ├── openai_provider.py / gemini_provider.py / grok_provider.py
│   │   │   └── factory.py
│   │   ├── rag/
│   │   │   ├── chunking.py / embeddings.py / retriever.py
│   │   │   ├── reranker.py         # cross-encoder
│   │   │   ├── visual_search.py    # image embeddings + image collection
│   │   │   └── indexer.py
│   │   ├── shopify/
│   │   │   ├── client.py           # rate-limited Admin/Storefront
│   │   │   ├── tools.py            # order/tracking/stock/returns tools
│   │   │   └── catalog_sync.py     # configurable freshness
│   │   ├── handoff/                # HandoffProvider adapters
│   │   ├── recommendations/
│   │   ├── compliance/             # retention, deletion/export, PII redaction
│   │   ├── billing/                # token budgets, cost meter, anomaly alerts
│   │   ├── models/ schemas/ repositories/ services/
│   │   └── observability/          # logging, tracing, SLOs
│   ├── workers/                    # Arq tasks (re-index, sweep)
│   ├── migrations/                 # Alembic
│   ├── tests/                      # unit + integration
│   ├── eval/                       # eval set + scoring + prompt-eval gate
│   ├── pyproject.toml
│   └── Dockerfile
├── widget/                         # Preact embeddable widget (text + image, i18n, a11y)
├── admin/                          # React admin (analytics + feedback loop)
├── shopify-app/                    # theme app extension + app config
├── docs/  (ARCHITECTURE.md, DEPLOY.md, RUNBOOK.md, COMPLIANCE.md)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 5. Coding standards & clean-code guidelines

Enforced via pre-commit + CI, not aspirational.

**General:** Single Responsibility per unit; dependency inversion at boundaries (orchestrator depends on the `LLMProvider`/vector/Shopify/handoff interfaces, never concrete SDKs); no magic values (all config via env); explicit over clever (small functions, early returns, shallow nesting); errors are handled values (typed exceptions, timeouts + backoff + defined failure mode on every external call).

**Python:** full type hints, `mypy --strict`; Pydantic at all I/O boundaries; ruff + black + isort; docstrings on public functions; async for all I/O; layered `api → services → repositories → models` with thin route handlers (no business logic or SQL in routes).

**Frontend:** TypeScript strict, ESLint + Prettier; small presentational components, data fetching isolated in hooks; accessibility + responsive + i18n are acceptance criteria.

**Testing:** unit (chunking, rerank, guardrails, adapters mocked, tools); integration (`/chat`, webhooks HMAC, Shopify client via fixtures/sandbox); coverage gate ≥80% on core; small live smoke suite against the dev store.

**Prompts as code:** templates are versioned; a prompt change must pass the eval gate before deploy.

**Git:** Conventional Commits, required review, green CI to merge, secret scanning.

---

## 6. Security, privacy & compliance (first-class)

- **Secrets** via env / PaaS secret manager only; `.env` git-ignored; `.env.example` documents every variable with no real values.
- **Webhook authenticity:** verify Shopify HMAC on every webhook.
- **PII handling:** identity verification (email + order #) before any order/PII or return action; PII redacted from logs and LLM traces.
- **Data retention & rights:** configurable conversation retention window; **GDPR/CCPA deletion + export** endpoints; documented in `COMPLIANCE.md`.
- **AI disclosure:** explicit "you're chatting with an AI assistant" notice in the widget.
- **Prompt-injection defense:** retrieved content + user input treated as untrusted and fenced; tool execution allow-listed with validated args; system instructions non-overridable; output checked before tools fire.
- **Grounding guard:** post-generation check that claims map to sources; otherwise safe fallback + handoff.
- **Cost/abuse runaway protection:** per-session and per-IP token budgets, request rate limits, and anomaly alerts so abuse or injection loops can't run up the bill.
- **Transport:** HTTPS only, strict CORS to storefront origin, CSP for the widget.
- **Least privilege:** Shopify scopes limited per phase (read_products, read_orders, read_inventory, read_fulfillments, and return scopes only when needed).

---

## 7. Catalog sync & freshness (configurable)

Freshness is config/env-driven, with sane defaults. Three layers: **event-driven webhooks** (primary, near-real-time), **live-at-query** (volatile values never from the index), and a **reconciliation sweep** (repairs missed/delayed webhooks).

### 7.1 Per-data-type strategy

| Data type | Default | Env | Notes |
|---|---|---|---|
| Stock quantity / availability | `live` | `STOCK_SOURCE` | Keep `live`; `webhook` adds a staleness window |
| Final price (incl. discounts) | `live` | `PRICE_RESOLUTION` | Base price indexed; promos resolved live |
| Product content / variants / colors | `webhook` | `CATALOG_SYNC_MODE` | Near-real-time; harmless if briefly behind |
| Bundles | `webhook` | `BUNDLE_SYNC_MODE` | Depends on native/app/metafield implementation |
| Discounts / sales / price rules | `webhook`+`live` | `DISCOUNT_SYNC_MODE` | Subscribed + final effect resolved live |
| New / deleted products | `webhook` | `CATALOG_SYNC_MODE` | — |

### 7.2 Cadence & behavior

| Setting (env) | Default | Purpose |
|---|---|---|
| `RECONCILE_DELTA_INTERVAL` | `1h` | Delta sweep frequency (`15m`/`1h`/`6h`) |
| `RECONCILE_FULL_INTERVAL` | `24h` | Full catalog audit |
| `WEBHOOK_RETRY_MAX` / `_BACKOFF` | `5` / exp | Re-index retry policy |
| `STOCK_CACHE_TTL` | `0s` | Optional live-stock cache (>0 only under load) |
| `STOCK_LOW_THRESHOLD` | `3` | Force live check below this |
| `FAILSAFE_ON_API_ERROR` | `true` | On Shopify outage, decline + handoff vs. guess |
| `SYNC_PROFILE` | `balanced` | Preset: `realtime` / `balanced` / `eco` |

### 7.3 Profiles

- **`realtime`** — stock & price `live`, sweep `15m`, no stock cache. Highest accuracy/cost.
- **`balanced`** (default) — stock & price `live`, sweep hourly + nightly full.
- **`eco`** — stock `live` only below threshold (else short cache), sweep `6h`. Lowest API load/cost.

Validated at startup; active posture shown read-only in the admin dashboard.

---

## 8. Cross-cutting designs

### 8.1 Human handoff
A `HandoffProvider` interface with channel chosen by config (Shopify Inbox / Gorgias / Zendesk / email). Triggers: low retrieval/answer confidence, explicit user request, out-of-scope intent, repeated failure, or sensitive cases. On trigger the bot transfers the **full transcript + customer/order context + detected intent**, respects **business hours** (queued vs. live), tells the customer what's happening, and logs the handoff for analytics (handoff rate is a tracked KPI).

### 8.2 Feedback → content loop
Thumbs-down and low-confidence queries are clustered and surfaced in the admin as ranked **content gaps**, each with example questions and a one-click "create FAQ" that feeds ingestion and re-indexes. This turns observed failures into improved coverage automatically.

### 8.3 Observability & SLOs
Per-query traces capture retrieved chunks, rerank scores, provider, latency, and token cost. Targets to hold and load-test against (tune with you): **p95 chat first-token < ~2.5s**, **answer availability ≥ 99.5%**, **groundedness ≥ target**, **handoff rate within band**. Alerts on SLO breach and on cost anomalies.

### 8.4 Multilingual
Language detected per conversation; responses in the customer's language. Content/FAQs can be authored per locale; retrieval respects locale metadata. Enabled/scoped via config.

### 8.5 Caching & invalidation
Semantic response cache (Redis) deflects repeat FAQ-style questions; cache entries are **invalidated on re-index** of the underlying source so cached answers never outlive a content/price change.

---

## 9. Evaluation strategy

- **Eval set** (`backend/eval/`): curated Q/A pairs per intent (FAQ, policy, size, product, order, return, recommendation, visual, out-of-scope) with expected sources + ideal answers.
- **Retrieval metrics:** recall@k, MRR — before vs. after reranking.
- **Answer metrics:** groundedness/faithfulness, correctness (LLM-as-judge + spot human review), citation accuracy, refusal correctness.
- **Operational (live):** deflection, handoff rate, thumbs-up rate, p50/p95 latency, token cost/conversation.
- **CI gates:** regressions below threshold fail the build; **prompt changes must pass the eval gate before deploy.**

---

## 10. Cost estimate per 1,000 conversations

**Assumptions** (tune with real data): ~3 turns/conversation; ~2,500 input + ~350 output tokens/turn ⇒ ~7,500 input + ~1,050 output tokens/conversation. Query embeddings negligible; catalog (re)embedding is a separate periodic cost; reranking adds a small per-query cost.

| Model | Input $/1M | Output $/1M | ~Cost / 1k convos |
|---|---|---|---|
| **gpt-4o-mini** | $0.15 | ~$0.60 | **~$1.75** |
| **Gemini 2.5 Flash** | $0.30 | $2.50 | **~$4.90** |
| **Grok 3 Mini** | $0.30 | $0.50 | **~$2.80** |
| gpt-4.1-mini (higher quality) | $0.40 | $1.60 | ~$4.70 |

Inference is roughly **$2–$5 per 1,000 conversations**. Embeddings (`text-embedding-3-small` @ $0.02/M) are a rounding error; a full re-embed of 50k products (~20M tokens) ≈ $0.40 per rebuild — incremental webhook re-indexing makes steady-state trivial. Reranking adds a few cents–dollars per 1k depending on hosted vs. self-hosted.

**Infrastructure** (fixed monthly): PaaS + managed Postgres + Redis + Qdrant Cloud ≈ **~$70–$250/month** at the start, scaling with traffic.

**All-in rule of thumb:** **~$3–$8 per 1,000 conversations**, trending down as fixed infra amortizes over volume.

### Cost-reduction levers
1. Semantic response cache (deflect 20–40% of LLM calls).
2. Tiered routing: cheap model default, escalate only on low confidence.
3. Trim retrieved context — reranking lets us send fewer, better chunks (input tokens dominate).
4. Prompt-caching / system-prompt reuse where supported.
5. Cap output length; structured answers over prose.
6. Batch + incremental embeddings (only changed products).
7. Self-host the reranker/image model at scale; use provider free tiers in dev.

---

## 11. Open assumptions to confirm

These don't block Phase 0–1 but affect later phases:
1. **Catalog format/size** — product count and how well descriptions/materials/care are populated.
2. **Handoff target** — Shopify Inbox / Gorgias / Zendesk / email?
3. **Languages** — which locales to support.
4. **Existing platform** — what it exposes that the widget must coexist with.
5. **Traffic numbers** — peak QPS / monthly conversations for sizing + SLOs.
6. **Budget ceiling** — monthly cost target to tune model/infra/profile.
7. **Bundles** — how they're built in your store (native / app / metafields).
8. **Promotions** — sale price on variant vs. automatic discount vs. codes.

---

## 12. Immediate next step

If this looks right, I'll start **Phase 0 (Foundations)**: repo scaffold, Docker/compose, env template, settings, logging, observability/SLO baseline, dev/staging Shopify store + seed + demo mode, prompt-versioning scaffolding, CI, and `/health` — then **Phase 1 (RAG MVP with reranking + basic handoff)**. Each phase ships for review before the next; no all-at-once code dump.

Tell me to proceed, or flag anything to change in the stack or phase order first.
