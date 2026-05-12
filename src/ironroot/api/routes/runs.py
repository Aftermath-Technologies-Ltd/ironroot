# Author: Bradley R. Kinnard
"""run management endpoints.

Phase 3.2: this module now surfaces real run state to operators.

- ``RunStatus.gate_status`` is populated from the latest ``GateRecord``
  for the run, rather than being hard-coded ``None``.
- ``/runs/{id}/trace`` returns the actual belief subtree for the run
  (paginated, ordered by ``seq``), rather than a placeholder empty
  list.
- ``POST /runs/{id}/execute_async`` enqueues the run via Celery and
  returns the task id; the existing ``/execute`` route still runs the
  orchestrator synchronously for test and ops contexts.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.api.deps import RequestIdDep, get_db_session
from ironroot.orchestration.run_service import get_run_service
from ironroot.storage.models import BeliefRecord, GateRecord

router = APIRouter()


class BudgetsConfig(BaseModel):
    """budget configuration for a run."""

    max_steps: int = Field(default=240, ge=1)
    max_tool_calls: int = Field(default=500, ge=1)
    max_belief_writes: int = Field(default=200, ge=1)


class GatesConfig(BaseModel):
    """gate configuration for a run."""

    replay_required: bool = Field(default=True)
    integrity_required: bool = Field(default=True)
    invariants_required: bool = Field(default=True)
    regression_required: bool = Field(default=True)


class FaultInjectionConfig(BaseModel):
    """fault injection configuration for self-healing tests."""

    enabled: bool = Field(default=False)
    scenario_id: str = Field(default="none")
    trigger_phase: str = Field(default="test")
    trigger_condition: str = Field(default="always")
    expected_signature: str = Field(default="")


class RunConfig(BaseModel):
    """configuration for a new run."""

    seed: int = Field(..., description="deterministic seed for replay")
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)
    gates: GatesConfig = Field(default_factory=GatesConfig)
    fault_injection: FaultInjectionConfig = Field(default_factory=FaultInjectionConfig)


class RunCreateResponse(BaseModel):
    """response after creating a run."""

    run_id: str
    request_id: str


class RunStatus(BaseModel):
    """current state of a run."""

    run_id: str
    status: Literal["pending", "running", "completed", "failed", "stopped"]
    phase: str
    seed: int
    steps_used: int
    steps_remaining: int
    tool_calls_used: int
    tool_calls_remaining: int
    belief_writes_used: int
    belief_writes_remaining: int
    gate_status: Literal["pending", "passed", "failed"] | None
    failure_reason: str | None


class RunListResponse(BaseModel):
    """paginated run list response."""

    runs: list[RunStatus]
    offset: int
    limit: int
    total: int


async def _latest_gate_status(
    session: AsyncSession, run_id: str
) -> Literal["pending", "passed", "failed"] | None:
    """Returns the pass/fail status of the most recent gate run.

    ``None`` when no gate has executed for this run yet — distinct
    from ``"pending"``, which the gate service uses to mean
    "execution is in flight". For run-status purposes we collapse
    "never run" into ``None`` so the UI can hide the field rather
    than show a misleading ``"pending"``.
    """
    result = await session.execute(
        select(GateRecord)
        .where(GateRecord.run_id == run_id)
        .order_by(GateRecord.executed_at.desc())
        .limit(1)
    )
    gate = result.scalar_one_or_none()
    if gate is None:
        return None
    return "passed" if gate.passed else "failed"


@router.post("", response_model=RunCreateResponse, status_code=201)
async def create_run(
    config: RunConfig,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> RunCreateResponse:
    """creates a new run with the given config."""
    service = get_run_service()

    full_config: dict[str, Any] = {
        "budgets": config.budgets.model_dump(),
        "gates": config.gates.model_dump(),
        "fault_injection": config.fault_injection.model_dump(),
    }

    record = await service.create_run(session, seed=config.seed, config=full_config)
    return RunCreateResponse(run_id=record.id, request_id=request_id)


@router.get("", response_model=RunListResponse)
async def list_runs(
    status: str | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> RunListResponse:
    """lists runs with optional filters."""
    service = get_run_service()
    records, total = await service.list_runs(session, status=status, offset=offset, limit=limit)

    runs = []
    for r in records:
        budgets = r.config.get("budgets", {})
        gate_status = await _latest_gate_status(session, r.id)
        runs.append(
            RunStatus(
                run_id=r.id,
                status=r.status,  # type: ignore
                phase=r.phase,
                seed=r.seed,
                steps_used=r.steps_used,
                steps_remaining=budgets.get("max_steps", 240) - r.steps_used,
                tool_calls_used=r.tool_calls_used,
                tool_calls_remaining=budgets.get("max_tool_calls", 500) - r.tool_calls_used,
                belief_writes_used=r.belief_writes_used,
                belief_writes_remaining=budgets.get("max_belief_writes", 200)
                - r.belief_writes_used,
                gate_status=gate_status,
                failure_reason=r.failure_reason,
            )
        )

    return RunListResponse(runs=runs, offset=offset, limit=limit, total=total)


@router.post("/{run_id}/start")
async def start_run(
    run_id: str,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """starts orchestration for a pending run."""
    service = get_run_service()
    record = await service.start_run(session, run_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    return {"run_id": run_id, "status": "started", "phase": record.phase, "request_id": request_id}


@router.post("/{run_id}/execute")
async def execute_run(
    run_id: str,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """executes a run through all phases synchronously. Use for testing."""
    from ironroot.orchestration.executor import get_executor

    service = get_run_service()
    record = await service.get_run(session, run_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    # must be started first - this transitions to PROPOSE
    if record.status == "pending":
        await service.start_run(session, run_id)
        await session.commit()  # commit to ensure executor sees updated phase

    executor = get_executor()
    result = await executor.execute(session, run_id)
    result["request_id"] = request_id
    return result


@router.post("/{run_id}/execute_async", status_code=202)
async def execute_run_async(
    run_id: str,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Enqueues the run on Celery; returns the broker task id (Phase 3.2).

    The synchronous ``/execute`` route remains for tests and ops
    contexts where blocking is acceptable. Real operator-driven
    runs go through this route, which returns 202 + the task id
    immediately. Polling for completion happens via
    ``GET /runs/{run_id}`` (status + gate_status are populated as
    the worker progresses).

    Returns 404 if ``run_id`` does not exist — the broker would
    happily accept a phantom id, but failing loudly here matches
    the synchronous endpoint and prevents silent enqueue of bogus
    work.
    """
    from ironroot.orchestration.queue import enqueue_run

    service = get_run_service()
    record = await service.get_run(session, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    task_id = enqueue_run(run_id)
    return {
        "run_id": run_id,
        "task_id": task_id,
        "status": "enqueued",
        "request_id": request_id,
    }


@router.get("/{run_id}", response_model=RunStatus)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RunStatus:
    """returns current run status."""
    service = get_run_service()
    record = await service.get_run(session, run_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    budgets = record.config.get("budgets", {})
    gate_status = await _latest_gate_status(session, record.id)

    return RunStatus(
        run_id=record.id,
        status=record.status,  # type: ignore
        phase=record.phase,
        seed=record.seed,
        steps_used=record.steps_used,
        steps_remaining=budgets.get("max_steps", 240) - record.steps_used,
        tool_calls_used=record.tool_calls_used,
        tool_calls_remaining=budgets.get("max_tool_calls", 500) - record.tool_calls_used,
        belief_writes_used=record.belief_writes_used,
        belief_writes_remaining=budgets.get("max_belief_writes", 200) - record.belief_writes_used,
        gate_status=gate_status,
        failure_reason=record.failure_reason,
    )


@router.get("/{run_id}/trace")
async def get_trace(
    run_id: str,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Returns the belief subtree for ``run_id`` in seq order (Phase 3.2).

    The chain *is* the trace — every lifecycle / observation / gate
    result / violation belief written during the run, plus their
    parent hashes, content, and provenance. Ordered by the
    monotonic ``seq`` column so the output is byte-stable across
    reads.

    Pagination is offset/limit on the seq order. ``total`` is the
    full belief count for the run so a client can compute "is
    there more". An unknown ``run_id`` returns an empty page with
    ``total = 0`` rather than 404 — distinguishing "run never
    existed" from "run exists but has no beliefs yet" requires
    cross-checking the runs table, and the existing
    ``GET /runs/{run_id}`` endpoint already does that.
    """
    if limit <= 0 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be in [1, 1000]")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    count_result = await session.execute(
        select(BeliefRecord.id).where(BeliefRecord.run_id == run_id)
    )
    total = len(count_result.all())

    rows = await session.execute(
        select(BeliefRecord)
        .where(BeliefRecord.run_id == run_id)
        .order_by(BeliefRecord.seq.asc())
        .offset(offset)
        .limit(limit)
    )
    events = [
        {
            "belief_id": b.id,
            "seq": b.seq,
            "belief_type": b.belief_type,
            "agent_id": b.agent_id,
            "content_hash": b.content_hash,
            "parent_hash": b.parent_hash,
            "content": b.content,
            "confidence": b.confidence,
            "evidence_ids": b.evidence_ids,
            "topic_tags": b.topic_tags,
            "provenance": b.provenance,
            "created_at": b.created_at.isoformat(),
        }
        for b in rows.scalars().all()
    ]

    return {
        "run_id": run_id,
        "events": events,
        "offset": offset,
        "limit": limit,
        "total": total,
    }


@router.post("/{run_id}/stop")
async def stop_run(
    run_id: str,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """hard stops a run, freezing commits."""
    service = get_run_service()
    record = await service.stop_run(session, run_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    return {
        "run_id": run_id,
        "status": "stopped",
        "phase": record.phase,
        "request_id": request_id,
    }


@router.post("/{run_id}/gates/execute")
async def execute_gates(
    run_id: str,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """executes gate suite against run artifacts."""
    from ironroot.verification.gate_service import get_gate_service

    service = get_gate_service()
    try:
        gate = await service.execute_gates(session, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "run_id": run_id,
        "gate_id": gate.id,
        "status": "passed" if gate.passed else "failed",
        "artifact_id": gate.artifact_id,
        "request_id": request_id,
    }


@router.get("/{run_id}/gates/status")
async def get_gate_status(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """returns gate pass/fail with evidence artifact ids."""
    from ironroot.verification.gate_service import get_gate_service

    service = get_gate_service()
    status = await service.get_gate_status(session, run_id)
    return status
