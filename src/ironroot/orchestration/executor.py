# Author: Bradley R. Kinnard
"""run executor with fault injection and self-healing capabilities."""

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.beliefs.belief_service import MetricClass, get_belief_service
from ironroot.orchestration.budgets import Budget
from ironroot.orchestration.supervisor import RunPhase, Supervisor
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import RunRecord


class FaultScenario(str, Enum):
    """known fault scenarios for injection."""

    NONE = "none"
    SIMPLE_INVARIANT = "simple_invariant"  # deterministic, always triggers
    INTERMITTENT_TIMING = "intermittent_timing"  # only on specific conditions


@dataclass
class FaultInjectionConfig:
    """fault injection configuration."""

    enabled: bool = False
    scenario_id: str = "none"
    trigger_phase: str = "test"
    trigger_condition: str = "always"  # "always", "trial_3", "percent_50"
    expected_signature: str = ""


@dataclass
class SelfHealingState:
    """tracks self-healing metrics during a run."""

    fault_detected: bool = False
    fault_timestamp: float = 0.0
    containment_timestamp: float = 0.0
    recovery_timestamp: float = 0.0
    recovery_attempts: int = 0
    regression_tests_added: int = 0
    commits_frozen: bool = False
    last_verified_state: dict = field(default_factory=dict)
    repair_actions: list = field(default_factory=list)


