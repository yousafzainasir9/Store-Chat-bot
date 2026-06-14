"""FastAPI application factory.

Wires configuration, structured logging, middleware, the composition root, and
the API routers. On startup it builds the object graph (:func:`build_container`)
and indexes the seed knowledge base so ``/chat`` is answerable immediately.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, chat, health, visual, webhooks, widget
from app.api.middleware import RequestContextMiddleware
from app.api.ratelimit import RateLimiter
from app.api.security import SecurityHeadersMiddleware
from app.config import Settings, get_settings
from app.observability.logging import configure_logging, get_logger
from app.services.container import build_container


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the container and bootstrap the knowledge base on startup."""
    settings: Settings = app.state.settings
    log = get_logger("lifespan")
    container = build_container(settings)
    app.state.container = container
    if settings.rate_limit_enabled:
        app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    chunks = await container.bootstrap()
    log.info(
        "startup",
        environment=settings.environment.value,
        demo_mode=settings.demo_mode,
        version=settings.app_version,
        provider=container.provider.name,
        kb_chunks=chunks,
    )
    yield
    log.info("shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return a configured FastAPI application."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    app = FastAPI(
        title="Store Chat Bot API",
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        lifespan=_lifespan,
    )
    app.state.settings = settings

    # --- Middleware (request context outermost) ---
    app.add_middleware(RequestContextMiddleware)
    if settings.security_headers_enabled:
        app.add_middleware(SecurityHeadersMiddleware)
    # Never advertise credentialed access alongside a wildcard origin: Starlette
    # would otherwise reflect any caller's Origin and allow credentials, letting
    # any site make authenticated cross-origin requests. With an explicit origin
    # allow-list, credentials are safe to enable.
    cors_origins = settings.cors_origin_list
    cors_allow_credentials = cors_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # --- Routers ---
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(webhooks.router)
    app.include_router(visual.router)
    app.include_router(widget.router)
    app.include_router(admin.router)

    return app


# Module-level app for ``uvicorn app.main:app``.
app = create_app()
