"""Shared FastAPI dependencies.

Resolving settings from ``request.app.state`` (rather than the global cached
singleton) keeps route handlers bound to the settings the app was actually
created with — which is what makes the app testable with injected settings.
"""

from __future__ import annotations

from fastapi import Request

from app.config import Settings


def get_app_settings(request: Request) -> Settings:
    """Return the :class:`Settings` the running app was created with."""
    return request.app.state.settings  # type: ignore[no-any-return]
