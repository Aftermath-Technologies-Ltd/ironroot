# Author: Bradley R. Kinnard
"""Capability Registry - structured curriculum of increasingly hard tasks.

Each capability has:
- definition
- test protocol
- failure modes
- required evidence artifacts
- promotion thresholds
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service


class CapabilityLevel(int, Enum):
    """capability difficulty levels."""

    BASIC = 1  # foundational skills
    INTERMEDIATE = 2  # composition of basics
    ADVANCED = 3  # generalization required
    EXPERT = 4  # novel situations
    MASTER = 5  # adversarial conditions


class CapabilityStatus(str, Enum):
    """capability achievement status."""

    NOT_ATTEMPTED = "not_attempted"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    REGRESSED = "regressed"


@dataclass
class FailureMode:
    """a known failure mode for a capability."""

    mode_id: str
    description: str
    detection_method: str
    severity: str  # "minor", "major", "critical"


@dataclass
class CapabilityDefinition:
    """definition of a capability to be tested."""

    capability_id: str
    name: str
    description: str
    level: CapabilityLevel
    prerequisites: list[str]  # capability_ids that must be passed first
    test_protocol: str
    success_threshold: float  # metric value required to pass
    evidence_artifacts: list[str]  # artifact types required
    failure_modes: list[FailureMode]
    sample_efficiency_target: int  # max samples needed to demonstrate
    transfer_domains: list[str]  # domains where capability should transfer

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "level": self.level.value,
            "prerequisites": self.prerequisites,
            "test_protocol": self.test_protocol,
            "success_threshold": self.success_threshold,
            "evidence_artifacts": self.evidence_artifacts,
            "failure_modes": [
                {"mode_id": fm.mode_id, "description": fm.description, "severity": fm.severity}
                for fm in self.failure_modes
            ],
            "sample_efficiency_target": self.sample_efficiency_target,
            "transfer_domains": self.transfer_domains,
        }


@dataclass
class CapabilityAttempt:
    """a single attempt at demonstrating a capability."""

    attempt_id: str
    capability_id: str
    run_id: str
    domain: str
    samples_used: int
    metric_value: float
    passed: bool
    failure_modes_triggered: list[str]
    artifacts_produced: list[str]
    attempted_at: str


@dataclass
class CapabilityRecord:
    """tracking record for a capability."""

    capability_id: str
    status: CapabilityStatus
    attempts: list[CapabilityAttempt]
    first_passed_at: str | None = None
    passed_in_domains: list[str] = field(default_factory=list)
    total_samples_used: int = 0
    transfer_gain: float = 0.0  # how much faster on new domains


# Initial 10 capabilities - the AGI treadmill starts here
INITIAL_CAPABILITIES = [
    CapabilityDefinition(
        capability_id="cap_001_prediction_locking",
        name="Prediction Locking",
        description="Lock predictions before observing reality, accept penalties for errors",
        level=CapabilityLevel.BASIC,
        prerequisites=[],
        test_protocol="Make predictions, observe reality, compute contradiction rate",
        success_threshold=0.7,  # 70% of predictions must be correct
        evidence_artifacts=["prediction_lock_proof", "contradiction_report"],
        failure_modes=[
            FailureMode("fm_001", "Post-hoc prediction modification", "hash chain verification", "critical"),
            FailureMode("fm_002", "Overly wide prediction intervals", "interval width check", "major"),
        ],
        sample_efficiency_target=100,
        transfer_domains=["tabular", "time_series"],
    ),
    CapabilityDefinition(
        capability_id="cap_002_cross_domain_transfer",
        name="Cross-Domain Transfer",
        description="Apply learned patterns to new domains without retraining",
        level=CapabilityLevel.INTERMEDIATE,
        prerequisites=["cap_001_prediction_locking"],
        test_protocol="Train on domain A, test on domain B without adaptation",
        success_threshold=0.5,  # 50% of training domain performance
        evidence_artifacts=["cross_domain_report", "transfer_evaluation"],
        failure_modes=[
            FailureMode("fm_003", "Domain-specific overfitting", "holdout domain test", "major"),
            FailureMode("fm_004", "Catastrophic forgetting", "source domain retest", "critical"),
        ],
        sample_efficiency_target=200,
        transfer_domains=["tabular", "simulator", "time_series"],
    ),
    CapabilityDefinition(
        capability_id="cap_003_counterfactual_reasoning",
        name="Counterfactual Reasoning",
        description="Answer 'what if' questions about interventions",
        level=CapabilityLevel.INTERMEDIATE,
        prerequisites=["cap_001_prediction_locking"],
        test_protocol="Train causal model, test counterfactual queries",
        success_threshold=0.6,
        evidence_artifacts=["world_model_spec", "world_model_evaluation"],
        failure_modes=[
            FailureMode("fm_005", "Confounding variable ignored", "back-door criterion check", "major"),
            FailureMode("fm_006", "Intervention vs observation confusion", "do-calculus validation", "critical"),
        ],
        sample_efficiency_target=150,
        transfer_domains=["causal_graphs", "simulators"],
    ),
    CapabilityDefinition(
        capability_id="cap_004_distribution_shift_detection",
        name="Distribution Shift Detection",
        description="Detect when input distribution differs from training",
        level=CapabilityLevel.INTERMEDIATE,
        prerequisites=["cap_001_prediction_locking"],
        test_protocol="Train on clean data, detect shifted inputs",
        success_threshold=0.7,
        evidence_artifacts=["shift_detection_report"],
        failure_modes=[
            FailureMode("fm_007", "False positive on in-distribution", "calibration check", "major"),
            FailureMode("fm_008", "Missed covariate shift", "shift injection test", "critical"),
        ],
        sample_efficiency_target=100,
        transfer_domains=["tabular", "adversarial"],
    ),
    CapabilityDefinition(
        capability_id="cap_005_calibrated_uncertainty",
        name="Calibrated Uncertainty",
        description="Confidence should match actual accuracy",
        level=CapabilityLevel.ADVANCED,
        prerequisites=["cap_001_prediction_locking", "cap_004_distribution_shift_detection"],
        test_protocol="Measure calibration error across confidence bins",
        success_threshold=0.1,  # ECE < 0.1
        evidence_artifacts=["calibration_report"],
        failure_modes=[
            FailureMode("fm_009", "Overconfidence", "reliability diagram check", "major"),
            FailureMode("fm_010", "Underconfidence", "sharpness analysis", "minor"),
        ],
        sample_efficiency_target=200,
        transfer_domains=["all"],
    ),
    CapabilityDefinition(
        capability_id="cap_006_planning_with_model",
        name="Planning with World Model",
        description="Use learned model to select actions toward goals",
        level=CapabilityLevel.ADVANCED,
        prerequisites=["cap_003_counterfactual_reasoning"],
        test_protocol="Given goal, plan action sequence using model",
        success_threshold=0.5,
        evidence_artifacts=["planning_trace", "goal_achievement_report"],
        failure_modes=[
            FailureMode("fm_011", "Model exploitation (adversarial actions)", "robustness test", "critical"),
            FailureMode("fm_012", "Myopic planning", "horizon analysis", "major"),
        ],
        sample_efficiency_target=300,
        transfer_domains=["simulators", "interactive"],
    ),
    CapabilityDefinition(
        capability_id="cap_007_self_correction",
        name="Self-Correction",
        description="Detect and fix own errors without external signal",
        level=CapabilityLevel.ADVANCED,
        prerequisites=["cap_005_calibrated_uncertainty"],
        test_protocol="Inject errors, measure detection and correction rate",
        success_threshold=0.6,
        evidence_artifacts=["self_correction_log", "error_injection_report"],
        failure_modes=[
            FailureMode("fm_013", "False positive self-correction", "precision check", "major"),
            FailureMode("fm_014", "Undetected errors", "recall check", "critical"),
        ],
        sample_efficiency_target=150,
        transfer_domains=["all"],
    ),
    CapabilityDefinition(
        capability_id="cap_008_adversarial_robustness",
        name="Adversarial Robustness",
        description="Maintain performance under adversarial attacks",
        level=CapabilityLevel.EXPERT,
        prerequisites=["cap_004_distribution_shift_detection", "cap_005_calibrated_uncertainty"],
        test_protocol="Apply adversarial perturbations, measure degradation",
        success_threshold=0.3,  # max 30% degradation
        evidence_artifacts=["adversarial_evaluation", "robustness_report"],
        failure_modes=[
            FailureMode("fm_015", "Gradient-based attack vulnerability", "PGD attack test", "critical"),
            FailureMode("fm_016", "Distribution shift attack", "poisoning test", "critical"),
        ],
        sample_efficiency_target=500,
        transfer_domains=["adversarial"],
    ),
    CapabilityDefinition(
        capability_id="cap_009_multi_step_reasoning",
        name="Multi-Step Reasoning",
        description="Chain multiple inference steps correctly",
        level=CapabilityLevel.EXPERT,
        prerequisites=["cap_003_counterfactual_reasoning", "cap_006_planning_with_model"],
        test_protocol="Solve problems requiring 3+ inference steps",
        success_threshold=0.4,
        evidence_artifacts=["reasoning_trace", "step_verification_report"],
        failure_modes=[
            FailureMode("fm_017", "Error accumulation", "per-step accuracy analysis", "major"),
            FailureMode("fm_018", "Shortcut exploitation", "ablation test", "critical"),
        ],
        sample_efficiency_target=400,
        transfer_domains=["logical", "causal_graphs"],
    ),
    CapabilityDefinition(
        capability_id="cap_010_continual_learning",
        name="Continual Learning",
        description="Learn new tasks without forgetting old ones",
        level=CapabilityLevel.MASTER,
        prerequisites=["cap_002_cross_domain_transfer", "cap_007_self_correction"],
        test_protocol="Sequential task learning with retention tests",
        success_threshold=0.7,  # retain 70% of original performance
        evidence_artifacts=["continual_learning_report", "retention_matrix"],
        failure_modes=[
            FailureMode("fm_019", "Catastrophic forgetting", "old task retest", "critical"),
            FailureMode("fm_020", "Negative transfer", "new task interference check", "major"),
        ],
        sample_efficiency_target=1000,
        transfer_domains=["all"],
    ),
]


class CapabilityRegistry:
    """registry and tracker for capabilities."""

    def __init__(self):
        self._definitions: dict[str, CapabilityDefinition] = {}
        self._records: dict[str, CapabilityRecord] = {}
        self._artifact_service = get_artifact_service()

        # load initial capabilities
        for cap in INITIAL_CAPABILITIES:
            self._definitions[cap.capability_id] = cap
            self._records[cap.capability_id] = CapabilityRecord(
                capability_id=cap.capability_id,
                status=CapabilityStatus.NOT_ATTEMPTED,
                attempts=[],
            )

    def get_capability(self, capability_id: str) -> CapabilityDefinition | None:
        """returns capability definition."""
        return self._definitions.get(capability_id)

    def get_record(self, capability_id: str) -> CapabilityRecord | None:
        """returns capability tracking record."""
        return self._records.get(capability_id)

    def get_available_capabilities(self) -> list[CapabilityDefinition]:
        """returns capabilities whose prerequisites are met."""
        available = []
        for cap_id, cap in self._definitions.items():
            record = self._records.get(cap_id)
            if record and record.status == CapabilityStatus.PASSED:
                continue  # already passed

            # check prerequisites
            prereqs_met = all(
                self._records.get(prereq, CapabilityRecord(prereq, CapabilityStatus.NOT_ATTEMPTED, [])).status == CapabilityStatus.PASSED
                for prereq in cap.prerequisites
            )

            if prereqs_met:
                available.append(cap)

        return available

    async def record_attempt(
        self,
        session: AsyncSession,
        capability_id: str,
        run_id: str,
        domain: str,
        samples_used: int,
        metric_value: float,
        failure_modes_triggered: list[str],
        artifacts_produced: list[str],
    ) -> CapabilityAttempt:
        """records an attempt at a capability."""
        if capability_id not in self._definitions:
            raise ValueError(f"unknown capability: {capability_id}")

        cap = self._definitions[capability_id]
        record = self._records[capability_id]

        passed = metric_value >= cap.success_threshold

        attempt = CapabilityAttempt(
            attempt_id=generate_id("att"),
            capability_id=capability_id,
            run_id=run_id,
            domain=domain,
            samples_used=samples_used,
            metric_value=metric_value,
            passed=passed,
            failure_modes_triggered=failure_modes_triggered,
            artifacts_produced=artifacts_produced,
            attempted_at=datetime.now(UTC).isoformat(),
        )

        record.attempts.append(attempt)
        record.total_samples_used += samples_used

        if passed:
            if record.status != CapabilityStatus.PASSED:
                record.status = CapabilityStatus.PASSED
                record.first_passed_at = attempt.attempted_at

            if domain not in record.passed_in_domains:
                record.passed_in_domains.append(domain)

                # compute transfer gain
                if len(record.passed_in_domains) > 1:
                    first_attempt_samples = record.attempts[0].samples_used
                    latest_samples = samples_used
                    record.transfer_gain = 1.0 - (latest_samples / first_attempt_samples)
        else:
            if record.status == CapabilityStatus.PASSED:
                record.status = CapabilityStatus.REGRESSED
            elif record.status == CapabilityStatus.NOT_ATTEMPTED:
                record.status = CapabilityStatus.FAILED

        # store attempt artifact
        await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps({
                "attempt_id": attempt.attempt_id,
                "capability_id": capability_id,
                "capability_name": cap.name,
                "run_id": run_id,
                "domain": domain,
                "samples_used": samples_used,
                "metric_value": metric_value,
                "threshold": cap.success_threshold,
                "passed": passed,
                "failure_modes_triggered": failure_modes_triggered,
                "artifacts_produced": artifacts_produced,
            }).encode(),
            artifact_type="capability_attempt",
            created_by="capability_registry",
            run_id=run_id,
            filename=f"capability_attempt_{attempt.attempt_id}.json",
        )

        return attempt

    def get_stats(self) -> dict[str, Any]:
        """returns aggregate capability statistics."""
        by_level = {level: {"total": 0, "passed": 0} for level in CapabilityLevel}

        for cap_id, cap in self._definitions.items():
            record = self._records.get(cap_id)
            by_level[cap.level]["total"] += 1
            if record and record.status == CapabilityStatus.PASSED:
                by_level[cap.level]["passed"] += 1

        total_capabilities = len(self._definitions)
        total_passed = sum(
            1 for r in self._records.values() if r.status == CapabilityStatus.PASSED
        )

        # compute sample efficiency
        total_samples = sum(r.total_samples_used for r in self._records.values())

        # compute average transfer gain
        transfer_gains = [r.transfer_gain for r in self._records.values() if r.transfer_gain > 0]
        avg_transfer_gain = sum(transfer_gains) / len(transfer_gains) if transfer_gains else 0.0

        return {
            "total_capabilities": total_capabilities,
            "passed_capabilities": total_passed,
            "capability_pass_rate_by_level": {
                level.name: stats["passed"] / stats["total"] if stats["total"] else 0.0
                for level, stats in by_level.items()
            },
            "total_samples_used": total_samples,
            "sample_efficiency": total_passed / total_samples if total_samples else 0.0,
            "average_transfer_gain": avg_transfer_gain,
        }


_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    """returns shared capability registry."""
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry
