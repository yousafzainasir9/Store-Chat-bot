"""Catalog freshness posture (DEVELOPMENT_PLAN.md §7).

Resolves a :class:`SyncProfile` preset (``realtime`` / ``balanced`` / ``eco``)
into a concrete, read-only posture: where each data type is sourced from and how
often reconciliation runs. The principle is fixed regardless of profile —
volatile values (stock quantity, final price) are resolved *live* at answer time
and never served from the index; descriptive catalog content is webhook-synced.

The resolved posture is surfaced read-only in the admin dashboard (Phase 7).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, SyncProfile


@dataclass(frozen=True, slots=True)
class FreshnessPosture:
    """The active, resolved freshness configuration."""

    profile: str
    stock_source: str
    price_resolution: str
    catalog_sync_mode: str
    reconcile_delta_interval: str
    reconcile_full_interval: str
    stock_low_threshold: int
    failsafe_on_api_error: bool


# Profile presets. Explicit per-field env overrides win over these.
_PRESETS: dict[SyncProfile, dict[str, str]] = {
    SyncProfile.REALTIME: {
        "stock_source": "live",
        "price_resolution": "live",
        "reconcile_delta_interval": "15m",
        "reconcile_full_interval": "24h",
    },
    SyncProfile.BALANCED: {
        "stock_source": "live",
        "price_resolution": "live",
        "reconcile_delta_interval": "1h",
        "reconcile_full_interval": "24h",
    },
    SyncProfile.ECO: {
        "stock_source": "live",
        "price_resolution": "live",
        "reconcile_delta_interval": "6h",
        "reconcile_full_interval": "24h",
    },
}

# Accepted reconcile cadence tokens; validated so a typo fails fast at startup.
_VALID_INTERVALS = frozenset({"15m", "30m", "1h", "6h", "12h", "24h"})


def resolve_posture(settings: Settings) -> FreshnessPosture:
    """Resolve the active freshness posture from settings + profile preset."""
    preset = _PRESETS[settings.sync_profile]
    delta = settings.reconcile_delta_interval or preset["reconcile_delta_interval"]
    full = settings.reconcile_full_interval or preset["reconcile_full_interval"]
    for label, value in (("delta", delta), ("full", full)):
        if value not in _VALID_INTERVALS:
            raise ValueError(
                f"reconcile_{label}_interval={value!r} is invalid; "
                f"expected one of {sorted(_VALID_INTERVALS)}"
            )
    return FreshnessPosture(
        profile=settings.sync_profile.value,
        stock_source=settings.stock_source or preset["stock_source"],
        price_resolution=settings.price_resolution or preset["price_resolution"],
        catalog_sync_mode=settings.catalog_sync_mode,
        reconcile_delta_interval=delta,
        reconcile_full_interval=full,
        stock_low_threshold=settings.stock_low_threshold,
        failsafe_on_api_error=settings.failsafe_on_api_error,
    )
