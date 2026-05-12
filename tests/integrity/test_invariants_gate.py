# Author: Bradley R. Kinnard
"""Phase 1.6 — the invariants gate covers all three declared invariants
and each violation surfaces as a typed Violation belief.

The three declared core invariants from ``domain/invariants.py``:

* ``belief_hash_chain``  — every belief points at the prior content_hash.
* ``budget_not_negative`` — steps_used / tool_calls_used / belief_writes_used
  must all be >= 0.
* ``run_state_machine`` — the run's status field is in the known finite set.

Each scenario below produces a failing condition and asserts the gate
both reports the violation in its result dict AND appends a typed
Violation belief that an auditor can find later.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ironroot.beliefs import BeliefService, BeliefType
from ironroot.storage.models import BeliefRecord, RunRecord
from ironroot.verification.gate_service import GateService


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
async def test_clean_run_passes_all_three_invariants(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """positive control — a clean run trips no invariant."""
    await _seed(belief_service, session_factory, run_id, 3)
    gate = GateService()
    async with session_factory() as session:
        result = await gate._check_invariants(session, run_id)
    assert result["passed"] is True
    assert result["chain_valid"] is True
    assert result["state_valid"] is True
    assert result["budget_valid"] is True
    assert result["violations"] == []


@pytest.mark.asyncio
async def test_negative_budget_produces_violation_belief(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """budget_not_negative — set a budget counter < 0 and assert violation."""
    await _seed(belief_service, session_factory, run_id, 2)
    async with session_factory() as session:
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        run.tool_calls_used = -1
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        result = await gate._check_invariants(session, run_id)
        await session.commit()

    assert result["passed"] is False
    assert result["budget_valid"] is False
    names = [v["invariant"] for v in result["violations"]]
    assert "budget_not_negative" in names

    # the gate appended a Violation belief
    async with session_factory() as session:
        violations = (
            (
                await session.execute(
                    select(BeliefRecord)
                    .where(BeliefRecord.run_id == run_id)
                    .where(BeliefRecord.belief_type == BeliefType.VIOLATION.value)
                )
            )
            .scalars()
            .all()
        )
    assert any(v.content.get("invariant") == "budget_not_negative" for v in violations)


@pytest.mark.asyncio
async def test_unknown_status_produces_state_machine_violation(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """run_state_machine — a status outside the allowed set trips the gate."""
    await _seed(belief_service, session_factory, run_id, 2)
    async with session_factory() as session:
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        run.status = "totally_made_up"
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        result = await gate._check_invariants(session, run_id)
        await session.commit()

    assert result["passed"] is False
    assert result["state_valid"] is False
    assert any(v["invariant"] == "run_state_machine" for v in result["violations"])

    async with session_factory() as session:
        violations = (
            (
                await session.execute(
                    select(BeliefRecord)
                    .where(BeliefRecord.run_id == run_id)
                    .where(BeliefRecord.belief_type == BeliefType.VIOLATION.value)
                )
            )
            .scalars()
            .all()
        )
    assert any(v.content.get("invariant") == "run_state_machine" for v in violations)


@pytest.mark.asyncio
async def test_tampered_chain_produces_chain_violation(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """belief_hash_chain — tampering surfaces as a Violation belief."""
    await _seed(belief_service, session_factory, run_id, 3)
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
            .all()[1]
        )
        target.parent_hash = "f" * 64
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        result = await gate._check_invariants(session, run_id)
        await session.commit()

    assert result["passed"] is False
    assert result["chain_valid"] is False
    assert any(v["invariant"] == "belief_hash_chain" for v in result["violations"])


@pytest.mark.asyncio
async def test_multiple_violations_all_recorded(
    session_factory: async_sessionmaker[AsyncSession],
    belief_service: BeliefService,
    run_id: str,
) -> None:
    """multiple simultaneous failures produce one belief per failure."""
    await _seed(belief_service, session_factory, run_id, 3)

    async with session_factory() as session:
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        run.status = "nope"
        run.steps_used = -42
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        result = await gate._check_invariants(session, run_id)
        await session.commit()

    assert result["passed"] is False
    invariant_names = {v["invariant"] for v in result["violations"]}
    assert {"run_state_machine", "budget_not_negative"}.issubset(invariant_names)

    async with session_factory() as session:
        violations = (
            (
                await session.execute(
                    select(BeliefRecord)
                    .where(BeliefRecord.run_id == run_id)
                    .where(BeliefRecord.belief_type == BeliefType.VIOLATION.value)
                )
            )
            .scalars()
            .all()
        )
    recorded = {v.content.get("invariant") for v in violations}
    assert {"run_state_machine", "budget_not_negative"}.issubset(recorded)