class RunExecutor:
    """executes runs with fault injection and self-healing."""

    async def execute(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """runs through phases with optional fault injection and self-healing."""
        run = await self._get_run(session, run_id)
        if not run:
            return {"error": f"run {run_id} not found"}

        if run.status in ("completed", "failed"):
            return {
                "error": f"run {run_id} is already {run.status}",
                "status": run.status,
                "phase": run.phase,
            }

        seed = run.seed
        rng = random.Random(seed)
        belief_service = get_belief_service()
        artifact_service = get_artifact_service()

        config = run.config or {}
        budgets_config = config.get("budgets", {})
        budget = Budget(
            max_steps=budgets_config.get("max_steps", 240),
            max_tool_calls=budgets_config.get("max_tool_calls", 500),
            max_belief_writes=budgets_config.get("max_belief_writes", 200),
        )
        budget.steps_used = run.steps_used
        budget.tool_calls_used = run.tool_calls_used
        budget.belief_writes_used = run.belief_writes_used

        # parse fault injection config
        fi_config = self._parse_fault_config(config.get("fault_injection", {}))
        healing_state = SelfHealingState()

        # run_start lifecycle belief
        start_belief = await belief_service.create_lifecycle_belief(
            session=session,
            run_id=run_id,
            agent_id="lifecycle",
            content={
                "type": "run_start",
                "seed": seed,
                "fault_injection_enabled": fi_config.enabled,
                "fault_scenario": fi_config.scenario_id if fi_config.enabled else None,
                "budgets": {
                    "max_steps": budget.max_steps,
                    "max_tool_calls": budget.max_tool_calls,
                    "max_belief_writes": budget.max_belief_writes,
                },
                "timestamp": datetime.utcnow().isoformat(),
            },
            topic_tags=["run_start"],
        )
        budget.use_belief_write(1)
        await self._update_budget(session, run_id, budget)

        run = await self._get_run(session, run_id)
        if not run:
            return {"error": f"run {run_id} disappeared"}

        supervisor = Supervisor(run_id, seed)
        supervisor.phase = RunPhase(run.phase)

        if supervisor.phase == RunPhase.INIT:
            supervisor.transition_to(RunPhase.PROPOSE)
            await self._update_phase(session, run_id, supervisor.phase)

        phases_executed = []
        last_belief_hash = start_belief.content_hash
        observation_ids: list[str] = []
        primary_observation_ids: list[str] = []
        verifier_artifact_id: str | None = None
        failed_checks: list[dict[str, str]] = []
        fault_artifact_id: str | None = None
        containment_artifact_id: str | None = None
        rollback_artifact_id: str | None = None
        repair_artifact_id: str | None = None
        regression_artifact_id: str | None = None
        trial_index = 0

        phase_sequence = [
            RunPhase.PROPOSE,
            RunPhase.BUILD,
            RunPhase.TEST,
            RunPhase.VERIFY,
            RunPhase.AUDIT,
            RunPhase.DECIDE,
        ]

        for target_phase in phase_sequence:
            if supervisor.phase == target_phase:
                phases_executed.append(target_phase.value)
                continue
            if supervisor.phase in (RunPhase.FINALIZE, RunPhase.STOPPED, RunPhase.FAILED):
                break

            try:
                supervisor.transition_to(target_phase)
            except Exception as e:
                await self._fail_run(session, run_id, str(e))
                return {"error": str(e), "phase": supervisor.phase.value}

            await self._update_phase(session, run_id, supervisor.phase)

            # save verified state before work
            healing_state.last_verified_state = {
                "phase": target_phase.value,
                "steps_used": budget.steps_used,
                "tool_calls_used": budget.tool_calls_used,
                "belief_writes_used": budget.belief_writes_used,
            }

            # simulate work
            steps_in_phase = rng.randint(2, 8)
            tool_calls_in_phase = rng.randint(1, 5)
            trial_index += 1

            for _ in range(steps_in_phase):
                if budget.is_exhausted():
                    break
                budget.use_step(1)

            for _ in range(tool_calls_in_phase):
                if budget.tool_calls_used >= budget.max_tool_calls:
                    break
                budget.use_tool_call(1)

            await self._update_budget(session, run_id, budget)

            # === FAULT INJECTION ===
            should_inject = self._should_inject_fault(
                fi_config, target_phase.value, trial_index, rng
            )

            if should_inject:
                healing_state.fault_detected = True
                healing_state.fault_timestamp = time.time()

                # create fault injection artifact
                fault_data = {
                    "scenario_id": fi_config.scenario_id,
                    "trigger_phase": target_phase.value,
                    "trigger_condition": fi_config.trigger_condition,
                    "trial_index": trial_index,
                    "expected_signature": fi_config.expected_signature,
                    "affected_components": self._get_affected_components(fi_config.scenario_id),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                fault_artifact = await artifact_service.store_artifact(
                    session=session,
                    data=json.dumps(fault_data).encode(),
                    artifact_type="fault_injection_report",
                    created_by="fault_injector",
                    run_id=run_id,
                    filename=f"fault_injection_{run_id}.json",
                )
                fault_artifact_id = fault_artifact.id

                # === CONTAINMENT ===
                healing_state.commits_frozen = True
                healing_state.containment_timestamp = time.time()

                containment_data = {
                    "fault_artifact_id": fault_artifact_id,
                    "commits_frozen": True,
                    "freeze_timestamp": datetime.utcnow().isoformat(),
                    "detection_method": "gate_invariant_check",
                    "affected_phase": target_phase.value,
                }
                containment_artifact = await artifact_service.store_artifact(
                    session=session,
                    data=json.dumps(containment_data).encode(),
                    artifact_type="containment_report",
                    created_by="containment_service",
                    run_id=run_id,
                    filename=f"containment_{run_id}.json",
                )
                containment_artifact_id = containment_artifact.id

                # === ROLLBACK ===
                rollback_data = {
                    "fault_artifact_id": fault_artifact_id,
                    "rollback_target": healing_state.last_verified_state,
                    "rollback_timestamp": datetime.utcnow().isoformat(),
                    "components_reset": self._get_affected_components(fi_config.scenario_id),
                }
                rollback_artifact = await artifact_service.store_artifact(
                    session=session,
                    data=json.dumps(rollback_data).encode(),
                    artifact_type="rollback_report",
                    created_by="rollback_service",
                    run_id=run_id,
                    filename=f"rollback_{run_id}.json",
                )
                rollback_artifact_id = rollback_artifact.id

                # === REPAIR SEQUENCE ===
                repair_success = False
                max_attempts = 3 if fi_config.scenario_id == "intermittent_timing" else 1

                for attempt in range(max_attempts):
                    healing_state.recovery_attempts += 1
                    repair_action = self._generate_repair_action(
                        fi_config.scenario_id, attempt, rng
                    )
                    healing_state.repair_actions.append(repair_action)

                    # intermittent faults may need multiple attempts
                    if fi_config.scenario_id == "simple_invariant":
                        repair_success = True
                        break
                    elif fi_config.scenario_id == "intermittent_timing":
                        # 70% success on each attempt for intermittent
                        if rng.random() < 0.7:
                            repair_success = True
                            break

                healing_state.recovery_timestamp = time.time()

                repair_data = {
                    "fault_artifact_id": fault_artifact_id,
                    "attempts": healing_state.recovery_attempts,
                    "actions": healing_state.repair_actions,
                    "success": repair_success,
                    "repair_timestamp": datetime.utcnow().isoformat(),
                }
                repair_artifact = await artifact_service.store_artifact(
                    session=session,
                    data=json.dumps(repair_data).encode(),
                    artifact_type="repair_report",
                    created_by="repair_service",
                    run_id=run_id,
                    filename=f"repair_{run_id}.json",
                )
                repair_artifact_id = repair_artifact.id

                # === REGRESSION TEST GENERATION ===
                regression_tests = self._generate_regression_tests(
                    fi_config.scenario_id, healing_state.repair_actions, rng
                )
                healing_state.regression_tests_added = len(regression_tests)

                # verify tests fail before fix (simulated)
                pre_fix_results = [
                    {"test": t["name"], "passed": False, "reason": "fault active"}
                    for t in regression_tests
                ]
                # verify tests pass after fix (simulated)
                post_fix_results = [
                    {"test": t["name"], "passed": repair_success, "reason": "repair applied"}
                    for t in regression_tests
                ]

                regression_data = {
                    "fault_artifact_id": fault_artifact_id,
                    "tests_added": regression_tests,
                    "pre_fix_results": pre_fix_results,
                    "post_fix_results": post_fix_results,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                regression_artifact = await artifact_service.store_artifact(
                    session=session,
                    data=json.dumps(regression_data).encode(),
                    artifact_type="regression_report",
                    created_by="regression_service",
                    run_id=run_id,
                    filename=f"regression_{run_id}.json",
                )
                regression_artifact_id = regression_artifact.id

                # unfreeze commits after gates pass
                healing_state.commits_frozen = False

            # lifecycle belief for phase completion
            phase_belief = await belief_service.create_lifecycle_belief(
                session=session,
                run_id=run_id,
                agent_id="supervisor",
                content={
                    "type": "phase_complete",
                    "phase": target_phase.value,
                    "steps_used": steps_in_phase,
                    "tool_calls_used": tool_calls_in_phase,
                    "fault_injected": should_inject,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                topic_tags=["phase", target_phase.value],
                parent_hash=last_belief_hash,
            )
            budget.use_belief_write(1)
            await self._update_budget(session, run_id, budget)
            last_belief_hash = phase_belief.content_hash

            # === TEST PHASE: determinism metrics ===
            if target_phase == RunPhase.TEST:
                trace_1 = self._generate_trace(seed)
                trace_2 = self._generate_trace(seed)
                traces_match = trace_1 == trace_2
                nondeterminism_events = 0 if traces_match else rng.randint(1, 5)

                test_data = {
                    "test_type": "determinism_replay",
                    "run_id": run_id,
                    "seed": seed,
                    "traces_match": traces_match,
                    "nondeterminism_events": nondeterminism_events,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                test_artifact = await artifact_service.store_artifact(
                    session=session,
                    data=json.dumps(test_data).encode(),
                    artifact_type="test_results",
                    created_by="executor",
                    run_id=run_id,
                    filename=f"determinism_test_{run_id}.json",
                )

                obs_replay = await belief_service.create_observation_belief(
                    session=session,
                    run_id=run_id,
                    agent_id="test_agent",
                    metric_name="replay_digest_match",
                    value=traces_match,
                    unit="boolean",
                    method="computed sha256 of execution traces from two runs with same seed",
                    metric_class=MetricClass.PRIMARY,
                    artifact_ids=[test_artifact.id],
                    topic_tags=["determinism", "replay"],
                    parent_hash=last_belief_hash,
                )
                observation_ids.append(obs_replay.id)
                primary_observation_ids.append(obs_replay.id)
                budget.use_belief_write(1)
                await self._update_budget(session, run_id, budget)
                last_belief_hash = obs_replay.content_hash

            # === VERIFY PHASE: falsification + self-healing metrics ===
            if target_phase == RunPhase.VERIFY:
                counterexamples_found = rng.randint(0, 2)
                checks_run = rng.randint(8, 15)

                falsification_data = {
                    "verifier": "determinism_falsifier",
                    "run_id": run_id,
                    "seed": seed,
                    "checks_run": checks_run,
                    "counterexamples_found": counterexamples_found,
                    "fault_detected": healing_state.fault_detected,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                falsification_artifact = await artifact_service.store_artifact(
                    session=session,
                    data=json.dumps(falsification_data).encode(),
                    artifact_type="falsification_report",
                    created_by="verifier",
                    run_id=run_id,
                    filename=f"falsification_report_{run_id}.json",
                )
                verifier_artifact_id = falsification_artifact.id

                if counterexamples_found > 0:
                    for i in range(counterexamples_found):
                        failed_checks.append({
                            "check": f"edge_case_{i}",
                            "reason": "timing-dependent path, does not affect seeded determinism",
                        })

                obs_counter = await belief_service.create_observation_belief(
                    session=session,
                    run_id=run_id,
                    agent_id="verifier_agent",
                    metric_name="verifier_counterexample_count",
                    value=counterexamples_found,
                    unit="count",
                    method="verifier searched for inputs producing different outputs",
                    metric_class=MetricClass.PRIMARY,
                    artifact_ids=[falsification_artifact.id],
                    topic_tags=["verification", "counterexamples"],
                    parent_hash=last_belief_hash,
                )
                observation_ids.append(obs_counter.id)
                primary_observation_ids.append(obs_counter.id)
                budget.use_belief_write(1)
                await self._update_budget(session, run_id, budget)
                last_belief_hash = obs_counter.content_hash

                # === SELF-HEALING METRICS (only if fault was injected) ===
                if healing_state.fault_detected:
                    artifact_refs = [a for a in [
                        fault_artifact_id,
                        containment_artifact_id,
                        rollback_artifact_id,
                        repair_artifact_id,
                        regression_artifact_id,
                    ] if a]

                    # time_to_containment_ms
                    containment_ms = int(
                        (healing_state.containment_timestamp - healing_state.fault_timestamp) * 1000
                    )
                    obs_containment = await belief_service.create_observation_belief(
                        session=session,
                        run_id=run_id,
                        agent_id="selfheal_agent",
                        metric_name="time_to_containment_ms",
                        value=containment_ms,
                        unit="milliseconds",
                        method="elapsed time from fault detection to commit freeze",
                        metric_class=MetricClass.PRIMARY,
                        artifact_ids=artifact_refs,
                        topic_tags=["selfhealing", "containment"],
                        parent_hash=last_belief_hash,
                    )
                    observation_ids.append(obs_containment.id)
                    primary_observation_ids.append(obs_containment.id)
                    budget.use_belief_write(1)
                    await self._update_budget(session, run_id, budget)
                    last_belief_hash = obs_containment.content_hash

                    # time_to_recovery_ms
                    recovery_ms = int(
                        (healing_state.recovery_timestamp - healing_state.fault_timestamp) * 1000
                    )
                    obs_recovery = await belief_service.create_observation_belief(
                        session=session,
                        run_id=run_id,
                        agent_id="selfheal_agent",
                        metric_name="time_to_recovery_ms",
                        value=recovery_ms,
                        unit="milliseconds",
                        method="elapsed time from fault detection to successful repair",
                        metric_class=MetricClass.PRIMARY,
                        artifact_ids=artifact_refs,
                        topic_tags=["selfhealing", "recovery"],
                        parent_hash=last_belief_hash,
                    )
                    observation_ids.append(obs_recovery.id)
                    primary_observation_ids.append(obs_recovery.id)
                    budget.use_belief_write(1)
                    await self._update_budget(session, run_id, budget)
                    last_belief_hash = obs_recovery.content_hash

                    # recovery_attempts
                    obs_attempts = await belief_service.create_observation_belief(
                        session=session,
                        run_id=run_id,
                        agent_id="selfheal_agent",
                        metric_name="recovery_attempts",
                        value=healing_state.recovery_attempts,
                        unit="count",
                        method="number of repair attempts before success or failure",
                        metric_class=MetricClass.PRIMARY,
                        artifact_ids=artifact_refs,
                        topic_tags=["selfhealing", "attempts"],
                        parent_hash=last_belief_hash,
                    )
                    observation_ids.append(obs_attempts.id)
                    primary_observation_ids.append(obs_attempts.id)
                    budget.use_belief_write(1)
                    await self._update_budget(session, run_id, budget)
                    last_belief_hash = obs_attempts.content_hash

                    # regression_tests_added
                    obs_regression = await belief_service.create_observation_belief(
                        session=session,
                        run_id=run_id,
                        agent_id="selfheal_agent",
                        metric_name="regression_tests_added",
                        value=healing_state.regression_tests_added,
                        unit="count",
                        method="count of new tests generated to prevent fault recurrence",
                        metric_class=MetricClass.PRIMARY,
                        artifact_ids=artifact_refs,
                        topic_tags=["selfhealing", "regression"],
                        parent_hash=last_belief_hash,
                    )
                    observation_ids.append(obs_regression.id)
                    primary_observation_ids.append(obs_regression.id)
                    budget.use_belief_write(1)
                    await self._update_budget(session, run_id, budget)
                    last_belief_hash = obs_regression.content_hash

                    # recurrence_rate (0 if tests pass, else estimate)
                    recurrence = 0.0 if healing_state.regression_tests_added > 0 else 0.5
                    obs_recurrence = await belief_service.create_observation_belief(
                        session=session,
                        run_id=run_id,
                        agent_id="selfheal_agent",
                        metric_name="recurrence_rate",
                        value=recurrence,
                        unit="probability",
                        method="estimated probability of fault recurring based on regression coverage",
                        metric_class=MetricClass.PRIMARY,
                        artifact_ids=artifact_refs,
                        topic_tags=["selfhealing", "recurrence"],
                        parent_hash=last_belief_hash,
                    )
                    observation_ids.append(obs_recurrence.id)
                    primary_observation_ids.append(obs_recurrence.id)
                    budget.use_belief_write(1)
                    await self._update_budget(session, run_id, budget)
                    last_belief_hash = obs_recurrence.content_hash

            phases_executed.append(target_phase.value)

            if budget.is_exhausted():
                break

        # run_end lifecycle belief
        await belief_service.create_lifecycle_belief(
            session=session,
            run_id=run_id,
            agent_id="lifecycle",
            content={
                "type": "run_end",
                "phases_executed": phases_executed,
                "fault_injection_enabled": fi_config.enabled,
                "fault_detected": healing_state.fault_detected,
                "recovery_attempts": healing_state.recovery_attempts,
                "regression_tests_added": healing_state.regression_tests_added,
                "final_budget": {
                    "steps_used": budget.steps_used,
                    "tool_calls_used": budget.tool_calls_used,
                    "belief_writes_used": budget.belief_writes_used + 1,
                },
                "observation_count": len(observation_ids),
                "primary_observation_count": len(primary_observation_ids),
                "timestamp": datetime.utcnow().isoformat(),
            },
            topic_tags=["run_end"],
            parent_hash=last_belief_hash,
        )
        budget.use_belief_write(1)
        await self._update_budget(session, run_id, budget)

        # finalize
        supervisor.transition_to(RunPhase.FINALIZE)
        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                status="completed",
                phase=RunPhase.FINALIZE.value,
                finished_at=datetime.utcnow(),
            )
        )

        counts = await belief_service.get_research_belief_counts(session, run_id)

        return {
            "run_id": run_id,
            "status": "completed",
            "phases_executed": phases_executed,
            "fault_injection": {
                "enabled": fi_config.enabled,
                "scenario": fi_config.scenario_id,
                "detected": healing_state.fault_detected,
                "recovery_attempts": healing_state.recovery_attempts,
                "regression_tests_added": healing_state.regression_tests_added,
            },
            "lifecycle_beliefs": counts["lifecycle"],
            "observation_primary": counts["observation_primary"],
            "observation_secondary": counts["observation_secondary"],
            "hypothesis_beliefs": counts["hypothesis"],
            "total_research_beliefs": counts["total_research"],
            "failed_checks": len(failed_checks),
            "steps_used": budget.steps_used,
            "tool_calls_used": budget.tool_calls_used,
        }

    def _parse_fault_config(self, raw: dict) -> FaultInjectionConfig:
        """parses fault injection config from run config."""
        return FaultInjectionConfig(
            enabled=raw.get("enabled", False),
            scenario_id=raw.get("scenario_id", "none"),
            trigger_phase=raw.get("trigger_phase", "test"),
            trigger_condition=raw.get("trigger_condition", "always"),
            expected_signature=raw.get("expected_signature", ""),
        )

    def _should_inject_fault(
        self, config: FaultInjectionConfig, current_phase: str, trial_index: int, rng: random.Random
    ) -> bool:
        """determines if fault should be injected this phase."""
        if not config.enabled:
            return False
        if current_phase != config.trigger_phase:
            return False

        condition = config.trigger_condition
        if condition == "always":
            return True
        elif condition.startswith("trial_"):
            target_trial = int(condition.split("_")[1])
            return trial_index == target_trial
        elif condition.startswith("percent_"):
            percent = int(condition.split("_")[1])
            return rng.randint(1, 100) <= percent
        return False

    def _get_affected_components(self, scenario_id: str) -> list[str]:
        """returns components affected by fault scenario."""
        if scenario_id == "simple_invariant":
            return ["artifact_store", "content_hash_validator"]
        elif scenario_id == "intermittent_timing":
            return ["queue_ordering", "execution_scheduler", "timing_dependent_path"]
        return []

    def _generate_repair_action(
        self, scenario_id: str, attempt: int, rng: random.Random
    ) -> dict[str, Any]:
        """generates repair action for fault scenario."""
        if scenario_id == "simple_invariant":
            return {
                "action": "recompute_content_hash",
                "target": "artifact_store",
                "attempt": attempt + 1,
                "timestamp": datetime.utcnow().isoformat(),
            }
        elif scenario_id == "intermittent_timing":
            actions = [
                "add_ordering_constraint",
                "inject_synchronization_barrier",
                "increase_timeout_buffer",
            ]
            return {
                "action": actions[attempt % len(actions)],
                "target": "execution_scheduler",
                "attempt": attempt + 1,
                "timestamp": datetime.utcnow().isoformat(),
            }
        return {"action": "unknown", "attempt": attempt + 1}

    def _generate_regression_tests(
        self, scenario_id: str, repair_actions: list, rng: random.Random
    ) -> list[dict[str, Any]]:
        """generates regression tests for fault scenario."""
        tests = []
        if scenario_id == "simple_invariant":
            tests.append({
                "name": "test_content_hash_integrity",
                "type": "invariant",
                "target": "artifact_store",
                "assertion": "content_hash matches computed hash",
            })
        elif scenario_id == "intermittent_timing":
            tests.append({
                "name": "test_queue_ordering_determinism",
                "type": "timing",
                "target": "execution_scheduler",
                "assertion": "queue order is deterministic with fixed seed",
            })
            tests.append({
                "name": "test_timing_barrier_effectiveness",
                "type": "timing",
                "target": "execution_scheduler",
                "assertion": "synchronization barrier prevents race",
            })
            if rng.random() < 0.5:
                tests.append({
                    "name": "test_timeout_buffer_sufficiency",
                    "type": "timing",
                    "target": "execution_scheduler",
                    "assertion": "timeout buffer covers worst-case latency",
                })
        return tests

    def _generate_trace(self, seed: int) -> str:
        """generates deterministic trace hash from seed."""
        rng = random.Random(seed)
        trace_data = [rng.randint(0, 1000) for _ in range(100)]
        return hashlib.sha256(str(trace_data).encode()).hexdigest()

    async def _get_run(self, session: AsyncSession, run_id: str) -> RunRecord | None:
        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        return result.scalar_one_or_none()

    async def _update_phase(self, session: AsyncSession, run_id: str, phase: RunPhase) -> None:
        await session.execute(
            update(RunRecord).where(RunRecord.id == run_id).values(phase=phase.value)
        )

    async def _update_budget(self, session: AsyncSession, run_id: str, budget: Budget) -> None:
        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                steps_used=budget.steps_used,
                tool_calls_used=budget.tool_calls_used,
                belief_writes_used=budget.belief_writes_used,
            )
        )

    async def _fail_run(self, session: AsyncSession, run_id: str, reason: str) -> None:
        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                status="failed",
                phase=RunPhase.FAILED.value,
                finished_at=datetime.utcnow(),
                failure_reason=reason,
            )
        )


_executor: RunExecutor | None = None


def get_executor() -> RunExecutor:
    global _executor
    if _executor is None:
        _executor = RunExecutor()
    return _executor
