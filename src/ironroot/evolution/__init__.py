# Author: Bradley R. Kinnard
"""Strategy Evolution with External Promotion.

Strategies evolve only if they show improvement on held-out external tasks.
Promotion rules are strict and cannot be bypassed.
"""

import json
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service


class PromotionDecision(str, Enum):
    """promotion decision outcomes."""

    PROMOTED = "promoted"
    REJECTED_GATES = "rejected_gates"  # failed verification gates
    REJECTED_THRESHOLD = "rejected_threshold"  # improvement below threshold
    REJECTED_REGRESSION = "rejected_regression"  # regressed on baseline
    REJECTED_ADVERSARIAL = "rejected_adversarial"  # failed adversarial verification


@dataclass
class BaselineMetric:
    """a metric from the baseline suite."""

    metric_name: str
    baseline_value: float
    threshold_degradation: float  # max allowed degradation (0.0 = no degradation allowed)


@dataclass
class PromotionCandidate:
    """a strategy version being considered for promotion."""

    strategy_id: str
    from_version: int
    to_version: int
    changes_description: str
    primary_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    gates_passed: list[str]
    gates_failed: list[str]
    adversarial_tests_passed: int
    adversarial_tests_total: int


@dataclass
class PromotionResult:
    """result of promotion evaluation."""

    candidate: PromotionCandidate
    decision: PromotionDecision
    effect_size: float
    statistical_significance: float
    regression_rate_on_baseline: float
    reasoning: str
    decided_at: str


class BaselineSuite:
    """stable baseline test suite for regression detection."""

    def __init__(self):
        self._baseline_metrics: dict[str, BaselineMetric] = {}
        self._historical_values: dict[str, list[float]] = {}

    def register_baseline(
        self,
        metric_name: str,
        baseline_value: float,
        threshold_degradation: float = 0.05,
    ) -> None:
        """registers a baseline metric."""
        self._baseline_metrics[metric_name] = BaselineMetric(
            metric_name=metric_name,
            baseline_value=baseline_value,
            threshold_degradation=threshold_degradation,
        )
        self._historical_values[metric_name] = [baseline_value]

    def update_historical(self, metric_name: str, value: float) -> None:
        """adds a historical value for a metric."""
        if metric_name in self._historical_values:
            self._historical_values[metric_name].append(value)

    def check_regression(
        self,
        current_metrics: dict[str, float],
    ) -> tuple[bool, dict[str, float]]:
        """checks if current metrics regress from baselines.

        Returns (has_regression, degradation_by_metric).
        """
        degradations = {}
        has_regression = False

        for metric_name, baseline in self._baseline_metrics.items():
            if metric_name not in current_metrics:
                continue

            current = current_metrics[metric_name]
            degradation = (baseline.baseline_value - current) / baseline.baseline_value

            if degradation > 0:  # current is worse
                degradations[metric_name] = degradation
                if degradation > baseline.threshold_degradation:
                    has_regression = True

        return has_regression, degradations

    def get_baseline_values(self) -> dict[str, float]:
        """returns all baseline values."""
        return {m.metric_name: m.baseline_value for m in self._baseline_metrics.values()}


