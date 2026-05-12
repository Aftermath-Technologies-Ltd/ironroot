# Author: Bradley R. Kinnard
"""Phase 2b.1 — FaultFixture determinism + Phase 2b.4 e2e cycle.

Fixture-level tests (apply → revert round-trip, gate detection of the
applied fault) plus an end-to-end test: inject a known fault, run gates
(integrity + falsification fail), restore via the fixture, run gates
again (all pass), and confirm the second replay digest equals the
first.

These tests are the operational evidence that the self-healing pipeline
does what its name says.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ironroot.beliefs import BeliefService, BeliefType
from ironroot.healing.restoration import (
    InvariantType,
    RestorationStatus,
    SelfHealingRestorer,
)
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord, BeliefRecord, RunRecord
from ironroot.verification.falsification import (
    reset_claim_registry_for_testing,
    run_falsification,
)
from ironroot.verification.fault_fixtures import (
    ArtifactTamperFixture,
    BeliefParentHashTamperFixture,
    FaultFixtureRegistry,
    MissingArtifactFixture,
    get_fault_fixture_registry,
    reset_fault_fixture_registry_for_testing,
)
from ironroot.verification.gate_service import GateService
from ironroot.verification.regression import reset_regression_registry_for_testing
from ironroot.verification.replay import compute_chain_digest


@pytest.fixture(autouse=True)
def _reset_registries() -> None:
    reset_fault_fixture_registry_for_testing()
    reset_claim_registry_for_testing()
    reset_regression_registry_for_testing()


async def _seed_chain(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
    n: int = 4,
) -> None:
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
        run.steps_used = 3
        run.tool_calls_used = 1
        run.belief_writes_used = n
        await session.commit()


async def _store_artifact(session_factory: async_sessionmaker, run_id: str, data: bytes) -> str:
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


# ---------------------------------------------------------------------------
# Registry behaviour
# ---------------------------------------------------------------------------


def test_registry_register_and_lookup() -> None:
    reg = FaultFixtureRegistry()
    fixture = ArtifactTamperFixture("art_x")
    reg.register(fixture)
    assert reg.get(fixture.fixture_id) is fixture
    assert fixture.fixture_id in reg.names()


def test_registry_duplicate_rejected() -> None:
    reg = FaultFixtureRegistry()
    fixture = ArtifactTamperFixture("art_x")
    reg.register(fixture)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(fixture)


def test_singleton_registry_is_global() -> None:
    reg1 = get_fault_fixture_registry()
    reg2 = get_fault_fixture_registry()
    assert reg1 is reg2


# ---------------------------------------------------------------------------
# ArtifactTamperFixture
# ---------------------------------------------------------------------------


async def test_artifact_tamper_apply_then_revert_round_trip(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    await _seed_chain(belief_service, session_factory, run_id)
    art_id = await _store_artifact(session_factory, run_id, b"original")

    fixture = ArtifactTamperFixture(art_id)
    async with session_factory() as session:
        artifact = (
            await session.execute(select(ArtifactRecord).where(ArtifactRecord.id == art_id))
        ).scalar_one()
        original_hash = artifact.content_hash

        effect = await fixture.apply(session, run_id)
        assert effect.affected_artifact_ids == (art_id,)
        assert effect.after["content_hash"] == "0" * 64
        assert effect.before["content_hash"] == original_hash

        await fixture.revert(session, run_id)
        artifact = (
            await session.execute(select(ArtifactRecord).where(ArtifactRecord.id == art_id))
        ).scalar_one()
        assert artifact.content_hash == original_hash


async def test_belief_parent_tamper_caught_by_falsification(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    await _seed_chain(belief_service, session_factory, run_id, n=4)
    # Pick a non-root row so the fixture rewrites parent_hash (not
    # content_hash); both paths are covered by other fixtures.
    async with session_factory() as session:
        row = (
            await session.execute(
                select(BeliefRecord)
                .where(BeliefRecord.run_id == run_id)
                .where(BeliefRecord.seq == 3)
            )
        ).scalar_one()
        target_belief_id = row.id

    fixture = BeliefParentHashTamperFixture(target_belief_id)
    async with session_factory() as session:
        await fixture.apply(session, run_id)
        await session.commit()

    async with session_factory() as session:
        report = await run_falsification(session, run_id)
    assert "parent_hash_linkage" in report.falsified_claims


# ---------------------------------------------------------------------------
# Phase 2b.4 — end-to-end fixture-driven restoration cycle
# ---------------------------------------------------------------------------


async def test_end_to_end_fault_then_restore_then_replay_stable(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """The deliverable per upgrade-plan §2b.4.

    1. seed a clean chain + an artifact
    2. seal the replay digest by running the gate suite once
    3. inject a known fault (artifact tamper)
    4. re-run the gate suite — falsification and integrity must fail
    5. run the self-healing restorer with the same fixture → revert
       (restoration writes observation+inference beliefs and re-seals
       the replay baseline since the chain has legitimately grown).
    6. re-run the gate suite — all gates pass
    7. a SECOND replay (run the gate suite again immediately) produces
       a digest equal to the first post-restoration run's digest. This
       is the "second replay produces identical digest" deliverable
       from upgrade-plan §2b.4: the restoration outcome is itself
       replayable.
    """
    await _seed_chain(belief_service, session_factory, run_id, n=4)
    art_id = await _store_artifact(session_factory, run_id, b"important payload")

    gate = GateService()

    # 2. seal the replay digest by running the suite once
    async with session_factory() as session:
        first_record = await gate.execute_gates(session, run_id)
        assert first_record.passed is True
        await session.commit()

    # 3. inject the fault
    fixture = ArtifactTamperFixture(art_id)
    async with session_factory() as session:
        observed = await fixture.apply(session, run_id)
        await session.commit()
    assert observed.affected_artifact_ids == (art_id,)

    # 4. gates must catch it
    async with session_factory() as session:
        broken_record = await gate.execute_gates(session, run_id)
        await session.commit()
    assert broken_record.passed is False
    failed_gates = {
        name for name, decision in broken_record.results["gates"].items() if not decision["passed"]
    }
    assert "falsification" in failed_gates
    assert "integrity" in failed_gates

    # 5. restoration via the same fixture
    restorer = SelfHealingRestorer()
    violation = restorer.register_invariant_violation(
        invariant_type=InvariantType.ARTIFACT_TAMPER,
        description="artifact tamper fixture",
        run_id=run_id,
        component="artifact_store",
        evidence={"fixture_id": fixture.fixture_id},
    )
    async with session_factory() as session:
        report = await restorer.restore_correctness(
            session=session,
            violation_id=violation.violation_id,
            run_id=run_id,
            fault_fixture=fixture,
        )
        await session.commit()
    assert report.final_status == RestorationStatus.VERIFIED

    # 6. gates pass again (replay baseline was re-sealed by restoration)
    async with session_factory() as session:
        recovered_record = await gate.execute_gates(session, run_id)
        await session.commit()
    assert recovered_record.passed is True

    # 7. SECOND replay produces identical digest: run gates one more
    # time and confirm the chain digest is the same as right after the
    # restoration's reseal (since no further work was added).
    async with session_factory() as session:
        digest_after_first_recovered_run = await compute_chain_digest(session, run_id)

    async with session_factory() as session:
        second_recovered_record = await gate.execute_gates(session, run_id)
        await session.commit()
    assert second_recovered_record.passed is True

    async with session_factory() as session:
        digest_after_second_recovered_run = await compute_chain_digest(session, run_id)
    assert digest_after_first_recovered_run == digest_after_second_recovered_run


async def test_restoration_writes_inference_and_observation_beliefs(
    belief_service: BeliefService,
    session_factory: async_sessionmaker,
    run_id: str,
) -> None:
    """Phase 2b.3: restoration outcomes land as typed beliefs with provenance."""
    await _seed_chain(belief_service, session_factory, run_id, n=3)

    # Use a missing-artifact fixture (no apply mutation needed beyond
    # inserting a ghost row; revert removes it).
    fixture = MissingArtifactFixture(ghost_hash="a" * 64, run_id=run_id)
    async with session_factory() as session:
        await fixture.apply(session, run_id)
        await session.commit()

    restorer = SelfHealingRestorer()
    violation = restorer.register_invariant_violation(
        invariant_type=InvariantType.MISSING_ARTIFACT,
        description="ghost artifact fixture",
        run_id=run_id,
        component="artifact_store",
        evidence={"fixture_id": fixture.fixture_id},
    )
    async with session_factory() as session:
        await restorer.restore_correctness(
            session=session,
            violation_id=violation.violation_id,
            run_id=run_id,
            fault_fixture=fixture,
        )
        await session.commit()

    async with session_factory() as session:
        inferences = (
            (
                await session.execute(
                    select(BeliefRecord)
                    .where(BeliefRecord.run_id == run_id)
                    .where(BeliefRecord.belief_type == BeliefType.INFERENCE.value)
                )
            )
            .scalars()
            .all()
        )

    assert any(
        i.content.get("claim") in {"restoration_verified", "restoration_failed"}
        for i in inferences
    )
    target = next(i for i in inferences if "restoration" in i.content.get("claim", ""))
    assert target.provenance["kind"] == "restoration_outcome"
    assert fixture.fixture_id in target.provenance["fixture_ids"]
