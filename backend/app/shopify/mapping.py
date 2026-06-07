"""Map a Shopify product node into a RAG :class:`Document`.

Decision (confirmed with the user): **one document per product**, with
variants/sizes/colors/price/gender/category captured as *metadata*. This keeps
the index small and cheap while still supporting filtered retrieval
("women's dresses under $100") and "do you have this in M?" — answered by
filters plus a *live* stock check (quantity is never indexed, per §2.4/§7).

The function is pure and deterministic so it is trivially unit-testable.
"""

from __future__ import annotations

import re
from typing import Any

from app.rag.models import Document

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Heuristic gender inference from type/tags (a real store often has a metafield).
_WOMEN = {"women", "womens", "women's", "ladies", "dress", "skirt"}
_MEN = {"men", "mens", "men's"}


def strip_html(html: str) -> str:
    """Convert product description HTML to clean plain text."""
    text = _TAG_RE.sub(" ", html or "")
    text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    return _WS_RE.sub(" ", text).strip()


def _price_band(amount: float) -> str:
    if amount < 50:
        return "under_50"
    if amount < 100:
        return "50_100"
    if amount < 200:
        return "100_200"
    return "200_plus"


def _infer_gender(product_type: str, tags: list[str]) -> str:
    hay = {product_type.lower(), *[t.lower() for t in tags]}
    if hay & _MEN:
        return "men"
    if hay & _WOMEN:
        return "women"
    return "unisex"


def _collect_options(product: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (sizes, colors) from options + variant selectedOptions."""
    sizes: list[str] = []
    colors: list[str] = []
    for opt in product.get("options") or []:
        name = (opt.get("name") or "").lower()
        values = opt.get("values") or []
        if "size" in name:
            sizes = list(values)
        elif "color" in name or "colour" in name:
            colors = list(values)
    # Fall back to variant selectedOptions if options are absent.
    if not sizes or not colors:
        for v in product.get("variants") or []:
            for so in v.get("selectedOptions") or []:
                n, val = (so.get("name") or "").lower(), so.get("value")
                if val and "size" in n and val not in sizes:
                    sizes.append(val)
                elif val and ("color" in n or "colour" in n) and val not in colors:
                    colors.append(val)
    return sizes, colors


def _available_sizes(product: dict[str, Any]) -> list[str]:
    """Sizes with at least one variant marked availableForSale (descriptive only)."""
    out: list[str] = []
    for v in product.get("variants") or []:
        if not v.get("availableForSale"):
            continue
        for so in v.get("selectedOptions") or []:
            if (so.get("name") or "").lower() == "size":
                val = so.get("value")
                if val and val not in out:
                    out.append(val)
    return out


def _min_price(product: dict[str, Any]) -> float:
    pr = (product.get("priceRangeV2") or {}).get("minVariantPrice") or {}
    try:
        return float(pr.get("amount", 0.0))
    except (TypeError, ValueError):
        return 0.0


def product_to_document(product: dict[str, Any]) -> Document:
    """Map one Shopify product node to a single :class:`Document`."""
    product_id = product["id"]
    title = product.get("title", "")
    product_type = product.get("productType") or "Apparel"
    vendor = product.get("vendor") or ""
    tags = list(product.get("tags") or [])
    description = strip_html(product.get("descriptionHtml", ""))
    sizes, colors = _collect_options(product)
    available_sizes = _available_sizes(product)
    min_price = _min_price(product)
    gender = _infer_gender(product_type, tags)
    image_url = (product.get("featuredImage") or {}).get("url") or ""

    # Retrieval text: everything semantically useful, in natural language.
    parts = [
        title,
        f"Category: {product_type}.",
        f"Brand: {vendor}." if vendor else "",
        description,
        f"Available colors: {', '.join(colors)}." if colors else "",
        f"Available sizes: {', '.join(sizes)}." if sizes else "",
        f"Price from ${min_price:.2f}." if min_price else "",
        f"Tags: {', '.join(tags)}." if tags else "",
    ]
    text = "\n".join(p for p in parts if p)

    metadata = {
        "source": "Product",
        "title": title,
        "product_id": product_id,
        "handle": product.get("handle", ""),
        "category": product_type,
        "gender": gender,
        "vendor": vendor,
        "colors": ", ".join(colors),
        "sizes": ", ".join(sizes),
        "available_sizes": ", ".join(available_sizes),
        "price_min": f"{min_price:.2f}",
        "price_band": _price_band(min_price),
        "in_stock": "true" if available_sizes else "false",
        "url": product.get("onlineStoreUrl") or "",
        "image_url": image_url,
        "status": product.get("status", ""),
    }
    return Document(id=product_id, text=text, metadata=metadata)


def documents_from_products(products: list[dict[str, Any]]) -> list[Document]:
    """Map a list of product nodes, skipping non-active products."""
    return [
        product_to_document(p)
        for p in products
        if (p.get("status") or "ACTIVE").upper() == "ACTIVE"
    ]
