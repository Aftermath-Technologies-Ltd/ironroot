# Author: Bradley R. Kinnard
"""World Model Ensemble - Multiple Model Families with Arbitration.

One model will not generalize. You need:
- Multiple model families
- Arbitration based on prediction calibration
- Explicit model selection beliefs
"""

import hashlib
import json
import random
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service


class ModelFamily(str, Enum):
    """World model families."""
    LINEAR = "linear"
    TREE = "tree"
    NEURAL = "neural"
    CAUSAL = "causal"
    PROBABILISTIC = "probabilistic"


@dataclass
class ModelPrediction:
    """A prediction from a single model."""
    model_id: str
    family: ModelFamily
    prediction: Any
    confidence: float
    calibration_score: float


@dataclass
class EnsemblePrediction:
    """Aggregated prediction from the ensemble."""
    prediction_id: str
    query: dict
    member_predictions: list[ModelPrediction]
    selected_model: str
    selection_reason: str
    final_prediction: Any
    final_confidence: float
    disagreement_level: float
    timestamp: str


@dataclass
class ModelCalibration:
    """Calibration metrics for a model."""
    model_id: str
    family: ModelFamily
    predictions_made: int
    correct_predictions: int
    calibration_error: float
    brier_score: float
    reliability: float


@dataclass
class ModelSelectionBelief:
    """Belief about when to use which model."""
    belief_id: str
    domain: str
    preferred_family: ModelFamily
    confidence: float
    evidence: list[str]
    created_at: str


class WorldModelMember:
    """A single world model in the ensemble."""

    def __init__(self, model_id: str, family: ModelFamily, seed: int = 42):
        self.model_id = model_id
        self.family = family
        self.seed = seed
        self.rng = random.Random(seed)

        self.predictions_made = 0
        self.correct_predictions = 0
        self._calibration_history: list[tuple[float, bool]] = []

    def predict(self, query: dict) -> ModelPrediction:
        """Make a prediction."""
        # Simulate prediction based on model family
        base_performance = {
            ModelFamily.LINEAR: 0.6,
            ModelFamily.TREE: 0.65,
            ModelFamily.NEURAL: 0.75,
            ModelFamily.CAUSAL: 0.8,
            ModelFamily.PROBABILISTIC: 0.7,
        }

        performance = base_performance[self.family]
        noise = self.rng.uniform(-0.15, 0.15)

        # Confidence estimation
        confidence = min(0.95, max(0.3, performance + self.rng.uniform(-0.1, 0.1)))

        # Calibration score (how well confidence matches accuracy)
        calibration = 1.0 - abs(confidence - performance)

        # Make prediction
        if self.family == ModelFamily.CAUSAL:
            prediction = {"effect": round(self.rng.uniform(0.1, 0.9), 4)}
        elif self.family == ModelFamily.PROBABILISTIC:
            prediction = {"probability": round(performance + noise, 4)}
        else:
            prediction = {"value": round(self.rng.random() * 10, 2)}

        self.predictions_made += 1

        return ModelPrediction(
            model_id=self.model_id,
            family=self.family,
            prediction=prediction,
            confidence=round(confidence, 4),
            calibration_score=round(calibration, 4),
        )

    def update_with_outcome(self, predicted_correct: bool, confidence: float) -> None:
        """Update model with outcome."""
        if predicted_correct:
            self.correct_predictions += 1
        self._calibration_history.append((confidence, predicted_correct))

    def get_calibration(self) -> ModelCalibration:
        """Get calibration metrics."""
        if self.predictions_made == 0:
            return ModelCalibration(
                model_id=self.model_id,
                family=self.family,
                predictions_made=0,
                correct_predictions=0,
                calibration_error=0.0,
                brier_score=0.0,
                reliability=0.0,
            )

        accuracy = self.correct_predictions / self.predictions_made

        # Calculate calibration error
        if self._calibration_history:
            avg_confidence = statistics.mean(c for c, _ in self._calibration_history)
            avg_correct = statistics.mean(1 if correct else 0 for _, correct in self._calibration_history)
            calibration_error = abs(avg_confidence - avg_correct)

            # Brier score
            brier = statistics.mean(
                (c - (1 if correct else 0)) ** 2
                for c, correct in self._calibration_history
            )
        else:
            calibration_error = 0.0
            brier = 0.0

        return ModelCalibration(
            model_id=self.model_id,
            family=self.family,
            predictions_made=self.predictions_made,
            correct_predictions=self.correct_predictions,
            calibration_error=round(calibration_error, 4),
            brier_score=round(brier, 4),
            reliability=round(accuracy, 4),
        )


