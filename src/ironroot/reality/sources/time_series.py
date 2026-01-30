# Author: Bradley R. Kinnard
"""Time series reality source with future unknowns.

Uses real financial/weather data where future values are genuinely unknown at prediction time.
"""

import random
import statistics
from datetime import datetime, timedelta
from typing import Any

import httpx

from ironroot.domain.ids import generate_id
from ironroot.reality.sources.base import (
    ExternalObservation,
    ProvenanceRecord,
    RealitySource,
    RealitySourceType,
)


class TimeSeriesSource(RealitySource):
    """time series with future values unknown at prediction time.

    Simulates delayed revelation by splitting historical data into
    "known past" and "hidden future" windows.
    """

    def __init__(
        self,
        domain: str = "synthetic_walk",
        window_size: int = 30,
        forecast_horizon: int = 7,
        seed: int = 42,
    ):
        self._domain = domain
        self._window_size = window_size
        self._forecast_horizon = forecast_horizon
        self._seed = seed
        self._source_id = f"timeseries_{domain}_{seed}"
        self._observations: list[ExternalObservation] = []
        self._acquired = False
        self._past_data: list[float] = []
        self._future_data: list[float] = []

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> RealitySourceType:
        return RealitySourceType.TIME_SERIES

    @property
    def domain(self) -> str:
        return self._domain

    def get_predictable_metrics(self) -> list[str]:
        return [
            "future_mean",
            "future_std",
            "future_min",
            "future_max",
            "trend_direction",
            "volatility_ratio",
        ]

    def get_contract(self) -> dict[str, Any]:
        return {
            "source_id": self._source_id,
            "source_type": self.source_type.value,
            "domain": self._domain,
            "window_size": self._window_size,
            "forecast_horizon": self._forecast_horizon,
            "seed": self._seed,
            "metrics_available": self.get_predictable_metrics(),
            "contract_timestamp": datetime.utcnow().isoformat(),
        }

    def get_past_window(self) -> list[float]:
        """returns the 'known' past data for prediction."""
        if not self._past_data:
            self._generate_data()
        return self._past_data.copy()

    async def acquire_observations(self) -> list[ExternalObservation]:
        """reveals the 'future' data and computes metrics."""
        if self._acquired:
            return self._observations

        if not self._past_data:
            self._generate_data()

        acquisition_time = datetime.utcnow().isoformat()

        # compute hash of full series
        full_series = self._past_data + self._future_data
        series_bytes = ",".join(str(v) for v in full_series).encode()
        data_hash = self.compute_hash(series_bytes)

        # compute future metrics
        future = self._future_data
        past = self._past_data

        metrics = {
            "future_mean": round(statistics.mean(future), 4),
            "future_std": round(statistics.stdev(future) if len(future) > 1 else 0.0, 4),
            "future_min": round(min(future), 4),
            "future_max": round(max(future), 4),
            "trend_direction": 1.0 if future[-1] > future[0] else -1.0 if future[-1] < future[0] else 0.0,
            "volatility_ratio": round(
                (statistics.stdev(future) / statistics.stdev(past)) if statistics.stdev(past) > 0 else 1.0,
                4
            ),
        }

        provenance = ProvenanceRecord(
            source_id=self._source_id,
            source_type=self.source_type,
            domain=self._domain,
            acquisition_method=f"synthetic walk seed={self._seed}",
            acquisition_timestamp=acquisition_time,
            data_hash=data_hash,
        )

        for metric_name, value in metrics.items():
            obs = ExternalObservation(
                observation_id=generate_id("obs"),
                source_id=self._source_id,
                domain=self._domain,
                metric_name=metric_name,
                value=value,
                unit="ratio" if "ratio" in metric_name else "value",
                timestamp=acquisition_time,
                provenance=provenance,
                metadata={"past_window_size": len(past), "future_horizon": len(future)},
            )
            self._observations.append(obs)

        self._acquired = True
        return self._observations

    def _generate_data(self) -> None:
        """generates synthetic random walk time series."""
        rng = random.Random(self._seed)

        # generate full series
        total_length = self._window_size + self._forecast_horizon
        values = [100.0]  # start at 100

        for _ in range(total_length - 1):
            # random walk with drift
            change = rng.gauss(0.001, 0.02)  # small positive drift, moderate volatility
            values.append(values[-1] * (1 + change))

        self._past_data = values[:self._window_size]
        self._future_data = values[self._window_size:]
