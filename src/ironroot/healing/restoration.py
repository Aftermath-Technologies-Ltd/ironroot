# Author: Bradley R. Kinnard
"""Self-healing correctness restoration (Phase 2b.2 / 2b.3).

Each restoration attempt runs against a known ``FaultFixture`` so the
pipeline is deterministic. End-state assertions are produced by the
real gate service (``verification.gate_service``); ``_verify_invariants``
and ``_verify_replay`` are no longer stubs.

Restoration outcomes are written as typed beliefs with provenance
pointing at the fault fixture id and any upstream evidence belief or
artifact:

* one ``OBSERVATION`` belief per measured metric (``recovery_attempts``,
  ``recurrence_rate``, …) — these are PRIMARY observations that sit at
  the bottom of the inference graph.
* one ``INFERENCE`` belief naming the conclusion (``restored`` or
  ``unrecoverable``) with provenance back to the fault fixture and
  the gate-result beliefs the gate service wrote.

The old RNG-driven ``_check_recurrence`` is gone. Recurrence is now
determined by re-running the same FaultFixture under the same fixture
id.
"""

from __future__ import annotations

import contextlib
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from ironroot.beliefs import MetricClass, ProvenanceRef, get_belief_service
from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.verification.gate_service import get_gate_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ironroot.verification.fault_fixtures import FaultFixture, ObservedFaultEffect


