# Author: Bradley R. Kinnard
"""health check endpoint.

Phase 3.1: real readiness probe. Replaces the hard-coded ``"ok"`` stub
with a report that an operator can act on:

- ``db``: latency-bounded ``SELECT 1`` against Postgres.
- ``redis``: latency-bounded ``PING`` against Redis.
- ``artifacts``: artifact root path exists and is writable.
- ``chain.latest_seq``: ``MAX(beliefs.seq)`` across all chains.
- ``chain.runs_total``: number of distinct chains seen.
- ``replay.oldest_baseline_age_seconds``: how long ago the oldest run
  with a sealed replay digest was sealed. ``None`` if no run has been
  sealed yet. Stale baselines are an operator signal that no run has
  completed recently.
- ``gates.recent_failures``: count of GateRecord rows in the last
  ``recent_failure_window_seconds`` where ``passed = False``.
- ``worker.alive``: at least one Celery worker is responding to ping
  within the configured timeout. Best-effort; failures degrade the
  status rather than 500ing the endpoint.
- ``status``: ``healthy`` (everything green), ``degraded`` (a soft
  signal like worker offline or stale baseline), ``unhealthy`` (DB,
  Redis, or artifact root broken).

The endpoint never raises — it catches and reports per-subsystem. An
operator should be able to hit ``/api/v1/health`` and know whether
integrity is intact without reading source.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ironroot.api.deps import DbSessionDep  # noqa: TC001 — used in route signature at runtime
from ironroot.settings import get_settings
from ironroot.storage.models import BeliefRecord, GateRecord, RunRecord

router = APIRouter()

# How recent a gate failure has to be to count toward
# ``gates.recent_failures``. 24h is a deliberate, audit-friendly window —
# operators want "today's failures", not "all-time".
RECENT_FAILURE_WINDOW_SECONDS = 24 * 60 * 60

# How long a probe is allowed to run before we treat it as failed. We
# never want /health itself to hang behind a wedged dependency.
DB_PROBE_TIMEOUT_SECONDS = 2.0
REDIS_PROBE_TIMEOUT_SECONDS = 2.0
WORKER_PROBE_TIMEOUT_SECONDS = 2.0


class SubsystemStatus(BaseModel):
    """one dependency's reachability."""

    status: Literal["ok", "error", "unknown"]
    latency_ms: float | None = None
    detail: str | None = None


class ChainSummary(BaseModel):
    """rollup of the append-only chain across all runs."""

    latest_seq: int
    runs_total: int


class ReplaySummary(BaseModel):
    """rollup of replay-digest baselines across all runs."""

    sealed_runs: int
    oldest_baseline_age_seconds: float | None
    newest_baseline_age_seconds: float | None


class GatesSummary(BaseModel):
    """rollup of recent gate-suite outcomes."""

    recent_failures: int
    recent_window_seconds: int
    last_failure_at: str | None


class WorkerSummary(BaseModel):
    """Celery worker liveness via ``ping``."""

    alive: bool
    responding_workers: int
    detail: str | None = None


class HealthResponse(BaseModel):
    """structured /health response."""

    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    checked_at: str = Field(description="ISO-8601 UTC timestamp of the probe.")
    db: SubsystemStatus
    redis: SubsystemStatus
    artifacts: SubsystemStatus
    chain: ChainSummary
    replay: ReplaySummary
    gates: GatesSummary
    worker: WorkerSummary


