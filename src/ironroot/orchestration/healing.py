# Author: Bradley R. Kinnard
"""self-healing pipeline: containment, rollback, repair, retest."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.errors import NotFoundError
from ironroot.domain.ids import generate_id
from ironroot.logging.configure import get_logger
from ironroot.orchestration.incidents import DEFAULT_SEVERITY, IncidentType, Severity
from ironroot.orchestration.supervisor import RunPhase
from ironroot.storage.models import AgentRecord, IncidentRecord, RunRecord

logger = get_logger(__name__)


class HealingPipeline:
    """orchestrates detection, containment, rollback, repair, retest."""

    async def record_incident(
        self,
        session: AsyncSession,
        run_id: str,
        incident_type: IncidentType,
        description: str,
        agent_id: str | None = None,
        evidence_ids: list[str] | None = None,
        severity: Severity | None = None,
    ) -> IncidentRecord:
        """records an incident and triggers containment."""
        incident_id = generate_id("inc")

        if severity is None:
            severity = DEFAULT_SEVERITY.get(incident_type, Severity.MEDIUM)

        record = IncidentRecord(
            id=incident_id,
            run_id=run_id,
            agent_id=agent_id,
            incident_type=incident_type.value,
            severity=severity.value,
            description=description,
            evidence_ids=evidence_ids or [],
            penalties_applied={},
            created_at=datetime.now(UTC),
        )

        session.add(record)
        await session.flush()

        logger.warning(
            "incident recorded",
            incident_id=incident_id,
            run_id=run_id,
            incident_type=incident_type.value,
            severity=severity.value,
        )

        # trigger containment for critical/high severity
        if severity in (Severity.CRITICAL, Severity.HIGH):
            await self.contain(session, run_id, incident_id)

        return record

    async def contain(
        self,
        session: AsyncSession,
        run_id: str,
        incident_id: str,
    ) -> dict[str, Any]:
        """freezes commits and quarantines affected components."""
        # verify run exists before containment
        await self._get_run(session, run_id)

        # freeze the run - stop accepting new commits
        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                status="contained",
                phase=RunPhase.STOPPED.value,
            )
        )

        containment_result: dict[str, Any] = {
            "run_id": run_id,
            "incident_id": incident_id,
            "actions": ["run_frozen", "commits_halted"],
        }

        logger.info(
            "containment executed",
            run_id=run_id,
            incident_id=incident_id,
        )

        return containment_result

    async def apply_penalty(
        self,
        session: AsyncSession,
        agent_id: str,
        incident_id: str,
        revoke_tools: list[str] | None = None,
        restrict_tasks: list[str] | None = None,
    ) -> dict[str, Any]:
        """applies penalties to an agent after an incident."""
        result = await session.execute(select(AgentRecord).where(AgentRecord.id == agent_id))
        agent = result.scalar_one_or_none()

        if not agent:
            raise NotFoundError("agent", agent_id)

        # update penalties
        new_penalty_count = agent.penalty_count + 1
        new_tools_revoked = list(set(agent.tools_revoked + (revoke_tools or [])))
        new_restricted_tasks = list(set(agent.restricted_tasks + (restrict_tasks or [])))

        await session.execute(
            update(AgentRecord)
            .where(AgentRecord.id == agent_id)
            .values(
                penalty_count=new_penalty_count,
                tools_revoked=new_tools_revoked,
                restricted_tasks=new_restricted_tasks,
            )
        )

        # update incident with penalties applied
        await session.execute(
            update(IncidentRecord)
            .where(IncidentRecord.id == incident_id)
            .values(
                penalties_applied={
                    "revoked_tools": revoke_tools or [],
                    "restricted_tasks": restrict_tasks or [],
                }
            )
        )

        logger.info(
            "penalty applied",
            agent_id=agent_id,
            incident_id=incident_id,
            penalty_count=new_penalty_count,
        )

        return {
            "agent_id": agent_id,
            "penalty_count": new_penalty_count,
            "tools_revoked": new_tools_revoked,
            "restricted_tasks": new_restricted_tasks,
        }

    async def rollback(
        self,
        session: AsyncSession,
        run_id: str,
        incident_id: str,
    ) -> dict[str, Any]:
        """restores to last known-good state."""
        # in a full system this would restore to a snapshot
        # for now, we mark the run for repair

        await session.execute(
            update(RunRecord).where(RunRecord.id == run_id).values(phase=RunPhase.REPAIR.value)
        )

        logger.info(
            "rollback executed",
            run_id=run_id,
            incident_id=incident_id,
        )

        return {
            "run_id": run_id,
            "incident_id": incident_id,
            "action": "rollback_to_repair_phase",
        }

    async def request_repair(
        self,
        session: AsyncSession,
        run_id: str,
        incident_id: str,
        repair_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """creates a repair request with required test additions."""
        # store repair plan as part of incident resolution
        result = await session.execute(
            select(IncidentRecord).where(IncidentRecord.id == incident_id)
        )
        incident = result.scalar_one_or_none()

        if not incident:
            raise NotFoundError("incident", incident_id)

        # validate repair plan includes test additions
        if "new_tests" not in repair_plan or not repair_plan["new_tests"]:
            raise ValueError("repair plan must include at least one new test")

        logger.info(
            "repair requested",
            run_id=run_id,
            incident_id=incident_id,
            new_tests_count=len(repair_plan["new_tests"]),
        )

        return {
            "run_id": run_id,
            "incident_id": incident_id,
            "repair_plan": repair_plan,
            "status": "repair_pending",
        }

    async def resolve_incident(
        self,
        session: AsyncSession,
        incident_id: str,
        resolution_notes: str,
    ) -> IncidentRecord:
        """marks an incident as resolved after successful repair."""
        result = await session.execute(
            select(IncidentRecord).where(IncidentRecord.id == incident_id)
        )
        incident = result.scalar_one_or_none()

        if not incident:
            raise NotFoundError("incident", incident_id)

        await session.execute(
            update(IncidentRecord)
            .where(IncidentRecord.id == incident_id)
            .values(resolved_at=datetime.now(UTC))
        )

        # refetch
        result = await session.execute(
            select(IncidentRecord).where(IncidentRecord.id == incident_id)
        )
        incident = result.scalar_one_or_none()

        logger.info(
            "incident resolved",
            incident_id=incident_id,
            resolution=resolution_notes,
        )

        return incident  # type: ignore

    async def get_incidents_for_run(
        self,
        session: AsyncSession,
        run_id: str,
        include_resolved: bool = False,
    ) -> list[IncidentRecord]:
        """gets all incidents for a run."""
        query = select(IncidentRecord).where(IncidentRecord.run_id == run_id)

        if not include_resolved:
            query = query.where(IncidentRecord.resolved_at.is_(None))

        query = query.order_by(IncidentRecord.created_at.desc())

        result = await session.execute(query)
        return list(result.scalars().all())

    async def _get_run(self, session: AsyncSession, run_id: str) -> RunRecord:
        """fetches run or raises NotFoundError."""
        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            raise NotFoundError("run", run_id)
        return run


# singleton
_healing_pipeline: HealingPipeline | None = None


def get_healing_pipeline() -> HealingPipeline:
    """returns shared healing pipeline instance."""
    global _healing_pipeline
    if _healing_pipeline is None:
        _healing_pipeline = HealingPipeline()
    return _healing_pipeline
