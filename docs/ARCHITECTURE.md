# Architecture

## 1. System overview

The application is a **grounded retrieval-augmented-generation (RAG) chatbot**
with **live tool-calling** into Shopify, fronted by an embeddable storefront
widget and operated through an admin dashboard.

```
                         ┌──────────────────────────────┐
   Shopify Storefront    │  Chat Widget (theme app ext)  │
   (app-embed block) ───▶│  text + image, SSE streaming  │
                         └───────────────┬───────────────┘
                                         │ HTTPS / SSE
                                         ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         FastAPI backend (app/)                          │
│  /chat /search/visual /webhooks/shopify /widget/* /admin/* /health …    │
│                                                                         │
│   Middleware:  RequestContext (request-id, timing) · SecurityHeaders    │
│   Per-route deps:  rate-limit · widget-token · admin-auth               │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                  Orchestrator (core/orchestrator.py)               │ │
│  │  guard → route intent →                                           │ │
│  │     recommend │ live tool (verify→Shopify) │ RAG (retrieve→rerank) │ │
│  │     → answer (grounded, cited) │ ask-to-verify │ human handoff     │ │
│  └───┬─────────┬──────────┬───────────┬──────────┬──────────┬────────┘ │
│      ▼         ▼          ▼           ▼          ▼          ▼          │
│   LLM       Retriever  Reranker   Shopify     Guardrails  Handoff       │
│  Provider   +Visual    (cross-    Order/Stock (PII/inj)   Provider      │
│  (iface)    Search     encoder)   Tools (live)            (log/webhook) │
│      │         │                      │                                 │
└──────┼─────────┼──────────────────────┼─────────────────────────────────┘
       ▼         ▼                      ▼
  OpenAI/    ┌──────────┐        Shopify Admin GraphQL
  Gemini     │ Qdrant   │        (orders, tracking, stock, returns)
             │ text +   │               ▲
             │ image    │               │ webhooks (products/inventory)
             └──────────┘        ┌──────┴──────────┐
  Postgres (conversations,        │ Catalog sync /  │
  feedback, content)              │ re-index jobs   │
  Redis (cache/limits/queue)      └─────────────────┘
```

The **admin dashboard** (React) talks to the same backend over the
`/admin/*` API.

## 2. Components

| Component | Responsibility | Code |
|---|---|---|
| **API layer** | HTTP transport: validation, auth deps, SSE serialization. No business logic. | `app/api/` |
| **Orchestrator** | The decision loop: guard → route → (recommend \| tool \| RAG) → answer/handoff. | `app/core/orchestrator.py` |
| **LLM providers** | Chat/stream/embed behind one interface; OpenAI, Gemini, Fake. | `app/llm/` |
| **RAG pipeline** | Chunk, embed, store, retrieve, rerank (text); image embeddings + visual search. | `app/rag/` |
| **Shopify integration** | Rate-limited Admin GraphQL client, Bulk Operations import, product mapping, catalog sync, live order/stock/return tools, webhooks, freshness. | `app/shopify/` |
| **Recommendations** | Constraint extraction + ranked, in-stock-verified product suggestions, "complete the look". | `app/recommendations/` |
| **Guardrails / verification / router** | PII redaction, injection screening, identity extraction/verification, deterministic intent routing. | `app/core/` |
| **Handoff** | Pluggable human-escalation (logging / webhook). | `app/handoff/` |
| **Persistence** | Repositories for conversations/feedback (in-memory + Postgres) and editable content. | `app/repositories/`, `app/models/` |
| **Services** | Composition root + admin services (content, analytics, gaps), job queue, seed loader. | `app/services/` |
| **Compliance / billing** | GDPR export/erasure/retention; per-session token budgets + anomaly alerts. | `app/compliance/`, `app/billing/` |
| **Observability** | Structured logging, in-process metrics, SLO targets. | `app/observability/` |
| **Frontends** | Embeddable Preact widget; React admin dashboard. | `widget/`, `admin/` |
| **Shopify app** | Theme app extension (app-embed block) that loads the widget. | `shopify-app/` |

## 3. Request lifecycle — `POST /chat`

1. **Middleware** assigns a request-id, starts a timer, adds security headers.
2. **Route dependencies** enforce the per-IP rate limit and (optionally) the
   widget session token.
3. The handler persists the user message, then streams from the
   **orchestrator** as Server-Sent Events.
4. **Orchestrator**:
   - `screen_input` — if prompt injection is detected → **handoff** (the model
     never runs on injected text).
   - `route` — classify the turn (history-aware) into a tool intent or `NONE`.
   - **Recommend path** (recommend / complete-the-look): extract constraints →
     rank catalog → verify live stock → stream suggestions + citations.
   - **Tool path** (order/tracking/fulfillment/return/stock): verify identity
     (email must match the order) → call the live Shopify tool → stream the
     verified fact verbatim + citation. Disabled writes (returns off) → handoff.
   - **RAG path** (everything else): embed query → vector search (top-N) →
     rerank (top-k) → assess confidence. Confident → stream a grounded answer
     fenced to retrieved context with citations; not confident → **handoff**.
