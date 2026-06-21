"""One-command catalog import for the live (non-demo) Shopify integration.

Run this once after pointing ``.env`` at your real Shopify store
(``DEMO_MODE=false`` + ``SHOPIFY_STORE_DOMAIN`` + Dev Dashboard
``SHOPIFY_CLIENT_ID``/``SHOPIFY_CLIENT_SECRET``, or a legacy
``SHOPIFY_ADMIN_API_TOKEN``). It seeds the knowledge base and pulls your whole
product catalog into the search index via Shopify's Bulk Operations API.

Usage (from the ``backend`` directory):

    uv run python scripts/import_catalog.py

Or inside Docker:

    docker compose exec api python scripts/import_catalog.py

It prints how many product/KB chunks were indexed and exits non-zero on error,
so it's safe to run from any setup guide without reading the code.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import get_settings
from app.services.container import build_container


async def _run() -> int:
    settings = get_settings()

    if settings.demo_mode:
        print(
            "DEMO_MODE is true — this script imports a REAL Shopify catalog.\n"
            "Set DEMO_MODE=false in .env (and SHOPIFY_STORE_DOMAIN + "
            "SHOPIFY_CLIENT_ID/SHOPIFY_CLIENT_SECRET) first, then re-run.",
            file=sys.stderr,
        )
        return 1

    has_oauth = bool(settings.shopify_client_id and settings.shopify_client_secret)
    if not settings.shopify_store_domain or not (
        has_oauth or settings.shopify_admin_api_token
    ):
        print(
            "Missing Shopify credentials. Set SHOPIFY_STORE_DOMAIN plus either "
            "SHOPIFY_CLIENT_ID/SHOPIFY_CLIENT_SECRET (preferred) or "
            "SHOPIFY_ADMIN_API_TOKEN in .env, then re-run.",
            file=sys.stderr,
        )
        return 1

    print(f"Connecting to {settings.shopify_store_domain} ...")
    container = build_container(settings)

    print("Seeding the knowledge base (FAQs, policies, size guides) ...")
    seeded = await container.bootstrap()

    print("Importing the product catalog from Shopify (Bulk Operations) ...")
    products = await container.catalog.full_import()

    print(
        f"\nDone. Indexed {seeded} knowledge-base chunk(s) and "
        f"{products} product chunk(s).\n"
        "Your chatbot now answers from this store's real catalog."
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
