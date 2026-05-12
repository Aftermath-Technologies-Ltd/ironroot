# Author: Bradley R. Kinnard
"""Phase 2a.1 / 2a.5 — FalsifiableClaim registry + per-claim positive
and negative fixtures.

Each builtin claim has two tests:

* positive (clean chain): the falsifier runs and returns
  ``falsified=False`` with no evidence.
* negative (tampered fixture): the falsifier produces evidence pointing
  at the offending row / artifact.

The registry itself is also tested: empty registry raises
``no_claims_registered`` so the gate cannot be a free pass, and
duplicate registration raises.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ironroot.beliefs import BeliefService, MetricClass
from ironroot.domain.ids import generate_id, hash_content
from ironroot.orchestration.supervisor import RunPhase
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord, BeliefRecord, RunRecord
from ironroot.verification.falsification import (
    _BUILTIN_CLAIMS,
    FalsifiableClaim,
    FalsifiableClaimRegistry,
    FalsificationAttempt,
    FalsificationEvidence,
    get_claim_registry,
    reset_claim_registry_for_testing,
    run_falsification,
)


async def _build_chain(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
    n: int,
) -> None:
    async with session_factory() as session:
        for i in range(n):
            await belief_service.create_lifecycle_belief(
                session=session,
                run_id=run_id,
                agent_id="test",
                content={"i": i},
                topic_tags=["fixture"],
            )
        await session.commit()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_singleton_registry_seeds_three_claims() -> None:
    """get_claim_registry() preloads the three builtin claims."""
    reset_claim_registry_for_testing()
    reg = get_claim_registry()
    names = reg.names()
    assert "chain_seq_monotonic" in names
    assert "parent_hash_linkage" in names
    assert "artifact_hash_stability" in names


def test_duplicate_registration_raises() -> None:
    reg = FalsifiableClaimRegistry()
    claim = _BUILTIN_CLAIMS[0]
    reg.register(claim)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(claim)


async def test_run_falsification_empty_registry_raises(
    session_factory: async_sessionmaker, run_id: str
) -> None:
    """A falsification gate with zero claims must NOT pass silently."""
    empty = FalsifiableClaimRegistry()
    async with session_factory() as session:
        with pytest.raises(ValueError, match="no_claims_registered"):
            await run_falsification(session, run_id, registry=empty)


# ---------------------------------------------------------------------------
# chain_seq_monotonic
# ---------------------------------------------------------------------------


async def test_chain_seq_monotonic_clean_chain(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """contiguous chain returns falsified=False."""
    await _build_chain(belief_service, session_factory, run_id, 5)
    reset_claim_registry_for_testing()
    async with session_factory() as session:
        report = await run_falsification(session, run_id)
    by_name = {a.claim_name: a for a in report.attempts}
    assert by_name["chain_seq_monotonic"].falsified is False
    assert by_name["chain_seq_monotonic"].rows_examined == 5


async def test_chain_seq_monotonic_detects_gap(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """deleting a middle row creates a gap; falsifier flags it."""
    await _build_chain(belief_service, session_factory, run_id, 4)
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(BeliefRecord)
                    .where(BeliefRecord.run_id == run_id)
                    .order_by(BeliefRecord.seq.asc())
                )
            )
            .scalars()
            .all()
        )
        # delete seq=2 -> chain becomes 1, 3, 4
        await session.delete(rows[1])
        await session.commit()

    reset_claim_registry_for_testing()
    async with session_factory() as session:
        report = await run_falsification(session, run_id)
    by_name = {a.claim_name: a for a in report.attempts}
    attempt = by_name["chain_seq_monotonic"]
    assert attempt.falsified is True
    assert attempt.evidence is not None
    assert "seq=3" in attempt.evidence.details
    assert "expected seq=2" in attempt.evidence.details


# ---------------------------------------------------------------------------
# parent_hash_linkage
# ---------------------------------------------------------------------------


async def test_parent_hash_linkage_clean_chain(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    await _build_chain(belief_service, session_factory, run_id, 3)
    reset_claim_registry_for_testing()
    async with session_factory() as session:
        report = await run_falsification(session, run_id)
    by_name = {a.claim_name: a for a in report.attempts}
    assert by_name["parent_hash_linkage"].falsified is False


async def test_parent_hash_linkage_detects_rewritten_parent(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """rewrite a non-root row's parent_hash to a bogus value."""
    await _build_chain(belief_service, session_factory, run_id, 3)
    async with session_factory() as session:
        row = (
            await session.execute(
                select(BeliefRecord).where(BeliefRecord.run_id == run_id, BeliefRecord.seq == 2)
            )
        ).scalar_one()
        row.parent_hash = "0" * 64
        await session.commit()

    reset_claim_registry_for_testing()
    async with session_factory() as session:
        report = await run_falsification(session, run_id)
    by_name = {a.claim_name: a for a in report.attempts}
    attempt = by_name["parent_hash_linkage"]
    assert attempt.falsified is True
    assert attempt.evidence is not None
    assert "seq=2" in attempt.evidence.details