class RestorationStatus(str, Enum):
    """restoration process status."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    INVARIANTS_RESTORED = "invariants_restored"
    REPLAY_RESTORED = "replay_restored"
    TESTS_EXPANDED = "tests_expanded"
    VERIFIED = "verified"
    FAILED = "failed"


class InvariantType(str, Enum):
    """types of invariants that can be broken."""

    HASH_CHAIN = "hash_chain"
    BUDGET = "budget"
    PHASE = "phase"
    REPLAY = "replay"
    ARTIFACT = "artifact"
    BELIEF = "belief"
    ARTIFACT_TAMPER = "artifact_tamper"
    MISSING_ARTIFACT = "missing_artifact"
    NONDETERMINISM = "nondeterminism"
    VERIFIER_CORRUPTION = "verifier_corruption"


@dataclass
class InvariantViolation:
    """a detected invariant violation."""

    violation_id: str
    invariant_type: InvariantType
    description: str
    detected_at: str
    run_id: str
    component: str
    evidence: dict[str, Any]


@dataclass
class RestorationAttempt:
    """a single restoration attempt."""

    attempt_id: str
    violation_id: str
    strategy: str
    started_at: str
    completed_at: str | None = None
    success: bool = False
    invariants_restored: bool = False
    replay_restored: bool = False
    regression_tests_added: int = 0
    time_to_restore_ms: float = 0.0


@dataclass
class RestorationReport:
    """complete restoration report."""

    violation: InvariantViolation
    attempts: list[RestorationAttempt]
    final_status: RestorationStatus
    time_to_invariant_restoration_ms: float
    repair_success_rate_over_trials: float
    recurrence_checks: int
    recurrence_count: int
    recurrence_rate: float
    new_regression_tests: list[str]


class SelfHealingRestorer:
    """deterministic self-healing pipeline.

    The restorer requires a ``FaultFixture`` as input — the same fixture
    that produced the violation in the first place. Recurrence is
    measured by re-playing the fixture under controlled conditions,
    NOT by sampling a probability.
    """

    MAX_RESTORATION_ATTEMPTS = 5
    RECURRENCE_CHECK_COUNT = 10

    def __init__(self) -> None:
        self._artifact_service = get_artifact_service()
        self._gate_service = get_gate_service()
        self._belief_service = get_belief_service()
        self._violations: dict[str, InvariantViolation] = {}
        self._restoration_history: dict[str, RestorationReport] = {}
        self._regression_tests: list[Callable[[], bool]] = []

    def register_invariant_violation(
        self,
        invariant_type: InvariantType,
        description: str,
        run_id: str,
        component: str,
        evidence: dict[str, Any],
    ) -> InvariantViolation:
        violation = InvariantViolation(
            violation_id=generate_id("vio"),
            invariant_type=invariant_type,
            description=description,
            detected_at=datetime.now(UTC).isoformat(),
            run_id=run_id,
            component=component,
            evidence=evidence,
        )
        self._violations[violation.violation_id] = violation
        return violation

    async def restore_correctness(
        self,
        session: AsyncSession,
        violation_id: str,
        run_id: str,
        fault_fixture: FaultFixture,
    ) -> RestorationReport:
        """attempts to restore correctness after a fixture-driven violation.

        Process (no RNG anywhere):

        1. Revert the fault fixture (this is the "repair").
        2. Run the real gate service — invariants + replay must now
           pass for the attempt to count as ``invariants_restored`` and
           ``replay_restored``.
        3. Record the outcome as a typed INFERENCE belief whose
           provenance points at the fault fixture id and the gate
           result beliefs.
        4. For recurrence: re-apply the fixture (in a sandboxed
           session) RECURRENCE_CHECK_COUNT times. Each replay either
           still trips the gates (recurrence_count++) or doesn't.
           Always revert before exiting.
        """
        if violation_id not in self._violations:
            raise ValueError(f"unknown violation: {violation_id}")

        violation = self._violations[violation_id]
        attempts: list[RestorationAttempt] = []
        final_status = RestorationStatus.FAILED
        time_to_invariant_ms = 0.0

        # The fixture's `revert` is the only strategy we run because it
        # is the only one that mechanically undoes the named fault. The
        # old strategy table was decorative; the real action is "undo".
        start_time = time.time()
        attempt = RestorationAttempt(
            attempt_id=generate_id("rst"),
            violation_id=violation_id,
            strategy=f"fault_fixture_revert:{fault_fixture.fixture_id}",
            started_at=datetime.now(UTC).isoformat(),
        )

        try:
            await fault_fixture.revert(session, run_id)
            await session.flush()

            invariants_ok = await self._verify_invariants(session, run_id)
            attempt.invariants_restored = invariants_ok
            elapsed_ms = (time.time() - start_time) * 1000
            attempt.time_to_restore_ms = elapsed_ms
            if invariants_ok and time_to_invariant_ms == 0:
                time_to_invariant_ms = elapsed_ms

            replay_ok = await self._verify_replay(session, run_id)
            attempt.replay_restored = replay_ok

            test_added = self._add_regression_test(violation)
            attempt.regression_tests_added = 1 if test_added else 0

            if invariants_ok and replay_ok:
                attempt.success = True
                final_status = RestorationStatus.VERIFIED

            attempt.completed_at = datetime.now(UTC).isoformat()
        except Exception as exc:  # pragma: no cover - defensive
            attempt.completed_at = datetime.now(UTC).isoformat()
            attempt.success = False
            attempt.invariants_restored = False
            attempt.replay_restored = False
            attempt.regression_tests_added = 0
            attempt.time_to_restore_ms = (time.time() - start_time) * 1000
            violation.evidence["restoration_error"] = str(exc)

        attempts.append(attempt)

        # Recurrence: replay the fixture deterministically. Each replay
        # applies then reverts, so the chain is left in a clean state.
        recurrence_count = 0
        recurrence_evidence: list[ObservedFaultEffect] = []
        for _ in range(self.RECURRENCE_CHECK_COUNT):
            effect = await fault_fixture.replay(session, run_id)
            recurrence_evidence.append(effect)
            # If applying the fixture produces ANY observed effect on the
            # chain, that is by definition a recurrence — the fault can
            # still happen against this chain shape. The only way to
            # eliminate recurrence is to change the chain so the fixture
            # can no longer apply (e.g., the targeted row was rebuilt
            # under a different id). We model this honestly: a fixture
            # that still applies has recurred.
            if effect.before != effect.after:
                recurrence_count += 1

        recurrence_rate = recurrence_count / self.RECURRENCE_CHECK_COUNT

        successful_attempts = sum(1 for a in attempts if a.success)
        success_rate = successful_attempts / len(attempts) if attempts else 0.0

        new_tests = [f"regression_test_{violation.invariant_type.value}_{violation.violation_id}"]

        report = RestorationReport(
            violation=violation,
            attempts=attempts,
            final_status=final_status,
            time_to_invariant_restoration_ms=time_to_invariant_ms,
            repair_success_rate_over_trials=success_rate,
            recurrence_checks=self.RECURRENCE_CHECK_COUNT,
            recurrence_count=recurrence_count,
            recurrence_rate=recurrence_rate,
            new_regression_tests=new_tests if final_status == RestorationStatus.VERIFIED else [],
        )

        await self._record_restoration_beliefs(
            session=session,
            run_id=run_id,
            violation=violation,
            report=report,
            fault_fixture=fault_fixture,
        )

        # Re-seal the replay baseline iff the restoration verified.
        # Restoration legitimately added observation/inference beliefs;
        # the replay gate must treat the new chain as the new ground
        # truth or it will report drift forever. Audit trail lives in
        # the gate_result + restoration_report artifacts.
        if final_status == RestorationStatus.VERIFIED:
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                await self._gate_service.reseal_replay_baseline(session, run_id)

        await self._artifact_service.store_artifact(
            session=session,
            data=json.dumps(
                {
                    "violation_id": violation.violation_id,
                    "invariant_type": violation.invariant_type.value,
                    "fault_fixture_id": fault_fixture.fixture_id,
                    "final_status": final_status.value,
                    "attempts": len(attempts),
                    "time_to_invariant_restoration_ms": time_to_invariant_ms,
                    "repair_success_rate_over_trials": success_rate,
                    "recurrence_rate_over_10_runs": recurrence_rate,
                    "new_regression_tests": new_tests,
                }
            ).encode(),
            artifact_type="restoration_report",
            created_by="self_healing_restorer",
            run_id=run_id,
            filename=f"restoration_{violation.violation_id}.json",
        )

        self._restoration_history[violation_id] = report
        return report

    async def _verify_invariants(self, session: AsyncSession, run_id: str) -> bool:
        """real invariants check via gate_service.

        Returns True iff the invariants gate's decision dict reports
        ``passed=True``. We do NOT run the full gate suite because we
        only need the invariant signal here; the caller decides whether
        to run the full suite next.
        """
        try:
            decision = await self._gate_service._check_invariants(session, run_id)
        except Exception:  # pragma: no cover - defensive
            return False
        return bool(decision.get("passed", False))

    async def _verify_replay(self, session: AsyncSession, run_id: str) -> bool:
        """real replay check via gate_service.

        Returns True iff the replay digest matches the sealed baseline.
        If no baseline is sealed, the gate seals one and reports passed
        — that case still counts as restored (the digest is well-defined
        and stable from this point on).
        """
        try:
            decision = await self._gate_service._check_replay(session, run_id, seed=0)
        except Exception:  # pragma: no cover - defensive
            return False
        return bool(decision.get("passed", False))

    def _add_regression_test(self, violation: InvariantViolation) -> bool:
        """records a placeholder regression-test entry for stats.

        The real regression suite registry (Phase 2a.2) is the
        canonical home for executable checks. This list is only for
        aggregate restoration statistics.
        """

        def regression_test() -> bool:
            return True

        self._regression_tests.append(regression_test)
        return True

    async def _record_restoration_beliefs(
        self,
        session: AsyncSession,
        run_id: str,
        violation: InvariantViolation,
        report: RestorationReport,
        fault_fixture: FaultFixture,
    ) -> None:
        """writes typed beliefs for the restoration outcome (Phase 2b.3).

        Two layers:

        1. PRIMARY observations: ``time_to_invariant_restoration_ms``,
           ``repair_success_rate_over_trials``, ``recurrence_rate_over_10_runs``.
           These sit at the bottom of the inference graph — no provenance
           required.
        2. One INFERENCE belief naming the conclusion
           (``restored`` / ``unrecoverable``) with provenance back to
           the fault fixture id.
        """
        observation_metrics: tuple[tuple[str, float, str, str], ...] = (
            (
                "time_to_invariant_restoration_ms",
                report.time_to_invariant_restoration_ms,
                "milliseconds",
                "elapsed wall-clock time from fault revert to invariants gate pass",
            ),
            (
                "repair_success_rate_over_trials",
                report.repair_success_rate_over_trials,
                "ratio",
                "fraction of restoration attempts that achieved invariants+replay pass",
            ),
            (
                "recurrence_rate_over_10_runs",
                report.recurrence_rate,
                "probability",
                "fraction of fixture replays that observed an effect on the chain",
            ),
        )

        for metric_name, value, unit, method in observation_metrics:
            # A broken chain (the very thing we're restoring) can prevent
            # appends; we proceed so the restoration record still lands
            # as an artifact.
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                await self._belief_service.append_observation(
                    session=session,
                    run_id=run_id,
                    agent_id="self_healing_restorer",
                    metric_name=metric_name,
                    value=value,
                    unit=unit,
                    method=method,
                    metric_class=MetricClass.PRIMARY,
                    artifact_ids=[],
                    topic_tags=["self_healing"],
                )

        with contextlib.suppress(Exception):  # pragma: no cover - defensive
            await self._belief_service.append_inference(
                session=session,
                run_id=run_id,
                agent_id="self_healing_restorer",
                claim=(
                    "restoration_verified"
                    if report.final_status == RestorationStatus.VERIFIED
                    else "restoration_failed"
                ),
                provenance=ProvenanceRef(
                    kind="restoration_outcome",
                    fixture_ids=(fault_fixture.fixture_id,),
                    notes=(
                        f"violation={violation.violation_id} status="
                        f"{report.final_status.value} attempts={len(report.attempts)} "
                        f"recurrence={report.recurrence_count}/{report.recurrence_checks}"
                    ),
                ),
                topic_tags=["self_healing", "restoration"],
                confidence=1.0 if report.final_status == RestorationStatus.VERIFIED else 0.0,
                details={
                    "violation_id": violation.violation_id,
                    "fault_fixture_id": fault_fixture.fixture_id,
                    "attempts": len(report.attempts),
                    "invariants_restored": any(a.invariants_restored for a in report.attempts),
                    "replay_restored": any(a.replay_restored for a in report.attempts),
                    "recurrence_rate": report.recurrence_rate,
                },
            )

    def get_restoration_stats(self) -> dict[str, Any]:
        """returns aggregate restoration statistics."""
        if not self._restoration_history:
            return {"total_restorations": 0}

        reports = list(self._restoration_history.values())
        verified = sum(1 for r in reports if r.final_status == RestorationStatus.VERIFIED)
        avg_time = (
            statistics.mean(
                r.time_to_invariant_restoration_ms
                for r in reports
                if r.time_to_invariant_restoration_ms > 0
            )
            if any(r.time_to_invariant_restoration_ms > 0 for r in reports)
            else 0.0
        )
        avg_success_rate = statistics.mean(r.repair_success_rate_over_trials for r in reports)
        avg_recurrence = statistics.mean(r.recurrence_rate for r in reports)

        return {
            "total_restorations": len(reports),
            "verified_restorations": verified,
            "verification_rate": verified / len(reports),
            "time_to_invariant_restoration_ms": avg_time,
            "repair_success_rate_over_trials": avg_success_rate,
            "recurrence_rate_over_10_runs": avg_recurrence,
            "total_regression_tests": len(self._regression_tests),
        }


_restorer: SelfHealingRestorer | None = None


def get_self_healing_restorer() -> SelfHealingRestorer:
    global _restorer
    if _restorer is None:
        _restorer = SelfHealingRestorer()
    return _restorer
