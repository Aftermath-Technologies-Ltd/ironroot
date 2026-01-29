# Author: Bradley R. Kinnard
"""artifact retrieval endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ArtifactMetadata(BaseModel):
    """artifact metadata response."""

    artifact_id: str
    content_hash: str
    artifact_type: str
    size_bytes: int
    created_by: str
    created_at: str
    download_url: str | None


@router.get("/{artifact_id}", response_model=ArtifactMetadata)
async def get_artifact(artifact_id: str) -> ArtifactMetadata:
    """returns artifact metadata and download url."""
    # todo: fetch from storage in phase 1
    raise HTTPException(status_code=404, detail=f"artifact not found: {artifact_id}")


@router.get("")
async def list_artifacts(
    run_id: str | None = None,
    artifact_type: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, object]:
    """lists artifacts with optional filters."""
    # todo: query db in phase 1
    return {"artifacts": [], "offset": offset, "limit": limit, "total": 0}