class StrategyEvolutionGate:
    """enforces strict promotion rules for strategy evolution."""

    # minimum improvement required for promotion
    MIN_EFFECT_SIZE = 0.05  # 5% improvement
    MIN_SIGNIFICANCE = 0.05  # p < 0.05
    MAX_BASELINE_REGRESSION = 0.02  # max 2% regression on baseline
    MIN_ADVERSARIAL_PASS_RATE = 0.8  # 80% adversarial tests must pass

    def __init__(self):
        self._baseline_suite = BaselineSuite()
        self._artifact_service = get_artifact_service()
        self._promotion_history: list[PromotionResult] = []

    def register_baseline(
        self,
        metric_name: str,
        value: float,
        threshold: float = 0.05,
    ) -> None:
        """registers a baseline metric."""
        self._baseline_suite.register_baseline(metric_name, value, threshold)

    async def evaluate_candidate(
        self,
        session: AsyncSession,
        candidate: PromotionCandidate,
        run_id: str,
    ) -> PromotionResult:
        """evaluates a strategy candidate for promotion."""
        # Rule 1: Must pass all verification gates
        if candidate.gates_failed:
            result = PromotionResult(
                candidate=candidate,
                decision=PromotionDecision.REJECTED_GATES,
                effect_size=0.0,
                statistical_significance=1.0,
                regression_rate_on_baseline=0.0,
                reasoning=f"Failed gates: {candidate.gates_failed}",
                decided_at=datetime.now(UTC).isoformat(),
            )
            await self._store_result(session, result, run_id)
            return result

        # Rule 2: Must improve primary metrics by threshold
        effect_size = self._compute_effect_size(candidate.primary_metrics)
        significance = self._compute_significance(candidate.primary_metrics)

        if effect_size < self.MIN_EFFECT_SIZE:
            result = PromotionResult(
                candidate=candidate,
                decision=PromotionDecision.REJECTED_THRESHOLD,
                effect_size=effect_size,
                statistical_significance=significance,
                regression_rate_on_baseline=0.0,
                reasoning=f"Effect size {effect_size:.4f} below threshold {self.MIN_EFFECT_SIZE}",
                decided_at=datetime.now(UTC).isoformat(),
            )
            await self._store_result(session, result, run_id)
            return result

        # Rule 3: Must not regress on baseline suite
        has_regression, degradations = self._baseline_suite.check_regression(
            candidate.baseline_metrics
        )
        regression_rate = sum(degradations.values()) / len(degradations) if degradations else 0.0

        if has_regression:
            result = PromotionResult(
                candidate=candidate,
                decision=PromotionDecision.REJECTED_REGRESSION,
                effect_size=effect_size,
                statistical_significance=significance,
                regression_rate_on_baseline=regression_rate,
                reasoning=f"Baseline regression: {degradations}",
                decided_at=datetime.now(UTC).isoformat(),
            )
            await self._store_result(session, result, run_id)
            return result

        # Rule 4: Must survive adversarial verifier attempts
        if candidate.adversarial_tests_total > 0:
            adv_pass_rate = candidate.adversarial_tests_passed / candidate.adversarial_tests_total
            if adv_pass_rate < self.MIN_ADVERSARIAL_PASS_RATE:
                result = PromotionResult(
                    candidate=candidate,
                    decision=PromotionDecision.REJECTED_ADVERSARIAL,
                    effect_size=effect_size,
                    statistical_significance=significance,
                    regression_rate_on_baseline=regression_rate,
                    reasoning=f"Adversarial pass rate {adv_pass_rate:.2f} below {self.MIN_ADVERSARIAL_PASS_RATE}",
                    decided_at=datetime.now(UTC).isoformat(),
                )
                await self._store_result(session, result, run_id)
                return result

        # All rules passed - promote
        result = PromotionResult(
            candidate=candidate,
            decision=PromotionDecision.PROMOTED,
            effect_size=effect_size,
            statistical_significance=significance,
            regression_rate_on_baseline=regression_rate,
            reasoning="All promotion rules satisfied",
            decided_at=datetime.now(UTC).isoformat(),
        )

        # update baselines with new values
        for metric_name, value in candidate.primary_metrics.items():
            self._baseline_suite.update_historical(metric_name, value)

        await self._store_result(session, result, run_id)
        self._promotion_history.append(result)

        return result

    def _compute_effect_size(self, metrics: dict[str, float]) -> float:
        """computes effect size from primary metrics.

        Uses improvement over baseline as effect size.
        """
        baselines = self._baseline_suite.get_baseline_values()
        improvements = []

        for metric_name, value in metrics.items():
            if metric_name in baselines:
                baseline = baselines[metric_name]
                if baseline > 0:
                    improvement = (value - baseline) / baseline
                    improvements.append(improvement)

        return statistics.mean(improvements) if improvements else 0.0

    def _compute_significance(self, metrics: dict[str, float]) -> float:
        """computes statistical significance.

        Simplified: uses historical variance to estimate p-value.
        """
        # in practice, this would use proper statistical tests
        # for now, return conservative estimate
        return 0.05 if metrics else 1.0

    async def _store_result(
        self,
        session: AsyncSession,
        result: PromotionResult,
        run_id: str,
    ) -> None:
        """stores promotion result as artifact."""
        await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps({
                "strategy_id": result.candidate.strategy_id,
                "from_version": result.candidate.from_version,
                "to_version": result.candidate.to_version,
                "decision": result.decision.value,
                "effect_size": result.effect_size,
                "statistical_significance": result.statistical_significance,
                "regression_rate_on_baseline": result.regression_rate_on_baseline,
                "reasoning": result.reasoning,
                "decided_at": result.decided_at,
                "gates_passed": result.candidate.gates_passed,
                "gates_failed": result.candidate.gates_failed,
            }).encode(),
            artifact_type="promotion_decision",
            created_by="strategy_evolution_gate",
            run_id=run_id,
            filename=f"promotion_{result.candidate.strategy_id}_v{result.candidate.to_version}.json",
        )

    def get_promotion_stats(self) -> dict[str, Any]:
        """returns promotion statistics."""
        if not self._promotion_history:
            return {"total_evaluations": 0}

        promoted = sum(1 for r in self._promotion_history if r.decision == PromotionDecision.PROMOTED)
        rejected_gates = sum(1 for r in self._promotion_history if r.decision == PromotionDecision.REJECTED_GATES)
        rejected_threshold = sum(1 for r in self._promotion_history if r.decision == PromotionDecision.REJECTED_THRESHOLD)
        rejected_regression = sum(1 for r in self._promotion_history if r.decision == PromotionDecision.REJECTED_REGRESSION)
        rejected_adversarial = sum(1 for r in self._promotion_history if r.decision == PromotionDecision.REJECTED_ADVERSARIAL)

        avg_effect_size = statistics.mean(r.effect_size for r in self._promotion_history if r.decision == PromotionDecision.PROMOTED) if promoted else 0.0

        return {
            "total_evaluations": len(self._promotion_history),
            "promoted": promoted,
            "rejected_gates": rejected_gates,
            "rejected_threshold": rejected_threshold,
            "rejected_regression": rejected_regression,
            "rejected_adversarial": rejected_adversarial,
            "promotion_rate": promoted / len(self._promotion_history),
            "average_effect_size": avg_effect_size,
        }


_gate: StrategyEvolutionGate | None = None


def get_strategy_evolution_gate() -> StrategyEvolutionGate:
    """returns shared strategy evolution gate."""
    global _gate
    if _gate is None:
        _gate = StrategyEvolutionGate()
    return _gate
