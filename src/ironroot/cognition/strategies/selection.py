# Author: Bradley R. Kinnard
"""strategy selection based on scores."""

from ironroot.cognition.strategies.scoring import StrategyScore


def select_best(scores: list[StrategyScore]) -> StrategyScore | None:
    """selects the strategy with highest composite score."""
    if not scores:
        return None

    # filter to only strategies that passed correctness
    passing = [s for s in scores if s.correctness > 0]
    if not passing:
        return None

    return max(passing, key=lambda s: s.composite())


def select_top_k(scores: list[StrategyScore], k: int) -> list[StrategyScore]:
    """selects top k strategies by composite score."""
    passing = [s for s in scores if s.correctness > 0]
    sorted_scores = sorted(passing, key=lambda s: s.composite(), reverse=True)
    return sorted_scores[:k]
