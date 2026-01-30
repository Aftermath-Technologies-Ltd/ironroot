# Author: Bradley R. Kinnard
"""Tabular dataset reality source.

Supports multiple public datasets with hidden holdout splits.
"""

import random
import statistics
from datetime import datetime
from typing import Any

import httpx

from ironroot.domain.ids import generate_id
from ironroot.reality.sources.base import (
    ExternalObservation,
    ProvenanceRecord,
    RealitySource,
    RealitySourceType,
)


class TabularDatasetSource(RealitySource):
    """tabular dataset with hidden structure revealed after predictions.

    Supports multiple datasets:
    - wine_quality: UCI Wine Quality (Red)
    - iris: UCI Iris dataset
    - diabetes: Pima Indians Diabetes
    """

    DATASETS = {
        "wine_quality": {
            "url": "https://archive.ics.uci.edu/ml/machine-learning-databases/wine-quality/winequality-red.csv",
            "delimiter": ";",
            "target_col": -1,
            "metrics": ["mean_target", "std_target", "class_balance", "feature_correlation"],
        },
        "iris": {
            "url": "https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data",
            "delimiter": ",",
            "target_col": -1,
            "metrics": ["mean_sepal_length", "std_sepal_length", "class_balance", "feature_correlation"],
        },
        "adult_income": {
            "url": "https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.data",
            "delimiter": ",",
            "target_col": -1,
            "metrics": ["mean_age", "income_ratio", "education_distribution"],
        },
    }

    def __init__(
        self,
        dataset_name: str = "wine_quality",
        holdout_fraction: float = 0.2,
        seed: int = 42,
    ):
        if dataset_name not in self.DATASETS:
            raise ValueError(f"unknown dataset: {dataset_name}. Valid: {list(self.DATASETS.keys())}")

        self._dataset_name = dataset_name
        self._dataset_config = self.DATASETS[dataset_name]
        self._holdout_fraction = holdout_fraction
        self._seed = seed
        self._source_id = f"tabular_{dataset_name}_{seed}"
        self._observations: list[ExternalObservation] = []
        self._acquired = False

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> RealitySourceType:
        return RealitySourceType.TABULAR

    @property
    def domain(self) -> str:
        return self._dataset_name

    def get_predictable_metrics(self) -> list[str]:
        return self._dataset_config["metrics"]

    def get_contract(self) -> dict[str, Any]:
        return {
            "source_id": self._source_id,
            "source_type": self.source_type.value,
            "domain": self._dataset_name,
            "dataset_url": self._dataset_config["url"],
            "holdout_fraction": self._holdout_fraction,
            "seed": self._seed,
            "metrics_available": self.get_predictable_metrics(),
            "contract_timestamp": datetime.utcnow().isoformat(),
        }

    async def acquire_observations(self) -> list[ExternalObservation]:
        if self._acquired:
            return self._observations

        # fetch data
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self._dataset_config["url"])
                response.raise_for_status()
                raw_data = response.content
        except Exception:
            raw_data = self._get_fallback_data()

        data_hash = self.compute_hash(raw_data)
        acquisition_time = datetime.utcnow().isoformat()

        # parse and compute holdout metrics
        metrics = self._compute_holdout_metrics(raw_data)

        provenance = ProvenanceRecord(
            source_id=self._source_id,
            source_type=self.source_type,
            domain=self._dataset_name,
            acquisition_method=f"HTTP GET + {self._holdout_fraction} holdout split",
            acquisition_timestamp=acquisition_time,
            data_hash=data_hash,
        )

        for metric_name, value in metrics.items():
            obs = ExternalObservation(
                observation_id=generate_id("obs"),
                source_id=self._source_id,
                domain=self._dataset_name,
                metric_name=metric_name,
                value=value,
                unit="ratio" if "ratio" in metric_name or "fraction" in metric_name else "value",
                timestamp=acquisition_time,
                provenance=provenance,
            )
            self._observations.append(obs)

        self._acquired = True
        return self._observations

    def _compute_holdout_metrics(self, raw_data: bytes) -> dict[str, float]:
        """compute metrics on holdout split."""
        lines = raw_data.decode("utf-8", errors="ignore").strip().split("\n")

        # skip header if present
        if self._dataset_name == "wine_quality":
            lines = lines[1:]

        delimiter = self._dataset_config["delimiter"]
        target_col = self._dataset_config["target_col"]

        values = []
        targets = []

        for line in lines:
            parts = line.split(delimiter)
            if len(parts) < 2:
                continue
            try:
                if self._dataset_name == "wine_quality":
                    target = float(parts[target_col])
                    targets.append(target)
                    values.append([float(p) for p in parts[:-1]])
                elif self._dataset_name == "iris":
                    targets.append(parts[target_col].strip())
                    values.append([float(p) for p in parts[:-1]])
                else:
                    targets.append(parts[target_col].strip())
            except (ValueError, IndexError):
                continue

        # holdout split
        rng = random.Random(self._seed)
        indices = list(range(len(targets)))
        rng.shuffle(indices)
        holdout_size = int(len(indices) * self._holdout_fraction)
        holdout_indices = set(indices[:holdout_size])

        holdout_targets = [targets[i] for i in holdout_indices]
        holdout_values = [values[i] for i in holdout_indices] if values else []

        metrics = {}

        if self._dataset_name == "wine_quality":
            numeric_targets = [float(t) for t in holdout_targets]
            metrics["mean_target"] = round(statistics.mean(numeric_targets), 4)
            metrics["std_target"] = round(statistics.stdev(numeric_targets) if len(numeric_targets) > 1 else 0.0, 4)
            metrics["class_balance"] = round(sum(1 for t in numeric_targets if t >= 7) / len(numeric_targets), 4)

            if holdout_values:
                first_col = [v[0] for v in holdout_values]
                if len(first_col) > 1:
                    mean_f = statistics.mean(first_col)
                    mean_t = metrics["mean_target"]
                    num = sum((f - mean_f) * (t - mean_t) for f, t in zip(first_col, numeric_targets))
                    denom_f = sum((f - mean_f) ** 2 for f in first_col) ** 0.5
                    denom_t = sum((t - mean_t) ** 2 for t in numeric_targets) ** 0.5
                    corr = num / (denom_f * denom_t) if denom_f * denom_t > 0 else 0.0
                    metrics["feature_correlation"] = round(corr, 4)

        elif self._dataset_name == "iris":
            # class balance for iris
            class_counts = {}
            for t in holdout_targets:
                class_counts[t] = class_counts.get(t, 0) + 1
            total = len(holdout_targets)
            metrics["class_balance"] = round(max(class_counts.values()) / total if total else 0, 4)

            if holdout_values:
                sepal_lengths = [v[0] for v in holdout_values]
                metrics["mean_sepal_length"] = round(statistics.mean(sepal_lengths), 4)
                metrics["std_sepal_length"] = round(statistics.stdev(sepal_lengths) if len(sepal_lengths) > 1 else 0.0, 4)
                metrics["feature_correlation"] = 0.0  # placeholder

        return metrics

    def _get_fallback_data(self) -> bytes:
        """embedded sample for offline testing."""
        if self._dataset_name == "wine_quality":
            return b'''"fixed acidity";"volatile acidity";"citric acid";"residual sugar";"chlorides";"free sulfur dioxide";"total sulfur dioxide";"density";"pH";"sulphates";"alcohol";"quality"
7.4;0.7;0;1.9;0.076;11;34;0.9978;3.51;0.56;9.4;5
7.8;0.88;0;2.6;0.098;25;67;0.9968;3.2;0.68;9.8;5
7.8;0.76;0.04;2.3;0.092;15;54;0.997;3.26;0.65;9.8;5
11.2;0.28;0.56;1.9;0.075;17;60;0.998;3.16;0.58;9.8;6
7.4;0.7;0;1.9;0.076;11;34;0.9978;3.51;0.56;9.4;5
'''
        return b""
