# Store Chat Bot — Fashion & Clothing AI Support Assistant (Shopify)

A grounded, RAG-based AI customer-support chatbot for a fashion & clothing
e-commerce store, integrated with Shopify and deployable as an embeddable
storefront widget. Built phase by phase per [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md).

> **Status:** ✅ All 8 phases complete. The system is feature-complete: grounded
> RAG chat, Shopify catalog sync, live order/return tools, fashion
> recommendations, visual search, an embeddable storefront widget, an admin
> dashboard + feedback loop, and Phase 8 hardening — GDPR/CCPA export/erasure +
> retention, per-session token budgets with cost-anomaly alerts, a prompt-
> injection red-team suite, a 106-pair eval gate (a CI unit test), a load-test
> script, and launch docs ([DEPLOY](./docs/DEPLOY.md) · [RUNBOOK](./docs/RUNBOOK.md)
> · [COMPLIANCE](./docs/COMPLIANCE.md) · [COST](./docs/COST.md)).

---

## Documentation

Full documentation lives in [`docs/`](./docs/) — start at
[`docs/README.md`](./docs/README.md). It covers the
[architecture](./docs/ARCHITECTURE.md), a file-by-file
[code structure](./docs/CODE_STRUCTURE.md), the
[API reference](./docs/API_REFERENCE.md),
[configuration](./docs/CONFIGURATION.md),
[data model](./docs/DATA_MODEL.md),
[frontend](./docs/FRONTEND.md),
[testing & eval](./docs/TESTING.md), plus deploy/runbook/compliance/cost guides.

---

## Why these choices (design summary)

The full rationale and trade-offs live in [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md);
the short version:

- **FastAPI (Python 3.12)** — async-native for streaming chat and concurrent
  Shopify calls; Pydantic typing and OpenAPI for free.
- **Provider abstraction first** — the LLM is swappable (OpenAI / Gemini / Grok)
  behind one interface, so adding a provider is config, not a rewrite.
- **Grounded-only answering** — every factual claim traces to a retrieved source
  or a live tool result; low confidence routes to a human, never a guess.
- **Live data is never vectorized** — orders, tracking, fulfillment, and
  real-time stock come from Shopify tool calls at answer time.
- **Config over hardcoding** — all settings come from the environment and are
  validated at startup, so a misconfigured deploy fails fast.
- **Observability + SLOs from day one** — request correlation, structured logs,
  a metrics baseline, and declared SLO targets to load-test against.

---

## Repository layout

```
store-chat-bot/
├── backend/                 # FastAPI backend (this phase)
│   ├── app/
│   │   ├── main.py          # App factory + middleware wiring
│   │   ├── config.py        # Pydantic Settings (env only, validated)
│   │   ├── api/             # Thin route handlers (health/ready/metrics)
│   │   ├── core/prompts/    # Versioned, eval-gated prompt registry
│   │   └── observability/   # Structured logging, metrics, SLO targets
│   ├── eval/                # Evaluation harness (grows in Phase 1+)
│   ├── tests/               # Unit/integration tests
│   ├── Dockerfile
│   └── pyproject.toml
├── docker-compose.yml       # api + postgres + redis + qdrant (local dev)
├── .env.example             # Documented env template (copy to .env)
├── .github/workflows/ci.yml # lint → format → type → test → secret scan
└── DEVELOPMENT_PLAN.md      # Master engineering plan
```

The `widget/` (embeddable chat widget), `shopify-app/` (theme app extension),
and `admin/` (React dashboard) directories are all present.

---

## Quick start (local, with Docker)

```bash
cp .env.example .env          # then edit as needed
docker compose up --build     # backend + widget + admin + datastores
# API:    http://localhost:8000   (Swagger at /docs, health at /health)
# Widget: http://localhost:8082   (serves widget.js — the embeddable asset)
# Admin:  http://localhost:8081   (operations dashboard)
```

**Core services always run:** the **backend**, the **widget** (serves `widget.js`),
and the **admin dashboard**, plus Postgres/Redis/Qdrant.

For a full local demo, add the **sample storefront** with the `local` profile:

```bash
docker compose --profile local up --build
# Sample store: http://localhost:8080   (mock store with the chat widget embedded)
```

(For ngrok / live Shopify, use the core command — the sample store is skipped —
and set `DEMO_MODE=false` + the Shopify/provider keys.)

## Quick start (local, without Docker)

Uses [**uv**](https://docs.astral.sh/uv/) for package management (Python 3.12 is
fetched automatically by uv).

> The Python project lives in **`backend/`** — run all `uv` commands from there
> (or use `uv --directory backend …` from the repo root).

```bash
cd backend
uv sync --extra dev                  # create .venv + install deps + toolchain
cp ../.env.example ../.env           # demo mode by default (no keys needed)
uv run uvicorn app.main:app --reload --env-file ../.env
```

