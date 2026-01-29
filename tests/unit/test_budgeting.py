# Author: Bradley R. Kinnard
"""unit tests for budget tracking."""

import pytest

from ironroot.domain.errors import BudgetExhausted
from ironroot.orchestration.budgets import Budget


class TestBudget:
    """tests for budget enforcement."""

    def test_initial_state(self) -> None:
        """budget starts with zero usage."""
        budget = Budget(max_steps=100, max_tool_calls=50, max_belief_writes=20)

        assert budget.steps_used == 0
        assert budget.tool_calls_used == 0
        assert budget.belief_writes_used == 0

    def test_use_step(self) -> None:
        """using steps increments counter."""
        budget = Budget(max_steps=100, max_tool_calls=50, max_belief_writes=20)

        budget.use_step()
        assert budget.steps_used == 1

        budget.use_step(5)
        assert budget.steps_used == 6

    def test_use_tool_call(self) -> None:
        """using tool calls increments counter."""
        budget = Budget(max_steps=100, max_tool_calls=50, max_belief_writes=20)

        budget.use_tool_call()
        assert budget.tool_calls_used == 1

    def test_use_belief_write(self) -> None:
        """using belief writes increments counter."""
        budget = Budget(max_steps=100, max_tool_calls=50, max_belief_writes=20)

        budget.use_belief_write()
        assert budget.belief_writes_used == 1

    def test_steps_remaining(self) -> None:
        """remaining calculation is correct."""
        budget = Budget(max_steps=100, max_tool_calls=50, max_belief_writes=20)

        assert budget.steps_remaining() == 100

        budget.use_step(30)
        assert budget.steps_remaining() == 70

    def test_budget_exhaustion_raises(self) -> None:
        """exceeding budget raises BudgetExhausted."""
        budget = Budget(max_steps=10, max_tool_calls=5, max_belief_writes=3)

        # use up all steps
        budget.use_step(10)

        # next step should raise
        with pytest.raises(BudgetExhausted) as exc_info:
            budget.use_step()

        assert exc_info.value.resource == "steps"
        assert exc_info.value.limit == 10

    def test_tool_call_exhaustion(self) -> None:
        """exceeding tool call budget raises."""
        budget = Budget(max_steps=100, max_tool_calls=2, max_belief_writes=20)

        budget.use_tool_call(2)

        with pytest.raises(BudgetExhausted) as exc_info:
            budget.use_tool_call()

        assert exc_info.value.resource == "tool_calls"

    def test_belief_write_exhaustion(self) -> None:
        """exceeding belief write budget raises."""
        budget = Budget(max_steps=100, max_tool_calls=50, max_belief_writes=1)

        budget.use_belief_write()

        with pytest.raises(BudgetExhausted):
            budget.use_belief_write()

    def test_is_exhausted(self) -> None:
        """is_exhausted returns true when any budget is zero."""
        budget = Budget(max_steps=5, max_tool_calls=50, max_belief_writes=20)

        assert not budget.is_exhausted()

        budget.use_step(5)
        assert budget.is_exhausted()

    def test_multiple_exhaustions(self) -> None:
        """multiple budget types can be exhausted."""
        budget = Budget(max_steps=2, max_tool_calls=2, max_belief_writes=2)

        budget.use_step(2)
        budget.use_tool_call(2)
        budget.use_belief_write(2)

        assert budget.is_exhausted()
        assert budget.steps_remaining() == 0
        assert budget.tool_calls_remaining() == 0
        assert budget.belief_writes_remaining() == 0
