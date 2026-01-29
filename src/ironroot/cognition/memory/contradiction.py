# Author: Bradley R. Kinnard
"""contradiction detection and linking."""

from dataclasses import dataclass

from ironroot.domain.ids import generate_id
from ironroot.domain.time import now_iso


@dataclass(frozen=True)
class ContradictionEvent:
    """records a detected contradiction between beliefs."""

    contradiction_id: str
    belief_a_id: str
    belief_b_id: str
    detected_by: str
    detection_method: str
    created_at: str
    details: str


class ContradictionDetector:
    """detects and records contradictions between beliefs."""

    def __init__(self) -> None:
        self._contradictions: dict[str, ContradictionEvent] = {}
        self._by_belief: dict[str, list[str]] = {}

    def record(
        self,
        belief_a_id: str,
        belief_b_id: str,
        detected_by: str,
        detection_method: str,
        details: str,
    ) -> ContradictionEvent:
        """records a new contradiction event."""
        contradiction_id = generate_id("inc")

        event = ContradictionEvent(
            contradiction_id=contradiction_id,
            belief_a_id=belief_a_id,
            belief_b_id=belief_b_id,
            detected_by=detected_by,
            detection_method=detection_method,
            created_at=now_iso(),
            details=details,
        )

        self._contradictions[contradiction_id] = event

        # index by both beliefs
        self._by_belief.setdefault(belief_a_id, []).append(contradiction_id)
        self._by_belief.setdefault(belief_b_id, []).append(contradiction_id)

        return event

    def get_for_belief(self, belief_id: str) -> list[ContradictionEvent]:
        """returns all contradictions involving a belief."""
        ids = self._by_belief.get(belief_id, [])
        return [self._contradictions[cid] for cid in ids if cid in self._contradictions]

    def list_all(self) -> list[ContradictionEvent]:
        """returns all contradiction events."""
        return list(self._contradictions.values())
