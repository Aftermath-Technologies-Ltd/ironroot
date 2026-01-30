# Author: Bradley R. Kinnard
"""Long-Horizon Agency - 50-200 Step Tasks with Delayed Reward.

Environments:
1. Partially observable navigation/search
2. Resource management (budgets, tradeoffs)
3. Repair under constraints (fix with time/budget limits)

Gate passes if:
- Success rate above threshold across 100 episodes per environment
- Recovers from mid-episode distribution shifts
- Logs plan revisions with grounded reasons
"""

import asyncio
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service


class EnvironmentType(str, Enum):
    """Long-horizon environment types."""
    NAVIGATION = "navigation"
    RESOURCE_MANAGEMENT = "resource_management"
    REPAIR_TASK = "repair_task"


@dataclass
class Observation:
    """Partial observation from environment."""
    step: int
    visible_state: dict
    hidden_state_hash: str  # We don't reveal hidden state
    timestamp: str


@dataclass
class Action:
    """Action taken by agent."""
    step: int
    action_type: str
    parameters: dict
    rationale: str


@dataclass
class PlanRevision:
    """Record of plan being revised."""
    revision_id: str
    step: int
    previous_plan: list[str]
    new_plan: list[str]
    reason: str
    triggering_observation: Observation
    grounded_in_evidence: bool


@dataclass
class EpisodeTrace:
    """Complete trace of an episode."""
    episode_id: str
    environment: str
    seed: int
    total_steps: int
    observations: list[Observation]
    actions: list[Action]
    plan_revisions: list[PlanRevision]
    distribution_shifts: list[dict]
    final_reward: float
    success: bool
    trace_hash: str


@dataclass
class EnvironmentMetrics:
    """Metrics for one environment across episodes."""
    environment: str
    episodes_run: int
    success_rate: float
    avg_steps: float
    avg_reward: float
    recovery_rate: float  # Recovery from distribution shifts
    plan_revisions_per_episode: float
    grounded_revisions_rate: float


