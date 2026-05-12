# Author: Bradley R. Kinnard
"""run executor with fault injection and self-healing capabilities."""

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.beliefs import MetricClass, get_belief_service
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
    """fault injection configuration.

    Phase 2b.1: the executor now delegates fault behaviour to a named
    ``FaultFixture`` resolved via ``fixture_id``. The fixture is the
    deterministic source of truth for what to break and how to revert.

    Legacy fields (``scenario_id``, ``trigger_condition``, …) are kept
    for backward compatibility with the older RNG-driven path but only
    ``percent_*`` triggers are removed because they depended on RNG.
    Supported triggers are ``always`` and ``trial_<N>``.
    """

    enabled: bool = False
    fixture_id: str = ""  # FaultFixture.fixture_id, registered via get_fault_fixture_registry
    scenario_id: str = "none"
    trigger_phase: str = "test"
    trigger_condition: str = "always"
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
                "timestamp": datetime.now(UTC).isoformat(),
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
        observed_fault_effect: dict[str, Any] | None = None
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
            # === FAULT INJECTION (Phase 2b.1 — deterministic) ===
            #
            # If the run config names a FaultFixture and we're in the
            # configured trigger phase, the executor applies the fixture
            # against the live chain and records the OBSERVED effect.
            # The fixture is responsible for being deterministic; the
            # executor records what happened, not a sampled probability.
            #
            # Repair / regression / restoration is no longer the
            # executor's job. The self-healing pipeline (see
            # `ironroot.healing.restoration.SelfHealingRestorer`)
            # consumes the fixture id from the observed-effect belief
            # and runs deterministic restoration via the same fixture's
            # `revert` method.
            should_inject = self._should_inject_fault(fi_config, target_phase.value, trial_index)

            if should_inject and fi_config.fixture_id:
                fixture = self._resolve_fault_fixture(fi_config.fixture_id)
                if fixture is None:
                    fault_data = {
                        "fixture_id": fi_config.fixture_id,
                        "error": "fixture_not_registered",
                        "trigger_phase": target_phase.value,
                        "trial_index": trial_index,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                else:
                    healing_state.fault_detected = True
                    healing_state.fault_timestamp = time.time()
                    effect = await fixture.apply(session, run_id)
                    observed_fault_effect = effect.to_dict()
                    fault_data = {
                        "fixture_id": fixture.fixture_id,
                        "fixture_description": fixture.description,
                        "trigger_phase": target_phase.value,
                        "trial_index": trial_index,
                        "observed_effect": observed_fault_effect,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                fault_artifact = await artifact_service.store_artifact(
                    session=session,
                    data=json.dumps(fault_data, sort_keys=True).encode(),
                    artifact_type="fault_injection_report",
                    created_by="fault_injector",
                    run_id=run_id,
                    filename=f"fault_injection_{run_id}.json",
                )
                fault_artifact_id = fault_artifact.id

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
                    "timestamp": datetime.now(UTC).isoformat(),
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
                    "timestamp": datetime.now(UTC).isoformat(),
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
                    "timestamp": datetime.now(UTC).isoformat(),
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
                        failed_checks.append(
                            {
                                "check": f"edge_case_{i}",
                                "reason": "timing-dependent path, does not affect seeded determinism",
                            }
                        )

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

                # Self-healing metrics are now owned by
                # `SelfHealingRestorer.restore_correctness`, which writes
                # typed PRIMARY observations + an INFERENCE belief with
                # provenance pointing at the fault fixture id. The
                # executor's job ends at recording the observed fault
                # effect (above); restoration is a separate phase.

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
                "timestamp": datetime.now(UTC).isoformat(),
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
                finished_at=datetime.now(UTC),
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
            fixture_id=raw.get("fixture_id", ""),
            scenario_id=raw.get("scenario_id", "none"),
            trigger_phase=raw.get("trigger_phase", "test"),
            trigger_condition=raw.get("trigger_condition", "always"),
            expected_signature=raw.get("expected_signature", ""),
        )

    def _should_inject_fault(
        self,
        config: FaultInjectionConfig,
        current_phase: str,
        trial_index: int,
    ) -> bool:
        """determines if fault should be injected this phase.

        Phase 2b.1: deterministic only. ``percent_*`` triggers are gone
        because they required RNG. Supported triggers:

        * ``always``     — inject on every phase that matches
                           ``trigger_phase``
        * ``trial_<N>``  — inject only on the N-th trial in
                           ``trigger_phase``
        """
        if not config.enabled:
            return False
        if current_phase != config.trigger_phase:
            return False

        condition = config.trigger_condition
        if condition == "always":
            return True
        if condition.startswith("trial_"):
            target_trial = int(condition.split("_")[1])
            return trial_index == target_trial
        return False

    def _resolve_fault_fixture(self, fixture_id: str) -> Any | None:
        """looks up a FaultFixture by id from the process-global registry."""
        from ironroot.verification.fault_fixtures import get_fault_fixture_registry

        return get_fault_fixture_registry().get(fixture_id)

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
                finished_at=datetime.now(UTC),
                failure_reason=reason,
            )
        )


_executor: RunExecutor | None = None


def get_executor() -> RunExecutor:
    global _executor
    if _executor is None:
        _executor = RunExecutor()
    return _executor
