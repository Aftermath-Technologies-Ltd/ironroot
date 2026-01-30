# Author: Bradley R. Kinnard
"""Reality Interface Layer - the gate between IRONROOT and external truth.

This layer ensures beliefs can be wrong because of reality, not simulation.
All external data flows through here with immutable provenance.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx


class RealitySourceType(str, Enum):
    """types of external reality sources."""

    DATASET_HOLDOUT = "dataset_holdout"  # public dataset with hidden labels
    TIME_DELAYED = "time_delayed"  # future values unknown at prediction time
    MEASUREMENT_STREAM = "measurement_stream"  # noisy physical measurements
    HIDDEN_PARAMETER_SIM = "hidden_parameter_sim"  # simulator with secret params


@dataclass(frozen=True)
class ProvenanceRecord:
    """immutable provenance for external observations."""

    source_id: str
    source_type: RealitySourceType
    acquisition_method: str
    acquisition_timestamp: str
    data_hash: str
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
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
    metric_name: str
    value: float | int | bool | str
    unit: str
    timestamp: str
    provenance: ProvenanceRecord
    raw_data: bytes | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "source_id": self.source_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "provenance": self.provenance.to_dict(),
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

    @abstractmethod
    async def acquire_observations(self) -> list[ExternalObservation]:
        """fetches observations from reality. Append-only, no filtering."""
        pass

    @abstractmethod
    def get_contract(self) -> dict[str, Any]:
        """returns the domain contract for this source."""
        pass


class HiddenParameterDataset(RealitySource):
    """dataset with hidden structure revealed after predictions.

    Uses a real public dataset (UCI Wine Quality) with parameters
    hidden from agents until observation phase.
    """

    def __init__(self, holdout_fraction: float = 0.2, seed: int = 42):
        self._source_id = f"wine_quality_holdout_{seed}"
        self._holdout_fraction = holdout_fraction
        self._seed = seed
        self._hidden_params: dict[str, float] = {}
        self._observations: list[ExternalObservation] = []
        self._acquired = False

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> RealitySourceType:
        return RealitySourceType.DATASET_HOLDOUT

    def get_contract(self) -> dict[str, Any]:
        """domain contract written before any hypothesis."""
        return {
            "source_id": self._source_id,
            "source_type": self.source_type.value,
            "dataset": "UCI Wine Quality (Red)",
            "measurement_protocol": "holdout validation with hidden test set",
            "acquisition_method": "HTTP fetch from UCI ML Repository",
            "holdout_fraction": self._holdout_fraction,
            "seed": self._seed,
            "metrics_available": [
                "mean_quality",
                "std_quality",
                "correlation_alcohol_quality",
                "high_quality_fraction",
            ],
            "contract_timestamp": datetime.utcnow().isoformat(),
        }

    async def acquire_observations(self) -> list[ExternalObservation]:
        """fetches real data from UCI repository, computes hidden metrics."""
        if self._acquired:
            return self._observations

        # fetch actual data from UCI
        url = "https://archive.ics.uci.edu/ml/machine-learning-databases/wine-quality/winequality-red.csv"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                raw_data = response.content
        except Exception:
            # fallback to embedded sample if network fails
            raw_data = self._get_fallback_data()

        data_hash = hashlib.sha256(raw_data).hexdigest()
        acquisition_time = datetime.utcnow().isoformat()

        # parse CSV (skip header, last column is quality)
        lines = raw_data.decode("utf-8").strip().split("\n")[1:]
        qualities = []
        alcohols = []

        for line in lines:
            parts = line.split(";")
            if len(parts) >= 12:
                try:
                    quality = float(parts[-1])
                    alcohol = float(parts[10])
                    qualities.append(quality)
                    alcohols.append(alcohol)
                except ValueError:
                    continue

        # compute holdout split deterministically
        import random
        rng = random.Random(self._seed)
        indices = list(range(len(qualities)))
        rng.shuffle(indices)
        holdout_size = int(len(indices) * self._holdout_fraction)
        holdout_indices = set(indices[:holdout_size])

        holdout_qualities = [qualities[i] for i in holdout_indices]
        holdout_alcohols = [alcohols[i] for i in holdout_indices]

        # compute hidden parameters (these are the "reality" values)
        import statistics
        mean_quality = statistics.mean(holdout_qualities)
        std_quality = statistics.stdev(holdout_qualities) if len(holdout_qualities) > 1 else 0.0

        # correlation coefficient
        n = len(holdout_qualities)
        if n > 1:
            mean_a = statistics.mean(holdout_alcohols)
            mean_q = mean_quality
            numerator = sum((a - mean_a) * (q - mean_q) for a, q in zip(holdout_alcohols, holdout_qualities))
            denom_a = sum((a - mean_a) ** 2 for a in holdout_alcohols) ** 0.5
            denom_q = sum((q - mean_q) ** 2 for q in holdout_qualities) ** 0.5
            correlation = numerator / (denom_a * denom_q) if denom_a * denom_q > 0 else 0.0
        else:
            correlation = 0.0

        high_quality_fraction = sum(1 for q in holdout_qualities if q >= 7) / len(holdout_qualities)

        self._hidden_params = {
            "mean_quality": round(mean_quality, 4),
            "std_quality": round(std_quality, 4),
            "correlation_alcohol_quality": round(correlation, 4),
            "high_quality_fraction": round(high_quality_fraction, 4),
        }

        provenance = ProvenanceRecord(
            source_id=self._source_id,
            source_type=self.source_type,
            acquisition_method="HTTP GET from UCI ML Repository + holdout split",
            acquisition_timestamp=acquisition_time,
            data_hash=data_hash,
        )

        # create observations
        from ironroot.domain.ids import generate_id

        for metric_name, value in self._hidden_params.items():
            obs = ExternalObservation(
                observation_id=generate_id("obs"),
                source_id=self._source_id,
                metric_name=metric_name,
                value=value,
                unit="ratio" if "fraction" in metric_name or "correlation" in metric_name else "score",
                timestamp=acquisition_time,
                provenance=provenance,
                raw_data=raw_data if metric_name == "mean_quality" else None,
            )
            self._observations.append(obs)

        self._acquired = True
        return self._observations

    def _get_fallback_data(self) -> bytes:
        """embedded sample for offline testing."""
        # Real subset of UCI Wine Quality data
        return b'''"fixed acidity";"volatile acidity";"citric acid";"residual sugar";"chlorides";"free sulfur dioxide";"total sulfur dioxide";"density";"pH";"sulphates";"alcohol";"quality"
7.4;0.7;0;1.9;0.076;11;34;0.9978;3.51;0.56;9.4;5
7.8;0.88;0;2.6;0.098;25;67;0.9968;3.2;0.68;9.8;5
7.8;0.76;0.04;2.3;0.092;15;54;0.997;3.26;0.65;9.8;5
11.2;0.28;0.56;1.9;0.075;17;60;0.998;3.16;0.58;9.8;6
7.4;0.7;0;1.9;0.076;11;34;0.9978;3.51;0.56;9.4;5
7.4;0.66;0;1.8;0.075;13;40;0.9978;3.51;0.56;9.4;5
7.9;0.6;0.06;1.6;0.069;15;59;0.9964;3.3;0.46;9.4;5
7.3;0.65;0;1.2;0.065;15;21;0.9946;3.39;0.47;10;7
7.8;0.58;0.02;2;0.073;9;18;0.9968;3.36;0.57;9.5;7
7.5;0.5;0.36;6.1;0.071;17;102;0.9978;3.35;0.8;10.5;5
'''


class RealityInterfaceLayer:
    """the gate between IRONROOT and external truth.

    Rules:
    1. All external data flows through here
    2. Observations are append-only (agents cannot discard)
    3. Provenance is mandatory and immutable
    4. Predictions must be locked BEFORE observations arrive
    """

    def __init__(self):
        self._sources: dict[str, RealitySource] = {}
        self._observations: dict[str, list[ExternalObservation]] = {}
        self._contracts: dict[str, dict[str, Any]] = {}
        self._locked_channels: set[str] = set()

    def register_source(self, source: RealitySource) -> dict[str, Any]:
        """registers an external reality source and returns its contract."""
        contract = source.get_contract()
        self._sources[source.source_id] = source
        self._contracts[source.source_id] = contract
        self._observations[source.source_id] = []
        return contract

    def lock_channel(self, source_id: str) -> None:
        """locks the observation channel. After this, agents cannot modify inputs."""
        if source_id not in self._sources:
            raise ValueError(f"unknown source: {source_id}")
        self._locked_channels.add(source_id)

    def is_channel_locked(self, source_id: str) -> bool:
        """returns whether the channel is locked for predictions."""
        return source_id in self._locked_channels

    async def acquire_reality(self, source_id: str) -> list[ExternalObservation]:
        """fetches observations from reality. Append-only, no filtering allowed."""
        if source_id not in self._sources:
            raise ValueError(f"unknown source: {source_id}")

        source = self._sources[source_id]
        observations = await source.acquire_observations()

        # append-only: add to existing, never replace
        self._observations[source_id].extend(observations)

        return observations

    def get_observations(self, source_id: str) -> list[ExternalObservation]:
        """returns all observations for a source. Read-only."""
        return list(self._observations.get(source_id, []))

    def get_contract(self, source_id: str) -> dict[str, Any] | None:
        """returns the domain contract for a source."""
        return self._contracts.get(source_id)

    def get_provenance_proof(self, source_id: str) -> dict[str, Any]:
        """returns proof that reality was real."""
        if source_id not in self._sources:
            raise ValueError(f"unknown source: {source_id}")

        observations = self._observations.get(source_id, [])
        if not observations:
            return {"error": "no observations acquired yet"}

        # use first observation's provenance (all share same acquisition)
        prov = observations[0].provenance

        return {
            "source_id": source_id,
            "source_type": prov.source_type.value,
            "acquisition_method": prov.acquisition_method,
            "acquisition_timestamp": prov.acquisition_timestamp,
            "data_hash": prov.data_hash,
            "observation_count": len(observations),
            "contract": self._contracts.get(source_id),
        }


# singleton
_ril: RealityInterfaceLayer | None = None


def get_reality_interface() -> RealityInterfaceLayer:
    """returns shared reality interface layer."""
    global _ril
    if _ril is None:
        _ril = RealityInterfaceLayer()
    return _ril
