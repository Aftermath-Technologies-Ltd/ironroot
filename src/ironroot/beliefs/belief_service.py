# Author: Bradley R. Kinnard
"""belief service with strict research discipline enforcement."""

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.errors import InvariantViolation
from ironroot.domain.ids import generate_id
from ironroot.orchestration.supervisor import RunPhase
from ironroot.storage.models import ArtifactRecord, BeliefRecord, RunRecord


class BeliefType(str, Enum):
    """explicit belief categories."""

    LIFECYCLE = "lifecycle"  # run_start, run_end, phase transitions - NOT research
    OBSERVATION = "observation"  # numeric measurements, zero interpretation
    HYPOTHESIS = "hypothesis"  # claims about causation, max 1 per run
    PREDICTION = "prediction"  # locked claims about future reality, penalties apply


class MetricClass(str, Enum):
    """observation metric classification."""

    PRIMARY = "primary"  # directly measures the capability under test
    SECONDARY = "secondary"  # operational/bookkeeping metrics


class PredictionStatus(str, Enum):
    """prediction belief status."""

    PENDING = "pending"  # awaiting reality observation
    CONFIRMED = "confirmed"  # observation fell within predicted range
    CONTRADICTED = "contradicted"  # observation fell outside predicted range


# phases where observation beliefs are allowed
OBSERVATION_ALLOWED_PHASES = {RunPhase.TEST, RunPhase.VERIFY, RunPhase.AUDIT, RunPhase.DECIDE}

# forbidden interpretation language in observations
INTERPRETATION_PATTERNS = [
    r"\b(better|worse|good|bad|improved|degraded)\b",
    r"\b(suggests?|implies?|indicates?|proves?|shows?)\b",
    r"\b(because|therefore|thus|hence|consequently)\b",
    r"\b(likely|probably|possibly|seems?|appears?)\b",
]

# required verifier artifact types for hypothesis formation
VERIFIER_ARTIFACT_TYPES = {
    "falsification_report",
    "replay_report",
    "contradiction_report",
    "verification_report",
}

# primary outcome metric names that indicate real research
PRIMARY_METRIC_NAMES = {
    # determinism/replay metrics
    "replay_digest_match",
    "trace_hash_match",
    "artifact_hash_match",
    "nondeterminism_events",
    # belief/contradiction metrics
    "false_positive_rate",
    "contradiction_rate",
    "self_correction_latency_ms",
    "belief_stability_score",
    # verification metrics
    "verifier_counterexample_count",
    "falsification_success_rate",
    # comparison metrics
    "condition_a_outcome",
    "condition_b_outcome",
    "effect_size",
    "statistical_significance",
    # self-healing metrics
    "time_to_containment_ms",
    "time_to_recovery_ms",
    "recovery_attempts",
    "regression_tests_added",
    "recurrence_rate",
    "fault_detected",
    "repair_successful",
    # reality interface metrics (external data)
    "mean_quality",
    "std_quality",
    "correlation_alcohol_quality",
    "high_quality_fraction",
}


