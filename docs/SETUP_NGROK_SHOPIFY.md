# Connect the chatbot to your Shopify store (with ngrok)

This guide takes you from nothing to a **working AI chatbot answering questions
about your real Shopify store** — running on your own computer, connected to the
store through a secure [ngrok](https://ngrok.com) tunnel.

It's written so you **don't need to be a developer**. You'll copy a few values,
paste them into one file, and run a handful of commands exactly as written.
After each step there's a **"✅ What you should see"** check so you always know
it worked before moving on.

> **Your store for this guide:** `acme-threads.myshopify.com`
> **Your AI provider:** Groq (already set up in your `.env`).

---

## What you'll have at the end

- The chatbot running at `http://localhost:8000` on your computer.
- It knows your 20 products, prices, sizes, and policies.
- A public web address (from ngrok) so Shopify can talk to it.
- Live updates: edit a product in Shopify and the bot knows within seconds.

Total time: about **20–30 minutes** the first time.

---

## Before you start: install two free tools

You only need these two. Click each link, download, and install like any normal
app.

1. **Docker Desktop** — runs the chatbot for you so you don't have to install
   Python or anything else. Get it at <https://www.docker.com/products/docker-desktop/>.
   After installing, **open Docker Desktop once** and leave it running (you'll
   see a whale icon in your menu bar / system tray).
2. **ngrok** — creates the secure public address. Get it at
   <https://ngrok.com/download> and create a free account.

You'll also open a **Terminal** (Mac: press ⌘+Space, type "Terminal", Enter.
Windows: Start menu → type "PowerShell", Enter). Every command below is typed
there, one line at a time, pressing Enter after each.

> Whenever a command starts with `cd`, it means "go into this folder." Replace
> the path with wherever you saved this project.

---

## Part A — Get your two Shopify keys

The chatbot needs permission to read your store. You grant it by making a
**custom app** inside Shopify. This is just clicking through a settings page.

1. Go to **<https://admin.shopify.com/store/acme-threads/settings/apps/development>**.
2. If you see a button **Allow custom app development**, click it (and confirm).
3. Click **Create an app** → name it `Support Chatbot` → **Create app**.
4. Click the **Configuration** tab → under *Admin API integration* click
   **Configure**. Tick these boxes, then **Save**:
   - `read_products`
   - `read_inventory`
5. Click the **API credentials** tab → **Install app** → **Install**.
6. On that same page, copy your **two keys** somewhere safe for a minute:
   - **Admin API access token** — click **Reveal token once**. It starts with
     `shpat_`. ⚠️ You can only see it **once**, so copy it now.
   - **API secret key** — copy this too.

✅ **What you should see:** an "Admin API access token" beginning `shpat_…` and
an "API secret key". You now have both keys.

---

## Part B — Put the keys in the `.env` file

`.env` is the chatbot's settings file. It's in the **main project folder**
(the same folder as this `docs` folder). Open it with any text editor
(Notepad, TextEdit, VS Code).

Find these lines and set them to look exactly like this — pasting **your** keys
where shown:

```bash
# Turn OFF demo mode so it uses your real store:
DEMO_MODE=false

# Your AI provider (already set — leave as-is):
LLM_DEFAULT_PROVIDER=groq
GROQ_API_KEY=gsk_...            # already filled in
EMBEDDING_BACKEND=auto

# Your Shopify store and the two keys from Part A:
SHOPIFY_STORE_DOMAIN=acme-threads.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_...     # paste the Admin API access token
SHOPIFY_WEBHOOK_SECRET=...            # paste the API secret key
SHOPIFY_API_VERSION=2025-01

# Lets the chat widget load on your storefront:
CORS_ORIGINS=https://acme-threads.myshopify.com,http://localhost:5173
```

**Save the file.**

> You do **not** need to touch the database or Qdrant lines — Docker sets those
> up for you automatically.

✅ **What you should see:** the file saved with `DEMO_MODE=false` and your two
`shpat_…` / secret values filled in. No line should still say `...`.

---

## Part C — Start the chatbot

In your Terminal, go into the project folder and start everything with one
command:

```bash
cd path/to/Store-Chat-bot
docker compose up
```

The first time, Docker downloads and builds things — this can take **5–10
minutes**. Leave it running. When it's ready you'll see log lines mentioning
`Uvicorn running on http://0.0.0.0:8000`.

Open a **second** Terminal window and check it's alive:

```bash
curl http://localhost:8000/health
```

✅ **What you should see:** a line containing `"demo_mode": false`. That means
the chatbot started and is pointed at your real store.

> Keep the first Terminal (with `docker compose up`) running the whole time.
> To stop everything later, click that window and press **Ctrl+C**.

---

## Part D — Load your products into the chatbot

