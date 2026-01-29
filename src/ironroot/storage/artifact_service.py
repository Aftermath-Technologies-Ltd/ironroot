# Author: Bradley R. Kinnard
"""artifact service layer combining storage and metadata."""

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifacts import ArtifactStore
from ironroot.storage.models import ArtifactRecord


class ArtifactService:
    """coordinates artifact storage with metadata persistence."""

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or ArtifactStore()

    async def store_artifact(
        self,
        session: AsyncSession,
        data: bytes,
        artifact_type: str,
        created_by: str,
        run_id: str | None = None,
        filename: str | None = None,
    ) -> ArtifactRecord:
        """stores artifact bytes and creates metadata record."""
        content_hash = self.store.store(data, artifact_type)

        # check if record already exists for this hash
        existing = await session.execute(
            select(ArtifactRecord).where(ArtifactRecord.content_hash == content_hash)
        )
        if record := existing.scalar_one_or_none():
            return record

        artifact_id = generate_id("art")
        record = ArtifactRecord(
            id=artifact_id,
            content_hash=content_hash,
            artifact_type=artifact_type,
            size_bytes=len(data),
            created_by=created_by,
            run_id=run_id,
            filename=filename,
            created_at=datetime.utcnow(),
        )
        session.add(record)
        await session.flush()
        return record

    async def get_by_id(self, session: AsyncSession, artifact_id: str) -> ArtifactRecord | None:
        """fetches artifact metadata by id."""
        result = await session.execute(
            select(ArtifactRecord).where(ArtifactRecord.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def get_by_hash(self, session: AsyncSession, content_hash: str) -> ArtifactRecord | None:
        """fetches artifact metadata by content hash."""
        result = await session.execute(
            select(ArtifactRecord).where(ArtifactRecord.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def list_artifacts(
        self,
        session: AsyncSession,
        run_id: str | None = None,
        artifact_type: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[ArtifactRecord], int]:
        """lists artifacts with optional filters, returns (records, total)."""
        query = select(ArtifactRecord)

        if run_id:
            query = query.where(ArtifactRecord.run_id == run_id)
        if artifact_type:
            query = query.where(ArtifactRecord.artifact_type == artifact_type)

        # count total
        count_query = select(ArtifactRecord.id)
        if run_id:
            count_query = count_query.where(ArtifactRecord.run_id == run_id)
        if artifact_type:
            count_query = count_query.where(ArtifactRecord.artifact_type == artifact_type)
        count_result = await session.execute(count_query)
        total = len(count_result.all())

        # fetch page
        query = query.order_by(ArtifactRecord.created_at.desc())
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        records = list(result.scalars().all())

        return records, total

    def retrieve_data(self, content_hash: str) -> bytes:
        """retrieves artifact bytes by content hash."""
        return self.store.retrieve(content_hash)

    def verify_integrity(self, content_hash: str) -> bool:
        """verifies stored artifact integrity."""
        return self.store.verify(content_hash)

    def get_artifact_path(self, content_hash: str) -> Path:
        """returns local path for artifact download."""
        return self.store._get_artifact_path(content_hash)


# singleton for convenience
_artifact_service: ArtifactService | None = None


def get_artifact_service() -> ArtifactService:
    """returns shared artifact service instance."""
    global _artifact_service
    if _artifact_service is None:
        _artifact_service = ArtifactService()
    return _artifact_service
