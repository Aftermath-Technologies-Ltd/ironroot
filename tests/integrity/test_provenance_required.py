# Author: Bradley R. Kinnard
"""Phase 2c.2 / 2c.3 — typed write API + ProvenanceRef enforcement.

The new typed API is `append_observation`, `append_inference`,
`append_gate_result`. Every derived belief (inference, hypothesis,
prediction, violation, gate_result) carries a non-empty `provenance`
column. The DB CHECK constraint `ck_beliefs_provenance_for_derived`
catches anyone bypassing the service.

These tests pin the application-level enforcement; the
`test_provenance_db_check` test verifies the constraint actually fires
by writing through the ORM with `provenance={}`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from ironroot.beliefs import (
    BeliefService,
    BeliefType,
    MetricClass,
    ProvenanceRef,
)
from ironroot.domain.errors import InvariantViolation
from ironroot.domain.ids import generate_id, hash_content
from ironroot.orchestration.supervisor import RunPhase
from ironroot.storage.models import ArtifactRecord, BeliefRecord, RunRecord

pytestmark = pytest.mark.asyncio


async def _promote_to_test_phase(session_factory: async_sessionmaker, run_id: str) -> None:
    async with session_factory() as session:
        run = (await session.execute(select(RunRecord).where(RunRecord.id == run_id))).scalar_one()
        run.phase = RunPhase.TEST.value
        await session.commit()


async def _store_artifact(session_factory: async_sessionmaker, run_id: str) -> str:
    """drops a fixture artifact row so observation beliefs have a valid ref."""
    artifact_id = generate_id("art")
    async with session_factory() as session:
        session.add(
            ArtifactRecord(
                id=artifact_id,
                content_hash=hash_content(b"fixture-bytes"),
                artifact_type="falsification_report",
                size_bytes=13,
                created_by="test",
                run_id=run_id,
                filename="fixture.json",
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    return artifact_id


async def test_append_inference_requires_provenance(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """append_inference with an empty ref refuses to write."""
    async with session_factory() as session:
        with pytest.raises(InvariantViolation) as exc:
            await belief_service.append_inference(
                session=session,
                run_id=run_id,
                agent_id="test",
                claim="something derived",
                provenance=ProvenanceRef(),
            )
        assert "provenance" in str(exc.value).lower()


async def test_append_inference_persists_with_provenance(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """append_inference with a real ref writes a chain row that survives readback."""
    async with session_factory() as session:
        belief = await belief_service.append_inference(
            session=session,
            run_id=run_id,
            agent_id="test",
            claim="x correlates with y",
            provenance=ProvenanceRef(
                kind="derived_from",
                belief_ids=("bel_upstream",),
                notes="test",
            ),
        )
        await session.commit()
        assert belief.belief_type == BeliefType.INFERENCE.value
        assert belief.provenance != {}
        assert belief.provenance["belief_ids"] == ["bel_upstream"]


async def test_append_gate_result_carries_input_digest(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """gate result has gate_name, passed, input_digest, decision in content."""
    async with session_factory() as session:
        belief = await belief_service.append_gate_result(
            session=session,
            run_id=run_id,
            gate_name="replay",
            passed=True,
            input_digest="deadbeef" * 8,
            decision_details={"baseline": "x", "live": "x"},
            evidence_artifact_ids=["art_one"],
        )
        await session.commit()
        assert belief.belief_type == BeliefType.GATE_RESULT.value
        assert belief.content["gate_name"] == "replay"
        assert belief.content["input_digest"] == "deadbeef" * 8
        assert belief.content["passed"] is True
        assert belief.confidence == 1.0
        assert belief.provenance["artifact_ids"] == ["art_one"]


async def test_gate_result_failed_has_zero_confidence(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """a failed gate writes confidence=0.0 — audits filter on it."""
    async with session_factory() as session:
        belief = await belief_service.append_gate_result(
            session=session,
            run_id=run_id,
            gate_name="falsification",
            passed=False,
            input_digest="cafebabe" * 8,
            decision_details={"counterexample_belief_id": "bel_bad"},
        )
        await session.commit()
        assert belief.confidence == 0.0


async def test_append_observation_secondary_requires_provenance(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """SECONDARY observations are non-PRIMARY and must trace upstream."""
    await _promote_to_test_phase(session_factory, run_id)
    artifact_id = await _store_artifact(session_factory, run_id)
    async with session_factory() as session:
        with pytest.raises(InvariantViolation) as exc:
            await belief_service.append_observation(
                session=session,
                run_id=run_id,
                agent_id="test",
                metric_name="bookkeeping_count",
                value=1,
                unit="count",
                method="counted internal items",
                metric_class=MetricClass.SECONDARY,
                artifact_ids=[artifact_id],
                topic_tags=["bookkeeping"],
            )
        assert "SECONDARY" in str(exc.value)


async def test_primary_observation_does_not_require_provenance(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """PRIMARY observations sit at the bottom of the graph — exempt."""
    await _promote_to_test_phase(session_factory, run_id)
    artifact_id = await _store_artifact(session_factory, run_id)
    async with session_factory() as session:
        belief = await belief_service.append_observation(
            session=session,
            run_id=run_id,
            agent_id="test",
            metric_name="fault_detected",
            value=True,
            unit="boolean",
            method="checked fault injection telemetry",
            metric_class=MetricClass.PRIMARY,
            artifact_ids=[artifact_id],
            topic_tags=["primary"],
        )
        await session.commit()
        assert belief.belief_type == BeliefType.OBSERVATION.value
        assert belief.provenance == {}


async def test_provenance_db_check_fires_on_orm_bypass(
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """Bypass BeliefService and write a GATE_RESULT row with empty provenance.

    The CHECK constraint must reject it. This is the safety net for any
    code path that constructs a BeliefRecord directly instead of going
    through the service.
    """
    async with session_factory() as session:
        record = BeliefRecord(
            id=generate_id("bel"),
            run_id=run_id,
            seq=1,
            agent_id="test",
            belief_type=BeliefType.GATE_RESULT.value,
            content={"gate_name": "x", "passed": True},
            content_hash=hash_content(b"bypass"),
            parent_hash=None,
            confidence=1.0,
            evidence_ids=[],
            topic_tags=[],
            provenance={},
            created_at=datetime.now(UTC),
        )
        session.add(record)
        with pytest.raises(IntegrityError):
            await session.commit()
