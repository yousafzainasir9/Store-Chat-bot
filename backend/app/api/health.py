"""Health, readiness, and metrics endpoints.

``/health``   — liveness: process is up (cheap, no external deps).
``/ready``    — readiness: external dependencies reachable (best-effort).
``/metrics``  — in-process metric snapshot + declared SLOs (Phase 0 baseline).

These power container orchestration probes and the observability baseline.

Settings are read directly from ``request.app.state`` rather than via a
``Depends`` because FastAPI would otherwise try to construct the
``BaseSettings`` model from the request itself. Pulling from app state keeps the
handler bound to the settings the app was created with (and testable).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import get_app_settings
from app.observability.metrics import SLOS, metrics

router = APIRouter(tags=["ops"])


@router.get("/health", summary="Liveness probe")
async def health(request: Request) -> dict[str, Any]:
    """Return liveness status. Always cheap; never touches external services."""
    settings = get_app_settings(request)
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment.value,
        "demo_mode": settings.demo_mode,
    }


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request) -> dict[str, Any]:
    """Report whether configured dependencies appear wired.

    In Phase 0 nothing is required, so readiness reflects only what is
    *configured*. Later phases add live pings (Postgres/Redis/Qdrant).
    """
    settings = get_app_settings(request)
    checks = {
        "database": settings.database_url is not None,
        "redis": settings.redis_url is not None,
        "qdrant": settings.qdrant_url is not None,
    }
    return {"status": "ok", "checks": checks}


@router.get("/metrics", summary="Metrics snapshot + SLO targets")
async def metrics_snapshot() -> dict[str, Any]:
    """Expose the in-process metric snapshot and declared SLO targets."""
    return {
        "metrics": metrics.snapshot(),
        "slos": [{"name": s.name, "description": s.description, "target": s.target} for s in SLOS],
    }


@router.get("/ops/freshness", summary="Active catalog freshness posture")
async def freshness(request: Request) -> dict[str, Any]:
    """Expose the resolved, read-only catalog freshness posture (plan §7)."""
    posture = request.app.state.container.freshness
    return {
        "profile": posture.profile,
        "stock_source": posture.stock_source,
        "price_resolution": posture.price_resolution,
        "catalog_sync_mode": posture.catalog_sync_mode,
        "reconcile_delta_interval": posture.reconcile_delta_interval,
        "reconcile_full_interval": posture.reconcile_full_interval,
        "stock_low_threshold": posture.stock_low_threshold,
        "failsafe_on_api_error": posture.failsafe_on_api_error,
    }
