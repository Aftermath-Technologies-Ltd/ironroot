# Author: Bradley R. Kinnard
"""task planning with budget awareness."""

from dataclasses import dataclass


@dataclass
class PlanStep:
    """single step in a plan."""

    step_id: int
    action: str
    agent_role: str
    estimated_cost: int
    dependencies: list[int]


@dataclass
class Plan:
    """ordered sequence of steps."""

    plan_id: str
    steps: list[PlanStep]
    total_estimated_cost: int


def create_plan(goal: str, budget_remaining: int) -> Plan | None:
    """creates a plan if budget allows, returns none if infeasible."""
    # todo: implement planning logic in phase 3
    return None
