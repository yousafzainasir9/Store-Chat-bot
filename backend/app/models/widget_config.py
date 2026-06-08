"""Merchant-managed widget configuration (branding + behavior).

Edited in the admin dashboard, served publicly to the embedded widget so changes
apply live without re-pasting the embed snippet. Contains no secrets — only
public branding/behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class WidgetConfig:
    """Public widget branding/behavior settings."""

    store_name: str
    primary_color: str = "#1f6feb"
    position: str = "right"  # "left" | "right"
    locale: str = "en"  # "en" | "es" | "fr"
    greeting: str = ""  # optional opening assistant message
    show_image_upload: bool = True
    updated_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.updated_at is None:
            self.updated_at = _now()
