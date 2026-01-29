# Author: Bradley R. Kinnard
"""run management endpoints."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ironroot.api.deps import RequestIdDep
from ironroot.domain.ids import generate_id

router = APIRouter()


class RunConfig(BaseModel):
    """configuration for a new run."""

    seed: int = Field(..., description="deterministic seed for replay")
    max_steps: int = Field(default=240, ge=1)
    max_tool_calls: int = Field(default=500, ge=1)
    max_belief_writes: int = Field(default=200, ge=1)
    replay_required: bool = Field(default=True)
    integrity_required: bool = Field(default=True)
    invariants_required: bool = Field(default=True)
    regression_required: bool = Field(default=True)


class RunCreateResponse(BaseModel):
    """response after creating a run."""

    run_id: str
    request_id: str


class RunStatus(BaseModel):
    """current state of a run."""

    run_id: str
    status: Literal["pending", "running", "completed", "failed", "stopped"]
    phase: str
    steps_used: int
    steps_remaining: int
    tool_calls_used: int
    tool_calls_remaining: int
    gate_status: Literal["pending", "passed", "failed"] | None


@router.post("", response_model=RunCreateResponse)
async def create_run(config: RunConfig, request_id: RequestIdDep) -> RunCreateResponse:
    """creates a new run with the given config."""
    run_id = generate_id("run")
    # todo: persist to db in phase 3
    return RunCreateResponse(run_id=run_id, request_id=request_id)


@router.post("/{run_id}/start")
async def start_run(run_id: str, request_id: RequestIdDep) -> dict[str, str]:
    """starts orchestration for a pending run."""
    # todo: queue supervisor task in phase 3
    return {"run_id": run_id, "status": "started", "request_id": request_id}


@router.get("/{run_id}", response_model=RunStatus)
async def get_run(run_id: str) -> RunStatus:
    """returns current run status."""
    # todo: fetch from db in phase 3
    return RunStatus(
        run_id=run_id,
        status="pending",
        phase="init",
        steps_used=0,
        steps_remaining=240,
        tool_calls_used=0,
        tool_calls_remaining=500,
        gate_status=None,
    )


@router.get("/{run_id}/trace")
async def get_trace(run_id: str, offset: int = 0, limit: int = 100) -> dict[str, object]:
    """returns paginated trace events for a run."""
    # todo: fetch trace from storage in phase 3
    return {"run_id": run_id, "events": [], "offset": offset, "limit": limit, "total": 0}


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, request_id: RequestIdDep) -> dict[str, str]:
    """hard stops a run, freezing commits."""
    # todo: implement kill switch in phase 3
    return {"run_id": run_id, "status": "stopped", "request_id": request_id}


@router.post("/{run_id}/gates/execute")
async def execute_gates(run_id: str, request_id: RequestIdDep) -> dict[str, object]:
    """executes gate suite against run artifacts."""
    # todo: implement in phase 4
    gate_id = generate_id("gat")
    return {"run_id": run_id, "gate_id": gate_id, "status": "pending", "request_id": request_id}


@router.get("/{run_id}/gates/status")
async def get_gate_status(run_id: str) -> dict[str, object]:
    """returns gate pass/fail with evidence artifact ids."""
    # todo: fetch from db in phase 4
    return {"run_id": run_id, "status": "pending", "artifact_ids": []}
