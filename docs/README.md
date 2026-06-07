# Documentation — Store Chat Bot

Complete technical documentation for the **Fashion & Clothing AI Customer-Support
Chatbot** (Shopify-integrated, RAG-based, with an embeddable storefront widget
and an admin dashboard).

This folder is the canonical reference. Start with the index below.

## Contents

| Document | What it covers |
|---|---|
| **[SETUP.md](./SETUP.md)** | **Start here for installation** — prerequisites + which path to choose. |
| [SETUP_LOCAL.md](./SETUP_LOCAL.md) | Local setup with tests (demo mode, no API keys). |
| [SETUP_LIVE.md](./SETUP_LIVE.md) | Live / production setup (real providers, Qdrant, Postgres, Shopify). |
| [SETUP_NGROK_SHOPIFY.md](./SETUP_NGROK_SHOPIFY.md) | Local backend + ngrok tunnel + live Shopify webhooks. |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System overview, components, request lifecycle, data flow, key design decisions, the offline-seam pattern. |
| [CODE_STRUCTURE.md](./CODE_STRUCTURE.md) | Repository layout, layering, the composition root, and a **file-by-file reference** for every backend module. |
| [API_REFERENCE.md](./API_REFERENCE.md) | Every HTTP endpoint: method, path, auth, request/response shapes, SSE event protocol, errors. |
| [CONFIGURATION.md](./CONFIGURATION.md) | Every environment variable, its default, validation, and which phase/feature it controls. |
| [DATA_MODEL.md](./DATA_MODEL.md) | Domain models, the Postgres schema, and the vector collections. |
| [FRONTEND.md](./FRONTEND.md) | The Preact storefront widget and the React admin dashboard — architecture and files. |
| [TESTING.md](./TESTING.md) | Test suite map, the evaluation harness, the eval gate, and CI. |
| [SHOPIFY_SETUP.md](./SHOPIFY_SETUP.md) | Custom-app setup, scopes, Bulk Operations import, webhooks, freshness. |
| [WIDGET.md](./WIDGET.md) | Embedding the widget on a Shopify storefront, CORS, CSP. |
| [DEPLOY.md](./DEPLOY.md) | Deployment topology, env, migrations, scaling. |
| [RUNBOOK.md](./RUNBOOK.md) | Operations: dashboards, alerts, routine tasks, incidents. |
| [COMPLIANCE.md](./COMPLIANCE.md) | Privacy, GDPR/CCPA rights, retention, injection defense. |
| [COST.md](./COST.md) | Cost per 1,000 conversations and reduction levers. |

See also the repo root: [`../README.md`](../README.md) (quick start) and
[`../DEVELOPMENT_PLAN.md`](../DEVELOPMENT_PLAN.md) (the master engineering plan).

## What this system is

A production-grade, **grounded** RAG chatbot for a fashion e-commerce store:

- Answers FAQs, shipping/returns/size/care questions from a knowledge base, with
  **citations** and a **human handoff** when confidence is low.
- Looks up **live** order status, tracking, fulfillment, and stock through Shopify
  (never from the index), behind **identity verification**.
- Gives **fashion recommendations** and **visual (image) search**, both verified
  in stock before suggesting.
- Ships as an **embeddable storefront widget** (Shopify theme app extension) and
  comes with a **React admin dashboard** (content management, conversation
  review, a feedback→content-gap loop, and analytics).

## Tech stack at a glance

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, async SQLAlchemy |
| Retrieval | Qdrant (text + image collections), provider embeddings, cross-encoder rerank |
| LLM | OpenAI / Gemini behind a provider interface (swappable) |
| Datastores | Postgres (conversations/feedback/content), Redis (cache/limits/queue) |
| Catalog | Shopify Admin GraphQL + Bulk Operations + webhooks |
| Widget | Preact + Vite (single ~10 KB gzip bundle) |
| Admin | React (Preact/compat) + Vite + Recharts |
| Tooling | ruff, black, mypy --strict, pytest, gitleaks, GitHub Actions |

## Conventions used in these docs

- **Offline / demo mode** means `DEMO_MODE=true`: every external dependency is
  replaced by a deterministic in-process stand-in, so the whole system runs and
  is tested with no API keys or services. Production swaps in the real backends
  via configuration — see the seam table in
  [ARCHITECTURE.md](./ARCHITECTURE.md#5-the-offline-seam-pattern).
- Paths are relative to the repository root unless noted.
