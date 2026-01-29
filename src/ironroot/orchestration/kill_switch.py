# Author: Bradley R. Kinnard
"""kill switch for immediate containment on invariant violations."""

from ironroot.domain.errors import InvariantViolation
from ironroot.logging.configure import get_logger
from ironroot.orchestration.supervisor import Supervisor

logger = get_logger(__name__)


class KillSwitch:
    """triggers containment when invariants are violated."""

    def __init__(self, supervisor: Supervisor) -> None:
        self.supervisor = supervisor
        self.triggered = False
        self.trigger_reason: str | None = None

    def check_and_trigger(self, violation: InvariantViolation) -> None:
        """logs violation and stops the run."""
        if self.triggered:
            return

        self.triggered = True
        self.trigger_reason = str(violation)

        logger.error(
            "kill switch triggered",
            run_id=self.supervisor.run_id,
            invariant=violation.invariant,
            details=violation.details,
        )

        self.supervisor.stop()

    def is_triggered(self) -> bool:
        """returns true if kill switch has been triggered."""
        return self.triggered
