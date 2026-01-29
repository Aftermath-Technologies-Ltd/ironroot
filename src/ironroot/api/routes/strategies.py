# Author: Bradley R. Kinnard
"""strategy management endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ironroot.api.deps import RequestIdDep
from ironroot.domain.ids import generate_id

router = APIRouter()


class StrategyManifest(BaseModel):
    """strategy registration request."""

    name: str
    version: str
    capabilities: list[str]
    tool_permissions: list[str]
    abstention_threshold: float
    pinned_dependencies: dict[str, str]


class StrategyResponse(BaseModel):
    """strategy response."""

    strategy_id: str
    name: str
    version: str
    status: str
    gate_passed: bool
    scoring_history: list[dict[str, object]]


@router.get("", response_model=list[StrategyResponse])
async def list_strategies() -> list[StrategyResponse]:
    """lists available strategy versions."""
    # todo: query db in phase 6
    return []


@router.post("", response_model=StrategyResponse)
async def register_strategy(
    manifest: StrategyManifest, request_id: RequestIdDep
) -> StrategyResponse:
    """registers a new strategy version."""
    strategy_id = generate_id("str")
    # todo: persist to db in phase 6
    return StrategyResponse(
        strategy_id=strategy_id,
        name=manifest.name,
        version=manifest.version,
        status="registered",
        gate_passed=False,
        scoring_history=[],
    )


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: str) -> StrategyResponse:
    """returns strategy manifest, scoring history, failure incidents."""
    # todo: fetch from db in phase 6
    raise HTTPException(status_code=404, detail=f"strategy not found: {strategy_id}")


@router.post("/{strategy_id}/promote")
async def promote_strategy(strategy_id: str, request_id: RequestIdDep) -> dict[str, str]:
    """promotes strategy to eligible set, only if gate passed."""
    # todo: check gate status in phase 6
    raise HTTPException(status_code=400, detail="gate not passed, promotion blocked")
