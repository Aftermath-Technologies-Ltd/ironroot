# Author: Bradley R. Kinnard
"""Reality Interface Layer API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.api.deps import RequestIdDep, get_db_session
from ironroot.beliefs.belief_service import get_belief_service
from ironroot.domain.ids import generate_id
from ironroot.reality import get_reality_interface, HiddenParameterDataset
from ironroot.reality.executor import get_reality_executor
from ironroot.orchestration.run_service import get_run_service

router = APIRouter()


class PredictionSpec(BaseModel):
    """a single prediction specification."""

    metric_name: str = Field(..., description="which metric to predict")
    lower: float = Field(..., description="lower bound of prediction")
    upper: float = Field(..., description="upper bound of prediction")
    rationale: str = Field(..., description="why this prediction was made")
    unit: str = Field(default="ratio", description="unit of measurement")


class FalsificationRunRequest(BaseModel):
    """request to run a prediction-locked falsification test."""

    source_seed: int = Field(..., description="seed for holdout split")
    predictions: list[PredictionSpec] = Field(..., description="predictions to make")


class FalsificationRunResponse(BaseModel):
    """response from a falsification run."""

    run_id: str
    source_id: str
    hypothesis_survived: bool
    contradictions_count: int
    total_penalty: float
    request_id: str


class PredictionOutcome(BaseModel):
    """outcome of a single prediction."""

    prediction_id: str
    metric_name: str
    predicted_lower: float
    predicted_upper: float
    observed_value: float
    confirmed: bool
    penalty: float


class FalsificationDetailResponse(BaseModel):
    """detailed response from a falsification run."""

    run_id: str
    source_id: str
    contract: dict[str, Any]
    predictions: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    outcomes: list[PredictionOutcome]
    contradictions_count: int
    total_penalty: float
    hypothesis_survived: bool
    provenance: dict[str, Any]


class SurvivalStatsResponse(BaseModel):
    """cross-run survival statistics."""

    source_id: str
    total_predictions: int
    survived_all_runs: int
    contradicted_once: int
    contradicted_multiple: int
    metrics: dict[str, Any]


@router.post("/falsification", response_model=FalsificationRunResponse, status_code=201)
async def run_falsification_test(
    request: FalsificationRunRequest,
    request_id: RequestIdDep,
    session: AsyncSession = Depends(get_db_session),
) -> FalsificationRunResponse:
    """runs a prediction-locked falsification test against external reality.

    Flow:
    1. Creates a new run
    2. Registers external reality source
    3. Locks predictions BEFORE observing reality
    4. Acquires reality observations
    5. Automatically evaluates predictions
    6. Returns contradiction count and penalties
    """
    # create a new run for this test
    run_service = get_run_service()
    run_record = await run_service.create_run(
        session,
        seed=request.source_seed,
        config={
            "test_type": "reality_falsification",
            "source_seed": request.source_seed,
            "prediction_count": len(request.predictions),
        },
    )

    executor = get_reality_executor()

    predictions = [
        {
            "metric_name": p.metric_name,
            "lower": p.lower,
            "upper": p.upper,
            "rationale": p.rationale,
            "unit": p.unit,
        }
        for p in request.predictions
    ]

    result = await executor.execute_falsification_run(
        session=session,
        run_id=run_record.id,
        source_seed=request.source_seed,
        predictions=predictions,
    )

    return FalsificationRunResponse(
        run_id=result.run_id,
        source_id=result.source_id,
        hypothesis_survived=result.hypothesis_survived,
        contradictions_count=result.contradictions_count,
        total_penalty=result.total_penalty,
        request_id=request_id,
    )


@router.get("/falsification/{run_id}", response_model=FalsificationDetailResponse)
async def get_falsification_details(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> FalsificationDetailResponse:
    """returns detailed results from a falsification run."""
    belief_service = get_belief_service()

    # get all beliefs for this run
    from sqlalchemy import select
    from ironroot.storage.models import BeliefRecord
    from ironroot.beliefs.belief_service import BeliefType

    result = await session.execute(
        select(BeliefRecord).where(BeliefRecord.run_id == run_id)
    )
    beliefs = list(result.scalars().all())

    predictions = [b for b in beliefs if b.belief_type == BeliefType.PREDICTION.value]
    observations = [b for b in beliefs if b.belief_type == BeliefType.OBSERVATION.value]

    if not predictions:
        raise HTTPException(status_code=404, detail=f"no predictions found for run {run_id}")

    # extract source_id from first prediction
    source_id = predictions[0].content.get("source_id", "unknown")

    # get contract from artifacts
    from ironroot.storage.models import ArtifactRecord
    art_result = await session.execute(
        select(ArtifactRecord)
        .where(ArtifactRecord.run_id == run_id)
        .where(ArtifactRecord.artifact_type == "reality_contract")
    )
    contract_artifact = art_result.scalar_one_or_none()
    contract = {}
    if contract_artifact:
        import json
        from ironroot.storage.artifact_service import get_artifact_service
        artifact_service = get_artifact_service()
        contract_data = artifact_service.retrieve_data(contract_artifact.content_hash)
        if contract_data:
            contract = json.loads(contract_data.decode())

    # get provenance from artifacts
    prov_result = await session.execute(
        select(ArtifactRecord)
        .where(ArtifactRecord.run_id == run_id)
        .where(ArtifactRecord.artifact_type == "reality_observations")
    )
    prov_artifact = prov_result.scalar_one_or_none()
    provenance = {}
    obs_list = []
    if prov_artifact:
        import json
        from ironroot.storage.artifact_service import get_artifact_service
        artifact_service = get_artifact_service()
        prov_data = artifact_service.retrieve_data(prov_artifact.content_hash)
        if prov_data:
            prov_json = json.loads(prov_data.decode())
            obs_list = prov_json.get("observations", [])
            if obs_list:
                provenance = obs_list[0].get("provenance", {})

    # build outcomes
    outcomes = []
    contradictions = 0
    total_penalty = 0.0

    for pred in predictions:
        content = pred.content
        outcomes.append(PredictionOutcome(
            prediction_id=pred.id,
            metric_name=content.get("metric_name", "unknown"),
            predicted_lower=content.get("predicted_lower", 0),
            predicted_upper=content.get("predicted_upper", 0),
            observed_value=content.get("observed_value", 0) or 0,
            confirmed=content.get("status") == "confirmed",
            penalty=content.get("penalty_applied", 0) or 0,
        ))
        if content.get("status") == "contradicted":
            contradictions += 1
            total_penalty += content.get("penalty_applied", 0) or 0

    return FalsificationDetailResponse(
        run_id=run_id,
        source_id=source_id,
        contract=contract,
        predictions=[p.content for p in predictions],
        observations=[o.content for o in observations],
        outcomes=outcomes,
        contradictions_count=contradictions,
        total_penalty=total_penalty,
        hypothesis_survived=contradictions == 0,
        provenance=provenance,
    )


@router.get("/survival/{source_id}", response_model=SurvivalStatsResponse)
async def get_survival_stats(
    source_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> SurvivalStatsResponse:
    """returns cross-run survival statistics for predictions on a source."""
    belief_service = get_belief_service()
    stats = await belief_service.get_prediction_survival_stats(session, source_id)

    return SurvivalStatsResponse(
        source_id=stats["source_id"],
        total_predictions=stats["total_predictions"],
        survived_all_runs=stats["survived_all_runs"],
        contradicted_once=stats["contradicted_once"],
        contradicted_multiple=stats["contradicted_multiple"],
        metrics=stats["metrics"],
    )
