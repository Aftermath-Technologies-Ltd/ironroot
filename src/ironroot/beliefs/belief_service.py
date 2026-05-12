# Author: Bradley R. Kinnard
"""belief service with strict research discipline enforcement."""

import asyncio
import contextlib
import hashlib
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import event, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.errors import ImmutabilityViolation, InvariantViolation
from ironroot.domain.ids import generate_id, hash_content
from ironroot.orchestration.supervisor import RunPhase
from ironroot.storage.models import ArtifactRecord, BeliefRecord, RunRecord


class BeliefType(StrEnum):
    """explicit belief categories."""

    LIFECYCLE = "lifecycle"  # run_start, run_end, phase transitions - NOT research
    OBSERVATION = "observation"  # numeric measurements, zero interpretation
    INFERENCE = "inference"  # derived from observation(s), carries provenance
    HYPOTHESIS = "hypothesis"  # claims about causation, max 1 per run
    PREDICTION = "prediction"  # locked claims about future reality, penalties apply
    VIOLATION = "violation"  # named invariant fired; emitted by the invariants gate
    GATE_RESULT = "gate_result"  # gate decision belief (Phase 2a populates this)


# Belief types that must carry a non-empty `provenance` blob (DB-enforced
# by ck_beliefs_provenance_for_derived plus this list). PRIMARY observations
# and lifecycle bookkeeping legitimately have no upstream belief.
_DERIVED_BELIEF_TYPES = frozenset(
    {
        BeliefType.INFERENCE,
        BeliefType.HYPOTHESIS,
        BeliefType.PREDICTION,
        BeliefType.VIOLATION,
        BeliefType.GATE_RESULT,
    }
)


@dataclass(frozen=True)
class ProvenanceRef:
    """typed reference to upstream source(s) for a derived belief (Phase 2c.3).

    A derived belief carries a `provenance` blob that survives the chain
    digest and is queryable. It records:

    * `belief_ids` — upstream belief ids this belief was derived from
    * `artifact_ids` — upstream artifact ids (e.g., a falsification report)
    * `fixture_ids` — deterministic fixture ids (e.g., a FaultFixture id)
    * `kind`        — short tag for the relation ("derived_from",
                       "fault_observation", "gate_decision", ...)
    * `notes`       — free-text annotation surfaced in audits

    At least one of `belief_ids`, `artifact_ids`, `fixture_ids` must be
    non-empty for the value to be considered a valid provenance — empty
    refs serialize to `{}` and trip the DB CHECK on derived rows.
    """

    kind: str = "derived_from"
    belief_ids: tuple[str, ...] = field(default_factory=tuple)
    artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    fixture_ids: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def is_empty(self) -> bool:
        """True if no upstream id of any kind is recorded."""
        return not (self.belief_ids or self.artifact_ids or self.fixture_ids)

    def to_dict(self) -> dict[str, Any]:
        """canonical dict form persisted in the `provenance` column.

        Returns `{}` if the ref is empty so downstream readers (and the DB
        CHECK constraint) treat it as "no provenance recorded" — matters
        because the constraint compares the JSON text to `'{}'`.
        """
        if self.is_empty():
            return {}
        return {
            "kind": self.kind,
            "belief_ids": list(self.belief_ids),
            "artifact_ids": list(self.artifact_ids),
            "fixture_ids": list(self.fixture_ids),
            "notes": self.notes,
        }


class MetricClass(StrEnum):
    """observation metric classification."""

    PRIMARY = "primary"  # directly measures the capability under test
    SECONDARY = "secondary"  # operational/bookkeeping metrics


