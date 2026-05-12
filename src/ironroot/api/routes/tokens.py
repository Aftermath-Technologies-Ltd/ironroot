# Author: Bradley R. Kinnard
"""Admin endpoints for API token management (Phase 3.4)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.api.auth import (
    SCOPE_ADMIN,
    IssuedToken,
    TokenPrincipal,
    issue_token,
    list_tokens,
    require_scope,
)
from ironroot.api.deps import get_db_session

router = APIRouter()

_admin_dep = require_scope(SCOPE_ADMIN)


class TokenCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    scopes: list[str] = Field(..., min_length=1)


class TokenIssuedResponse(BaseModel):
    """Returned once at creation. ``secret`` is the bearer credential."""

    token_id: str
    name: str
    scopes: list[str]
    secret: str = Field(
        ...,
        description=(
            "Raw bearer secret. Returned exactly once; the server " "never sees this value again."
        ),
    )


class TokenSummary(BaseModel):
    """Public summary; never includes the secret."""

    token_id: str
    name: str
    scopes: list[str]
    created_at: datetime
    created_by: str | None
    last_used_at: datetime | None
    revoked_at: datetime | None


@router.post("", response_model=TokenIssuedResponse, status_code=201)
async def create_token(
    payload: TokenCreateRequest,
    principal: TokenPrincipal = Depends(_admin_dep),
    session: AsyncSession = Depends(get_db_session),
) -> TokenIssuedResponse:
    """Issues a new API token. Requires the ``admin`` scope.

    The returned ``secret`` is the only time the raw bearer credential
    is visible. Clients MUST capture and store it immediately;
    subsequent reads only return the hash.
    """
    try:
        issued: IssuedToken = await issue_token(
            session,
            name=payload.name,
            scopes=payload.scopes,
            created_by=principal.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return TokenIssuedResponse(
        token_id=issued.token_id,
        name=issued.name,
        scopes=issued.scopes,
        secret=issued.secret,
    )


@router.get("", response_model=list[TokenSummary])
async def list_all_tokens(
    _principal: TokenPrincipal = Depends(_admin_dep),
    session: AsyncSession = Depends(get_db_session),
) -> list[TokenSummary]:
    """Lists every token (active + revoked) for audit. Requires ``admin``."""
    rows = await list_tokens(session)
    return [
        TokenSummary(
            token_id=r.id,
            name=r.name,
            scopes=list(r.scopes or []),
            created_at=r.created_at,
            created_by=r.created_by,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
        )
        for r in rows
    ]


@router.delete("/{token_id}", status_code=204)
async def revoke_token_endpoint(
    token_id: str,
    _principal: TokenPrincipal = Depends(_admin_dep),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Revokes ``token_id``. Idempotent: revoking twice is a 404."""
    from ironroot.api.auth import revoke_token

    ok = await revoke_token(session, token_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"token {token_id} not found or already revoked",
        )
