# Operations runbook

## Dashboards & signals
- **Analytics:** `GET /admin/analytics` (or the admin dashboard Overview) —
  volume, deflection, handoff rate, confidence, token cost/conversation, latency.
- **SLOs (§8.3):** p95 chat first-token < 2.5s; answer availability ≥ 99.5%;
  groundedness ≥ target; handoff rate within band.
- **Logs:** structured JSON; filter by `event` (`handoff`, `cost_anomaly`,
  `webhook_unverified`, `order_auth_failed`).

## Common alerts

| Signal | Likely cause | Action |
|---|---|---|
| `cost_anomaly` spike | abuse / injection loop | check IP rate limits; lower `PER_SESSION_TOKEN_BUDGET`; block IP |
| Handoff rate ↑ | content gap or retrieval regression | review `/admin/gaps`; add FAQs; check eval gate |
| p95 latency ↑ | provider slowness / cold vector store | check provider status; Qdrant health; scale out |
| `webhook_unverified` | wrong `SHOPIFY_WEBHOOK_SECRET` | rotate + re-register webhooks |
| Stale catalog answers | missed webhooks | run reconciliation sweep / full re-import |

## Routine tasks
- **Retention purge:** schedule `POST /admin/privacy/purge-expired` daily (or run
  the worker sweep) to enforce `DATA_RETENTION_DAYS`.
- **Re-index after bulk catalog edits:** trigger a full import.
- **Prompt change:** must pass the eval gate (`pytest tests/test_eval_gate.py`
  and `python -m eval.run_eval`) before deploy.

## Incident: Shopify outage
`FAILSAFE_ON_API_ERROR=true` makes order/stock tools decline + hand off rather
than guess. Verify the flag, then communicate degraded order-lookup status.

## Load test
```bash
python -m scripts.loadtest --url https://api.example.com --concurrency 20 --requests 500
```
Compares p95 first-token latency against the SLO.
