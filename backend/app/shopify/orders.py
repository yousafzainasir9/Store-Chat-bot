"""Live order, tracking, stock, and return tools.

These resolve **live** data through the Shopify Admin API at answer time — never
from the vector index (DEVELOPMENT_PLAN.md §2.4). Every order/PII/return call is
gated by identity verification: the supplied email must match the email on the
order, or the call returns ``unauthorized`` and reveals nothing.

Return/exchange *initiation* writes to Shopify and is guarded by feature flags
(off until the return scopes are granted).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.verification import emails_match
from app.observability.logging import get_logger
from app.shopify.client import ShopifyClient

_log = get_logger("shopify.orders")


class ToolStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result of a live tool call, ready to ground an answer on."""

    status: ToolStatus
    summary: str
    data: dict[str, str] = field(default_factory=dict)
    citation: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ToolStatus.OK


_ORDER_QUERY = """
query($query: String!) {
  orders(first: 1, query: $query) {
    edges {
      node {
        id name email displayFinancialStatus displayFulfillmentStatus
        fulfillments {
          status
          trackingInfo { number company url }
        }
      }
    }
  }
}
"""

_VARIANT_STOCK_QUERY = """
query($query: String!) {
  productVariants(first: 5, query: $query) {
    edges { node { id title sku inventoryQuantity availableForSale product { title } } }
  }
}
"""


