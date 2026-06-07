# Testing, evaluation & CI

## 1. Test suite

28 test files under `backend/tests/` (136 tests), all runnable **offline** (no
API keys, no services) via the demo-mode stand-ins.

```bash
cd backend
pytest                      # full suite + coverage
pytest tests/test_chat_api.py -q
```

| Area | Files |
|---|---|
| Ops / config / prompts | `test_health.py`, `test_config.py`, `test_prompts.py` |
| RAG pipeline | `test_chunking.py`, `test_rag_pipeline.py` |
| Guardrails / injection | `test_guardrails.py`, `test_injection_redteam.py` |
| Chat / streaming | `test_chat_api.py`, `test_chat_tools.py`, `test_chat_recommend.py` |
| Orders / verification / router | `test_order_tools.py`, `test_verification.py`, `test_router.py` |
| Shopify catalog | `test_shopify_mapping.py`, `test_shopify_webhooks.py`, `test_bulk.py`, `test_catalog_sync.py`, `test_throttle.py`, `test_webhook_endpoint.py` |
| Recommendations | `test_constraints.py`, `test_recommendations.py` |
| Visual search | `test_visual_search.py`, `test_visual_api.py` |
| Widget / abuse / budget | `test_widget_backend.py`, `test_budget.py` |
| Admin | `test_admin_content.py`, `test_admin_dashboard.py` |
| Eval gate | `test_eval_gate.py` |

Notable coverage: the **prompt-injection red-team** (`test_injection_redteam.py`)
asserts 12 adversarial inputs are detected and routed to handoff and that the
system prompt never leaks; identity verification blocks order lookups with a
mismatched email; returns are gated by feature flags; the session budget hands
off when exhausted.

## 2. Evaluation harness

`backend/eval/` scores the RAG stack against a labeled dataset.

```bash
cd backend
python -m eval.run_eval --k 5
```

- **Dataset**: `eval/dataset.jsonl` — 106 pairs across FAQ, shipping, returns,
  size, care, product, recommendation, out-of-scope, and injection. Each pair:
  `{id, intent, question, expected_source, expect_answer, must_include}`.
- **Retrieval metrics**: recall@k and MRR, **before vs. after rerank** (shows the
  rerank lift).
- **Answer metrics**: grounded-answer accuracy (cited + contains the expected
  substring) and refusal correctness (out-of-scope/injection correctly handed
  off).
- **Gate thresholds** (CLI flags, offline-calibrated floors): `--min-recall 0.85`
  `--min-answer 0.90` `--min-refusal 0.90`. Exit code non-zero on failure.

### Eval-gated prompt deploys
`tests/test_eval_gate.py` runs the eval **in-process as a unit test** and asserts
the thresholds, that rerank doesn't hurt recall, and that the set has ≥100 cases.
A prompt change that regresses quality fails CI here, so it can't deploy
(DEVELOPMENT_PLAN.md §9).

> **Important caveat.** Offline metrics use deterministic stand-ins (hashing
> embedder, overlap reranker, fake LLM). They prove wiring and logic, not real
> semantic quality. When the production embedding model + cross-encoder are
> connected, **re-baseline** the eval, **raise** the thresholds, and
> **recalibrate** `RAG_MIN_CONFIDENCE` to the new score scale.

## 3. Load test

```bash
python -m scripts.loadtest --url http://localhost:8000 --concurrency 20 --requests 500
```
Drives concurrent `/chat` requests and reports throughput + p50/p95/p99 latency,
compared against the SLO (p95 first-token < 2.5s).

## 4. Quality gates (local + CI)

```bash
cd backend
ruff check app tests eval scripts     # lint + import sort
black --check app tests eval scripts  # formatting
mypy app                              # strict typing
pytest                                # tests
python -m eval.run_eval --k 5         # eval gate
pre-commit install                    # run the above on commit (+ gitleaks)
```

CI (`.github/workflows/ci.yml`) runs, on every push and PR:
**lint → format-check → `mypy --strict` → tests → eval gate**, plus **gitleaks**
secret scanning. Frontends are built and type-checked separately
(`npm run build` in `widget/` and `admin/`).
