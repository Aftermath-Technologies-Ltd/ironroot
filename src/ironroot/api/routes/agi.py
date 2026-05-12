# Author: Bradley R. Kinnard
"""API routes for the 5 AGI layers.

Layer 1: Multi-domain RIL++
Layer 2: World Models
Layer 3: Capability Registry
Layer 4: Strategy Evolution
Layer 5: Self-healing Restoration
+ General Intelligence Battery
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.api.deps import get_db_session
from ironroot.domain.ids import generate_id

router = APIRouter(prefix="/agi", tags=["agi"])


# ============================================================================
# LAYER 1: Multi-domain RIL++
# ============================================================================


class CrossDomainRequest(BaseModel):
    """request for cross-domain testing."""

    seed: int = 42
    domains: list[str] = Field(default_factory=lambda: ["tabular_wine", "timeseries_walk"])
    predictions_by_domain: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class CrossDomainResponse(BaseModel):
    """response from cross-domain testing."""

    run_id: str
    domains_tested: int
    domains_survived: int
    cross_domain_survival_rate: float
    distribution_shift_failure_rate: float
    calibration_error: float
    domain_results: list[dict[str, Any]]


@router.post("/cross-domain", response_model=CrossDomainResponse)
async def run_cross_domain_test(
    request: CrossDomainRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CrossDomainResponse:
    """Run prediction tests across multiple reality domains."""
    from ironroot.orchestration.supervisor import RunPhase
    from ironroot.reality.multi_domain import get_multi_domain_executor
    from ironroot.storage.models import RunRecord

    run_id = generate_id("run")

    # create run record
    run = RunRecord(
        id=run_id,
        seed=request.seed,
        config={},
        phase=RunPhase.VERIFY.value,
        status="running",
    )
    session.add(run)
    await session.flush()

    executor = get_multi_domain_executor()
    result = await executor.execute_cross_domain_test(
        session=session,
        run_id=run_id,
        seed=request.seed,
        domains=request.domains,
        predictions_by_domain=request.predictions_by_domain,
    )

    run.status = "completed"
    await session.commit()

    return CrossDomainResponse(
        run_id=result.run_id,
        domains_tested=result.domains_tested,
        domains_survived=result.domains_survived,
        cross_domain_survival_rate=result.cross_domain_survival_rate,
        distribution_shift_failure_rate=result.distribution_shift_failure_rate,
        calibration_error=result.calibration_error,
        domain_results=[
            {
                "domain": r.domain,
                "source_type": r.source_type,
                "survived": r.survived,
                "predictions_made": r.predictions_made,
                "predictions_confirmed": r.predictions_confirmed,
                "total_penalty": r.total_penalty,
            }
            for r in result.domain_results
        ],
    )


@router.get("/domains")
async def list_domains() -> dict[str, list[str]]:
    """List available reality domains."""
    from ironroot.reality.multi_domain import MultiDomainExecutor

    return {"domains": list(MultiDomainExecutor.DOMAIN_SOURCES.keys())}


# ============================================================================
# LAYER 2: World Models
# ============================================================================


class WorldModelRequest(BaseModel):
    """request to create a world model."""

    domain: str
    coefficients: dict[str, float] = Field(default_factory=lambda: {"a_to_b": 1.5, "b_to_c": 2.0})


class CounterfactualQueryRequest(BaseModel):
    """request for counterfactual query."""

    model_id: str
    intervention: dict[str, Any]
    outcome_variable: str
    expected_outcome: Any = None


class WorldModelResponse(BaseModel):
    """response from world model operations."""

    model_id: str
    model_type: str
    domain: str
    training_data_hash: str


@router.post("/world-model", response_model=WorldModelResponse)
async def register_world_model(
    request: WorldModelRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorldModelResponse:
    """Register a new world model."""
    from ironroot.orchestration.supervisor import RunPhase
    from ironroot.storage.models import RunRecord
    from ironroot.world_models import SimpleCausalModel, get_world_model_registry

    run_id = generate_id("run")

    run = RunRecord(id=run_id, seed=42, config={}, phase=RunPhase.VERIFY.value, status="running")
    session.add(run)
    await session.flush()

    registry = get_world_model_registry()
    model = SimpleCausalModel(domain=request.domain, coefficients=request.coefficients)

    training_data = b"sample training data"
    spec = await registry.register_model(session, model, training_data, run_id)

    run.status = "completed"
    await session.commit()

    return WorldModelResponse(
        model_id=spec.model_id,
        model_type=spec.model_type.value,
        domain=spec.domain,
        training_data_hash=spec.training_data_hash,
    )


@router.post("/world-model/counterfactual")
async def query_counterfactual(
    request: CounterfactualQueryRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Query a counterfactual from a world model."""
    from ironroot.world_models import CounterfactualQuery, get_world_model_registry

    registry = get_world_model_registry()
    model = registry.get_model(request.model_id)

    if not model:
        raise HTTPException(status_code=404, detail=f"Model {request.model_id} not found")

    intervention_key = next(iter(request.intervention.keys()))
    intervention_value = next(iter(request.intervention.values()))
    query = CounterfactualQuery(
        query_id=generate_id("qry"),
        condition=f"if {intervention_key} were {intervention_value}",
        intervention=request.intervention,
        outcome_variable=request.outcome_variable,
        expected_outcome=request.expected_outcome,
    )

    result = model.query_counterfactual(query)

    return {
        "query_id": query.query_id,
        "model_id": request.model_id,
        "intervention": request.intervention,
        "outcome_variable": request.outcome_variable,
        "result": result,
        "expected": request.expected_outcome,
        "correct": (
            abs(result - request.expected_outcome) < 0.1 if request.expected_outcome else None
        ),
    }


