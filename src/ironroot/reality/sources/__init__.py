# Author: Bradley R. Kinnard
"""Multi-domain reality sources for RIL++.

Supports: tabular, time series, hidden-param simulators, delayed-outcome, adversarial.
All sources produce locked, hashed observations that agents cannot influence.
"""

from ironroot.reality.sources.base import (
    RealitySource,
    RealitySourceType,
    ProvenanceRecord,
    ExternalObservation,
)
from ironroot.reality.sources.tabular import TabularDatasetSource
from ironroot.reality.sources.time_series import TimeSeriesSource
from ironroot.reality.sources.simulator import HiddenParamSimulator
from ironroot.reality.sources.delayed import DelayedOutcomeSource
from ironroot.reality.sources.adversarial import AdversarialSource

__all__ = [
    "RealitySource",
    "RealitySourceType",
    "ProvenanceRecord",
    "ExternalObservation",
    "TabularDatasetSource",
    "TimeSeriesSource",
    "HiddenParamSimulator",
    "DelayedOutcomeSource",
    "AdversarialSource",
]
