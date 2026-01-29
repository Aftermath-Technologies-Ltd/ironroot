# Author: Bradley R. Kinnard
"""unit tests for strategy registry."""

from ironroot.cognition.strategies.registry import StrategyRegistry


class TestStrategyRegistry:
    """tests for strategy registration and promotion."""

    def test_register_creates_manifest(self) -> None:
        """registering creates a retrievable manifest."""
        registry = StrategyRegistry()

        manifest = registry.register(
            name="test_strategy",
            version="1.0.0",
            capabilities=["propose"],
            tool_permissions=["retriever"],
            abstention_threshold=0.5,
            pinned_dependencies={"python": "3.12"},
        )

        assert manifest.strategy_id.startswith("str_")
        assert manifest.name == "test_strategy"
        assert manifest.version == "1.0.0"
        assert not manifest.gate_passed
        assert not manifest.promoted

    def test_get_returns_registered(self) -> None:
        """can retrieve registered strategy by id."""
        registry = StrategyRegistry()
        manifest = registry.register("test", "1.0", [], [], 0.5, {})

        retrieved = registry.get(manifest.strategy_id)
        assert retrieved is not None
        assert retrieved.name == "test"

    def test_get_nonexistent_returns_none(self) -> None:
        """getting nonexistent returns none."""
        registry = StrategyRegistry()

        assert registry.get("nonexistent") is None

    def test_mark_gate_passed(self) -> None:
        """can mark strategy as gate passed."""
        registry = StrategyRegistry()
        manifest = registry.register("test", "1.0", [], [], 0.5, {})

        assert not manifest.gate_passed

        result = registry.mark_gate_passed(manifest.strategy_id)
        assert result
        assert manifest.gate_passed

    def test_promote_requires_gate_passed(self) -> None:
        """cannot promote without gate passing."""
        registry = StrategyRegistry()
        manifest = registry.register("test", "1.0", [], [], 0.5, {})

        # try to promote without gate
        result = registry.promote(manifest.strategy_id)
        assert not result
        assert not manifest.promoted

    def test_promote_after_gate(self) -> None:
        """can promote after gate passes."""
        registry = StrategyRegistry()
        manifest = registry.register("test", "1.0", [], [], 0.5, {})

        registry.mark_gate_passed(manifest.strategy_id)
        result = registry.promote(manifest.strategy_id)

        assert result
        assert manifest.promoted

    def test_list_all(self) -> None:
        """list_all returns all registered strategies."""
        registry = StrategyRegistry()

        registry.register("a", "1.0", [], [], 0.5, {})
        registry.register("b", "1.0", [], [], 0.5, {})
        registry.register("c", "1.0", [], [], 0.5, {})

        all_strategies = registry.list_all()
        assert len(all_strategies) == 3

    def test_list_promoted(self) -> None:
        """list_promoted returns only promoted strategies."""
        registry = StrategyRegistry()

        registry.register("a", "1.0", [], [], 0.5, {})
        m2 = registry.register("b", "1.0", [], [], 0.5, {})
        registry.register("c", "1.0", [], [], 0.5, {})

        # promote only m2
        registry.mark_gate_passed(m2.strategy_id)
        registry.promote(m2.strategy_id)

        promoted = registry.list_promoted()
        assert len(promoted) == 1
        assert promoted[0].name == "b"
