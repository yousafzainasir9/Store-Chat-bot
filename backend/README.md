# Store Chat Bot — backend

FastAPI backend for the Fashion & Clothing AI customer-support chatbot:
grounded RAG chat, Shopify catalog sync + live order/stock/return tools, fashion
recommendations, visual search, an admin API, and the abuse/compliance layer.

Full documentation is in [`../docs/`](../docs/) — start at
[`../docs/README.md`](../docs/README.md). For setup see
[`../docs/SETUP.md`](../docs/SETUP.md).

## Quick start (uv)

```bash
cd backend
uv sync --extra dev                      # create .venv + install deps + toolchain
cp ../.env.example ../.env               # demo mode by default (no keys needed)
uv run uvicorn app.main:app --reload --env-file ../.env
```

API: http://localhost:8000 · Docs: http://localhost:8000/docs · Health: `/health`

## Quality gates

```bash
uv run ruff check app tests eval scripts
uv run black --check app tests eval scripts
uv run mypy app
uv run pytest
uv run python -m eval.run_eval --k 5
```

## Layout

```
app/            FastAPI application package
  api/          HTTP routes + deps (thin handlers)
  core/         Orchestrator, router, guardrails, verification, prompts
  llm/          LLMProvider interface + adapters + fallback chain
  rag/          Chunk/embed/store/retrieve/rerank + visual search
  shopify/      Client, bulk import, mapping, sync, orders, webhooks
  recommendations/ constraints + recommendation service
  services/     Composition root + admin services + jobs + seed
  ...           handoff, repositories, models, schemas, compliance, billing, observability
eval/           Evaluation harness + dataset (106 pairs)
scripts/        Load-test script
seed/           Seed knowledge base (FAQs, policies, size guide)
tests/          Test suite (146 tests)
```

See [`../docs/CODE_STRUCTURE.md`](../docs/CODE_STRUCTURE.md) for the full
file-by-file reference.
