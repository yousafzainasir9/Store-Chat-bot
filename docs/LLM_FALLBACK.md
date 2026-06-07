# LLM fallback chain (multi-model failover with cooldown)

Stack multiple LLM providers/models/keys into a **priority-ordered chain**. Each
request goes to the highest-priority *available* provider. When a provider
returns a rate-limit / quota error (e.g. a Groq free-tier daily cap), it is
**disabled for a cooldown window** (default **24 hours** — the assumed refresh
period) and traffic fails over to the next provider. When the window elapses the
provider is automatically re-enabled.

Typical use: three Groq free-tier keys/models, with OpenAI as a final paid
fallback so the bot never goes dark.

## How it works

```
request ─▶ [priority 1] ──429?──▶ disable 24h ─▶ [priority 2] ──429?──▶ … ─▶ [priority N]
              │ available?                                                      │
              └────────────── serve the response ◀────────────────────────────┘
```

- **Ordering**: lower `priority` is tried first.
- **Failover**: any rate-limit/quota error (HTTP 429, "rate limit", "quota",
  "insufficient_quota", or a provider `RateLimitError`) parks the provider for
  `LLM_COOLDOWN_SECONDS` and moves on. Other (transient) errors use a short 60s
  cooldown.
- **Recovery**: cooldown is checked per call; once `now ≥ disabled_until` the
  provider is available again — no restart needed.
- **Streaming**: failover happens before the first token; once a provider starts
  streaming, its response is passed through.
- **Embeddings**: the chain skips providers that don't support embeddings (Groq
  has no embeddings API) and uses the first embedding-capable provider. Keep at
  least one OpenAI/Gemini entry if the chain also serves retrieval embeddings,
  or run embeddings on a dedicated provider.

State is **in-memory per process**. For a shared cooldown across replicas, back
the registry with Redis behind the same interface.

Code: `app/llm/fallback.py` (chain + `CooldownRegistry`), `app/llm/groq_provider.py`
(Groq, OpenAI-compatible), `app/llm/factory.py` (builds the chain from settings).

## Configuration

Define the chain as a JSON list in `LLM_CHAIN`. Each entry:

| Field | Required | Meaning |
|---|---|---|
| `provider` | yes | `groq` \| `openai` \| `gemini`. |
| `model` | recommended | Model id for that provider (defaults per provider if omitted). |
| `priority` | recommended | Lower = tried first. |
| `name` | optional | Label shown in logs and the status endpoint. |
| `api_key` | optional | The key inline (avoid; prefer `api_key_env`). |
| `api_key_env` | optional | Name of another env var holding the key. |
| `base_url` | optional | Override the API base URL (OpenAI-compatible providers). |

Plus:

| Variable | Default | Meaning |
|---|---|---|
| `LLM_COOLDOWN_SECONDS` | `86400` | Cooldown after a rate-limit (24h). |
| `GROQ_API_KEY` / `GROQ_API_KEY_1..3` / `OPENAI_API_KEY` | — | The keys referenced by `api_key_env`. |

### Example — three Groq keys, then OpenAI

```bash
GROQ_API_KEY_1=gsk_aaa
GROQ_API_KEY_2=gsk_bbb
GROQ_API_KEY_3=gsk_ccc
OPENAI_API_KEY=sk-...
LLM_COOLDOWN_SECONDS=86400

LLM_CHAIN='[
  {"provider":"groq","name":"groq-8b","model":"llama-3.1-8b-instant","api_key_env":"GROQ_API_KEY_1","priority":1},
  {"provider":"groq","name":"groq-70b","model":"llama-3.3-70b-versatile","api_key_env":"GROQ_API_KEY_2","priority":2},
  {"provider":"groq","name":"groq-spare","model":"llama-3.1-8b-instant","api_key_env":"GROQ_API_KEY_3","priority":3},
  {"provider":"openai","name":"openai","model":"gpt-4o-mini","api_key_env":"OPENAI_API_KEY","priority":4}
]'
```

> The chain is only active when `DEMO_MODE=false`. In demo/test the deterministic
> Fake provider is always used. When `LLM_CHAIN` is empty, the single-provider
> path (`LLM_DEFAULT_PROVIDER` / `LLM_DEFAULT_MODEL`) is used.

## Monitoring

- **Status**: `GET /admin/llm` (admin bearer auth) returns each provider's
  availability and `disabled_until` timestamp — no secrets.
  ```json
  { "chain": true, "providers": [
    {"id":"groq-8b-0","label":"groq-8b","provider":"groq","priority":1,"available":false,"disabled_until":1718900000.0},
    {"id":"openai-3","label":"openai","provider":"openai","priority":4,"available":true,"disabled_until":null}
  ]}
  ```
- **Logs**: `llm_provider_disabled` (with reason + cooldown) on failover;
  `llm_chain_built` at startup.
- **Metrics**: `llm_provider_used_total.<id>` and
  `llm_provider_cooldown_total.{rate_limit,error}`.

## Notes & caveats

- The 24h cooldown is an *assumption* about when the limit refreshes; tune
  `LLM_COOLDOWN_SECONDS` to your provider's actual reset window (Groq free-tier
  limits are typically per-minute and per-day — set this to the per-day reset if
  you're hitting the daily cap).
- Mixing models changes answer style; keep an eye on the eval/groundedness when a
  lower-quality fallback takes over.
- Per-process cooldown means each replica learns independently; use Redis-backed
  state for a global view at scale.
