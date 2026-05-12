# Author: Bradley R. Kinnard
"""BeliefEventBus implementations.

Three implementations ship:

* :class:`RedisBeliefEventBus` — production. Publishes to Redis pubsub
  on ``BELIEF_EVENT_CHANNEL``. Subscribers (the ``/ui/events/stream``
  WebSocket) call :meth:`subscribe` to get an async iterator of
  decoded events. Connection errors degrade to no-op for the failing
  call, so a broken broker cannot break belief writes.
* :class:`InMemoryBeliefEventBus` — test and single-process. Uses
  ``asyncio.Queue`` per subscriber. Useful for the integration
  tests and for setups where Redis is not available.
* :class:`NullBeliefEventBus` — explicit no-op. The default the
  Settings layer uses when no bus is configured.

All three implement the same :class:`BeliefEventBus` Protocol so
callers can be agnostic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


BELIEF_EVENT_CHANNEL = "ironroot.beliefs"
"""Redis pubsub channel name.

Single channel for now — the event payload carries ``run_id`` so a
client can filter. Splitting per-run channels is a future optimization
that buys nothing until the UI has multiple concurrent operators.
"""


class BeliefEventBus(ABC):
    """Abstract publish/subscribe surface for belief append events."""

    @abstractmethod
    async def publish(self, event: dict[str, Any]) -> None:
        """Fire-and-forget publish. Errors degrade to logging."""

    @abstractmethod
    def subscribe(self) -> AbstractSubscription:
        """Returns a context-manager that yields an async iterator of events."""

    async def close(self) -> None:  # pragma: no cover - default no-op
        """Releases bus-level resources. Subclasses override."""
        return None


class AbstractSubscription:
    """Async context manager around an event iterator.

    Used as::

        async with bus.subscribe() as events:
            async for event in events:
                ...
    """

    async def __aenter__(self) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        raise NotImplementedError


class NullBeliefEventBus(BeliefEventBus):
    """Drops every publish on the floor. Subscribers see no events."""

    async def publish(self, event: dict[str, Any]) -> None:
        return None

    def subscribe(self) -> AbstractSubscription:
        return _NullSubscription()


class _NullSubscription(AbstractSubscription):
    async def __aenter__(self) -> AsyncIterator[dict[str, Any]]:
        async def _empty() -> AsyncIterator[dict[str, Any]]:
            if False:  # pragma: no cover
                yield {}
            return

        return _empty()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class InMemoryBeliefEventBus(BeliefEventBus):
    """Single-process pub/sub via per-subscriber asyncio.Queue.

    Every active subscription gets a copy of every published event.
    Backpressure: queues are unbounded by default; in test
    contexts that's fine, and in single-process production
    deployments the worker that's publishing is also the one
    consuming.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []
        self._lock = asyncio.Lock()

    async def publish(self, event: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - unbounded by default
                logger.warning("dropping belief event for full in-memory queue")

    def subscribe(self) -> AbstractSubscription:
        return _InMemorySubscription(self)

    async def _register(self, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        async with self._lock:
            self._subscribers.append(queue)

    async def _unregister(self, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        import contextlib

        async with self._lock:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(queue)


class _InMemorySubscription(AbstractSubscription):
    def __init__(self, bus: InMemoryBeliefEventBus) -> None:
        self._bus = bus
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def __aenter__(self) -> AsyncIterator[dict[str, Any]]:
        await self._bus._register(self._queue)
        return self._iter()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        import contextlib

        await self._bus._unregister(self._queue)
        # Sentinel: ensure any in-flight iterator wakes.
        with contextlib.suppress(asyncio.QueueFull):  # pragma: no cover
            self._queue.put_nowait(None)

    async def _iter(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item


class RedisBeliefEventBus(BeliefEventBus):
    """Production publisher backed by Redis pubsub.

    ``redis.asyncio.Redis`` is imported lazily so unit tests that
    don't touch this class never need the redis client at import
    time.
    """

    def __init__(self, redis_url: str, channel: str = BELIEF_EVENT_CHANNEL) -> None:
        self._redis_url = redis_url
        self._channel = channel
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()
        self._warned_unreachable = False

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                from redis import asyncio as redis_asyncio

                self._client = redis_asyncio.from_url(self._redis_url)
        return self._client

    async def publish(self, event: dict[str, Any]) -> None:
        try:
            client = await self._get_client()
            await client.publish(self._channel, json.dumps(event, default=str))
        except Exception as exc:
            # Belief append must not fail because the broker is down.
            # First failure logs at WARNING; subsequent failures are
            # debug-level to avoid flooding the log.
            if not self._warned_unreachable:
                self._warned_unreachable = True
                logger.warning("redis pubsub unreachable: %s — dropping events", exc)
            else:
                logger.debug("redis pubsub publish failed: %s", exc)

    def subscribe(self) -> AbstractSubscription:
        return _RedisSubscription(self._redis_url, self._channel)

    async def close(self) -> None:
        import contextlib

        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.aclose()
            self._client = None


class _RedisSubscription(AbstractSubscription):
    def __init__(self, redis_url: str, channel: str) -> None:
        self._redis_url = redis_url
        self._channel = channel
        self._client: Any | None = None
        self._pubsub: Any | None = None

    async def __aenter__(self) -> AsyncIterator[dict[str, Any]]:
        from redis import asyncio as redis_asyncio

        self._client = redis_asyncio.from_url(self._redis_url)
        self._pubsub = self._client.pubsub()
        await self._pubsub.subscribe(self._channel)
        return self._iter()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        import contextlib

        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.unsubscribe(self._channel)
                await self._pubsub.aclose()
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.aclose()

    async def _iter(self) -> AsyncIterator[dict[str, Any]]:
        assert self._pubsub is not None
        while True:
            message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                # No message in this window; yield control and loop.
                await asyncio.sleep(0)
                continue
            payload = message.get("data")
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", errors="replace")
            try:
                yield json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                # Drop malformed events rather than killing the stream.
                continue


_bus: BeliefEventBus | None = None
_bus_lock = asyncio.Lock()


def get_belief_event_bus() -> BeliefEventBus:
    """Returns the process-wide bus. Constructs a Redis-backed bus the
    first time it's called against the configured ``IRONROOT_REDIS_*``
    URL; tests override via :func:`set_belief_event_bus`.
    """
    global _bus
    if _bus is not None:
        return _bus
    from ironroot.settings import get_settings

    settings = get_settings()
    _bus = RedisBeliefEventBus(settings.redis_url)
    return _bus


def set_belief_event_bus(bus: BeliefEventBus) -> None:
    """Override hook for tests."""
    global _bus
    _bus = bus


def reset_belief_event_bus() -> None:
    """Drops the singleton so the next ``get_belief_event_bus`` rebuilds."""
    global _bus
    _bus = None


@asynccontextmanager
async def _suppress_publish_errors() -> AsyncIterator[None]:
    """Internal helper; keeps publish errors from propagating."""
    try:
        yield
    except Exception as exc:
        logger.debug("belief event publish failed: %s", exc)
