"""Anthropic (Claude) adapter.

The ``anthropic`` SDK is imported lazily so the app (and the offline test suite)
runs without the dependency installed. Configure via ``ANTHROPIC_API_KEY`` and
``LLM_DEFAULT_PROVIDER=anthropic`` (or ``claude``).

Anthropic's Messages API differs from the OpenAI shape in two ways this adapter
normalises: the system prompt is a separate top-level argument (not a message),
and ``max_tokens`` is required. Anthropic has no embeddings endpoint, so
:meth:`embed` raises and the container falls back to the offline hashing
embedder (``EMBEDDING_BACKEND=auto``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from app.llm.base import ChatChunk, ChatResult, LLMProvider, Message, Role, Usage

# Anthropic requires an explicit max output token budget on every call.
_DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider(LLMProvider):
    """LLMProvider backed by the Anthropic Messages API (Claude models)."""

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "claude-3-5-sonnet-latest",
        name: str = "anthropic",
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for AnthropicProvider")
        self.name = name
        self._default_model = default_model
        self._api_key = api_key
        self._client: object | None = None

    def _get_client(self) -> object:
        if self._client is None:
            from anthropic import AsyncAnthropic  # lazy import

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    @staticmethod
    def _split(messages: Sequence[Message]) -> tuple[str | None, list[dict[str, str]]]:
        """Separate system text (top-level arg) from user/assistant turns."""
        system_parts: list[str] = []
        turns: list[dict[str, str]] = []
        for m in messages:
            if m.role is Role.SYSTEM:
                system_parts.append(m.content)
            elif m.role in (Role.USER, Role.ASSISTANT):
                turns.append({"role": m.role.value, "content": m.content})
            # TOOL-role messages are not used on the Anthropic path.
        system = "\n\n".join(system_parts) if system_parts else None
        return system, turns

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        client = self._get_client()
        system, turns = self._split(messages)
        resp = await client.messages.create(  # type: ignore[attr-defined]
            model=model or self._default_model,
            system=system or "",
            messages=turns,
            temperature=temperature,
            max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
        )
        text = "".join(getattr(block, "text", "") for block in resp.content)
        usage = Usage(
            input_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
        )
        return ChatResult(text=text, model=resp.model, usage=usage)

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        client = self._get_client()
        system, turns = self._split(messages)
        async with client.messages.stream(  # type: ignore[attr-defined]
            model=model or self._default_model,
            system=system or "",
            messages=turns,
            temperature=temperature,
            max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
        ) as stream:
            async for delta in stream.text_stream:
                if delta:
                    yield ChatChunk(delta=delta)
            final = await stream.get_final_message()
        usage = Usage(
            input_tokens=getattr(final.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(final.usage, "output_tokens", 0) or 0,
        )
        yield ChatChunk(done=True, usage=usage)

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        raise NotImplementedError("Anthropic does not provide an embeddings API")