# ---------------------------------------------------------------------------
# artifact_hash_stability
# ---------------------------------------------------------------------------


async def test_artifact_hash_stability_clean(
    session_factory: async_sessionmaker, run_id: str
) -> None:
    """a freshly stored artifact whose bytes are still on disk passes."""
    artifact_service = get_artifact_service()
    async with session_factory() as session:
        await artifact_service.store_artifact(
            session=session,
            data=b"clean fixture bytes",
            artifact_type="falsification_report",
            created_by="test",
            run_id=run_id,
        )
        await session.commit()

    reset_claim_registry_for_testing()
    async with session_factory() as session:
        report = await run_falsification(session, run_id)
    by_name = {a.claim_name: a for a in report.attempts}
    assert by_name["artifact_hash_stability"].falsified is False


async def test_artifact_hash_stability_detects_missing_bytes(
    session_factory: async_sessionmaker, run_id: str
) -> None:
    """an ArtifactRecord whose content_hash has no bytes on disk fails."""
    async with session_factory() as session:
        session.add(
            ArtifactRecord(
                id=generate_id("art"),
                content_hash=hash_content(b"never-stored-fixture"),
                artifact_type="falsification_report",
                size_bytes=20,
                created_by="test",
                run_id=run_id,
                filename="ghost.bin",
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    reset_claim_registry_for_testing()
    async with session_factory() as session:
        report = await run_falsification(session, run_id)
    by_name = {a.claim_name: a for a in report.attempts}
    attempt = by_name["artifact_hash_stability"]
    assert attempt.falsified is True
    assert attempt.evidence is not None
    assert "verify()" in attempt.evidence.details


# ---------------------------------------------------------------------------
# FalsificationAttempt / FalsificationEvidence serialization
# ---------------------------------------------------------------------------


def test_evidence_dict_round_trip() -> None:
    ev = FalsificationEvidence(
        offending_belief_ids=("b1", "b2"),
        offending_artifact_ids=("a1",),
        details="boom",
    )
    d = ev.to_dict()
    assert d["offending_belief_ids"] == ["b1", "b2"]
    assert d["offending_artifact_ids"] == ["a1"]
    assert d["details"] == "boom"


def test_attempt_dict_round_trip() -> None:
    attempt = FalsificationAttempt(
        claim_name="claim",
        falsified=True,
        evidence=FalsificationEvidence(details="bad"),
        method="m",
        rows_examined=3,
    )
    d = attempt.to_dict()
    assert d["claim_name"] == "claim"
    assert d["falsified"] is True
    assert d["evidence"]["details"] == "bad"


def test_attempt_with_no_evidence_serializes_none() -> None:
    attempt = FalsificationAttempt(
        claim_name="claim",
        falsified=False,
        evidence=None,
        method="m",
        rows_examined=0,
    )
    assert attempt.to_dict()["evidence"] is None
