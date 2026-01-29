# Author: Bradley R. Kinnard
"""unit tests for belief service immutability and contradiction linking."""

import pytest

from ironroot.domain.errors import ImmutabilityViolation


class TestBeliefImmutability:
    """tests that beliefs cannot be modified."""

    def test_update_raises_immutability_violation(self) -> None:
        """update attempt raises ImmutabilityViolation."""
        from ironroot.cognition.memory.belief_service import BeliefService

        service = BeliefService()

        with pytest.raises(ImmutabilityViolation) as exc_info:
            # this is sync wrapper just to test the exception
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                service.update_belief(None, "bel_test", {"new": "content"})  # type: ignore
            )

        assert "append-only" in str(exc_info.value)
        assert "bel_test" in str(exc_info.value)

    def test_delete_raises_immutability_violation(self) -> None:
        """delete attempt raises ImmutabilityViolation."""
        from ironroot.cognition.memory.belief_service import BeliefService

        service = BeliefService()

        with pytest.raises(ImmutabilityViolation) as exc_info:
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                service.delete_belief(None, "bel_test")  # type: ignore
            )

        assert "append-only" in str(exc_info.value)
        assert "bel_test" in str(exc_info.value)


class TestHashChainCorrectness:
    """tests for hash chain integrity in append-only store."""

    def test_chain_links_are_correct(self) -> None:
        """each belief parent_hash points to previous content_hash."""
        from ironroot.cognition.memory.append_only_store import AppendOnlyBeliefStore

        store = AppendOnlyBeliefStore()

        beliefs = []
        for i in range(5):
            record = store.append(f"belief {i}".encode(), "agt", "run", 1.0)
            beliefs.append(record)

        # first has no parent
        assert beliefs[0].parent_hash is None

        # each subsequent points to previous
        for i in range(1, len(beliefs)):
            assert beliefs[i].parent_hash == beliefs[i - 1].content_hash

    def test_chain_verification_detects_tampering(self) -> None:
        """tampered chain fails verification."""
        from ironroot.cognition.memory.append_only_store import AppendOnlyBeliefStore

        store = AppendOnlyBeliefStore()

        store.append(b"first", "agt", "run", 1.0)
        store.append(b"second", "agt", "run", 1.0)

        # tamper with internal state
        first_id = next(iter(store._beliefs.keys()))
        original = store._beliefs[first_id]

        # create a tampered record with wrong content
        from ironroot.cognition.memory.append_only_store import BeliefRecord

        tampered = BeliefRecord(
            belief_id=original.belief_id,
            content_hash=original.content_hash,  # keep original hash
            parent_hash=original.parent_hash,
            agent_id=original.agent_id,
            run_id=original.run_id,
            content=b"TAMPERED CONTENT",  # but change content
            confidence=original.confidence,
            created_at=original.created_at,
            evidence_artifact_ids=original.evidence_artifact_ids,
        )
        store._beliefs[first_id] = tampered

        # verification should fail
        assert store.verify_chain() is False


class TestContradictionLinking:
    """tests for contradiction events."""

    def test_record_contradiction(self) -> None:
        """can record a contradiction between beliefs."""
        from ironroot.cognition.memory.contradiction import ContradictionDetector

        detector = ContradictionDetector()

        event = detector.record(
            belief_a_id="bel_001",
            belief_b_id="bel_002",
            detected_by="verifier_agent",
            detection_method="rule_based",
            details="contradictory claims about same entity",
        )

        assert event.contradiction_id.startswith("inc_")
        assert event.belief_a_id == "bel_001"
        assert event.belief_b_id == "bel_002"

    def test_get_contradictions_for_belief(self) -> None:
        """can retrieve contradictions involving a belief."""
        from ironroot.cognition.memory.contradiction import ContradictionDetector

        detector = ContradictionDetector()

        detector.record("bel_001", "bel_002", "agent", "rule", "conflict 1")
        detector.record("bel_001", "bel_003", "agent", "rule", "conflict 2")
        detector.record("bel_004", "bel_005", "agent", "rule", "unrelated")

        # bel_001 has 2 contradictions
        contradictions = detector.get_for_belief("bel_001")
        assert len(contradictions) == 2

        # bel_002 has 1 contradiction (as target)
        contradictions = detector.get_for_belief("bel_002")
        assert len(contradictions) == 1

        # bel_004 has 1 contradiction
        contradictions = detector.get_for_belief("bel_004")
        assert len(contradictions) == 1

    def test_contradiction_does_not_modify_beliefs(self) -> None:
        """recording contradiction creates new event, not modifying beliefs."""
        from ironroot.cognition.memory.append_only_store import AppendOnlyBeliefStore
        from ironroot.cognition.memory.contradiction import ContradictionDetector

        store = AppendOnlyBeliefStore()
        detector = ContradictionDetector()

        # create beliefs
        b1 = store.append(b"claim A", "agt", "run", 1.0)
        b2 = store.append(b"claim not-A", "agt", "run", 1.0)

        original_b1_hash = b1.content_hash
        original_b2_hash = b2.content_hash

        # record contradiction
        detector.record(
            b1.belief_id,
            b2.belief_id,
            "verifier",
            "logical",
            "direct negation",
        )

        # beliefs should be unchanged
        retrieved_b1 = store.get(b1.belief_id)
        retrieved_b2 = store.get(b2.belief_id)

        assert retrieved_b1 is not None
        assert retrieved_b2 is not None
        assert retrieved_b1.content_hash == original_b1_hash
        assert retrieved_b2.content_hash == original_b2_hash

        # chain should still be valid
        assert store.verify_chain()
