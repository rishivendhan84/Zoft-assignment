from typing import AsyncIterator

import anthropic

from .base import LLMProvider, ProviderError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0):
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)
        self._model = model

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        if json_mode:
            system += "\nRespond with a single JSON object only — no prose, no fences."
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=8192,  # headroom: thinking tokens count against this
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as e:  # includes timeouts/5xx
            raise ProviderError(f"anthropic: {e}") from e
        if resp.stop_reason == "max_tokens":
            # a truncated JSON plan must fail loudly, not parse mysteriously
            raise ProviderError("anthropic: response truncated at max_tokens")
        text = "".join(b.text for b in resp.content if b.type == "text")
        if json_mode:
            # models occasionally fence JSON despite instructions
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return text.strip()

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                async for token in stream.text_stream:
                    yield token
        except anthropic.APIError as e:
            raise ProviderError(f"anthropic: {e}") from e
