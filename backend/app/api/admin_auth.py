"""Admin authentication (Phase 7).

Bearer-token auth for the ``/admin/*`` surface. When ``ADMIN_API_KEY`` is set,
every admin request must present ``Authorization: Bearer <key>`` (constant-time
compared). When it is unset, admin routes are open only outside production
(developer convenience) — production startup validation requires the key, so it
can never be unset in prod. A full OAuth2/JWT + RBAC scheme slots in behind this
same dependency later.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status


def require_admin(request: Request) -> None:
    """Dependency: authorize an admin request, or raise 401/403."""
    settings = request.app.state.settings
    key = settings.admin_api_key
    if not key:
        # No key configured: allowed in dev/staging/test, blocked in production
        # (production startup also rejects a missing key).
        if settings.is_production:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin API is not configured.")
        return
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not (token and hmac.compare_digest(token, key)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
