"""Fashion recommendation service.

Pipeline:

    semantic candidates (vector search)
      -> constraint filter (gender, category, color, size availability, budget)
      -> LIVE in-stock verification (never suggest what can't be bought)
      -> rank -> top-N with reasons + citations

"Complete the look" maps a seed category to complementary categories and returns
one in-stock item per complementary category, respecting the same constraints.

In-stock is confirmed live through the order service at suggest time — the
descriptive ``available_sizes`` in the index is only a pre-filter (quantity is
volatile and never indexed, per the plan).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.observability.logging import get_logger
from app.observability.metrics import metrics
from app.rag.embeddings import Embedder
from app.rag.models import Chunk
from app.rag.vector_store import VectorStore
from app.recommendations.constraints import Constraints
from app.shopify.orders import OrderService, ToolStatus

_log = get_logger("recommendations")

# Fashion complementary-category map for "complete the look".
_COMPLEMENTS: dict[str, tuple[str, ...]] = {
    "Dress": ("Jacket", "Skirt"),
    "Jeans": ("Shirt", "Sweater", "Jacket"),
    "Shirt": ("Jeans", "Jacket"),
    "Sweater": ("Jeans", "Skirt"),
    "Jacket": ("Shirt", "Jeans"),
    "Skirt": ("Sweater", "Jacket"),
}


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A single suggested product with a human-readable reason."""

    product_id: str
    title: str
    price: float
    url: str
    reason: str

    @property
    def citation(self) -> str:
        return self.title


class RecommendationService:
    """Constraint-aware, live-stock-verified product recommendations."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        order_service: OrderService,
        *,
        candidate_k: int = 30,
        max_results: int = 3,
        verify_live_stock: bool = True,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._orders = order_service
        self._candidate_k = candidate_k
        self._max_results = max_results
        self._verify_live_stock = verify_live_stock

    async def recommend(self, query: str, constraints: Constraints) -> list[Recommendation]:
        """Return up to ``max_results`` in-stock products matching constraints."""
        search_text = _enrich_query(query, constraints)
        vector = (await self._embedder.embed([search_text]))[0]
        filters: dict[str, str] = {}
        if constraints.gender and constraints.gender != "unisex":
            filters["gender"] = constraints.gender
        candidates = await self._store.search(
            vector, top_k=self._candidate_k, filters=filters or None
        )

        results: list[Recommendation] = []
        for sc in candidates:
            chunk = sc.chunk
            if chunk.metadata.get("source") != "Product":
                continue
            if not passes_constraints(chunk, constraints):
                continue
            if self._verify_live_stock and not await self._in_stock(chunk):
                continue
            results.append(to_recommendation(chunk, constraints))
            if len(results) >= self._max_results:
                break

        metrics.incr("recommendations_total")
        _log.info("recommend", returned=len(results), candidates=len(candidates))
        return results

    async def complete_the_look(
        self, seed_category: str, constraints: Constraints
    ) -> list[Recommendation]:
        """Suggest one in-stock complementary item per related category."""
        complements = _COMPLEMENTS.get(seed_category, ())
        out: list[Recommendation] = []
        for category in complements:
            cat_constraints = Constraints(
                category=category,
                color=constraints.color,
                size=constraints.size,
                gender=constraints.gender,
                budget_min=constraints.budget_min,
                budget_max=constraints.budget_max,
            )
            recs = await self.recommend(f"{category} to pair", cat_constraints)
            if recs:
                top = recs[0]
                out.append(
                    Recommendation(
                        product_id=top.product_id,
                        title=top.title,
                        price=top.price,
                        url=top.url,
                        reason=f"Pairs well with your {seed_category.lower()}",
                    )
                )
        return out

    async def _in_stock(self, chunk: Chunk) -> bool:
        title = chunk.metadata.get("title") or chunk.metadata.get("handle") or ""
        result = await self._orders.check_stock(title)
        return result.status is ToolStatus.OK and result.data.get("available") == "True"


def _enrich_query(query: str, c: Constraints) -> str:
    parts = [query]
    for value in (c.category, c.color, c.occasion, c.gender):
        if value:
            parts.append(value)
    return " ".join(parts)


def passes_constraints(chunk: Chunk, c: Constraints) -> bool:
    meta = chunk.metadata
    if c.category and meta.get("category", "").lower() != c.category.lower():
        return False
    if c.color and c.color.lower() not in meta.get("colors", "").lower():
        return False
    if c.size:
        available = [
            s.strip().upper() for s in meta.get("available_sizes", "").split(",") if s.strip()
        ]
        if c.size.upper() not in available:
            return False
    price = _price(meta)
    if c.budget_max is not None and price > c.budget_max:
        return False
    return not (c.budget_min is not None and price < c.budget_min)


def _price(meta: dict[str, str]) -> float:
    try:
        return float(meta.get("price_min", "0") or 0)
    except ValueError:
        return 0.0


def to_recommendation(chunk: Chunk, c: Constraints) -> Recommendation:
    meta = chunk.metadata
    reasons = []
    if c.category:
        reasons.append(f"matches the {c.category.lower()} you asked for")
    if c.color:
        reasons.append(f"in {c.color.lower()}")
    if c.budget_max is not None:
        reasons.append(f"under ${c.budget_max:.0f}")
    if c.size:
        reasons.append(f"available in size {c.size}")
    reason = ", ".join(reasons) if reasons else "a strong match for your request"
    return Recommendation(
        product_id=meta.get("product_id", chunk.document_id),
        title=meta.get("title", "this item"),
        price=_price(meta),
        url=meta.get("url", ""),
        reason=reason,
    )
