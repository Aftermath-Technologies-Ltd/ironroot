# Author: Bradley R. Kinnard
"""proposer agent: suggests changes to cognitive layers or strategies."""

from typing import Any

from ironroot.agents.base import BaseAgent
from ironroot.domain.policies import DEFAULT_POLICIES
from ironroot.orchestration.budgets import Budget


class ProposerAgent(BaseAgent):
    """proposes changes, does not implement them."""

    def __init__(self, agent_id: str, run_id: str, budget: Budget) -> None:
        policy = DEFAULT_POLICIES["proposer"]
        super().__init__(agent_id, run_id, policy, budget)

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """generates a proposal based on context."""
        self.use_step()
        # todo: implement proposal logic in phase 3
        return {
            "agent_id": self.agent_id,
            "proposal": None,
            "confidence": 0.0,
        }
