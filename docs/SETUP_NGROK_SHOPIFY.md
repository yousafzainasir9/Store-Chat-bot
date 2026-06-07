# Local setup with ngrok + live Shopify

Run the backend on your laptop but connect it to a **real Shopify (dev) store** —
including **webhooks that reach `localhost`** through an [ngrok](https://ngrok.com)
HTTPS tunnel. This is the realistic way to develop/test the live Shopify
integration (catalog sync, webhooks, live order/stock tools) without deploying.

```
 Shopify dev store ──webhook──▶  https://abc123.ngrok-free.app  ──▶  localhost:8000 (your backend)
        ▲                                   (ngrok tunnel)
        └──── Admin GraphQL (catalog/orders) ◀── your backend
```

> Prerequisites: everything from [SETUP_LOCAL.md](./SETUP_LOCAL.md) working, plus
> a Shopify dev store + custom app, an OpenAI/Gemini key, and an ngrok account.

---

## 1. Create the Shopify custom app

Do **[SHOPIFY_SETUP.md](./SHOPIFY_SETUP.md)** steps 1–4. You need:
- `SHOPIFY_STORE_DOMAIN` (e.g. `my-dev-store.myshopify.com`)
- `SHOPIFY_ADMIN_API_TOKEN` (`shpat_…`)
- `SHOPIFY_WEBHOOK_SECRET` = the app's **API secret key** (used to verify webhook
  HMAC)
- Scopes: `read_products`, `read_inventory` (add `read_orders`,
  `read_fulfillments` to test order tools).

---

## 2. Configure the local `.env` for live Shopify

Edit the repo-root `.env`:

```bash
ENVIRONMENT=development
DEMO_MODE=false                       # <-- use the REAL backends now

# LLM (required once DEMO_MODE=false)
LLM_DEFAULT_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Shopify (your dev store)
SHOPIFY_STORE_DOMAIN=my-dev-store.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_...
SHOPIFY_WEBHOOK_SECRET=<app API secret key>

# Vector store + data: simplest is the docker-compose services (next step).
QDRANT_URL=http://localhost:6333
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/storechat
REDIS_URL=redis://localhost:6379/0

# Allow your storefront origin if you also embed the widget on the dev store:
CORS_ORIGINS=https://my-dev-store.myshopify.com,http://localhost:5173
```

> Minimal variant: you can leave `QDRANT_URL`/`DATABASE_URL` unset to use the
> in-memory stores for a quick test, and only set Shopify + OpenAI. Webhooks and
> live order/stock tools still work; data just isn't persisted across restarts.

Install the real-backend extras:

```bash
cd backend
source .venv/bin/activate
pip install -e ".[dev,providers,vector]"      # add ,ml for cross-encoder/CLIP
```

---

## 3. Start local services (Qdrant/Postgres/Redis)

If you set `QDRANT_URL`/`DATABASE_URL`/`REDIS_URL` above, bring them up:

```bash
docker compose up -d postgres redis qdrant
```

(Or skip this and use the in-memory variant.)

---

## 4. Run the backend

```bash
cd backend
uvicorn app.main:app --reload --env-file ../.env --host 0.0.0.0 --port 8000
curl http://localhost:8000/health      # "demo_mode": false
```

---

## 5. Start the ngrok tunnel

In a second terminal:

```bash
ngrok http 8000
```

ngrok prints a public HTTPS URL, e.g.:

```
Forwarding   https://abc123.ngrok-free.app -> http://localhost:8000
```

Copy that `https://abc123.ngrok-free.app` — call it **`$NGROK`**. Verify it
reaches your backend:

```bash
curl https://abc123.ngrok-free.app/health
```

> Keep ngrok running; the free URL changes each restart. If it changes, re-run
> the webhook registration in step 7 with the new URL.

---

## 6. Import the catalog

Trigger a one-time Bulk Operations import so your dev store's products are
indexed (via a management command/REPL):

```bash
cd backend
python - <<'PY'
import asyncio
from app.config import get_settings
from app.services.container import build_container

async def main():
    c = build_container(get_settings())
    await c.bootstrap()                       # seed KB
    n = await c.catalog.full_import()         # live Shopify bulk import
    print("indexed product chunks:", n)

asyncio.run(main())
PY
```

Now product questions and recommendations use your real catalog. Test it:

```bash
curl -N -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"do you have any dresses?"}'
```

---

## 7. Register Shopify webhooks → the ngrok URL

Point Shopify's webhooks at `"$NGROK/webhooks/shopify"`:

```bash
NGROK=https://abc123.ngrok-free.app
STORE=my-dev-store.myshopify.com
TOKEN=shpat_...

for TOPIC in PRODUCTS_CREATE PRODUCTS_UPDATE PRODUCTS_DELETE INVENTORY_LEVELS_UPDATE; do
  curl -s -X POST "https://$STORE/admin/api/2025-01/graphql.json" \
    -H "X-Shopify-Access-Token: $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { webhookSubscriptionCreate(topic: $TOPIC, webhookSubscription: { callbackUrl: \\\"$NGROK/webhooks/shopify\\\", format: JSON }) { userErrors { message } webhookSubscription { id } } }\"}"
  echo
done
```

---

## 8. Test the end-to-end webhook flow

1. In the Shopify admin, **edit a product** (e.g. change its title or
   description) and save.
2. Watch the backend logs — you should see a verified webhook and a re-index:
   ```
   {"event":"request","path":"/webhooks/shopify","status":200,...}
   {"event":"reindex_product","product_id":"gid://shopify/Product/...","chunks":1}
   ```
3. Ask the bot about the changed product — the new content is reflected.

If you instead see `{"event":"webhook_unverified"}` with a `401`, your
`SHOPIFY_WEBHOOK_SECRET` doesn't match the app's API secret key — fix it and
restart the backend.

---

## 9. (Optional) Embed the widget on the dev storefront

To test the widget on the real store pointing at your local backend via ngrok:

- Build the widget (`cd widget && npm run build`) and deploy the theme app
  extension to the dev store (`cd shopify-app && shopify app deploy`).
- In the theme editor's App embed settings, set the **API base URL** to your
  **`$NGROK`** URL.
- Ensure `CORS_ORIGINS` in `.env` includes `https://my-dev-store.myshopify.com`,
  then restart the backend.

---

## 10. Test live order tools (optional)

With `read_orders` + `read_fulfillments` scopes granted and a real order in the
dev store:

```bash
curl -N -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"where is my order #1001, email customer@example.com"}'
```

The bot verifies the email against the order before returning anything; a
mismatch returns a uniform "couldn't verify" with no data leak. Keep
`RETURNS_ENABLED=false` unless you've granted return scopes and want to test
writes.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401` on webhooks (`webhook_unverified`) | `SHOPIFY_WEBHOOK_SECRET` ≠ app API secret key. |
| ngrok URL stopped working | Free URLs rotate on restart; re-run step 7 with the new URL. |
| Catalog questions return nothing | Run the import in step 6; check `read_products` scope. |
| `THROTTLED` errors in logs | Normal under load; the client backs off automatically. |
| Provider/auth error once `DEMO_MODE=false` | Set `OPENAI_API_KEY` (or `GEMINI_API_KEY`) and install `.[providers]`. |
| ngrok browser warning page | Add header `ngrok-skip-browser-warning: 1` when testing via curl, or use a paid domain. |
