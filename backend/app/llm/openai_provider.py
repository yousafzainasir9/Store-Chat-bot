"""OpenAI adapter.

The ``openai`` SDK is imported lazily so the app (and the offline test suite)
runs without the dependency installed. Configure via ``OPENAI_API_KEY``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from app.llm.base import ChatChunk, ChatResult, LLMProvider, Message, Usage


class OpenAIProvider(LLMProvider):
    """LLMProvider backed by the OpenAI Chat Completions + Embeddings APIs."""

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIProvider")
        self.name = "openai"
        self._default_model = default_model
        self._embedding_model = embedding_model
        self._api_key = api_key
        self._client: object | None = None

    def _get_client(self) -> object:
        if self._client is None:
            from openai import AsyncOpenAI  # lazy import

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    @staticmethod
    def _to_openai(messages: Sequence[Message]) -> list[dict[str, str]]:
        return [{"role": m.role.value, "content": m.content} for m in messages]

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        client = self._get_client()
        resp = await client.chat.completions.create(  # type: ignore[attr-defined]
            model=model or self._default_model,
            messages=self._to_openai(messages),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0].message.content or ""
        usage = Usage(
            input_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "completion_tokens", 0) or 0,
        )
        return ChatResult(text=choice, model=resp.model, usage=usage)

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        client = self._get_client()
        stream = await client.chat.completions.create(  # type: ignore[attr-defined]
            model=model or self._default_model,
            messages=self._to_openai(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        usage = Usage()
        async for event in stream:
            if event.usage is not None:
                usage = Usage(
                    input_tokens=event.usage.prompt_tokens,
                    output_tokens=event.usage.completion_tokens,
                )
            if event.choices and event.choices[0].delta.content:
                yield ChatChunk(delta=event.choices[0].delta.content)
        yield ChatChunk(done=True, usage=usage)

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        client = self._get_client()
        resp = await client.embeddings.create(  # type: ignore[attr-defined]
            model=model or self._embedding_model,
            input=list(texts),
        )
        return [item.embedding for item in resp.data]
