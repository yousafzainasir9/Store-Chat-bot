"""Shopify Dev Dashboard authentication (client-credentials grant).

Legacy in-admin custom apps were retired on 2026-01-01. Apps created in the
Shopify Dev Dashboard authenticate with the OAuth *client-credentials* grant:
the long-lived Client ID/secret are exchanged for a short-lived (~24h) Admin API
access token. This module performs that exchange, caches the token, and refreshes
it automatically shortly before expiry.

No static token is persisted and no operator action is ever required: the running
service obtains a fresh token on demand and reuses it until it is about to expire.
``httpx`` is imported lazily so the offline test suite needs no network stack.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol

from app.observability.logging import get_logger

_log = get_logger("shopify.auth")

# Refresh this many seconds before the reported expiry to avoid edge races where
# a token expires mid-request.
_DEFAULT_REFRESH_SKEW_SECONDS = 300
# Shopify currently issues 24h tokens; used only if the response omits expires_in.
_FALLBACK_EXPIRES_IN = 86399


class TokenProvider(Protocol):
    """Supplies a valid Admin API access token, refreshing as needed."""

    async def get_token(self) -> str: ...


class ClientCredentialsTokenProvider(TokenProvider):
    """Fetch + cache a short-lived Admin API token via the client-credentials grant.

    Thread/coroutine-safe: concurrent callers share a single in-flight refresh via
    an :class:`asyncio.Lock`, so a token is never fetched more than once per cycle.
    """

    def __init__(
        self,
        store_domain: str,
        client_id: str,
        client_secret: str,
        *,
        refresh_skew_seconds: int = _DEFAULT_REFRESH_SKEW_SECONDS,
    ) -> None:
        if not (store_domain and client_id and client_secret):
            raise ValueError(
                "store_domain, client_id and client_secret are required"
            )
        self._url = f"https://{store_domain}/admin/oauth/access_token"
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_skew = refresh_skew_seconds
        self._token: str | None = None
        self._expires_at_monotonic: float = 0.0
        self._lock = asyncio.Lock()
        self._http: Any | None = None

    def _is_fresh(self) -> bool:
        return (
            self._token is not None
            and time.monotonic() < self._expires_at_monotonic - self._refresh_skew
        )

    async def get_token(self) -> str:
        """Return a valid access token, refreshing it if missing or near expiry."""
        if self._is_fresh():
            assert self._token is not None  # for type-checkers; guaranteed by _is_fresh
            return self._token
        async with self._lock:
            # Re-check inside the lock: another coroutine may have refreshed while
            # we awaited the lock.
            if self._is_fresh():
                assert self._token is not None
                return self._token
            return await self._refresh()

    async def _refresh(self) -> str:
        import httpx  # lazy import

        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)

        resp = await self._http.post(
            self._url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        body = resp.json()

        token = body.get("access_token")
        if not token:
            raise RuntimeError("Shopify token endpoint returned no access_token")
        expires_in = float(body.get("expires_in") or _FALLBACK_EXPIRES_IN)

        self._token = str(token)
        self._expires_at_monotonic = time.monotonic() + expires_in
        _log.info("shopify_token_refreshed", expires_in=int(expires_in))
        return self._token

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


class StaticTokenProvider(TokenProvider):
    """Wraps a pre-issued static token (legacy custom apps). Fallback only."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("token is required")
        self._token = token

    async def get_token(self) -> str:
        return self._token

    async def aclose(self) -> None:  # symmetry with ClientCredentialsTokenProvider
        return None
