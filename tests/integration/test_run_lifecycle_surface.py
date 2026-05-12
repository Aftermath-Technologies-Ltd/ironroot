# Author: Bradley R. Kinnard
"""Phase 3.2: real run lifecycle surface tests.

These tests prove that:

1. ``RunStatus.gate_status`` is populated from the latest GateRecord,
   not hard-coded ``None``.
2. ``/runs/{id}/trace`` returns the actual belief subtree for the
   run, ordered by ``seq``.
3. The Celery ``execute_run`` task, when run eagerly (no broker),
   actually dispatches to the orchestrator and updates run state.

The Celery task is exercised against an aiosqlite DB by patching the
``get_session_factory`` it imports inside, since the real engine
isn't running in unit-test mode.
"""

from __future__ import annotations

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

from ironroot.api.deps import get_db_session
from ironroot.domain.ids import generate_id
from ironroot.main import app
from ironroot.storage.models import BeliefRecord, GateRecord, RunRecord
from ironroot.storage.postgres import Base


@pytest_asyncio.fixture
async def engine_and_factory() -> (
    AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]
):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "lifecycle.sqlite"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield engine, factory
        finally:
            await engine.dispose()


@pytest.fixture
def client_with_db(
    engine_and_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    _, factory = engine_and_factory

    async def _override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.pop(get_db_session, None)


async def _seed_run(factory: async_sessionmaker[AsyncSession]) -> str:
    """creates a Run row and returns its id."""
    run_id = generate_id("run")
    async with factory() as session:
        session.add(
            RunRecord(
                id=run_id,
                seed=11,
                status="running",
                phase="verify",
                config={"budgets": {"max_steps": 240}},
                created_at=datetime.now(UTC),
                steps_used=1,
                tool_calls_used=0,
                belief_writes_used=0,
            )
        )
        await session.commit()
    return run_id


class TestGateStatusOnRun:
    async def test_no_gate_record_means_none(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, factory = client_with_db
        run_id = await _seed_run(factory)
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200, response.text
        assert response.json()["gate_status"] is None

    async def test_passed_gate_record_surfaces_as_passed(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, factory = client_with_db
        run_id = await _seed_run(factory)
        async with factory() as session:
            session.add(
                GateRecord(
                    id=generate_id("gat"),
                    run_id=run_id,
                    gate_type="full_suite",
                    passed=True,
                    artifact_id=None,
                    results={"overall": "passed"},
                    executed_at=datetime.now(UTC),
                )
            )
            await session.commit()

        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.json()["gate_status"] == "passed"

    async def test_latest_gate_wins(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        """A later failed gate must override an earlier passed gate."""
        client, factory = client_with_db
        run_id = await _seed_run(factory)
        async with factory() as session:
            now = datetime.now(UTC)
            session.add_all(
                [
                    GateRecord(
                        id=generate_id("gat"),
                        run_id=run_id,
                        gate_type="full_suite",
                        passed=True,
                        artifact_id=None,
                        results={},
                        executed_at=now.replace(microsecond=0),
                    ),
                    GateRecord(
                        id=generate_id("gat"),
                        run_id=run_id,
                        gate_type="full_suite",
                        passed=False,
                        artifact_id=None,
                        results={},
                        executed_at=now.replace(microsecond=500_000),
                    ),
                ]
            )
            await session.commit()

        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.json()["gate_status"] == "failed"

    async def test_list_runs_includes_gate_status(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, factory = client_with_db
        run_id = await _seed_run(factory)
        async with factory() as session:
            session.add(
                GateRecord(
                    id=generate_id("gat"),
                    run_id=run_id,
                    gate_type="full_suite",
                    passed=True,
                    artifact_id=None,
                    results={},
                    executed_at=datetime.now(UTC),
                )
            )
            await session.commit()

        response = client.get("/api/v1/runs")
        data = response.json()
        match = [r for r in data["runs"] if r["run_id"] == run_id]
        assert match, "run not present in list"
        assert match[0]["gate_status"] == "passed"


class TestTraceEndpoint:
    async def test_trace_returns_belief_subtree_ordered_by_seq(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, factory = client_with_db
        run_id = await _seed_run(factory)

        async with factory() as session:
            for i in range(4):
                session.add(
                    BeliefRecord(
                        id=generate_id("bel"),
                        run_id=run_id,
                        seq=i + 1,
                        agent_id="probe",
                        belief_type="lifecycle",
                        content_hash=f"{i:064d}",
                        parent_hash=None if i == 0 else f"{i - 1:064d}",
                        content={"i": i, "note": f"step-{i}"},
                        confidence=1.0,
                        evidence_ids=[],
                        topic_tags=["trace"],
                        provenance={},
                        created_at=datetime.now(UTC),
                    )
                )
            await session.commit()

        response = client.get(f"/api/v1/runs/{run_id}/trace")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["total"] == 4
        seqs = [e["seq"] for e in data["events"]]
        assert seqs == [1, 2, 3, 4]
        assert data["events"][0]["content"] == {"i": 0, "note": "step-0"}
        assert "provenance" in data["events"][0]

    async def test_trace_paginates(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, factory = client_with_db
        run_id = await _seed_run(factory)

        async with factory() as session:
            for i in range(5):
                session.add(
                    BeliefRecord(
                        id=generate_id("bel"),
                        run_id=run_id,
                        seq=i + 1,
                        agent_id="probe",
                        belief_type="lifecycle",
                        content_hash=f"{i:064d}",
                        parent_hash=None if i == 0 else f"{i - 1:064d}",
                        content={"i": i},
                        confidence=1.0,
                        evidence_ids=[],
                        topic_tags=[],
                        provenance={},
                        created_at=datetime.now(UTC),
                    )
                )
            await session.commit()

        response = client.get(f"/api/v1/runs/{run_id}/trace?offset=2&limit=2")
        data = response.json()
        assert data["total"] == 5
        assert [e["seq"] for e in data["events"]] == [3, 4]

    async def test_trace_for_unknown_run_is_empty_not_404(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, _ = client_with_db
        response = client.get("/api/v1/runs/run_nonexistent/trace")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["events"] == []

    def test_trace_rejects_invalid_pagination(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, _ = client_with_db
        # negative offset
        response = client.get("/api/v1/runs/run_anything/trace?offset=-1")
        assert response.status_code == 400
        # limit over cap
        response = client.get("/api/v1/runs/run_anything/trace?limit=10000")
        assert response.status_code == 400


class TestCeleryExecuteRunTask:
    """The Phase 3.2 wrapper is no longer a no-op.

    We don't need a real broker — we set ``task_always_eager`` so the
    task body runs inline, then assert the orchestrator actually
    advanced the run.
    """

    def test_execute_run_invokes_real_orchestrator(
        self,
        engine_and_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ironroot.orchestration import queue as queue_module
        from ironroot.storage import postgres as postgres_module

        _, factory = engine_and_factory

        # Force the executor's session factory to use the test sqlite
        # engine. The Celery task imports get_session_factory inside
        # _run_orchestrator, so the monkeypatch must hit that exact
        # symbol.
        monkeypatch.setattr(postgres_module, "get_session_factory", lambda: factory)
        # Run inline rather than over a real broker.
        queue_module.celery_app.conf.task_always_eager = True
        queue_module.celery_app.conf.task_eager_propagates = True

        # Seed a pending run.
        import asyncio

        async def _seed() -> str:
            run_id = generate_id("run")
            async with factory() as session:
                session.add(
                    RunRecord(
                        id=run_id,
                        seed=99,
                        status="pending",
                        phase="init",
                        config={
                            "budgets": {
                                "max_steps": 240,
                                "max_tool_calls": 500,
                                "max_belief_writes": 200,
                            }
                        },
                        created_at=datetime.now(UTC),
                        steps_used=0,
                        tool_calls_used=0,
                        belief_writes_used=0,
                    )
                )
                await session.commit()
            return run_id

        run_id = asyncio.run(_seed())

        # Fire the task synchronously.
        result = queue_module.execute_run.apply(args=(run_id,)).get()
        assert result["run_id"] == run_id
        # The orchestrator marks completed runs with status="completed".
        # If the executor errored, the task wrapper returns status="task_error".
        assert result.get("status") in {"completed", "failed"}, result

        # Sanity-check the run record actually moved off "pending".
        async def _read() -> RunRecord:
            async with factory() as session:
                from sqlalchemy import select

                rec = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
                return rec.scalar_one()

        record = asyncio.run(_read())
        assert record.status != "pending"

    def test_execute_run_missing_id_returns_not_found_payload(
        self,
        engine_and_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ironroot.orchestration import queue as queue_module
        from ironroot.storage import postgres as postgres_module

        _, factory = engine_and_factory
        monkeypatch.setattr(postgres_module, "get_session_factory", lambda: factory)
        queue_module.celery_app.conf.task_always_eager = True
        queue_module.celery_app.conf.task_eager_propagates = True

        result = queue_module.execute_run.apply(args=("run_does_not_exist",)).get()
        assert result == {"run_id": "run_does_not_exist", "status": "not_found"}


class TestEnqueueRoute:
    def test_enqueue_returns_task_id(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client, factory = client_with_db

        # We don't want the eager celery task to actually run inside
        # the request handler, just confirm the API contract.
        from ironroot.orchestration import queue as queue_module

        monkeypatch.setattr(queue_module, "enqueue_run", lambda run_id: f"task-{run_id}")
        import ironroot.api.routes.runs as runs_module

        # The route imports enqueue_run inside the function via
        # `from ironroot.orchestration.queue import enqueue_run` — so
        # patching the queue module attribute is the right hook.
        # But to be safe, also patch the imported symbol on the route
        # module if it has been imported eagerly.
        if hasattr(runs_module, "enqueue_run"):
            monkeypatch.setattr(runs_module, "enqueue_run", lambda run_id: f"task-{run_id}")

        import asyncio

        async def _seed() -> str:
            run_id = generate_id("run")
            async with factory() as session:
                session.add(
                    RunRecord(
                        id=run_id,
                        seed=5,
                        status="pending",
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

        run_id = asyncio.run(_seed())
        response = client.post(f"/api/v1/runs/{run_id}/execute_async")
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["run_id"] == run_id
        assert body["task_id"] == f"task-{run_id}"
        assert body["status"] == "enqueued"

    def test_enqueue_unknown_run_returns_404(
        self,
        client_with_db: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, _ = client_with_db
        response = client.post("/api/v1/runs/run_phantom/execute_async")
        assert response.status_code == 404