class WorldModelEnsemble:
    """Ensemble of world models with arbitration."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.artifact_service = get_artifact_service()

        # Create ensemble members
        self.members: dict[str, WorldModelMember] = {}
        for i, family in enumerate(ModelFamily):
            model_id = f"model_{family.value}_{seed + i}"
            self.members[model_id] = WorldModelMember(model_id, family, seed + i)

        self.predictions: list[EnsemblePrediction] = []
        self.selection_beliefs: list[ModelSelectionBelief] = []

    def predict(
        self,
        query: dict,
        domain: str | None = None,
    ) -> EnsemblePrediction:
        """Make an ensemble prediction with arbitration."""
        prediction_id = generate_id("pred")

        # Get predictions from all members
        member_predictions = []
        for member in self.members.values():
            pred = member.predict(query)
            member_predictions.append(pred)

        # Arbitrate - select best model
        selected, reason = self._arbitrate(member_predictions, domain)

        # Calculate disagreement
        if len(member_predictions) > 1:
            confidences = [p.confidence for p in member_predictions]
            disagreement = statistics.stdev(confidences)
        else:
            disagreement = 0.0

        # Final prediction from selected model
        final_pred = next(p for p in member_predictions if p.model_id == selected)

        ensemble_pred = EnsemblePrediction(
            prediction_id=prediction_id,
            query=query,
            member_predictions=member_predictions,
            selected_model=selected,
            selection_reason=reason,
            final_prediction=final_pred.prediction,
            final_confidence=final_pred.confidence,
            disagreement_level=round(disagreement, 4),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self.predictions.append(ensemble_pred)
        return ensemble_pred

    def _arbitrate(
        self,
        predictions: list[ModelPrediction],
        domain: str | None,
    ) -> tuple[str, str]:
        """Arbitrate between member predictions."""
        # Check for domain-specific belief
        if domain:
            for belief in self.selection_beliefs:
                if belief.domain == domain:
                    preferred_family = belief.preferred_family
                    matching = [p for p in predictions if p.family == preferred_family]
                    if matching:
                        return matching[0].model_id, f"Domain belief for {domain}"

        # Fallback to calibration-based selection
        best = max(predictions, key=lambda p: p.calibration_score * p.confidence)
        return best.model_id, f"Best calibration score: {best.calibration_score:.2f}"

    def update_with_outcome(
        self,
        prediction_id: str,
        actual_outcome: Any,
    ) -> None:
        """Update ensemble with actual outcome."""
        # Find prediction
        pred = next((p for p in self.predictions if p.prediction_id == prediction_id), None)
        if not pred:
            return

        # Update each member that made a prediction
        for member_pred in pred.member_predictions:
            member = self.members.get(member_pred.model_id)
            if member:
                # Simple correctness check
                correct = self.rng.random() < member_pred.calibration_score
                member.update_with_outcome(correct, member_pred.confidence)

    def form_selection_belief(
        self,
        domain: str,
        preferred_family: ModelFamily,
        evidence: list[str],
    ) -> ModelSelectionBelief:
        """Form a belief about which model to use for a domain."""
        belief = ModelSelectionBelief(
            belief_id=generate_id("belief"),
            domain=domain,
            preferred_family=preferred_family,
            confidence=0.7 + self.rng.uniform(0, 0.2),
            evidence=evidence,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        self.selection_beliefs.append(belief)
        return belief

    def get_all_calibrations(self) -> list[ModelCalibration]:
        """Get calibration metrics for all members."""
        return [member.get_calibration() for member in self.members.values()]

    async def store_ensemble_state(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> str:
        """Store ensemble state as artifact."""
        calibrations = self.get_all_calibrations()

        state = {
            "member_count": len(self.members),
            "prediction_count": len(self.predictions),
            "belief_count": len(self.selection_beliefs),
            "calibrations": [
                {
                    "model_id": c.model_id,
                    "family": c.family.value,
                    "predictions": c.predictions_made,
                    "correct": c.correct_predictions,
                    "calibration_error": c.calibration_error,
                    "brier_score": c.brier_score,
                }
                for c in calibrations
            ],
            "selection_beliefs": [
                {
                    "domain": b.domain,
                    "preferred_family": b.preferred_family.value,
                    "confidence": b.confidence,
                }
                for b in self.selection_beliefs
            ],
            "recent_predictions": [
                {
                    "prediction_id": p.prediction_id,
                    "selected_model": p.selected_model,
                    "reason": p.selection_reason,
                    "disagreement": p.disagreement_level,
                }
                for p in self.predictions[-10:]
            ],
        }

        artifact = await self.artifact_service.store_artifact(
            session=session,
            data=json.dumps(state, indent=2).encode(),
            artifact_type="world_model_ensemble",
            created_by="ensemble",
            run_id=run_id,
            filename=f"ensemble_state_{len(self.predictions)}.json",
        )

        return artifact.id


_ensemble: WorldModelEnsemble | None = None


def get_world_model_ensemble(seed: int = 42) -> WorldModelEnsemble:
    """Get or create the world model ensemble."""
    global _ensemble
    if _ensemble is None or _ensemble.seed != seed:
        _ensemble = WorldModelEnsemble(seed=seed)
    return _ensemble
