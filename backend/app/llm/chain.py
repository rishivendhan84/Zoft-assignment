"""Provider chain: timeout → retry with backoff → circuit breaker → failover.

Order is [Anthropic (if key configured), Scripted]. Each call walks the chain,
skipping providers whose breaker is open; the first success wins. The scripted
provider is the deterministic anchor at the end, so 'every provider down' is
only reachable when a demo lever forces it — and then the run still fails
*cleanly* (error + done events, nothing persisted).
"""

import asyncio
import time
from typing import AsyncIterator, Awaitable, Callable

from ..config import get_settings
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider, ProviderError, ProviderTimeout
from .scripted import ScriptedProvider


class CircuitBreaker:
    def __init__(self, threshold: int, cooldown: float):
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.cooldown:
            self.opened_at = None  # half-open: allow a probe call
            self.failures = self.threshold - 1
            return False
        return True

    def record(self, ok: bool) -> None:
        if ok:
            self.failures = 0
            self.opened_at = None
        else:
            self.failures += 1
            if self.failures >= self.threshold:
                self.opened_at = time.monotonic()


class ProviderChain:
    def __init__(self, providers: list[LLMProvider],
                 on_event: Callable[[dict], Awaitable[None]] | None = None):
        s = get_settings()
        self.providers = providers
        self.timeout = s.llm_timeout_seconds
        self.breakers = {
            p.name: CircuitBreaker(
                s.circuit_breaker_threshold, s.circuit_breaker_cooldown_seconds)
            for p in providers
        }
        self.on_event = on_event

    async def _notify(self, data: dict) -> None:
        if self.on_event:
            await self.on_event(data)

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        last_error: Exception | None = None
        for provider in self.providers:
            breaker = self.breakers[provider.name]
            if breaker.open:
                await self._notify({"provider": provider.name, "status": "circuit_open"})
                continue
            for attempt in range(2):  # one retry with backoff per provider
                try:
                    result = await asyncio.wait_for(
                        provider.complete(system, user, json_mode),
                        timeout=self.timeout,
                    )
                    breaker.record(ok=True)
                    return result
                except (ProviderError, asyncio.TimeoutError) as e:
                    last_error = e if isinstance(e, ProviderError) else ProviderTimeout(
                        f"{provider.name}: timed out after {self.timeout}s")
                    breaker.record(ok=False)
                    await self._notify({
                        "provider": provider.name,
                        "status": "retrying" if attempt == 0 else "failing_over",
                        "error": str(last_error),
                    })
                    if attempt == 0:
                        await asyncio.sleep(0.5 * (attempt + 1))
        raise last_error or ProviderError("no providers configured", recoverable=False)

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        last_error: Exception | None = None
        for provider in self.providers:
            breaker = self.breakers[provider.name]
            if breaker.open:
                continue
            try:
                async for token in provider.stream(system, user):
                    yield token
                breaker.record(ok=True)
                return
            except ProviderError as e:
                last_error = e
                breaker.record(ok=False)
                await self._notify({
                    "provider": provider.name, "status": "failing_over", "error": str(e),
                })
        raise last_error or ProviderError("no providers configured", recoverable=False)


def build_chain(on_event=None) -> ProviderChain:
    s = get_settings()
    providers: list[LLMProvider] = []
    if s.anthropic_api_key:
        providers.append(AnthropicProvider(
            s.anthropic_api_key, s.anthropic_model, s.llm_timeout_seconds))
    providers.append(ScriptedProvider())
    return ProviderChain(providers, on_event=on_event)