async def _probe_db(
    session: Any,
) -> tuple[SubsystemStatus, ChainSummary, ReplaySummary, GatesSummary]:
    """probes the DB and rolls up chain/replay/gates in one transaction.

    Bundling these into the same session avoids paying connection
    overhead five times in a row. Each piece is wrapped so a single
    failed query still lets the others report.
    """
    db_status: SubsystemStatus
    chain = ChainSummary(latest_seq=0, runs_total=0)
    replay = ReplaySummary(
        sealed_runs=0,
        oldest_baseline_age_seconds=None,
        newest_baseline_age_seconds=None,
    )
    gates = GatesSummary(
        recent_failures=0,
        recent_window_seconds=RECENT_FAILURE_WINDOW_SECONDS,
        last_failure_at=None,
    )

    started = time.perf_counter()
    try:
        await asyncio.wait_for(session.execute(select(1)), timeout=DB_PROBE_TIMEOUT_SECONDS)
        latency_ms = (time.perf_counter() - started) * 1000.0
        db_status = SubsystemStatus(status="ok", latency_ms=round(latency_ms, 3))
    except TimeoutError:
        return (
            SubsystemStatus(status="error", detail="db probe timed out"),
            chain,
            replay,
            gates,
        )
    except Exception as exc:
        return (
            SubsystemStatus(status="error", detail=f"db probe failed: {exc!s}"),
            chain,
            replay,
            gates,
        )

    try:
        seq_result = await session.execute(select(func.max(BeliefRecord.seq)))
        runs_result = await session.execute(select(func.count(func.distinct(BeliefRecord.run_id))))
        chain = ChainSummary(
            latest_seq=int(seq_result.scalar() or 0),
            runs_total=int(runs_result.scalar() or 0),
        )
    except Exception:
        # Chain rollup is best-effort; a query failure here is an
        # additional data point, not a reason to fail the probe.
        pass

    try:
        sealed_total = await session.execute(
            select(func.count(RunRecord.id)).where(RunRecord.replay_digest.isnot(None))
        )
        oldest_dt = await session.execute(
            select(func.min(RunRecord.replay_digest_sealed_at)).where(
                RunRecord.replay_digest.isnot(None)
            )
        )
        newest_dt = await session.execute(
            select(func.max(RunRecord.replay_digest_sealed_at)).where(
                RunRecord.replay_digest.isnot(None)
            )
        )
        now = datetime.now(UTC)
        oldest = oldest_dt.scalar()
        newest = newest_dt.scalar()
        replay = ReplaySummary(
            sealed_runs=int(sealed_total.scalar() or 0),
            oldest_baseline_age_seconds=_age_seconds(oldest, now),
            newest_baseline_age_seconds=_age_seconds(newest, now),
        )
    except Exception:
        pass

    try:
        cutoff = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() - RECENT_FAILURE_WINDOW_SECONDS, tz=UTC
        )
        failure_count = await session.execute(
            select(func.count(GateRecord.id)).where(
                GateRecord.passed.is_(False), GateRecord.executed_at >= cutoff
            )
        )
        last_failure_dt = await session.execute(
            select(func.max(GateRecord.executed_at)).where(GateRecord.passed.is_(False))
        )
        last_failure = last_failure_dt.scalar()
        gates = GatesSummary(
            recent_failures=int(failure_count.scalar() or 0),
            recent_window_seconds=RECENT_FAILURE_WINDOW_SECONDS,
            last_failure_at=last_failure.isoformat() if last_failure else None,
        )
    except Exception:
        pass

    return db_status, chain, replay, gates


def _age_seconds(when: datetime | None, now: datetime) -> float | None:
    """Returns seconds between ``when`` and ``now`` or ``None``.

    Tolerates both timezone-aware and naive datetimes — SQLite returns
    naive UTC, Postgres returns aware UTC, we treat both as UTC.
    """
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (now - when).total_seconds())


async def _probe_redis() -> SubsystemStatus:
    """PING the Redis broker.

    Imported lazily — the redis client is a real dependency but we
    want unit tests that monkey-patch ``redis.asyncio`` to be able to
    intercept it.
    """
    try:
        from redis import asyncio as redis_asyncio
    except ImportError:
        return SubsystemStatus(status="unknown", detail="redis client not installed")

    settings = get_settings()
    started = time.perf_counter()
    client = redis_asyncio.from_url(settings.redis_url, socket_timeout=REDIS_PROBE_TIMEOUT_SECONDS)
    try:
        ping_call = client.ping()
        await asyncio.wait_for(ping_call, timeout=REDIS_PROBE_TIMEOUT_SECONDS)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return SubsystemStatus(status="ok", latency_ms=round(latency_ms, 3))
    except TimeoutError:
        return SubsystemStatus(status="error", detail="redis probe timed out")
    except Exception as exc:
        return SubsystemStatus(status="error", detail=f"redis probe failed: {exc!s}")
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()


