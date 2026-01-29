# Author: Bradley R. Kinnard
"""invariant checking for runs and beliefs."""

from dataclasses import dataclass

from ironroot.domain.invariants import (
    ARTIFACT_INTEGRITY,
    BELIEF_HASH_CHAIN,
    BUDGET_NOT_NEGATIVE,
    Invariant,
)


@dataclass
class InvariantCheckResult:
    """result of an invariant check."""

    invariant: Invariant
    passed: bool
    details: str


def check_all_invariants(
    belief_chain_ok: bool,
    artifact_integrity_ok: bool,
    budget_ok: bool,
) -> list[InvariantCheckResult]:
    """checks all core invariants, returns results."""
    results = []

    results.append(
        InvariantCheckResult(
            invariant=BELIEF_HASH_CHAIN,
            passed=belief_chain_ok,
            details="" if belief_chain_ok else "hash chain verification failed",
        )
    )

    results.append(
        InvariantCheckResult(
            invariant=ARTIFACT_INTEGRITY,
            passed=artifact_integrity_ok,
            details="" if artifact_integrity_ok else "artifact integrity check failed",
        )
    )

    results.append(
        InvariantCheckResult(
            invariant=BUDGET_NOT_NEGATIVE,
            passed=budget_ok,
            details="" if budget_ok else "budget went negative",
        )
    )

    return results


def any_failed(results: list[InvariantCheckResult]) -> bool:
    """returns true if any invariant failed."""
    return any(not r.passed for r in results)
