# Author: Bradley R. Kinnard
"""strategy version registry."""

from dataclasses import dataclass

from ironroot.domain.ids import generate_id
from ironroot.domain.time import now_iso


@dataclass
class StrategyManifest:
    """versioned strategy definition."""

    strategy_id: str
    name: str
    version: str
    capabilities: list[str]
    tool_permissions: list[str]
    abstention_threshold: float
    pinned_dependencies: dict[str, str]
    created_at: str
    gate_passed: bool = False
    promoted: bool = False


class StrategyRegistry:
    """manages strategy versions and promotion."""

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyManifest] = {}
        self._by_name: dict[str, list[str]] = {}

    def register(
        self,
        name: str,
        version: str,
        capabilities: list[str],
        tool_permissions: list[str],
        abstention_threshold: float,
        pinned_dependencies: dict[str, str],
    ) -> StrategyManifest:
        """registers a new strategy version."""
        strategy_id = generate_id("str")

        manifest = StrategyManifest(
            strategy_id=strategy_id,
            name=name,
            version=version,
            capabilities=capabilities,
            tool_permissions=tool_permissions,
            abstention_threshold=abstention_threshold,
            pinned_dependencies=pinned_dependencies,
            created_at=now_iso(),
        )

        self._strategies[strategy_id] = manifest
        self._by_name.setdefault(name, []).append(strategy_id)

        return manifest

    def get(self, strategy_id: str) -> StrategyManifest | None:
        """retrieves a strategy by id."""
        return self._strategies.get(strategy_id)

    def mark_gate_passed(self, strategy_id: str) -> bool:
        """marks that a strategy passed its gate."""
        manifest = self._strategies.get(strategy_id)
        if manifest:
            manifest.gate_passed = True
            return True
        return False

    def promote(self, strategy_id: str) -> bool:
        """promotes a strategy if gate passed."""
        manifest = self._strategies.get(strategy_id)
        if manifest and manifest.gate_passed:
            manifest.promoted = True
            return True
        return False

    def list_all(self) -> list[StrategyManifest]:
        """returns all registered strategies."""
        return list(self._strategies.values())

    def list_promoted(self) -> list[StrategyManifest]:
        """returns only promoted strategies."""
        return [s for s in self._strategies.values() if s.promoted]
