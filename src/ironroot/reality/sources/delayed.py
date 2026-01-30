# Author: Bradley R. Kinnard
"""Delayed outcome reality source.

Outcomes are revealed after a prediction window closes.
Simulates real-world scenarios like clinical trials, A/B tests, investment returns.
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


class DelayedOutcomeSource(RealitySource):
    """outcomes revealed after prediction window.

    Simulates:
    - treatment effects (revealed after follow-up period)
    - investment returns (revealed after holding period)
    - user retention (revealed after observation window)
    """

    SCENARIOS = {
        "treatment_effect": {
            "metrics": ["effect_size", "p_value", "confidence_interval_width", "responder_rate"],
            "baseline_effect": 0.0,
            "effect_std": 0.3,
        },
        "investment_return": {
            "metrics": ["total_return", "volatility", "max_drawdown", "sharpe_ratio"],
            "baseline_return": 0.07,
            "return_std": 0.15,
        },
        "user_retention": {
            "metrics": ["day_7_retention", "day_30_retention", "churn_rate", "ltv_ratio"],
            "baseline_retention": 0.4,
            "retention_std": 0.1,
        },
    }

    def __init__(
        self,
        scenario: str = "treatment_effect",
        seed: int = 42,
        sample_size: int = 100,
    ):
        if scenario not in self.SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}. Valid: {list(self.SCENARIOS.keys())}")

        self._scenario = scenario
        self._scenario_config = self.SCENARIOS[scenario]
        self._seed = seed
        self._sample_size = sample_size
        self._source_id = f"delayed_{scenario}_{seed}"
        self._observations: list[ExternalObservation] = []
        self._acquired = False
        self._baseline_data: dict[str, float] = {}
        self._outcome_data: dict[str, float] = {}

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> RealitySourceType:
        return RealitySourceType.DELAYED

    @property
    def domain(self) -> str:
        return self._scenario

    def get_predictable_metrics(self) -> list[str]:
        return self._scenario_config["metrics"]

    def get_contract(self) -> dict[str, Any]:
        return {
            "source_id": self._source_id,
            "source_type": self.source_type.value,
            "domain": self._scenario,
            "sample_size": self._sample_size,
            "seed": self._seed,
            "metrics_available": self.get_predictable_metrics(),
            "prediction_window": "before_outcome_reveal",
            "contract_timestamp": datetime.utcnow().isoformat(),
        }

    def get_baseline_data(self) -> dict[str, float]:
        """returns baseline/pre-outcome data for prediction."""
        if not self._baseline_data:
            self._generate_data()
        return self._baseline_data.copy()

    async def acquire_observations(self) -> list[ExternalObservation]:
        """reveals outcomes after prediction window."""
        if self._acquired:
            return self._observations

        if not self._outcome_data:
            self._generate_data()

        acquisition_time = datetime.utcnow().isoformat()

        # hash outcomes
        outcome_str = ",".join(f"{k}={v}" for k, v in sorted(self._outcome_data.items()))
        data_hash = self.compute_hash(outcome_str.encode())

        provenance = ProvenanceRecord(
            source_id=self._source_id,
            source_type=self.source_type,
            domain=self._scenario,
            acquisition_method=f"delayed reveal seed={self._seed}",
            acquisition_timestamp=acquisition_time,
            data_hash=data_hash,
        )

        for metric_name, value in self._outcome_data.items():
            obs = ExternalObservation(
                observation_id=generate_id("obs"),
                source_id=self._source_id,
                domain=self._scenario,
                metric_name=metric_name,
                value=round(value, 4),
                unit="outcome",
                timestamp=acquisition_time,
                provenance=provenance,
                metadata={"revealed_after": "prediction_window"},
            )
            self._observations.append(obs)

        self._acquired = True
        return self._observations

    def _generate_data(self) -> None:
        """generate baseline and outcome data."""
        rng = random.Random(self._seed)

        if self._scenario == "treatment_effect":
            # simulate clinical trial
            control = [rng.gauss(0, 1) for _ in range(self._sample_size)]
            treatment = [rng.gauss(0.3, 1) for _ in range(self._sample_size)]  # true effect = 0.3

            self._baseline_data = {
                "control_baseline_mean": round(statistics.mean(control[:20]), 4),
                "treatment_baseline_mean": round(statistics.mean(treatment[:20]), 4),
                "sample_size": self._sample_size,
            }

            # true outcomes (revealed later)
            effect = statistics.mean(treatment) - statistics.mean(control)
            pooled_std = statistics.stdev(control + treatment)
            se = pooled_std * (2 / self._sample_size) ** 0.5

            self._outcome_data = {
                "effect_size": effect,
                "p_value": 0.05 if abs(effect / se) > 1.96 else 0.2,  # simplified
                "confidence_interval_width": 1.96 * se * 2,
                "responder_rate": sum(1 for t in treatment if t > 0.5) / len(treatment),
            }

        elif self._scenario == "investment_return":
            # simulate portfolio returns
            daily_returns = [rng.gauss(0.0003, 0.01) for _ in range(252)]  # 1 year

            self._baseline_data = {
                "initial_value": 10000,
                "first_month_return": round(sum(daily_returns[:21]) * 100, 2),
                "initial_volatility": round(statistics.stdev(daily_returns[:21]) * 100, 4),
            }

            cumulative = 1.0
            peak = 1.0
            max_dd = 0.0
            for r in daily_returns:
                cumulative *= (1 + r)
                peak = max(peak, cumulative)
                dd = (peak - cumulative) / peak
                max_dd = max(max_dd, dd)

            total_return = cumulative - 1
            vol = statistics.stdev(daily_returns) * (252 ** 0.5)
            sharpe = (total_return - 0.02) / vol if vol > 0 else 0

            self._outcome_data = {
                "total_return": total_return,
                "volatility": vol,
                "max_drawdown": max_dd,
                "sharpe_ratio": sharpe,
            }

        elif self._scenario == "user_retention":
            # simulate user cohort
            users = list(range(self._sample_size))

            # retention probabilities (hidden)
            day_7_prob = 0.4 + rng.uniform(-0.1, 0.1)
            day_30_prob = 0.2 + rng.uniform(-0.05, 0.05)

            self._baseline_data = {
                "cohort_size": self._sample_size,
                "day_1_active": round(self._sample_size * 0.8),
                "acquisition_cost": round(rng.uniform(1, 5), 2),
            }

            retained_7 = sum(1 for _ in users if rng.random() < day_7_prob)
            retained_30 = sum(1 for _ in users if rng.random() < day_30_prob)

            self._outcome_data = {
                "day_7_retention": retained_7 / self._sample_size,
                "day_30_retention": retained_30 / self._sample_size,
                "churn_rate": 1 - (retained_30 / self._sample_size),
                "ltv_ratio": (retained_30 / self._sample_size) * 50 / self._baseline_data["acquisition_cost"],
            }
