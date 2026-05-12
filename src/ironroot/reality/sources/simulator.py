# Author: Bradley R. Kinnard
"""Hidden-parameter simulator reality source.

Agents observe behavior but hidden parameters are revealed only after predictions.
Classic control/physics environments with secret configurations.
"""

import math
import random
from datetime import UTC, datetime
from typing import Any

from ironroot.domain.ids import generate_id
from ironroot.reality.sources.base import (
    ExternalObservation,
    ProvenanceRecord,
    RealitySource,
    RealitySourceType,
)


class HiddenParamSimulator(RealitySource):
    """simulator with hidden parameters revealed after prediction.

    Simulates environments like:
    - pendulum with hidden mass/length
    - spring system with hidden k
    - projectile with hidden air resistance
    """

    ENVIRONMENTS = {
        "pendulum": {
            "hidden_params": ["mass", "length", "damping"],
            "observable_metrics": ["period", "max_velocity", "decay_rate", "energy_loss_ratio"],
        },
        "spring": {
            "hidden_params": ["spring_constant", "damping", "mass"],
            "observable_metrics": ["natural_frequency", "decay_time", "max_displacement"],
        },
        "projectile": {
            "hidden_params": ["drag_coefficient", "wind_speed", "initial_velocity"],
            "observable_metrics": ["max_height", "range", "flight_time", "landing_angle"],
        },
    }

    def __init__(
        self,
        environment: str = "pendulum",
        seed: int = 42,
        num_trials: int = 10,
    ):
        if environment not in self.ENVIRONMENTS:
            raise ValueError(
                f"unknown environment: {environment}. Valid: {list(self.ENVIRONMENTS.keys())}"
            )

        self._environment = environment
        self._env_config = self.ENVIRONMENTS[environment]
        self._seed = seed
        self._num_trials = num_trials
        self._source_id = f"simulator_{environment}_{seed}"
        self._observations: list[ExternalObservation] = []
        self._acquired = False
        self._hidden_params: dict[str, float] = {}
        self._trial_observations: list[dict] = []

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> RealitySourceType:
        return RealitySourceType.SIMULATOR

    @property
    def domain(self) -> str:
        return self._environment

    def get_predictable_metrics(self) -> list[str]:
        return self._env_config["observable_metrics"]

    def get_contract(self) -> dict[str, Any]:
        return {
            "source_id": self._source_id,
            "source_type": self.source_type.value,
            "domain": self._environment,
            "hidden_params": self._env_config["hidden_params"],
            "observable_metrics": self._env_config["observable_metrics"],
            "num_trials": self._num_trials,
            "seed": self._seed,
            "contract_timestamp": datetime.now(UTC).isoformat(),
        }

    def run_observable_trials(self) -> list[dict]:
        """run trials and return observable data (not hidden params)."""
        if not self._trial_observations:
            self._simulate()
        return self._trial_observations.copy()

    async def acquire_observations(self) -> list[ExternalObservation]:
        """reveals hidden parameters and computed metrics."""
        if self._acquired:
            return self._observations

        if not self._hidden_params:
            self._simulate()

        acquisition_time = datetime.now(UTC).isoformat()

        # hash the hidden params
        param_str = ",".join(f"{k}={v}" for k, v in sorted(self._hidden_params.items()))
        data_hash = self.compute_hash(param_str.encode())

        provenance = ProvenanceRecord(
            source_id=self._source_id,
            source_type=self.source_type,
            domain=self._environment,
            acquisition_method=f"physics simulation seed={self._seed}",
            acquisition_timestamp=acquisition_time,
            data_hash=data_hash,
        )

        # add hidden param observations
        for param_name, value in self._hidden_params.items():
            obs = ExternalObservation(
                observation_id=generate_id("obs"),
                source_id=self._source_id,
                domain=self._environment,
                metric_name=f"hidden_{param_name}",
                value=round(value, 4),
                unit="physics_unit",
                timestamp=acquisition_time,
                provenance=provenance,
                metadata={"revealed": True},
            )
            self._observations.append(obs)

        # add computed metric observations
        metrics = self._compute_metrics()
        for metric_name, value in metrics.items():
            obs = ExternalObservation(
                observation_id=generate_id("obs"),
                source_id=self._source_id,
                domain=self._environment,
                metric_name=metric_name,
                value=round(value, 4),
                unit="derived",
                timestamp=acquisition_time,
                provenance=provenance,
            )
            self._observations.append(obs)

        self._acquired = True
        return self._observations

    def _simulate(self) -> None:
        """run physics simulation with hidden parameters."""
        rng = random.Random(self._seed)

        if self._environment == "pendulum":
            # hidden params
            self._hidden_params = {
                "mass": rng.uniform(0.5, 2.0),  # kg
                "length": rng.uniform(0.5, 2.0),  # meters
                "damping": rng.uniform(0.01, 0.1),  # damping coefficient
            }

            # simulate trials
            for trial in range(self._num_trials):
                g = 9.81
                L = self._hidden_params["length"]
                theta0 = rng.uniform(0.1, 0.5)  # initial angle (radians)

                # small angle approximation
                period = 2 * math.pi * math.sqrt(L / g)
                max_v = theta0 * math.sqrt(g * L)

                self._trial_observations.append(
                    {
                        "trial": trial,
                        "initial_angle": theta0,
                        "observed_period": period * rng.uniform(0.98, 1.02),  # add noise
                        "observed_max_velocity": max_v * rng.uniform(0.95, 1.05),
                    }
                )

        elif self._environment == "spring":
            self._hidden_params = {
                "spring_constant": rng.uniform(10, 100),  # N/m
                "damping": rng.uniform(0.1, 1.0),
                "mass": rng.uniform(0.5, 5.0),  # kg
            }

            for trial in range(self._num_trials):
                k = self._hidden_params["spring_constant"]
                m = self._hidden_params["mass"]
                x0 = rng.uniform(0.1, 0.5)  # initial displacement

                omega = math.sqrt(k / m)

                self._trial_observations.append(
                    {
                        "trial": trial,
                        "initial_displacement": x0,
                        "observed_frequency": omega / (2 * math.pi) * rng.uniform(0.98, 1.02),
                    }
                )

        elif self._environment == "projectile":
            self._hidden_params = {
                "drag_coefficient": rng.uniform(0.1, 0.5),
                "wind_speed": rng.uniform(-5, 5),  # m/s
                "initial_velocity": rng.uniform(20, 50),  # m/s
            }

            for trial in range(self._num_trials):
                v0 = self._hidden_params["initial_velocity"]
                angle = rng.uniform(30, 60)  # degrees
                g = 9.81

                # simplified ballistics (ignoring drag for observables)
                angle_rad = math.radians(angle)
                t_flight = 2 * v0 * math.sin(angle_rad) / g
                range_m = v0 * math.cos(angle_rad) * t_flight
                max_h = (v0 * math.sin(angle_rad)) ** 2 / (2 * g)

                self._trial_observations.append(
                    {
                        "trial": trial,
                        "launch_angle": angle,
                        "observed_range": range_m * rng.uniform(0.9, 1.1),
                        "observed_max_height": max_h * rng.uniform(0.9, 1.1),
                    }
                )

    def _compute_metrics(self) -> dict[str, float]:
        """compute metrics from hidden params."""
        metrics = {}

        if self._environment == "pendulum":
            L = self._hidden_params["length"]
            g = 9.81
            metrics["period"] = 2 * math.pi * math.sqrt(L / g)
            metrics["max_velocity"] = math.sqrt(g * L) * 0.3  # typical small angle
            metrics["decay_rate"] = self._hidden_params["damping"] / self._hidden_params["mass"]
            metrics["energy_loss_ratio"] = 1 - math.exp(-2 * metrics["decay_rate"])

        elif self._environment == "spring":
            k = self._hidden_params["spring_constant"]
            m = self._hidden_params["mass"]
            b = self._hidden_params["damping"]
            omega = math.sqrt(k / m)
            metrics["natural_frequency"] = omega / (2 * math.pi)
            metrics["decay_time"] = 2 * m / b
            metrics["max_displacement"] = 0.3  # typical

        elif self._environment == "projectile":
            v0 = self._hidden_params["initial_velocity"]
            g = 9.81
            metrics["max_height"] = (v0 * 0.707) ** 2 / (2 * g)  # 45 degree
            metrics["range"] = v0**2 / g  # 45 degree, no drag
            metrics["flight_time"] = 2 * v0 * 0.707 / g
            metrics["landing_angle"] = 45.0

        return metrics
