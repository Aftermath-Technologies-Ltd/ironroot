# Author: Bradley R. Kinnard
"""Fixtures for Phase 4 promotion tests.

Each test file under ``tests/promotion/`` exercises the FalsifiableClaim
and RegressionSuite registered by a candidate subsystem. They share the
same lightweight aiosqlite + temp artifact root setup as the integrity
tests, so promotion fixtures behave the same way the production gate
will when it runs against a sealed run.
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

os.environ.setdefault("IRONROOT_DEBUG", "true")

from ironroot.domain.ids import generate_id
from ironroot.storage.models import RunRecord
from ironroot.storage.postgres import Base
from ironroot.world_models.invariants import register_with_default_registries


@pytest.fixture(autouse=True)
def _reregister_world_models_invariants() -> None:
    """Phase 4: claims/suites are process-global singletons; some integrity
    tests call ``reset_claim_registry_for_testing()`` which drops the
    world_models registration done at package import. Re-register before
    every promotion test so order-dependent suite isolation can't make a
    promoted subsystem look un-promoted.
    """
    register_with_default_registries()


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncIterator[AsyncEngine]:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "promotion.sqlite"
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
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def run_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    run_id_value = generate_id("run")
    async with session_factory() as session:
        run = RunRecord(
            id=run_id_value,
            seed=42,
            status="running",
            phase="plan",
            config={"run_kind": "world_models_promotion"},
            created_at=datetime.now(UTC),
            steps_used=0,
            tool_calls_used=0,
            belief_writes_used=0,
        )
        session.add(run)
        await session.commit()
    return run_id_value


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-mark promotion tests so `pytest -m integration` includes them."""
    for item in items:
        item.add_marker(pytest.mark.integration)
