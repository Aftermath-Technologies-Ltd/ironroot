# Author: Bradley R. Kinnard
"""belief service layer with database persistence and immutability."""

import json
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.errors import ImmutabilityViolation
from ironroot.domain.ids import generate_id, hash_content
from ironroot.storage.models import BeliefRecord, ContradictionRecord


class BeliefService:
    """manages append-only beliefs with hash chain integrity."""

    async def create_belief(
        self,
        session: AsyncSession,
        run_id: str,
        agent_id: str,
        content: dict[str, object],
        confidence: float,
        evidence_ids: list[str] | None = None,
        topic_tags: list[str] | None = None,
    ) -> BeliefRecord:
        """creates a new belief, linking to parent hash."""
        belief_id = generate_id("bel")

        # compute content hash from deterministic json serialization
        content_bytes = json.dumps(content, sort_keys=True).encode()
        content_hash = hash_content(content_bytes)

        # get the latest belief for this run to chain from
        parent_hash = await self._get_latest_hash(session, run_id)

        record = BeliefRecord(
            id=belief_id,
            run_id=run_id,
            agent_id=agent_id,
            content_hash=content_hash,
            parent_hash=parent_hash,
            content=content,
            confidence=confidence,
            evidence_ids=evidence_ids or [],
            topic_tags=topic_tags or [],
            created_at=datetime.now(UTC),
        )

        session.add(record)
        await session.flush()

        # update run belief count
        from ironroot.storage.models import RunRecord

        await session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .values(belief_writes_used=RunRecord.belief_writes_used + 1)
        )

        return record

    async def _get_latest_hash(self, session: AsyncSession, run_id: str) -> str | None:
        """gets the content hash of the most recent belief in this run."""
        result = await session.execute(
            select(BeliefRecord.content_hash)
            .where(BeliefRecord.run_id == run_id)
            .order_by(BeliefRecord.created_at.desc())
            .limit(1)
        )
        row = result.first()
        return row[0] if row else None

    async def get_by_id(self, session: AsyncSession, belief_id: str) -> BeliefRecord | None:
        """fetches a belief by id."""
        result = await session.execute(select(BeliefRecord).where(BeliefRecord.id == belief_id))
        return result.scalar_one_or_none()

    async def get_by_hash(self, session: AsyncSession, content_hash: str) -> BeliefRecord | None:
        """fetches a belief by content hash."""
        result = await session.execute(
            select(BeliefRecord).where(BeliefRecord.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def list_beliefs(
        self,
        session: AsyncSession,
        run_id: str | None = None,
        agent_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[BeliefRecord], int]:
        """lists beliefs with filters, returns (records, total)."""
        query = select(BeliefRecord)

        if run_id:
            query = query.where(BeliefRecord.run_id == run_id)
        if agent_id:
            query = query.where(BeliefRecord.agent_id == agent_id)

        # count
        count_query = select(BeliefRecord.id)
        if run_id:
            count_query = count_query.where(BeliefRecord.run_id == run_id)
        if agent_id:
            count_query = count_query.where(BeliefRecord.agent_id == agent_id)
        count_result = await session.execute(count_query)
        total = len(count_result.all())

        # paginate
        query = query.order_by(BeliefRecord.created_at.asc())
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)

        return list(result.scalars().all()), total

    async def verify_chain(self, session: AsyncSession, run_id: str) -> bool:
        """verifies the hash chain for a run's beliefs."""
        result = await session.execute(
            select(BeliefRecord)
            .where(BeliefRecord.run_id == run_id)
            .order_by(BeliefRecord.created_at.asc())
        )
        beliefs = list(result.scalars().all())

        if not beliefs:
            return True

        # first belief should have no parent
        if beliefs[0].parent_hash is not None:
            return False

        # each subsequent belief should point to previous content hash
        for i in range(1, len(beliefs)):
            if beliefs[i].parent_hash != beliefs[i - 1].content_hash:
                return False

        # verify each content hash is correct
        for belief in beliefs:
            content_bytes = json.dumps(belief.content, sort_keys=True).encode()
            expected_hash = hash_content(content_bytes)
            if belief.content_hash != expected_hash:
                return False

        return True

    async def update_belief(
        self, session: AsyncSession, belief_id: str, content: dict[str, object]
    ) -> None:
        """intentionally raises - beliefs are immutable."""
        raise ImmutabilityViolation(f"beliefs are append-only, cannot update belief {belief_id}")

    async def delete_belief(self, session: AsyncSession, belief_id: str) -> None:
        """intentionally raises - beliefs are immutable."""
        raise ImmutabilityViolation(f"beliefs are append-only, cannot delete belief {belief_id}")


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


# singletons
_belief_service: BeliefService | None = None
_contradiction_service: ContradictionService | None = None


def get_belief_service() -> BeliefService:
    """returns shared belief service instance."""
    global _belief_service
    if _belief_service is None:
        _belief_service = BeliefService()
    return _belief_service


def get_contradiction_service() -> ContradictionService:
    """returns shared contradiction service instance."""
    global _contradiction_service
    if _contradiction_service is None:
        _contradiction_service = ContradictionService()
    return _contradiction_service
