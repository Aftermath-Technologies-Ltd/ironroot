# Author: Bradley R. Kinnard
"""bounded strategy mutation."""

import random

from ironroot.cognition.strategies.registry import StrategyManifest
from ironroot.domain.ids import generate_id


def mutate_strategy(
    base: StrategyManifest,
    seed: int,
    mutation_rate: float = 0.1,
) -> StrategyManifest:
    """creates a mutated variant with bounded changes."""
    rng = random.Random(seed)

    # mutate abstention threshold within bounds
    delta = rng.uniform(-mutation_rate, mutation_rate)
    new_threshold = max(0.0, min(1.0, base.abstention_threshold + delta))

    # generate new version
    base_version = base.version.split(".")
    patch = int(base_version[-1]) if base_version[-1].isdigit() else 0
    new_version = f"{'.'.join(base_version[:-1])}.{patch + 1}"

    new_id = generate_id("str")

    return StrategyManifest(
        strategy_id=new_id,
        name=base.name,
        version=new_version,
        capabilities=list(base.capabilities),
        tool_permissions=list(base.tool_permissions),
        abstention_threshold=new_threshold,
        pinned_dependencies=dict(base.pinned_dependencies),
        created_at=base.created_at,
        gate_passed=False,
        promoted=False,
    )
