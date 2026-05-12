# Author: Bradley R. Kinnard
"""Celery task queue for background orchestration.

Phase 3.2: ``execute_run`` is no longer a no-op. The Celery task opens
a fresh async DB session, calls the real orchestrator (``RunExecutor``),
and returns the structured result. ``RunExecutor`` lives in
``ironroot.experimental.*`` (it currently uses RNG for trace-simulation
work and is quarantined accordingly) but the Celery wrapper itself is
production code: it must not crash a worker on a bad run id, and it
must return a JSON-serializable payload.

We intentionally use ``asyncio.run`` per task rather than reusing an
event loop across tasks — Celery's default worker model is one task at
a time per process, so the per-task loop is cheapest and cleanest, and
the AsyncEngine survives across tasks via the lazy singletons in
``ironroot.storage.postgres``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from celery import Celery

from ironroot.settings import get_settings

if TYPE_CHECKING:
    from celery.result import AsyncResult
    from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()

celery_app = Celery(
    "ironroot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
)


async def _run_orchestrator(run_id: str) -> dict[str, Any]:
    """Opens a fresh session and dispatches to the real orchestrator.

    Imports are inside the function so the worker process pays the
    cost only when the task fires, and so importing ``queue`` from the
    health probe doesn't drag the executor module in.
    """
    from ironroot.orchestration.executor import get_executor
    from ironroot.orchestration.run_service import get_run_service
    from ironroot.storage.postgres import get_session_factory

    factory = get_session_factory()
    run_service = get_run_service()
    executor = get_executor()

    session: AsyncSession
    async with factory() as session:
        record = await run_service.get_run(session, run_id)
        if record is None:
            await session.commit()
            return {"run_id": run_id, "status": "not_found"}

        if record.status == "pending":
            # Move the run from INIT to PROPOSE before the executor
            # starts, mirroring the sync /execute route.
            await run_service.start_run(session, run_id)
            await session.commit()

        result = await executor.execute(session, run_id)
        await session.commit()
        return result


@celery_app.task(bind=True, name="ironroot.run.execute")  # type: ignore[untyped-decorator]
def execute_run(self: object, run_id: str) -> dict[str, Any]:
    """Background task: runs the orchestrator for ``run_id`` to completion.

    Returns the same structured result the synchronous
    ``/runs/{run_id}/execute`` endpoint returns, so an operator that
    enqueued via Celery can fetch the result by task id and parse it
    identically.
    """
    try:
        result = asyncio.run(_run_orchestrator(run_id))
    except Exception as exc:
        # The supervisor.fail_run path in the executor already records
        # failures as run-state changes. This branch catches harness
        # bugs (engine import, connection errors) so the task result
        # is still JSON, not a stack trace blob.
        return {"run_id": run_id, "status": "task_error", "error": str(exc)}
    return result


def enqueue_run(run_id: str) -> str:
    """Submits ``run_id`` to the Celery broker and returns the task id.

    Thin wrapper around ``execute_run.delay`` so callers in the API
    don't have to import the Celery decorator object directly. The
    return value is opaque — operators look it up via the standard
    Celery result backend.
    """
    async_result: AsyncResult = execute_run.delay(run_id)  # type: ignore[attr-defined]
    return str(async_result.id)
