# Author: Bradley R. Kinnard
"""abstention policy: when to refuse action."""

from dataclasses import dataclass


@dataclass
class AbstentionDecision:
    """result of abstention check."""

    should_abstain: bool
    reason: str | None
    confidence: float


def should_abstain(
    confidence: float,
    threshold: float,
    budget_remaining: int,
    min_budget: int = 10,
) -> AbstentionDecision:
    """decides whether to abstain from an action."""
    if confidence < threshold:
        return AbstentionDecision(
            should_abstain=True,
            reason=f"confidence {confidence:.2f} below threshold {threshold:.2f}",
            confidence=confidence,
        )

    if budget_remaining < min_budget:
        return AbstentionDecision(
            should_abstain=True,
            reason=f"budget {budget_remaining} below minimum {min_budget}",
            confidence=confidence,
        )

    return AbstentionDecision(
        should_abstain=False,
        reason=None,
        confidence=confidence,
    )
