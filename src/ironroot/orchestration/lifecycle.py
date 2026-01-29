# Author: Bradley R. Kinnard
"""run lifecycle management."""

from dataclasses import dataclass
from typing import Literal

from ironroot.domain.ids import generate_id
from ironroot.domain.time import now_iso
from ironroot.orchestration.budgets import Budget
from ironroot.orchestration.supervisor import RunPhase, Supervisor


@dataclass
class RunRecord:
    """persisted run state."""

    run_id: str
    seed: int
    status: Literal["pending", "running", "completed", "failed", "stopped"]
    phase: RunPhase
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    gate_artifact_id: str | None = None


def create_run(
    seed: int, max_steps: int, max_tool_calls: int, max_belief_writes: int
) -> tuple[RunRecord, Supervisor, Budget]:
    """creates a new run with supervisor and budget."""
    run_id = generate_id("run")

    record = RunRecord(
        run_id=run_id,
        seed=seed,
        status="pending",
        phase=RunPhase.INIT,
        created_at=now_iso(),
    )

    supervisor = Supervisor(run_id, seed)

    budget = Budget(
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        max_belief_writes=max_belief_writes,
    )

    return record, supervisor, budget
