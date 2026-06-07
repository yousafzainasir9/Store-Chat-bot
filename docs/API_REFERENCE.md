# API reference

Base URL: the deployed backend origin (e.g. `https://api.example.com`).
Interactive docs (non-production): `GET /docs` (Swagger UI), `GET /openapi.json`.

All responses include security headers and an `X-Request-ID`. CORS is restricted
to the configured origins (`CORS_ORIGINS`).

## Authentication

| Surface | Auth |
|---|---|
| `/chat`, `/search/visual` | Optional widget session token via `X-Widget-Token` (enforced only when `WIDGET_REQUIRE_TOKEN=true`). Per-IP rate limited. |
| `/widget/session` | None (mints a token). |
| `/webhooks/shopify` | Shopify HMAC (`X-Shopify-Hmac-Sha256`) over the raw body. |
| `/admin/*` | `Authorization: Bearer <ADMIN_API_KEY>`. |
| `/health`, `/ready`, `/metrics`, `/ops/freshness` | None. |

---

## Public chat

### `POST /chat`
Stream a grounded answer over **Server-Sent Events**.

**Request body**
```json
{
  "message": "How long does shipping take?",
  "conversation_id": "optional-existing-id",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
}
```
- `message` (required, 1–8000 chars).
- `conversation_id` (optional) — omit to start a new conversation.
- `history` (optional, ≤20 turns) — prior turns for multi-turn context.

**Response** — `text/event-stream`. See the [SSE event protocol](#sse-event-protocol).

**Status / headers**: `200` stream; `422` validation error; `429` rate limited;
`401` if widget token required and missing/invalid.

```bash
curl -N -X POST $BASE/chat -H 'Content-Type: application/json' \
  -d '{"message":"How long does shipping take?"}'
```

### `POST /feedback`
Record thumbs up/down on an assistant message (feeds the content-gap loop).

```json
{ "conversation_id": "c123", "message_id": "m456", "value": "up", "comment": "optional" }
```
`value` ∈ `{up, down}`. Returns `{ "status": "ok", "feedback_id": "..." }`.

### SSE event protocol

`POST /chat` emits these events in order:

| Event | Data | Meaning |
|---|---|---|
| `meta` | `{conversation_id, message_id, disclosure}` | Sent first; `disclosure` is the AI-disclosure string. |
| `token` | raw text delta | Streamed answer chunk (zero or more). |
| `citations` | JSON array of source labels | Sources the answer is grounded in. |
| `handoff` | `{text, reason}` | Sent instead of an answer; `reason` ∈ `low_confidence`, `out_of_scope`, `injection`, `budget`. |
| `done` | `{message_id, confidence}` | Terminal event. |

A turn that needs identity verification streams `token`s asking for the order
number + email, then `done` (no `handoff`).

---

## Visual search

### `POST /search/visual`
`multipart/form-data`. Find nearest in-catalog, in-stock products for an image.

**Fields**: `image` (file, required, ≤8 MB), and optional `category`, `color`,
`size`, `gender`, `budget_max`.

**Response**
```json
{ "count": 2, "results": [
  { "product_id": "...", "title": "Navy Linen Jacket", "price": 69.0, "url": "...", "reason": "..." }
] }
```
`503` if visual search is disabled; `400` empty upload; `413` too large.

```bash
curl -X POST $BASE/search/visual -F image=@jacket.jpg -F category=Jacket -F budget_max=200
```

---

## Widget session

### `POST /widget/session`
Mint a short-lived signed token. Returns `{ token, expires_at, required }`.
When `WIDGET_SECRET` is unset, returns `{token: null, required: false}` (no-op).
The widget sends the token back as `X-Widget-Token`.

---

## Shopify webhooks

### `POST /webhooks/shopify`
Headers: `X-Shopify-Topic`, `X-Shopify-Hmac-Sha256`. Body: raw Shopify payload.

- Verifies HMAC (`401` if invalid).
- Routes `products/create|update` → reindex, `products/delete` → delete,
  `inventory_levels/*` → acknowledge.
- Dispatches work to the job queue and returns `{ "status": "ok", "action": "..." }`.

---

## Admin API (`/admin/*`, bearer auth)

### Content
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/content` | List editable FAQs/policies. |
| `POST` | `/admin/content` | Create (`title`, `body`, `category`, `source`, `locale`) → **re-indexes immediately**. `201`. |
| `PATCH` | `/admin/content/{id}` | Update title/body/category → re-indexes. |
| `DELETE` | `/admin/content/{id}` | Delete + de-index. |

### Conversations & feedback
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/conversations?limit=N` | Recent conversations (preview, message count, handoff flag). |
| `GET` | `/admin/conversations/{id}` | Full transcript with per-message confidence + handoff reason. |
| `GET` | `/admin/feedback` | All feedback entries. |

### Content gaps
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/gaps` | Clustered unanswered questions (count + examples), ranked. |
| `POST` | `/admin/gaps/create-faq` | One-click FAQ from a gap (`title`, `body`) → re-indexes. `201`. |

### Analytics & posture
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/analytics` | Volume, deflection/handoff rate, confidence, feedback split, token cost/conversation, latency. |
| `GET` | `/admin/freshness` | Resolved catalog freshness posture. |
| `GET` | `/admin/llm` | LLM fallback-chain status (per-provider availability + cooldown). |

### Privacy (GDPR/CCPA)
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/privacy/export/{conversation_id}` | Machine-readable export of a conversation. |
| `DELETE` | `/admin/privacy/conversation/{conversation_id}` | Erase a conversation + its feedback. |
| `POST` | `/admin/privacy/purge-expired` | Purge conversations older than `DATA_RETENTION_DAYS`. |

`401` without a valid bearer token; `403` if the admin API isn't configured in
production; `404` for missing resources.

---

## Ops

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness (cheap, no external deps). |
| `GET` | `/ready` | Readiness — which datastores are configured. |
| `GET` | `/metrics` | In-process metric snapshot + declared SLO targets. |
| `GET` | `/ops/freshness` | Read-only catalog freshness posture. |
