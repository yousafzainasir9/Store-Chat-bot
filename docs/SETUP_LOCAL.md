# Local setup with tests (demo mode)

Run the **entire system on your machine with no API keys and no external
services**. This uses `DEMO_MODE=true`, where the LLM, embeddings, vector store,
Postgres, and Shopify are all replaced by deterministic in-process stand-ins.

Outcome: a working `/chat` (and admin, widget) plus a green test suite and eval.

> Prerequisites: uv + Node 18+. (Docker optional.) uv fetches Python 3.12 for
> you. See [SETUP.md](./SETUP.md#prerequisites-all-paths).
>
> Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
> (Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`).

---

## 1. Get the code & environment file

```bash
git clone <your-repo-url> store-chat-bot
cd store-chat-bot
cp .env.example .env          # defaults are demo-mode; no edits needed
```

The default `.env` has `DEMO_MODE=true` and `ENVIRONMENT=development` — nothing
else is required for local use.

---

## 2. Backend — Option A: uv (recommended for development)

> ⚠️ The `pyproject.toml` is in **`backend/`**, not the repo root. Run `uv` from
> `backend/` (`cd backend`), or from the root use `uv --directory backend …`.
> Running `uv sync` from the repo root gives
> `error: No pyproject.toml found in current directory or any parent directory`.

```bash
cd backend
uv sync --extra dev                # creates .venv, installs deps + toolchain
# (uv auto-installs Python 3.12 if it's not already present)

# Run the API (reads ../.env)
uv run uvicorn app.main:app --reload --env-file ../.env
```

`uv run <cmd>` executes inside the project's `.venv` without manual activation.
Generate a lockfile once for reproducible installs: `uv lock` (commit `uv.lock`).

API: http://localhost:8000 · Swagger UI: http://localhost:8000/docs ·
Health: http://localhost:8000/health

## 2. Backend — Option B: Docker Compose

From the repo root:

```bash
# Core services (always): backend + widget + admin + datastores
docker compose up --build

# Full local demo: also run the sample storefront (profile "local")
docker compose --profile local up --build
```

This starts:
- **API** on http://localhost:8000 (Swagger at `/docs`),
- **Widget** on http://localhost:8082 — serves `widget.js`, the embeddable asset,
- **Admin** on http://localhost:8081 — the operations dashboard (connect with API
  base `http://localhost:8000`; leave the admin key blank in demo mode),
- **Sample store** on http://localhost:8080 *(only with `--profile local`)* — a
  mock store with the chat widget embedded (bottom-right), wired to the API, so
  you can try the bot end to end,
- **Postgres, Redis, Qdrant** (in demo mode the API uses in-process stores and
  ignores these; they're there for the live path).

### About the admin key

The **admin key** is the value of the `ADMIN_API_KEY` environment variable — a
single bearer token that protects every `/admin/*` endpoint (content/FAQ CRUD,
conversation review, content gaps, analytics, GDPR export/erase, and LLM-chain
status). The admin dashboard sends it as `Authorization: Bearer <key>` and stores
it in your browser's `localStorage`.

| Mode | `ADMIN_API_KEY` | Dashboard "Admin API key" field |
|---|---|---|
| **Demo / local dev** (default `.env`, `ENVIRONMENT=development`) | unset | **Leave blank** — admin routes are open in non-production for convenience. |
| **Locked-down local / production** | set to a long random string | Enter the same value you put in `.env`. |

In **production** (`ENVIRONMENT=production`) the key is **required** — the app
refuses to start without it, and unauthenticated `/admin/*` calls get `401`.

**Generate a strong key** and put it in `.env`:

```bash
# any of these:
python -c "import secrets; print(secrets.token_urlsafe(32))"
openssl rand -hex 32
```

```bash
# .env
ADMIN_API_KEY=PASTE_THE_GENERATED_VALUE_HERE
```

Then in the dashboard's connect screen enter **API base** `http://localhost:8000`
and that **admin key**. (Docker reads it via the api service's `env_file: .env`,
so rebuild/restart after changing it: `docker compose up -d --build api`.)

Notes:
- It is **auth, not user accounts** — one shared token. A real OAuth2/SSO login is
  the production upgrade path and slots in front of this token (see the auth
  dependency in `backend/app/api/admin_auth.py`).
- Treat it like a password: never commit it (`.env` is git-ignored); rotate it by
  changing `ADMIN_API_KEY` and restarting.
- It is unrelated to `WIDGET_SECRET` (widget session tokens) and to the Shopify
  tokens — each secures a different surface.

---

## 3. Run the tests, eval, and quality gates

```bash
cd backend
uv run pytest                               # full suite (146 tests)
uv run python -m eval.run_eval --k 5        # RAG evaluation (106 pairs) + gate

uv run ruff check app tests eval scripts    # lint + import sort
uv run black --check app tests eval scripts # formatting
uv run mypy app                             # strict type check
```

Expected: `pytest` all green; eval prints `All gates passed.`

Install the pre-commit hooks so these run automatically on each commit:

```bash
uv run pre-commit install
```

---

## 4. Smoke-test the chat API

```bash
# A grounded FAQ answer (streams SSE):
curl -N -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is your return policy?"}'

# Out-of-scope → handoff event:
curl -N -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is the capital of France?"}'

# A recommendation (demo synthetic catalog):
curl -N -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Can you recommend a dress under $100?"}'

# Visual search (any file stands in as the image in demo mode):
echo "Black Dress" > /tmp/q.txt
curl -X POST http://localhost:8000/search/visual \
  -F image=@/tmp/q.txt -F category=Dress
```

In demo mode the backend auto-loads the seed knowledge base (FAQs, shipping,
size guide) and a small **synthetic product catalog**, so product, recommend,
and visual-search flows all work offline.

---

## 5. Widget (embeddable chat) — local preview

```bash
cd widget
npm install
npm run dev        # Vite dev server, http://localhost:5173
```

The dev page (`widget/index.html`) mounts the widget and points it at
`http://localhost:8000`. Run the backend (step 2) alongside it.

To produce the shippable bundle:

```bash
npm run build      # type-check + build → dist/widget.js (~10 KB gzip)
```

---

## 6. Admin dashboard — local

```bash
cd admin
npm install
npm run dev        # http://localhost:5173
```

On the connect screen, enter:
- **API base URL**: `http://localhost:8000`
- **Admin API key**: leave blank in demo mode (admin auth is open in
  non-production when `ADMIN_API_KEY` is unset).

You'll see analytics, conversations, content management, and content gaps. Try
creating an FAQ in **Content & FAQs**, then ask the bot about it on `/chat` — it
re-indexes instantly.

To build:

```bash
npm run build      # → dist/
```

---

## 7. Common issues

| Symptom | Fix |
|---|---|
| `StrEnum` / `datetime.UTC` import error | Python < 3.12. `uv sync` pins 3.12 via `.python-version`. |
| `uvicorn: command not found` | Use `uv run uvicorn …`, or `uv sync --extra dev` first. |
| `.env` not picked up | Run uvicorn from `backend/` with `--env-file ../.env`, or put `.env` in `backend/`. |
| Port 8000 in use | `uvicorn ... --port 8001` and update the widget/admin API base. |
| Admin returns 401 locally | You set `ADMIN_API_KEY` — either send `Authorization: Bearer <key>` or unset it for demo. |

When this all works, move on to **[SETUP_NGROK_SHOPIFY.md](./SETUP_NGROK_SHOPIFY.md)**
to test against a real Shopify store, or **[SETUP_LIVE.md](./SETUP_LIVE.md)** to
deploy.
