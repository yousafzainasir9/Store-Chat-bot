"""Tests for the versioned prompt registry."""

from __future__ import annotations

import pytest
from app.core.prompts import PromptError, PromptRegistry, PromptTemplate, registry


def test_default_system_prompt_registered() -> None:
    tpl = registry.get("system")
    assert tpl.version >= 1
    rendered = tpl.render(store_name="Acme Threads")
    assert "Acme Threads" in rendered


def test_missing_variable_raises() -> None:
    tpl = PromptTemplate(name="x", version=1, template="hi {who}")
    with pytest.raises(PromptError):
        tpl.render()


def test_register_activate_and_resolve() -> None:
    reg = PromptRegistry()
    reg.register(PromptTemplate("greet", 1, "v1"), activate=True)
    reg.register(PromptTemplate("greet", 2, "v2"), activate=False)
    assert reg.get("greet").template == "v1"  # active stays v1
    reg.activate("greet", 2)
    assert reg.get("greet").template == "v2"
    assert reg.versions("greet") == [1, 2]


def test_duplicate_version_rejected() -> None:
    reg = PromptRegistry()
    reg.register(PromptTemplate("a", 1, "x"))
    with pytest.raises(PromptError):
        reg.register(PromptTemplate("a", 1, "y"))
