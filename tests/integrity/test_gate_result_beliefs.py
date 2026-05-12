# Author: Bradley R. Kinnard
"""Phase 2a.4 / 2a.5 — gate suite writes GATE_RESULT beliefs and
negative-path coverage for each gate.

After ``execute_gates`` runs, the belief chain must contain one
``GATE_RESULT`` belief per executed gate (replay / integrity /
invariants / regression / falsification), carrying:

* ``content.gate_name``
* ``content.passed``
* ``content.input_digest``
* ``content.decision`` (gate-specific payload)

Negative-path tests run a known-broken fixture and assert the relevant
gate's GATE_RESULT belief carries ``passed=False`` and ``confidence=0.0``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ironroot.beliefs import BeliefService, BeliefType
from ironroot.domain.ids import generate_id, hash_content
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import (
    ArtifactRecord,
    BeliefRecord,
    IncidentRecord,
    RunRecord,
)
from ironroot.verification.falsification import reset_claim_registry_for_testing
from ironroot.verification.gate_service import GateService
from ironroot.verification.regression import reset_regression_registry_for_testing


@pytest.fixture(autouse=True)
def _reset_registries() -> None:
    reset_claim_registry_for_testing()
    reset_regression_registry_for_testing()


async def _seed_chain(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
    n: int = 3,
) -> None:
    """seeds n lifecycle beliefs and bumps the run's activity counters."""
    async with session_factory() as session:
        for i in range(n):
            await belief_service.create_lifecycle_belief(
                session=session,
                run_id=run_id,
                agent_id="test",
                content={"i": i},
                topic_tags=["seed"],
            )
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        run.steps_used = 5
        run.tool_calls_used = 2
        run.belief_writes_used = n
        await session.commit()


async def _store_artifact(
    session_factory: async_sessionmaker, run_id: str, data: bytes = b"clean"
) -> str:
    artifact_service = get_artifact_service()
    async with session_factory() as session:
        rec = await artifact_service.store_artifact(
            session=session,
            data=data,
            artifact_type="falsification_report",
            created_by="test",
            run_id=run_id,
        )
        await session.commit()
        return rec.id


async def _gate_results_by_name(
    session_factory: async_sessionmaker, run_id: str
) -> dict[str, BeliefRecord]:
    async with session_factory() as session:
        result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.run_id == run_id)
            .where(BeliefRecord.belief_type == BeliefType.GATE_RESULT.value)
            .order_by(BeliefRecord.seq.asc())
        )
        rows = list(result.scalars().all())
    by_name: dict[str, BeliefRecord] = {}
    for row in rows:
        by_name[row.content["gate_name"]] = row
    return by_name


