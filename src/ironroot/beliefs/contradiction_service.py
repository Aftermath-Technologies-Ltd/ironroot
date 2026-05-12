# Author: Bradley R. Kinnard
"""contradiction service (consolidated from cognition.memory.belief_service in Phase 1.7).

Records and queries contradictions between beliefs.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.models import ContradictionRecord


class ContradictionService:
    """manages contradiction events between beliefs."""

    async def record_contradiction(
        self,
        session: AsyncSession,
        belief_id: str,
        contradicts_belief_id: str,
        reason: str,
    ) -> ContradictionRecord:
        """records a new contradiction between two beliefs."""
        contradiction_id = generate_id("inc")
        record = ContradictionRecord(
            id=contradiction_id,
            belief_id=belief_id,
            contradicts_belief_id=contradicts_belief_id,
            reason=reason,
            detected_at=datetime.now(UTC),
        )
        session.add(record)
        await session.flush()
        return record

    async def get_for_belief(
        self, session: AsyncSession, belief_id: str
    ) -> list[ContradictionRecord]:
        """gets all contradictions involving a belief."""
        result = await session.execute(
            select(ContradictionRecord).where(
                (ContradictionRecord.belief_id == belief_id)
                | (ContradictionRecord.contradicts_belief_id == belief_id)
            )
        )
        return list(result.scalars().all())

    async def list_all(
        self, session: AsyncSession, offset: int = 0, limit: int = 100
    ) -> list[ContradictionRecord]:
        """lists all contradictions."""
        result = await session.execute(
            select(ContradictionRecord)
            .order_by(ContradictionRecord.detected_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())


_contradiction_service: ContradictionService | None = None


def get_contradiction_service() -> ContradictionService:
    """returns shared contradiction service instance."""
    global _contradiction_service
    if _contradiction_service is None:
        _contradiction_service = ContradictionService()
    return _contradiction_service
