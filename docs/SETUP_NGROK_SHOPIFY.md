# Connect the chatbot to your Shopify store with ngrok

Run the backend on your laptop but wire it to your **real Shopify dev store**
(`acme-threads.myshopify.com`) — including **webhooks that reach `localhost`**
through an [ngrok](https://ngrok.com) HTTPS tunnel. This is the realistic way to
develop and test the live Shopify integration (catalog sync, webhooks, live
order/stock tools) without deploying anything.

```
 Shopify dev store ──webhook──▶  https://abc123.ngrok-free.app  ──▶  localhost:8000 (your backend)
        ▲                                   (ngrok tunnel)
        └──── Admin GraphQL (catalog/orders) ◀── your backend
```

> **Prerequisites**
> - [SETUP_LOCAL.md](./SETUP_LOCAL.md) working (backend runs, tests pass).
> - Your Shopify dev store: **`acme-threads.myshopify.com`**.
> - An LLM key — you already use **Groq** (`GROQ_API_KEY`). OpenAI/Gemini are
>   optional alternatives.
> - A free [ngrok](https://ngrok.com) account + the `ngrok` CLI installed.

---

## 0. The five keys you need (and where each one comes from)

Everything below is just about getting these five values and pasting them into
`.env`. Get them first; the rest is wiring.

| `.env` variable | What it is | Where to get it |
|---|---|---|
| `SHOPIFY_STORE_DOMAIN` | Your store's permanent domain | It's `acme-threads.myshopify.com` (the `*.myshopify.com` URL, **not** a custom domain). |
| `SHOPIFY_ADMIN_API_TOKEN` | Admin API access token (`shpat_…`) | Custom app → **API credentials** → *Admin API access token* → **Reveal once**. |
| `SHOPIFY_WEBHOOK_SECRET` | Verifies webhook HMAC signatures | Custom app → **API credentials** → *API secret key*. |
| `GROQ_API_KEY` | Your LLM key (already set) | [console.groq.com](https://console.groq.com) → **API Keys**. Already in your `.env`. |
| ngrok authtoken | Authorizes the tunnel | [dashboard.ngrok.com](https://dashboard.ngrok.com) → *Your Authtoken*. |

> 🔐 **Never commit these.** They live only in `.env`, which is git-ignored. The
> Admin API token and API secret key grant full access to your store data.

---

## 1. Create the Shopify custom app and grab the two Shopify keys

A **custom app** (single store, token auth, no App Store review) is the right
choice here — see [SHOPIFY_SETUP.md](./SHOPIFY_SETUP.md) for the why.

1. In your Acme Threads admin: **Settings → Apps and sales channels →
   Develop apps**.
   - Direct link: `https://admin.shopify.com/store/acme-threads/settings/apps/development`
   - If prompted, click **Allow custom app development**.
2. **Create an app** → name it `Support Chatbot` → **Create app**.
3. Open the **Configuration** tab → **Admin API integration → Configure** and
   grant **only** these scopes for now (least privilege):
   - `read_products`
   - `read_inventory`
   - *(Add `read_orders`, `read_fulfillments` later only when you test order
     tools — see step 9.)*
   - **Save**.
4. Go to the **API credentials** tab → **Install app** → **Install**.
5. Copy your two Shopify keys from this same **API credentials** tab:
   - **Admin API access token** — click **Reveal token once**. This is
     `SHOPIFY_ADMIN_API_TOKEN` (starts with `shpat_`). ⚠️ Shown **once** — copy it
     now; if you lose it you must uninstall/reinstall.
   - **API secret key** — this is `SHOPIFY_WEBHOOK_SECRET`.

---

## 2. Add the keys to `.env`

Edit the **repo-root `.env`** (not `.env.example`). Flip these values:

```bash
# --- Switch off demo mode: use the REAL Shopify backend now ---
DEMO_MODE=false

# --- LLM (you're on Groq) ---
LLM_DEFAULT_PROVIDER=groq
LLM_DEFAULT_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=gsk_...                      # already set in your .env

# Groq has no embeddings API, so retrieval uses the offline hashing embedder.
# "auto" handles this automatically — leave it as-is (or set explicitly):
EMBEDDING_BACKEND=auto

# --- Shopify (your Acme Threads dev store) ---
SHOPIFY_STORE_DOMAIN=acme-threads.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_...         # from step 1.5
SHOPIFY_WEBHOOK_SECRET=...                # = API secret key, from step 1.5
SHOPIFY_API_VERSION=2025-01

# --- Datastores: simplest is the in-memory variant (see note) ---
# Leave these UNSET for a quick test (in-memory). Set them to use Postgres/Qdrant.
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/storechat
# QDRANT_URL=http://localhost:6333
# REDIS_URL=redis://localhost:6379/0

# --- Allow the storefront origin if you embed the widget on the dev store ---
CORS_ORIGINS=https://acme-threads.myshopify.com,http://localhost:5173
```

> **In-memory vs. persistent:** with `DATABASE_URL`/`QDRANT_URL`/`REDIS_URL`
> unset, the app uses in-memory stores — perfect for a quick end-to-end test
> (webhooks and live order/stock tools still work; data just resets on restart).
> To persist conversations and the index, set all three and run the datastores
> via `docker compose up -d postgres redis qdrant`.

> **Why `EMBEDDING_BACKEND=auto`:** Groq is chat-only (no embeddings endpoint).
> `auto` detects this and uses the deterministic offline hashing embedder for
> retrieval, so RAG works without an OpenAI/Gemini key. If you later add an
> `OPENAI_API_KEY` and want higher-quality retrieval, set
> `EMBEDDING_BACKEND=provider`.

Install the real-backend extras:

```bash
cd backend
uv sync --extra dev --extra providers --extra vector   # add --extra ml for cross-encoder/CLIP
```

---

## 3. Run the backend

```bash
cd backend
uv run uvicorn app.main:app --reload --env-file ../.env --host 0.0.0.0 --port 8000
curl http://localhost:8000/health      # expect "demo_mode": false
```

If `/health` shows `"demo_mode": false`, your keys loaded and you're talking to
real Shopify.

---

## 4. Start the ngrok tunnel

First-time only — register your authtoken (from
[dashboard.ngrok.com](https://dashboard.ngrok.com)):

```bash
ngrok config add-authtoken <your-ngrok-authtoken>
```

Then, in a **second terminal**:

```bash
ngrok http 8000
```

ngrok prints a public HTTPS URL:

```
Forwarding   https://abc123.ngrok-free.app -> http://localhost:8000
```

Copy that URL — call it **`$NGROK`**. Verify it reaches your backend:

```bash
curl https://abc123.ngrok-free.app/health
```

> ⚠️ **Free ngrok URLs change every restart.** Keep this terminal running. If the
> URL rotates, re-run the webhook registration (step 6) with the new URL.

---

## 5. Import the catalog (one-time full sync)

Pull your dev store's products into the RAG index via Shopify Bulk Operations:

```bash
cd backend
uv run python - <<'PY'
import asyncio
from app.config import get_settings
from app.services.container import build_container

async def main():
    c = build_container(get_settings())
    await c.bootstrap()                       # seed the knowledge base (FAQs, policies)
    n = await c.catalog.full_import()         # live Shopify bulk import of products
    print("indexed product chunks:", n)

asyncio.run(main())
PY
```

Now product questions and recommendations use your **real** catalog. Test it:

```bash
curl -N -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"do you have any shirts under $50?"}'
```

> If you haven't loaded products into Acme Threads yet (the catalog is empty),
> this returns nothing useful — reconnect the Shopify connector first so I can
> create the 20 products with images, then re-run this import.

---

## 6. Register Shopify webhooks → your ngrok URL

This is what keeps the index fresh: when you edit a product in Shopify, it pings
your local backend through ngrok and re-indexes. Run this once (re-run if the
ngrok URL changes):

```bash
NGROK=https://abc123.ngrok-free.app
STORE=acme-threads.myshopify.com
TOKEN=shpat_...                              # SHOPIFY_ADMIN_API_TOKEN

for TOPIC in PRODUCTS_CREATE PRODUCTS_UPDATE PRODUCTS_DELETE INVENTORY_LEVELS_UPDATE; do
  curl -s -X POST "https://$STORE/admin/api/2025-01/graphql.json" \
    -H "X-Shopify-Access-Token: $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { webhookSubscriptionCreate(topic: $TOPIC, webhookSubscription: { callbackUrl: \\\"$NGROK/webhooks/shopify\\\", format: JSON }) { userErrors { message } webhookSubscription { id } } }\"}"
  echo
done
```

---

## 7. Test the end-to-end webhook flow

1. In the Shopify admin, **edit a product** (change its title or description) and
   save.
2. Watch the backend logs — you should see a verified webhook and a re-index:
   ```
   {"event":"request","path":"/webhooks/shopify","status":200,...}
   {"event":"reindex_product","product_id":"gid://shopify/Product/...","chunks":1}
   ```
3. Ask the bot about the changed product — the new content is reflected.

If you instead see `{"event":"webhook_unverified"}` with a `401`, your
`SHOPIFY_WEBHOOK_SECRET` doesn't match the app's **API secret key** — fix it in
`.env` and restart the backend.

---

## 8. (Optional) Embed the widget on the dev storefront

To test the chat widget on the real store, pointing at your local backend via
ngrok:

1. Build the widget: `cd widget && npm run build`.
2. Deploy the theme app extension: `cd shopify-app && shopify app deploy`.
3. In the dev store's **theme editor → App embeds**, enable the widget and set
   the **API base URL** to your **`$NGROK`** URL.
4. Make sure `CORS_ORIGINS` in `.env` includes
   `https://acme-threads.myshopify.com`, then restart the backend.

> Your dev store storefront is **password-protected** (dev stores can't go fully
> public without a paid plan). That's fine — preview the storefront as the
> logged-in owner via **Online Store → Themes → Preview**; the widget works there.

---

## 9. (Optional) Test live order tools

Order, tracking, and stock are resolved **live** at answer time — never from the
index. To test:

1. Add `read_orders` + `read_fulfillments` scopes to the custom app
   (step 1.3) and **reinstall** to refresh the token.
2. Create a test order in the dev store.
3. Ask:

```bash
curl -N -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"where is my order #1001, email customer@example.com"}'
```

The bot verifies the email against the order before returning anything; a
mismatch returns a uniform "couldn't verify" message with no data leak. Keep
`RETURNS_ENABLED=false` unless you've granted return scopes and want to test
writes.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/health` shows `"demo_mode": true` | `.env` still has `DEMO_MODE=true`, or you didn't pass `--env-file ../.env`. |
| `401` on webhooks (`webhook_unverified`) | `SHOPIFY_WEBHOOK_SECRET` ≠ the app's **API secret key**. |
| `403` / scope errors from Shopify | Missing scope; add it in the app's Configuration tab and **reinstall**. |
| Admin API token lost | It's shown once — uninstall/reinstall the app to mint a new one. |
| ngrok URL stopped working | Free URLs rotate on restart; re-run step 6 with the new URL. |
| Catalog questions return nothing | Run the import (step 5); confirm products exist in the store and `read_products` is granted. |
| Provider/auth error after `DEMO_MODE=false` | Set `GROQ_API_KEY` (or another provider key) and install `.[providers]`. |
| `THROTTLED` errors in logs | Normal under load; the client backs off automatically. |
| ngrok browser warning page | Add header `ngrok-skip-browser-warning: 1` when testing via curl, or use a paid ngrok domain. |

---

## Quick reference: full env diff to go live

```diff
- DEMO_MODE=true
+ DEMO_MODE=false

  LLM_DEFAULT_PROVIDER=groq
  GROQ_API_KEY=gsk_...                       # already set
+ EMBEDDING_BACKEND=auto

+ SHOPIFY_STORE_DOMAIN=acme-threads.myshopify.com
+ SHOPIFY_ADMIN_API_TOKEN=shpat_...
+ SHOPIFY_WEBHOOK_SECRET=...                 # API secret key
  SHOPIFY_API_VERSION=2025-01

+ CORS_ORIGINS=https://acme-threads.myshopify.com,http://localhost:5173
```
