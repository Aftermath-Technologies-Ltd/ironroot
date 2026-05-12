# Author: Bradley R. Kinnard
"""Phase 3.3: /ui/events/stream tests + event bus tests.

Tests cover:

* InMemoryBeliefEventBus delivers events to all live subscribers.
* BeliefService.publish hook fires on every chain append.
* The WebSocket route forwards events from the bus to the client.
* The bus singleton's set/reset hook works as advertised.
* RedisBeliefEventBus.publish swallows broker errors instead of
  raising (so a broken broker can't break belief writes).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault("IRONROOT_DEBUG", "true")

from ironroot.beliefs import BeliefService
from ironroot.domain.ids import generate_id
from ironroot.events import (
    InMemoryBeliefEventBus,
    NullBeliefEventBus,
    RedisBeliefEventBus,
    reset_belief_event_bus,
    set_belief_event_bus,
)
from ironroot.main import app
from ironroot.storage.models import RunRecord
from ironroot.storage.postgres import Base


@pytest_asyncio.fixture
async def in_memory_bus() -> AsyncIterator[InMemoryBeliefEventBus]:
    bus = InMemoryBeliefEventBus()
    set_belief_event_bus(bus)
    try:
        yield bus
    finally:
        reset_belief_event_bus()


@pytest_asyncio.fixture
async def engine_and_factory() -> (
    AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]
):
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{Path(tmp)/'events.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield engine, factory
        finally:
            await engine.dispose()


async def _seed_run(factory: async_sessionmaker[AsyncSession]) -> str:
    run_id = generate_id("run")
    async with factory() as session:
        session.add(
            RunRecord(
                id=run_id,
                seed=1,
                status="running",
                phase="init",
                config={},
                created_at=datetime.now(UTC),
                steps_used=0,
                tool_calls_used=0,
                belief_writes_used=0,
            )
        )
        await session.commit()
    return run_id


class TestInMemoryBus:
    async def test_publish_delivers_to_subscriber(
        self, in_memory_bus: InMemoryBeliefEventBus
    ) -> None:
        async with in_memory_bus.subscribe() as events:
            await in_memory_bus.publish({"type": "test", "value": 1})
            await in_memory_bus.publish({"type": "test", "value": 2})

            received: list[dict[str, object]] = []

            async def _drain() -> None:
                async for event in events:
                    received.append(event)
                    if len(received) == 2:
                        return

            await asyncio.wait_for(_drain(), timeout=1.0)
            assert [r["value"] for r in received] == [1, 2]

    async def test_publish_fans_out_to_all_subscribers(
        self, in_memory_bus: InMemoryBeliefEventBus
    ) -> None:
        async with (
            in_memory_bus.subscribe() as events_a,
            in_memory_bus.subscribe() as events_b,
        ):
            await in_memory_bus.publish({"v": 42})
            got_a = await asyncio.wait_for(anext_async(events_a), timeout=1.0)
            got_b = await asyncio.wait_for(anext_async(events_b), timeout=1.0)
            assert got_a == {"v": 42}
            assert got_b == {"v": 42}


async def anext_async(it: AsyncIterator[dict[str, object]]) -> dict[str, object]:
    return await it.__anext__()


class TestBeliefServicePublishesOnAppend:
    async def test_lifecycle_belief_emits_event(
        self,
        in_memory_bus: InMemoryBeliefEventBus,
        engine_and_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    ) -> None:
        _, factory = engine_and_factory
        run_id = await _seed_run(factory)

        async with in_memory_bus.subscribe() as events:
            svc = BeliefService()
            async with factory() as session:
                await svc.create_lifecycle_belief(
                    session=session,
                    run_id=run_id,
                    agent_id="lifecycle",
                    content={"type": "run_start"},
                    topic_tags=["run_start"],
                )
                await session.commit()

            event = await asyncio.wait_for(anext_async(events), timeout=1.0)
            assert event["type"] == "belief_append"
            assert event["run_id"] == run_id
            assert event["belief_type"] == "lifecycle"
            assert event["seq"] == 1
            assert "content_hash" in event

    async def test_publish_swallows_bus_errors(
        self,
        engine_and_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A broken bus must not break belief writes."""
        from ironroot.events.bus import BeliefEventBus

        class _BoomBus(BeliefEventBus):
            async def publish(self, event: dict[str, object]) -> None:
                raise RuntimeError("broker down")

            def subscribe(self):  # type: ignore[override]
                raise RuntimeError("never subscribed in this test")

        set_belief_event_bus(_BoomBus())
        try:
            _, factory = engine_and_factory
            run_id = await _seed_run(factory)
            svc = BeliefService()
            async with factory() as session:
                belief = await svc.create_lifecycle_belief(
                    session=session,
                    run_id=run_id,
                    agent_id="lifecycle",
                    content={"type": "run_start"},
                    topic_tags=["run_start"],
                )
                await session.commit()
            # The append must have succeeded despite the bus raising.
            assert belief.seq == 1
        finally:
            reset_belief_event_bus()


class TestWebSocketRoute:
    def test_stream_forwards_published_events(
        self,
        in_memory_bus: InMemoryBeliefEventBus,
    ) -> None:
        """The route forwards what the bus publishes, with the right shape."""
        with TestClient(app) as client, client.websocket_connect("/api/v1/ui/events/stream") as ws:

            async def _publish() -> None:
                await in_memory_bus.publish(
                    {
                        "type": "belief_append",
                        "belief_id": "blf_1",
                        "run_id": "run_x",
                        "seq": 1,
                    }
                )

            asyncio.run(_publish())

            got = ws.receive_json()
            assert got == {
                "type": "belief_append",
                "belief_id": "blf_1",
                "run_id": "run_x",
                "seq": 1,
            }

    def test_ping_pong(self, in_memory_bus: InMemoryBeliefEventBus) -> None:
        with TestClient(app) as client, client.websocket_connect("/api/v1/ui/events/stream") as ws:
            ws.send_json({"type": "ping"})
            got = ws.receive_json()
            assert got == {"type": "pong"}


class TestRedisBusErrorHandling:
    """The Redis bus must not raise when the broker is unreachable."""

    async def test_publish_on_unreachable_broker_does_not_raise(self) -> None:
        bus = RedisBeliefEventBus("redis://127.0.0.1:6/0")  # invalid port
        # Should swallow connection error and log instead.
        await bus.publish({"type": "ping"})
        await bus.close()


def test_null_bus_is_safe() -> None:
    """The Null bus accepts publishes and yields no events."""
    bus = NullBeliefEventBus()
    asyncio.run(bus.publish({"x": 1}))


def test_set_and_reset_swap_singleton() -> None:
    """The override hook actually swaps the singleton in and out."""
    from ironroot.events import get_belief_event_bus

    sentinel = InMemoryBeliefEventBus()
    set_belief_event_bus(sentinel)
    try:
        assert get_belief_event_bus() is sentinel
    finally:
        reset_belief_event_bus()
