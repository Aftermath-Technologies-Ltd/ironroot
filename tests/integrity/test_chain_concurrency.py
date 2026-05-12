# Author: Bradley R. Kinnard
"""Phase 1.3 — concurrent appenders produce a totally-ordered chain.

The append path uses a per-chain lock (`pg_advisory_xact_lock` on
Postgres, process-level `asyncio.Lock` on the SQLite fallback used here).
Under N concurrent appenders we must observe:

* Every belief has a unique `seq` per `run_id` (the UNIQUE constraint).
* `seq` values are exactly ``1..N``; no gaps, no duplicates.
* `parent_hash` linkage is contiguous in `seq` order.
* `BeliefService.verify_chain` returns True afterwards.

If the lock were missing, two appenders racing on the same chain would
both see the same prev_seq, both compute new_seq = prev_seq + 1, and the
UNIQUE(run_id, seq) constraint would raise — meaning either the test fails
or fails noisily (caught here as a regression signal).
"""

from __future__ import annotations

import asyncio
import itertools
from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ironroot.beliefs import BeliefService
from ironroot.storage.models import BeliefRecord, RunRecord

# Module-level counter ensures every hypothesis-generated belief gets a
# globally unique payload, so the content_hash UNIQUE constraint never
# fires across iterations that share a fixture run_id.
_payload_counter = itertools.count()


async def _append_one(
    service: BeliefService,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    agent_id: str,
    payload: dict[str, Any],
) -> None:
    """one append in its own session (simulates a concurrent writer)."""
    async with session_factory() as session:
        await service.create_belief(
            session,
            run_id=run_id,
            agent_id=agent_id,
            content=payload,
            confidence=1.0,
        )
        await session.commit()


@pytest.mark.asyncio
async def test_no_forks_under_concurrent_appenders(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """20 appenders racing on the same chain produce a fork-free chain."""
    n = 20
    tasks = [
        _append_one(
            belief_service,
            session_factory,
            run_id,
            agent_id=f"agent_{i:02d}",
            payload={"i": i, "msg": f"belief {i}"},
        )
        for i in range(n)
    ]
    await asyncio.gather(*tasks)

    async with session_factory() as session:
        result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.run_id == run_id)
            .order_by(BeliefRecord.seq.asc())
        )
        beliefs = list(result.scalars().all())

        # property 1: every appender produced exactly one row
        assert len(beliefs) == n

        # property 2: seq is exactly 1..N, no gaps no duplicates
        assert [b.seq for b in beliefs] == list(range(1, n + 1))

        # property 3: parent_hash linkage is contiguous in seq order
        assert beliefs[0].parent_hash is None
        for prev, cur in zip(beliefs, beliefs[1:], strict=False):
            assert cur.parent_hash == prev.content_hash

        # property 4: BeliefService.verify_chain agrees
        assert await belief_service.verify_chain(session, run_id) is True

        # property 5: belief_writes_used was incremented n times (generic API)
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        assert run.belief_writes_used == n


@pytest.mark.asyncio
async def test_negative_control_unlocked_appends_fork(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> None:
    """negative control — proves the test would fail without the lock.

    Bypass the BeliefService chain lock and call the same insert path
    concurrently. With no serialization, multiple appenders compute the
    same `seq = max + 1`, and the UNIQUE(run_id, seq) constraint must
    raise. If this test ever stops raising, either the constraint was
    dropped or SQLite has started serializing differently and the
    positive tests are no longer meaningfully covering the lock.
    """
    from sqlalchemy.exc import IntegrityError

    async def _append_without_lock(i: int) -> None:
        async with session_factory() as session:
            # Read max seq with NO lock and NO advisory lock.
            row = (
                await session.execute(
                    select(
                        BeliefRecord.seq.label("seq"),
                        BeliefRecord.content_hash.label("h"),
                    )
                    .where(BeliefRecord.run_id == run_id)
                    .order_by(BeliefRecord.seq.desc())
                    .limit(1)
                )
            ).first()
            prev_seq = int(row.seq) if row else 0
            prev_hash = row.h if row else None
            new_seq = prev_seq + 1
            await asyncio.sleep(0)  # encourage interleaving
            content_hash = f"unlocked_{i:04d}_" + ("0" * 51)
            record = BeliefRecord(
                id=f"bel_unlocked_{i:04d}",
                run_id=run_id,
                seq=new_seq,
                agent_id=f"unlocked_{i}",
                belief_type="lifecycle",
                content_hash=content_hash[:64],
                parent_hash=prev_hash,
                content={"i": i},
                confidence=1.0,
                evidence_ids=[],
                topic_tags=[],
                created_at=datetime.now(UTC),
            )
            session.add(record)
            await session.commit()

    # Run 8 unlocked appenders. At least one pair must collide on seq.
    results = await asyncio.gather(
        *[_append_without_lock(i) for i in range(8)], return_exceptions=True
    )
    integrity_errors = [r for r in results if isinstance(r, IntegrityError)]
    assert integrity_errors, (
        "Negative control: with no lock, concurrent appenders MUST violate "
        "UNIQUE(run_id, seq). If this assertion fails, either the constraint "
        "is gone or the test fixture has started serializing implicitly."
    )


@given(
    n_appenders=st.integers(min_value=2, max_value=15),
    payloads=st.lists(
        st.dictionaries(
            keys=st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=8,
            ),
            values=st.integers(min_value=0, max_value=1000),
            max_size=4,
        ),
        min_size=2,
        max_size=15,
    ),
)
@settings(
    deadline=None,
    max_examples=8,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@pytest.mark.asyncio
async def test_hypothesis_chain_stays_consistent_under_concurrency(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
    n_appenders: int,
    payloads: list[dict[str, int]],
) -> None:
    """hypothesis-driven: random N and random payloads still produce
    a fork-free chain. We clamp N to len(payloads) and ensure payloads
    are unique so the content_hash UNIQUE constraint doesn't false-fail.
    """
    # Tag every payload with a globally unique nonce so the content_hash
    # UNIQUE constraint can't be tripped by repeated payload shapes across
    # hypothesis iterations.
    unique: list[dict[str, int]] = [{**p, "_nonce": next(_payload_counter)} for p in payloads]
    n = min(n_appenders, len(unique))
    if n < 2:
        return  # not enough material to race

    # Use a fresh logical chain per example (different run_id) so previous
    # hypothesis iterations don't poison this one. We piggyback on the
    # fixture run_id by namespacing in agent_id; cheaper than re-creating
    # the run row each iteration.
    tag = f"hyp_{n}"
    tasks = [
        _append_one(
            belief_service,
            session_factory,
            run_id,
            agent_id=f"{tag}_{i:02d}",
            payload=unique[i],
        )
        for i in range(n)
    ]
    await asyncio.gather(*tasks)

    async with session_factory() as session:
        beliefs = (
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

        # property: seq is contiguous starting at 1 and no duplicates exist
        seqs = [b.seq for b in beliefs]
        assert seqs == list(range(1, len(seqs) + 1))

        # property: chain links are contiguous
        assert beliefs[0].parent_hash is None
        for prev, cur in zip(beliefs, beliefs[1:], strict=False):
            assert cur.parent_hash == prev.content_hash

        # property: verify_chain agrees
        assert await belief_service.verify_chain(session, run_id) is True