# ============================================================================
# LAYER 3: Capability Registry
# ============================================================================


@router.get("/capabilities")
async def list_capabilities() -> dict[str, Any]:
    """List all capabilities and their status."""
    from ironroot.capabilities import get_capability_registry

    registry = get_capability_registry()
    capabilities = []

    for cap in registry._definitions.values():
        record = registry.get_record(cap.capability_id)
        capabilities.append(
            {
                "capability_id": cap.capability_id,
                "name": cap.name,
                "level": cap.level.value,
                "status": record.status.value if record else "unknown",
                "prerequisites": cap.prerequisites,
                "success_threshold": cap.success_threshold,
                "passed_in_domains": record.passed_in_domains if record else [],
            }
        )

    return {
        "capabilities": capabilities,
        "stats": registry.get_stats(),
    }


@router.get("/capabilities/available")
async def get_available_capabilities() -> dict[str, list[dict[str, Any]]]:
    """Get capabilities whose prerequisites are met."""
    from ironroot.capabilities import get_capability_registry

    registry = get_capability_registry()
    available = registry.get_available_capabilities()

    return {
        "available": [
            {
                "capability_id": cap.capability_id,
                "name": cap.name,
                "level": cap.level.value,
                "description": cap.description,
            }
            for cap in available
        ]
    }


class CapabilityAttemptRequest(BaseModel):
    """request to record a capability attempt."""

    capability_id: str
    domain: str
    samples_used: int
    metric_value: float
    failure_modes_triggered: list[str] = Field(default_factory=list)
    artifacts_produced: list[str] = Field(default_factory=list)


