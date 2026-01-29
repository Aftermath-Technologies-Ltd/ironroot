# Author: Bradley R. Kinnard
"""belief management endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.api.deps import get_db_session
from ironroot.cognition.memory.belief_service import (
    get_belief_service,
    get_contradiction_service,
)
from ironroot.domain.errors import ImmutabilityViolation

router = APIRouter()


class BeliefResponse(BaseModel):
    """belief record response."""

    belief_id: str
    content_hash: str
    parent_hash: str | None
    agent_id: str
    run_id: str
    content: dict[str, Any]
    confidence: float
    created_at: str
    evidence_ids: list[str]
    topic_tags: list[str]


class BeliefCreateRequest(BaseModel):
    """request to create a new belief."""

    run_id: str
    agent_id: str
    content: dict[str, Any]
    confidence: float
    evidence_ids: list[str] | None = None
    topic_tags: list[str] | None = None


class BeliefListResponse(BaseModel):
    """paginated belief list response."""

    beliefs: list[BeliefResponse]
    offset: int
    limit: int
    total: int


class ContradictionResponse(BaseModel):
    """contradiction record response."""

    contradiction_id: str
    belief_id: str
    contradicts_belief_id: str
    reason: str
    detected_at: str


class ContradictionCreateRequest(BaseModel):
    """request to record a contradiction."""

    contradicts_belief_id: str
    reason: str


@router.post("", response_model=BeliefResponse, status_code=201)
async def create_belief(
    request: BeliefCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BeliefResponse:
    """creates a new belief, appending to the hash chain."""
    service = get_belief_service()
    record = await service.create_belief(
        session,
        run_id=request.run_id,
        agent_id=request.agent_id,
        content=request.content,
        confidence=request.confidence,
        evidence_ids=request.evidence_ids,
        topic_tags=request.topic_tags,
    )

    return BeliefResponse(
        belief_id=record.id,
        content_hash=record.content_hash,
        parent_hash=record.parent_hash,
        agent_id=record.agent_id,
        run_id=record.run_id,
        content=record.content,
        confidence=record.confidence,
        created_at=record.created_at.isoformat(),
        evidence_ids=record.evidence_ids,
        topic_tags=record.topic_tags,
    )


@router.get("", response_model=BeliefListResponse)
async def list_beliefs(
    agent_id: str | None = None,
    run_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> BeliefListResponse:
    """lists beliefs with optional filters."""
    service = get_belief_service()
    records, total = await service.list_beliefs(
        session, run_id=run_id, agent_id=agent_id, offset=offset, limit=limit
    )

    beliefs = [
        BeliefResponse(
            belief_id=r.id,
            content_hash=r.content_hash,
            parent_hash=r.parent_hash,
            agent_id=r.agent_id,
            run_id=r.run_id,
            content=r.content,
            confidence=r.confidence,
            created_at=r.created_at.isoformat(),
            evidence_ids=r.evidence_ids,
            topic_tags=r.topic_tags,
        )
        for r in records
    ]

    return BeliefListResponse(beliefs=beliefs, offset=offset, limit=limit, total=total)


@router.get("/{belief_id}", response_model=BeliefResponse)
async def get_belief(
    belief_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> BeliefResponse:
    """returns belief content, hashes, evidence pointers."""
    service = get_belief_service()
    record = await service.get_by_id(session, belief_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"belief not found: {belief_id}")

    return BeliefResponse(
        belief_id=record.id,
        content_hash=record.content_hash,
        parent_hash=record.parent_hash,
        agent_id=record.agent_id,
        run_id=record.run_id,
        content=record.content,
        confidence=record.confidence,
        created_at=record.created_at.isoformat(),
        evidence_ids=record.evidence_ids,
        topic_tags=record.topic_tags,
    )


@router.put("/{belief_id}")
async def update_belief(
    belief_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """intentionally rejects all updates - beliefs are immutable."""
    service = get_belief_service()
    try:
        await service.update_belief(session, belief_id, {})
    except ImmutabilityViolation as e:
        raise HTTPException(status_code=405, detail=str(e)) from e


@router.delete("/{belief_id}")
async def delete_belief(
    belief_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """intentionally rejects all deletes - beliefs are immutable."""
    service = get_belief_service()
    try:
        await service.delete_belief(session, belief_id)
    except ImmutabilityViolation as e:
        raise HTTPException(status_code=405, detail=str(e)) from e


@router.get("/{belief_id}/contradictions", response_model=list[ContradictionResponse])
async def get_contradictions(
    belief_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[ContradictionResponse]:
    """returns linked contradiction events."""
    service = get_contradiction_service()
    records = await service.get_for_belief(session, belief_id)

    return [
        ContradictionResponse(
            contradiction_id=r.id,
            belief_id=r.belief_id,
            contradicts_belief_id=r.contradicts_belief_id,
            reason=r.reason,
            detected_at=r.detected_at.isoformat(),
        )
        for r in records
    ]


@router.post("/{belief_id}/contradictions", response_model=ContradictionResponse, status_code=201)
async def create_contradiction(
    belief_id: str,
    request: ContradictionCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ContradictionResponse:
    """records a contradiction between beliefs."""
    service = get_contradiction_service()
    record = await service.record_contradiction(
        session,
        belief_id=belief_id,
        contradicts_belief_id=request.contradicts_belief_id,
        reason=request.reason,
    )

    return ContradictionResponse(
        contradiction_id=record.id,
        belief_id=record.belief_id,
        contradicts_belief_id=record.contradicts_belief_id,
        reason=record.reason,
        detected_at=record.detected_at.isoformat(),
    )


@router.get("/{belief_id}/chain/verify")
async def verify_belief_chain(
    belief_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """verifies the hash chain for the belief's run."""
    belief_service = get_belief_service()
    record = await belief_service.get_by_id(session, belief_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"belief not found: {belief_id}")

    is_valid = await belief_service.verify_chain(session, record.run_id)

    return {
        "belief_id": belief_id,
        "run_id": record.run_id,
        "chain_valid": is_valid,
    }
