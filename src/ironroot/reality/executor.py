# Author: Bradley R. Kinnard
"""Reality falsification executor - runs prediction-locked tests against external reality."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.beliefs.belief_service import (
    MetricClass,
    get_belief_service,
)
from ironroot.orchestration.supervisor import RunPhase
from ironroot.reality import (
    HiddenParameterDataset,
    RealityInterfaceLayer,
    get_reality_interface,
)
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import RunRecord


@dataclass
class PredictionResult:
    """result of a single prediction evaluation."""

    prediction_id: str
    metric_name: str
    predicted_lower: float
    predicted_upper: float
    observed_value: float
    confirmed: bool
    penalty: float


@dataclass
class FalsificationRunResult:
    """result of a prediction-locked falsification run."""

    run_id: str
    source_id: str
    contract: dict[str, Any]
    predictions: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    results: list[PredictionResult]
    contradictions_count: int
    total_penalty: float
    hypothesis_survived: bool
    provenance: dict[str, Any]


class RealityFalsificationExecutor:
    """executes prediction-locked falsification tests.

    Flow:
    1. Register external reality source, get contract
    2. Lock the observation channel
    3. Write prediction beliefs BEFORE seeing reality
    4. Acquire reality observations
    5. Automatically evaluate predictions vs reality
    6. Apply penalties, record contradictions
    """

    def __init__(self, ril: RealityInterfaceLayer | None = None):
        self._ril = ril or get_reality_interface()
        self._belief_service = get_belief_service()
        self._artifact_service = get_artifact_service()

    async def execute_falsification_run(
        self,
        session: AsyncSession,
        run_id: str,
        source_seed: int,
        predictions: list[dict[str, Any]],
    ) -> FalsificationRunResult:
        """executes a complete prediction-locked falsification test.

        Args:
            session: database session
            run_id: the run id for this test
            source_seed: seed for holdout split (different seeds = different reality)
            predictions: list of predictions to make, each with:
                - metric_name: which metric to predict
                - lower: lower bound of prediction
                - upper: upper bound of prediction
                - rationale: why this prediction was made
        """
        # Step 1: Register external reality source
        source = HiddenParameterDataset(holdout_fraction=0.2, seed=source_seed)
        contract = self._ril.register_source(source)

        # store contract as artifact
        contract_artifact = await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps(contract).encode(),
            artifact_type="reality_contract",
            created_by="reality_interface",
            run_id=run_id,
            filename=f"reality_contract_{run_id}.json",
        )

        # Step 2: Lock the observation channel
        self._ril.lock_channel(source.source_id)

        # Step 3: Write prediction beliefs BEFORE observation
        prediction_beliefs = []
        for pred in predictions:
            belief = await self._belief_service.create_prediction_belief(
                session=session,
                run_id=run_id,
                agent_id="prediction_agent",
                source_id=source.source_id,
                metric_name=pred["metric_name"],
                predicted_lower=pred["lower"],
                predicted_upper=pred["upper"],
                unit=pred.get("unit", "ratio"),
                rationale=pred["rationale"],
                topic_tags=["reality_test", source.source_id],
            )
            prediction_beliefs.append(belief)

        # store predictions artifact (proof they were locked before observation)
        predictions_artifact = await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps(
                {
                    "predictions": [
                        {
                            "id": b.id,
                            "metric_name": b.content["metric_name"],
                            "predicted_lower": b.content["predicted_lower"],
                            "predicted_upper": b.content["predicted_upper"],
                            "locked_at": b.content["locked_at"],
                        }
                        for b in prediction_beliefs
                    ],
                    "channel_locked": True,
                    "observations_acquired": False,
                }
            ).encode(),
            artifact_type="prediction_lock_proof",
            created_by="reality_interface",
            run_id=run_id,
            filename=f"prediction_lock_{run_id}.json",
        )

        # Step 4: Transition run to VERIFY phase (required for observation beliefs)
        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(phase=RunPhase.VERIFY.value, status="running")
        )
        await session.flush()

        # Step 5: Acquire reality observations (AFTER predictions are locked)
        observations = await self._ril.acquire_reality(source.source_id)

        # store observations as artifact
        observations_artifact = await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps(
                {
                    "observations": [o.to_dict() for o in observations],
                    "acquisition_timestamp": datetime.now(UTC).isoformat(),
                }
            ).encode(),
            artifact_type="reality_observations",
            created_by="reality_interface",
            run_id=run_id,
            filename=f"reality_observations_{run_id}.json",
        )

        # create observation beliefs for each reality observation
        observation_beliefs = []
        for obs in observations:
            obs_belief = await self._belief_service.create_observation_belief(
                session=session,
                run_id=run_id,
                agent_id="reality_interface",
                metric_name=obs.metric_name,
                value=obs.value,
                unit=obs.unit,
                method=obs.provenance.acquisition_method,
                metric_class=MetricClass.PRIMARY,
                artifact_ids=[observations_artifact.id],
                topic_tags=["reality", source.source_id, obs.metric_name],
            )
            observation_beliefs.append((obs, obs_belief))

        # Step 5: Automatic evaluation - no agent discretion
        results = []
        total_penalty = 0.0
        contradictions = 0

        for pred_belief in prediction_beliefs:
            metric_name = pred_belief.content["metric_name"]

            # find matching observation
            matching_obs = None
            matching_belief = None
            for obs, obs_belief in observation_beliefs:
                if obs.metric_name == metric_name:
                    matching_obs = obs
                    matching_belief = obs_belief
                    break

            if matching_obs and matching_belief:
                confirmed, penalty = await self._belief_service.evaluate_prediction(
                    session=session,
                    prediction_id=pred_belief.id,
                    observed_value=matching_obs.value,
                    observation_id=matching_belief.id,
                )

                results.append(
                    PredictionResult(
                        prediction_id=pred_belief.id,
                        metric_name=metric_name,
                        predicted_lower=pred_belief.content["predicted_lower"],
                        predicted_upper=pred_belief.content["predicted_upper"],
                        observed_value=matching_obs.value,
                        confirmed=confirmed,
                        penalty=penalty,
                    )
                )

                total_penalty += penalty
                if not confirmed:
                    contradictions += 1

        # Step 6: Generate contradiction report artifact
        contradiction_artifact = await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps(
                {
                    "run_id": run_id,
                    "source_id": source.source_id,
                    "total_predictions": len(prediction_beliefs),
                    "contradictions": contradictions,
                    "total_penalty": total_penalty,
                    "results": [
                        {
                            "prediction_id": r.prediction_id,
                            "metric_name": r.metric_name,
                            "predicted_range": [r.predicted_lower, r.predicted_upper],
                            "observed_value": r.observed_value,
                            "confirmed": r.confirmed,
                            "penalty": r.penalty,
                        }
                        for r in results
                    ],
                    "evaluated_at": datetime.now(UTC).isoformat(),
                }
            ).encode(),
            artifact_type="contradiction_report",
            created_by="reality_interface",
            run_id=run_id,
            filename=f"contradiction_report_{run_id}.json",
        )

        # get provenance proof
        provenance = self._ril.get_provenance_proof(source.source_id)

        # hypothesis survives if all predictions confirmed
        hypothesis_survived = contradictions == 0

        return FalsificationRunResult(
            run_id=run_id,
            source_id=source.source_id,
            contract=contract,
            predictions=[b.content for b in prediction_beliefs],
            observations=[o.to_dict() for o in observations],
            results=results,
            contradictions_count=contradictions,
            total_penalty=total_penalty,
            hypothesis_survived=hypothesis_survived,
            provenance=provenance,
        )


_executor: RealityFalsificationExecutor | None = None


def get_reality_executor() -> RealityFalsificationExecutor:
    """returns shared reality falsification executor."""
    global _executor
    if _executor is None:
        _executor = RealityFalsificationExecutor()
    return _executor
