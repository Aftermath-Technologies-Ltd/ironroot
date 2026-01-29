# Author: Bradley R. Kinnard
"""run management endpoints."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.api.deps import RequestIdDep, get_db_session
from ironroot.domain.ids import generate_id
from ironroot.orchestration.run_service import get_run_service

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


class RunConfig(BaseModel):
    """configuration for a new run."""

    seed: int = Field(..., description="deterministic seed for replay")
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)
    gates: GatesConfig = Field(default_factory=GatesConfig)


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
                gate_status=None,
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
        gate_status=None,
        failure_reason=record.failure_reason,
    )


@router.get("/{run_id}/trace")
async def get_trace(
    run_id: str,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """returns paginated trace events for a run."""
    # trace retrieval - placeholder for now, will be artifact-based
    return {"run_id": run_id, "events": [], "offset": offset, "limit": limit, "total": 0}


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
    # implemented in phase 4
    gate_id = generate_id("gat")
    return {"run_id": run_id, "gate_id": gate_id, "status": "pending", "request_id": request_id}


@router.get("/{run_id}/gates/status")
async def get_gate_status(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """returns gate pass/fail with evidence artifact ids."""
    # implemented in phase 4
    return {"run_id": run_id, "status": "pending", "artifact_ids": []}
