"""Groq adapter.

Groq exposes an **OpenAI-compatible** Chat Completions API, so this reuses the
OpenAI adapter pointed at Groq's base URL. Groq does not offer an embeddings API,
so :meth:`embed` raises ``NotImplementedError`` — the fallback chain skips a Groq
provider for embedding calls and uses an embedding-capable provider instead.

Configure one or more Groq entries (e.g. three free-tier keys) via ``LLM_CHAIN``;
see CONFIGURATION.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.llm.openai_provider import OpenAIProvider

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_DEFAULT_MODEL = "llama-3.1-8b-instant"


class GroqProvider(OpenAIProvider):
    """LLMProvider backed by Groq's OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str | None = None,
        base_url: str | None = None,
        name: str = "groq",
    ) -> None:
        super().__init__(
            api_key,
            default_model=default_model or _DEFAULT_MODEL,
            base_url=base_url or _GROQ_BASE_URL,
            name=name,
        )

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        raise NotImplementedError("Groq does not provide an embeddings API")
