# Author: Bradley R. Kinnard
"""Phase 3.1: real /health endpoint integration tests.

These tests use FastAPI's dependency override hook to inject a real
aiosqlite session, then monkeypatch the redis and celery worker probes
so the assertions stay deterministic. The point is to prove the
endpoint reports actual state, not the Phase-0 hardcoded ``"ok"``.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
from ironroot.api.routes import health as health_module
from ironroot.domain.ids import generate_id
from ironroot.main import app
from ironroot.storage.models import BeliefRecord, GateRecord, RunRecord
from ironroot.storage.postgres import Base


@pytest_asyncio.fixture
async def engine_and_session() -> (
    AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]
):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "health.sqlite"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield engine, factory
        finally:
            await engine.dispose()


@pytest.fixture
def client_factory(
    engine_and_session: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    _, factory = engine_and_session

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


@pytest.fixture
def patch_external_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """force redis/worker probes to deterministic shapes."""
    from ironroot.api.routes.health import SubsystemStatus, WorkerSummary

    async def _ok_redis() -> SubsystemStatus:
        return SubsystemStatus(status="ok", latency_ms=0.1)

    async def _ok_worker() -> WorkerSummary:
        return WorkerSummary(alive=True, responding_workers=1)

    monkeypatch.setattr(health_module, "_probe_redis", _ok_redis)
    monkeypatch.setattr(health_module, "_probe_worker", _ok_worker)


class TestHealthEndpoint:
    def test_empty_db_reports_healthy(
        self,
        client_factory: tuple[TestClient, async_sessionmaker[AsyncSession]],
        patch_external_probes: None,
    ) -> None:
        client, _ = client_factory
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["db"]["status"] == "ok"
        assert data["chain"]["latest_seq"] == 0
        assert data["chain"]["runs_total"] == 0
        assert data["replay"]["sealed_runs"] == 0
        assert data["replay"]["oldest_baseline_age_seconds"] is None
        assert data["gates"]["recent_failures"] == 0
        assert data["worker"]["alive"] is True

    async def test_chain_seq_reflects_latest_belief(
        self,
        client_factory: tuple[TestClient, async_sessionmaker[AsyncSession]],
        patch_external_probes: None,
    ) -> None:
        client, factory = client_factory
        run_id = generate_id("run")
        async with factory() as session:
            session.add(
                RunRecord(
                    id=run_id,
                    seed=1,
                    status="running",
                    phase="plan",
                    config={},
                    created_at=datetime.now(UTC),
                    steps_used=1,
                    tool_calls_used=0,
                    belief_writes_used=0,
                )
            )
            await session.commit()

        # Direct row inserts — the test target here is the
        # /health rollup query, not the BeliefService phase rules.
        async with factory() as session:
            for i in range(3):
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
                        topic_tags=["health"],
                        provenance={},
                        created_at=datetime.now(UTC),
                    )
                )
            await session.commit()

        response = client.get("/api/v1/health")
        data = response.json()
        assert data["chain"]["latest_seq"] == 3
        assert data["chain"]["runs_total"] == 1

    async def test_replay_age_is_reported(
        self,
        client_factory: tuple[TestClient, async_sessionmaker[AsyncSession]],
        patch_external_probes: None,
    ) -> None:
        client, factory = client_factory
        async with factory() as session:
            session.add(
                RunRecord(
                    id=generate_id("run"),
                    seed=2,
                    status="completed",
                    phase="finalize",
                    config={},
                    created_at=datetime.now(UTC),
                    steps_used=1,
                    tool_calls_used=0,
                    belief_writes_used=0,
                    replay_digest="a" * 64,
                    replay_digest_sealed_at=datetime.now(UTC) - timedelta(seconds=10),
                )
            )
            await session.commit()

        response = client.get("/api/v1/health")
        data = response.json()
        assert data["replay"]["sealed_runs"] == 1
        age = data["replay"]["oldest_baseline_age_seconds"]
        assert age is not None and age >= 9.0

    async def test_recent_gate_failures_counted(
        self,
        client_factory: tuple[TestClient, async_sessionmaker[AsyncSession]],
        patch_external_probes: None,
    ) -> None:
        client, factory = client_factory
        run_id = generate_id("run")
        async with factory() as session:
            session.add(
                RunRecord(
                    id=run_id,
                    seed=3,
                    status="failed",
                    phase="verify",
                    config={},
                    created_at=datetime.now(UTC),
                    steps_used=1,
                    tool_calls_used=0,
                    belief_writes_used=0,
                )
            )
            now = datetime.now(UTC)
            session.add_all(
                [
                    GateRecord(
                        id=generate_id("gat"),
                        run_id=run_id,
                        gate_type="full_suite",
                        passed=False,
                        artifact_id=None,
                        results={},
                        executed_at=now,
                    ),
                    GateRecord(
                        id=generate_id("gat"),
                        run_id=run_id,
                        gate_type="full_suite",
                        passed=True,
                        artifact_id=None,
                        results={},
                        executed_at=now,
                    ),
                ]
            )
            await session.commit()

        response = client.get("/api/v1/health")
        data = response.json()
        assert data["gates"]["recent_failures"] == 1
        assert data["gates"]["last_failure_at"] is not None

    def test_redis_offline_marks_unhealthy(
        self,
        client_factory: tuple[TestClient, async_sessionmaker[AsyncSession]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ironroot.api.routes.health import SubsystemStatus, WorkerSummary

        async def _down_redis() -> SubsystemStatus:
            return SubsystemStatus(status="error", detail="connection refused")

        async def _ok_worker() -> WorkerSummary:
            return WorkerSummary(alive=True, responding_workers=1)

        monkeypatch.setattr(health_module, "_probe_redis", _down_redis)
        monkeypatch.setattr(health_module, "_probe_worker", _ok_worker)

        client, _ = client_factory
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["redis"]["status"] == "error"

    def test_worker_offline_marks_degraded(
        self,
        client_factory: tuple[TestClient, async_sessionmaker[AsyncSession]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ironroot.api.routes.health import SubsystemStatus, WorkerSummary

        async def _ok_redis() -> SubsystemStatus:
            return SubsystemStatus(status="ok", latency_ms=0.1)

        async def _down_worker() -> WorkerSummary:
            return WorkerSummary(alive=False, responding_workers=0, detail="no workers")

        monkeypatch.setattr(health_module, "_probe_redis", _ok_redis)
        monkeypatch.setattr(health_module, "_probe_worker", _down_worker)

        client, _ = client_factory
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "degraded"
        assert data["worker"]["alive"] is False

    def test_response_has_iso_timestamp_and_version(
        self,
        client_factory: tuple[TestClient, async_sessionmaker[AsyncSession]],
        patch_external_probes: None,
    ) -> None:
        client, _ = client_factory
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["version"] == "0.1.0"
        # ISO-8601 parse — raises if not parseable.
        datetime.fromisoformat(data["checked_at"])


def test_rollup_priority() -> None:
    """Direct unit test of the rollup decision matrix."""
    from ironroot.api.routes.health import (
        SubsystemStatus,
        WorkerSummary,
        _rollup_status,
    )

    ok = SubsystemStatus(status="ok")
    bad = SubsystemStatus(status="error")
    live = WorkerSummary(alive=True, responding_workers=1)
    dead = WorkerSummary(alive=False, responding_workers=0)

    assert _rollup_status(ok, ok, ok, live) == "healthy"
    assert _rollup_status(ok, ok, ok, dead) == "degraded"
    assert _rollup_status(bad, ok, ok, live) == "unhealthy"
    assert _rollup_status(ok, bad, ok, live) == "unhealthy"
    assert _rollup_status(ok, ok, bad, live) == "unhealthy"
    # hard failure wins over degraded
    assert _rollup_status(bad, ok, ok, dead) == "unhealthy"


def test_age_seconds_handles_naive_and_aware_datetimes() -> None:
    from ironroot.api.routes.health import _age_seconds

    now = datetime.now(UTC)
    aware = now - timedelta(seconds=30)
    naive = aware.replace(tzinfo=None)

    assert abs((_age_seconds(aware, now) or 0) - 30.0) < 1.0
    assert abs((_age_seconds(naive, now) or 0) - 30.0) < 1.0
    assert _age_seconds(None, now) is None


def test_artifacts_probe_when_writable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """artifact root probe creates the dir and reports ok."""
    from ironroot.api.routes.health import _probe_artifacts

    def _settings_with_path() -> Any:
        from ironroot.settings import Settings

        return Settings(
            debug=True,
            db_password="changeme",
            artifact_path=tmp_path / "store",
            _env_file=None,  # type: ignore[call-arg]
        )

    monkeypatch.setattr(health_module, "get_settings", _settings_with_path)
    status = _probe_artifacts()
    assert status.status == "ok"
    assert (tmp_path / "store").exists()


def test_artifacts_probe_when_unwritable(monkeypatch: pytest.MonkeyPatch) -> None:
    """artifact root probe surfaces filesystem errors."""
    from ironroot.api.routes.health import _probe_artifacts

    def _settings_with_bad_path() -> Any:
        from ironroot.settings import Settings

        # Force a path no process can write to.
        return Settings(
            debug=True,
            db_password="changeme",
            artifact_path=Path("/nonexistent/forbidden/health-probe"),
            _env_file=None,  # type: ignore[call-arg]
        )

    monkeypatch.setattr(health_module, "get_settings", _settings_with_bad_path)
    status = _probe_artifacts()
    assert status.status == "error"
    assert "unwritable" in (status.detail or "")
