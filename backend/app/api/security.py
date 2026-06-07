"""Security response headers (Phase 6).

Adds conservative security headers to every response. These harden the API
surface; the storefront widget's own Content-Security-Policy is documented in
docs/WIDGET.md (the merchant's theme controls page CSP).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Resource-Policy": "cross-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for key, value in _HEADERS.items():
            response.headers.setdefault(key, value)
        return response