@router.post("/capabilities/attempt")
async def record_capability_attempt(
    request: CapabilityAttemptRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Record an attempt at a capability."""
    from ironroot.capabilities import get_capability_registry
    from ironroot.orchestration.supervisor import RunPhase
    from ironroot.storage.models import RunRecord

    run_id = generate_id("run")

    run = RunRecord(id=run_id, seed=42, config={}, phase=RunPhase.VERIFY.value, status="running")
    session.add(run)
    await session.flush()

    registry = get_capability_registry()
    attempt = await registry.record_attempt(
        session=session,
        capability_id=request.capability_id,
        run_id=run_id,
        domain=request.domain,
        samples_used=request.samples_used,
        metric_value=request.metric_value,
        failure_modes_triggered=request.failure_modes_triggered,
        artifacts_produced=request.artifacts_produced,
    )

    run.status = "completed"
    await session.commit()

    return {
        "attempt_id": attempt.attempt_id,
        "capability_id": attempt.capability_id,
        "passed": attempt.passed,
        "metric_value": attempt.metric_value,
        "domain": attempt.domain,
    }


# ============================================================================
# LAYER 4: Strategy Evolution
# ============================================================================


class PromotionRequest(BaseModel):
    """request to evaluate a strategy for promotion."""

    strategy_id: str
    from_version: int
    to_version: int
    changes_description: str
    primary_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    gates_passed: list[str] = Field(default_factory=list)
    gates_failed: list[str] = Field(default_factory=list)
    adversarial_tests_passed: int = 0
    adversarial_tests_total: int = 0


@router.post("/evolution/evaluate")
async def evaluate_promotion(
    request: PromotionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Evaluate a strategy candidate for promotion."""
    from ironroot.evolution import PromotionCandidate, get_strategy_evolution_gate
    from ironroot.orchestration.supervisor import RunPhase
    from ironroot.storage.models import RunRecord

    run_id = generate_id("run")

    run = RunRecord(id=run_id, seed=42, config={}, phase=RunPhase.VERIFY.value, status="running")
    session.add(run)
    await session.flush()

    gate = get_strategy_evolution_gate()

    candidate = PromotionCandidate(
        strategy_id=request.strategy_id,
        from_version=request.from_version,
        to_version=request.to_version,
        changes_description=request.changes_description,
        primary_metrics=request.primary_metrics,
        baseline_metrics=request.baseline_metrics,
        gates_passed=request.gates_passed,
        gates_failed=request.gates_failed,
        adversarial_tests_passed=request.adversarial_tests_passed,
        adversarial_tests_total=request.adversarial_tests_total,
    )

    result = await gate.evaluate_candidate(session, candidate, run_id)

    run.status = "completed"
    await session.commit()

    return {
        "strategy_id": result.candidate.strategy_id,
        "decision": result.decision.value,
        "effect_size": result.effect_size,
        "statistical_significance": result.statistical_significance,
        "regression_rate_on_baseline": result.regression_rate_on_baseline,
        "reasoning": result.reasoning,
    }


@router.post("/evolution/baseline")
async def register_baseline(
    metric_name: str,
    value: float,
    threshold: float = 0.05,
) -> dict[str, str]:
    """Register a baseline metric for regression detection."""
    from ironroot.evolution import get_strategy_evolution_gate

    gate = get_strategy_evolution_gate()
    gate.register_baseline(metric_name, value, threshold)

    return {"status": "registered", "metric": metric_name}


@router.get("/evolution/stats")
async def get_evolution_stats() -> dict[str, Any]:
    """Get strategy evolution statistics."""
    from ironroot.evolution import get_strategy_evolution_gate

    gate = get_strategy_evolution_gate()
    return gate.get_promotion_stats()


# ============================================================================
# LAYER 5: Self-healing Restoration
# ============================================================================


class ViolationRequest(BaseModel):
    """request to report an invariant violation."""

    invariant_type: str
    description: str
    component: str
    evidence: dict[str, Any] = Field(default_factory=dict)


@router.post("/healing/violation")
async def report_violation(
    request: ViolationRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Report an invariant violation."""
    from ironroot.healing.restoration import InvariantType, get_self_healing_restorer
    from ironroot.orchestration.supervisor import RunPhase
    from ironroot.storage.models import RunRecord

    run_id = generate_id("run")

    run = RunRecord(id=run_id, seed=42, config={}, phase=RunPhase.VERIFY.value, status="running")
    session.add(run)
    await session.flush()

    restorer = get_self_healing_restorer()

    try:
        inv_type = InvariantType(request.invariant_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid invariant type: {request.invariant_type}",
        ) from exc

    violation = restorer.register_invariant_violation(
        invariant_type=inv_type,
        description=request.description,
        run_id=run_id,
        component=request.component,
        evidence=request.evidence,
    )

    run.status = "completed"
    await session.commit()

    return {
        "violation_id": violation.violation_id,
        "invariant_type": violation.invariant_type.value,
        "detected_at": violation.detected_at,
    }


@router.post("/healing/restore/{violation_id}")
async def restore_correctness(
    violation_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Attempt to restore correctness after a violation."""
    from ironroot.healing.restoration import get_self_healing_restorer
    from ironroot.orchestration.supervisor import RunPhase
    from ironroot.storage.models import RunRecord

    run_id = generate_id("run")

    run = RunRecord(id=run_id, seed=42, config={}, phase=RunPhase.VERIFY.value, status="running")
    session.add(run)
    await session.flush()

    restorer = get_self_healing_restorer()

    # Phase 2b.1: restoration now requires a FaultFixture for
    # determinism (recurrence is measured by replaying the fixture, not
    # by sampling RNG). Callers using this API endpoint don't carry a
    # FaultFixture, so we construct a no-op fixture whose revert /
    # replay both do nothing. The restorer still runs the real gate
    # checks against the live chain — which is the operator's actual
    # question: "are invariants intact and is the replay digest
    # stable?". For deterministic fault-injection campaigns, use the
    # FaultFixture API directly rather than this endpoint.
    from ironroot.verification.fault_fixtures import FaultFixture, ObservedFaultEffect

    class _NoopFixture(FaultFixture):
        async def apply(self, session: AsyncSession, run_id: str) -> ObservedFaultEffect:
            return ObservedFaultEffect(fixture_id=self.fixture_id)

        async def revert(self, session: AsyncSession, run_id: str) -> None:
            return None

    noop_fixture = _NoopFixture(
        fixture_id=f"noop:{violation_id}",
        description="no-op fixture for legacy /restore endpoint",
    )

    try:
        report = await restorer.restore_correctness(session, violation_id, run_id, noop_fixture)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    run.status = "completed"
    await session.commit()

    return {
        "violation_id": report.violation.violation_id,
        "final_status": report.final_status.value,
        "attempts": len(report.attempts),
        "time_to_invariant_restoration_ms": report.time_to_invariant_restoration_ms,
        "repair_success_rate_over_trials": report.repair_success_rate_over_trials,
        "recurrence_rate_over_10_runs": report.recurrence_rate,
        "new_regression_tests": report.new_regression_tests,
    }


@router.get("/healing/stats")
async def get_healing_stats() -> dict[str, Any]:
    """Get self-healing restoration statistics."""
    from ironroot.healing.restoration import get_self_healing_restorer

    restorer = get_self_healing_restorer()
    return restorer.get_restoration_stats()


# ============================================================================
# GENERAL INTELLIGENCE BATTERY
# ============================================================================


class BatteryRequest(BaseModel):
    """request to run the GI battery."""

    strategy_id: str
    seed: int = 42


@router.post("/battery/evaluate")
async def run_battery(
    request: BatteryRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Run the General Intelligence Battery against a strategy."""
    from ironroot.battery import get_gi_battery
    from ironroot.orchestration.supervisor import RunPhase
    from ironroot.storage.models import RunRecord

    run_id = generate_id("run")

    run = RunRecord(id=run_id, seed=42, config={}, phase=RunPhase.VERIFY.value, status="running")
    session.add(run)
    await session.flush()

    battery = get_gi_battery(request.seed)

    # simple predictor for demo - in practice this would invoke the strategy
    def dummy_predictor(task: Any) -> Any:
        # return baseline predictions
        if "sequence" in task.input_data:
            seq = task.input_data["sequence"]
            return seq[-1] + (seq[-1] - seq[-2]) if len(seq) > 1 else seq[-1]
        elif "question" in task.input_data:
            return 42  # placeholder
        elif "goal" in task.input_data:
            goal = task.input_data["goal"]
            return abs(goal[0]) + abs(goal[1])
        elif "samples" in task.input_data:
            samples = task.input_data["samples"]
            return sum(samples) / len(samples)
        return 0

    result = await battery.evaluate_strategy(
        session=session,
        strategy_id=request.strategy_id,
        run_id=run_id,
        predictor=dummy_predictor,
    )

    run.status = "completed"
    await session.commit()

    return {
        "battery_id": result.battery_id,
        "strategy_id": result.strategy_id,
        "tasks_run": result.tasks_run,
        "tasks_correct": result.tasks_correct,
        "overall_score": result.overall_score,
        "score_by_domain": result.score_by_domain,
        "score_by_difficulty": result.score_by_difficulty,
        "calibration_error": result.calibration_error,
        "meets_promotion_threshold": battery.meets_promotion_threshold(result),
    }


@router.get("/battery/threshold")
async def get_battery_threshold() -> dict[str, float]:
    """Get the promotion threshold for the GI battery."""
    from ironroot.battery import get_gi_battery

    battery = get_gi_battery()
    return {"promotion_threshold": battery.get_promotion_threshold()}