> Prefer pip? `pip install -e ".[dev]"` still works — the project is standard
> PEP 621. Generate a lockfile once with `uv lock` (commit `uv.lock`).

## Ops endpoints

| Endpoint   | Purpose                                            |
|------------|----------------------------------------------------|
| `/health`  | Liveness — process is up (cheap, no external deps) |
| `/ready`   | Readiness — configured dependencies reachable      |
| `/metrics` | In-process metric snapshot + declared SLO targets  |
| `/docs`    | Swagger UI (disabled in production)                |

## Development workflow

```bash
cd backend
uv run ruff check app tests eval scripts   # lint + import sort
uv run black app tests eval scripts        # format
uv run mypy app                            # strict type check
uv run pytest                              # tests + coverage
uv run python -m eval.run_eval --k 5       # eval gate

uv run pre-commit install                  # run the gates on every commit
```

CI (`.github/workflows/ci.yml`) runs lint → format-check → `mypy --strict` →
tests → eval gate, plus secret scanning, on every push and PR.

## Configuration

All configuration is environment-driven and validated at startup. See
[`.env.example`](./.env.example) for the full, documented list. Nothing is
hardcoded; secrets never live in the repo (`.env` is git-ignored).

## Security posture (Phase 0 baselines; expanded per phase)

- Secrets only via environment / PaaS secret manager; `.env` git-ignored.
- `debug` is rejected in production by config validation.
- Request-id correlation on every request; a `redact()` helper keeps PII out of
  logs (enforced as data flows in from Phase 1).
- Strict CORS (lock `CORS_ORIGINS` to the storefront origin in production).
- Secret scanning (gitleaks) in pre-commit and CI.

See [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md) §6 for the full security,
privacy, and compliance design.

## Talking to the bot (Phase 1)

`POST /chat` streams a grounded answer over Server-Sent Events:

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How long does shipping take?"}'
```

The stream emits `meta` (conversation/message ids + AI disclosure), then `token`
deltas, then `citations`, then `done`. Out-of-scope, low-confidence, or
prompt-injection inputs emit a `handoff` event instead of a guessed answer.

`POST /feedback` records a thumbs up/down on a reply (feeds the Phase-7
content-gap loop):

```bash
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"<id>","message_id":"<id>","value":"up"}'
```

### How it works

```
guard -> retrieve (vector top-N) -> rerank (top-k) -> assess confidence
      -> grounded answer with citations   (confident)
      -> human handoff                     (low confidence / out-of-scope / injection)
```

Every external dependency sits behind an interface with a deterministic offline
implementation, selected in one place (`app/services/container.py`):

| Seam | Demo / CI (offline) | Production (via config) |
|------|---------------------|--------------------------|
| LLM provider | `FakeLLMProvider` | OpenAI / Gemini (`LLM_DEFAULT_PROVIDER`) |
| Embeddings | `HashingEmbedder` | provider embeddings |
| Vector store | `InMemoryVectorStore` | Qdrant (`QDRANT_URL`) |
| Reranker | `OverlapReranker` | cross-encoder (`ml` extra) |
| Image embedder | `FakeImageEmbedder` | CLIP (`CLIP_MODEL_NAME`, `ml` extra) |
| Conversation store | in-memory | Postgres (`DATABASE_URL`) |
| Handoff | logging adapter | Gorgias / Zendesk / Inbox (Phase 3) |

Install real backends with the optional extras: `uv sync --extra providers --extra vector --extra ml`.

### Evaluation

```bash
cd backend && python -m eval.run_eval --k 5
```

Scores retrieval (recall@k, MRR — before vs. after rerank) and answering
(grounded-answer accuracy + refusal correctness) over `backend/eval/dataset.jsonl`
(106 pairs across FAQ, shipping, returns, size, care, product, recommendation, out-of-scope, and injection).
The same command is a CI gate.

## Visual search (Phase 5)

Upload a garment photo to find the nearest in-catalog, in-stock products:

```bash
curl -X POST http://localhost:8000/search/visual \
  -F "image=@my-jacket.jpg" \
  -F "category=Jacket" -F "budget_max=200"
```

Image vectors live in a **separate** collection from text (different model and
dimension — never mixed). In demo mode a deterministic stand-in matches on visual
attributes so the pipeline runs with no model; set `DEMO_MODE=false` and install
the `ml` extra to use a real CLIP-class encoder. Results respect the same
constraints as text recommendations and are verified in stock live.

## Roadmap

Phase 0 ✅ → Phase 1 (RAG MVP) ✅ → Phase 2 (Shopify catalog sync) ✅ →
Phase 3 (live orders + returns) ✅ → Phase 4 (recommendations) ✅ →
Phase 5 (visual search) ✅ → Phase 6 (storefront widget) ✅ →
Phase 7 (admin + feedback loop) ✅ → Phase 8 (hardening, eval, launch) ✅.
Each phase ships independently for review.
