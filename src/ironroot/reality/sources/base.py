# Author: Bradley R. Kinnard
"""Base classes for reality sources."""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class RealitySourceType(str, Enum):
    """types of external reality sources."""

    TABULAR = "tabular"  # structured datasets (CSV, Parquet)
    TIME_SERIES = "time_series"  # temporal sequences with future unknowns
    SIMULATOR = "simulator"  # hidden-param environments
    DELAYED = "delayed"  # outcomes revealed after prediction window
    ADVERSARIAL = "adversarial"  # poisoned or shifted distributions
    INTERACTIVE = "interactive"  # games, physics simulations


@dataclass(frozen=True)
class ProvenanceRecord:
    """immutable provenance for external observations."""

    source_id: str
    source_type: RealitySourceType
    domain: str  # e.g., "wine_quality", "cartpole", "weather"
    acquisition_method: str
    acquisition_timestamp: str
    data_hash: str
    schema_version: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "domain": self.domain,
            "acquisition_method": self.acquisition_method,
            "acquisition_timestamp": self.acquisition_timestamp,
            "data_hash": self.data_hash,
            "schema_version": self.schema_version,
        }


@dataclass
class ExternalObservation:
    """a single observation from external reality."""

    observation_id: str
    source_id: str
    domain: str
    metric_name: str
    value: float | int | bool | str | list | dict
    unit: str
    timestamp: str
    provenance: ProvenanceRecord
    raw_data: bytes | None = None
    metadata: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "source_id": self.source_id,
            "domain": self.domain,
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "provenance": self.provenance.to_dict(),
            "metadata": self.metadata,
        }


class RealitySource(ABC):
    """abstract base for external reality sources."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """unique identifier for this source."""
        pass

    @property
    @abstractmethod
    def source_type(self) -> RealitySourceType:
        """type of reality source."""
        pass

    @property
    @abstractmethod
    def domain(self) -> str:
        """domain name for this source."""
        pass

    @abstractmethod
    async def acquire_observations(self) -> list[ExternalObservation]:
        """fetches observations from reality. Append-only, no filtering."""
        pass

    @abstractmethod
    def get_contract(self) -> dict[str, Any]:
        """returns the domain contract for this source."""
        pass

    @abstractmethod
    def get_predictable_metrics(self) -> list[str]:
        """returns list of metric names that can be predicted."""
        pass

    def compute_hash(self, data: bytes) -> str:
        """computes SHA256 hash of data."""
        return hashlib.sha256(data).hexdigest()