The bot starts empty. This one command pulls your whole catalog in:

```bash
docker compose exec api python scripts/import_catalog.py
```

✅ **What you should see:** a message like
`Indexed N knowledge-base chunk(s) and M product chunk(s).` `M` should be a
number in the dozens (you have 20 products with variants).

Quick test — ask the bot something:

```bash
curl -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d "{\"message\":\"what shirts do you have?\"}"
```

✅ **What you should see:** a reply that mentions real products from your store
(e.g. the Oxford Shirt, Polo, or T-shirt), not "I don't have that information."

---

## Part E — Give the chatbot a public address (ngrok)

Shopify lives on the internet and can't reach `localhost` on your computer.
ngrok creates a public web address that forwards to it.

First time only, connect ngrok to your account (copy your token from
<https://dashboard.ngrok.com> → *Your Authtoken*):

```bash
ngrok config add-authtoken YOUR_TOKEN_HERE
```

Then start the tunnel (in a **third** Terminal window):

```bash
ngrok http 8000
```

ngrok shows a line like:

```
Forwarding   https://abc123.ngrok-free.app -> http://localhost:8000
```

Copy that `https://abc123.ngrok-free.app` address.

✅ **What you should see:** a `https://…ngrok-free.app` address. Paste it into a
browser with `/health` on the end (e.g.
`https://abc123.ngrok-free.app/health`) — it should show the same
`"demo_mode": false`.

> ⚠️ The free ngrok address **changes every time you restart ngrok.** If it
> changes, just re-run Part F with the new address.

---

## Part F — Connect Shopify's live updates (webhooks)

This makes the bot update itself when you change a product. Run this one
command, pasting **your** ngrok address from Part E:

```bash
docker compose exec api python scripts/register_webhooks.py https://abc123.ngrok-free.app
```

✅ **What you should see:** four lines each ending in `[ok]` (or `[skip]` if you
ran it before):

```
  [ok]   PRODUCTS_CREATE
  [ok]   PRODUCTS_UPDATE
  [ok]   PRODUCTS_DELETE
  [ok]   INVENTORY_LEVELS_UPDATE
```

---

## Part G — Test the whole thing end to end

1. In Shopify admin, open any product and change its description, then **Save**.
2. Look at your first Terminal (the `docker compose up` one). Within a few
   seconds you should see a line like `reindex_product`.
3. Ask the bot about that product again (the `curl … /chat` command from Part
   D) — your change is reflected.

✅ **If that worked, you're done.** The chatbot is live, knows your catalog, and
stays in sync with your store.

---

## Everyday use after the first setup

You don't repeat the whole guide each time. To start working again:

1. Open Docker Desktop (whale icon running).
2. Terminal 1: `cd path/to/Store-Chat-bot` then `docker compose up`.
3. Terminal 2: `ngrok http 8000`.
4. If the ngrok address changed, re-run **Part F** with the new one.

To stop: press **Ctrl+C** in the `docker compose up` window.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| `curl … /health` shows `"demo_mode": true` | `.env` still has `DEMO_MODE=true`, or you didn't save it. Fix it and run `docker compose restart api`. |
| `docker: command not found` | Docker Desktop isn't installed or isn't running. Open the app and wait for the whale icon. |
| Import says "Missing Shopify credentials" | A key in `.env` is blank or misspelled. Re-check Part B, then re-run. |
| Webhook step shows `[FAIL]` | The ngrok address is wrong/expired, or the token is missing `read_products`. Re-copy the ngrok URL and re-run. |
| `/chat` replies "I don't have that information" | The catalog import (Part D) didn't run or returned 0. Re-run it and check it reports a product count. |
| ngrok shows a warning page in the browser | Normal for the free plan when visiting in a browser; it doesn't affect Shopify or the chatbot. |
| The first `docker compose up` is very slow | Normal the first time (it's downloading). Later starts take seconds. |

---

## Advanced: run it without Docker

If you'd rather not use Docker and you're comfortable with a terminal, you can
run the backend directly with [uv](https://docs.astral.sh/uv/):

```bash
cd backend
uv sync --extra dev --extra providers --extra vector
# Start Qdrant/Postgres/Redis so the import and server share one index:
docker compose up -d postgres redis qdrant
uv run uvicorn app.main:app --reload --env-file ../.env --host 0.0.0.0 --port 8000
# In another terminal:
uv run python scripts/import_catalog.py
uv run python scripts/register_webhooks.py https://abc123.ngrok-free.app
```

Everything else (ngrok, testing, webhooks) is identical to the Docker steps
above.

> Note: the catalog import and the running server must share the **same vector
> store**, which is why Qdrant is started even in this mode. Skipping it would
> import into a throwaway in-memory index the server can't see.