class PredictionStatus(StrEnum):
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
    # cross-domain RIL++ metrics
    "cross_domain_survival_rate",
    "distribution_shift_failure_rate",
    "calibration_error",
    # time series metrics
    "future_mean",
    "future_std",
    "future_min",
    "future_max",
    "trend_direction",
    "volatility_ratio",
    # simulator metrics
    "period",
    "max_velocity",
    "decay_rate",
    "energy_loss_ratio",
    "natural_frequency",
    "decay_time",
    "max_displacement",
    "max_height",
    "range",
    "flight_time",
    "landing_angle",
    "hidden_mass",
    "hidden_length",
    "hidden_damping",
    "hidden_spring_constant",
    "hidden_drag_coefficient",
    "hidden_wind_speed",
    "hidden_initial_velocity",
    # delayed outcome metrics
    "p_value",
    "confidence_interval_width",
    "responder_rate",
    "total_return",
    "volatility",
    "max_drawdown",
    "sharpe_ratio",
    "day_7_retention",
    "day_30_retention",
    "churn_rate",
    "ltv_ratio",
    # adversarial metrics
    "shift_magnitude",
    "accuracy_drop",
    "ood_detection_rate",
    "noise_rate",
    "accuracy_on_clean",
    "accuracy_on_noisy",
    "noise_detection_rate",
    "drift_magnitude",
    "adaptation_speed",
    "performance_degradation",
    "detection_delay",
    # tabular dataset metrics
    "mean_target",
    "std_target",
    "class_balance",
    "feature_correlation",
    "mean_sepal_length",
    "std_sepal_length",
    "mean_age",
    "income_ratio",
    "education_distribution",
    # world model metrics (Layer 2)
    "counterfactual_accuracy",
    "intervention_success_rate",
    "causal_consistency_score",
    # capability registry metrics (Layer 3)
    "capability_pass_rate_by_level",
    "sample_efficiency",
    "transfer_gain",
    # strategy evolution metrics (Layer 4)
    "regression_rate_on_baseline_suite",
    # self-healing restoration metrics (Layer 5)
    "time_to_invariant_restoration_ms",
    "repair_success_rate_over_trials",
    "recurrence_rate_over_10_runs",
}


