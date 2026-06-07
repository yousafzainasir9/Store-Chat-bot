# Data model

The system has three stores: **Postgres** (conversations, feedback, content),
**Qdrant** (text + image vector collections), and **Redis** (ephemeral
cache/limits/queue — no schema). In demo mode all three are replaced by
in-process structures.

## 1. Domain models (framework-free)

Defined in `app/models/` as plain dataclasses so the domain never depends on the
persistence layer.

### `Conversation` (`models/conversation.py`)
| Field | Type | Notes |
|---|---|---|
| `id` | str | Conversation id (also the SSE `conversation_id`). |
| `locale` | str | Detected/declared language; default `en`. |
| `created_at` | datetime (UTC) | |
| `messages` | list[`StoredMessage`] | Ordered turns. |

### `StoredMessage`
| Field | Type | Notes |
|---|---|---|
| `id` | str | Message id (assistant id is the SSE `message_id`). |
| `conversation_id` | str | FK. |
| `role` | `MessageRole` | `user` \| `assistant`. |
| `content` | str | Message text. |
| `citations` | list[str] | Source labels for grounded answers. |
| `handoff_reason` | str \| null | `low_confidence` / `out_of_scope` / `injection` / `budget` / null. |
| `confidence` | float | Answer confidence (0–1). |
| `token_count` | int | Tokens spent on this assistant turn (cost analytics). |
| `created_at` | datetime (UTC) | |

### `Feedback`
| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `conversation_id` / `message_id` | str | What the feedback is about. |
| `value` | str | `up` \| `down`. |
| `comment` | str \| null | Optional. |
| `created_at` | datetime (UTC) | |

### `ContentItem` (`models/content.py`)
Editable FAQ/policy managed in the admin and indexed for retrieval.
| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `title` / `body` | str | Indexed as `content::{id}`. |
| `category` / `source` | str | e.g. `FAQ`. |
| `locale` | str | |
| `created_at` / `updated_at` | datetime (UTC) | |

### RAG types (`rag/models.py`)
- `Document(id, text, metadata)` — ingestion unit (FAQ section, policy, product).
- `Chunk(id, document_id, text, metadata)` — embedded/retrieved unit.
- `ScoredChunk(chunk, score)` — retrieval/rerank result; `.citation` derives a
  source label from metadata.

## 2. Postgres schema (`repositories/sql.py`)

Created via SQLAlchemy (Alembic migrations in production).

### `conversations`
| Column | Type | |
|---|---|---|
| `id` | varchar(64) | PK |
| `locale` | varchar(8) | |
| `created_at` | timestamptz | |

### `messages`
| Column | Type | |
|---|---|---|
| `id` | varchar(64) | PK |
| `conversation_id` | varchar(64) | FK → conversations.id, indexed |
| `role` | varchar(16) | |
| `content` | text | |
| `citations` | text | JSON-encoded array |
| `handoff_reason` | varchar(32) | nullable |
| `confidence` | float | |
| `token_count` | int | |
| `created_at` | timestamptz | |

### `feedback`
| Column | Type | |
|---|---|---|
| `id` | varchar(64) | PK |
| `conversation_id` / `message_id` | varchar(64) | indexed |
| `value` | varchar(8) | |
| `comment` | text | nullable |
| `created_at` | timestamptz | |

> Editable content currently uses the in-memory repository; a SQL `content`
> table mirrors `ContentItem` and slots in behind `ContentRepository`.

Erasure deletes a conversation's `messages` + `feedback` + the `conversations`
row; the retention sweep deletes everything older than `DATA_RETENTION_DAYS`.

## 3. Vector collections (Qdrant)

Two **separate** collections — different models and dimensions, never mixed.

### `kb_text` (text retrieval)
- **Vector**: text embedding (`EMBEDDING_DIMENSION`, cosine).
- **Sources**: seed KB sections, editable content, and **one point per product**.
- **Payload (filters + citation)**: `chunk_id`, `document_id`, `text`,
  `source`, `title`, `category`, `gender`, `vendor`, `colors`, `sizes`,
  `available_sizes`, `price_min`, `price_band`, `in_stock`, `url`, `image_url`,
  `handle`, `status`.

### `kb_image` (visual search)
- **Vector**: image embedding (`IMAGE_EMBEDDING_DIMENSION`, cosine).
- **Sources**: one point per product image (`{product_id}::image`).
- **Payload**: the same product metadata as above (for filtering + citation).

**Indexed vs. live.** Descriptive availability (a product *has* an XL) and
base price band are indexed for filtering; **quantity on hand and final price
are always resolved live** through Shopify and never trusted from the index.

## 4. Product metadata mapping

`app/shopify/mapping.py` maps a Shopify product node to one `Document`:

| Metadata key | Source |
|---|---|
| `category` | `productType` |
| `gender` | inferred from type/tags (`men`/`women`/`unisex`) |
| `colors` / `sizes` | product options + variant `selectedOptions` |
| `available_sizes` | sizes with a variant `availableForSale` (descriptive) |
| `price_min` / `price_band` | `priceRangeV2.minVariantPrice` → `under_50`/`50_100`/`100_200`/`200_plus` |
| `in_stock` | any available size present |
| `url` / `image_url` | `onlineStoreUrl` / `featuredImage.url` |
| `vendor` / `handle` / `status` | passthrough |
