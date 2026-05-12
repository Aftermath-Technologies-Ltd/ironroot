# Author: Bradley R. Kinnard
"""Multi-domain reality sources for RIL++.

Supports: tabular, time series, hidden-param simulators, delayed-outcome, adversarial.
All sources produce locked, hashed observations that agents cannot influence.
"""

from ironroot.reality.sources.adversarial import AdversarialSource
from ironroot.reality.sources.base import (
    ExternalObservation,
    ProvenanceRecord,
    RealitySource,
    RealitySourceType,
)
from ironroot.reality.sources.delayed import DelayedOutcomeSource
from ironroot.reality.sources.simulator import HiddenParamSimulator
from ironroot.reality.sources.tabular import TabularDatasetSource
from ironroot.reality.sources.time_series import TimeSeriesSource

__all__ = [
    "AdversarialSource",
    "DelayedOutcomeSource",
    "ExternalObservation",
    "HiddenParamSimulator",
    "ProvenanceRecord",
    "RealitySource",
    "RealitySourceType",
    "TabularDatasetSource",
    "TimeSeriesSource",
]
