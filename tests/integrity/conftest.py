# Author: Bradley R. Kinnard
"""Fixtures for Phase 1 adversarial integrity tests.

The integrity tests run against aiosqlite by default so they are fast and
require no external services. The seq column, UNIQUE(run_id, seq) constraint,
and check constraint are emitted by SQLAlchemy `create_all` and behave
identically to the production schema for these tests. The Postgres advisory
lock path is exercised by separate integration tests under
``tests/integration/`` when an ``IRONROOT_PG_URL`` env var is set.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Ensure debug mode for the settings guard before ironroot.* imports.
os.environ.setdefault("IRONROOT_DEBUG", "true")

from ironroot.beliefs import BeliefService
from ironroot.domain.ids import generate_id
from ironroot.storage.models import RunRecord
from ironroot.storage.postgres import Base


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncIterator[AsyncEngine]:
    """fresh in-memory sqlite engine with the full schema."""
    # File-backed so a single engine across multiple sessions sees the same DB.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "integrity.sqlite"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            yield engine
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(
    sqlite_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """session factory bound to the fixture engine."""
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def belief_service() -> BeliefService:
    """fresh BeliefService — clears the singleton's in-process lock dict."""
    return BeliefService()


@pytest_asyncio.fixture
async def run_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    """creates a Run row so beliefs have a valid FK target."""
    run_id_value = generate_id("run")
    async with session_factory() as session:
        run = RunRecord(
            id=run_id_value,
            seed=42,
            status="running",
            phase="plan",
            config={},
            created_at=datetime.now(UTC),
            steps_used=0,
            tool_calls_used=0,
            belief_writes_used=0,
        )
        session.add(run)
        await session.commit()
    return run_id_value


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """auto-mark integrity tests so they're easy to filter with -m integrity."""
    for item in items:
        item.add_marker(pytest.mark.integrity)
