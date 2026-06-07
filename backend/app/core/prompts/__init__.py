"""Versioned, eval-gated prompt registry.

Prompts are treated as code (see DEVELOPMENT_PLAN.md §5, §9): every template is
versioned, and a prompt change must pass the eval gate before it is allowed to
deploy. This module provides:

* :class:`PromptTemplate` — an immutable, named, versioned template.
* :class:`PromptRegistry` — registers templates and resolves the active version.
* a default registry pre-seeded with the Phase-0 system prompt.

In Phase 1 the orchestrator pulls its system/answer prompts from here, and the
eval harness asserts that the active version passes thresholds before deploy.
"""

from __future__ import annotations

from dataclasses import dataclass


class PromptError(Exception):
    """Raised on prompt registration or resolution errors."""


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """An immutable, versioned prompt template.

    Attributes:
        name: Logical name (e.g. ``"system"``, ``"grounded_answer"``).
        version: Monotonically increasing integer version.
        template: The template body; ``render`` fills ``{placeholders}``.
        description: Human note on what changed / why.
    """

    name: str
    version: int
    template: str
    description: str = ""

    def render(self, **kwargs: object) -> str:
        """Render the template, substituting ``{name}`` placeholders.

        Raises:
            PromptError: if a referenced placeholder is missing.
        """
        try:
            return self.template.format(**kwargs)
        except KeyError as exc:  # missing placeholder
            raise PromptError(
                f"Missing variable {exc} rendering prompt '{self.name}' v{self.version}"
            ) from exc


class PromptRegistry:
    """Registers prompt templates and resolves the active version per name."""

    def __init__(self) -> None:
        # name -> {version -> template}
        self._templates: dict[str, dict[int, PromptTemplate]] = {}
        # name -> active version
        self._active: dict[str, int] = {}

    def register(self, template: PromptTemplate, *, activate: bool = True) -> None:
        """Register a template version, optionally marking it active."""
        versions = self._templates.setdefault(template.name, {})
        if template.version in versions:
            raise PromptError(f"Prompt '{template.name}' v{template.version} already registered")
        versions[template.version] = template
        if activate or template.name not in self._active:
            self._active[template.name] = template.version

    def activate(self, name: str, version: int) -> None:
        """Mark a specific registered version as active (post eval-gate)."""
        if version not in self._templates.get(name, {}):
            raise PromptError(f"Prompt '{name}' v{version} is not registered")
        self._active[name] = version

    def get(self, name: str, version: int | None = None) -> PromptTemplate:
        """Return a template by name; the active version unless one is given."""
        versions = self._templates.get(name)
        if not versions:
            raise PromptError(f"No prompt registered under '{name}'")
        resolved = version if version is not None else self._active[name]
        try:
            return versions[resolved]
        except KeyError as exc:
            raise PromptError(f"Prompt '{name}' v{resolved} not found") from exc

    def versions(self, name: str) -> list[int]:
        """Return all registered versions for a prompt name, ascending."""
        return sorted(self._templates.get(name, {}))


# --- Default registry, seeded with the Phase-0 grounded-only system prompt. ---
registry = PromptRegistry()

registry.register(
    PromptTemplate(
        name="system",
        version=1,
        description="Phase 0 baseline: grounded-only, cite sources, handoff on low confidence.",
        template=(
            "You are the AI customer-support assistant for {store_name}, a fashion and "
            "clothing store. Answer ONLY from the provided sources and tool results. "
            "If the answer is not supported by a source, say you are not sure and offer "
            "to connect the customer to a human. Never invent prices, stock, or policies. "
            "Always cite the source for any factual claim. Be concise, warm, and helpful."
        ),
    )
)
