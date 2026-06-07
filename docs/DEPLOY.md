# Deployment guide

The system is container-based and cloud-portable (Render / Railway / Fly.io +
managed Postgres, Redis, and Qdrant). Nothing is hardcoded — every setting comes
from the environment (see `.env.example`).

## Components to deploy

| Component | What | How |
|---|---|---|
| Backend API | FastAPI (`backend/`) | Docker image; `uvicorn app.main:app` |
| Worker (Phase 2+) | Arq re-index/reconcile jobs | same image, worker entrypoint |
| Postgres | conversations, feedback, content | managed |
| Redis | cache, rate-limit, job queue, budgets | managed |
| Qdrant | text + image vector collections | managed (Qdrant Cloud) |
| Widget | `widget/dist/widget.js` | Shopify theme app extension asset |
| Admin | `admin/dist/` | static host |

## Backend

```bash
cd backend
docker build -t store-chat-bot .
# Provide env via the PaaS secret manager (not a committed .env).
docker run -p 8000:8000 --env-file .env store-chat-bot
```

Required production env (beyond defaults): `ENVIRONMENT=production`,
`OPENAI_API_KEY` (or `GEMINI_API_KEY`), `DATABASE_URL`, `REDIS_URL`,
`QDRANT_URL`, `SHOPIFY_*`, `ADMIN_API_KEY`, `WIDGET_SECRET`,
`CORS_ORIGINS` (locked to the storefront + admin origins). Startup validation
fails fast if `ADMIN_API_KEY` is missing or `DEBUG=true` in production.

## Database migrations

Alembic migrations live in `backend/migrations/`. Run them on deploy:

```bash
alembic upgrade head
```

## Catalog bootstrap

After first deploy with real Shopify credentials, trigger a full catalog import
(`CatalogSyncService.full_import`) and register the product/inventory webhooks
(see `docs/SHOPIFY_SETUP.md`). Steady state is webhook-driven.

## Health & probes

Point orchestration liveness at `GET /health` and readiness at `GET /ready`.
`GET /metrics` exposes the in-process metric snapshot + SLO targets.

## Scaling notes

- The API is stateless; scale horizontally behind a load balancer.
- The in-memory rate limiter and session-budget meter are per-instance — back
  them with Redis for global limits across replicas.
- Embedding/re-index throughput is tuned by `CATALOG_EMBED_BATCH_SIZE` and
  `CATALOG_IMPORT_CONCURRENCY`.
