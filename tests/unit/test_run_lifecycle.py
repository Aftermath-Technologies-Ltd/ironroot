# Author: Bradley R. Kinnard
"""unit tests for run lifecycle and budget enforcement."""

import pytest

from ironroot.domain.errors import BudgetExhausted, InvariantViolation
from ironroot.orchestration.budgets import Budget
from ironroot.orchestration.kill_switch import KillSwitch
from ironroot.orchestration.supervisor import RunPhase, Supervisor


class TestSupervisorStateMachine:
    """tests for supervisor phase transitions."""

    def test_initial_phase_is_init(self) -> None:
        """supervisor starts in init phase."""
        supervisor = Supervisor("run_001", seed=42)
        assert supervisor.phase == RunPhase.INIT

    def test_valid_transition_init_to_propose(self) -> None:
        """can transition from init to propose."""
        supervisor = Supervisor("run_001", seed=42)
        supervisor.transition_to(RunPhase.PROPOSE)
        assert supervisor.phase == RunPhase.PROPOSE

    def test_valid_transition_propose_to_build(self) -> None:
        """can transition from propose to build."""
        supervisor = Supervisor("run_001", seed=42)
        supervisor.transition_to(RunPhase.PROPOSE)
        supervisor.transition_to(RunPhase.BUILD)
        assert supervisor.phase == RunPhase.BUILD

    def test_full_happy_path(self) -> None:
        """can transition through complete happy path."""
        supervisor = Supervisor("run_001", seed=42)

        phases = [
            RunPhase.PROPOSE,
            RunPhase.BUILD,
            RunPhase.TEST,
            RunPhase.VERIFY,
            RunPhase.AUDIT,
            RunPhase.DECIDE,
            RunPhase.FINALIZE,
        ]

        for phase in phases:
            supervisor.transition_to(phase)

        assert supervisor.phase == RunPhase.FINALIZE
        assert supervisor.is_terminal()

    def test_invalid_transition_raises(self) -> None:
        """invalid transition raises InvariantViolation."""
        supervisor = Supervisor("run_001", seed=42)

        # cannot go directly from init to test
        with pytest.raises(InvariantViolation):
            supervisor.transition_to(RunPhase.TEST)

    def test_stop_from_any_phase(self) -> None:
        """can stop from any non-terminal phase."""
        for start_phase in [RunPhase.INIT, RunPhase.PROPOSE, RunPhase.BUILD, RunPhase.TEST]:
            supervisor = Supervisor("run_001", seed=42)
            # manually set phase for testing
            supervisor.phase = start_phase
            supervisor.stop()
            assert supervisor.phase == RunPhase.STOPPED

    def test_stop_is_terminal(self) -> None:
        """stopped phase is terminal."""
        supervisor = Supervisor("run_001", seed=42)
        supervisor.stop()
        assert supervisor.is_terminal()

    def test_fail_is_terminal(self) -> None:
        """failed phase is terminal."""
        supervisor = Supervisor("run_001", seed=42)
        supervisor.fail("test failure")
        assert supervisor.is_terminal()
        assert supervisor.phase == RunPhase.FAILED

    def test_cannot_transition_from_terminal(self) -> None:
        """cannot transition away from terminal states."""
        supervisor = Supervisor("run_001", seed=42)
        supervisor.stop()

        with pytest.raises(InvariantViolation):
            supervisor.transition_to(RunPhase.PROPOSE)


class TestBudgetEnforcement:
    """tests for budget exhaustion halting runs."""

    def test_budget_exhaustion_raises(self) -> None:
        """exhausting budget raises BudgetExhausted."""
        budget = Budget(max_steps=5, max_tool_calls=10, max_belief_writes=10)

        for _ in range(5):
            budget.use_step()

        with pytest.raises(BudgetExhausted) as exc_info:
            budget.use_step()

        assert exc_info.value.resource == "steps"
        assert exc_info.value.limit == 5
        assert exc_info.value.used == 6

    def test_tool_call_exhaustion(self) -> None:
        """exhausting tool calls raises."""
        budget = Budget(max_steps=100, max_tool_calls=3, max_belief_writes=100)

        budget.use_tool_call(3)

        with pytest.raises(BudgetExhausted) as exc_info:
            budget.use_tool_call()

        assert exc_info.value.resource == "tool_calls"

    def test_belief_write_exhaustion(self) -> None:
        """exhausting belief writes raises."""
        budget = Budget(max_steps=100, max_tool_calls=100, max_belief_writes=2)

        budget.use_belief_write(2)

        with pytest.raises(BudgetExhausted):
            budget.use_belief_write()

    def test_is_exhausted_true_when_any_depleted(self) -> None:
        """is_exhausted returns true when any budget is at zero."""
        budget = Budget(max_steps=1, max_tool_calls=100, max_belief_writes=100)
        budget.use_step()

        assert budget.is_exhausted()

    def test_is_exhausted_false_when_all_have_remaining(self) -> None:
        """is_exhausted returns false when budgets remain."""
        budget = Budget(max_steps=10, max_tool_calls=10, max_belief_writes=10)
        budget.use_step(5)

        assert not budget.is_exhausted()


class TestKillSwitch:
    """tests for kill switch triggering containment."""

    def test_kill_switch_stops_run(self) -> None:
        """kill switch triggers stop on supervisor."""
        supervisor = Supervisor("run_001", seed=42)
        kill_switch = KillSwitch(supervisor)

        violation = InvariantViolation("test_invariant", "test details")
        kill_switch.check_and_trigger(violation)

        assert kill_switch.is_triggered()
        assert supervisor.phase == RunPhase.STOPPED

    def test_kill_switch_records_reason(self) -> None:
        """kill switch records trigger reason."""
        supervisor = Supervisor("run_001", seed=42)
        kill_switch = KillSwitch(supervisor)

        violation = InvariantViolation("hash_chain", "chain broken at belief 5")
        kill_switch.check_and_trigger(violation)

        assert "hash_chain" in kill_switch.trigger_reason

    def test_kill_switch_idempotent(self) -> None:
        """multiple triggers are ignored."""
        supervisor = Supervisor("run_001", seed=42)
        kill_switch = KillSwitch(supervisor)

        violation1 = InvariantViolation("first", "first violation")
        violation2 = InvariantViolation("second", "second violation")

        kill_switch.check_and_trigger(violation1)
        kill_switch.check_and_trigger(violation2)

        # should record first violation only
        assert "first" in kill_switch.trigger_reason


class TestDeterministicSeeding:
    """tests for deterministic run replay."""

    def test_same_seed_same_run_id_format(self) -> None:
        """same seed produces consistent behavior."""
        supervisor1 = Supervisor("run_001", seed=12345)
        supervisor2 = Supervisor("run_001", seed=12345)

        # both start in same phase
        assert supervisor1.phase == supervisor2.phase
        assert supervisor1.seed == supervisor2.seed

    def test_seed_is_preserved(self) -> None:
        """seed is preserved through transitions."""
        supervisor = Supervisor("run_001", seed=98765)

        supervisor.transition_to(RunPhase.PROPOSE)
        supervisor.transition_to(RunPhase.BUILD)

        assert supervisor.seed == 98765
