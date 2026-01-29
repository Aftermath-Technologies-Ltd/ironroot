# Author: Bradley R. Kinnard
"""run service layer for lifecycle management."""

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.errors import NotFoundError
from ironroot.domain.ids import generate_id
from ironroot.orchestration.budgets import Budget
from ironroot.orchestration.supervisor import RunPhase, Supervisor
from ironroot.storage.models import RunRecord


class RunService:
    """manages run creation, lifecycle transitions, and budget enforcement."""

    async def create_run(
        self,
        session: AsyncSession,
        seed: int,
        config: dict[str, Any],
    ) -> RunRecord:
        """creates a new run in INIT phase."""
        run_id = generate_id("run")

        record = RunRecord(
            id=run_id,
            seed=seed,
            status="pending",
            phase=RunPhase.INIT.value,
            config=config,
            created_at=datetime.utcnow(),
            steps_used=0,
            tool_calls_used=0,
            belief_writes_used=0,
        )

        session.add(record)
        await session.flush()
        return record

    async def get_run(self, session: AsyncSession, run_id: str) -> RunRecord | None:
        """fetches a run by id."""
        result = await session.execute(select(RunRecord).where(RunRecord.id == run_id))
        return result.scalar_one_or_none()

    async def start_run(self, session: AsyncSession, run_id: str) -> RunRecord:
        """starts a run, transitions from INIT to PROPOSE."""
        run = await self.get_run(session, run_id)
        if not run:
            raise NotFoundError("run", run_id)

        supervisor = Supervisor(run_id, run.seed)
        supervisor.phase = RunPhase(run.phase)
        supervisor.transition_to(RunPhase.PROPOSE)

        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                status="running",
                phase=supervisor.phase.value,
                started_at=datetime.utcnow(),
            )
        )

        return await self.get_run(session, run_id)  # type: ignore

    async def transition_phase(
        self, session: AsyncSession, run_id: str, target_phase: RunPhase
    ) -> RunRecord:
        """transitions run to target phase."""
        run = await self.get_run(session, run_id)
        if not run:
            raise NotFoundError("run", run_id)

        supervisor = Supervisor(run_id, run.seed)
        supervisor.phase = RunPhase(run.phase)
        supervisor.transition_to(target_phase)

        await session.execute(
            update(RunRecord).where(RunRecord.id == run_id).values(phase=supervisor.phase.value)
        )

        return await self.get_run(session, run_id)  # type: ignore

    async def stop_run(
        self, session: AsyncSession, run_id: str, reason: str | None = None
    ) -> RunRecord:
        """hard stops a run, freezes commits."""
        run = await self.get_run(session, run_id)
        if not run:
            raise NotFoundError("run", run_id)

        supervisor = Supervisor(run_id, run.seed)
        supervisor.phase = RunPhase(run.phase)
        supervisor.stop()

        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                status="stopped",
                phase=supervisor.phase.value,
                finished_at=datetime.utcnow(),
                failure_reason=reason,
            )
        )

        return await self.get_run(session, run_id)  # type: ignore

    async def fail_run(self, session: AsyncSession, run_id: str, reason: str) -> RunRecord:
        """marks run as failed."""
        run = await self.get_run(session, run_id)
        if not run:
            raise NotFoundError("run", run_id)

        supervisor = Supervisor(run_id, run.seed)
        supervisor.phase = RunPhase(run.phase)
        supervisor.fail(reason)

        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                status="failed",
                phase=supervisor.phase.value,
                finished_at=datetime.utcnow(),
                failure_reason=reason,
            )
        )

        return await self.get_run(session, run_id)  # type: ignore

    async def finalize_run(self, session: AsyncSession, run_id: str) -> RunRecord:
        """finalizes a successful run."""
        run = await self.get_run(session, run_id)
        if not run:
            raise NotFoundError("run", run_id)

        supervisor = Supervisor(run_id, run.seed)
        supervisor.phase = RunPhase(run.phase)
        supervisor.transition_to(RunPhase.FINALIZE)

        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                status="completed",
                phase=supervisor.phase.value,
                finished_at=datetime.utcnow(),
            )
        )

        return await self.get_run(session, run_id)  # type: ignore

    async def use_budget(
        self,
        session: AsyncSession,
        run_id: str,
        steps: int = 0,
        tool_calls: int = 0,
        belief_writes: int = 0,
    ) -> None:
        """consumes budget, raises BudgetExhausted if exceeded."""
        run = await self.get_run(session, run_id)
        if not run:
            raise NotFoundError("run", run_id)

        config = run.config
        budgets = config.get("budgets", {})

        budget = Budget(
            max_steps=budgets.get("max_steps", 240),
            max_tool_calls=budgets.get("max_tool_calls", 500),
            max_belief_writes=budgets.get("max_belief_writes", 200),
        )

        # load current usage
        budget.steps_used = run.steps_used
        budget.tool_calls_used = run.tool_calls_used
        budget.belief_writes_used = run.belief_writes_used

        # try to consume
        if steps:
            budget.use_step(steps)
        if tool_calls:
            budget.use_tool_call(tool_calls)
        if belief_writes:
            budget.use_belief_write(belief_writes)

        # persist
        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(
                steps_used=budget.steps_used,
                tool_calls_used=budget.tool_calls_used,
                belief_writes_used=budget.belief_writes_used,
            )
        )

    async def check_budget_exhausted(self, session: AsyncSession, run_id: str) -> bool:
        """checks if any budget is exhausted."""
        run = await self.get_run(session, run_id)
        if not run:
            raise NotFoundError("run", run_id)

        config = run.config
        budgets = config.get("budgets", {})

        budget = Budget(
            max_steps=budgets.get("max_steps", 240),
            max_tool_calls=budgets.get("max_tool_calls", 500),
            max_belief_writes=budgets.get("max_belief_writes", 200),
        )

        budget.steps_used = run.steps_used
        budget.tool_calls_used = run.tool_calls_used
        budget.belief_writes_used = run.belief_writes_used

        return budget.is_exhausted()

    async def list_runs(
        self,
        session: AsyncSession,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[RunRecord], int]:
        """lists runs with optional filters."""
        query = select(RunRecord)

        if status:
            query = query.where(RunRecord.status == status)

        # count
        count_query = select(RunRecord.id)
        if status:
            count_query = count_query.where(RunRecord.status == status)
        count_result = await session.execute(count_query)
        total = len(count_result.all())

        # paginate
        query = query.order_by(RunRecord.created_at.desc())
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)

        return list(result.scalars().all()), total


# singleton
_run_service: RunService | None = None


def get_run_service() -> RunService:
    """returns shared run service instance."""
    global _run_service
    if _run_service is None:
        _run_service = RunService()
    return _run_service
