"""Tests for FAQ document import (admin upload)."""

from __future__ import annotations

from app.services.faq_import import UnsupportedDocument, parse_faq_document
from fastapi.testclient import TestClient


def test_parse_markdown_sections() -> None:
    md = b"""---
source: FAQ
---

## Do you offer gift wrapping?
Yes, gift wrapping is available at checkout for $4.95.

## What is your return window?
Returns are accepted within 30 days.
"""
    items = parse_faq_document("faqs.md", md)
    assert len(items) == 2
    assert items[0].title == "Do you offer gift wrapping?"
    assert "gift wrapping" in items[0].body.lower()


def test_parse_csv_with_header() -> None:
    csv_bytes = b"question,answer\nDo you ship internationally?,Yes to 40+ countries.\n"
    items = parse_faq_document("faq.csv", csv_bytes)
    assert len(items) == 1
    assert items[0].title.startswith("Do you ship")
    assert "40+" in items[0].body


def test_parse_csv_without_header() -> None:
    items = parse_faq_document("faq.csv", b"Can I cancel?,Within 60 minutes.\n")
    assert items[0].title == "Can I cancel?"


def test_plain_text_single_item() -> None:
    items = parse_faq_document("policy.txt", b"All sales of clearance items are final.")
    assert len(items) == 1
    assert "clearance" in items[0].body


def test_unsupported_type() -> None:
    import pytest

    with pytest.raises(UnsupportedDocument):
        parse_faq_document("logo.png", b"\x89PNG")


def test_upload_endpoint_creates_and_answers(client: TestClient) -> None:
    md = (
        b"## Do you offer gift wrapping?\n"
        b"Yes, gift wrapping is available at checkout for $4.95.\n"
    )
    resp = client.post(
        "/admin/content/upload",
        files={"file": ("faqs.md", md, "text/markdown")},
    )
    assert resp.status_code == 201
    assert resp.json()["imported"] == 1

    # The imported FAQ is now answerable on /chat (re-indexed on import).
    ans = client.post("/chat", json={"message": "do you offer gift wrapping?"})
    text = " ".join(
        line[5:].strip() for line in ans.text.splitlines() if line.startswith("data:")
    ).lower()
    assert "gift wrapping" in text


def test_upload_empty_rejected(client: TestClient) -> None:
    resp = client.post("/admin/content/upload", files={"file": ("x.md", b"", "text/markdown")})
    assert resp.status_code == 400


def test_upload_unsupported_type_rejected(client: TestClient) -> None:
    resp = client.post("/admin/content/upload", files={"file": ("x.png", b"data", "image/png")})
    assert resp.status_code == 415
