"""Tests for configuration validation."""

from __future__ import annotations

import pytest
from app.config import Environment, Settings, SyncProfile
from pydantic import ValidationError


def test_cors_origin_list_parsing() -> None:
    s = Settings(cors_origins="https://a.com, https://b.com ,")
    assert s.cors_origin_list == ["https://a.com", "https://b.com"]


def test_debug_forbidden_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(environment=Environment.PRODUCTION, debug=True)


def test_defaults_are_safe() -> None:
    s = Settings()
    assert s.demo_mode is True
    assert s.sync_profile is SyncProfile.BALANCED
    assert s.is_production is False
    assert s.per_session_token_budget > 0