class BeliefService:
    """enforces research belief discipline: types, phases, and semantic requirements."""

    async def create_lifecycle_belief(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        content: dict[str, Any],
        topic_tags: list[str],
        parent_hash: str | None = None,
    ) -> BeliefRecord:
        """creates a lifecycle belief. No restrictions - internal bookkeeping."""
        return await self._create_belief(
            session=session,
            run_id=run_id,
            agent_id=agent_id,
            belief_type=BeliefType.LIFECYCLE,
            content=content,
            confidence=1.0,
            topic_tags=["lifecycle", *topic_tags],
            parent_hash=parent_hash,
            evidence_ids=[],
        )

    async def create_observation_belief(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        metric_name: str,
        value: int | float | bool,
        unit: str,
        method: str,
        metric_class: MetricClass,
        artifact_ids: list[str],
        topic_tags: list[str],
        comparator: str | None = None,
        parent_hash: str | None = None,
    ) -> BeliefRecord:
        """creates an observation belief with strict schema enforcement."""
        # rule 1: check run phase
        run = await self._get_run(session, run_id)
        if not run:
            raise InvariantViolation("belief_run_exists", f"run {run_id} not found")

        current_phase = RunPhase(run.phase)
        if current_phase not in OBSERVATION_ALLOWED_PHASES:
            raise InvariantViolation(
                "observation_phase",
                f"observation beliefs only allowed after test/verify, current phase: {current_phase.value}",
            )

        # rule 2: must include artifact references
        if not artifact_ids:
            raise InvariantViolation(
                "observation_evidence",
                "observation beliefs must reference at least one artifact",
            )

        # rule 3: primary metrics must use recognized names
        if metric_class == MetricClass.PRIMARY:
            if metric_name not in PRIMARY_METRIC_NAMES:
                raise InvariantViolation(
                    "observation_primary_metric",
                    f"primary metric '{metric_name}' not recognized. "
                    f"Valid names: {sorted(PRIMARY_METRIC_NAMES)[:5]}...",
                )

        # rule 4: no interpretation language in method description
        for pattern in INTERPRETATION_PATTERNS:
            if re.search(pattern, method, re.IGNORECASE):
                raise InvariantViolation(
                    "observation_interpretation",
                    f"method description must not contain interpretation language",
                )

        # build structured content
        content = {
            "metric_name": metric_name,
            "value": value,
            "unit": unit,
            "method": method,
            "metric_class": metric_class.value,
        }
        if comparator:
            content["comparator"] = comparator

        return await self._create_belief(
            session=session,
            run_id=run_id,
            agent_id=agent_id,
            belief_type=BeliefType.OBSERVATION,
            content=content,
            confidence=1.0,
            topic_tags=["observation", metric_class.value, *topic_tags],
            parent_hash=parent_hash,
            evidence_ids=artifact_ids,
        )

    async def create_hypothesis_belief(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        claim: str,
        observation_ids: list[str],
        verifier_artifact_id: str,
        scope: str,
        limitations: list[str],
        failed_checks: list[dict[str, str]],  # [{"check": "name", "reason": "why not fatal"}]
        topic_tags: list[str],
        parent_hash: str | None = None,
        contradicted: bool = False,
    ) -> BeliefRecord:
        """creates a hypothesis belief with strict evidence requirements."""
        # rule 1: max 1 hypothesis per run
        existing = await self._count_hypotheses(session, run_id)
        if existing >= 1:
            raise InvariantViolation(
                "hypothesis_limit",
                f"run {run_id} already has {existing} hypothesis belief(s), max is 1",
            )

        # rule 2: must reference at least 2 observations
        if len(observation_ids) < 2:
            raise InvariantViolation(
                "hypothesis_observations",
                f"hypothesis must reference at least 2 observations, got {len(observation_ids)}",
            )

        # rule 3: must include at least 1 primary outcome observation
        primary_count = await self._count_primary_observations(session, observation_ids)
        if primary_count < 1:
            raise InvariantViolation(
                "hypothesis_primary_outcome",
                "hypothesis must reference at least 1 primary outcome observation, "
                "not just secondary/bookkeeping metrics",
            )

        # rule 4: verifier artifact must be of correct type
        verifier = await self._get_artifact(session, verifier_artifact_id)
        if not verifier:
            raise InvariantViolation(
                "hypothesis_verifier_exists",
                f"verifier artifact {verifier_artifact_id} not found",
            )
        if verifier.artifact_type not in VERIFIER_ARTIFACT_TYPES:
            raise InvariantViolation(
                "hypothesis_verifier_type",
                f"verifier artifact must be one of {VERIFIER_ARTIFACT_TYPES}, "
                f"got '{verifier.artifact_type}'",
            )

        # rule 5: must have scope and limitations
        if not scope:
            raise InvariantViolation("hypothesis_scope", "hypothesis must define explicit scope")
        if not limitations:
            raise InvariantViolation(
                "hypothesis_limitations", "hypothesis must list at least one limitation"
            )

        # rule 6: any failed checks must be explained in limitations
        if failed_checks:
            for fc in failed_checks:
                check_name = fc.get("check", "unknown")
                reason = fc.get("reason", "")
                if not reason:
                    raise InvariantViolation(
                        "hypothesis_failed_check",
                        f"failed check '{check_name}' must have an explanation of why it doesn't invalidate the claim",
                    )
                # verify the explanation is in limitations
                if not any(check_name in lim for lim in limitations):
                    raise InvariantViolation(
                        "hypothesis_failed_check_limitation",
                        f"failed check '{check_name}' must be mentioned in limitations",
                    )

        # build structured content
        full_content = {
            "claim": claim,
            "scope": scope,
            "limitations": limitations,
            "observation_refs": observation_ids,
            "verifier_artifact": verifier_artifact_id,
            "verifier_type": verifier.artifact_type,
            "failed_checks": failed_checks,
            "contradicted": contradicted,
        }

        return await self._create_belief(
            session=session,
            run_id=run_id,
            agent_id=agent_id,
            belief_type=BeliefType.HYPOTHESIS,
            content=full_content,
            confidence=0.0 if contradicted else 1.0,
            topic_tags=["hypothesis", *topic_tags],
            parent_hash=parent_hash,
            evidence_ids=[verifier_artifact_id, *observation_ids],
        )

    async def mark_hypothesis_contradicted(
        self, session: AsyncSession, hypothesis_id: str, reason: str
    ) -> BeliefRecord:
        """marks a hypothesis as contradicted by verifier."""
        result = await session.execute(
            select(BeliefRecord).where(BeliefRecord.id == hypothesis_id)
        )
        belief = result.scalar_one_or_none()
        if not belief:
            raise InvariantViolation("hypothesis_exists", f"belief {hypothesis_id} not found")
        if belief.belief_type != BeliefType.HYPOTHESIS.value:
            raise InvariantViolation(
                "hypothesis_type", f"belief {hypothesis_id} is not a hypothesis"
            )

        # update content to mark as contradicted
        new_content = {**belief.content, "contradicted": True, "contradiction_reason": reason}
        belief.content = new_content
        belief.confidence = 0.0
        await session.flush()
        return belief

    async def create_prediction_belief(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        source_id: str,
        metric_name: str,
        predicted_lower: float,
        predicted_upper: float,
        unit: str,
        rationale: str,
        topic_tags: list[str],
        parent_hash: str | None = None,
    ) -> BeliefRecord:
        """creates a locked prediction belief before reality observation.

        Predictions are immutable once written. Penalties apply if contradicted.
        Must be created BEFORE observations from the source are acquired.
        """
        # rule: predictions must have valid bounds
        if predicted_lower > predicted_upper:
            raise InvariantViolation(
                "prediction_bounds",
                f"lower bound {predicted_lower} cannot exceed upper bound {predicted_upper}",
            )

        content = {
            "source_id": source_id,
            "metric_name": metric_name,
            "predicted_lower": predicted_lower,
            "predicted_upper": predicted_upper,
            "unit": unit,
            "rationale": rationale,
            "status": PredictionStatus.PENDING.value,
            "locked_at": datetime.utcnow().isoformat(),
            "observed_value": None,
            "penalty_applied": 0.0,
        }

        return await self._create_belief(
            session=session,
            run_id=run_id,
            agent_id=agent_id,
            belief_type=BeliefType.PREDICTION,
            content=content,
            confidence=1.0,
            topic_tags=["prediction", metric_name, *topic_tags],
            parent_hash=parent_hash,
            evidence_ids=[],
        )

    async def evaluate_prediction(
        self,
        session: AsyncSession,
        prediction_id: str,
        observed_value: float,
        observation_id: str,
    ) -> tuple[bool, float]:
        """evaluates a prediction against reality. Returns (confirmed, penalty).

        No agent discretion here. Math only.
        """
        result = await session.execute(
            select(BeliefRecord).where(BeliefRecord.id == prediction_id)
        )
        prediction = result.scalar_one_or_none()
        if not prediction:
            raise InvariantViolation("prediction_exists", f"prediction {prediction_id} not found")
        if prediction.belief_type != BeliefType.PREDICTION.value:
            raise InvariantViolation(
                "prediction_type", f"belief {prediction_id} is not a prediction"
            )
        if prediction.content.get("status") != PredictionStatus.PENDING.value:
            raise InvariantViolation(
                "prediction_pending",
                f"prediction {prediction_id} already evaluated",
            )

        lower = prediction.content["predicted_lower"]
        upper = prediction.content["predicted_upper"]

        # automatic contradiction detection - no interpretation
        confirmed = lower <= observed_value <= upper

        # penalty calculation - proportional to distance from range
        if confirmed:
            penalty = 0.0
        else:
            if observed_value < lower:
                distance = lower - observed_value
            else:
                distance = observed_value - upper
            # normalize by range width
            range_width = upper - lower if upper > lower else 1.0
            penalty = min(1.0, distance / range_width)

        # update prediction (immutable content is replaced)
        new_content = {
            **prediction.content,
            "status": PredictionStatus.CONFIRMED.value if confirmed else PredictionStatus.CONTRADICTED.value,
            "observed_value": observed_value,
            "observation_id": observation_id,
            "penalty_applied": penalty,
            "evaluated_at": datetime.utcnow().isoformat(),
        }
        prediction.content = new_content
        prediction.confidence = 1.0 if confirmed else 0.0
        prediction.evidence_ids = [observation_id]
        await session.flush()

        return confirmed, penalty

    async def get_predictions_for_source(
        self, session: AsyncSession, run_id: str, source_id: str
    ) -> list[BeliefRecord]:
        """returns all predictions for a reality source."""
        result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.run_id == run_id)
            .where(BeliefRecord.belief_type == BeliefType.PREDICTION.value)
        )
        predictions = list(result.scalars().all())
        return [p for p in predictions if p.content.get("source_id") == source_id]

    async def get_prediction_survival_stats(
        self, session: AsyncSession, source_id: str
    ) -> dict[str, Any]:
        """returns cross-run survival statistics for predictions on a source."""
        result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.belief_type == BeliefType.PREDICTION.value)
        )
        all_predictions = list(result.scalars().all())

        # filter by source
        predictions = [p for p in all_predictions if p.content.get("source_id") == source_id]

        # group by metric_name
        by_metric: dict[str, list[BeliefRecord]] = {}
        for p in predictions:
            metric = p.content.get("metric_name", "unknown")
            by_metric.setdefault(metric, []).append(p)

        stats = {
            "source_id": source_id,
            "total_predictions": len(predictions),
            "metrics": {},
            "survived_all_runs": 0,
            "contradicted_once": 0,
            "contradicted_multiple": 0,
        }

        for metric, preds in by_metric.items():
            confirmed = sum(1 for p in preds if p.content.get("status") == "confirmed")
            contradicted = sum(1 for p in preds if p.content.get("status") == "contradicted")
            pending = sum(1 for p in preds if p.content.get("status") == "pending")

            stats["metrics"][metric] = {
                "total": len(preds),
                "confirmed": confirmed,
                "contradicted": contradicted,
                "pending": pending,
                "survival_rate": confirmed / len(preds) if preds else 0.0,
            }

            if contradicted == 0 and confirmed > 0:
                stats["survived_all_runs"] += 1
            elif contradicted == 1:
                stats["contradicted_once"] += 1
            elif contradicted > 1:
                stats["contradicted_multiple"] += 1

        return stats

    async def get_research_belief_counts(
        self, session: AsyncSession, run_id: str
    ) -> dict[str, int]:
        """returns counts of beliefs by type and class."""
        result = await session.execute(
            select(BeliefRecord.belief_type, func.count(BeliefRecord.id))
            .where(BeliefRecord.run_id == run_id)
            .group_by(BeliefRecord.belief_type)
        )
        counts = {row[0]: row[1] for row in result.fetchall()}

        # count primary observations
        obs_result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.run_id == run_id)
            .where(BeliefRecord.belief_type == BeliefType.OBSERVATION.value)
        )
        observations = list(obs_result.scalars().all())
        primary_count = sum(
            1 for o in observations if o.content.get("metric_class") == "primary"
        )
        secondary_count = len(observations) - primary_count

        # count predictions
        pred_result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.run_id == run_id)
            .where(BeliefRecord.belief_type == BeliefType.PREDICTION.value)
        )
        predictions = list(pred_result.scalars().all())
        pred_confirmed = sum(1 for p in predictions if p.content.get("status") == "confirmed")
        pred_contradicted = sum(1 for p in predictions if p.content.get("status") == "contradicted")
        pred_pending = sum(1 for p in predictions if p.content.get("status") == "pending")

        return {
            "lifecycle": counts.get("lifecycle", 0),
            "observation_primary": primary_count,
            "observation_secondary": secondary_count,
            "observation_total": len(observations),
            "hypothesis": counts.get("hypothesis", 0),
            "prediction_total": len(predictions),
            "prediction_confirmed": pred_confirmed,
            "prediction_contradicted": pred_contradicted,
            "prediction_pending": pred_pending,
            "total_research": len(observations) + counts.get("hypothesis", 0) + len(predictions),
        }

    async def _create_belief(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        belief_type: BeliefType,
        content: dict[str, Any],
        confidence: float,
        topic_tags: list[str],
        parent_hash: str | None,
        evidence_ids: list[str],
    ) -> BeliefRecord:
        """internal belief creation with hashing."""
        # include run_id in hash to allow same content across runs
        hash_input = json.dumps({"run_id": run_id, "content": content}, sort_keys=True)
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        belief_id = generate_id("bel")
        record = BeliefRecord(
            id=belief_id,
            run_id=run_id,
            agent_id=agent_id,
            belief_type=belief_type.value,
            content=content,
            content_hash=content_hash,
            parent_hash=parent_hash,
            confidence=confidence,
            topic_tags=topic_tags,
            evidence_ids=evidence_ids,
            created_at=datetime.utcnow(),
        )
        session.add(record)
        await session.flush()
        return record

    async def _get_run(self, session: AsyncSession, run_id: str) -> RunRecord | None:
        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        return result.scalar_one_or_none()

    async def _get_artifact(self, session: AsyncSession, artifact_id: str) -> ArtifactRecord | None:
        result = await session.execute(
            select(ArtifactRecord).where(ArtifactRecord.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def _count_hypotheses(self, session: AsyncSession, run_id: str) -> int:
        result = await session.execute(
            select(func.count(BeliefRecord.id)).where(
                BeliefRecord.run_id == run_id,
                BeliefRecord.belief_type == BeliefType.HYPOTHESIS.value,
            )
        )
        return result.scalar() or 0

    async def _count_primary_observations(
        self, session: AsyncSession, observation_ids: list[str]
    ) -> int:
        """counts how many of the given observations are primary metrics."""
        if not observation_ids:
            return 0
        result = await session.execute(
            select(BeliefRecord).where(BeliefRecord.id.in_(observation_ids))
        )
        observations = list(result.scalars().all())
        return sum(
            1 for o in observations if o.content.get("metric_class") == "primary"
        )


# singleton
_belief_service: BeliefService | None = None


def get_belief_service() -> BeliefService:
    """returns shared belief service instance."""
    global _belief_service
    if _belief_service is None:
        _belief_service = BeliefService()
    return _belief_service
