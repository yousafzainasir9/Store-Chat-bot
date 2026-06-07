"""Tests for bulk JSONL grouping and the synthetic catalog generator."""

from __future__ import annotations

from app.shopify.bulk import group_jsonl_by_parent
from app.shopify.fake import generate_catalog_jsonl


def test_group_links_variants_to_parents() -> None:
    lines = generate_catalog_jsonl(n_products=3)
    products = group_jsonl_by_parent(lines)
    assert len(products) == 3
    assert all(p["variants"] for p in products)
    # Every variant points back at its parent.
    for p in products:
        assert all(v["__parentId"] == p["id"] for v in p["variants"])


def test_blank_lines_ignored() -> None:
    assert group_jsonl_by_parent(["", "  "]) == []
