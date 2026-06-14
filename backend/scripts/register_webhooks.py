"""Register the Shopify webhooks that keep the catalog index fresh.

Points Shopify at ``<PUBLIC_URL>/webhooks/shopify`` for the product and
inventory topics the chatbot cares about. Reads the store domain, admin token,
and API version from ``.env``; takes the public URL (your ngrok URL) as the one
argument.

Usage (from the ``backend`` directory):

    uv run python scripts/register_webhooks.py https://abc123.ngrok-free.app

Or inside Docker:

    docker compose exec api python scripts/register_webhooks.py https://abc123.ngrok-free.app

Safe to re-run: topics that are already registered for the same URL are
reported as "already registered" instead of failing. Re-run it whenever your
free ngrok URL changes.
"""

from __future__ import annotations

import sys

import httpx

from app.config import get_settings

# Topics the re-indexer handles (see app/api/webhooks.py).
TOPICS = [
    "PRODUCTS_CREATE",
    "PRODUCTS_UPDATE",
    "PRODUCTS_DELETE",
    "INVENTORY_LEVELS_UPDATE",
]

_MUTATION = """
mutation($topic: WebhookSubscriptionTopic!, $url: URL!) {
  webhookSubscriptionCreate(
    topic: $topic
    webhookSubscription: { callbackUrl: $url, format: JSON }
  ) {
    userErrors { message }
    webhookSubscription { id }
  }
}
"""


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        print(
            "Usage: python scripts/register_webhooks.py https://<your-ngrok-url>\n"
            "The URL must be the public HTTPS address that forwards to your backend.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    public_url = sys.argv[1].rstrip("/")
    callback = f"{public_url}/webhooks/shopify"
    settings = get_settings()

    if not settings.shopify_store_domain or not settings.shopify_admin_api_token:
        print(
            "Missing Shopify credentials. Set SHOPIFY_STORE_DOMAIN and "
            "SHOPIFY_ADMIN_API_TOKEN in .env, then re-run.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    endpoint = (
        f"https://{settings.shopify_store_domain}"
        f"/admin/api/{settings.shopify_api_version}/graphql.json"
    )
    headers = {
        "X-Shopify-Access-Token": settings.shopify_admin_api_token,
        "Content-Type": "application/json",
    }

    print(f"Registering webhooks -> {callback}\n")
    failures = 0
    with httpx.Client(timeout=30) as client:
        for topic in TOPICS:
            resp = client.post(
                endpoint,
                headers=headers,
                json={"query": _MUTATION, "variables": {"topic": topic, "url": callback}},
            )
            payload = resp.json()
            result = (payload.get("data") or {}).get("webhookSubscriptionCreate") or {}
            errors = result.get("userErrors") or []
            if not errors and result.get("webhookSubscription"):
                print(f"  [ok]   {topic}")
            elif any("already" in (e.get("message") or "").lower() for e in errors):
                print(f"  [skip] {topic} (already registered)")
            else:
                msg = "; ".join(e.get("message", "") for e in errors) or str(payload)
                print(f"  [FAIL] {topic}: {msg}")
                failures += 1

    if failures:
        print(f"\n{failures} topic(s) failed. Check your token scopes and URL.", file=sys.stderr)
        raise SystemExit(1)
    print("\nAll webhooks registered. Edit a product in Shopify to test the re-index.")


if __name__ == "__main__":
    main()
