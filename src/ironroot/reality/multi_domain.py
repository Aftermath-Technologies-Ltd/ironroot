# Author: Bradley R. Kinnard
"""Multi-domain reality falsification executor.

Runs prediction-locked tests across multiple reality domains.
Computes cross-domain survival rates and distribution shift metrics.
"""

import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.beliefs.belief_service import MetricClass, get_belief_service
from ironroot.reality.sources.adversarial import AdversarialSource
from ironroot.reality.sources.base import RealitySource
from ironroot.reality.sources.delayed import DelayedOutcomeSource
from ironroot.reality.sources.simulator import HiddenParamSimulator
from ironroot.reality.sources.tabular import TabularDatasetSource
from ironroot.reality.sources.time_series import TimeSeriesSource
from ironroot.storage.artifact_service import get_artifact_service


@dataclass
class DomainResult:
    """result from a single domain test."""

    domain: str
    source_type: str
    predictions_made: int
    predictions_confirmed: int
    predictions_contradicted: int
    total_penalty: float
    survived: bool


@dataclass
class CrossDomainResult:
    """aggregated result across multiple domains."""

    run_id: str
    domains_tested: int
    domains_survived: int
    cross_domain_survival_rate: float
    distribution_shift_failure_rate: float
    calibration_error: float
    domain_results: list[DomainResult]
    provenance_hashes: dict[str, str]


