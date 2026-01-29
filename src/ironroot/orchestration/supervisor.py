# Author: Bradley R. Kinnard
"""supervisor state machine for run orchestration."""

from enum import Enum
from typing import TYPE_CHECKING

from ironroot.domain.invariants import RUN_STATE_MACHINE, check_invariant

if TYPE_CHECKING:
    from collections.abc import Callable


class RunPhase(str, Enum):
    """explicit state machine phases for a run."""

    INIT = "init"
    PROPOSE = "propose"
    BUILD = "build"
    TEST = "test"
    VERIFY = "verify"
    AUDIT = "audit"
    DECIDE = "decide"
    REPAIR = "repair"
    FINALIZE = "finalize"
    STOPPED = "stopped"
    FAILED = "failed"


# valid phase transitions
TRANSITIONS: dict[RunPhase, set[RunPhase]] = {
    RunPhase.INIT: {RunPhase.PROPOSE, RunPhase.STOPPED, RunPhase.FAILED},
    RunPhase.PROPOSE: {RunPhase.BUILD, RunPhase.STOPPED, RunPhase.FAILED},
    RunPhase.BUILD: {RunPhase.TEST, RunPhase.STOPPED, RunPhase.FAILED},
    RunPhase.TEST: {RunPhase.VERIFY, RunPhase.REPAIR, RunPhase.STOPPED, RunPhase.FAILED},
    RunPhase.VERIFY: {RunPhase.AUDIT, RunPhase.REPAIR, RunPhase.STOPPED, RunPhase.FAILED},
    RunPhase.AUDIT: {RunPhase.DECIDE, RunPhase.REPAIR, RunPhase.STOPPED, RunPhase.FAILED},
    RunPhase.DECIDE: {RunPhase.FINALIZE, RunPhase.REPAIR, RunPhase.STOPPED, RunPhase.FAILED},
    RunPhase.REPAIR: {RunPhase.TEST, RunPhase.STOPPED, RunPhase.FAILED},
    RunPhase.FINALIZE: set(),
    RunPhase.STOPPED: set(),
    RunPhase.FAILED: set(),
}


class Supervisor:
    """orchestrates run phases with budget enforcement."""

    def __init__(self, run_id: str, seed: int) -> None:
        self.run_id = run_id
        self.seed = seed
        self.phase = RunPhase.INIT
        self._phase_handlers: dict[RunPhase, Callable[[], RunPhase]] = {}

    def transition_to(self, target: RunPhase) -> None:
        """transitions to target phase, validates state machine."""
        allowed = TRANSITIONS.get(self.phase, set())
        check_invariant(
            RUN_STATE_MACHINE,
            target in allowed,
            f"cannot transition from {self.phase} to {target}",
        )
        self.phase = target

    def stop(self) -> None:
        """hard stop, valid from any non-terminal phase."""
        if self.phase not in {RunPhase.FINALIZE, RunPhase.STOPPED, RunPhase.FAILED}:
            self.phase = RunPhase.STOPPED

    def fail(self, reason: str) -> None:
        """marks run as failed."""
        if self.phase not in {RunPhase.FINALIZE, RunPhase.STOPPED, RunPhase.FAILED}:
            self.phase = RunPhase.FAILED

    def is_terminal(self) -> bool:
        """returns true if run is in terminal state."""
        return self.phase in {RunPhase.FINALIZE, RunPhase.STOPPED, RunPhase.FAILED}