async def test_full_suite_writes_one_gate_result_belief_per_gate(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """clean run → 5 gate_result beliefs (one per gate), all passing."""
    await _seed_chain(belief_service, session_factory, run_id)
    await _store_artifact(session_factory, run_id)

    gate = GateService()
    async with session_factory() as session:
        gate_record = await gate.execute_gates(session, run_id)
        await session.commit()

    by_name = await _gate_results_by_name(session_factory, run_id)
    assert set(by_name) == {
        "replay",
        "integrity",
        "invariants",
        "regression",
        "falsification",
    }
    for name, belief in by_name.items():
        assert belief.content["passed"] is True, f"{name} expected pass"
        assert belief.confidence == 1.0, f"{name} confidence != 1.0"
        assert belief.content["input_digest"], f"{name} missing input_digest"
        assert belief.provenance, f"{name} missing provenance"
    assert gate_record.passed is True


async def test_regression_fails_when_incident_exists(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """Phase 2a.5 negative: regression gate must fail on a run with incidents."""
    await _seed_chain(belief_service, session_factory, run_id)
    await _store_artifact(session_factory, run_id)

    async with session_factory() as session:
        session.add(
            IncidentRecord(
                id=generate_id("inc"),
                run_id=run_id,
                agent_id=None,
                incident_type="invariant_violation",
                severity="high",
                description="seeded incident",
                evidence_ids=[],
                penalties_applied={},
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        await gate.execute_gates(session, run_id)
        await session.commit()

    by_name = await _gate_results_by_name(session_factory, run_id)
    regression_belief = by_name["regression"]
    assert regression_belief.content["passed"] is False
    assert regression_belief.confidence == 0.0
    decision = regression_belief.content["decision"]
    assert decision["incident_count"] == 1


async def test_regression_fails_when_no_suite_registered(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """Phase 2a.5 negative: missing suite must NOT be a free pass."""
    await _seed_chain(belief_service, session_factory, run_id)
    await _store_artifact(session_factory, run_id)

    # Mark this run as a kind for which no suite exists.
    async with session_factory() as session:
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        run.config = {"run_kind": "no_such_kind"}
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        await gate.execute_gates(session, run_id)
        await session.commit()

    by_name = await _gate_results_by_name(session_factory, run_id)
    regression_belief = by_name["regression"]
    assert regression_belief.content["passed"] is False
    decision = regression_belief.content["decision"]
    assert "no_suite_for_run_kind" in decision["error"]


async def test_falsification_fails_on_missing_artifact(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """Phase 2a.5 negative: ghost artifact row trips the falsification gate."""
    await _seed_chain(belief_service, session_factory, run_id)

    # store an ArtifactRecord whose bytes were never written.
    async with session_factory() as session:
        session.add(
            ArtifactRecord(
                id=generate_id("art"),
                content_hash=hash_content(b"never-stored"),
                artifact_type="falsification_report",
                size_bytes=12,
                created_by="test",
                run_id=run_id,
                filename="ghost.bin",
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        gate_record = await gate.execute_gates(session, run_id)
        await session.commit()

    by_name = await _gate_results_by_name(session_factory, run_id)
    fals = by_name["falsification"]
    assert fals.content["passed"] is False
    decision = fals.content["decision"]
    assert "artifact_hash_stability" in decision["falsified_claims"]
    assert gate_record.passed is False


async def test_invariants_fails_on_negative_budget(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """Phase 2a.5 negative: negative budget produces an invariants failure."""
    await _seed_chain(belief_service, session_factory, run_id)
    await _store_artifact(session_factory, run_id)

    async with session_factory() as session:
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        run.belief_writes_used = -1  # corrupt the counter
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        await gate.execute_gates(session, run_id)
        await session.commit()

    by_name = await _gate_results_by_name(session_factory, run_id)
    inv = by_name["invariants"]
    assert inv.content["passed"] is False
    decision = inv.content["decision"]
    assert decision["budget_valid"] is False


async def test_integrity_fails_on_ghost_artifact(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """Phase 2a.5 negative: integrity gate flags ghost artifacts."""
    await _seed_chain(belief_service, session_factory, run_id)

    async with session_factory() as session:
        session.add(
            ArtifactRecord(
                id=generate_id("art"),
                content_hash=hash_content(b"missing-bytes"),
                artifact_type="falsification_report",
                size_bytes=13,
                created_by="test",
                run_id=run_id,
                filename="ghost.bin",
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    gate = GateService()
    async with session_factory() as session:
        await gate.execute_gates(session, run_id)
        await session.commit()

    by_name = await _gate_results_by_name(session_factory, run_id)
    intg = by_name["integrity"]
    assert intg.content["passed"] is False
    assert intg.content["decision"]["failures"]


async def test_gate_results_carry_input_digest_and_provenance(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """Every GATE_RESULT belief is replayable: input_digest stable, provenance present."""
    await _seed_chain(belief_service, session_factory, run_id)
    await _store_artifact(session_factory, run_id)

    gate = GateService()
    async with session_factory() as session:
        await gate.execute_gates(session, run_id)
        await session.commit()

    by_name = await _gate_results_by_name(session_factory, run_id)
    for name, belief in by_name.items():
        assert isinstance(belief.content["input_digest"], str), name
        assert len(belief.content["input_digest"]) == 64, name
        assert belief.provenance, f"{name} provenance empty"
