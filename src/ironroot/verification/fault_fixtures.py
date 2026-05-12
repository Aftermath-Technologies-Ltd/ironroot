# Author: Bradley R. Kinnard
"""Deterministic fault fixtures (Phase 2b.1).

A *fault fixture* is a named, deterministic description of a way to
break the chain. It is the integrity counterpart to a unit test
fixture: instead of asserting expected outputs, it specifies an
expected *failure* and exercises the gate suite against it.

Each fixture provides three async operations:

* ``apply(session, run_id)``  — mutate the chain / artifact store so
  the named failure mode is present. Returns an
  ``ObservedFaultEffect`` recording what changed.
* ``revert(session, run_id)`` — undo the mutation so the chain is back
  to its pre-apply state. Returns nothing; the operator must rely on
  the gate suite to confirm restoration.
* ``replay(session, run_id)`` — re-apply the fault under the same
  fixture id and return the observed effect. Used by the self-healing
  recurrence check (Phase 2b.2) so recurrence is determined by
  re-running the deterministic fixture rather than ``random.random()``.

Fixtures are RNG-free and time-independent. Two callers applying the
same fixture to the same chain MUST produce identical observed
effects. This is what makes the self-healing pipeline auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from ironroot.storage.models import ArtifactRecord, BeliefRecord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ObservedFaultEffect:
    """structured record of what a fault did to the chain.

    The observed effect is the *real* state recorded after ``apply``,
    not a probability or a sampled value. It is suitable for embedding
    in a typed observation belief (Phase 2b.3).
    """

    fixture_id: str
    affected_belief_ids: tuple[str, ...] = field(default_factory=tuple)
    affected_artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "affected_belief_ids": list(self.affected_belief_ids),
            "affected_artifact_ids": list(self.affected_artifact_ids),
            "before": self.before,
            "after": self.after,
            "details": self.details,
        }


class FaultFixture:
    """abstract fault fixture. Subclasses implement apply / revert.

    ``fixture_id`` is the audit handle every downstream belief and
    artifact references via provenance. Two fixtures with the same id
    must produce identical observed effects when applied to identical
    chain state.
    """

    fixture_id: str
    description: str

    def __init__(self, fixture_id: str, description: str) -> None:
        self.fixture_id = fixture_id
        self.description = description

    async def apply(
        self, session: AsyncSession, run_id: str
    ) -> ObservedFaultEffect:  # pragma: no cover - abstract
        raise NotImplementedError

    async def revert(self, session: AsyncSession, run_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def replay(self, session: AsyncSession, run_id: str) -> ObservedFaultEffect:
        """apply then revert; returns the observed effect.

        Used by the recurrence check: the fault is replayed in a
        sandboxed window, observed, and then reverted before the next
        gate run. This is deterministic — the same fixture against the
        same chain produces the same observed effect every time.
        """
        effect = await self.apply(session, run_id)
        await session.flush()
        await self.revert(session, run_id)
        await session.flush()
        return effect


class ArtifactTamperFixture(FaultFixture):
    """flip an ArtifactRecord.content_hash to a known-bad value.

    Detected by:
      * falsification gate ``artifact_hash_stability`` claim
      * integrity gate (artifact verify_integrity check)
    """

    def __init__(self, target_artifact_id: str) -> None:
        super().__init__(
            fixture_id=f"artifact_tamper:{target_artifact_id}",
            description=f"rewrite ArtifactRecord.content_hash for {target_artifact_id}",
        )
        self.target_artifact_id = target_artifact_id
        self._original_hash: str | None = None

    async def apply(self, session: AsyncSession, run_id: str) -> ObservedFaultEffect:
        artifact = (
            await session.execute(
                select(ArtifactRecord).where(ArtifactRecord.id == self.target_artifact_id)
            )
        ).scalar_one()
        self._original_hash = artifact.content_hash
        new_hash = "0" * 64
        artifact.content_hash = new_hash
        await session.flush()
        return ObservedFaultEffect(
            fixture_id=self.fixture_id,
            affected_artifact_ids=(self.target_artifact_id,),
            before={"content_hash": self._original_hash},
            after={"content_hash": new_hash},
            details=f"ArtifactRecord.content_hash overwritten to {new_hash[:8]}…",
        )

    async def revert(self, session: AsyncSession, run_id: str) -> None:
        if self._original_hash is None:
            return
        artifact = (
            await session.execute(
                select(ArtifactRecord).where(ArtifactRecord.id == self.target_artifact_id)
            )
        ).scalar_one()
        artifact.content_hash = self._original_hash
        await session.flush()
        self._original_hash = None


class BeliefParentHashTamperFixture(FaultFixture):
    """flip a BeliefRecord.parent_hash to a known-bad value.

    Detected by:
      * falsification gate ``parent_hash_linkage`` claim
      * invariants gate ``belief_hash_chain`` (verify_chain returns False)
    """

    def __init__(self, target_belief_id: str) -> None:
        super().__init__(
            fixture_id=f"belief_parent_tamper:{target_belief_id}",
            description=f"rewrite BeliefRecord.parent_hash for {target_belief_id}",
        )
        self.target_belief_id = target_belief_id
        self._original_parent_hash: str | None = None
        self._was_root: bool = False

    async def apply(self, session: AsyncSession, run_id: str) -> ObservedFaultEffect:
        belief = (
            await session.execute(
                select(BeliefRecord).where(BeliefRecord.id == self.target_belief_id)
            )
        ).scalar_one()
        self._original_parent_hash = belief.parent_hash
        self._was_root = belief.parent_hash is None
        if self._was_root:
            # The root row must keep parent_hash NULL per CHECK constraint
            # ck_beliefs_root_iff_seq_one, so tamper a different field that
            # still trips the digest: content_hash.
            self._original_parent_hash = belief.content_hash
            belief.content_hash = "0" * 64
            after = {"content_hash": belief.content_hash}
        else:
            belief.parent_hash = "0" * 64
            after = {"parent_hash": belief.parent_hash}
        await session.flush()
        before_field = "content_hash" if self._was_root else "parent_hash"
        details_msg = (
            "root-row content_hash overwritten" if self._was_root else "parent_hash overwritten"
        )
        return ObservedFaultEffect(
            fixture_id=self.fixture_id,
            affected_belief_ids=(self.target_belief_id,),
            before={before_field: self._original_parent_hash},
            after=after,
            details=details_msg,
        )

    async def revert(self, session: AsyncSession, run_id: str) -> None:
        if self._original_parent_hash is None:
            return
        belief = (
            await session.execute(
                select(BeliefRecord).where(BeliefRecord.id == self.target_belief_id)
            )
        ).scalar_one()
        if self._was_root:
            belief.content_hash = self._original_parent_hash
        else:
            belief.parent_hash = self._original_parent_hash
        await session.flush()
        self._original_parent_hash = None


class MissingArtifactFixture(FaultFixture):
    """insert an ArtifactRecord whose bytes do not exist on disk.

    Detected by:
      * falsification gate ``artifact_hash_stability`` claim
      * integrity gate (verify_integrity fails)
    """

    def __init__(self, ghost_hash: str, run_id: str | None = None) -> None:
        super().__init__(
            fixture_id=f"missing_artifact:{ghost_hash}",
            description=f"insert ArtifactRecord with non-existent bytes (hash={ghost_hash[:8]}…)",
        )
        self.ghost_hash = ghost_hash
        self.run_id = run_id
        self._inserted_artifact_id: str | None = None

    async def apply(self, session: AsyncSession, run_id: str) -> ObservedFaultEffect:
        from datetime import UTC, datetime

        from ironroot.domain.ids import generate_id

        artifact_id = generate_id("art")
        session.add(
            ArtifactRecord(
                id=artifact_id,
                content_hash=self.ghost_hash,
                artifact_type="ghost_fixture",
                size_bytes=0,
                created_by="fault_fixture",
                run_id=run_id,
                filename="ghost.bin",
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
        self._inserted_artifact_id = artifact_id
        return ObservedFaultEffect(
            fixture_id=self.fixture_id,
            affected_artifact_ids=(artifact_id,),
            before={"existed": False},
            after={"existed": True, "content_hash": self.ghost_hash},
            details="ArtifactRecord inserted with bytes-not-on-disk",
        )

    async def revert(self, session: AsyncSession, run_id: str) -> None:
        if self._inserted_artifact_id is None:
            return
        artifact = (
            await session.execute(
                select(ArtifactRecord).where(ArtifactRecord.id == self._inserted_artifact_id)
            )
        ).scalar_one_or_none()
        if artifact is not None:
            await session.delete(artifact)
            await session.flush()
        self._inserted_artifact_id = None


class FaultFixtureRegistry:
    """process-global registry of constructed FaultFixtures.

    Useful for the orchestration executor: when run config names a
    fixture, look it up here. Tests construct fixtures inline and don't
    need the registry.
    """

    def __init__(self) -> None:
        self._fixtures: dict[str, FaultFixture] = {}

    def register(self, fixture: FaultFixture) -> None:
        if fixture.fixture_id in self._fixtures:
            raise ValueError(f"fixture already registered: {fixture.fixture_id}")
        self._fixtures[fixture.fixture_id] = fixture

    def unregister(self, fixture_id: str) -> None:
        self._fixtures.pop(fixture_id, None)

    def get(self, fixture_id: str) -> FaultFixture | None:
        return self._fixtures.get(fixture_id)

    def names(self) -> tuple[str, ...]:
        return tuple(self._fixtures.keys())


_registry: FaultFixtureRegistry | None = None


def get_fault_fixture_registry() -> FaultFixtureRegistry:
    global _registry
    if _registry is None:
        _registry = FaultFixtureRegistry()
    return _registry


def reset_fault_fixture_registry_for_testing() -> None:
    global _registry
    _registry = None


__all__ = [
    "ArtifactTamperFixture",
    "BeliefParentHashTamperFixture",
    "FaultFixture",
    "FaultFixtureRegistry",
    "MissingArtifactFixture",
    "ObservedFaultEffect",
    "get_fault_fixture_registry",
    "reset_fault_fixture_registry_for_testing",
]
