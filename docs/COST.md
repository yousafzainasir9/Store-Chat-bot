# Cost estimate per 1,000 conversations

**Assumptions** (tune with real traffic): ~3 turns/conversation; ~2,500 input +
~350 output tokens/turn ⇒ ~7,500 input + ~1,050 output tokens/conversation.
Query embeddings are negligible; catalog (re)embedding is a separate periodic
cost; reranking adds a small per-query cost.

## Inference (LLM) per 1,000 conversations

| Model | Input $/1M | Output $/1M | ~Cost / 1k convos |
|---|---|---|---|
| **gpt-4o-mini** (default) | $0.15 | ~$0.60 | **~$1.75** |
| Gemini 2.5 Flash | $0.30 | $2.50 | ~$4.90 |
| Grok 3 Mini | $0.30 | $0.50 | ~$2.80 |
| gpt-4.1-mini (higher quality) | $0.40 | $1.60 | ~$4.70 |

Inference is roughly **$2–$5 per 1,000 conversations**.

## Embeddings & reranking
- `text-embedding-3-small` @ $0.02/1M — a rounding error per query.
- Full re-embed of 50k products (~20M tokens) ≈ **$0.40** per rebuild;
  incremental webhook re-indexing makes steady state trivial.
- At ~5k products (your catalog), a full re-embed is **a few cents**.
- Reranking adds cents–dollars per 1k depending on hosted vs. self-hosted.
- Image embeddings (visual search) are a one-time per-product cost at index time.

## Infrastructure (fixed monthly)
PaaS + managed Postgres + Redis + Qdrant Cloud ≈ **$70–$250/month** at the start,
amortizing over volume.

## All-in rule of thumb
**~$3–$8 per 1,000 conversations**, trending down as fixed infra amortizes.

## Cost-reduction levers (implemented or available)
1. **Semantic response cache** (Redis) — deflect 20–40% of repeat FAQ calls.
2. **Tiered routing** — cheap default model; escalate only on low confidence.
3. **Trim retrieved context** — reranking sends fewer, better chunks (input
   tokens dominate cost).
4. **Prompt caching / system-prompt reuse** where the provider supports it.
5. **Cap output length**; structured answers over prose.
6. **Incremental embeddings** — only changed products (webhook-driven).
7. **Self-host** the reranker / image model at scale; provider free tiers in dev.
8. **Per-session token budgets** (`PER_SESSION_TOKEN_BUDGET`) cap worst-case spend
   and stop abuse/injection loops from running up the bill.
