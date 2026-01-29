# Author: Bradley R. Kinnard
"""unit tests for verification and regression gates."""

from ironroot.domain.errors import GateFailed
from ironroot.verification.regression_gate import execute_gate_suite
from ironroot.verification.replay import (
    ReplayDigest,
    compute_replay_digest,
    compute_trace_digest,
    verify_replay,
)


class TestReplayDigest:
    """tests for replay determinism checking."""

    def test_compute_trace_digest_deterministic(self) -> None:
        """same events produce same digest."""
        events = [b"event1", b"event2", b"event3"]

        digest1 = compute_trace_digest(events)
        digest2 = compute_trace_digest(events)

        assert digest1 == digest2

    def test_compute_trace_digest_order_matters(self) -> None:
        """different order produces different digest."""
        events1 = [b"event1", b"event2"]
        events2 = [b"event2", b"event1"]

        digest1 = compute_trace_digest(events1)
        digest2 = compute_trace_digest(events2)

        assert digest1 != digest2

    def test_compute_replay_digest(self) -> None:
        """computes full replay digest."""
        digest = compute_replay_digest(
            run_id="run_001",
            seed=42,
            trace_events=[b"event1", b"event2"],
            artifact_hashes=["abc123", "def456"],
            belief_chain_hash="chain_hash",
        )

        assert digest.run_id == "run_001"
        assert digest.seed == 42
        assert digest.belief_chain_hash == "chain_hash"
        assert len(digest.artifact_hashes) == 2

    def test_verify_replay_matches(self) -> None:
        """identical digests verify as matching."""
        digest1 = compute_replay_digest(
            run_id="run_001",
            seed=42,
            trace_events=[b"event1"],
            artifact_hashes=["hash1"],
            belief_chain_hash="chain",
        )
        digest2 = compute_replay_digest(
            run_id="run_001",
            seed=42,
            trace_events=[b"event1"],
            artifact_hashes=["hash1"],
            belief_chain_hash="chain",
        )

        assert verify_replay(digest1, digest2)

    def test_verify_replay_seed_mismatch(self) -> None:
        """different seeds fail verification."""
        digest1 = ReplayDigest(
            run_id="run_001",
            seed=42,
            trace_hash="same",
            artifact_hashes=("hash1",),
            belief_chain_hash="chain",
        )
        digest2 = ReplayDigest(
            run_id="run_001",
            seed=99,
            trace_hash="same",
            artifact_hashes=("hash1",),
            belief_chain_hash="chain",
        )

        assert not verify_replay(digest1, digest2)

    def test_verify_replay_trace_mismatch(self) -> None:
        """different traces fail verification."""
        digest1 = ReplayDigest(
            run_id="run_001",
            seed=42,
            trace_hash="trace_a",
            artifact_hashes=("hash1",),
            belief_chain_hash="chain",
        )
        digest2 = ReplayDigest(
            run_id="run_001",
            seed=42,
            trace_hash="trace_b",
            artifact_hashes=("hash1",),
            belief_chain_hash="chain",
        )

        assert not verify_replay(digest1, digest2)


class TestGateSuite:
    """tests for gate suite execution."""

    def test_all_gates_pass(self) -> None:
        """all gates passing produces passed result."""
        result = execute_gate_suite(
            run_id="run_001",
            replay_ok=True,
            integrity_ok=True,
            invariants_ok=True,
            regression_ok=True,
        )

        assert result.overall_status == "passed"
        assert all(g.passed for g in result.gates)

    def test_one_gate_fails(self) -> None:
        """one failing gate produces failed result."""
        result = execute_gate_suite(
            run_id="run_001",
            replay_ok=True,
            integrity_ok=False,
            invariants_ok=True,
            regression_ok=True,
        )

        assert result.overall_status == "failed"

        integrity_gate = next(g for g in result.gates if g.gate_name == "integrity")
        assert not integrity_gate.passed

    def test_all_gates_fail(self) -> None:
        """all gates failing produces failed result."""
        result = execute_gate_suite(
            run_id="run_001",
            replay_ok=False,
            integrity_ok=False,
            invariants_ok=False,
            regression_ok=False,
        )

        assert result.overall_status == "failed"
        assert not any(g.passed for g in result.gates)

    def test_gate_bundle_has_id(self) -> None:
        """gate result has bundle id."""
        result = execute_gate_suite(
            run_id="run_001",
            replay_ok=True,
            integrity_ok=True,
            invariants_ok=True,
            regression_ok=True,
        )

        assert result.gate_bundle_id.startswith("gat_")

    def test_gate_includes_details_on_failure(self) -> None:
        """failed gates include failure details."""
        result = execute_gate_suite(
            run_id="run_001",
            replay_ok=False,
            integrity_ok=True,
            invariants_ok=True,
            regression_ok=True,
        )

        replay_gate = next(g for g in result.gates if g.gate_name == "replay")
        assert "failed" in replay_gate.details


class TestGateBlocking:
    """tests that gates block promotion on failure."""

    def test_gate_failed_error(self) -> None:
        """GateFailed exception contains gate info."""
        error = GateFailed("integrity", "hash mismatch detected")

        assert error.gate_name == "integrity"
        assert "hash mismatch" in error.reason
        assert "integrity" in str(error)

    def test_gate_failed_code(self) -> None:
        """GateFailed has correct error code."""
        error = GateFailed("regression", "tests failed")

        assert error.code == "GATE_FAILED"
