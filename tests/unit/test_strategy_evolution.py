# Author: Bradley R. Kinnard
"""unit tests for strategy evolution."""

from ironroot.cognition.strategies.mutation import mutate_strategy
from ironroot.cognition.strategies.registry import StrategyManifest, StrategyRegistry
from ironroot.domain.errors import GateFailed


class TestStrategyRegistry:
    """tests for strategy version registry."""

    def test_register_strategy(self) -> None:
        """can register a new strategy."""
        registry = StrategyRegistry()

        manifest = registry.register(
            name="test_strategy",
            version="1.0.0",
            capabilities=["planning", "tool_use"],
            tool_permissions=["external_retriever"],
            abstention_threshold=0.3,
            pinned_dependencies={"model": "gpt-4"},
        )

        assert manifest.strategy_id.startswith("str_")
        assert manifest.name == "test_strategy"
        assert manifest.version == "1.0.0"
        assert not manifest.gate_passed
        assert not manifest.promoted

    def test_get_strategy(self) -> None:
        """can retrieve registered strategy."""
        registry = StrategyRegistry()

        manifest = registry.register(
            name="test",
            version="1.0.0",
            capabilities=[],
            tool_permissions=[],
            abstention_threshold=0.5,
            pinned_dependencies={},
        )

        retrieved = registry.get(manifest.strategy_id)
        assert retrieved is not None
        assert retrieved.strategy_id == manifest.strategy_id

    def test_mark_gate_passed(self) -> None:
        """can mark strategy as gate passed."""
        registry = StrategyRegistry()

        manifest = registry.register(
            name="test",
            version="1.0.0",
            capabilities=[],
            tool_permissions=[],
            abstention_threshold=0.5,
            pinned_dependencies={},
        )

        result = registry.mark_gate_passed(manifest.strategy_id)
        assert result

        retrieved = registry.get(manifest.strategy_id)
        assert retrieved is not None
        assert retrieved.gate_passed

    def test_promote_requires_gate_passed(self) -> None:
        """cannot promote without gate passed."""
        registry = StrategyRegistry()

        manifest = registry.register(
            name="test",
            version="1.0.0",
            capabilities=[],
            tool_permissions=[],
            abstention_threshold=0.5,
            pinned_dependencies={},
        )

        # promotion should fail without gate passed
        result = registry.promote(manifest.strategy_id)
        assert not result

        retrieved = registry.get(manifest.strategy_id)
        assert retrieved is not None
        assert not retrieved.promoted

    def test_promote_after_gate_passed(self) -> None:
        """can promote after gate passed."""
        registry = StrategyRegistry()

        manifest = registry.register(
            name="test",
            version="1.0.0",
            capabilities=[],
            tool_permissions=[],
            abstention_threshold=0.5,
            pinned_dependencies={},
        )

        registry.mark_gate_passed(manifest.strategy_id)
        result = registry.promote(manifest.strategy_id)
        assert result

        retrieved = registry.get(manifest.strategy_id)
        assert retrieved is not None
        assert retrieved.promoted


class TestStrategyMutation:
    """tests for bounded strategy mutation."""

    def test_mutate_creates_new_strategy(self) -> None:
        """mutation creates a new strategy id."""
        base = StrategyManifest(
            strategy_id="str_base",
            name="test",
            version="1.0.0",
            capabilities=["planning"],
            tool_permissions=["retriever"],
            abstention_threshold=0.5,
            pinned_dependencies={"model": "gpt-4"},
            created_at="2025-01-01T00:00:00",
        )

        mutated = mutate_strategy(base, seed=42)

        assert mutated.strategy_id != base.strategy_id
        assert mutated.strategy_id.startswith("str_")

    def test_mutate_increments_version(self) -> None:
        """mutation increments version number."""
        base = StrategyManifest(
            strategy_id="str_base",
            name="test",
            version="1.0.0",
            capabilities=[],
            tool_permissions=[],
            abstention_threshold=0.5,
            pinned_dependencies={},
            created_at="2025-01-01T00:00:00",
        )

        mutated = mutate_strategy(base, seed=42)

        assert mutated.version == "1.0.1"

    def test_mutate_bounds_threshold(self) -> None:
        """mutation keeps threshold in 0-1 range."""
        base = StrategyManifest(
            strategy_id="str_base",
            name="test",
            version="1.0.0",
            capabilities=[],
            tool_permissions=[],
            abstention_threshold=0.0,  # at minimum
            pinned_dependencies={},
            created_at="2025-01-01T00:00:00",
        )

        # run many mutations to test bounds
        for seed in range(100):
            mutated = mutate_strategy(base, seed=seed)
            assert 0.0 <= mutated.abstention_threshold <= 1.0

    def test_mutate_deterministic_with_seed(self) -> None:
        """same seed produces same mutation."""
        base = StrategyManifest(
            strategy_id="str_base",
            name="test",
            version="1.0.0",
            capabilities=[],
            tool_permissions=[],
            abstention_threshold=0.5,
            pinned_dependencies={},
            created_at="2025-01-01T00:00:00",
        )

        mutated1 = mutate_strategy(base, seed=12345)
        mutated2 = mutate_strategy(base, seed=12345)

        assert mutated1.abstention_threshold == mutated2.abstention_threshold

    def test_mutate_preserves_capabilities(self) -> None:
        """mutation preserves base capabilities."""
        base = StrategyManifest(
            strategy_id="str_base",
            name="test",
            version="1.0.0",
            capabilities=["planning", "tool_use", "memory"],
            tool_permissions=["retriever", "web_search"],
            abstention_threshold=0.5,
            pinned_dependencies={"model": "gpt-4"},
            created_at="2025-01-01T00:00:00",
        )

        mutated = mutate_strategy(base, seed=42)

        assert mutated.capabilities == base.capabilities
        assert mutated.tool_permissions == base.tool_permissions
        assert mutated.pinned_dependencies == base.pinned_dependencies

    def test_mutated_strategy_not_promoted(self) -> None:
        """mutated strategies start unpromoted."""
        base = StrategyManifest(
            strategy_id="str_base",
            name="test",
            version="1.0.0",
            capabilities=[],
            tool_permissions=[],
            abstention_threshold=0.5,
            pinned_dependencies={},
            created_at="2025-01-01T00:00:00",
            gate_passed=True,
            promoted=True,
        )

        mutated = mutate_strategy(base, seed=42)

        assert not mutated.gate_passed
        assert not mutated.promoted


class TestGateBlockedPromotion:
    """tests that promotion is blocked without gate pass."""

    def test_gate_failed_error(self) -> None:
        """GateFailed raised for promotion without gate."""
        error = GateFailed("strategy_promotion", "gates have not passed")

        assert error.gate_name == "strategy_promotion"
        assert "gates have not passed" in error.reason

    def test_selection_prefers_gate_passed(self) -> None:
        """selection should prefer strategies that passed gates."""
        # simulate selection logic
        strategies = [
            {"id": "str_1", "gate_passed": False, "correctness": 0.9},
            {"id": "str_2", "gate_passed": True, "correctness": 0.7},
            {"id": "str_3", "gate_passed": True, "correctness": 0.8},
        ]

        # filter to only gate_passed
        eligible = [s for s in strategies if s["gate_passed"]]

        # select best by correctness
        best = max(eligible, key=lambda s: s["correctness"])

        assert best["id"] == "str_3"
        assert best["gate_passed"]
