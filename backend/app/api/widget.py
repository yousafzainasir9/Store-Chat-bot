"""Widget session token endpoint + verification (Phase 6).

The embeddable widget requests a short-lived, HMAC-signed session token and
sends it on subsequent ``/chat`` / ``/search/visual`` calls. This is a
lightweight abuse deterrent (not user authentication): it ties traffic to a
token the server issued and that expires, so the public endpoints aren't trivial
to hammer from arbitrary origins. Enforcement is opt-in (``WIDGET_REQUIRE_TOKEN``)
so it can be rolled out without breaking existing clients.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(tags=["widget"])


def _sign(payload: dict[str, int | str], secret: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def issue_token(secret: str, *, ttl_seconds: int) -> tuple[str, int]:
    """Return a signed token and its absolute expiry (unix seconds)."""
    exp = int(time.time()) + ttl_seconds
    return _sign({"exp": exp}, secret), exp


def verify_token(token: str | None, secret: str) -> bool:
    """Constant-time verify a widget session token and check expiry."""
    if not token or "." not in token:
        return False
    body, _, sig = token.partition(".")
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode()))
    except (ValueError, json.JSONDecodeError):
        return False
    return int(payload.get("exp", 0)) > int(time.time())


@router.post("/widget/session", summary="Issue a short-lived widget session token")
async def widget_session(request: Request) -> dict[str, object]:
    """Mint a signed session token for the embeddable widget."""
    settings = request.app.state.settings
    if not settings.widget_secret:
        # Tokens are not configured; return a no-op so the widget still works.
        return {"token": None, "expires_at": None, "required": False}
    token, exp = issue_token(settings.widget_secret, ttl_seconds=settings.widget_token_ttl_seconds)
    return {"token": token, "expires_at": exp, "required": settings.widget_require_token}


def enforce_widget_token(request: Request) -> None:
    """Dependency: reject calls missing a valid token when enforcement is on."""
    settings = request.app.state.settings
    if not (settings.widget_require_token and settings.widget_secret):
        return
    token = request.headers.get("x-widget-token")
    if not verify_token(token, settings.widget_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid widget session token.",
        )


def _widget_config_dto(request: Request) -> dict[str, object]:
    store = request.app.state.container.widget_config.get()
    return {
        "store_name": store.store_name,
        "primary_color": store.primary_color,
        "position": store.position,
        "locale": store.locale,
        "greeting": store.greeting,
        "show_image_upload": store.show_image_upload,
        "updated_at": store.updated_at.isoformat(),
    }


@router.get("/widget/config", summary="Public widget branding/behavior config")
async def widget_config(request: Request) -> dict[str, object]:
    """Served to the embedded widget so merchant settings apply live."""
    return _widget_config_dto(request)
