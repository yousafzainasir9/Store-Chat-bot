"""Tests for Shopify client-credentials authentication (token fetch + refresh).

These run fully offline by injecting a fake HTTP client, so no network is used.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from app.shopify.auth import ClientCredentialsTokenProvider, StaticTokenProvider
from app.shopify.client import AdminGraphQLClient

pytestmark = pytest.mark.asyncio


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeHTTP:
    """Records POST calls and returns a sequence of canned token responses."""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads
        self.calls: list[dict[str, Any]] = []

    async def post(
        self, url: str, *, data: dict[str, Any], headers: dict[str, Any]
    ) -> _FakeResponse:
        self.calls.append({"url": url, "data": data, "headers": headers})
        idx = min(len(self.calls) - 1, len(self._payloads) - 1)
        return _FakeResponse(self._payloads[idx])

    async def aclose(self) -> None:
        return None


def _provider(http: _FakeHTTP, **kwargs: Any) -> ClientCredentialsTokenProvider:
    p = ClientCredentialsTokenProvider(
        "acme-threads.myshopify.com", "cid", "secret", **kwargs
    )
    p._http = http  # inject fake transport (skip lazy httpx import)
    return p


async def test_first_call_exchanges_credentials_for_token() -> None:
    http = _FakeHTTP([{"access_token": "tok-1", "expires_in": 86399}])
    provider = _provider(http)

    token = await provider.get_token()

    assert token == "tok-1"
    assert len(http.calls) == 1
    sent = http.calls[0]
    assert sent["url"].endswith("/admin/oauth/access_token")
    assert sent["data"]["grant_type"] == "client_credentials"
    assert sent["data"]["client_id"] == "cid"
    assert sent["data"]["client_secret"] == "secret"


async def test_token_is_cached_between_calls() -> None:
    http = _FakeHTTP([{"access_token": "tok-1", "expires_in": 86399}])
    provider = _provider(http)

    first = await provider.get_token()
    second = await provider.get_token()

    assert first == second == "tok-1"
    assert len(http.calls) == 1  # no second network round-trip


async def test_token_refreshes_when_near_expiry() -> None:
    http = _FakeHTTP(
        [
            {"access_token": "tok-1", "expires_in": 100},
            {"access_token": "tok-2", "expires_in": 86399},
        ]
    )
    # refresh_skew > expires_in forces the cached token to be considered stale.
    provider = _provider(http, refresh_skew_seconds=200)

    first = await provider.get_token()
    second = await provider.get_token()

    assert first == "tok-1"
    assert second == "tok-2"
    assert len(http.calls) == 2


async def test_concurrent_callers_share_single_refresh() -> None:
    class _SlowHTTP(_FakeHTTP):
        async def post(
            self, url: str, *, data: dict[str, Any], headers: dict[str, Any]
        ) -> _FakeResponse:
            await asyncio.sleep(0.02)
            return await super().post(url, data=data, headers=headers)

    http = _SlowHTTP([{"access_token": "tok-1", "expires_in": 86399}])
    provider = _provider(http)

    tokens = await asyncio.gather(*[provider.get_token() for _ in range(10)])

    assert all(t == "tok-1" for t in tokens)
    assert len(http.calls) == 1  # one in-flight refresh shared by all callers


async def test_missing_access_token_raises() -> None:
    http = _FakeHTTP([{"expires_in": 86399}])  # no access_token field
    provider = _provider(http)

    with pytest.raises(RuntimeError):
        await provider.get_token()


def test_provider_requires_all_credentials() -> None:
    with pytest.raises(ValueError):
        ClientCredentialsTokenProvider("shop", "", "secret")


async def test_client_wraps_static_token() -> None:
    client = AdminGraphQLClient("acme-threads.myshopify.com", "shpat_static")
    headers = await client._auth_headers()
    assert headers["X-Shopify-Access-Token"] == "shpat_static"


async def test_client_uses_token_provider_header() -> None:
    http = _FakeHTTP([{"access_token": "tok-1", "expires_in": 86399}])
    client = AdminGraphQLClient(
        "acme-threads.myshopify.com", token_provider=_provider(http)
    )
    headers = await client._auth_headers()
    assert headers["X-Shopify-Access-Token"] == "tok-1"


def test_client_requires_a_credential_source() -> None:
    with pytest.raises(ValueError):
        AdminGraphQLClient("acme-threads.myshopify.com")


async def test_static_provider_returns_token() -> None:
    provider = StaticTokenProvider("shpat_x")
    assert await provider.get_token() == "shpat_x"
