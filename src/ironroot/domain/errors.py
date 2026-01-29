# Author: Bradley R. Kinnard
"""domain errors with explicit failure modes."""


class IronrootError(Exception):
    """base error for all ironroot exceptions."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or "IRONROOT_ERROR"


class IntegrityError(IronrootError):
    """hash mismatch or tamper detection."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="INTEGRITY_ERROR")


class ImmutabilityViolation(IronrootError):
    """attempt to modify append-only data."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="IMMUTABILITY_VIOLATION")


class BudgetExhausted(IronrootError):
    """agent or run exceeded resource budget."""

    def __init__(self, resource: str, limit: int, used: int) -> None:
        super().__init__(
            f"budget exhausted: {resource} limit={limit} used={used}",
            code="BUDGET_EXHAUSTED",
        )
        self.resource = resource
        self.limit = limit
        self.used = used


class InvariantViolation(IronrootError):
    """system invariant broken, triggers containment."""

    def __init__(self, invariant: str, details: str) -> None:
        super().__init__(
            f"invariant violated: {invariant} - {details}",
            code="INVARIANT_VIOLATION",
        )
        self.invariant = invariant
        self.details = details


class GateFailed(IronrootError):
    """verification gate did not pass."""

    def __init__(self, gate_name: str, reason: str) -> None:
        super().__init__(
            f"gate failed: {gate_name} - {reason}",
            code="GATE_FAILED",
        )
        self.gate_name = gate_name
        self.reason = reason


class NotFoundError(IronrootError):
    """requested resource does not exist."""

    def __init__(self, resource_type: str, resource_id: str) -> None:
        super().__init__(
            f"{resource_type} not found: {resource_id}",
            code="NOT_FOUND",
        )
        self.resource_type = resource_type
        self.resource_id = resource_id
