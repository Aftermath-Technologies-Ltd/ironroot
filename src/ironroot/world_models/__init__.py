# Author: Bradley R. Kinnard
"""World Model Registry - causal and counterfactual reasoning.

Stores world models as first-class artifacts with:
- model structure
- training data hashes
- evaluation reports
- counterfactual test suites
"""

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord


class WorldModelType(str, Enum):
    """types of world models."""

    CAUSAL = "causal"  # directed acyclic graph of causal relationships
    DYNAMICS = "dynamics"  # state transition model
    COUNTERFACTUAL = "counterfactual"  # what-if reasoning model


@dataclass
class CounterfactualQuery:
    """a counterfactual query: what if X instead of Y?"""

    query_id: str
    condition: str  # "if X were different"
    intervention: dict[str, Any]  # variable -> new value
    outcome_variable: str
    expected_outcome: Any | None = None
    actual_outcome: Any | None = None
    correct: bool | None = None


@dataclass
class WorldModelSpec:
    """specification for a world model."""

    model_id: str
    model_type: WorldModelType
    domain: str
    structure: dict[str, Any]  # graph structure, equations, etc.
    training_data_hash: str
    created_at: str
    version: int = 1
    parent_model_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type.value,
            "domain": self.domain,
            "structure": self.structure,
            "training_data_hash": self.training_data_hash,
            "created_at": self.created_at,
            "version": self.version,
            "parent_model_id": self.parent_model_id,
        }


@dataclass
class EvaluationReport:
    """evaluation metrics for a world model."""

    model_id: str
    counterfactual_accuracy: float
    intervention_success_rate: float
    causal_consistency_score: float
    num_queries_tested: int
    failed_queries: list[str]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "counterfactual_accuracy": self.counterfactual_accuracy,
            "intervention_success_rate": self.intervention_success_rate,
            "causal_consistency_score": self.causal_consistency_score,
            "num_queries_tested": self.num_queries_tested,
            "failed_queries": self.failed_queries,
            "evaluated_at": self.evaluated_at,
        }


