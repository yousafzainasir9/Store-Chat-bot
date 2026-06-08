"""In-memory store for the merchant-managed widget configuration.

A single :class:`WidgetConfig` seeded from settings. Process-local — for a shared
config across replicas (and persistence across restarts) back this with Postgres
or Redis behind the same ``get``/``update`` interface.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.config import Settings
from app.models.widget_config import WidgetConfig

_ALLOWED_POSITIONS = {"left", "right"}


class WidgetConfigStore:
    """Holds and updates the active widget configuration."""

    def __init__(self, config: WidgetConfig) -> None:
        self._config = config

    @classmethod
    def from_settings(cls, settings: Settings) -> WidgetConfigStore:
        return cls(WidgetConfig(store_name=settings.store_name))

    def get(self) -> WidgetConfig:
        return self._config

    def update(
        self,
        *,
        store_name: str | None = None,
        primary_color: str | None = None,
        position: str | None = None,
        locale: str | None = None,
        greeting: str | None = None,
        show_image_upload: bool | None = None,
    ) -> WidgetConfig:
        c = self._config
        if store_name is not None:
            c.store_name = store_name
        if primary_color is not None:
            c.primary_color = primary_color
        if position is not None:
            if position not in _ALLOWED_POSITIONS:
                raise ValueError("position must be 'left' or 'right'")
            c.position = position
        if locale is not None:
            c.locale = locale
        if greeting is not None:
            c.greeting = greeting
        if show_image_upload is not None:
            c.show_image_upload = show_image_upload
        c.updated_at = datetime.now(UTC)
        return c