class MultiDomainExecutor:
    """executes prediction-locked tests across multiple reality domains."""

    DOMAIN_SOURCES = {
        "tabular_wine": lambda seed: TabularDatasetSource("wine_quality", seed=seed),
        "tabular_iris": lambda seed: TabularDatasetSource("iris", seed=seed),
        "timeseries_walk": lambda seed: TimeSeriesSource("synthetic_walk", seed=seed),
        "simulator_pendulum": lambda seed: HiddenParamSimulator("pendulum", seed=seed),
        "simulator_spring": lambda seed: HiddenParamSimulator("spring", seed=seed),
        "delayed_treatment": lambda seed: DelayedOutcomeSource("treatment_effect", seed=seed),
        "delayed_investment": lambda seed: DelayedOutcomeSource("investment_return", seed=seed),
        "adversarial_shift": lambda seed: AdversarialSource("covariate_shift", seed=seed),
        "adversarial_noise": lambda seed: AdversarialSource("label_noise", seed=seed),
    }

    def __init__(self):
        self._belief_service = get_belief_service()
        self._artifact_service = get_artifact_service()

    async def execute_cross_domain_test(
        self,
        session: AsyncSession,
        run_id: str,
        seed: int,
        domains: list[str],
        predictions_by_domain: dict[str, list[dict]],
    ) -> CrossDomainResult:
        """run predictions across multiple domains.

        Args:
            session: database session
            run_id: run identifier
            seed: random seed for reproducibility
            domains: list of domain names to test
            predictions_by_domain: predictions for each domain
        """
        domain_results = []
        provenance_hashes = {}
        calibration_errors = []

        for domain_name in domains:
            if domain_name not in self.DOMAIN_SOURCES:
                raise ValueError(f"unknown domain: {domain_name}")

            source = self.DOMAIN_SOURCES[domain_name](seed)
            predictions = predictions_by_domain.get(domain_name, [])

            if not predictions:
                continue

            result = await self._test_single_domain(
                session=session,
                run_id=run_id,
                source=source,
                predictions=predictions,
            )
            domain_results.append(result)

            # track provenance
            observations = await source.acquire_observations()
            if observations:
                provenance_hashes[domain_name] = observations[0].provenance.data_hash

            # track calibration error (prediction width vs actual error)
            if result.predictions_made > 0:
                # simplified calibration: confidence should match accuracy
                expected_accuracy = 0.9  # we expect 90% of predictions to be correct
                actual_accuracy = result.predictions_confirmed / result.predictions_made
                calibration_errors.append(abs(expected_accuracy - actual_accuracy))

        # compute aggregate metrics
        domains_survived = sum(1 for r in domain_results if r.survived)
        cross_domain_survival_rate = (
            domains_survived / len(domain_results) if domain_results else 0.0
        )

        # distribution shift failure: how many domains with shift attacks failed
        shift_domains = [
            r for r in domain_results if "shift" in r.domain or "adversarial" in r.domain
        ]
        shift_failures = sum(1 for r in shift_domains if not r.survived)
        distribution_shift_failure_rate = (
            shift_failures / len(shift_domains) if shift_domains else 0.0
        )

        calibration_error = (
            sum(calibration_errors) / len(calibration_errors) if calibration_errors else 0.0
        )

        # store cross-domain observations
        await self._belief_service.create_observation_belief(
            session=session,
            run_id=run_id,
            agent_id="multi_domain_executor",
            metric_name="cross_domain_survival_rate",
            value=round(cross_domain_survival_rate, 4),
            unit="ratio",
            method="cross-domain aggregation",
            metric_class=MetricClass.PRIMARY,
            artifact_ids=[],
            topic_tags=["cross_domain", "ril++"],
        )

        await self._belief_service.create_observation_belief(
            session=session,
            run_id=run_id,
            agent_id="multi_domain_executor",
            metric_name="distribution_shift_failure_rate",
            value=round(distribution_shift_failure_rate, 4),
            unit="ratio",
            method="adversarial domain aggregation",
            metric_class=MetricClass.PRIMARY,
            artifact_ids=[],
            topic_tags=["cross_domain", "adversarial"],
        )

        await self._belief_service.create_observation_belief(
            session=session,
            run_id=run_id,
            agent_id="multi_domain_executor",
            metric_name="calibration_error",
            value=round(calibration_error, 4),
            unit="ratio",
            method="prediction vs outcome calibration",
            metric_class=MetricClass.PRIMARY,
            artifact_ids=[],
            topic_tags=["cross_domain", "calibration"],
        )

        # store artifact
        artifact = await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps(
                {
                    "run_id": run_id,
                    "domains_tested": len(domain_results),
                    "domains_survived": domains_survived,
                    "cross_domain_survival_rate": cross_domain_survival_rate,
                    "distribution_shift_failure_rate": distribution_shift_failure_rate,
                    "calibration_error": calibration_error,
                    "domain_results": [
                        {
                            "domain": r.domain,
                            "source_type": r.source_type,
                            "survived": r.survived,
                            "predictions_made": r.predictions_made,
                            "predictions_confirmed": r.predictions_confirmed,
                            "total_penalty": r.total_penalty,
                        }
                        for r in domain_results
                    ],
                    "provenance_hashes": provenance_hashes,
                }
            ).encode(),
            artifact_type="cross_domain_report",
            created_by="multi_domain_executor",
            run_id=run_id,
            filename=f"cross_domain_{run_id}.json",
        )

        return CrossDomainResult(
            run_id=run_id,
            domains_tested=len(domain_results),
            domains_survived=domains_survived,
            cross_domain_survival_rate=cross_domain_survival_rate,
            distribution_shift_failure_rate=distribution_shift_failure_rate,
            calibration_error=calibration_error,
            domain_results=domain_results,
            provenance_hashes=provenance_hashes,
        )

    async def _test_single_domain(
        self,
        session: AsyncSession,
        run_id: str,
        source: RealitySource,
        predictions: list[dict],
    ) -> DomainResult:
        """test predictions against a single domain."""
        # create prediction beliefs
        prediction_beliefs = []
        for pred in predictions:
            belief = await self._belief_service.create_prediction_belief(
                session=session,
                run_id=run_id,
                agent_id="domain_predictor",
                source_id=source.source_id,
                metric_name=pred["metric_name"],
                predicted_lower=pred["lower"],
                predicted_upper=pred["upper"],
                unit=pred.get("unit", "value"),
                rationale=pred["rationale"],
                topic_tags=["multi_domain", source.domain],
            )
            prediction_beliefs.append(belief)

        # acquire reality
        observations = await source.acquire_observations()

        # evaluate predictions
        confirmed = 0
        contradicted = 0
        total_penalty = 0.0

        for pred_belief in prediction_beliefs:
            metric_name = pred_belief.content["metric_name"]

            # find matching observation
            matching_obs = None
            for obs in observations:
                if obs.metric_name == metric_name:
                    matching_obs = obs
                    break

            if matching_obs:
                # create observation belief
                obs_belief = await self._belief_service.create_observation_belief(
                    session=session,
                    run_id=run_id,
                    agent_id="reality_interface",
                    metric_name=matching_obs.metric_name,
                    value=matching_obs.value,
                    unit=matching_obs.unit,
                    method=matching_obs.provenance.acquisition_method,
                    metric_class=MetricClass.PRIMARY,
                    artifact_ids=[],
                    topic_tags=["reality", source.source_id],
                )

                is_confirmed, penalty = await self._belief_service.evaluate_prediction(
                    session=session,
                    prediction_id=pred_belief.id,
                    observed_value=matching_obs.value,
                    observation_id=obs_belief.id,
                )

                if is_confirmed:
                    confirmed += 1
                else:
                    contradicted += 1
                    total_penalty += penalty

        survived = contradicted == 0

        return DomainResult(
            domain=source.domain,
            source_type=source.source_type.value,
            predictions_made=len(prediction_beliefs),
            predictions_confirmed=confirmed,
            predictions_contradicted=contradicted,
            total_penalty=total_penalty,
            survived=survived,
        )


_executor: MultiDomainExecutor | None = None


def get_multi_domain_executor() -> MultiDomainExecutor:
    """returns shared multi-domain executor."""
    global _executor
    if _executor is None:
        _executor = MultiDomainExecutor()
    return _executor