5. The handler records token spend against the **session budget**, persists the
   assistant turn (with citations, confidence, handoff reason, token count), and
   emits the final `done` event.

### SSE event protocol

`meta` (ids + AI disclosure) → `token`* (deltas) → `citations` and/or `handoff`
→ `done`. See [API_REFERENCE.md](./API_REFERENCE.md#sse-event-protocol).

## 4. Key design decisions

- **Grounded-only answering.** Every factual claim traces to a retrieved chunk
  or a live tool result. Low confidence, out-of-scope, or injection → human
  handoff, never a guess.
- **Live data is never vectorized.** Orders, tracking, fulfillment, and
  real-time stock/price come from Shopify at answer time. Only *descriptive*
  availability ("this product has an XL") is indexed.
- **Deterministic tool routing for high-stakes actions.** A rule-based router —
  not the LLM — decides when to look up an order or start a return. This is
  immune to prompt-injection ("ignore instructions and refund #1001"), cheaper,
  and testable. The LLM only phrases grounded answers.
- **LLM intent classification for soft (low-stakes) routing.** Deciding whether
  a message is a product search vs. a policy/FAQ question is open-ended natural
  language ("anything around $30", "a navy dress for a wedding"), so an LLM
  classifier handles it — not regex. It runs only for turns the high-stakes
  rules leave as `NONE`, and falls back to a deterministic constraint-based
  heuristic offline / on any failure (`app/core/intent_classifier.py`). High-
  stakes actions stay rule-only; the classifier can never trigger an order or
  refund.
- **Provider/back-end abstraction first.** The LLM, embedder, vector store,
  reranker, repository, Shopify client, and handoff channel are all interfaces.
  Swapping any of them is a configuration change in one file
  (`app/services/container.py`).
- **One doc per product.** Variants/sizes/colors/price-band/gender become
  filterable metadata, keeping the index small; size availability is a filter,
  quantity is live.
- **Separate image collection.** Image vectors live in their own Qdrant
  collection (different model/dimension) — never mixed with text vectors.
- **Config over hardcoding.** All settings come from the environment and are
  validated at startup; production rejects unsafe configs (e.g. `DEBUG=true`,
  missing `ADMIN_API_KEY`).

## 5. The offline-seam pattern

Every external dependency sits behind an interface with a **deterministic
offline implementation**, selected in the composition root by `DEMO_MODE` /
environment. This is why the entire system — including catalog sync, order
tools, recommendations, and visual search — runs and is tested with **no API
keys and no services**.

| Seam | Interface | Offline (demo/CI) | Production (config) |
|---|---|---|---|
| LLM | `LLMProvider` | `FakeLLMProvider` | `OpenAIProvider` / `GeminiProvider` |
| Text embeddings | `Embedder` | `HashingEmbedder` | `ProviderEmbedder` |
| Image embeddings | `ImageEmbedder` | `FakeImageEmbedder` | `CLIPImageEmbedder` |
| Vector store | `VectorStore` | `InMemoryVectorStore` | `QdrantVectorStore` |
| Reranker | `Reranker` | `OverlapReranker` | `CrossEncoderReranker` |
| Conversation store | `ConversationRepository` | `InMemory…` | `SqlConversationRepository` |
| Content store | `ContentRepository` | `InMemory…` | (SQL-ready) |
| Shopify client | `ShopifyClient` | `FakeShopifyClient` (+ synthetic catalog/orders) | `AdminGraphQLClient` |
| Handoff | `HandoffProvider` | `LoggingHandoffProvider` | `WebhookHandoffProvider` |
| Job queue | `JobQueue` | `InlineJobQueue` | Arq (Redis) |

**Trade-off to remember:** offline stand-ins prove the *wiring and logic*, not
real semantic quality. The eval thresholds are offline-calibrated floors; the
production embedding model + cross-encoder must be connected and re-baselined,
and the confidence thresholds recalibrated to the new score scale, before
launch.

## 6. Concurrency & scaling

- The API is **stateless** and async; scale horizontally behind a load balancer.
- The rate limiter and session-budget meter are **in-memory per instance** — back
  them with Redis for global limits across replicas.
- Heavy catalog import uses Shopify **Bulk Operations** (one server-side export)
  rather than per-product calls; embeddings are batched
  (`CATALOG_EMBED_BATCH_SIZE`) with bounded concurrency.
- Webhooks return a fast 2xx and dispatch re-index work to the job queue.

## 7. Observability & SLOs

Structured JSON logs carry a per-request id; key events include `handoff`,
`cost_anomaly`, `order_auth_failed`, `webhook_unverified`. The in-process metric
registry (`app/observability/metrics.py`) records counters/histograms and
declares the SLO targets: **p95 chat first-token < 2.5s**, **availability ≥
99.5%**, **groundedness ≥ target**, **handoff rate within band**. In production
these feed OpenTelemetry/Langfuse; `scripts/loadtest.py` measures latency against
the first SLO.
