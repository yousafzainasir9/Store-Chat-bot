# Local setup with tests (demo mode)

Run the **entire system on your machine with no API keys and no external
services**. This uses `DEMO_MODE=true`, where the LLM, embeddings, vector store,
Postgres, and Shopify are all replaced by deterministic in-process stand-ins.

Outcome: a working `/chat` (and admin, widget) plus a green test suite and eval.

> Prerequisites: Python 3.12+, Node 18+. (Docker optional.) See
> [SETUP.md](./SETUP.md#prerequisites-all-paths).

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

## 2. Backend — Option A: virtualenv (recommended for development)

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # app + lint/type/test toolchain

# Run the API (reads ../.env)
uvicorn app.main:app --reload --env-file ../.env
```

API: http://localhost:8000 · Swagger UI: http://localhost:8000/docs ·
Health: http://localhost:8000/health

## 2. Backend — Option B: Docker Compose

From the repo root:

```bash
docker compose up --build
```

This starts the API plus Postgres, Redis, and Qdrant. In demo mode the API uses
in-process stores and simply ignores those services (they're there for the live
path). The API is on http://localhost:8000.

---

## 3. Run the tests, eval, and quality gates

```bash
cd backend
source .venv/bin/activate

pytest                                 # full suite (136 tests)
python -m eval.run_eval --k 5          # RAG evaluation (106 pairs) + gate

ruff check app tests eval scripts      # lint + import sort
black --check app tests eval scripts   # formatting
mypy app                               # strict type check
```

Expected: `pytest` all green; eval prints `All gates passed.`

Install the pre-commit hooks so these run automatically on each commit:

```bash
pip install pre-commit && pre-commit install
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
| `StrEnum` / `datetime.UTC` import error | You're on Python < 3.12. Use 3.12+. |
| `uvicorn: command not found` | Activate the venv; `pip install -e ".[dev]"`. |
| `.env` not picked up | Run uvicorn from `backend/` with `--env-file ../.env`, or put `.env` in `backend/`. |
| Port 8000 in use | `uvicorn ... --port 8001` and update the widget/admin API base. |
| Admin returns 401 locally | You set `ADMIN_API_KEY` — either send `Authorization: Bearer <key>` or unset it for demo. |

When this all works, move on to **[SETUP_NGROK_SHOPIFY.md](./SETUP_NGROK_SHOPIFY.md)**
to test against a real Shopify store, or **[SETUP_LIVE.md](./SETUP_LIVE.md)** to
deploy.
