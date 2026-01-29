# Author: Bradley R. Kinnard
"""artifact retrieval endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.api.deps import get_db_session
from ironroot.storage.artifact_service import get_artifact_service

router = APIRouter()


class ArtifactMetadata(BaseModel):
    """artifact metadata response."""

    artifact_id: str
    content_hash: str
    artifact_type: str
    size_bytes: int
    created_by: str
    created_at: str
    run_id: str | None
    filename: str | None


class ArtifactListResponse(BaseModel):
    """paginated artifact list response."""

    artifacts: list[ArtifactMetadata]
    offset: int
    limit: int
    total: int


@router.get("/{artifact_id}", response_model=ArtifactMetadata)
async def get_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ArtifactMetadata:
    """returns artifact metadata."""
    service = get_artifact_service()
    record = await service.get_by_id(session, artifact_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"artifact not found: {artifact_id}")

    return ArtifactMetadata(
        artifact_id=record.id,
        content_hash=record.content_hash,
        artifact_type=record.artifact_type,
        size_bytes=record.size_bytes,
        created_by=record.created_by,
        created_at=record.created_at.isoformat(),
        run_id=record.run_id,
        filename=record.filename,
    )


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    """downloads artifact content."""
    service = get_artifact_service()
    record = await service.get_by_id(session, artifact_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"artifact not found: {artifact_id}")

    path = service.get_artifact_path(record.content_hash)
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact file missing")

    filename = record.filename or f"{record.content_hash[:16]}.bin"
    return FileResponse(
        path=path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get("/{artifact_id}/verify")
async def verify_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool | str]:
    """verifies artifact integrity."""
    service = get_artifact_service()
    record = await service.get_by_id(session, artifact_id)

    if not record:
        raise HTTPException(status_code=404, detail=f"artifact not found: {artifact_id}")

    is_valid = service.verify_integrity(record.content_hash)
    return {
        "artifact_id": artifact_id,
        "content_hash": record.content_hash,
        "valid": is_valid,
    }


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    run_id: str | None = None,
    artifact_type: str | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> ArtifactListResponse:
    """lists artifacts with optional filters."""
    service = get_artifact_service()
    records, total = await service.list_artifacts(
        session, run_id=run_id, artifact_type=artifact_type, offset=offset, limit=limit
    )

    artifacts = [
        ArtifactMetadata(
            artifact_id=r.id,
            content_hash=r.content_hash,
            artifact_type=r.artifact_type,
            size_bytes=r.size_bytes,
            created_by=r.created_by,
            created_at=r.created_at.isoformat(),
            run_id=r.run_id,
            filename=r.filename,
        )
        for r in records
    ]

    return ArtifactListResponse(artifacts=artifacts, offset=offset, limit=limit, total=total)
