# Live / production setup

Deploy the system for real: a real LLM provider (OpenAI/Gemini), Qdrant for
vectors, Postgres for data, Redis for cache/limits, and a live Shopify store.
This sets `DEMO_MODE=false`, so every stand-in is replaced by the real backend.

> Prerequisites: an LLM API key, Qdrant, Postgres, Redis, a Shopify store with a
> custom app, and a host for the API (Render/Railway/Fly/your cloud). See
> [SETUP.md](./SETUP.md#prerequisites-all-paths) and the deeper
> [DEPLOY.md](./DEPLOY.md).

---

## 1. Provision the managed services

| Service | Purpose | Get a connection string |
|---|---|---|
| **Postgres** | conversations, feedback, content | `DATABASE_URL=postgresql+asyncpg://USER:PASS@HOST:5432/DB` |
| **Redis** | cache, rate-limit, queue, budgets | `REDIS_URL=redis://HOST:6379/0` |
| **Qdrant** | text + image vector collections | `QDRANT_URL=https://...`, `QDRANT_API_KEY=...` |
| **LLM** | OpenAI or Gemini | `OPENAI_API_KEY=...` (or `GEMINI_API_KEY=...`) |

(For a self-hosted trial you can run these from `docker-compose.yml`, but
production should use managed instances.)

---

## 2. Create the Shopify custom app

Follow **[SHOPIFY_SETUP.md](./SHOPIFY_SETUP.md)** in full. Summary (legacy
in-admin custom apps were retired 2026-01-01 — use the **Dev Dashboard**):

1. **<https://dev.shopify.com/dashboard>** → **Create app** → name it, **Create**.
2. **Configure Admin API scopes** (least privilege):
   - catalog: `read_products`, `read_inventory`
   - orders (Phase 3): `read_orders`, `read_fulfillments` (+ return scopes only
     if you enable returns).
3. **Install** the app, then open **Settings** and copy the **Client ID** and
   **Client secret**. (No `shpat_…` token — the app auto-fetches a 24h token via
   the client-credentials grant.)
4. The **Client secret** also serves as the webhook HMAC secret.

You'll set:
```
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_CLIENT_ID=<client id>
SHOPIFY_CLIENT_SECRET=<client secret>
SHOPIFY_WEBHOOK_SECRET=<client secret>
```

---

## 3. Production environment

Create the production env (inject via your PaaS secret manager — **do not commit
a `.env`**). Minimum required:

```bash
ENVIRONMENT=production
DEBUG=false
DEMO_MODE=false

# LLM
LLM_DEFAULT_PROVIDER=openai
LLM_DEFAULT_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# Datastores
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/storechat
REDIS_URL=redis://host:6379/0
QDRANT_URL=https://your-qdrant:6333
QDRANT_API_KEY=...

# Shopify (Dev Dashboard client-credentials grant)
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_CLIENT_ID=...
SHOPIFY_CLIENT_SECRET=...
SHOPIFY_WEBHOOK_SECRET=...              # = the app's Client secret

# Security / access
ADMIN_API_KEY=<long-random-string>     # REQUIRED in production (startup fails without it)
WIDGET_SECRET=<long-random-string>     # enables signed widget tokens
WIDGET_REQUIRE_TOKEN=true
CORS_ORIGINS=https://your-store.myshopify.com,https://admin.yourdomain.com
```

Startup validation will reject the deploy if `ADMIN_API_KEY` is missing or
`DEBUG=true`. Review every option in [CONFIGURATION.md](./CONFIGURATION.md).

> Real semantic quality: with `DEMO_MODE=false`, install the model extras and
> connect a cross-encoder/CLIP for best results:
> `uv sync --extra providers --extra vector --extra ml`. Then **re-baseline the eval and raise
> the gate thresholds**, and recalibrate `RAG_MIN_CONFIDENCE` to the new score
> scale (the defaults are calibrated for the offline reranker).

---

## 4. Build & deploy the backend

```bash
cd backend
docker build -t store-chat-bot .
# Run with your production env (secret manager), exposing port 8000:
docker run -p 8000:8000 --env-file /path/to/prod.env store-chat-bot
```

On a PaaS (Render/Railway/Fly), point it at `backend/Dockerfile` (a uv-based
multi-stage build) and set the env in the dashboard. Health/readiness probes:
`GET /health`, `GET /ready`.

To run without Docker: `uv sync --extra providers --extra vector --extra ml`
then `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### Database schema
The SQL repository creates its tables on first use for convenience. For
controlled production migrations, generate and apply Alembic migrations from
`backend/migrations/` (`alembic upgrade head`) as part of your deploy.

---

## 5. Initial catalog import + webhooks

After the backend is live with real Shopify credentials:

1. **Full catalog import** (Bulk Operations) — invoke
   `CatalogSyncService.full_import()` once (add a small management command or an
   admin-triggered job). This exports the whole catalog server-side and indexes
   it into Qdrant in batches.
2. **Register webhooks** pointing at your deployed API
   (`https://api.yourdomain.com/webhooks/shopify`) for:
   `products/create`, `products/update`, `products/delete`,
   `inventory_levels/update`. Each is HMAC-verified with `SHOPIFY_WEBHOOK_SECRET`.

Easiest: run the bundled helper, which uses the same client-credentials auth as
the app:

```bash
python -m scripts.register_webhooks
```

Or, by hand with curl — first exchange your Client ID/secret for a short-lived
token (the same call the app makes), then register the webhook:

```bash
ACCESS_TOKEN=$(curl -s -X POST \
  "https://$SHOPIFY_STORE_DOMAIN/admin/oauth/access_token" \
  -d "grant_type=client_credentials" \
  -d "client_id=$SHOPIFY_CLIENT_ID" \
  -d "client_secret=$SHOPIFY_CLIENT_SECRET" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST "https://$SHOPIFY_STORE_DOMAIN/admin/api/2025-01/graphql.json" \
  -H "X-Shopify-Access-Token: $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation { webhookSubscriptionCreate(topic: PRODUCTS_UPDATE, webhookSubscription: { callbackUrl: \"https://api.yourdomain.com/webhooks/shopify\", format: JSON }) { userErrors { message } webhookSubscription { id } } }"}'
```

Repeat for `PRODUCTS_CREATE`, `PRODUCTS_DELETE`, `INVENTORY_LEVELS_UPDATE`.

---

## 6. Deploy the widget to the storefront

```bash
cd widget && npm install && npm run build
cp dist/widget.js ../shopify-app/extensions/chat-widget/assets/widget.js
cd ../shopify-app && shopify app deploy        # Shopify CLI
```

In the Shopify admin: **Online Store → Themes → Customize → App embeds** →
enable **AI Support Chat** → set the **API base URL** to your deployed backend,
brand colour, position, language. See [WIDGET.md](./WIDGET.md) for CORS/CSP.

---

## 7. Deploy the admin dashboard

```bash
cd admin && npm install && npm run build       # → dist/
```

Host `dist/` as a static site (behind auth/VPN ideally). Operators connect with
the API base URL + the `ADMIN_API_KEY`. Lock `CORS_ORIGINS` to include the admin
origin. (For real auth, place SSO in front of the token entry.)

---

## 8. Go-live checklist

- [ ] `ENVIRONMENT=production`, `DEBUG=false`, `DEMO_MODE=false`.
- [ ] `ADMIN_API_KEY` and `WIDGET_SECRET` set to strong random values.
- [ ] `CORS_ORIGINS` locked to the storefront + admin origins (no `*`).
- [ ] Provider/Qdrant/Postgres/Redis reachable (`GET /ready`).
- [ ] Catalog imported; product/inventory webhooks registered + verified.
- [ ] Eval re-baselined with real models; gate thresholds raised;
      `RAG_MIN_CONFIDENCE` recalibrated.
- [ ] Returns: leave `RETURNS_ENABLED=false` until return scopes are granted.
- [ ] Retention sweep scheduled (`POST /admin/privacy/purge-expired` daily).
- [ ] Load test run against the p95 SLO (`scripts/loadtest.py`).
- [ ] Rate limiter / session budget backed by Redis if running multiple replicas.

See [DEPLOY.md](./DEPLOY.md), [RUNBOOK.md](./RUNBOOK.md),
[COMPLIANCE.md](./COMPLIANCE.md), and [COST.md](./COST.md) for operations.