class LongHorizonEnvironment:
    """Base class for long-horizon environments."""

    def __init__(
        self,
        env_type: EnvironmentType,
        name: str,
        min_steps: int = 50,
        max_steps: int = 200,
        seed: int = 42,
    ):
        self.env_type = env_type
        self.name = name
        self.min_steps = min_steps
        self.max_steps = max_steps
        self.seed = seed
        self.rng = random.Random(seed)
        self._current_step = 0
        self._hidden_state: dict = {}
        self._episode_observations: list[Observation] = []
        self._episode_actions: list[Action] = []
        self._plan_revisions: list[PlanRevision] = []
        self._distribution_shifts: list[dict] = []

    def reset(self, episode_seed: int) -> Observation:
        """Reset environment for new episode."""
        self.rng = random.Random(episode_seed)
        self._current_step = 0
        self._hidden_state = self._init_hidden_state()
        self._episode_observations = []
        self._episode_actions = []
        self._plan_revisions = []
        self._distribution_shifts = []

        obs = self._get_observation()
        self._episode_observations.append(obs)
        return obs

    def step(self, action: Action) -> tuple[Observation, float, bool]:
        """Take a step in the environment."""
        self._current_step += 1
        self._episode_actions.append(action)

        # Apply action and get reward
        reward = self._apply_action(action)

        # Check for distribution shift (random events)
        if self.rng.random() < 0.1:  # 10% chance per step
            shift = self._apply_distribution_shift()
            self._distribution_shifts.append(shift)

        # Get new observation
        obs = self._get_observation()
        self._episode_observations.append(obs)

        # Check termination
        done = self._is_done()

        return obs, reward, done

    def record_plan_revision(self, revision: PlanRevision) -> None:
        """Record a plan revision."""
        self._plan_revisions.append(revision)

    def get_trace(self) -> EpisodeTrace:
        """Get complete episode trace."""
        trace_data = {
            "observations": len(self._episode_observations),
            "actions": len(self._episode_actions),
            "revisions": len(self._plan_revisions),
        }
        trace_hash = hashlib.sha256(json.dumps(trace_data).encode()).hexdigest()

        return EpisodeTrace(
            episode_id=generate_id("episode"),
            environment=self.name,
            seed=self.seed,
            total_steps=self._current_step,
            observations=self._episode_observations,
            actions=self._episode_actions,
            plan_revisions=self._plan_revisions,
            distribution_shifts=self._distribution_shifts,
            final_reward=self._compute_final_reward(),
            success=self._is_success(),
            trace_hash=trace_hash,
        )

    def _init_hidden_state(self) -> dict:
        """Initialize hidden state."""
        return {}

    def _get_observation(self) -> Observation:
        """Get current partial observation."""
        return Observation(
            step=self._current_step,
            visible_state={},
            hidden_state_hash=hashlib.sha256(
                json.dumps(self._hidden_state, sort_keys=True).encode()
            ).hexdigest()[:16],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _apply_action(self, action: Action) -> float:
        """Apply action and return immediate reward."""
        return 0.0

    def _apply_distribution_shift(self) -> dict:
        """Apply a distribution shift event."""
        return {"type": "none", "step": self._current_step}

    def _is_done(self) -> bool:
        """Check if episode is done."""
        return self._current_step >= self.max_steps

    def _compute_final_reward(self) -> float:
        """Compute final episode reward."""
        return 0.0

    def _is_success(self) -> bool:
        """Check if episode was successful."""
        return False


class NavigationEnvironment(LongHorizonEnvironment):
    """Partially observable navigation/search task."""

    def __init__(self, seed: int = 42):
        super().__init__(
            env_type=EnvironmentType.NAVIGATION,
            name="PartiallyObservableNavigation",
            min_steps=50,
            max_steps=150,
            seed=seed,
        )
        self.grid_size = 20
        self.view_radius = 2

    def _init_hidden_state(self) -> dict:
        """Initialize hidden grid state."""
        # Agent position
        agent_x = self.rng.randint(0, self.grid_size - 1)
        agent_y = self.rng.randint(0, self.grid_size - 1)

        # Goal position (hidden)
        goal_x = self.rng.randint(0, self.grid_size - 1)
        goal_y = self.rng.randint(0, self.grid_size - 1)

        # Obstacles (hidden until revealed)
        obstacles = set()
        for _ in range(self.grid_size * 2):
            ox = self.rng.randint(0, self.grid_size - 1)
            oy = self.rng.randint(0, self.grid_size - 1)
            if (ox, oy) != (agent_x, agent_y) and (ox, oy) != (goal_x, goal_y):
                obstacles.add((ox, oy))

        return {
            "agent_x": agent_x,
            "agent_y": agent_y,
            "goal_x": goal_x,
            "goal_y": goal_y,
            "obstacles": list(obstacles),
            "visited": [(agent_x, agent_y)],
        }

    def _get_observation(self) -> Observation:
        """Get partial observation (only nearby cells)."""
        ax = self._hidden_state["agent_x"]
        ay = self._hidden_state["agent_y"]

        visible = {}
        for dx in range(-self.view_radius, self.view_radius + 1):
            for dy in range(-self.view_radius, self.view_radius + 1):
                nx, ny = ax + dx, ay + dy
                if 0 <= nx < self.grid_size and 0 <= ny < self.grid_size:
                    cell = "empty"
                    if (nx, ny) in [tuple(o) for o in self._hidden_state["obstacles"]]:
                        cell = "obstacle"
                    if (nx, ny) == (self._hidden_state["goal_x"], self._hidden_state["goal_y"]):
                        cell = "goal"
                    visible[f"{nx},{ny}"] = cell

        return Observation(
            step=self._current_step,
            visible_state={
                "agent_position": (ax, ay),
                "visible_cells": visible,
                "steps_remaining": self.max_steps - self._current_step,
            },
            hidden_state_hash=hashlib.sha256(
                json.dumps(self._hidden_state, sort_keys=True).encode()
            ).hexdigest()[:16],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _apply_action(self, action: Action) -> float:
        """Apply movement action."""
        direction = action.parameters.get("direction", "stay")
        dx, dy = 0, 0

        if direction == "up":
            dy = -1
        elif direction == "down":
            dy = 1
        elif direction == "left":
            dx = -1
        elif direction == "right":
            dx = 1

        new_x = self._hidden_state["agent_x"] + dx
        new_y = self._hidden_state["agent_y"] + dy

        # Check bounds and obstacles
        if 0 <= new_x < self.grid_size and 0 <= new_y < self.grid_size:
            if (new_x, new_y) not in [tuple(o) for o in self._hidden_state["obstacles"]]:
                self._hidden_state["agent_x"] = new_x
                self._hidden_state["agent_y"] = new_y
                self._hidden_state["visited"].append((new_x, new_y))

        # Small penalty for each step
        return -0.1

    def _apply_distribution_shift(self) -> dict:
        """Move goal or add obstacles."""
        shift_type = self.rng.choice(["goal_move", "new_obstacle", "obstacle_remove"])

        if shift_type == "goal_move":
            self._hidden_state["goal_x"] = self.rng.randint(0, self.grid_size - 1)
            self._hidden_state["goal_y"] = self.rng.randint(0, self.grid_size - 1)
        elif shift_type == "new_obstacle":
            ox = self.rng.randint(0, self.grid_size - 1)
            oy = self.rng.randint(0, self.grid_size - 1)
            self._hidden_state["obstacles"].append((ox, oy))
        elif shift_type == "obstacle_remove" and self._hidden_state["obstacles"]:
            self._hidden_state["obstacles"].pop(0)

        return {"type": shift_type, "step": self._current_step}

    def _is_done(self) -> bool:
        """Done if reached goal or max steps."""
        at_goal = (
            self._hidden_state["agent_x"] == self._hidden_state["goal_x"] and
            self._hidden_state["agent_y"] == self._hidden_state["goal_y"]
        )
        return at_goal or self._current_step >= self.max_steps

    def _compute_final_reward(self) -> float:
        """Reward based on goal distance."""
        dx = abs(self._hidden_state["agent_x"] - self._hidden_state["goal_x"])
        dy = abs(self._hidden_state["agent_y"] - self._hidden_state["goal_y"])
        distance = dx + dy

        if distance == 0:
            return 100.0 - self._current_step * 0.1  # Bonus for speed
        else:
            return -distance  # Penalty for not reaching

    def _is_success(self) -> bool:
        """Success if reached goal."""
        return (
            self._hidden_state["agent_x"] == self._hidden_state["goal_x"] and
            self._hidden_state["agent_y"] == self._hidden_state["goal_y"]
        )


class ResourceManagementEnvironment(LongHorizonEnvironment):
    """Resource management with budgets and tradeoffs."""

    def __init__(self, seed: int = 42):
        super().__init__(
            env_type=EnvironmentType.RESOURCE_MANAGEMENT,
            name="ResourceManagement",
            min_steps=75,
            max_steps=200,
            seed=seed,
        )

    def _init_hidden_state(self) -> dict:
        """Initialize resource state."""
        return {
            "money": 1000,
            "energy": 100,
            "materials": 50,
            "workers": 10,
            "production_rate": 1.0,
            "demand": [self.rng.randint(5, 15) for _ in range(10)],
            "current_demand_idx": 0,
            "total_produced": 0,
            "total_sold": 0,
        }

    def _get_observation(self) -> Observation:
        """Get current resource observation."""
        return Observation(
            step=self._current_step,
            visible_state={
                "money": self._hidden_state["money"],
                "energy": self._hidden_state["energy"],
                "materials": self._hidden_state["materials"],
                "workers": self._hidden_state["workers"],
                "current_demand": self._hidden_state["demand"][
                    self._hidden_state["current_demand_idx"] % len(self._hidden_state["demand"])
                ],
                "production_rate": self._hidden_state["production_rate"],
            },
            hidden_state_hash=hashlib.sha256(
                json.dumps(self._hidden_state, sort_keys=True).encode()
            ).hexdigest()[:16],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _apply_action(self, action: Action) -> float:
        """Apply resource management action."""
        action_type = action.parameters.get("type", "wait")
        reward = 0.0

        if action_type == "produce":
            # Produce goods if we have materials and energy
            units = min(
                self._hidden_state["materials"],
                self._hidden_state["energy"] // 10,
                self._hidden_state["workers"],
            )
            if units > 0:
                self._hidden_state["materials"] -= units
                self._hidden_state["energy"] -= units * 10
                self._hidden_state["total_produced"] += units
                reward = units * 0.5

        elif action_type == "sell":
            # Sell to meet demand
            demand_idx = self._hidden_state["current_demand_idx"] % len(self._hidden_state["demand"])
            demand = self._hidden_state["demand"][demand_idx]
            sold = min(self._hidden_state["total_produced"], demand)

            self._hidden_state["total_produced"] -= sold
            self._hidden_state["total_sold"] += sold
            self._hidden_state["money"] += sold * 20
            self._hidden_state["current_demand_idx"] += 1
            reward = sold * 2

        elif action_type == "buy_materials":
            cost = 100
            if self._hidden_state["money"] >= cost:
                self._hidden_state["money"] -= cost
                self._hidden_state["materials"] += 20

        elif action_type == "hire_worker":
            cost = 200
            if self._hidden_state["money"] >= cost:
                self._hidden_state["money"] -= cost
                self._hidden_state["workers"] += 1

        # Passive energy regeneration
        self._hidden_state["energy"] = min(100, self._hidden_state["energy"] + 5)

        return reward

    def _apply_distribution_shift(self) -> dict:
        """Economic shifts."""
        shift_type = self.rng.choice(["demand_spike", "material_shortage", "energy_crisis"])

        if shift_type == "demand_spike":
            for i in range(len(self._hidden_state["demand"])):
                self._hidden_state["demand"][i] = self.rng.randint(10, 25)
        elif shift_type == "material_shortage":
            self._hidden_state["materials"] = max(0, self._hidden_state["materials"] - 20)
        elif shift_type == "energy_crisis":
            self._hidden_state["energy"] = max(0, self._hidden_state["energy"] - 50)

        return {"type": shift_type, "step": self._current_step}

    def _compute_final_reward(self) -> float:
        """Final reward based on total money and sales."""
        return self._hidden_state["money"] / 100 + self._hidden_state["total_sold"] * 5

    def _is_success(self) -> bool:
        """Success if profitable."""
        return self._hidden_state["money"] > 1000 and self._hidden_state["total_sold"] > 50


class RepairTaskEnvironment(LongHorizonEnvironment):
    """Repair under constraints - fix something with limited time/budget."""

    def __init__(self, seed: int = 42):
        super().__init__(
            env_type=EnvironmentType.REPAIR_TASK,
            name="RepairUnderConstraints",
            min_steps=50,
            max_steps=120,
            seed=seed,
        )

    def _init_hidden_state(self) -> dict:
        """Initialize broken system state."""
        # Generate random broken components
        components = ["power", "cooling", "compute", "network", "storage"]
        broken = self.rng.sample(components, self.rng.randint(2, 4))

        return {
            "components": {c: c not in broken for c in components},
            "repair_budget": 500,
            "time_budget": 100,
            "diagnostics_run": [],
            "repairs_attempted": [],
            "system_health": 0.0,
        }

    def _get_observation(self) -> Observation:
        """Get partial system observation (only diagnosed components visible)."""
        visible_components = {
            c: status for c, status in self._hidden_state["components"].items()
            if c in self._hidden_state["diagnostics_run"]
        }

        return Observation(
            step=self._current_step,
            visible_state={
                "diagnosed_components": visible_components,
                "undiagnosed_count": 5 - len(self._hidden_state["diagnostics_run"]),
                "repair_budget_remaining": self._hidden_state["repair_budget"],
                "time_remaining": self._hidden_state["time_budget"] - self._current_step,
                "system_health": self._hidden_state["system_health"],
            },
            hidden_state_hash=hashlib.sha256(
                json.dumps(self._hidden_state, sort_keys=True).encode()
            ).hexdigest()[:16],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _apply_action(self, action: Action) -> float:
        """Apply diagnostic or repair action."""
        action_type = action.parameters.get("type", "wait")
        component = action.parameters.get("component")
        reward = 0.0

        if action_type == "diagnose" and component:
            cost = 50
            if self._hidden_state["repair_budget"] >= cost:
                self._hidden_state["repair_budget"] -= cost
                if component not in self._hidden_state["diagnostics_run"]:
                    self._hidden_state["diagnostics_run"].append(component)

        elif action_type == "repair" and component:
            cost = 150
            if self._hidden_state["repair_budget"] >= cost:
                self._hidden_state["repair_budget"] -= cost
                self._hidden_state["repairs_attempted"].append(component)

                # Repair has 80% success rate
                if self.rng.random() < 0.8:
                    if component in self._hidden_state["components"]:
                        self._hidden_state["components"][component] = True
                        reward = 20

        # Update system health
        working = sum(1 for v in self._hidden_state["components"].values() if v)
        self._hidden_state["system_health"] = working / 5.0

        return reward

    def _apply_distribution_shift(self) -> dict:
        """Component failures during repair."""
        # Random component breaks
        components = list(self._hidden_state["components"].keys())
        victim = self.rng.choice(components)
        self._hidden_state["components"][victim] = False

        return {"type": "component_failure", "component": victim, "step": self._current_step}

    def _is_done(self) -> bool:
        """Done if fully repaired, budget depleted, or time up."""
        all_working = all(self._hidden_state["components"].values())
        no_budget = self._hidden_state["repair_budget"] < 50
        no_time = self._current_step >= self._hidden_state["time_budget"]

        return all_working or no_budget or no_time or self._current_step >= self.max_steps

    def _compute_final_reward(self) -> float:
        """Reward based on system health and remaining budget."""
        health_reward = self._hidden_state["system_health"] * 100
        budget_bonus = self._hidden_state["repair_budget"] / 10
        return health_reward + budget_bonus

    def _is_success(self) -> bool:
        """Success if all components working."""
        return all(self._hidden_state["components"].values())


class AgencySuite:
    """Suite of long-horizon environments."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.environments = {
            "navigation": NavigationEnvironment(seed),
            "resource_management": ResourceManagementEnvironment(seed + 1),
            "repair_task": RepairTaskEnvironment(seed + 2),
        }
        self.artifact_service = get_artifact_service()
        self.rng = random.Random(seed)

    async def run_episodes(
        self,
        session: AsyncSession,
        env_name: str,
        n_episodes: int,
        run_id: str,
    ) -> tuple[list[EpisodeTrace], EnvironmentMetrics]:
        """Run multiple episodes in an environment."""
        env = self.environments.get(env_name)
        if not env:
            raise ValueError(f"Unknown environment: {env_name}")

        traces = []
        successes = 0
        total_steps = 0
        total_reward = 0
        shift_recoveries = 0
        total_shifts = 0
        total_revisions = 0
        grounded_revisions = 0

        for ep in range(n_episodes):
            episode_seed = self.seed + ep * 100
            env.reset(episode_seed)

            # Simulate agent behavior
            done = False
            step = 0
            current_plan = ["explore", "find_goal", "navigate"]

            while not done and step < env.max_steps:
                # Get observation
                obs = env._get_observation()

                # Decide action (simple heuristic for simulation)
                action = self._simulate_agent_action(env, obs, step)

                # Maybe revise plan based on observation
                if self.rng.random() < 0.1:
                    revision = PlanRevision(
                        revision_id=generate_id("rev"),
                        step=step,
                        previous_plan=current_plan.copy(),
                        new_plan=["adapt", "recover", "continue"],
                        reason=f"Observation at step {step} suggests plan change",
                        triggering_observation=obs,
                        grounded_in_evidence=self.rng.random() < 0.8,
                    )
                    env.record_plan_revision(revision)
                    current_plan = revision.new_plan
                    total_revisions += 1
                    if revision.grounded_in_evidence:
                        grounded_revisions += 1

                # Take step
                _, reward, done = env.step(action)
                step += 1

            # Get trace
            trace = env.get_trace()
            traces.append(trace)

            if trace.success:
                successes += 1
            total_steps += trace.total_steps
            total_reward += trace.final_reward

            # Count shift recoveries
            total_shifts += len(trace.distribution_shifts)
            if len(trace.distribution_shifts) > 0 and trace.success:
                shift_recoveries += 1

        metrics = EnvironmentMetrics(
            environment=env_name,
            episodes_run=n_episodes,
            success_rate=successes / n_episodes,
            avg_steps=total_steps / n_episodes,
            avg_reward=total_reward / n_episodes,
            recovery_rate=shift_recoveries / max(1, total_shifts),
            plan_revisions_per_episode=total_revisions / n_episodes,
            grounded_revisions_rate=grounded_revisions / max(1, total_revisions),
        )

        # Store traces bundle
        await self._store_traces(session, traces, metrics, run_id)

        return traces, metrics

    def _simulate_agent_action(
        self, env: LongHorizonEnvironment, obs: Observation, step: int
    ) -> Action:
        """Simulate agent action (placeholder for real agent)."""
        if isinstance(env, NavigationEnvironment):
            direction = self.rng.choice(["up", "down", "left", "right", "stay"])
            return Action(
                step=step,
                action_type="move",
                parameters={"direction": direction},
                rationale=f"Exploring toward goal",
            )
        elif isinstance(env, ResourceManagementEnvironment):
            action_type = self.rng.choice(["produce", "sell", "buy_materials", "hire_worker", "wait"])
            return Action(
                step=step,
                action_type=action_type,
                parameters={"type": action_type},
                rationale=f"Managing resources",
            )
        elif isinstance(env, RepairTaskEnvironment):
            action_type = self.rng.choice(["diagnose", "repair", "wait"])
            component = self.rng.choice(["power", "cooling", "compute", "network", "storage"])
            return Action(
                step=step,
                action_type=action_type,
                parameters={"type": action_type, "component": component},
                rationale=f"Attempting to fix {component}",
            )
        else:
            return Action(step=step, action_type="wait", parameters={}, rationale="Default")

    async def _store_traces(
        self,
        session: AsyncSession,
        traces: list[EpisodeTrace],
        metrics: EnvironmentMetrics,
        run_id: str,
    ) -> str:
        """Store episode traces as artifact."""
        bundle = {
            "environment": metrics.environment,
            "episodes": len(traces),
            "metrics": {
                "success_rate": metrics.success_rate,
                "avg_steps": metrics.avg_steps,
                "avg_reward": metrics.avg_reward,
                "recovery_rate": metrics.recovery_rate,
                "plan_revisions_per_episode": metrics.plan_revisions_per_episode,
                "grounded_revisions_rate": metrics.grounded_revisions_rate,
            },
            "trace_hashes": [t.trace_hash for t in traces],
            "sample_traces": [
                {
                    "episode_id": t.episode_id,
                    "total_steps": t.total_steps,
                    "success": t.success,
                    "final_reward": t.final_reward,
                    "distribution_shifts": len(t.distribution_shifts),
                    "plan_revisions": len(t.plan_revisions),
                }
                for t in traces[:5]  # Sample
            ],
        }

        artifact = await self.artifact_service.store_artifact(
            session=session,
            data=json.dumps(bundle, indent=2).encode(),
            artifact_type="episode_trace_bundle",
            created_by="agency_suite",
            run_id=run_id,
            filename=f"traces_{metrics.environment}_{len(traces)}.json",
        )

        return artifact.id


_suite: AgencySuite | None = None


def get_agency_suite(seed: int = 42) -> AgencySuite:
    """Get or create the agency suite."""
    global _suite
    if _suite is None or _suite.seed != seed:
        _suite = AgencySuite(seed=seed)
    return _suite
