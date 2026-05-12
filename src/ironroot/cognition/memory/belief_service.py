# Author: Bradley R. Kinnard
"""DEPRECATED — re-exports from ``ironroot.beliefs`` (Phase 1.7 consolidation).

Importing from ``ironroot.cognition.memory.belief_service`` raises a
``DeprecationWarning`` and forwards to the canonical
``ironroot.beliefs.belief_service`` module. This shim is scheduled for
removal in the next release; update imports to
``from ironroot.beliefs import BeliefService, get_belief_service``.

No parallel ``BeliefService`` class is defined here — the CI test
``tests/unit/test_belief_service_consolidation.py`` asserts there is only
one ``class BeliefService`` definition in ``src/ironroot``.
"""

from __future__ import annotations

import warnings

from ironroot.beliefs.belief_service import (
    BeliefService,
    BeliefType,
    MetricClass,
    PredictionStatus,
    get_belief_service,
)
from ironroot.beliefs.contradiction_service import (
    ContradictionService,
    get_contradiction_service,
)

warnings.warn(
    "ironroot.cognition.memory.belief_service is deprecated; "
    "import from ironroot.beliefs instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "BeliefService",
    "BeliefType",
    "ContradictionService",
    "MetricClass",
    "PredictionStatus",
    "get_belief_service",
    "get_contradiction_service",
]
