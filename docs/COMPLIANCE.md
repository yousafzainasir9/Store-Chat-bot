# Privacy & compliance

## Principles
- **Data minimization:** the bot is anonymous unless a customer verifies an order
  (email + order #). PII is redacted from logs and handoff payloads (`redact_pii`).
- **AI disclosure:** every widget conversation shows "You're chatting with an AI
  assistant."
- **Grounded-only:** no fabricated prices, stock, or policies; low confidence →
  human handoff.

## Data subject rights (GDPR / CCPA)
All under the admin-protected `/admin/privacy/*` surface:

- **Export:** `GET /admin/privacy/export/{conversation_id}` → machine-readable
  copy of the conversation's stored data.
- **Erasure:** `DELETE /admin/privacy/conversation/{conversation_id}` → deletes
  the conversation and its feedback.
- **Retention:** `POST /admin/privacy/purge-expired` deletes conversations older
  than `DATA_RETENTION_DAYS` (default 365). Schedule it daily.

## Identity verification
Order, tracking, fulfillment, and return actions require the email on the order;
a mismatch returns a uniform "couldn't verify" response that leaks nothing about
whether the order exists.

## Prompt-injection defense
Untrusted user input is screened (`app/core/guardrails.py`); detected injections
route to handoff and never trigger a tool. Regression coverage lives in
`tests/test_injection_redteam.py`. System instructions are non-overridable and
order/return actions are deterministically routed (not model-decided).

## Secrets & transport
Secrets only via env / PaaS secret manager (`.env` git-ignored; gitleaks in CI).
HTTPS only; strict CORS to the storefront + admin origins; security headers on
every response.
