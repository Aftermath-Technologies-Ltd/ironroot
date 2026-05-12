# Author: Bradley R. Kinnard
"""belief domain module — canonical home for BeliefService and ContradictionService."""

from ironroot.beliefs.belief_service import (
    PRIMARY_METRIC_NAMES,
    VERIFIER_ARTIFACT_TYPES,
    BeliefService,
    BeliefType,
    MetricClass,
    PredictionStatus,
    ProvenanceRef,
    get_belief_service,
)
from ironroot.beliefs.contradiction_service import (
    ContradictionService,
    get_contradiction_service,
)

__all__ = [
    "PRIMARY_METRIC_NAMES",
    "VERIFIER_ARTIFACT_TYPES",
    "BeliefService",
    "BeliefType",
    "ContradictionService",
    "MetricClass",
    "PredictionStatus",
    "ProvenanceRef",
    "get_belief_service",
    "get_contradiction_service",
]
