# Author: Bradley R. Kinnard
"""base agent class with budget tracking and policy enforcement."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ironroot.domain.policies import AgentPolicy, ToolPermission
from ironroot.orchestration.budgets import Budget


@dataclass
class AgentState:
    """mutable agent state for tracking usage and penalties."""

    steps_used: int = 0
    tool_calls_used: int = 0
    belief_writes_used: int = 0
    penalties: list[dict[str, Any]] = field(default_factory=list)
    revoked_tools: set[ToolPermission] = field(default_factory=set)
    terminated: bool = False


class BaseAgent(ABC):
    """abstract base for all agent roles."""

    def __init__(self, agent_id: str, run_id: str, policy: AgentPolicy, budget: Budget) -> None:
        self.agent_id = agent_id
        self.run_id = run_id
        self.policy = policy
        self.budget = budget
        self.state = AgentState()

    def can_use_tool(self, tool: ToolPermission) -> bool:
        """checks if tool is allowed and not revoked."""
        if self.state.terminated:
            return False
        if tool in self.state.revoked_tools:
            return False
        return tool in self.policy.allowed_tools

    def use_step(self) -> None:
        """consumes a step from budget."""
        self.budget.use_step()
        self.state.steps_used += 1

    def use_tool_call(self) -> None:
        """consumes a tool call from budget."""
        self.budget.use_tool_call()
        self.state.tool_calls_used += 1

    def apply_penalty(self, penalty_type: str, details: str) -> None:
        """records a penalty against this agent."""
        self.state.penalties.append(
            {
                "type": penalty_type,
                "details": details,
                "at_step": self.state.steps_used,
            }
        )

    def revoke_tool(self, tool: ToolPermission) -> None:
        """permanently revokes a tool from this agent."""
        self.state.revoked_tools.add(tool)

    def terminate(self) -> None:
        """terminates this agent instance."""
        self.state.terminated = True

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """executes the agent's primary function."""
        pass
