# Author: Bradley R. Kinnard
"""event types for ui streaming."""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class UIEvent:
    """event for ui consumption."""

    event_type: Literal["run_update", "gate_update", "belief_added", "incident"]
    run_id: str
    data: dict[str, Any]
    timestamp: str


def run_update_event(run_id: str, phase: str, status: str, timestamp: str) -> UIEvent:
    """creates a run update event."""
    return UIEvent(
        event_type="run_update",
        run_id=run_id,
        data={"phase": phase, "status": status},
        timestamp=timestamp,
    )


def gate_update_event(run_id: str, gate_bundle_id: str, status: str, timestamp: str) -> UIEvent:
    """creates a gate update event."""
    return UIEvent(
        event_type="gate_update",
        run_id=run_id,
        data={"gate_bundle_id": gate_bundle_id, "status": status},
        timestamp=timestamp,
    )
