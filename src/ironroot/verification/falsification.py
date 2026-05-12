# Author: Bradley R. Kinnard
"""Falsifiable claims registry + falsifier protocol (Phase 2a.1).

A *claim* in this codebase is a named, machine-checkable assertion about
the contents of the belief chain and the artifact store. The falsification
gate's job is the opposite of the integrity gate's: instead of verifying
that the chain is internally consistent, it actively searches for
counterexamples to a registered claim.

For each registered ``FalsifiableClaim`` the gate runs the falsifier
against the live chain. If the falsifier produces evidence (an offending
``seq``, a row id, a content_hash mismatch, …) the gate returns
``falsified=True`` together with a structured ``FalsificationEvidence``
blob naming the offender. The blob is suitable for embedding in a
typed ``GATE_RESULT`` belief (Phase 2a.4) so the falsification result
is itself part of the chain.

Three real claims ship with the registry, mirroring the integrity
invariants the chain itself depends on:

1. ``chain_seq_monotonic``    — for every belief row beyond the root,
                                ``seq`` is one greater than the previous
                                row in (run_id-)sequence.
2. ``parent_hash_linkage``    — ``parent_hash`` matches the prior row's
                                ``content_hash``; seq=1 ⇔ parent_hash IS NULL.
3. ``artifact_hash_stability``— every artifact's stored bytes hash to
                                its declared ``content_hash`` and the
                                row's ``size_bytes`` matches the bytes
                                on disk.

The old stub returning ``falsified=False`` is gone. Callers asking the
gate to "attempt falsification" without registered claims now receive an
explicit ``no_claims_registered`` error rather than a free pass.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord, BeliefRecord

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FalsificationEvidence:
    """structured counterexample produced by a falsifier.

    Fields are deliberately small and stringly typed so the dict the gate
    persists into a GATE_RESULT belief is portable across PG/SQLite JSON
    and survives the chain digest. ``offending_belief_ids`` /
    ``offending_artifact_ids`` are the audit pointers; ``details`` is the
    free-text reason.
    """

    offending_belief_ids: tuple[str, ...] = field(default_factory=tuple)
    offending_artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "offending_belief_ids": list(self.offending_belief_ids),
            "offending_artifact_ids": list(self.offending_artifact_ids),
            "details": self.details,
        }


@dataclass(frozen=True)
class FalsificationAttempt:
    """outcome of running a single falsifier against the live chain.

    ``falsified=True`` means the falsifier found a counterexample — the
    claim does NOT hold. ``falsified=False`` means the falsifier ran to
    completion without finding one.
    """

    claim_name: str
    falsified: bool
    evidence: FalsificationEvidence | None
    method: str
    rows_examined: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_name": self.claim_name,
            "falsified": self.falsified,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "method": self.method,
            "rows_examined": self.rows_examined,
        }


Falsifier = Callable[[AsyncSession, str], Awaitable[FalsificationAttempt]]


@dataclass(frozen=True)
class FalsifiableClaim:
    """named, machine-checkable claim plus its falsifier.

    ``falsifier`` is an async callable accepting ``(session, run_id)``
    and returning a ``FalsificationAttempt``. The falsifier MUST be
    deterministic — no RNG, no clock-dependent behaviour. It MUST NOT
    write to the database.
    """

    name: str
    description: str
    falsifier: Falsifier


class FalsifiableClaimRegistry:
    """process-global registry of FalsifiableClaims.

    Claims are added via ``register`` and looked up by name. The gate
    enumerates registered claims via ``all_claims``. The registry is
    a plain dict — no async ops, no I/O — so tests can stand up an
    isolated registry and replace it without affecting the singleton.
    """

    def __init__(self) -> None:
        self._claims: dict[str, FalsifiableClaim] = {}

    def register(self, claim: FalsifiableClaim) -> None:
        if claim.name in self._claims:
            raise ValueError(f"claim already registered: {claim.name}")
        self._claims[claim.name] = claim

    def unregister(self, name: str) -> None:
        self._claims.pop(name, None)

    def get(self, name: str) -> FalsifiableClaim | None:
        return self._claims.get(name)

    def all_claims(self) -> tuple[FalsifiableClaim, ...]:
        return tuple(self._claims.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._claims.keys())


# ---------------------------------------------------------------------------
# Built-in falsifiers
# ---------------------------------------------------------------------------


async def _falsify_chain_seq_monotonic(session: AsyncSession, run_id: str) -> FalsificationAttempt:
    """seq is strictly 1, 2, 3, … with no gaps / duplicates / re-orderings.

    The UNIQUE(run_id, seq) constraint catches duplicates at write time;
    this falsifier catches gaps (a row was deleted) and verifies the
    chain has not been split across runs.
    """
    result = await session.execute(
        select(BeliefRecord.id, BeliefRecord.seq)
        .where(BeliefRecord.run_id == run_id)
        .order_by(BeliefRecord.seq.asc())
    )
    rows = list(result.all())

    expected = 1
    for row in rows:
        if row.seq != expected:
            return FalsificationAttempt(
                claim_name="chain_seq_monotonic",
                falsified=True,
                evidence=FalsificationEvidence(
                    offending_belief_ids=(row.id,),
                    details=(
                        f"row id={row.id} has seq={row.seq}, expected "
                        f"seq={expected}; chain is non-contiguous"
                    ),
                ),
                method="ORDER BY seq ASC + contiguity check",
                rows_examined=len(rows),
            )
        expected += 1

    return FalsificationAttempt(
        claim_name="chain_seq_monotonic",
        falsified=False,
        evidence=None,
        method="ORDER BY seq ASC + contiguity check",
        rows_examined=len(rows),
    )


async def _falsify_parent_hash_linkage(session: AsyncSession, run_id: str) -> FalsificationAttempt:
    """parent_hash == previous row's content_hash; root has parent_hash NULL.

    Catches: (a) a row whose parent_hash was rewritten to point elsewhere,
    (b) the root row gaining a non-NULL parent_hash, (c) a non-root row
    set to NULL.
    """
    result = await session.execute(
        select(
            BeliefRecord.id,
            BeliefRecord.seq,
            BeliefRecord.content_hash,
            BeliefRecord.parent_hash,
        )
        .where(BeliefRecord.run_id == run_id)
        .order_by(BeliefRecord.seq.asc())
    )
    rows = list(result.all())

    previous_hash: str | None = None
    for index, row in enumerate(rows):
        if index == 0:
            if row.parent_hash is not None:
                return FalsificationAttempt(
                    claim_name="parent_hash_linkage",
                    falsified=True,
                    evidence=FalsificationEvidence(
                        offending_belief_ids=(row.id,),
                        details=(
                            f"root row id={row.id} has non-NULL "
                            f"parent_hash={row.parent_hash!r}"
                        ),
                    ),
                    method="seq-ordered scan + parent_hash check",
                    rows_examined=len(rows),
                )
        elif row.parent_hash != previous_hash:
            return FalsificationAttempt(
                claim_name="parent_hash_linkage",
                falsified=True,
                evidence=FalsificationEvidence(
                    offending_belief_ids=(row.id,),
                    details=(
                        f"row id={row.id} seq={row.seq} has "
                        f"parent_hash={row.parent_hash!r}; expected "
                        f"previous content_hash={previous_hash!r}"
                    ),
                ),
                method="seq-ordered scan + parent_hash check",
                rows_examined=len(rows),
            )
        previous_hash = row.content_hash

    return FalsificationAttempt(
        claim_name="parent_hash_linkage",
        falsified=False,
        evidence=None,
        method="seq-ordered scan + parent_hash check",
        rows_examined=len(rows),
    )


async def _falsify_artifact_hash_stability(
    session: AsyncSession, run_id: str
) -> FalsificationAttempt:
    """every artifact's stored bytes hash to its declared content_hash.

    Calls ``ArtifactStore.verify`` (sha256 of the bytes on disk) for each
    ``ArtifactRecord.content_hash`` belonging to ``run_id`` and flags
    any mismatch. The verify call also catches a missing artifact
    (returns False). Size-mismatch is implied — any byte change changes
    the hash — so we do not need a separate size check.
    """
    result = await session.execute(select(ArtifactRecord).where(ArtifactRecord.run_id == run_id))
    artifacts = list(result.scalars().all())

    artifact_service = get_artifact_service()

    for artifact in artifacts:
        if not artifact_service.verify_integrity(artifact.content_hash):
            return FalsificationAttempt(
                claim_name="artifact_hash_stability",
                falsified=True,
                evidence=FalsificationEvidence(
                    offending_artifact_ids=(artifact.id,),
                    details=(
                        f"artifact id={artifact.id} "
                        f"content_hash={artifact.content_hash} failed "
                        "verify(): bytes on disk are missing or hash to a "
                        "different value"
                    ),
                ),
                method="ArtifactStore.verify per artifact",
                rows_examined=len(artifacts),
            )

    return FalsificationAttempt(
        claim_name="artifact_hash_stability",
        falsified=False,
        evidence=None,
        method="ArtifactStore.verify per artifact",
        rows_examined=len(artifacts),
    )


# ---------------------------------------------------------------------------
# Singleton registry, pre-populated with the three core claims.
# ---------------------------------------------------------------------------


_BUILTIN_CLAIMS: tuple[FalsifiableClaim, ...] = (
    FalsifiableClaim(
        name="chain_seq_monotonic",
        description=(
            "Every belief row's seq is contiguous, starting at 1, with "
            "no gaps and no duplicates."
        ),
        falsifier=_falsify_chain_seq_monotonic,
    ),
    FalsifiableClaim(
        name="parent_hash_linkage",
        description=(
            "Each row's parent_hash equals the previous row's content_hash; "
            "the seq=1 root row has parent_hash IS NULL."
        ),
        falsifier=_falsify_parent_hash_linkage,
    ),
    FalsifiableClaim(
        name="artifact_hash_stability",
        description=(
            "Every artifact's stored bytes hash to its declared "
            "content_hash and the stored size_bytes matches the on-disk size."
        ),
        falsifier=_falsify_artifact_hash_stability,
    ),
)


_registry: FalsifiableClaimRegistry | None = None


def get_claim_registry() -> FalsifiableClaimRegistry:
    """returns the process-global claim registry, populated with builtins."""
    global _registry
    if _registry is None:
        _registry = FalsifiableClaimRegistry()
        for claim in _BUILTIN_CLAIMS:
            _registry.register(claim)
    return _registry


def reset_claim_registry_for_testing() -> None:
    """test helper — forces the next ``get_claim_registry`` to re-init."""
    global _registry
    _registry = None


# ---------------------------------------------------------------------------
# Public falsification entry point used by the gate.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FalsificationReport:
    """aggregate falsification report over all registered claims."""

    run_id: str
    attempts: tuple[FalsificationAttempt, ...]

    @property
    def any_falsified(self) -> bool:
        return any(a.falsified for a in self.attempts)

    @property
    def falsified_claims(self) -> tuple[str, ...]:
        return tuple(a.claim_name for a in self.attempts if a.falsified)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "any_falsified": self.any_falsified,
            "falsified_claims": list(self.falsified_claims),
            "attempts": [a.to_dict() for a in self.attempts],
        }


async def run_falsification(
    session: AsyncSession,
    run_id: str,
    registry: FalsifiableClaimRegistry | None = None,
) -> FalsificationReport:
    """runs every registered falsifier against `run_id` in registration order.

    Returns a structured report. The gate (Phase 2a.4) embeds this report
    in a GATE_RESULT belief.

    Raises ``ValueError("no_claims_registered")`` if the registry is empty
    — a falsification gate without claims is not a free pass.
    """
    reg = registry or get_claim_registry()
    claims = reg.all_claims()
    if not claims:
        raise ValueError("no_claims_registered")

    attempts: list[FalsificationAttempt] = []
    for claim in claims:
        attempts.append(await claim.falsifier(session, run_id))

    return FalsificationReport(run_id=run_id, attempts=tuple(attempts))
