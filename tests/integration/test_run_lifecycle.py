# Author: Bradley R. Kinnard
"""integration tests for run lifecycle."""

import pytest

from ironroot.orchestration.lifecycle import create_run
from ironroot.orchestration.supervisor import RunPhase, Supervisor


class TestRunLifecycle:
    """tests for run creation and state transitions."""

    def test_create_run_returns_components(self) -> None:
        """create_run returns record, supervisor, and budget."""
        record, supervisor, budget = create_run(
            seed=12345,
            max_steps=100,
            max_tool_calls=50,
            max_belief_writes=20,
        )

        assert record.run_id.startswith("run_")
        assert record.seed == 12345
        assert record.status == "pending"
        assert record.phase == RunPhase.INIT

        assert supervisor.run_id == record.run_id
        assert supervisor.seed == 12345

        assert budget.max_steps == 100

    def test_supervisor_transitions(self) -> None:
        """supervisor follows valid state machine."""
        supervisor = Supervisor("run_test", seed=1)

        assert supervisor.phase == RunPhase.INIT

        supervisor.transition_to(RunPhase.PROPOSE)
        assert supervisor.phase == RunPhase.PROPOSE

        supervisor.transition_to(RunPhase.BUILD)
        assert supervisor.phase == RunPhase.BUILD

        supervisor.transition_to(RunPhase.TEST)
        assert supervisor.phase == RunPhase.TEST

    def test_invalid_transition_raises(self) -> None:
        """invalid transitions raise InvariantViolation."""
        from ironroot.domain.errors import InvariantViolation

        supervisor = Supervisor("run_test", seed=1)

        # cannot go directly from INIT to TEST
        with pytest.raises(InvariantViolation):
            supervisor.transition_to(RunPhase.TEST)

    def test_stop_from_any_phase(self) -> None:
        """can stop from any non-terminal phase."""
        supervisor = Supervisor("run_test", seed=1)

        supervisor.transition_to(RunPhase.PROPOSE)
        supervisor.stop()

        assert supervisor.phase == RunPhase.STOPPED
        assert supervisor.is_terminal()

    def test_fail_sets_terminal(self) -> None:
        """fail sets terminal state."""
        supervisor = Supervisor("run_test", seed=1)

        supervisor.fail("test failure")

        assert supervisor.phase == RunPhase.FAILED
        assert supervisor.is_terminal()
