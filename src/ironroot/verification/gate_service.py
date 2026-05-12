# Author: Bradley R. Kinnard
"""gate service layer for verification and regression gates."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.beliefs import get_belief_service
from ironroot.domain.errors import GateFailed, NotFoundError
from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord, GateRecord, RunRecord
from ironroot.verification.replay import compute_chain_digest


class GateService:
    """executes verification gates and stores results as artifacts."""

    async def execute_gates(
        self,
        session: AsyncSession,
        run_id: str,
        check_replay: bool = True,
        check_integrity: bool = True,
        check_invariants: bool = True,
        check_regression: bool = True,
    ) -> GateRecord:
        """executes all enabled gates and stores results."""
        # fetch run
        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            raise NotFoundError("run", run_id)

        # reject gate execution on idle runs - no activity = no meaningful validation
        has_activity = run.steps_used > 0 or run.tool_calls_used > 0 or run.belief_writes_used > 0
        if not has_activity:
            raise ValueError(
                f"cannot execute gates on idle run {run_id}: "
                f"steps_used={run.steps_used}, tool_calls_used={run.tool_calls_used}, "
                f"belief_writes_used={run.belief_writes_used}. "
                "Run must have activity before gate validation is meaningful."
            )

        results: dict[str, Any] = {
            "gates": {},
            "overall": "passed",
        }

        # replay gate
        if check_replay:
            replay_result = await self._check_replay(session, run_id, run.seed)
            results["gates"]["replay"] = replay_result
            if not replay_result["passed"]:
                results["overall"] = "failed"

        # integrity gate
        if check_integrity:
            integrity_result = await self._check_integrity(session, run_id)
            results["gates"]["integrity"] = integrity_result
            if not integrity_result["passed"]:
                results["overall"] = "failed"

        # invariants gate
        if check_invariants:
            invariants_result = await self._check_invariants(session, run_id)
            results["gates"]["invariants"] = invariants_result
            if not invariants_result["passed"]:
                results["overall"] = "failed"

        # regression gate
        if check_regression:
            regression_result = await self._check_regression(session, run_id)
            results["gates"]["regression"] = regression_result
            if not regression_result["passed"]:
                results["overall"] = "failed"

        # store gate bundle as artifact
        artifact_service = get_artifact_service()
        bundle_bytes = json.dumps(results, sort_keys=True).encode()
        artifact = await artifact_service.store_artifact(
            session,
            data=bundle_bytes,
            artifact_type="gate_bundle",
            created_by="gate_service",
            run_id=run_id,
            filename=f"gate_bundle_{run_id}.json",
        )

        # create gate record
        gate_id = generate_id("gat")
        gate_record = GateRecord(
            id=gate_id,
            run_id=run_id,
            gate_type="full_suite",
            passed=results["overall"] == "passed",
            artifact_id=artifact.id,
            results=results,
            executed_at=datetime.now(UTC),
        )

        session.add(gate_record)
        await session.flush()

        return gate_record

    async def _check_replay(self, session: AsyncSession, run_id: str, seed: int) -> dict[str, Any]:
        """checks replay determinism by comparing live digest to sealed baseline.

        Phase 1.5 semantics:

        - If no baseline is sealed yet (first time this gate runs against a
          completed chain), compute the live digest and seal it. Reports
          ``passed=True`` with ``baselined=True`` so an operator knows
          this run established the baseline rather than verifying one.
        - If a baseline is sealed, recompute the live digest and compare.
          Match -> pass. Mismatch -> fail with both digests in the
          evidence so the operator can diff manually.

        The old "re-run verify_chain" implementation was deleted — that
        check is the integrity gate's job. The replay gate now does
        something distinct: detect non-deterministic / tampered chains
        across time.
        """
        live_digest = await compute_chain_digest(session, run_id)

        run = (
            await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        ).scalar_one_or_none()
        baseline = run.replay_digest if run is not None else None

        if baseline is None:
            # First check: seal the baseline.
            await session.execute(
                update(RunRecord)
                .where(RunRecord.id == run_id)
                .values(
                    replay_digest=live_digest,
                    replay_digest_sealed_at=datetime.now(UTC),
                )
            )
            return {
                "passed": True,
                "seed": seed,
                "baselined": True,
                "live_digest": live_digest,
                "baseline_digest": live_digest,
                "details": "no prior baseline; sealed current digest",
            }

        match = baseline == live_digest
        return {
            "passed": match,
            "seed": seed,
            "baselined": False,
            "live_digest": live_digest,
            "baseline_digest": baseline,
            "details": (
                "" if match else f"replay digest mismatch: baseline={baseline} live={live_digest}"
            ),
        }

    async def _check_integrity(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """checks artifact integrity for a run."""
        # fetch all artifacts for this run
        result = await session.execute(
            select(ArtifactRecord).where(ArtifactRecord.run_id == run_id)
        )
        artifacts = list(result.scalars().all())

        artifact_service = get_artifact_service()
        all_valid = True
        checked = 0
        failures: list[str] = []

        for art in artifacts:
            is_valid = artifact_service.verify_integrity(art.content_hash)
            if not is_valid:
                all_valid = False
                failures.append(art.id)
            checked += 1

        return {
            "passed": all_valid,
            "artifacts_checked": checked,
            "failures": failures,
            "details": "" if all_valid else f"integrity failed for: {failures}",
        }

    async def _check_invariants(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """checks the three declared invariants for a run (Phase 1.6).

        Covers all three from ``domain.invariants``: ``belief_hash_chain``,
        ``budget_not_negative``, ``run_state_machine``. The artifact-
        integrity invariant is the integrity gate's job and isn't
        duplicated here.

        Each failed check produces a typed Violation belief
        (BeliefType.VIOLATION) so the violation itself is part of the
        chain and surfaces in audits.
        """
        from ironroot.domain.invariants import (
            BELIEF_HASH_CHAIN,
            BUDGET_NOT_NEGATIVE,
            RUN_STATE_MACHINE,
        )

        belief_service = get_belief_service()
        chain_valid = await belief_service.verify_chain(session, run_id)

        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        run = result.scalar_one_or_none()

        # Run-state-machine invariant — the run's status field is in the
        # known finite set. Tightening to "valid transitions" is Phase 3
        # work (proper lifecycle).
        valid_statuses = {"pending", "running", "completed", "stopped", "failed"}
        state_valid = run is not None and run.status in valid_statuses

        # Budget-not-negative invariant — the third declared invariant
        # that was missing pre-Phase 1.6. Negative budget counters would
        # mean either over-decrement or write-corruption and warrant
        # containment.
        if run is None:
            budget_valid = False
            budget_details = "run not found"
        else:
            negatives = {
                "steps_used": run.steps_used,
                "tool_calls_used": run.tool_calls_used,
                "belief_writes_used": run.belief_writes_used,
            }
            offending = {k: v for k, v in negatives.items() if v < 0}
            budget_valid = not offending
            budget_details = "" if budget_valid else f"negative budgets: {offending}"

        violations: list[dict[str, str]] = []
        if not chain_valid:
            violations.append(
                {
                    "invariant": BELIEF_HASH_CHAIN.name,
                    "details": "verify_chain returned False",
                }
            )
        if not state_valid:
            details = (
                "run not found"
                if run is None
                else f"status '{run.status}' not in {sorted(valid_statuses)}"
            )
            violations.append({"invariant": RUN_STATE_MACHINE.name, "details": details})
        if not budget_valid:
            violations.append({"invariant": BUDGET_NOT_NEGATIVE.name, "details": budget_details})

        # Emit one Violation belief per failed invariant. Violations are
        # appended *after* the chain check has already failed, so they
        # are themselves part of the (now-tampered) chain and visible to
        # audits. We do not require the chain to be valid to record a
        # violation — that would be self-defeating.
        violation_belief_ids: list[str] = []
        for v in violations:
            try:
                belief = await belief_service.create_violation_belief(
                    session,
                    run_id=run_id,
                    agent_id="invariants_gate",
                    invariant_name=v["invariant"],
                    details=v["details"],
                )
                violation_belief_ids.append(belief.id)
            except Exception:
                # Recording the violation must never crash the gate; if
                # the chain is so broken we can't even append a
                # violation, the chain_valid=False signal already tells
                # the operator something is very wrong.
                pass

        all_valid = chain_valid and state_valid and budget_valid
        return {
            "passed": all_valid,
            "chain_valid": chain_valid,
            "state_valid": state_valid,
            "budget_valid": budget_valid,
            "violations": violations,
            "violation_belief_ids": violation_belief_ids,
            "details": "" if all_valid else "; ".join(v["details"] for v in violations),
        }

    async def _check_regression(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """checks regression tests for a run."""
        # placeholder - in real system would run test suite
        # for now, return passed if no incidents recorded
        from ironroot.storage.models import IncidentRecord

        result = await session.execute(
            select(IncidentRecord).where(IncidentRecord.run_id == run_id)
        )
        incidents = list(result.scalars().all())

        no_incidents = len(incidents) == 0

        return {
            "passed": no_incidents,
            "incident_count": len(incidents),
            "details": "" if no_incidents else f"{len(incidents)} incidents found",
        }

    async def get_gate_status(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """gets the latest gate status for a run."""
        result = await session.execute(
            select(GateRecord)
            .where(GateRecord.run_id == run_id)
            .order_by(GateRecord.executed_at.desc())
            .limit(1)
        )
        gate = result.scalar_one_or_none()

        if not gate:
            return {
                "run_id": run_id,
                "status": "pending",
                "artifact_ids": [],
            }

        return {
            "run_id": run_id,
            "status": "passed" if gate.passed else "failed",
            "gate_id": gate.id,
            "artifact_id": gate.artifact_id,
            "results": gate.results,
            "executed_at": gate.executed_at.isoformat(),
        }

    async def require_gate_passed(self, session: AsyncSession, run_id: str) -> None:
        """raises GateFailed if gates have not passed."""
        status = await self.get_gate_status(session, run_id)

        if status["status"] == "pending":
            raise GateFailed("full_suite", "gates have not been executed")

        if status["status"] == "failed":
            raise GateFailed("full_suite", "gates failed")


# singleton
_gate_service: GateService | None = None


def get_gate_service() -> GateService:
    """returns shared gate service instance."""
    global _gate_service
    if _gate_service is None:
        _gate_service = GateService()
    return _gate_service