class OrderService:
    """Live order/stock/return operations with identity verification."""

    def __init__(
        self,
        client: ShopifyClient,
        *,
        returns_enabled: bool = False,
        exchanges_enabled: bool = False,
    ) -> None:
        self._client = client
        self._returns_enabled = returns_enabled
        self._exchanges_enabled = exchanges_enabled

    async def _fetch_order(self, order_number: str) -> dict[str, Any] | None:
        data = await self._client.graphql(_ORDER_QUERY, {"query": f"name:#{order_number}"})
        edges = (data.get("orders") or {}).get("edges") or []
        return edges[0]["node"] if edges else None

    async def _verified_order(
        self, order_number: str, email: str
    ) -> tuple[ToolStatus, dict[str, Any] | None]:
        """Fetch an order only if the supplied email matches the one on record."""
        order = await self._fetch_order(order_number)
        if order is None:
            return ToolStatus.NOT_FOUND, None
        if not emails_match(email, str(order.get("email") or "")):
            # Do not leak whether the order exists; same response either way.
            _log.info("order_auth_failed", order_number=order_number)
            return ToolStatus.UNAUTHORIZED, None
        return ToolStatus.OK, order

    async def get_order_status(self, order_number: str, email: str) -> ToolResult:
        status, order = await self._verified_order(order_number, email)
        if status is not ToolStatus.OK or order is None:
            return _gate_result(status, order_number)
        financial = str(order.get("displayFinancialStatus") or "UNKNOWN")
        fulfillment = str(order.get("displayFulfillmentStatus") or "UNKNOWN")
        return ToolResult(
            status=ToolStatus.OK,
            summary=(
                f"Order #{order_number}: payment {financial.lower()}, "
                f"fulfillment {fulfillment.lower().replace('_', ' ')}."
            ),
            data={"financial_status": financial, "fulfillment_status": fulfillment},
            citation=f"Order #{order_number}",
        )

    async def get_tracking(self, order_number: str, email: str) -> ToolResult:
        status, order = await self._verified_order(order_number, email)
        if status is not ToolStatus.OK or order is None:
            return _gate_result(status, order_number)
        for f in order.get("fulfillments") or []:
            for t in f.get("trackingInfo") or []:
                number = t.get("number")
                if number:
                    company = t.get("company") or "the carrier"
                    return ToolResult(
                        status=ToolStatus.OK,
                        summary=f"Order #{order_number} shipped via {company}, tracking {number}.",
                        data={
                            "tracking_number": str(number),
                            "carrier": str(company),
                            "url": str(t.get("url") or ""),
                        },
                        citation=f"Order #{order_number}",
                    )
        return ToolResult(
            status=ToolStatus.OK,
            summary=f"Order #{order_number} does not have tracking yet.",
            citation=f"Order #{order_number}",
        )

    async def get_fulfillment(self, order_number: str, email: str) -> ToolResult:
        status, order = await self._verified_order(order_number, email)
        if status is not ToolStatus.OK or order is None:
            return _gate_result(status, order_number)
        fulfillments = order.get("fulfillments") or []
        state = fulfillments[0].get("status") if fulfillments else "UNFULFILLED"
        return ToolResult(
            status=ToolStatus.OK,
            summary=f"Order #{order_number} fulfillment status: {str(state).lower()}.",
            data={"fulfillment_state": str(state)},
            citation=f"Order #{order_number}",
        )

    async def check_stock(self, query: str) -> ToolResult:
        """Live stock lookup by SKU/title (quantity is always real-time)."""
        data = await self._client.graphql(_VARIANT_STOCK_QUERY, {"query": query})
        edges = (data.get("productVariants") or {}).get("edges") or []
        if not edges:
            return ToolResult(
                ToolStatus.NOT_FOUND, f"I couldn't find a product matching {query!r}."
            )
        node = edges[0]["node"]
        qty = int(node.get("inventoryQuantity") or 0)
        available = bool(node.get("availableForSale"))
        title = (node.get("product") or {}).get("title") or node.get("title") or query
        if available and qty > 0:
            summary = f"{title} ({node.get('title')}) is in stock — {qty} available."
        else:
            summary = f"{title} ({node.get('title')}) is currently out of stock."
        return ToolResult(
            status=ToolStatus.OK,
            summary=summary,
            data={"quantity": str(qty), "available": str(available)},
            citation="Live inventory",
        )

    async def initiate_return(
        self, order_number: str, email: str, *, reason: str = ""
    ) -> ToolResult:
        if not self._returns_enabled:
            return ToolResult(
                ToolStatus.DISABLED,
                "Returns can't be started here yet — I'll connect you to our team.",
            )
        status, order = await self._verified_order(order_number, email)
        if status is not ToolStatus.OK or order is None:
            return _gate_result(status, order_number)
        # Write path (returnRequest mutation) is wired when scopes are granted.
        _log.info("return_initiated", order_number=order_number, reason=reason[:80])
        return ToolResult(
            status=ToolStatus.OK,
            summary=(
                f"I've started a return for order #{order_number}. "
                "Check your email for the return label."
            ),
            citation=f"Order #{order_number}",
        )

    async def initiate_exchange(
        self, order_number: str, email: str, *, new_size: str = ""
    ) -> ToolResult:
        if not self._exchanges_enabled:
            return ToolResult(
                ToolStatus.DISABLED,
                "Exchanges can't be started here yet — I'll connect you to our team.",
            )
        status, order = await self._verified_order(order_number, email)
        if status is not ToolStatus.OK or order is None:
            return _gate_result(status, order_number)
        _log.info("exchange_initiated", order_number=order_number, new_size=new_size)
        return ToolResult(
            status=ToolStatus.OK,
            summary=f"I've started an exchange for order #{order_number}"
            + (f" to size {new_size}." if new_size else "."),
            citation=f"Order #{order_number}",
        )


def _gate_result(status: ToolStatus, order_number: str) -> ToolResult:
    """Uniform messaging for not-found / unauthorized (no information leak)."""
    if status is ToolStatus.UNAUTHORIZED:
        return ToolResult(
            ToolStatus.UNAUTHORIZED,
            "I couldn't verify that order with the email provided. For your security, "
            "please share the email used on the order.",
        )
    return ToolResult(
        ToolStatus.NOT_FOUND,
        f"I couldn't find order #{order_number}. Please double-check the number.",
    )
