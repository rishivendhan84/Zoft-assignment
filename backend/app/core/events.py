"""Run event bus: publish agent progress, subscribe from the SSE endpoint.

Two implementations behind one interface:
  • InMemoryEventBus — default; per-run buffer gives Last-Event-ID replay.
  • RedisEventBus   — set REDIS_URL; events RPUSHed to a list (replay) and
    PUBLISHed to a channel (live). This is the seam where the agent run moves
    to a separate worker process in production — the API only needs the bus.
"""

import asyncio
import json
from collections import OrderedDict
from typing import AsyncIterator

try:
    import redis.asyncio as aioredis
except ImportError:  # redis is optional
    aioredis = None

TERMINAL_EVENT = "done"
KEEPALIVE_SECONDS = 30
BUFFER_TTL_SECONDS = 3600
MAX_BUFFERED_RUNS = 500


class EventBus:
    async def publish(self, run_id: str, event: str, data: dict) -> None:
        raise NotImplementedError

    async def count(self, run_id: str) -> int:
        """Number of buffered events for a run (0 ⇒ nothing to replay)."""
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
        # OrderedDict as an LRU: bounded even if 'done' eviction never fires
        self._buffers: OrderedDict[str, list[dict]] = OrderedDict()
        self._conds: dict[str, asyncio.Condition] = {}

    def _cond(self, run_id: str) -> asyncio.Condition:
        return self._conds.setdefault(run_id, asyncio.Condition())

    def _evict(self, run_id: str) -> None:
        self._buffers.pop(run_id, None)
        self._conds.pop(run_id, None)

    async def publish(self, run_id: str, event: str, data: dict) -> None:
        buf = self._buffers.setdefault(run_id, [])
        self._buffers.move_to_end(run_id)
        while len(self._buffers) > MAX_BUFFERED_RUNS:
            self._buffers.popitem(last=False)
        cond = self._cond(run_id)
        async with cond:
            buf.append({"id": len(buf) + 1, "event": event, "data": data})
            cond.notify_all()
        if event == TERMINAL_EVENT:
            # keep the buffer around for late reconnect replay, then drop it
            asyncio.get_running_loop().call_later(
                BUFFER_TTL_SECONDS, self._evict, run_id)

    async def count(self, run_id: str) -> int:
        return len(self._buffers.get(run_id, []))

    async def subscribe(
        self, run_id: str, last_event_id: int | None = None
    ) -> AsyncIterator[dict]:
        cursor = last_event_id or 0
        cond = self._cond(run_id)
        while True:
            buf = self._buffers.get(run_id, [])
            while cursor < len(buf):
                item = buf[cursor]
                cursor += 1
                yield item
                if item["event"] == TERMINAL_EVENT:
                    return
            idle = False
            async with cond:
                # re-check under the lock so a publish between the drain above
                # and this wait can never be missed
                if cursor >= len(self._buffers.get(run_id, [])):
                    try:
                        await asyncio.wait_for(cond.wait(),
                                               timeout=KEEPALIVE_SECONDS)
                    except asyncio.TimeoutError:
                        idle = True
            if idle:  # yielded outside the lock so publishers never block
                yield {"id": cursor, "event": "ping", "data": {}}


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
            pipe.expire(key, BUFFER_TTL_SECONDS)
            pipe.publish(key, "1")
            await pipe.execute()

    async def count(self, run_id: str) -> int:
        return await self._redis.llen(self._key(run_id))

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
                # get_message returns None on timeout (it does not raise)
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=KEEPALIVE_SECONDS)
                if msg is None:
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
