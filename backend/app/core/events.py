"""Run event bus: publish agent progress, subscribe from the SSE endpoint.

Two implementations behind one interface:
  • InMemoryEventBus — default; per-run buffer gives Last-Event-ID replay.
  • RedisEventBus   — set REDIS_URL; events RPUSHed to a list (replay) and
    PUBLISHed to a channel (live). This is the seam where the agent run moves
    to a separate worker process in production — the API only needs the bus.
"""

import asyncio
import json
from typing import AsyncIterator

try:
    import redis.asyncio as aioredis
except ImportError:  # redis is optional
    aioredis = None

TERMINAL_EVENT = "done"


class EventBus:
    async def publish(self, run_id: str, event: str, data: dict) -> None:
        raise NotImplementedError

    async def subscribe(
        self, run_id: str, last_event_id: int | None = None
    ) -> AsyncIterator[dict]:
        """Yield {'id', 'event', 'data'} dicts; replay from last_event_id,
        then live until (and including) the terminal 'done' event."""
        raise NotImplementedError
        yield  # pragma: no cover


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._buffers: dict[str, list[dict]] = {}
        self._signals: dict[str, asyncio.Event] = {}

    def _signal(self, run_id: str) -> asyncio.Event:
        return self._signals.setdefault(run_id, asyncio.Event())

    async def publish(self, run_id: str, event: str, data: dict) -> None:
        buf = self._buffers.setdefault(run_id, [])
        buf.append({"id": len(buf) + 1, "event": event, "data": data})
        sig = self._signal(run_id)
        sig.set()
        sig.clear()

    async def subscribe(
        self, run_id: str, last_event_id: int | None = None
    ) -> AsyncIterator[dict]:
        cursor = last_event_id or 0
        while True:
            buf = self._buffers.get(run_id, [])
            while cursor < len(buf):
                item = buf[cursor]
                cursor += 1
                yield item
                if item["event"] == TERMINAL_EVENT:
                    return
            try:
                await asyncio.wait_for(self._signal(run_id).wait(), timeout=30)
            except asyncio.TimeoutError:
                yield {"id": cursor, "event": "ping", "data": {}}  # keep-alive


class RedisEventBus(EventBus):
    def __init__(self, url: str) -> None:
        if aioredis is None:
            raise RuntimeError("redis package not installed")
        self._redis = aioredis.from_url(url, decode_responses=True)

    def _key(self, run_id: str) -> str:
        return f"run:{run_id}:events"

    async def publish(self, run_id: str, event: str, data: dict) -> None:
        key = self._key(run_id)
        entry = {"event": event, "data": data}
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, json.dumps(entry))
            pipe.expire(key, 3600)
            pipe.publish(key, "1")
            await pipe.execute()

    async def subscribe(
        self, run_id: str, last_event_id: int | None = None
    ) -> AsyncIterator[dict]:
        key = self._key(run_id)
        cursor = last_event_id or 0
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(key)
        try:
            while True:
                raw = await self._redis.lrange(key, cursor, -1)
                for offset, item in enumerate(raw):
                    entry = json.loads(item)
                    entry["id"] = cursor + offset + 1
                    yield entry
                    if entry["event"] == TERMINAL_EVENT:
                        return
                cursor += len(raw)
                try:
                    await asyncio.wait_for(pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=30
                    ), timeout=31)
                except asyncio.TimeoutError:
                    yield {"id": cursor, "event": "ping", "data": {}}
        finally:
            await pubsub.unsubscribe(key)
            await pubsub.aclose()


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        from ..config import get_settings

        url = get_settings().redis_url
        _bus = RedisEventBus(url) if url else InMemoryEventBus()
    return _bus