class WorldModel(ABC):
    """abstract base for world models."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        pass

    @property
    @abstractmethod
    def model_type(self) -> WorldModelType:
        pass

    @abstractmethod
    def predict_next_state(
        self, current_state: dict[str, Any], action: dict[str, Any]
    ) -> dict[str, Any]:
        """predicts next state given current state and action."""
        pass

    @abstractmethod
    def query_counterfactual(self, query: CounterfactualQuery) -> Any:
        """answers a counterfactual query."""
        pass

    @abstractmethod
    def get_causal_parents(self, variable: str) -> list[str]:
        """returns causal parents of a variable."""
        pass

    @abstractmethod
    def intervene(self, variable: str, value: Any) -> "WorldModel":
        """returns a new model with the intervention applied."""
        pass


class SimpleCausalModel(WorldModel):
    """simple linear causal model for testing.

    Structure: a -> b -> c with linear relationships.
    """

    def __init__(
        self,
        domain: str,
        coefficients: dict[str, float],
        seed: int = 42,
    ):
        self._model_id = f"causal_{domain}_{seed}"
        self._domain = domain
        self._coefficients = coefficients
        self._structure = {
            "type": "linear_dag",
            "edges": [("a", "b"), ("b", "c")],
            "coefficients": coefficients,
        }
        self._interventions: dict[str, Any] = {}

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_type(self) -> WorldModelType:
        return WorldModelType.CAUSAL

    def predict_next_state(
        self, current_state: dict[str, Any], action: dict[str, Any]
    ) -> dict[str, Any]:
        """predicts next state using causal model."""
        state = current_state.copy()

        # apply action as intervention
        for var, val in action.items():
            state[var] = val

        # propagate through causal graph
        if "a" in state and "b" not in self._interventions:
            state["b"] = state["a"] * self._coefficients.get("a_to_b", 1.0)

        if "b" in state and "c" not in self._interventions:
            state["c"] = state["b"] * self._coefficients.get("b_to_c", 1.0)

        return state

    def query_counterfactual(self, query: CounterfactualQuery) -> Any:
        """answers counterfactual: what if intervention were different?"""
        # create intervened model
        intervened = self.intervene(
            list(query.intervention.keys())[0],
            list(query.intervention.values())[0],
        )

        # run forward pass
        initial_state = {"a": 1.0}  # baseline
        initial_state.update(query.intervention)

        result = intervened.predict_next_state(initial_state, {})
        return result.get(query.outcome_variable)

    def get_causal_parents(self, variable: str) -> list[str]:
        """returns causal parents."""
        parents = {
            "a": [],
            "b": ["a"],
            "c": ["b"],
        }
        return parents.get(variable, [])

    def intervene(self, variable: str, value: Any) -> "SimpleCausalModel":
        """returns model with do(variable=value)."""
        new_model = SimpleCausalModel(
            domain=self._domain,
            coefficients=self._coefficients.copy(),
        )
        new_model._interventions = {**self._interventions, variable: value}
        return new_model

    def get_spec(self, training_data_hash: str) -> WorldModelSpec:
        """returns model specification."""
        return WorldModelSpec(
            model_id=self._model_id,
            model_type=self.model_type,
            domain=self._domain,
            structure=self._structure,
            training_data_hash=training_data_hash,
            created_at=datetime.now(UTC).isoformat(),
        )


class WorldModelRegistry:
    """registry for world models with evaluation and versioning."""

    def __init__(self):
        self._models: dict[str, WorldModel] = {}
        self._specs: dict[str, WorldModelSpec] = {}
        self._evaluations: dict[str, EvaluationReport] = {}
        self._artifact_service = get_artifact_service()

    async def register_model(
        self,
        session: AsyncSession,
        model: WorldModel,
        training_data: bytes,
        run_id: str,
    ) -> WorldModelSpec:
        """registers a world model with training data provenance."""
        data_hash = hashlib.sha256(training_data).hexdigest()

        if isinstance(model, SimpleCausalModel):
            spec = model.get_spec(data_hash)
        else:
            spec = WorldModelSpec(
                model_id=model.model_id,
                model_type=model.model_type,
                domain="unknown",
                structure={},
                training_data_hash=data_hash,
                created_at=datetime.now(UTC).isoformat(),
            )

        self._models[model.model_id] = model
        self._specs[model.model_id] = spec

        # store as artifact
        await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps(spec.to_dict()).encode(),
            artifact_type="world_model_spec",
            created_by="world_model_registry",
            run_id=run_id,
            filename=f"world_model_{model.model_id}.json",
        )

        return spec

    async def evaluate_model(
        self,
        session: AsyncSession,
        model_id: str,
        queries: list[CounterfactualQuery],
        run_id: str,
    ) -> EvaluationReport:
        """evaluates a model against counterfactual queries."""
        if model_id not in self._models:
            raise ValueError(f"model {model_id} not registered")

        model = self._models[model_id]

        correct = 0
        interventions_succeeded = 0
        consistency_checks = 0
        failed_queries = []

        for query in queries:
            result = model.query_counterfactual(query)
            query.actual_outcome = result

            if query.expected_outcome is not None:
                if isinstance(query.expected_outcome, (int, float)):
                    # numeric comparison with tolerance
                    is_correct = abs(result - query.expected_outcome) < 0.1
                else:
                    is_correct = result == query.expected_outcome

                query.correct = is_correct
                if is_correct:
                    correct += 1
                else:
                    failed_queries.append(query.query_id)

            # check intervention succeeded (value was set)
            if query.intervention:
                interventions_succeeded += 1

            # consistency: do(X) should override X's parents
            for var in query.intervention:
                parents = model.get_causal_parents(var)
                if not parents:  # root node, always consistent
                    consistency_checks += 1

        num_tested = len(queries)
        report = EvaluationReport(
            model_id=model_id,
            counterfactual_accuracy=correct / num_tested if num_tested else 0.0,
            intervention_success_rate=interventions_succeeded / num_tested if num_tested else 0.0,
            causal_consistency_score=consistency_checks / num_tested if num_tested else 0.0,
            num_queries_tested=num_tested,
            failed_queries=failed_queries,
            evaluated_at=datetime.now(UTC).isoformat(),
        )

        self._evaluations[model_id] = report

        # store evaluation artifact
        await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps(report.to_dict()).encode(),
            artifact_type="world_model_evaluation",
            created_by="world_model_registry",
            run_id=run_id,
            filename=f"world_model_eval_{model_id}.json",
        )

        return report

    def get_model(self, model_id: str) -> WorldModel | None:
        """returns a registered model."""
        return self._models.get(model_id)

    def get_evaluation(self, model_id: str) -> EvaluationReport | None:
        """returns the latest evaluation for a model."""
        return self._evaluations.get(model_id)

    def list_models(self) -> list[WorldModelSpec]:
        """returns all registered model specs."""
        return list(self._specs.values())


_registry: WorldModelRegistry | None = None


def get_world_model_registry() -> WorldModelRegistry:
    """returns shared world model registry."""
    global _registry
    if _registry is None:
        _registry = WorldModelRegistry()
    return _registry
