# Author: Bradley R. Kinnard
"""incident types for self-healing pipeline."""

from enum import Enum


class IncidentType(str, Enum):
    """types of incidents that trigger containment."""

    INTEGRITY_FAILURE = "integrity_failure"
    DETERMINISM_MISMATCH = "determinism_mismatch"
    INVARIANT_VIOLATION = "invariant_violation"
    VERIFICATION_FAILURE = "verification_failure"
    BUDGET_EXCEEDED = "budget_exceeded"
    POLICY_VIOLATION = "policy_violation"


class Severity(str, Enum):
    """severity levels for incidents."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# mapping of incident types to default severity
DEFAULT_SEVERITY: dict[IncidentType, Severity] = {
    IncidentType.INTEGRITY_FAILURE: Severity.CRITICAL,
    IncidentType.DETERMINISM_MISMATCH: Severity.HIGH,
    IncidentType.INVARIANT_VIOLATION: Severity.CRITICAL,
    IncidentType.VERIFICATION_FAILURE: Severity.HIGH,
    IncidentType.BUDGET_EXCEEDED: Severity.MEDIUM,
    IncidentType.POLICY_VIOLATION: Severity.HIGH,
}
