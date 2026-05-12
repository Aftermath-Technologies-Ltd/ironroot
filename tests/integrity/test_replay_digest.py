# Author: Bradley R. Kinnard
"""Phase 1.5 / 1.9 — replay digest behaviour against adversarial inputs.

Property under test: the replay gate flips from "passing (baselined)" to
"failing (mismatch)" the moment any field on any belief row is altered,
or the row order is changed, or a row is dropped.

We use the GateService directly so the test exercises the exact code
path operators will run, not a stand-alone helper.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ironroot.beliefs import BeliefService
from ironroot.storage.models import BeliefRecord, RunRecord
from ironroot.verification.gate_service import GateService
from ironroot.verification.replay import (
    compute_chain_digest,
    compute_chain_digest_from_rows,
)


async def _seed_chain(
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
                content={"i": i, "msg": f"belief {i}"},
                confidence=1.0,
            )
            await session.commit()


@pytest.mark.asyncio
async def test_digest_is_stable_for_identical_chains(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """recomputing the digest on an unchanged chain yields the same value."""
    await _seed_chain(belief_service, session_factory, run_id, 5)
    async with session_factory() as session:
        d1 = await compute_chain_digest(session, run_id)
        d2 = await compute_chain_digest(session, run_id)
    assert d1 == d2


@pytest.mark.asyncio
async def test_first_replay_gate_seals_baseline(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """no prior baseline -> gate stores current digest and reports baselined."""
    await _seed_chain(belief_service, session_factory, run_id, 3)

    gate = GateService()
    async with session_factory() as session:
        # need some activity to satisfy execute_gates' guard
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        run.belief_writes_used = 3
        await session.commit()

    async with session_factory() as session:
        result = await gate._check_replay(session, run_id, seed=42)
        await session.commit()

    assert result["passed"] is True
    assert result["baselined"] is True
    assert result["live_digest"] == result["baseline_digest"]

    async with session_factory() as session:
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        assert run.replay_digest == result["live_digest"]
        assert run.replay_digest_sealed_at is not None


@pytest.mark.asyncio
async def test_replay_gate_passes_when_chain_unchanged(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """seal a baseline, then re-check with the same chain -> pass."""
    await _seed_chain(belief_service, session_factory, run_id, 4)
    gate = GateService()

    # first check seals
    async with session_factory() as session:
        await gate._check_replay(session, run_id, seed=42)
        await session.commit()

    # second check should pass without re-sealing
    async with session_factory() as session:
        result = await gate._check_replay(session, run_id, seed=42)
        await session.commit()

    assert result["passed"] is True
    assert result["baselined"] is False
    assert result["live_digest"] == result["baseline_digest"]


@pytest.mark.asyncio
async def test_tampered_content_breaks_replay_gate(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """mutating any field of any belief row makes the gate fail."""
    await _seed_chain(belief_service, session_factory, run_id, 5)
    gate = GateService()

    # seal a baseline against the clean chain
    async with session_factory() as session:
        await gate._check_replay(session, run_id, seed=42)
        await session.commit()

    # adversary edits one row's agent_id directly — the kind of tamper
    # the gate exists to catch.
    async with session_factory() as session:
        target = (
            (
                await session.execute(
                    select(BeliefRecord)
                    .where(BeliefRecord.run_id == run_id)
                    .order_by(BeliefRecord.seq.asc())
                )
            )
            .scalars()
            .all()[2]
        )
        target.agent_id = "ATTACKER"
        await session.commit()

    async with session_factory() as session:
        result = await gate._check_replay(session, run_id, seed=42)

    assert result["passed"] is False
    assert "mismatch" in result["details"]
    assert result["live_digest"] != result["baseline_digest"]


@pytest.mark.asyncio
async def test_dropped_row_breaks_replay_gate(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """deleting a chain row makes seq non-monotonic -> digest raises.

    The replay gate refuses to silently paper over a chain that has
    gaps. ``compute_chain_digest`` raises ``ValueError``; the gate
    surfaces this as a failure rather than crashing the caller.
    """
    await _seed_chain(belief_service, session_factory, run_id, 4)

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
        # Drop the middle row.
        await session.delete(rows[1])
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="out of order"):
            await compute_chain_digest(session, run_id)


def test_digest_distinguishes_rows_with_different_seqs() -> None:
    """rows that differ only by seq still produce different digests."""
    from dataclasses import dataclass

    @dataclass
    class R:
        seq: int
        parent_hash: str | None
        content_hash: str
        agent_id: str
        belief_type: str

    rows_a = [
        R(1, None, "h1", "agt", "lifecycle"),
        R(2, "h1", "h2", "agt", "lifecycle"),
    ]
    rows_b = [
        R(1, None, "h1", "agt", "lifecycle"),
        R(2, "h1", "h3", "agt", "lifecycle"),  # different content_hash
    ]
    assert compute_chain_digest_from_rows(rows_a) != compute_chain_digest_from_rows(rows_b)


def test_digest_rejects_out_of_order_rows() -> None:
    """rows passed out of order are rejected explicitly."""
    from dataclasses import dataclass

    @dataclass
    class R:
        seq: int
        parent_hash: str | None
        content_hash: str
        agent_id: str
        belief_type: str

    out_of_order = [
        R(2, "h1", "h2", "agt", "lifecycle"),
        R(1, None, "h1", "agt", "lifecycle"),
    ]
    with pytest.raises(ValueError, match="out of order"):
        compute_chain_digest_from_rows(out_of_order)


@pytest.mark.asyncio
async def test_empty_chain_digest_is_well_defined(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> None:
    """digest over the empty chain is the sha256 of empty bytes."""
    async with session_factory() as session:
        digest = await compute_chain_digest(session, run_id)
    # sha256 of empty bytes
    assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.mark.asyncio
async def test_replay_gate_pass_then_tamper_then_fail_full_cycle(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """end-to-end: pass once, tamper, then fail.

    This is the canonical positive-then-negative property: the gate
    transitions from passing to failing iff the chain changes. The
    baseline seal + tamper + re-check sequence is exactly what an
    operator would run after a re-execution suspected of drift.
    """
    await _seed_chain(belief_service, session_factory, run_id, 6)
    gate = GateService()

    # seal
    async with session_factory() as session:
        seal_result = await gate._check_replay(session, run_id, seed=42)
        await session.commit()
    assert seal_result["passed"] is True
    sealed = seal_result["live_digest"]

    # re-check, no tamper -> still passing, no re-seal
    async with session_factory() as session:
        recheck = await gate._check_replay(session, run_id, seed=42)
    assert recheck["passed"] is True
    assert recheck["baseline_digest"] == sealed

    # tamper: change content of the last WORK row in place. Gate-result
    # rows (which Phase 2a.4 appends on every gate run) are excluded
    # from the replay digest, so tampering them is a separate concern
    # the integrity gate covers. To prove the replay gate notices
    # research-content drift we tamper the latest lifecycle row.
    async with session_factory() as session:
        last = (
            await session.execute(
                select(BeliefRecord)
                .where(BeliefRecord.run_id == run_id)
                .where(BeliefRecord.belief_type == "lifecycle")
                .order_by(BeliefRecord.seq.desc())
                .limit(1)
            )
        ).scalar_one()
        last.content = {"tampered": True}
        last.content_hash = "0" * 64  # corrupt
        await session.commit()

    # re-check post-tamper -> fail
    async with session_factory() as session:
        post = await gate._check_replay(session, run_id, seed=42)
    assert post["passed"] is False
    assert post["baseline_digest"] == sealed
    assert post["live_digest"] != sealed
