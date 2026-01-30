# Author: Bradley R. Kinnard
"""Adversarial reality source.

Poisoned or shifted distributions that test robustness.
"""

import random
import statistics
from datetime import datetime
from typing import Any

from ironroot.domain.ids import generate_id
from ironroot.reality.sources.base import (
    ExternalObservation,
    ProvenanceRecord,
    RealitySource,
    RealitySourceType,
)


class AdversarialSource(RealitySource):
    """adversarial data source with distribution shifts and poisoning.

    Tests:
    - covariate shift (input distribution changes)
    - label noise (some labels are wrong)
    - concept drift (relationship changes over time)
    - adversarial examples (worst-case inputs)
    """

    ATTACK_TYPES = {
        "covariate_shift": {
            "metrics": ["shift_magnitude", "accuracy_drop", "calibration_error", "ood_detection_rate"],
            "description": "Input distribution shifts between train and test",
        },
        "label_noise": {
            "metrics": ["noise_rate", "accuracy_on_clean", "accuracy_on_noisy", "noise_detection_rate"],
            "description": "Some labels are corrupted",
        },
        "concept_drift": {
            "metrics": ["drift_magnitude", "adaptation_speed", "performance_degradation", "detection_delay"],
            "description": "True relationship changes over time",
        },
    }

    def __init__(
        self,
        attack_type: str = "covariate_shift",
        severity: float = 0.3,
        seed: int = 42,
        sample_size: int = 200,
    ):
        if attack_type not in self.ATTACK_TYPES:
            raise ValueError(f"unknown attack: {attack_type}. Valid: {list(self.ATTACK_TYPES.keys())}")

        self._attack_type = attack_type
        self._attack_config = self.ATTACK_TYPES[attack_type]
        self._severity = severity
        self._seed = seed
        self._sample_size = sample_size
        self._source_id = f"adversarial_{attack_type}_{seed}"
        self._observations: list[ExternalObservation] = []
        self._acquired = False
        self._clean_data: list[dict] = []
        self._adversarial_data: list[dict] = []
        self._computed_metrics: dict[str, float] = {}

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> RealitySourceType:
        return RealitySourceType.ADVERSARIAL

    @property
    def domain(self) -> str:
        return self._attack_type

    def get_predictable_metrics(self) -> list[str]:
        return self._attack_config["metrics"]

    def get_contract(self) -> dict[str, Any]:
        return {
            "source_id": self._source_id,
            "source_type": self.source_type.value,
            "domain": self._attack_type,
            "attack_description": self._attack_config["description"],
            "severity": self._severity,
            "seed": self._seed,
            "sample_size": self._sample_size,
            "metrics_available": self.get_predictable_metrics(),
            "contract_timestamp": datetime.utcnow().isoformat(),
        }

    def get_clean_data(self) -> list[dict]:
        """returns clean (non-adversarial) data for training/calibration."""
        if not self._clean_data:
            self._generate_data()
        return self._clean_data.copy()

    def get_adversarial_data(self) -> list[dict]:
        """returns adversarial test data."""
        if not self._adversarial_data:
            self._generate_data()
        return self._adversarial_data.copy()

    async def acquire_observations(self) -> list[ExternalObservation]:
        """reveals adversarial metrics."""
        if self._acquired:
            return self._observations

        if not self._computed_metrics:
            self._generate_data()

        acquisition_time = datetime.utcnow().isoformat()

        # hash the adversarial setup
        setup_str = f"{self._attack_type}_{self._severity}_{self._seed}"
        data_hash = self.compute_hash(setup_str.encode())

        provenance = ProvenanceRecord(
            source_id=self._source_id,
            source_type=self.source_type,
            domain=self._attack_type,
            acquisition_method=f"adversarial generation severity={self._severity}",
            acquisition_timestamp=acquisition_time,
            data_hash=data_hash,
        )

        for metric_name, value in self._computed_metrics.items():
            obs = ExternalObservation(
                observation_id=generate_id("obs"),
                source_id=self._source_id,
                domain=self._attack_type,
                metric_name=metric_name,
                value=round(value, 4),
                unit="ratio",
                timestamp=acquisition_time,
                provenance=provenance,
                metadata={"attack_severity": self._severity},
            )
            self._observations.append(obs)

        self._acquired = True
        return self._observations

    def _generate_data(self) -> None:
        """generate clean and adversarial data."""
        rng = random.Random(self._seed)

        if self._attack_type == "covariate_shift":
            # generate clean data from N(0, 1)
            self._clean_data = [
                {"x": rng.gauss(0, 1), "y": 1 if rng.gauss(0, 1) > 0 else 0}
                for _ in range(self._sample_size)
            ]

            # shifted data from N(shift, 1)
            shift = self._severity * 3  # shift in standard deviations
            self._adversarial_data = [
                {"x": rng.gauss(shift, 1), "y": 1 if rng.gauss(0, 1) > 0 else 0}
                for _ in range(self._sample_size)
            ]

            # compute metrics
            clean_mean = statistics.mean(d["x"] for d in self._clean_data)
            adv_mean = statistics.mean(d["x"] for d in self._adversarial_data)

            self._computed_metrics = {
                "shift_magnitude": abs(adv_mean - clean_mean),
                "accuracy_drop": self._severity * 0.3,  # simulated
                "calibration_error": self._severity * 0.2,
                "ood_detection_rate": 1.0 - self._severity,  # harder to detect at high severity
            }

        elif self._attack_type == "label_noise":
            # generate clean data
            self._clean_data = [
                {"x": rng.gauss(0, 1), "y": 1 if rng.gauss(0, 1) > 0 else 0}
                for _ in range(self._sample_size)
            ]

            # add label noise
            self._adversarial_data = []
            noisy_count = 0
            for d in self._clean_data:
                if rng.random() < self._severity:
                    # flip label
                    self._adversarial_data.append({"x": d["x"], "y": 1 - d["y"], "noisy": True})
                    noisy_count += 1
                else:
                    self._adversarial_data.append({"x": d["x"], "y": d["y"], "noisy": False})

            self._computed_metrics = {
                "noise_rate": noisy_count / self._sample_size,
                "accuracy_on_clean": 0.85,  # baseline
                "accuracy_on_noisy": 0.85 - self._severity * 0.4,
                "noise_detection_rate": 0.6,  # how well can noise be detected
            }

        elif self._attack_type == "concept_drift":
            # generate data where relationship changes
            self._clean_data = [
                {"x": rng.gauss(0, 1), "y": 1 if rng.gauss(0, 1) > 0 else 0, "t": i}
                for i in range(self._sample_size)
            ]

            # drift: after midpoint, relationship inverts partially
            midpoint = self._sample_size // 2
            self._adversarial_data = []
            for i, d in enumerate(self._clean_data):
                if i >= midpoint:
                    # apply concept drift
                    if rng.random() < self._severity:
                        self._adversarial_data.append({"x": d["x"], "y": 1 - d["y"], "t": i, "drifted": True})
                    else:
                        self._adversarial_data.append({**d, "drifted": False})
                else:
                    self._adversarial_data.append({**d, "drifted": False})

            drifted_count = sum(1 for d in self._adversarial_data if d.get("drifted"))

            self._computed_metrics = {
                "drift_magnitude": self._severity,
                "adaptation_speed": 10 + self._severity * 20,  # samples needed to adapt
                "performance_degradation": self._severity * 0.35,
                "detection_delay": 5 + self._severity * 15,  # samples until drift detected
            }
