# Author: Bradley R. Kinnard
"""Phase 1.9 — adversarial fixtures against the chain invariants.

The Phase 1 integrity core commits to three named invariants. This
module exercises an adversary in each direction:

1. **Belief hash chain** — every belief points at the prior content_hash.
   Tampering breaks ``verify_chain``.
2. **(parent_hash IS NULL) iff seq == 1** — enforced at the DB level by
   ``ck_beliefs_root_iff_seq_one``. Inserting a non-root row with NULL
   parent_hash, or a root row with non-NULL parent_hash, must fail.
3. **UNIQUE(run_id, seq)** — two rows with the same (run_id, seq) must
   fail to insert, regardless of any application-level checks.

Each test is its own scenario; tests share no mutable state.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from ironroot.beliefs import BeliefService
from ironroot.storage.models import BeliefRecord


async def _seed(
    service: BeliefService,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    n: int,
) -> None:
    for i in range(n):
        async with session_factory() as session:
            await service.create_belief(
                session,
                run_id=run_id,
                agent_id=f"agent_{i}",
                content={"i": i},
                confidence=1.0,
            )
            await session.commit()


@pytest.mark.asyncio
async def test_tampering_parent_hash_breaks_verify_chain(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """flipping a parent_hash on any row trips verify_chain to False."""
    await _seed(belief_service, session_factory, run_id, 4)

    async with session_factory() as session:
        target = (
            await session.execute(
                select(BeliefRecord)
                .where(BeliefRecord.run_id == run_id)
                .order_by(BeliefRecord.seq.asc())
            )
        ).scalars().all()[2]
        target.parent_hash = "f" * 64  # bogus
        await session.commit()

    async with session_factory() as session:
        assert await belief_service.verify_chain(session, run_id) is False


@pytest.mark.asyncio
async def test_tampering_content_hash_breaks_verify_chain(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """changing a row's content_hash desynchronises the parent linkage."""
    await _seed(belief_service, session_factory, run_id, 4)

    async with session_factory() as session:
        target = (
            await session.execute(
                select(BeliefRecord)
                .where(BeliefRecord.run_id == run_id)
                .order_by(BeliefRecord.seq.asc())
            )
        ).scalars().all()[1]
        target.content_hash = "a" * 64
        await session.commit()

    async with session_factory() as session:
        assert await belief_service.verify_chain(session, run_id) is False


@pytest.mark.asyncio
async def test_duplicate_seq_violates_unique_constraint(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """attempting to insert two rows with the same (run_id, seq) fails."""
    await _seed(belief_service, session_factory, run_id, 2)

    async with session_factory() as session:
        existing = (
            await session.execute(
                select(BeliefRecord)
                .where(BeliefRecord.run_id == run_id)
                .order_by(BeliefRecord.seq.asc())
                .limit(1)
            )
        ).scalar_one()

        clone = BeliefRecord(
            id="bel_duplicate_seq_attempt",
            run_id=run_id,
            seq=existing.seq,  # collision!
            agent_id="impostor",
            belief_type="lifecycle",
            content_hash="b" * 64,
            parent_hash=None,  # bypass the chain
            content={"i": 999},
            confidence=1.0,
            evidence_ids=[],
            topic_tags=[],
            created_at=datetime.now(UTC),
        )
        session.add(clone)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_root_iff_seq_one_check_constraint(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> None:
    """seq=1 must be root (parent_hash NULL); seq>1 must have a parent."""
    # Insert seq=1 with a non-null parent_hash -> violates the CHECK.
    async with session_factory() as session:
        bad_root = BeliefRecord(
            id="bel_bad_root_attempt",
            run_id=run_id,
            seq=1,
            agent_id="impostor",
            belief_type="lifecycle",
            content_hash="c" * 64,
            parent_hash="d" * 64,  # NOT NULL with seq=1 → reject
            content={"x": 1},
            confidence=1.0,
            evidence_ids=[],
            topic_tags=[],
            created_at=datetime.now(UTC),
        )
        session.add(bad_root)
        with pytest.raises(IntegrityError):
            await session.commit()

    # Insert seq=5 with parent_hash NULL -> also violates the CHECK.
    async with session_factory() as session:
        bad_mid = BeliefRecord(
            id="bel_bad_mid_attempt",
            run_id=run_id,
            seq=5,
            agent_id="impostor",
            belief_type="lifecycle",
            content_hash="e" * 64,
            parent_hash=None,  # NULL with seq>1 → reject
            content={"x": 2},
            confidence=1.0,
            evidence_ids=[],
            topic_tags=[],
            created_at=datetime.now(UTC),
        )
        session.add(bad_mid)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_verify_chain_passes_clean_chain(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """positive control — a clean chain reports True."""
    await _seed(belief_service, session_factory, run_id, 8)
    async with session_factory() as session:
        assert await belief_service.verify_chain(session, run_id) is True


@pytest.mark.asyncio
async def test_verify_chain_handles_empty_chain(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """empty chain is trivially verified."""
    async with session_factory() as session:
        assert await belief_service.verify_chain(session, run_id) is True
