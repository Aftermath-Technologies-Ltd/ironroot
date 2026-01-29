# Author: Bradley R. Kinnard
"""strategy management endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.api.deps import RequestIdDep, get_db_session
from ironroot.cognition.strategies.strategy_service import get_strategy_service
from ironroot.domain.errors import GateFailed, NotFoundError

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
    manifest_hash: str
    gate_passed: bool
    promoted: bool
    correctness_score: float | None
    reproducibility_score: float | None
    efficiency_score: float | None
    safety_score: float | None


class StrategyListResponse(BaseModel):
    """paginated strategy list."""

    strategies: list[StrategyResponse]
    offset: int
    limit: int
    total: int


class MutateRequest(BaseModel):
    """mutation request."""

    seed: int
    mutation_rate: float = 0.1


@router.get("", response_model=StrategyListResponse)
async def list_strategies(
    name: str | None = None,
    promoted_only: bool = False,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> StrategyListResponse:
    """lists available strategy versions."""
    service = get_strategy_service()
    records, total = await service.list_strategies(
        session, name=name, promoted_only=promoted_only, offset=offset, limit=limit
    )

    strategies = [
        StrategyResponse(
            strategy_id=r.id,
            name=r.name,
            version=r.version,
            manifest_hash=r.manifest_hash,
            gate_passed=r.gate_passed,
            promoted=r.promoted,
            correctness_score=r.correctness_score,
            reproducibility_score=r.reproducibility_score,
            efficiency_score=r.efficiency_score,
            safety_score=r.safety_score,
        )
        for r in records
    ]

    return StrategyListResponse(strategies=strategies, offset=offset, limit=limit, total=total)


@router.post("", response_model=StrategyResponse, status_code=201)
async def register_strategy(
    manifest: StrategyManifest,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> StrategyResponse:
    """registers a new strategy version."""
    service = get_strategy_service()

    full_manifest: dict[str, Any] = {
        "capabilities": manifest.capabilities,
        "tool_permissions": manifest.tool_permissions,
        "abstention_threshold": manifest.abstention_threshold,
        "pinned_dependencies": manifest.pinned_dependencies,
    }

    record = await service.register_strategy(
        session,
        name=manifest.name,
        version=manifest.version,
        manifest=full_manifest,
    )

    return StrategyResponse(
        strategy_id=record.id,
        name=record.name,
        version=record.version,
        manifest_hash=record.manifest_hash,
        gate_passed=record.gate_passed,
        promoted=record.promoted,
        correctness_score=record.correctness_score,
        reproducibility_score=record.reproducibility_score,
        efficiency_score=record.efficiency_score,
        safety_score=record.safety_score,
    )


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> StrategyResponse:
    """returns strategy manifest, scoring history, failure incidents."""
    service = get_strategy_service()
    record = await service.get_strategy(session, strategy_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"strategy not found: {strategy_id}")

    return StrategyResponse(
        strategy_id=record.id,
        name=record.name,
        version=record.version,
        manifest_hash=record.manifest_hash,
        gate_passed=record.gate_passed,
        promoted=record.promoted,
        correctness_score=record.correctness_score,
        reproducibility_score=record.reproducibility_score,
        efficiency_score=record.efficiency_score,
        safety_score=record.safety_score,
    )


@router.post("/{strategy_id}/promote")
async def promote_strategy(
    strategy_id: str,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """promotes strategy to eligible set, only if gate passed."""
    service = get_strategy_service()

    try:
        record = await service.promote_strategy(session, strategy_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"strategy not found: {strategy_id}") from None
    except GateFailed as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    return {
        "strategy_id": record.id,
        "status": "promoted",
        "request_id": request_id,
    }


@router.post("/{strategy_id}/mutate", response_model=StrategyResponse, status_code=201)
async def mutate_strategy(
    strategy_id: str,
    request: MutateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> StrategyResponse:
    """creates a mutated variant from a base strategy."""
    service = get_strategy_service()

    try:
        record = await service.mutate_strategy(
            session,
            base_strategy_id=strategy_id,
            seed=request.seed,
            mutation_rate=request.mutation_rate,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"strategy not found: {strategy_id}") from None

    return StrategyResponse(
        strategy_id=record.id,
        name=record.name,
        version=record.version,
        manifest_hash=record.manifest_hash,
        gate_passed=record.gate_passed,
        promoted=record.promoted,
        correctness_score=record.correctness_score,
        reproducibility_score=record.reproducibility_score,
        efficiency_score=record.efficiency_score,
        safety_score=record.safety_score,
    )
