"""Tests for live order/stock/return tools over the Fake Shopify client."""

from __future__ import annotations

import pytest
from app.shopify.fake import FakeShopifyClient
from app.shopify.orders import OrderService, ToolStatus

pytestmark = pytest.mark.asyncio


def _svc(**kw: bool) -> OrderService:
    return OrderService(FakeShopifyClient(n_products=2), **kw)


async def test_order_status_verified() -> None:
    res = await _svc().get_order_status("1001", "alice@example.com")
    assert res.status is ToolStatus.OK
    assert "paid" in res.summary.lower()
    assert res.citation == "Order #1001"


async def test_wrong_email_is_unauthorized_and_leaks_nothing() -> None:
    res = await _svc().get_order_status("1001", "eve@evil.com")
    assert res.status is ToolStatus.UNAUTHORIZED
    assert "1001" not in res.summary  # no detail leaked
    assert "couldn't verify" in res.summary.lower()


async def test_unknown_order_not_found() -> None:
    res = await _svc().get_order_status("9999", "alice@example.com")
    assert res.status is ToolStatus.NOT_FOUND


async def test_tracking_returns_number() -> None:
    res = await _svc().get_tracking("1001", "alice@example.com")
    assert res.status is ToolStatus.OK
    assert "1Z999AA10123456784" in res.summary


async def test_check_stock_live() -> None:
    res = await _svc().check_stock("black dress")
    assert res.status is ToolStatus.OK
    assert "in stock" in res.summary.lower()


async def test_returns_disabled_by_default() -> None:
    res = await _svc().initiate_return("1001", "alice@example.com")
    assert res.status is ToolStatus.DISABLED


async def test_returns_enabled_when_flagged() -> None:
    res = await _svc(returns_enabled=True).initiate_return("1001", "alice@example.com")
    assert res.status is ToolStatus.OK


async def test_return_requires_verification_even_when_enabled() -> None:
    res = await _svc(returns_enabled=True).initiate_return("1001", "eve@evil.com")
    assert res.status is ToolStatus.UNAUTHORIZED
