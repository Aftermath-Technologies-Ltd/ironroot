# Author: Bradley R. Kinnard
"""integration tests for regression gate."""

from ironroot.verification.regression_gate import execute_gate_suite


class TestRegressionGate:
    """tests for gate suite execution."""

    def test_all_pass(self) -> None:
        """all gates passing produces passed status."""
        result = execute_gate_suite(
            run_id="run_test",
            replay_ok=True,
            integrity_ok=True,
            invariants_ok=True,
            regression_ok=True,
        )

        assert result.overall_status == "passed"
        assert result.gate_bundle_id.startswith("gat_")
        assert all(g.passed for g in result.gates)

    def test_any_fail(self) -> None:
        """any gate failing produces failed status."""
        result = execute_gate_suite(
            run_id="run_test",
            replay_ok=True,
            integrity_ok=False,  # one failure
            invariants_ok=True,
            regression_ok=True,
        )

        assert result.overall_status == "failed"

        integrity_gate = next(g for g in result.gates if g.gate_name == "integrity")
        assert not integrity_gate.passed
        assert "integrity" in integrity_gate.details.lower()

    def test_all_fail(self) -> None:
        """all gates failing produces failed status."""
        result = execute_gate_suite(
            run_id="run_test",
            replay_ok=False,
            integrity_ok=False,
            invariants_ok=False,
            regression_ok=False,
        )

        assert result.overall_status == "failed"
        assert all(not g.passed for g in result.gates)

    def test_gate_names(self) -> None:
        """all expected gates are present."""
        result = execute_gate_suite(
            run_id="run_test",
            replay_ok=True,
            integrity_ok=True,
            invariants_ok=True,
            regression_ok=True,
        )

        gate_names = {g.gate_name for g in result.gates}
        assert gate_names == {"replay", "integrity", "invariants", "regression"}
