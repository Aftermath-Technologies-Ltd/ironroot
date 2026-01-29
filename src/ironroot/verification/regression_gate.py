# Author: Bradley R. Kinnard
"""regression gate suite execution."""

from dataclasses import dataclass
from typing import Literal

from ironroot.domain.ids import generate_id
from ironroot.domain.time import now_iso


@dataclass
class GateResult:
    """result of a single gate check."""

    gate_name: str
    passed: bool
    artifact_id: str | None
    details: str


@dataclass
class GateSuiteResult:
    """result of running all gates."""

    gate_bundle_id: str
    run_id: str
    overall_status: Literal["passed", "failed"]
    gates: list[GateResult]
    created_at: str


def execute_gate_suite(
    run_id: str,
    replay_ok: bool,
    integrity_ok: bool,
    invariants_ok: bool,
    regression_ok: bool,
) -> GateSuiteResult:
    """executes all gates and produces a bundle."""
    gate_bundle_id = generate_id("gat")

    gates = [
        GateResult(
            gate_name="replay",
            passed=replay_ok,
            artifact_id=None,
            details="" if replay_ok else "replay determinism check failed",
        ),
        GateResult(
            gate_name="integrity",
            passed=integrity_ok,
            artifact_id=None,
            details="" if integrity_ok else "integrity check failed",
        ),
        GateResult(
            gate_name="invariants",
            passed=invariants_ok,
            artifact_id=None,
            details="" if invariants_ok else "invariant violation detected",
        ),
        GateResult(
            gate_name="regression",
            passed=regression_ok,
            artifact_id=None,
            details="" if regression_ok else "regression tests failed",
        ),
    ]

    all_passed = all(g.passed for g in gates)

    return GateSuiteResult(
        gate_bundle_id=gate_bundle_id,
        run_id=run_id,
        overall_status="passed" if all_passed else "failed",
        gates=gates,
        created_at=now_iso(),
    )
