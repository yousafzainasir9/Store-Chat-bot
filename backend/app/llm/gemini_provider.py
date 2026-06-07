"""Google Gemini adapter.

The ``google-generativeai`` SDK is imported lazily. Configure via
``GEMINI_API_KEY``. Gemini's SDK is sync; calls are offloaded to a thread so the
async interface contract holds.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from app.llm.base import ChatChunk, ChatResult, LLMProvider, Message, Role, Usage


class GeminiProvider(LLMProvider):
    """LLMProvider backed by Google Gemini."""

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "gemini-2.5-flash",
        embedding_model: str = "text-embedding-004",
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiProvider")
        self.name = "gemini"
        self._default_model = default_model
        self._embedding_model = embedding_model
        self._api_key = api_key
        self._configured = False

    def _ensure_configured(self) -> object:
        import google.generativeai as genai  # lazy import

        if not self._configured:
            genai.configure(api_key=self._api_key)
            self._configured = True
        return genai

    @staticmethod
    def _to_gemini(messages: Sequence[Message]) -> tuple[str | None, list[dict[str, object]]]:
        """Split out the system instruction; map roles to Gemini's schema."""
        system = next((m.content for m in messages if m.role is Role.SYSTEM), None)
        history: list[dict[str, object]] = []
        for m in messages:
            if m.role is Role.SYSTEM:
                continue
            role = "model" if m.role is Role.ASSISTANT else "user"
            history.append({"role": role, "parts": [m.content]})
        return system, history

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        genai = self._ensure_configured()
        system, history = self._to_gemini(messages)

        def _call() -> ChatResult:
            gen_model = genai.GenerativeModel(  # type: ignore[attr-defined]
                model_name=model or self._default_model,
                system_instruction=system,
            )
            resp = gen_model.generate_content(
                history,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            um = getattr(resp, "usage_metadata", None)
            usage = Usage(
                input_tokens=getattr(um, "prompt_token_count", 0) or 0,
                output_tokens=getattr(um, "candidates_token_count", 0) or 0,
            )
            return ChatResult(text=resp.text, model=model or self._default_model, usage=usage)

        return await asyncio.to_thread(_call)

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        # Gemini streaming is sync-iterable; for simplicity and reliability we
        # produce a single completion then chunk it. Real token streaming can be
        # added with a thread-bridged queue if first-token latency demands it.
        result = await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        for word in result.text.split(" "):
            yield ChatChunk(delta=word + " ")
        yield ChatChunk(done=True, usage=result.usage)

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        genai = self._ensure_configured()

        def _call() -> list[list[float]]:
            out: list[list[float]] = []
            for t in texts:
                r = genai.embed_content(  # type: ignore[attr-defined]
                    model=model or self._embedding_model, content=t
                )
                out.append(r["embedding"])
            return out

        return await asyncio.to_thread(_call)
