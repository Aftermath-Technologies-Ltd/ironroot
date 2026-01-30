# Author: Bradley R. Kinnard
"""General Intelligence Battery - external task suite for promotion anchoring.

Requirements:
- Tasks unknown at strategy creation time (held out)
- Tasks cover different domains
- Scoring is automatic and external
- Results are stored with hashes and replay logs

Promotion must be anchored to this battery - otherwise "AGI" becomes self-referential.
"""

import hashlib
import json
import random
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service


class TaskDomain(str, Enum):
    """domains covered by the battery."""

    PREDICTION = "prediction"  # forecasting future values
    REASONING = "reasoning"  # logical inference
    PLANNING = "planning"  # action sequencing
    ADAPTATION = "adaptation"  # distribution shift handling
    CALIBRATION = "calibration"  # uncertainty quantification
    TRANSFER = "transfer"  # cross-domain generalization


class TaskDifficulty(str, Enum):
    """task difficulty levels."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ADVERSARIAL = "adversarial"


@dataclass
class TaskInstance:
    """a single task instance from the battery."""

    task_id: str
    domain: TaskDomain
    difficulty: TaskDifficulty
    description: str
    input_data: dict[str, Any]
    ground_truth: Any
    input_hash: str
    ground_truth_hash: str
    held_out: bool = True  # not seen during strategy creation


@dataclass
class TaskResult:
    """result of running a task."""

    task_id: str
    prediction: Any
    score: float
    correct: bool
    latency_ms: float
    evaluated_at: str


@dataclass
class BatteryResult:
    """aggregate result from running the battery."""

    battery_id: str
    run_id: str
    strategy_id: str
    tasks_run: int
    tasks_correct: int
    overall_score: float
    score_by_domain: dict[str, float]
    score_by_difficulty: dict[str, float]
    calibration_error: float
    average_latency_ms: float
    all_results: list[TaskResult]
    input_hashes: list[str]
    ground_truth_hashes: list[str]
    evaluated_at: str


class BatteryTask(ABC):
    """abstract base for battery tasks."""

    @property
    @abstractmethod
    def domain(self) -> TaskDomain:
        pass

    @property
    @abstractmethod
    def difficulty(self) -> TaskDifficulty:
        pass

    @abstractmethod
    def generate_instance(self, seed: int) -> TaskInstance:
        """generates a task instance."""
        pass

    @abstractmethod
    def score(self, prediction: Any, ground_truth: Any) -> tuple[float, bool]:
        """scores a prediction. Returns (score, correct)."""
        pass


class PredictionTask(BatteryTask):
    """predict next value in a sequence."""

    def __init__(self, difficulty: TaskDifficulty = TaskDifficulty.MEDIUM):
        self._difficulty = difficulty

    @property
    def domain(self) -> TaskDomain:
        return TaskDomain.PREDICTION

    @property
    def difficulty(self) -> TaskDifficulty:
        return self._difficulty

    def generate_instance(self, seed: int) -> TaskInstance:
        rng = random.Random(seed)

        # generate sequence based on difficulty
        if self._difficulty == TaskDifficulty.EASY:
            # simple arithmetic sequence
            start = rng.randint(1, 10)
            step = rng.randint(1, 5)
            seq = [start + i * step for i in range(5)]
            next_val = start + 5 * step
        elif self._difficulty == TaskDifficulty.MEDIUM:
            # polynomial sequence
            a = rng.uniform(0.5, 2)
            b = rng.uniform(-1, 1)
            seq = [a * i**2 + b * i for i in range(5)]
            next_val = a * 25 + b * 5
        else:
            # noisy sequence
            base = [rng.gauss(10, 2) for _ in range(5)]
            seq = base
            next_val = sum(base) / len(base)

        input_data = {"sequence": seq, "predict": "next"}
        input_hash = hashlib.sha256(json.dumps(input_data).encode()).hexdigest()
        gt_hash = hashlib.sha256(str(next_val).encode()).hexdigest()

        return TaskInstance(
            task_id=generate_id("tsk"),
            domain=self.domain,
            difficulty=self.difficulty,
            description="Predict the next value in the sequence",
            input_data=input_data,
            ground_truth=next_val,
            input_hash=input_hash,
            ground_truth_hash=gt_hash,
        )

    def score(self, prediction: Any, ground_truth: Any) -> tuple[float, bool]:
        try:
            pred = float(prediction)
            gt = float(ground_truth)
            error = abs(pred - gt) / (abs(gt) + 1e-10)
            score = max(0, 1 - error)
            correct = error < 0.1
            return score, correct
        except (ValueError, TypeError):
            return 0.0, False


class ReasoningTask(BatteryTask):
    """logical inference task."""

    def __init__(self, difficulty: TaskDifficulty = TaskDifficulty.MEDIUM):
        self._difficulty = difficulty

    @property
    def domain(self) -> TaskDomain:
        return TaskDomain.REASONING

    @property
    def difficulty(self) -> TaskDifficulty:
        return self._difficulty

    def generate_instance(self, seed: int) -> TaskInstance:
        rng = random.Random(seed)

        # generate logical puzzle
        if self._difficulty == TaskDifficulty.EASY:
            # simple transitivity: A > B, B > C, therefore A > C
            a, b, c = rng.sample(range(10, 100), 3)
            premises = [f"X = {a}", f"Y = {b}", f"Z = {c}"]
            question = "Is X > Z?"
            answer = a > c
        else:
            # multi-step
            values = rng.sample(range(1, 50), 4)
            premises = [f"A = {values[0]}", f"B = A + {values[1]}", f"C = B * 2"]
            question = "What is C?"
            answer = (values[0] + values[1]) * 2

        input_data = {"premises": premises, "question": question}
        input_hash = hashlib.sha256(json.dumps(input_data).encode()).hexdigest()
        gt_hash = hashlib.sha256(str(answer).encode()).hexdigest()

        return TaskInstance(
            task_id=generate_id("tsk"),
            domain=self.domain,
            difficulty=self.difficulty,
            description="Answer the logical question based on premises",
            input_data=input_data,
            ground_truth=answer,
            input_hash=input_hash,
            ground_truth_hash=gt_hash,
        )

    def score(self, prediction: Any, ground_truth: Any) -> tuple[float, bool]:
        if isinstance(ground_truth, bool):
            correct = prediction == ground_truth
            return 1.0 if correct else 0.0, correct
        try:
            correct = abs(float(prediction) - float(ground_truth)) < 0.1
            return 1.0 if correct else 0.0, correct
        except (ValueError, TypeError):
            return 0.0, False


class PlanningTask(BatteryTask):
    """action sequencing to reach a goal."""

    def __init__(self, difficulty: TaskDifficulty = TaskDifficulty.MEDIUM):
        self._difficulty = difficulty

    @property
    def domain(self) -> TaskDomain:
        return TaskDomain.PLANNING

    @property
    def difficulty(self) -> TaskDifficulty:
        return self._difficulty

    def generate_instance(self, seed: int) -> TaskInstance:
        rng = random.Random(seed)

        # grid navigation
        start = (0, 0)
        if self._difficulty == TaskDifficulty.EASY:
            goal = (rng.randint(1, 3), rng.randint(1, 3))
        else:
            goal = (rng.randint(3, 5), rng.randint(3, 5))

        # optimal path length
        optimal_length = abs(goal[0] - start[0]) + abs(goal[1] - start[1])

        input_data = {"start": start, "goal": goal, "grid_size": 10}
        input_hash = hashlib.sha256(json.dumps(input_data).encode()).hexdigest()
        gt_hash = hashlib.sha256(str(optimal_length).encode()).hexdigest()

        return TaskInstance(
            task_id=generate_id("tsk"),
            domain=self.domain,
            difficulty=self.difficulty,
            description="Find the minimum number of moves to reach the goal",
            input_data=input_data,
            ground_truth=optimal_length,
            input_hash=input_hash,
            ground_truth_hash=gt_hash,
        )

    def score(self, prediction: Any, ground_truth: Any) -> tuple[float, bool]:
        try:
            pred = int(prediction)
            gt = int(ground_truth)
            if pred == gt:
                return 1.0, True
            elif pred >= gt:
                # suboptimal but valid
                return gt / pred, False
            else:
                # impossible
                return 0.0, False
        except (ValueError, TypeError):
            return 0.0, False


class CalibrationTask(BatteryTask):
    """uncertainty quantification task."""

    def __init__(self, difficulty: TaskDifficulty = TaskDifficulty.MEDIUM):
        self._difficulty = difficulty

    @property
    def domain(self) -> TaskDomain:
        return TaskDomain.CALIBRATION

    @property
    def difficulty(self) -> TaskDifficulty:
        return self._difficulty

    def generate_instance(self, seed: int) -> TaskInstance:
        rng = random.Random(seed)

        # generate data for calibration test
        true_prob = rng.uniform(0.1, 0.9)
        samples = [1 if rng.random() < true_prob else 0 for _ in range(100)]
        observed_rate = sum(samples) / len(samples)

        input_data = {"samples": samples[:20], "task": "estimate_probability"}
        input_hash = hashlib.sha256(json.dumps(input_data).encode()).hexdigest()
        gt_hash = hashlib.sha256(str(round(observed_rate, 2)).encode()).hexdigest()

        return TaskInstance(
            task_id=generate_id("tsk"),
            domain=self.domain,
            difficulty=self.difficulty,
            description="Estimate the true probability from samples",
            input_data=input_data,
            ground_truth=observed_rate,
            input_hash=input_hash,
            ground_truth_hash=gt_hash,
        )

    def score(self, prediction: Any, ground_truth: Any) -> tuple[float, bool]:
        try:
            pred = float(prediction)
            gt = float(ground_truth)
            calibration_error = abs(pred - gt)
            score = max(0, 1 - calibration_error * 2)
            correct = calibration_error < 0.1
            return score, correct
        except (ValueError, TypeError):
            return 0.0, False


class GeneralIntelligenceBattery:
    """the GI battery for external evaluation."""

    def __init__(self, seed: int = 42):
        self._seed = seed
        self._artifact_service = get_artifact_service()

        # Initialize task generators
        self._tasks: list[BatteryTask] = [
            PredictionTask(TaskDifficulty.EASY),
            PredictionTask(TaskDifficulty.MEDIUM),
            PredictionTask(TaskDifficulty.HARD),
            ReasoningTask(TaskDifficulty.EASY),
            ReasoningTask(TaskDifficulty.MEDIUM),
            ReasoningTask(TaskDifficulty.HARD),
            PlanningTask(TaskDifficulty.EASY),
            PlanningTask(TaskDifficulty.MEDIUM),
            CalibrationTask(TaskDifficulty.MEDIUM),
            CalibrationTask(TaskDifficulty.HARD),
        ]

    def generate_battery(self, num_instances_per_task: int = 5) -> list[TaskInstance]:
        """generates a held-out task battery."""
        instances = []
        rng = random.Random(self._seed)

        for task in self._tasks:
            for i in range(num_instances_per_task):
                instance_seed = rng.randint(0, 1000000)
                instance = task.generate_instance(instance_seed)
                instances.append(instance)

        # shuffle to prevent task-type clustering
        rng.shuffle(instances)
        return instances

    async def evaluate_strategy(
        self,
        session: AsyncSession,
        strategy_id: str,
        run_id: str,
        predictor: Callable[[TaskInstance], Any],
    ) -> BatteryResult:
        """evaluates a strategy against the battery.

        Args:
            session: database session
            strategy_id: ID of strategy being evaluated
            run_id: run ID for tracking
            predictor: function that takes a TaskInstance and returns a prediction
        """
        import time

        battery_id = generate_id("bat")
        instances = self.generate_battery()
        results = []

        for instance in instances:
            start_time = time.time()

            try:
                prediction = predictor(instance)
            except Exception as e:
                prediction = None

            latency_ms = (time.time() - start_time) * 1000

            # find matching task for scoring
            task = next(
                (t for t in self._tasks if t.domain == instance.domain and t.difficulty == instance.difficulty),
                self._tasks[0]
            )

            if prediction is not None:
                score, correct = task.score(prediction, instance.ground_truth)
            else:
                score, correct = 0.0, False

            results.append(TaskResult(
                task_id=instance.task_id,
                prediction=prediction,
                score=score,
                correct=correct,
                latency_ms=latency_ms,
                evaluated_at=datetime.utcnow().isoformat(),
            ))

        # compute aggregate metrics
        tasks_correct = sum(1 for r in results if r.correct)
        overall_score = statistics.mean(r.score for r in results)

        # score by domain
        score_by_domain = {}
        for domain in TaskDomain:
            domain_results = [r for r, i in zip(results, instances) if i.domain == domain]
            if domain_results:
                score_by_domain[domain.value] = statistics.mean(r.score for r in domain_results)

        # score by difficulty
        score_by_difficulty = {}
        for diff in TaskDifficulty:
            diff_results = [r for r, i in zip(results, instances) if i.difficulty == diff]
            if diff_results:
                score_by_difficulty[diff.value] = statistics.mean(r.score for r in diff_results)

        # calibration error (how well predictions match confidence)
        # simplified: use variance in scores as proxy
        calibration_error = statistics.stdev(r.score for r in results) if len(results) > 1 else 0.0

        avg_latency = statistics.mean(r.latency_ms for r in results)

        battery_result = BatteryResult(
            battery_id=battery_id,
            run_id=run_id,
            strategy_id=strategy_id,
            tasks_run=len(results),
            tasks_correct=tasks_correct,
            overall_score=overall_score,
            score_by_domain=score_by_domain,
            score_by_difficulty=score_by_difficulty,
            calibration_error=calibration_error,
            average_latency_ms=avg_latency,
            all_results=results,
            input_hashes=[i.input_hash for i in instances],
            ground_truth_hashes=[i.ground_truth_hash for i in instances],
            evaluated_at=datetime.utcnow().isoformat(),
        )

        # store battery result artifact
        await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps({
                "battery_id": battery_id,
                "run_id": run_id,
                "strategy_id": strategy_id,
                "tasks_run": len(results),
                "tasks_correct": tasks_correct,
                "overall_score": overall_score,
                "score_by_domain": score_by_domain,
                "score_by_difficulty": score_by_difficulty,
                "calibration_error": calibration_error,
                "input_hashes": battery_result.input_hashes,
                "ground_truth_hashes": battery_result.ground_truth_hashes,
            }).encode(),
            artifact_type="gi_battery_result",
            created_by="general_intelligence_battery",
            run_id=run_id,
            filename=f"gi_battery_{battery_id}.json",
        )

        return battery_result

    def get_promotion_threshold(self) -> float:
        """returns the minimum battery score required for promotion."""
        return 0.5  # 50% accuracy required

    def meets_promotion_threshold(self, result: BatteryResult) -> bool:
        """checks if a battery result meets the promotion threshold."""
        return result.overall_score >= self.get_promotion_threshold()


_battery: GeneralIntelligenceBattery | None = None


def get_gi_battery(seed: int = 42) -> GeneralIntelligenceBattery:
    """returns shared GI battery."""
    global _battery
    if _battery is None:
        _battery = GeneralIntelligenceBattery(seed)
    return _battery
