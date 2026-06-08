# Setup guide

This is the master setup document. It lists prerequisites, helps you pick the
right path, and links to three step-by-step guides:

| Guide | Use it when… |
|---|---|
| **[SETUP_LOCAL.md](./SETUP_LOCAL.md)** — local + tests (demo mode) | You want to run and test everything on your machine with **no API keys and no external services**. Best first step. |
| **[SETUP_LIVE.md](./SETUP_LIVE.md)** — live / production | You're deploying for real: real LLM provider, Qdrant, Postgres, Redis, and a live Shopify store. |
| **[SETUP_NGROK_SHOPIFY.md](./SETUP_NGROK_SHOPIFY.md)** — local + ngrok + live Shopify | You want to run the backend on your laptop but connect it to a **real Shopify (dev) store**, including webhooks reaching `localhost` via an ngrok tunnel. |

> Not sure? Start with **SETUP_LOCAL.md**. Once that works, use
> **SETUP_NGROK_SHOPIFY.md** to test against a real store, then
> **SETUP_LIVE.md** to deploy.

---

## Prerequisites (all paths)

| Tool | Version | Notes |
|---|---|---|
| **Python** | **3.12+** | The backend targets 3.12. Installed automatically by uv. |
| **uv** | latest | Python package manager — `curl -LsSf https://astral.sh/uv/install.sh \| sh`. |
| **Node.js** | **18+** (20/22 recommended) | For the widget and admin frontends. |
| **Git** | any | |
| **Docker + Docker Compose** | recent | Optional locally; the fastest way to run Postgres/Redis/Qdrant. |

Path-specific extras:

| Tool | Needed for | Notes |
|---|---|---|
| **OpenAI or Gemini API key** | live, ngrok | The LLM provider. |
| **Qdrant** | live (and optional for ngrok) | Qdrant Cloud or the docker-compose service. |
| **Postgres + Redis** | live (optional for ngrok) | Managed in prod; docker-compose locally. |
| **Shopify dev store + custom app** | live, ngrok | Admin API token + API secret (for webhook HMAC). See [SHOPIFY_SETUP.md](./SHOPIFY_SETUP.md). |
| **ngrok** | ngrok path | Free account is enough; exposes `localhost:8000` over HTTPS. |

---

## Repository layout (what you'll touch)

```
store-chat-bot/
├── backend/        # FastAPI API  → run with uvicorn or Docker
├── widget/         # Embeddable chat widget (Vite build → dist/widget.js)
├── admin/          # Admin dashboard (Vite build → dist/)
├── shopify-app/    # Theme app extension (loads the built widget)
├── .env.example    # Copy to .env at the repo root and edit
└── docker-compose.yml
```

## The one rule that explains everything: `DEMO_MODE`

`DEMO_MODE=true` (the default) makes every external dependency use a
**deterministic in-process stand-in** — no LLM, no Qdrant, no Postgres, no
Shopify. This is what makes local setup and the test suite work with zero
credentials.

`DEMO_MODE=false` switches to the **real** backends, which you then configure via
environment variables. The live and ngrok guides set `DEMO_MODE=false`.

See [CONFIGURATION.md](./CONFIGURATION.md) for every variable.

---

## Verify any running instance

```bash
curl http://localhost:8000/health
# {"status":"ok", "demo_mode": true|false, ...}

curl -N -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"How long does shipping take?"}'
# streams: event: meta → event: token … → event: citations → event: done
```
