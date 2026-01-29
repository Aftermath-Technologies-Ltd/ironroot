# Author: Bradley R. Kinnard
"""budget tracking with strict enforcement."""

from dataclasses import dataclass, field

from ironroot.domain.errors import BudgetExhausted
from ironroot.domain.invariants import BUDGET_NOT_NEGATIVE, check_invariant


@dataclass
class Budget:
    """tracks resource usage against limits."""

    max_steps: int
    max_tool_calls: int
    max_belief_writes: int
    timeout_seconds: int = 3600

    steps_used: int = field(default=0, init=False)
    tool_calls_used: int = field(default=0, init=False)
    belief_writes_used: int = field(default=0, init=False)

    def use_step(self, count: int = 1) -> None:
        """consumes step budget, raises if exhausted."""
        new_used = self.steps_used + count
        if new_used > self.max_steps:
            raise BudgetExhausted("steps", self.max_steps, new_used)
        self.steps_used = new_used

    def use_tool_call(self, count: int = 1) -> None:
        """consumes tool call budget."""
        new_used = self.tool_calls_used + count
        if new_used > self.max_tool_calls:
            raise BudgetExhausted("tool_calls", self.max_tool_calls, new_used)
        self.tool_calls_used = new_used

    def use_belief_write(self, count: int = 1) -> None:
        """consumes belief write budget."""
        new_used = self.belief_writes_used + count
        if new_used > self.max_belief_writes:
            raise BudgetExhausted("belief_writes", self.max_belief_writes, new_used)
        self.belief_writes_used = new_used

    def steps_remaining(self) -> int:
        """remaining step budget."""
        remaining = self.max_steps - self.steps_used
        check_invariant(BUDGET_NOT_NEGATIVE, remaining >= 0, "steps went negative")
        return remaining

    def tool_calls_remaining(self) -> int:
        """remaining tool call budget."""
        remaining = self.max_tool_calls - self.tool_calls_used
        check_invariant(BUDGET_NOT_NEGATIVE, remaining >= 0, "tool_calls went negative")
        return remaining

    def belief_writes_remaining(self) -> int:
        """remaining belief write budget."""
        remaining = self.max_belief_writes - self.belief_writes_used
        check_invariant(BUDGET_NOT_NEGATIVE, remaining >= 0, "belief_writes went negative")
        return remaining

    def is_exhausted(self) -> bool:
        """returns true if any budget is exhausted."""
        return (
            self.steps_remaining() == 0
            or self.tool_calls_remaining() == 0
            or self.belief_writes_remaining() == 0
        )
