# Author: Bradley R. Kinnard
"""health check endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """health check response shape."""

    status: Literal["healthy", "degraded", "unhealthy"]
    db: Literal["ok", "error"]
    redis: Literal["ok", "error"]
    artifacts: Literal["ok", "error"]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """returns service readiness, db, redis, and artifact store status."""
    # todo: real connectivity checks in phase 1
    return HealthResponse(
        status="healthy",
        db="ok",
        redis="ok",
        artifacts="ok",
    )
