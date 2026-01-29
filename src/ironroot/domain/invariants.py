# Author: Bradley R. Kinnard
"""system invariants that trigger containment when violated."""

from dataclasses import dataclass
from typing import TypeVar

from ironroot.domain.errors import InvariantViolation

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Invariant:
    """named invariant with a check function."""

    name: str
    description: str


def check_invariant(
    invariant: Invariant,
    condition: bool,
    details: str = "",
) -> None:
    """raises InvariantViolation if condition is false."""
    if not condition:
        raise InvariantViolation(invariant.name, details or invariant.description)


# core system invariants
BELIEF_HASH_CHAIN = Invariant(
    name="belief_hash_chain",
    description="every belief must reference its parent hash correctly",
)

ARTIFACT_INTEGRITY = Invariant(
    name="artifact_integrity",
    description="stored artifact bytes must match recorded hash",
)

BUDGET_NOT_NEGATIVE = Invariant(
    name="budget_not_negative",
    description="resource budgets must never go negative",
)

RUN_STATE_MACHINE = Invariant(
    name="run_state_machine",
    description="run phase transitions must follow defined state machine",
)

STRATEGY_GATE_REQUIRED = Invariant(
    name="strategy_gate_required",
    description="strategies cannot be promoted without passing gates",
)
