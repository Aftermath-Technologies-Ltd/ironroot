# Author: Bradley R. Kinnard
"""gate service layer for verification and regression gates."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.cognition.memory.belief_service import get_belief_service
from ironroot.domain.errors import GateFailed, NotFoundError
from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord, GateRecord, RunRecord


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
        has_activity = (
            run.steps_used > 0 or run.tool_calls_used > 0 or run.belief_writes_used > 0
        )
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
        """checks replay determinism for a run."""
        # for now, compute current digest and store it
        # in a real system this would compare against a stored baseline
        belief_service = get_belief_service()
        chain_valid = await belief_service.verify_chain(session, run_id)

        return {
            "passed": chain_valid,
            "seed": seed,
            "chain_valid": chain_valid,
            "details": "" if chain_valid else "belief chain verification failed",
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
        """checks policy invariants for a run."""
        # check belief chain invariants
        belief_service = get_belief_service()
        chain_valid = await belief_service.verify_chain(session, run_id)

        # check run is in valid state
        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        run = result.scalar_one_or_none()

        state_valid = run is not None and run.status in (
            "pending",
            "running",
            "completed",
            "stopped",
            "failed",
        )

        all_valid = chain_valid and state_valid

        return {
            "passed": all_valid,
            "chain_valid": chain_valid,
            "state_valid": state_valid,
            "details": "" if all_valid else "invariant check failed",
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
