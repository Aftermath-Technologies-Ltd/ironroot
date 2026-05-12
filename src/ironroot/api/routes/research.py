# Author: Bradley R. Kinnard
"""Research API endpoints for researcher-facing interface."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ironroot.research.service import (
    ResearchStatus,
    get_research_results,
    get_research_status,
    submit_research,
)
from ironroot.storage.postgres import get_session

router = APIRouter()


class SubmitResearchRequest(BaseModel):
    """Request to submit new research."""

    criteria: str
    seed: int | None = None


class SubmitResearchResponse(BaseModel):
    """Response from submitting research."""

    research_id: str
    status: str
    message: str
    estimated_time_seconds: int


class ProgressResponse(BaseModel):
    """Current progress of research."""

    status: str
    percent: int
    phase_description: str
    eta_seconds: int | None
    phases_completed: list[str]
    current_phase: str
    details: dict[str, Any]


class FindingResponse(BaseModel):
    """A research finding."""

    finding_type: str
    summary: str
    metric_name: str | None
    value: float | None
    context: str


class EvidenceResponse(BaseModel):
    """An evidence artifact."""

    artifact_id: str
    artifact_type: str
    content_hash: str
    summary: str
    created_at: str
    expandable_data: dict[str, Any] | None


class ResultsResponse(BaseModel):
    """Complete research results."""

    research_id: str
    original_criteria: str
    summary: str
    findings: list[FindingResponse]
    evidence: list[EvidenceResponse]
    questions_generated: int
    hypotheses_formed: int
    hypotheses_supported: int
    hypotheses_falsified: int
    hypotheses_revised: int
    experiments_run: int
    data_sources_queried: int
    started_at: str
    completed_at: str
    duration_seconds: float
    gate_passed: bool


@router.post("/submit", response_model=SubmitResearchResponse)
async def submit_research_endpoint(request: SubmitResearchRequest) -> SubmitResearchResponse:
    """Submit a new research request.

    Accepts natural language criteria from researchers and starts
    an autonomous research campaign.
    """
    if not request.criteria or len(request.criteria.strip()) < 10:
        raise HTTPException(
            status_code=400, detail="Research criteria must be at least 10 characters"
        )

    async with get_session() as session:
        research_id = await submit_research(
            session=session,
            criteria=request.criteria.strip(),
            seed=request.seed,
        )

    return SubmitResearchResponse(
        research_id=research_id,
        status="pending",
        message="Research submitted successfully. Track progress using the status endpoint.",
        estimated_time_seconds=120,
    )


@router.get("/{research_id}/status", response_model=ProgressResponse)
async def get_status_endpoint(research_id: str) -> ProgressResponse:
    """Get current progress of a research job."""
    progress = await get_research_status(research_id)

    if not progress:
        raise HTTPException(status_code=404, detail=f"Research job {research_id} not found")

    return ProgressResponse(
        status=progress.status.value,
        percent=progress.percent,
        phase_description=progress.phase_description,
        eta_seconds=progress.eta_seconds,
        phases_completed=progress.phases_completed,
        current_phase=progress.current_phase,
        details=progress.details,
    )


@router.get("/{research_id}/results", response_model=ResultsResponse)
async def get_results_endpoint(research_id: str) -> ResultsResponse:
    """Get results of a completed research job."""
    results = await get_research_results(research_id)

    if not results:
        # Check if job exists but isn't complete
        progress = await get_research_status(research_id)
        if progress:
            if progress.status == ResearchStatus.FAILED:
                raise HTTPException(status_code=500, detail="Research job failed")
            raise HTTPException(
                status_code=202, detail=f"Research still in progress: {progress.percent}% complete"
            )
        raise HTTPException(status_code=404, detail=f"Research job {research_id} not found")

    return ResultsResponse(
        research_id=results.research_id,
        original_criteria=results.original_criteria,
        summary=results.summary,
        findings=[
            FindingResponse(
                finding_type=f.finding_type,
                summary=f.summary,
                metric_name=f.metric_name,
                value=f.value,
                context=f.context,
            )
            for f in results.findings
        ],
        evidence=[
            EvidenceResponse(
                artifact_id=e.artifact_id,
                artifact_type=e.artifact_type,
                content_hash=e.content_hash,
                summary=e.summary,
                created_at=e.created_at,
                expandable_data=e.expandable_data,
            )
            for e in results.evidence
        ],
        questions_generated=results.questions_generated,
        hypotheses_formed=results.hypotheses_formed,
        hypotheses_supported=results.hypotheses_supported,
        hypotheses_falsified=results.hypotheses_falsified,
        hypotheses_revised=results.hypotheses_revised,
        experiments_run=results.experiments_run,
        data_sources_queried=results.data_sources_queried,
        started_at=results.started_at,
        completed_at=results.completed_at,
        duration_seconds=results.duration_seconds,
        gate_passed=results.gate_passed,
    )
