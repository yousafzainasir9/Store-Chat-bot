"""Tests for Shopify product -> Document mapping."""

from __future__ import annotations

from app.shopify.mapping import (
    documents_from_products,
    product_to_document,
    strip_html,
)

_PRODUCT = {
    "id": "gid://shopify/Product/1",
    "title": "Navy Linen Shirt",
    "handle": "navy-linen-shirt",
    "descriptionHtml": "<p>A <b>navy</b> shirt in organic linen.</p>",
    "productType": "Shirt",
    "vendor": "Acme",
    "tags": ["men", "summer"],
    "status": "ACTIVE",
    "onlineStoreUrl": "https://example.com/products/navy-linen-shirt",
    "priceRangeV2": {"minVariantPrice": {"amount": "59.00", "currencyCode": "USD"}},
    "options": [{"name": "Size", "values": ["S", "M", "L"]}, {"name": "Color", "values": ["Navy"]}],
    "variants": [
        {
            "id": "v1",
            "availableForSale": True,
            "selectedOptions": [{"name": "Size", "value": "M"}, {"name": "Color", "value": "Navy"}],
        },
        {
            "id": "v2",
            "availableForSale": False,
            "selectedOptions": [{"name": "Size", "value": "L"}, {"name": "Color", "value": "Navy"}],
        },
    ],
}


def test_strip_html() -> None:
    # Tags collapse to spaces so adjacent words never merge.
    assert strip_html("<p>Hello <b>world</b> &amp; more</p>") == "Hello world & more"


def test_one_doc_per_product_with_metadata() -> None:
    doc = product_to_document(_PRODUCT)
    assert doc.id == "gid://shopify/Product/1"
    assert doc.metadata["category"] == "Shirt"
    assert doc.metadata["gender"] == "men"
    assert doc.metadata["price_band"] == "50_100"
    assert "M" in doc.metadata["sizes"]
    # Only in-stock sizes are recorded as available (descriptive, not quantity).
    assert doc.metadata["available_sizes"] == "M"
    assert doc.metadata["in_stock"] == "true"
    assert "linen" in doc.text.lower()


def test_inactive_products_skipped() -> None:
    inactive = {**_PRODUCT, "status": "ARCHIVED"}
    assert documents_from_products([inactive]) == []
    assert len(documents_from_products([_PRODUCT])) == 1