class BeliefService:
    """canonical belief service.

    Owns chain integrity: parent-hash linkage, monotonic `seq` ordering, and
    serialization of appends per chain (`run_id`). Callers MUST NOT supply a
    `parent_hash`; the service derives it under a per-chain Postgres advisory
    lock (`pg_advisory_xact_lock` on a stable hash of `run_id`) plus a
    `SELECT ... ORDER BY seq DESC LIMIT 1 FOR UPDATE` against the beliefs
    table. The `parent_hash=` parameter on the public methods is retained
    only as a deprecated, ignored kwarg so older callers (orchestration
    executor) keep type-checking until Phase 2 deletes the dead state. On
    non-Postgres backends used in tests (SQLite via aiosqlite), the service
    falls back to a process-level `asyncio.Lock` keyed by `(engine, run_id)`;
    the `with_for_update()` clause is a no-op there.
    """

    def __init__(self) -> None:
        # Per (bind_id, run_id) lock shared across sessions.
        self._chain_locks: dict[tuple[int, str], asyncio.Lock] = {}
        self._chain_locks_guard = asyncio.Lock()
        # Re-entry tracking: which (sync_session_id, run_id) pairs are
        # currently holding which lock. Releasing is idempotent and tied
        # to the session's transaction commit/rollback, not the
        # _chain_lock context-manager exit.
        self._session_holders: dict[tuple[int, str], asyncio.Lock] = {}

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
        provenance: ProvenanceRef | None = None,
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
                "observation beliefs only allowed after test/verify, "
                f"current phase: {current_phase.value}",
            )

        # rule 2: must include artifact references
        if not artifact_ids:
            raise InvariantViolation(
                "observation_evidence",
                "observation beliefs must reference at least one artifact",
            )

        # rule 3: primary metrics must use recognized names
        if metric_class == MetricClass.PRIMARY and metric_name not in PRIMARY_METRIC_NAMES:
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
                    "method description must not contain interpretation language",
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
            provenance=provenance,
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
                        f"failed check '{check_name}' must have an explanation of why "
                        "it doesn't invalidate the claim",
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
            provenance=ProvenanceRef(
                kind="hypothesis_from_observations",
                belief_ids=tuple(observation_ids),
                artifact_ids=(verifier_artifact_id,),
            ),
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
        provenance: ProvenanceRef | None = None,
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
            "locked_at": datetime.now(UTC).isoformat(),
            "observed_value": None,
            "penalty_applied": 0.0,
        }

        # Predictions are derived: they reference a `source_id` (reality
        # source). Synthesize a minimal ProvenanceRef from that if the
        # caller didn't supply one explicitly so the DB CHECK passes.
        effective_provenance = provenance or ProvenanceRef(
            kind="prediction_from_source",
            fixture_ids=(source_id,),
            notes=f"prediction on {metric_name} against source {source_id}",
        )

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
            provenance=effective_provenance,
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
            distance = lower - observed_value if observed_value < lower else observed_value - upper
            # normalize by range width
            range_width = upper - lower if upper > lower else 1.0
            penalty = min(1.0, distance / range_width)

        # update prediction (immutable content is replaced)
        status = PredictionStatus.CONFIRMED if confirmed else PredictionStatus.CONTRADICTED
        new_content = {
            **prediction.content,
            "status": status.value,
            "observed_value": observed_value,
            "observation_id": observation_id,
            "penalty_applied": penalty,
            "evaluated_at": datetime.now(UTC).isoformat(),
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
            select(BeliefRecord).where(BeliefRecord.belief_type == BeliefType.PREDICTION.value)
        )
        all_predictions = list(result.scalars().all())

        # filter by source
        predictions = [p for p in all_predictions if p.content.get("source_id") == source_id]

        # group by metric_name
        by_metric: dict[str, list[BeliefRecord]] = {}
        for p in predictions:
            metric = p.content.get("metric_name", "unknown")
            by_metric.setdefault(metric, []).append(p)

        stats: dict[str, Any] = {
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
        primary_count = sum(1 for o in observations if o.content.get("metric_class") == "primary")
        secondary_count = len(observations) - primary_count

        # count predictions
        pred_result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.run_id == run_id)
            .where(BeliefRecord.belief_type == BeliefType.PREDICTION.value)
        )
        predictions = list(pred_result.scalars().all())
        pred_confirmed = sum(1 for p in predictions if p.content.get("status") == "confirmed")
        pred_contradicted = sum(
            1 for p in predictions if p.content.get("status") == "contradicted"
        )
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
        parent_hash: str | None,  # ignored; chain owns parent linkage
        evidence_ids: list[str],
        provenance: ProvenanceRef | None = None,
    ) -> BeliefRecord:
        """internal belief creation.

        The `parent_hash` argument is intentionally ignored: the service
        derives the parent under the per-chain lock to prevent forks
        (see class docstring). The kwarg is retained for one release so
        the orchestration executor keeps type-checking.

        `provenance` is mandatory (non-empty) for derived belief types —
        see `_DERIVED_BELIEF_TYPES`. The DB CHECK constraint
        `ck_beliefs_provenance_for_derived` enforces the same rule and
        catches anyone bypassing this method.
        """
        del parent_hash  # explicitly discard caller-supplied value

        provenance_dict = self._validate_provenance(belief_type, content, provenance)

        # include run_id in hash to allow same content across runs
        hash_input = json.dumps({"run_id": run_id, "content": content}, sort_keys=True)
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        belief_id = generate_id("bel")
        now = datetime.now(UTC)

        async with self._chain_lock(session, run_id):
            prev_seq, prev_hash = await self._get_chain_tip_locked(session, run_id)
            new_seq = prev_seq + 1
            new_parent = prev_hash  # None when chain is empty (seq == 1)

            record = BeliefRecord(
                id=belief_id,
                run_id=run_id,
                seq=new_seq,
                agent_id=agent_id,
                belief_type=belief_type.value,
                content=content,
                content_hash=content_hash,
                parent_hash=new_parent,
                confidence=confidence,
                topic_tags=topic_tags,
                evidence_ids=evidence_ids,
                provenance=provenance_dict,
                created_at=now,
            )
            session.add(record)
            await session.flush()

        # Phase 3.3: publish an advisory event for the UI live stream.
        # Out of the chain lock — the row is already persistent in the
        # transaction; if the caller rolls back, the subscriber will
        # see the event but a refetch of the run's trace will reveal
        # the chain is intact. Events are advisory, the chain is the
        # source of truth.
        await self._publish_belief_event(record)

        return record

    async def _publish_belief_event(self, record: BeliefRecord) -> None:
        """Fires a belief-append event on the configured event bus.

        Publish errors are swallowed by the bus implementation; we
        do not want a broker outage to break belief writes. The bus
        is fetched per call so test overrides via
        ``set_belief_event_bus`` take effect without a service
        restart.
        """
        from ironroot.events import get_belief_event_bus

        try:
            bus = get_belief_event_bus()
        except Exception:
            return
        # The production buses (Redis) swallow their own errors. We
        # add an outer guard so a misbehaving custom bus (test
        # double, third-party shim) can't break the append either.
        try:
            await bus.publish(
                {
                    "type": "belief_append",
                    "belief_id": record.id,
                    "run_id": record.run_id,
                    "seq": record.seq,
                    "agent_id": record.agent_id,
                    "belief_type": record.belief_type,
                    "content_hash": record.content_hash,
                    "parent_hash": record.parent_hash,
                    "topic_tags": list(record.topic_tags or []),
                    "created_at": record.created_at.isoformat(),
                }
            )
        except Exception:
            return

    @staticmethod
    def _validate_provenance(
        belief_type: BeliefType,
        content: dict[str, Any],
        provenance: ProvenanceRef | None,
    ) -> dict[str, Any]:
        """returns the dict to persist in `provenance`; raises if invalid.

        Rules (Phase 2c.3):

        * derived types (`_DERIVED_BELIEF_TYPES`) MUST carry a non-empty
          ProvenanceRef.
        * SECONDARY observations MUST carry a non-empty ProvenanceRef.
        * PRIMARY observations and lifecycle events MAY have empty
          provenance (they sit at the bottom of the inference graph).
        """
        prov_dict = provenance.to_dict() if provenance is not None else {}
        empty = not prov_dict

        if belief_type in _DERIVED_BELIEF_TYPES and empty:
            raise InvariantViolation(
                "belief_provenance_required",
                f"belief_type={belief_type.value} requires a non-empty "
                "provenance ref pointing at source belief(s)/artifact(s)/"
                "fixture(s); got an empty ProvenanceRef",
            )

        if belief_type == BeliefType.OBSERVATION and empty:
            metric_class = content.get("metric_class")
            if metric_class == MetricClass.SECONDARY.value:
                raise InvariantViolation(
                    "belief_provenance_required",
                    "SECONDARY observations require a non-empty provenance "
                    "ref; PRIMARY observations are exempt because they sit "
                    "at the bottom of the inference graph",
                )

        return prov_dict

    @asynccontextmanager
    async def _chain_lock(self, session: AsyncSession, run_id: str) -> AsyncIterator[None]:
        """serializes appends per chain.

        Postgres: `pg_advisory_xact_lock(:key)` taken inside the current
        transaction; auto-released at commit/rollback. The key is a stable
        signed bigint derived from sha256(run_id), so different runs do not
        contend.

        Non-Postgres (SQLite/tests): process-level `asyncio.Lock` keyed by
        `(engine_id, run_id)`. The lock is acquired here but RELEASED on
        the session's `after_commit` / `after_rollback` event — held past
        the context-manager exit so the next session waiting on the same
        chain sees the committed row, matching the Postgres semantics
        exactly. Re-entry within the same session is a no-op so callers
        can append several beliefs to the same chain inside one
        transaction without deadlocking.
        """
        bind = session.bind
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "postgresql":
            digest = hashlib.sha256(run_id.encode()).digest()[:8]
            key = int.from_bytes(digest, "big", signed=True)
            await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
            yield
            return

        sync_session = session.sync_session
        sess_id = id(sync_session)
        bind_key = id(bind)
        chain_key = (bind_key, run_id)
        holder_key = (sess_id, run_id)

        # Re-entry within same session: lock already held, no-op.
        if holder_key in self._session_holders:
            yield
            return

        async with self._chain_locks_guard:
            lock = self._chain_locks.setdefault(chain_key, asyncio.Lock())

        await lock.acquire()
        self._session_holders[holder_key] = lock

        released = False

        def _release(*_args: Any, **_kwargs: Any) -> None:
            nonlocal released
            if released:
                return
            released = True
            self._session_holders.pop(holder_key, None)
            # already released = defensive RuntimeError suppression
            with contextlib.suppress(RuntimeError):
                lock.release()
            # Listeners stay registered on the sync_session for its
            # lifetime; the ``released`` flag short-circuits any
            # subsequent firing. We deliberately do NOT call
            # ``event.remove`` here because the dispatch is currently
            # iterating over the listener deque.

        event.listen(sync_session, "after_commit", _release)
        event.listen(sync_session, "after_rollback", _release)
        event.listen(sync_session, "after_soft_rollback", _release)

        # `after_transaction_end` is the catch-all that fires for any
        # SessionTransaction ending — including the implicit rollback
        # AsyncSession.close() issues when an `async with` block exits
        # without commit. We restrict to the root transaction (no parent)
        # so nested savepoints don't release the chain lock prematurely.
        def _release_if_root(_session: Any, transaction: Any) -> None:
            if getattr(transaction, "parent", None) is None:
                _release()

        event.listen(sync_session, "after_transaction_end", _release_if_root)

        try:
            yield
        except BaseException:
            # If the caller errors out before committing, release immediately
            # so other appenders aren't blocked indefinitely.
            _release()
            raise

    async def _get_chain_tip_locked(
        self, session: AsyncSession, run_id: str
    ) -> tuple[int, str | None]:
        """returns (max_seq, tip_content_hash) under FOR UPDATE.

        Returns (0, None) when the chain is empty. Callers must already hold
        the chain lock (see `_chain_lock`).
        """
        stmt = (
            select(BeliefRecord.seq, BeliefRecord.content_hash)
            .where(BeliefRecord.run_id == run_id)
            .order_by(BeliefRecord.seq.desc())
            .limit(1)
            .with_for_update()
        )
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            return 0, None
        return int(row.seq), str(row.content_hash)

    async def _get_run(self, session: AsyncSession, run_id: str) -> RunRecord | None:
        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        return result.scalar_one_or_none()

    async def _get_artifact(
        self, session: AsyncSession, artifact_id: str
    ) -> ArtifactRecord | None:
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
        return sum(1 for o in observations if o.content.get("metric_class") == "primary")

    # ------------------------------------------------------------------
    # Generic / chain-management API (consolidated from the old
    # cognition.memory.belief_service module — Phase 1.7).
    # ------------------------------------------------------------------

    async def create_belief(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        content: dict[str, object],
        confidence: float,
        evidence_ids: list[str] | None = None,
        topic_tags: list[str] | None = None,
    ) -> BeliefRecord:
        """generic belief append (legacy /beliefs API surface).

        Uses the same locked, seq-based append path as the typed writers,
        so concurrent calls produce a totally-ordered chain.
        """
        # Generic API hashes only the content bytes (the typed API includes
        # run_id in the hash input — see _create_belief). Diverging here is
        # intentional to preserve byte-equivalence with the cross-language
        # @ironroot/core fixtures which use raw-content hashing.
        content_bytes = json.dumps(content, sort_keys=True).encode()
        content_hash = hash_content(content_bytes)
        belief_id = generate_id("bel")
        now = datetime.now(UTC)

        async with self._chain_lock(session, run_id):
            prev_seq, prev_hash = await self._get_chain_tip_locked(session, run_id)
            new_seq = prev_seq + 1
            record = BeliefRecord(
                id=belief_id,
                run_id=run_id,
                seq=new_seq,
                agent_id=agent_id,
                belief_type=BeliefType.LIFECYCLE.value,
                content_hash=content_hash,
                parent_hash=prev_hash,
                content=content,
                confidence=confidence,
                evidence_ids=evidence_ids or [],
                topic_tags=topic_tags or [],
                provenance={},
                created_at=now,
            )
            session.add(record)
            await session.flush()

        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(belief_writes_used=RunRecord.belief_writes_used + 1)
        )
        return record

    async def get_by_id(self, session: AsyncSession, belief_id: str) -> BeliefRecord | None:
        """fetches a belief by id."""
        result = await session.execute(select(BeliefRecord).where(BeliefRecord.id == belief_id))
        return result.scalar_one_or_none()

    async def get_by_hash(self, session: AsyncSession, content_hash: str) -> BeliefRecord | None:
        """fetches a belief by content hash."""
        result = await session.execute(
            select(BeliefRecord).where(BeliefRecord.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def list_beliefs(
        self,
        session: AsyncSession,
        run_id: str | None = None,
        agent_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[BeliefRecord], int]:
        """lists beliefs with filters, ordered by seq within a chain."""
        filters = []
        if run_id:
            filters.append(BeliefRecord.run_id == run_id)
        if agent_id:
            filters.append(BeliefRecord.agent_id == agent_id)

        count_stmt = select(func.count(BeliefRecord.id))
        for f in filters:
            count_stmt = count_stmt.where(f)
        total = (await session.execute(count_stmt)).scalar() or 0

        query = select(BeliefRecord)
        for f in filters:
            query = query.where(f)
        if run_id:
            # chain-order; falls back to created_at when seq is unavailable
            # (only possible during a partial pre-migration state).
            query = query.order_by(BeliefRecord.seq.asc())
        else:
            query = query.order_by(BeliefRecord.created_at.asc())
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all()), int(total)

    async def verify_chain(self, session: AsyncSession, run_id: str) -> bool:
        """verifies the hash chain for a run's beliefs.

        Iterates rows in seq order; checks (a) seq contiguity starting at 1,
        (b) parent_hash linkage, (c) seq=1 iff parent_hash IS NULL,
        (d) generic-API beliefs satisfy their stored content hash. Typed
        beliefs (observation/hypothesis/prediction) hash `{run_id, content}`
        so their stored hash is treated as opaque here; tampering is caught
        by the seq/parent/uniqueness checks plus the Phase 1.5 replay digest.
        """
        result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.run_id == run_id)
            .order_by(BeliefRecord.seq.asc())
        )
        beliefs = list(result.scalars().all())
        if not beliefs:
            return True

        expected_seq = 1
        prev_hash: str | None = None
        for belief in beliefs:
            if belief.seq != expected_seq:
                return False
            if expected_seq == 1:
                if belief.parent_hash is not None:
                    return False
            elif belief.parent_hash != prev_hash:
                return False
            prev_hash = belief.content_hash
            expected_seq += 1
        return True

    async def create_violation_belief(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        invariant_name: str,
        details: str,
        evidence_ids: list[str] | None = None,
        topic_tags: list[str] | None = None,
        provenance: ProvenanceRef | None = None,
    ) -> BeliefRecord:
        """records an invariant violation as a typed belief (Phase 1.6).

        Emitted by the invariants gate whenever a named invariant fires.
        The belief carries the invariant name, a human-readable reason,
        and pointers to whichever evidence beliefs/artifacts surfaced the
        violation. Confidence is 1.0 (the system is reporting a fact,
        not a hypothesis).
        """
        content = {
            "invariant": invariant_name,
            "details": details,
        }
        # Synthesize a non-empty ProvenanceRef. If the caller supplied
        # evidence_ids treat those as the source artifacts; otherwise the
        # invariant name itself is the "fixture" (the named invariant is
        # the upstream check, recorded so audits can trace why this
        # violation belief exists).
        if provenance is not None:
            effective_provenance = provenance
        elif evidence_ids:
            effective_provenance = ProvenanceRef(
                kind="invariant_violation",
                artifact_ids=tuple(evidence_ids),
                notes=f"invariant '{invariant_name}' fired during invariants gate",
            )
        else:
            effective_provenance = ProvenanceRef(
                kind="invariant_violation",
                fixture_ids=(f"invariant:{invariant_name}",),
                notes=f"invariant '{invariant_name}' fired during invariants gate",
            )
        return await self._create_belief(
            session=session,
            run_id=run_id,
            agent_id=agent_id,
            belief_type=BeliefType.VIOLATION,
            content=content,
            confidence=1.0,
            topic_tags=["violation", invariant_name, *(topic_tags or [])],
            parent_hash=None,
            evidence_ids=evidence_ids or [],
            provenance=effective_provenance,
        )

    # ------------------------------------------------------------------
    # Phase 2c.2 — typed write API. The verbs are `append_*` to match the
    # upgrade-plan §2c.2 names and to make the call-site read like the
    # append-only invariant the chain enforces.
    # ------------------------------------------------------------------

    async def append_observation(
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
        provenance: ProvenanceRef | None = None,
    ) -> BeliefRecord:
        """typed alias for `create_observation_belief` (Phase 2c.2).

        Use this at all call sites instead of the older `create_*` form.
        No free-form `MetricClass` strings at the call site — pass the
        `MetricClass` enum.
        """
        return await self.create_observation_belief(
            session=session,
            run_id=run_id,
            agent_id=agent_id,
            metric_name=metric_name,
            value=value,
            unit=unit,
            method=method,
            metric_class=metric_class,
            artifact_ids=artifact_ids,
            topic_tags=topic_tags,
            comparator=comparator,
            provenance=provenance,
        )

    async def append_inference(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        claim: str,
        provenance: ProvenanceRef,
        topic_tags: list[str] | None = None,
        confidence: float = 1.0,
        details: dict[str, Any] | None = None,
    ) -> BeliefRecord:
        """records an inference derived from upstream beliefs/artifacts.

        Inferences are the "we computed X from Y" layer between raw
        observations and full hypotheses. Unlike `create_hypothesis_belief`
        the inference does NOT require 2 observations or a verifier
        artifact — it only requires a non-empty provenance ref. Use it
        when a subsystem (restoration, executor) needs to record a
        derivation without claiming a hypothesis-grade statistical
        finding.

        `provenance` is mandatory and must point at the source(s).
        """
        if provenance.is_empty():
            raise InvariantViolation(
                "inference_provenance_required",
                "append_inference requires a non-empty ProvenanceRef "
                "naming at least one upstream belief, artifact, or fixture",
            )

        content: dict[str, Any] = {"claim": claim}
        if details:
            content["details"] = details

        return await self._create_belief(
            session=session,
            run_id=run_id,
            agent_id=agent_id,
            belief_type=BeliefType.INFERENCE,
            content=content,
            confidence=confidence,
            topic_tags=["inference", *(topic_tags or [])],
            parent_hash=None,
            evidence_ids=list(provenance.belief_ids) + list(provenance.artifact_ids),
            provenance=provenance,
        )

    async def append_gate_result(
        self,
        session: AsyncSession,
        run_id: str,
        gate_name: str,
        passed: bool,
        input_digest: str,
        decision_details: dict[str, Any],
        evidence_belief_ids: list[str] | None = None,
        evidence_artifact_ids: list[str] | None = None,
    ) -> BeliefRecord:
        """records a gate decision as a typed GATE_RESULT belief (Phase 2a.4).

        Inputs:

        * `gate_name`            — short identifier (e.g. "replay",
                                   "falsification", "regression")
        * `passed`               — boolean decision
        * `input_digest`         — sha256 of the canonical inputs the
                                   decision was computed over; pins the
                                   gate's view of the world so replays
                                   can verify it didn't drift
        * `decision_details`     — gate-specific payload (counterexample
                                   evidence id, regression failure list,
                                   live vs baseline digest, etc.)
        * `evidence_belief_ids`  — upstream belief ids the gate consulted
        * `evidence_artifact_ids`— upstream artifact ids the gate consulted

        The gate result becomes part of the chain, so re-running gates
        appends a new belief rather than mutating the old one.
        """
        content: dict[str, Any] = {
            "gate_name": gate_name,
            "passed": passed,
            "input_digest": input_digest,
            "decision": decision_details,
        }

        belief_ids = tuple(evidence_belief_ids or ())
        artifact_ids = tuple(evidence_artifact_ids or ())

        # Even a "no upstream evidence" gate result (degenerate case)
        # carries provenance pointing at the input digest itself, which
        # is enough for the DB CHECK to accept it.
        if not belief_ids and not artifact_ids:
            provenance = ProvenanceRef(
                kind="gate_input_digest",
                fixture_ids=(input_digest,),
                notes=f"gate={gate_name} input_digest={input_digest}",
            )
        else:
            provenance = ProvenanceRef(
                kind="gate_decision",
                belief_ids=belief_ids,
                artifact_ids=artifact_ids,
                notes=f"gate={gate_name} input_digest={input_digest}",
            )

        return await self._create_belief(
            session=session,
            run_id=run_id,
            agent_id=f"gate:{gate_name}",
            belief_type=BeliefType.GATE_RESULT,
            content=content,
            confidence=1.0 if passed else 0.0,
            topic_tags=["gate", gate_name, "passed" if passed else "failed"],
            parent_hash=None,
            evidence_ids=list(belief_ids) + list(artifact_ids),
            provenance=provenance,
        )

    async def update_belief(
        self, session: AsyncSession, belief_id: str, content: dict[str, object]
    ) -> None:
        """beliefs are immutable; always raises."""
        raise ImmutabilityViolation(f"beliefs are append-only, cannot update belief {belief_id}")

    async def delete_belief(self, session: AsyncSession, belief_id: str) -> None:
        """beliefs are immutable; always raises."""
        raise ImmutabilityViolation(f"beliefs are append-only, cannot delete belief {belief_id}")


# singleton
_belief_service: BeliefService | None = None


def get_belief_service() -> BeliefService:
    """returns shared belief service instance."""
    global _belief_service
    if _belief_service is None:
        _belief_service = BeliefService()
    return _belief_service
