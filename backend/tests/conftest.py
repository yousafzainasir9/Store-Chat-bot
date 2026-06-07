"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.config import Environment, Settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def settings() -> Settings:
    """Deterministic test settings (no external dependencies)."""
    return Settings(
        environment=Environment.TEST,
        demo_mode=True,
        log_json=False,
        database_url=None,
        redis_url=None,
        qdrant_url=None,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient wired to an app built from test settings."""
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
