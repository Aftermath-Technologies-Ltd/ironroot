# Author: Bradley R. Kinnard
"""strategy scoring for selection."""

from dataclasses import dataclass


@dataclass
class StrategyScore:
    """multi-objective score for a strategy."""

    strategy_id: str
    correctness: float  # gate pass rate
    reproducibility: float  # replay digest match rate
    efficiency: float  # budget utilization
    safety: float  # inverse incident rate

    def composite(self) -> float:
        """weighted composite score, correctness dominates."""
        return (
            self.correctness * 0.5
            + self.reproducibility * 0.25
            + self.efficiency * 0.15
            + self.safety * 0.10
        )


def score_strategy(
    strategy_id: str,
    gate_passed: bool,
    replay_matched: bool,
    budget_used_ratio: float,
    incident_count: int,
) -> StrategyScore:
    """computes score from run results."""
    correctness = 1.0 if gate_passed else 0.0
    reproducibility = 1.0 if replay_matched else 0.0
    efficiency = 1.0 - min(budget_used_ratio, 1.0)
    safety = 1.0 / (1.0 + incident_count)

    return StrategyScore(
        strategy_id=strategy_id,
        correctness=correctness,
        reproducibility=reproducibility,
        efficiency=efficiency,
        safety=safety,
    )
