"""Shopify Admin GraphQL client.

A single throttled entry point for all Admin API access. ``httpx`` is imported
lazily so the offline test suite (which uses :class:`FakeShopifyClient`) needs no
network stack. On ``THROTTLED`` errors it backs off using the server's reported
cost state; on transient HTTP errors it retries with exponential backoff.

Authentication is delegated to a :class:`~app.shopify.auth.TokenProvider`: the
Dev Dashboard client-credentials flow (preferred) or a static token (legacy
fallback). The current token is read per request, so automatic refreshes are
transparent to callers.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from app.observability.logging import get_logger
from app.shopify.auth import StaticTokenProvider, TokenProvider
from app.shopify.throttle import CostThrottle

_log = get_logger("shopify.client")

_THROTTLED = "THROTTLED"


class ShopifyClient(Protocol):
    """Minimal Admin GraphQL surface the catalog/bulk layers depend on."""

    async def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


class AdminGraphQLClient(ShopifyClient):
    """Production Admin GraphQL client with cost-aware throttling + backoff."""

    def __init__(
        self,
        store_domain: str,
        access_token: str | None = None,
        *,
        token_provider: TokenProvider | None = None,
        api_version: str = "2025-01",
        max_retries: int = 5,
        throttle: CostThrottle | None = None,
    ) -> None:
        """Create a client.

        Provide exactly one credential source: either a ``token_provider`` (the
        Dev Dashboard client-credentials flow, preferred) or a static
        ``access_token`` (legacy custom apps, wrapped in a static provider).
        """
        if not store_domain:
            raise ValueError("store_domain is required")
        if token_provider is None:
            if not access_token:
                raise ValueError("either token_provider or access_token is required")
            token_provider = StaticTokenProvider(access_token)
        self._endpoint = f"https://{store_domain}/admin/api/{api_version}/graphql.json"
        self._token_provider = token_provider
        self._max_retries = max_retries
        self._throttle = throttle or CostThrottle()
        self._client: object | None = None

    async def _auth_headers(self) -> dict[str, str]:
        """Build request headers with a current (possibly just-refreshed) token."""
        return {
            "X-Shopify-Access-Token": await self._token_provider.get_token(),
            "Content-Type": "application/json",
        }

    def _get_client(self) -> object:
        if self._client is None:
            import httpx  # lazy import

            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()  # type: ignore[attr-defined]
            self._client = None
        aclose = getattr(self._token_provider, "aclose", None)
        if aclose is not None:
            await aclose()

    async def graphql(
        self, query: str, variables: dict[str, Any] | None = None, *, estimated_cost: float = 50.0
    ) -> dict[str, Any]:
        """Execute a GraphQL operation, respecting cost limits and retries."""
        client = self._get_client()
        payload = {"query": query, "variables": variables or {}}
        headers = await self._auth_headers()

        attempt = 0
        while True:
            await self._throttle.acquire(estimated_cost)
            try:
                resp = await client.post(  # type: ignore[attr-defined]
                    self._endpoint, json=payload, headers=headers
                )
            except Exception as exc:  # network error -> retry with backoff
                attempt += 1
                if attempt > self._max_retries:
                    raise
                await self._backoff(attempt)
                _log.warning("graphql_retry", attempt=attempt, error=str(exc))
                continue

            if resp.status_code == 429:
                attempt += 1
                if attempt > self._max_retries:
                    resp.raise_for_status()
                await self._backoff(attempt)
                continue

            resp.raise_for_status()
            data = resp.json()
            self._sync_throttle(data)

            if self._is_throttled(data):
                attempt += 1
                if attempt > self._max_retries:
                    raise RuntimeError("Shopify GraphQL throttled after retries")
                await self._backoff(attempt)
                continue

            if data.get("errors"):
                raise RuntimeError(f"Shopify GraphQL errors: {data['errors']}")
            result: dict[str, Any] = data["data"]
            return result

    def _sync_throttle(self, data: dict[str, Any]) -> None:
        cost = (data.get("extensions") or {}).get("cost") or {}
        status = cost.get("throttleStatus") or {}
        if "currentlyAvailable" in status:
            self._throttle.update_from_response(
                available=float(status["currentlyAvailable"]),
                restore_rate=status.get("restoreRate"),
            )

    @staticmethod
    def _is_throttled(data: dict[str, Any]) -> bool:
        for err in data.get("errors") or []:
            code = ((err.get("extensions") or {}).get("code")) or ""
            if code == _THROTTLED:
                return True
        return False

    @staticmethod
    async def _backoff(attempt: int) -> None:
        await asyncio.sleep(min(2.0**attempt * 0.1, 10.0))
