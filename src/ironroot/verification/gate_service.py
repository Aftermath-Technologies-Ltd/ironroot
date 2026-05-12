# Author: Bradley R. Kinnard
"""gate service layer for verification and regression gates."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.beliefs import get_belief_service
from ironroot.domain.errors import GateFailed, NotFoundError
from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord, BeliefRecord, GateRecord, RunRecord
from ironroot.verification.falsification import run_falsification
from ironroot.verification.regression import run_regression
from ironroot.verification.replay import compute_chain_digest


def _input_digest(payload: dict[str, Any]) -> str:
    """canonical sha256 of a JSON-serializable input payload.

    Used as the GATE_RESULT belief's ``input_digest`` so re-running a
    gate against the same chain produces a stable digest the auditor
    can compare across runs. ``payload`` MUST include
    ``chain_tip_seq`` (added by the per-gate caller) so two gate
    invocations against the same logical chain state but at different
    chain lengths produce different digests — otherwise two clean runs
    against an unchanged chain would emit byte-identical GATE_RESULT
    beliefs and trip the UNIQUE(content_hash) constraint.
    """
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


async def _chain_tip_seq(session: AsyncSession, run_id: str) -> int:
    """returns the highest seq currently in the chain for ``run_id``.

    Used as a tie-breaker in gate input digests so successive gate
    invocations against the same logical state still produce distinct
    GATE_RESULT belief content hashes.
    """
    result = await session.execute(
        select(func.max(BeliefRecord.seq)).where(BeliefRecord.run_id == run_id)
    )
    value = result.scalar()
    return int(value) if value is not None else 0


class GateService:
    """executes verification gates and stores results as artifacts + beliefs.

    Every gate that runs writes a typed ``GATE_RESULT`` belief to the
    chain via ``BeliefService.append_gate_result`` so the decision is
    itself part of the append-only history (Phase 2a.4). Failure to
    append the GATE_RESULT belief is non-fatal: the gate's pass/fail
    signal still propagates and the artifact still lands, but a warning
    is recorded in the gate output.
    """

    async def execute_gates(
        self,
        session: AsyncSession,
        run_id: str,
        check_replay: bool = True,
        check_integrity: bool = True,
        check_invariants: bool = True,
        check_regression: bool = True,
        check_falsification: bool = True,
    ) -> GateRecord:
        """executes all enabled gates and stores results."""
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
            "gate_result_belief_ids": {},
        }

        def _record(name: str, decision: dict[str, Any]) -> None:
            results["gates"][name] = decision
            belief_id = decision.get("gate_result_belief_id")
            if belief_id:
                results["gate_result_belief_ids"][name] = belief_id
            if not decision["passed"]:
                results["overall"] = "failed"

        if check_replay:
            _record("replay", await self._check_replay(session, run_id, run.seed))
        if check_integrity:
            _record("integrity", await self._check_integrity(session, run_id))
        if check_invariants:
            _record("invariants", await self._check_invariants(session, run_id))
        if check_regression:
            _record("regression", await self._check_regression(session, run_id))
        if check_falsification:
            _record("falsification", await self._check_falsification(session, run_id))

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

    async def _append_gate_belief(
        self,
        session: AsyncSession,
        run_id: str,
        gate_name: str,
        passed: bool,
        input_digest: str,
        decision_details: dict[str, Any],
        evidence_belief_ids: list[str] | None = None,
        evidence_artifact_ids: list[str] | None = None,
    ) -> str | None:
        """appends a GATE_RESULT belief; returns id or None on failure.

        The chain may be too broken to accept a new belief (e.g. a
        violation just fired and the chain check failed). We do NOT want
        the gate to crash in that case — the pass/fail signal must still
        propagate. A None return is logged via ``warning`` in the gate's
        decision dict for the operator.
        """
        belief_service = get_belief_service()
        try:
            belief = await belief_service.append_gate_result(
                session=session,
                run_id=run_id,
                gate_name=gate_name,
                passed=passed,
                input_digest=input_digest,
                decision_details=decision_details,
                evidence_belief_ids=evidence_belief_ids,
                evidence_artifact_ids=evidence_artifact_ids,
            )
        except Exception:
            return None
        return belief.id

    async def _check_replay(self, session: AsyncSession, run_id: str, seed: int) -> dict[str, Any]:
        """compares live digest to sealed baseline (Phase 1.5)."""
        live_digest = await compute_chain_digest(session, run_id)

        run = (
            await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        ).scalar_one_or_none()
        baseline = run.replay_digest if run is not None else None

        if baseline is None:
            await session.execute(
                update(RunRecord)
                .where(RunRecord.id == run_id)
                .values(
                    replay_digest=live_digest,
                    replay_digest_sealed_at=datetime.now(UTC),
                )
            )
            decision = {
                "passed": True,
                "seed": seed,
                "baselined": True,
                "live_digest": live_digest,
                "baseline_digest": live_digest,
                "details": "no prior baseline; sealed current digest",
            }
        else:
            match = baseline == live_digest
            decision = {
                "passed": match,
                "seed": seed,
                "baselined": False,
                "live_digest": live_digest,
                "baseline_digest": baseline,
                "details": (
                    ""
                    if match
                    else f"replay digest mismatch: baseline={baseline} live={live_digest}"
                ),
            }

        passed_value = bool(decision["passed"])
        chain_tip = await _chain_tip_seq(session, run_id)
        replay_input_digest = _input_digest(
            {"live_digest": live_digest, "chain_tip_seq": chain_tip}
        )
        belief_id = await self._append_gate_belief(
            session=session,
            run_id=run_id,
            gate_name="replay",
            passed=passed_value,
            input_digest=replay_input_digest,
            decision_details=decision,
        )
        decision["gate_result_belief_id"] = belief_id
        return decision

    async def _check_integrity(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """checks artifact integrity for a run."""
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

        decision = {
            "passed": all_valid,
            "artifacts_checked": checked,
            "failures": failures,
            "details": "" if all_valid else f"integrity failed for: {failures}",
        }

        chain_tip = await _chain_tip_seq(session, run_id)
        input_payload = {
            "artifact_ids": [a.id for a in artifacts],
            "chain_tip_seq": chain_tip,
        }
        belief_id = await self._append_gate_belief(
            session=session,
            run_id=run_id,
            gate_name="integrity",
            passed=all_valid,
            input_digest=_input_digest(input_payload),
            decision_details=decision,
            evidence_artifact_ids=failures or [a.id for a in artifacts],
        )
        decision["gate_result_belief_id"] = belief_id
        return decision

    async def _check_invariants(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """checks the three declared invariants for a run (Phase 1.6)."""
        from ironroot.domain.invariants import (
            BELIEF_HASH_CHAIN,
            BUDGET_NOT_NEGATIVE,
            RUN_STATE_MACHINE,
        )

        belief_service = get_belief_service()
        chain_valid = await belief_service.verify_chain(session, run_id)

        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        run = result.scalar_one_or_none()

        valid_statuses = {"pending", "running", "completed", "stopped", "failed"}
        state_valid = run is not None and run.status in valid_statuses

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
                pass

        all_valid = chain_valid and state_valid and budget_valid
        decision = {
            "passed": all_valid,
            "chain_valid": chain_valid,
            "state_valid": state_valid,
            "budget_valid": budget_valid,
            "violations": violations,
            "violation_belief_ids": violation_belief_ids,
            "details": "" if all_valid else "; ".join(v["details"] for v in violations),
        }

        chain_tip = await _chain_tip_seq(session, run_id)
        input_payload = {
            "chain_valid": chain_valid,
            "state_valid": state_valid,
            "budget_valid": budget_valid,
            "chain_tip_seq": chain_tip,
        }
        gate_belief_id = await self._append_gate_belief(
            session=session,
            run_id=run_id,
            gate_name="invariants",
            passed=all_valid,
            input_digest=_input_digest(input_payload),
            decision_details=decision,
            evidence_belief_ids=violation_belief_ids,
        )
        decision["gate_result_belief_id"] = gate_belief_id
        return decision

    async def _check_regression(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """runs the registered regression suite for this run's kind (Phase 2a.2).

        Empty-incident-list is NOT a free pass. The gate fails if any
        registered check fails OR any IncidentRecord exists for the run.
        Misconfigured runs (no suite for the kind) raise from
        ``run_regression`` and surface as a gate failure rather than a
        silent pass.
        """
        try:
            report = await run_regression(session, run_id)
        except ValueError as exc:
            decision = {
                "passed": False,
                "error": str(exc),
                "details": f"regression suite resolution failed: {exc}",
            }
            belief_id = await self._append_gate_belief(
                session=session,
                run_id=run_id,
                gate_name="regression",
                passed=False,
                input_digest=_input_digest({"error": str(exc)}),
                decision_details=decision,
            )
            decision["gate_result_belief_id"] = belief_id
            return decision

        decision = report.to_dict()
        decision["passed"] = report.passed
        decision["details"] = (
            ""
            if report.passed
            else (
                f"regression failed: failed_checks={list(report.failed_checks())}, "
                f"incident_count={report.incident_count}"
            )
        )

        chain_tip = await _chain_tip_seq(session, run_id)
        input_payload = {
            "suite_name": report.suite_name,
            "run_kind": report.run_kind,
            "check_names": [r.check_name for r in report.results],
            "chain_tip_seq": chain_tip,
        }
        offending_belief_ids: list[str] = []
        for r in report.results:
            offending_belief_ids.extend(r.offending_belief_ids)

        belief_id = await self._append_gate_belief(
            session=session,
            run_id=run_id,
            gate_name="regression",
            passed=report.passed,
            input_digest=_input_digest(input_payload),
            decision_details=decision,
            evidence_belief_ids=offending_belief_ids,
        )
        decision["gate_result_belief_id"] = belief_id
        return decision

    async def _check_falsification(self, session: AsyncSession, run_id: str) -> dict[str, Any]:
        """runs every registered falsifier against the live chain (Phase 2a.1).

        Passes iff no falsifier produced evidence. The empty-registry
        case raises from ``run_falsification`` and surfaces as a gate
        failure, never a silent pass.
        """
        try:
            report = await run_falsification(session, run_id)
        except ValueError as exc:
            decision = {
                "passed": False,
                "error": str(exc),
                "details": f"falsification gate misconfigured: {exc}",
            }
            belief_id = await self._append_gate_belief(
                session=session,
                run_id=run_id,
                gate_name="falsification",
                passed=False,
                input_digest=_input_digest({"error": str(exc)}),
                decision_details=decision,
            )
            decision["gate_result_belief_id"] = belief_id
            return decision

        passed = not report.any_falsified
        decision = report.to_dict()
        decision["passed"] = passed
        decision["details"] = (
            "" if passed else f"falsified claims: {list(report.falsified_claims)}"
        )

        offending_belief_ids: list[str] = []
        offending_artifact_ids: list[str] = []
        for a in report.attempts:
            if a.evidence is None:
                continue
            offending_belief_ids.extend(a.evidence.offending_belief_ids)
            offending_artifact_ids.extend(a.evidence.offending_artifact_ids)

        chain_tip = await _chain_tip_seq(session, run_id)
        input_payload = {
            "claim_names": [a.claim_name for a in report.attempts],
            "chain_tip_seq": chain_tip,
        }
        belief_id = await self._append_gate_belief(
            session=session,
            run_id=run_id,
            gate_name="falsification",
            passed=passed,
            input_digest=_input_digest(input_payload),
            decision_details=decision,
            evidence_belief_ids=offending_belief_ids,
            evidence_artifact_ids=offending_artifact_ids,
        )
        decision["gate_result_belief_id"] = belief_id
        return decision

    async def reseal_replay_baseline(self, session: AsyncSession, run_id: str) -> str:
        """forces a re-seal of the replay digest baseline.

        Used after an intentional, audited mutation of the chain (e.g.,
        a self-healing restoration that wrote observation/inference
        beliefs). Without this, the replay gate would treat the new
        rows as drift and report ``passed=False`` forever.

        Returns the freshly sealed digest. This is a tamper-class event
        for audit purposes — every caller should justify why they're
        bypassing the original baseline.
        """
        new_digest = await compute_chain_digest(session, run_id)
        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                replay_digest=new_digest,
                replay_digest_sealed_at=datetime.now(UTC),
            )
        )
        await session.flush()
        return new_digest

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


_gate_service: GateService | None = None


def get_gate_service() -> GateService:
    """returns shared gate service instance."""
    global _gate_service
    if _gate_service is None:
        _gate_service = GateService()
    return _gate_service