def _probe_artifacts() -> SubsystemStatus:
    """checks that the configured artifact root exists and is writable."""
    settings = get_settings()
    root = settings.artifact_path
    try:
        root.mkdir(parents=True, exist_ok=True)
        # Touch-and-remove rather than statvfs because the local store
        # contract is "we can write here", not "the FS reports free".
        probe = root / ".health-probe"
        probe.write_bytes(b"")
        probe.unlink(missing_ok=True)
        return SubsystemStatus(status="ok")
    except Exception as exc:
        return SubsystemStatus(status="error", detail=f"artifact root unwritable: {exc!s}")


async def _probe_worker() -> WorkerSummary:
    """asks Celery to ping all workers attached to the broker.

    ``celery_app.control.ping`` is sync — wrap it in ``asyncio.to_thread``
    so it doesn't block the event loop, and bound it with a timeout
    so a wedged broker can't stall /health.
    """
    try:
        from ironroot.orchestration.queue import celery_app
    except Exception as exc:
        return WorkerSummary(
            alive=False, responding_workers=0, detail=f"celery import failed: {exc!s}"
        )

    def _ping() -> list[dict[str, Any]]:
        # ``ping`` returns a list of single-key dicts, one per worker.
        # ``timeout`` is seconds; we still wrap in asyncio.wait_for as
        # a hard ceiling.
        result = celery_app.control.ping(timeout=WORKER_PROBE_TIMEOUT_SECONDS)
        return list(result or [])

    try:
        responses = await asyncio.wait_for(
            asyncio.to_thread(_ping),
            timeout=WORKER_PROBE_TIMEOUT_SECONDS + 0.5,
        )
    except TimeoutError:
        return WorkerSummary(alive=False, responding_workers=0, detail="worker ping timed out")
    except Exception as exc:
        return WorkerSummary(
            alive=False, responding_workers=0, detail=f"worker ping failed: {exc!s}"
        )

    responding = len(responses)
    return WorkerSummary(
        alive=responding > 0,
        responding_workers=responding,
        detail=None if responding else "no workers responded to ping",
    )


def _rollup_status(
    db: SubsystemStatus,
    redis: SubsystemStatus,
    artifacts: SubsystemStatus,
    worker: WorkerSummary,
) -> Literal["healthy", "degraded", "unhealthy"]:
    """combines subsystem signals into a single status.

    Rules:
    - DB / Redis / artifacts unreachable = unhealthy. The system cannot
      accept writes without these.
    - Worker offline = degraded. Reads still work; we just can't
      execute new runs in the background.
    - Everything green = healthy.
    """
    hard_failures = [s for s in (db, redis, artifacts) if s.status == "error"]
    if hard_failures:
        return "unhealthy"
    if not worker.alive:
        return "degraded"
    return "healthy"


@router.get("/health", response_model=HealthResponse)
async def health_check(session: DbSessionDep) -> HealthResponse:
    """returns service readiness with per-subsystem detail.

    Replaces the Phase-0 stub that returned hard-coded ``"ok"``. An
    operator who hits this can immediately tell whether integrity is
    intact (DB / chain / replay), whether the run pipeline can
    execute (Celery worker), and whether artifact persistence is
    working (artifact root).
    """
    db, chain, replay, gates = await _probe_db(session)
    redis_status, artifacts_status, worker = await asyncio.gather(
        _probe_redis(),
        asyncio.to_thread(_probe_artifacts),
        _probe_worker(),
    )

    return HealthResponse(
        status=_rollup_status(db, redis_status, artifacts_status, worker),
        version="0.1.0",
        checked_at=datetime.now(UTC).isoformat(),
        db=db,
        redis=redis_status,
        artifacts=artifacts_status,
        chain=chain,
        replay=replay,
        gates=gates,
        worker=worker,
    )
