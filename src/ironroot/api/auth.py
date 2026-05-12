# Author: Bradley R. Kinnard
"""API token auth + scope checking for /api/v1 (Phase 3.4).

Tokens are opaque random secrets. Storage uses ``sha256(secret)``; the
service never sees the secret again after issuance. Each token row
carries a scopes list drawn from ``{read, write, admin}``. Scopes are
required-not-sufficient: a route declared ``write`` accepts any token
that includes ``write``; ``admin`` does NOT implicitly grant
``read`` or ``write`` (operators must add them explicitly when
provisioning).

Why opaque instead of JWT: JWTs put a verification cost on every
request and require key rotation discipline. Opaque tokens with a
hashed DB lookup are cheaper to verify (one indexed SELECT), trivially
revocable (set ``revoked_at``), and avoid the "long-lived JWT cannot
be revoked" foot-gun. JWT support is deferred per upgrade-plan §3.4.

Rate limiting is in-process per-token, fixed-window-per-minute. This
is the "v1 enough" surface — production deploys should put a real
rate limiter at the edge. The in-process limiter at least makes the
ceiling visible from one place.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status
from sqlalchemy import select, update

from ironroot.api.deps import DbSessionDep  # noqa: TC001 — used in route signature at runtime
from ironroot.domain.ids import generate_id
from ironroot.settings import get_settings
from ironroot.storage.models import ApiTokenRecord

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


SCOPE_READ = "read"
SCOPE_WRITE = "write"
SCOPE_ADMIN = "admin"
ALL_SCOPES: frozenset[str] = frozenset({SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN})

TOKEN_PREFIX = "ironroot_pat_"
"""Visible token prefix so accidental leaks (logs, screenshots) are
identifiable. The remainder is 32 url-safe bytes of entropy.
"""


def _hash_token(secret: str) -> str:
    """sha256 hex digest used as the storage key for ``secret``."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _validate_scopes(scopes: Iterable[str]) -> list[str]:
    requested = list(scopes)
    unknown = [s for s in requested if s not in ALL_SCOPES]
    if unknown:
        raise ValueError(f"unknown scopes {unknown!r}; valid scopes are {sorted(ALL_SCOPES)!r}")
    if not requested:
        raise ValueError("at least one scope is required")
    # Dedupe while preserving order — tokens with duplicate scopes look like
    # an audit oddity. Caller almost always sends unique scopes anyway.
    seen: set[str] = set()
    out: list[str] = []
    for s in requested:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


@dataclass(frozen=True)
class IssuedToken:
    """Result of ``issue_token``.

    ``secret`` is the only time the raw bearer credential is visible —
    callers must surface it to the operator and discard immediately.
    The DB never sees ``secret``, only its sha256 hash.
    """

    token_id: str
    name: str
    scopes: list[str]
    secret: str


async def issue_token(
    session: AsyncSession,
    *,
    name: str,
    scopes: Iterable[str],
    created_by: str | None = None,
) -> IssuedToken:
    """Generates a new opaque token and inserts the hashed row.

    Returns the secret exactly once. Callers MUST store it themselves;
    a subsequent lookup will only ever see the hash.
    """
    validated_scopes = _validate_scopes(scopes)
    if not name.strip():
        raise ValueError("token name is required")

    raw_secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_secret)
    token_id = generate_id("tok")

    session.add(
        ApiTokenRecord(
            id=token_id,
            name=name,
            token_hash=token_hash,
            scopes=validated_scopes,
            created_at=datetime.now(UTC),
            created_by=created_by,
        )
    )
    await session.flush()
    return IssuedToken(
        token_id=token_id,
        name=name,
        scopes=validated_scopes,
        secret=raw_secret,
    )


async def revoke_token(session: AsyncSession, token_id: str) -> bool:
    """Marks ``token_id`` revoked. Returns True if a row was updated."""
    result = await session.execute(
        update(ApiTokenRecord)
        .where(ApiTokenRecord.id == token_id, ApiTokenRecord.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.flush()
    rowcount = getattr(result, "rowcount", 0)
    return bool(rowcount)


async def list_tokens(session: AsyncSession) -> list[ApiTokenRecord]:
    """Returns all tokens (including revoked ones) ordered by creation desc."""
    result = await session.execute(
        select(ApiTokenRecord).order_by(ApiTokenRecord.created_at.desc())
    )
    return list(result.scalars().all())


@dataclass(frozen=True)
class TokenPrincipal:
    """Authenticated subject attached to a request."""

    token_id: str
    name: str
    scopes: frozenset[str]


# Per-token request counter for the in-process rate limiter. Fixed
# window: we bucket by ``floor(now / 60)``; once the bucket rolls,
# every token gets fresh budget. Single-process by design — the
# limiter is best-effort for v1.
_rate_window_seconds = 60
_rate_buckets: dict[str, tuple[int, int]] = {}


def _rate_check(token_id: str, limit: int) -> bool:
    """Returns True if a new request is allowed against ``token_id``."""
    if limit <= 0:
        return True
    now_bucket = int(time.time() // _rate_window_seconds)
    bucket, count = _rate_buckets.get(token_id, (now_bucket, 0))
    if bucket != now_bucket:
        bucket, count = now_bucket, 0
    if count >= limit:
        _rate_buckets[token_id] = (bucket, count)
        return False
    _rate_buckets[token_id] = (bucket, count + 1)
    return True


def _reset_rate_buckets() -> None:
    """Test helper — clears the in-process rate counters."""
    _rate_buckets.clear()


async def _resolve_principal(
    session: AsyncSession,
    presented: str,
) -> TokenPrincipal:
    """Looks up a token by hash; raises 401 on miss or revocation."""
    token_hash = _hash_token(presented)
    result = await session.execute(
        select(ApiTokenRecord).where(ApiTokenRecord.token_hash == token_hash)
    )
    token: ApiTokenRecord | None = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    if token.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token revoked")

    # last_used_at is best-effort audit. Failure to update should not
    # break authentication.
    try:
        await session.execute(
            update(ApiTokenRecord)
            .where(ApiTokenRecord.id == token.id)
            .values(last_used_at=datetime.now(UTC))
        )
    except Exception as exc:
        logger.debug("api token last_used_at update failed: %s", exc)

    return TokenPrincipal(
        token_id=token.id,
        name=token.name,
        scopes=frozenset(token.scopes or []),
    )


def require_scope(scope: str) -> Callable[..., Awaitable[TokenPrincipal]]:
    """Returns a FastAPI dependency that enforces ``scope`` (Phase 3.4).

    Behaviour:

    - If ``settings.auth_required`` is False (the dev default), the
      dependency is a no-op and a synthetic principal with all scopes
      is returned.
    - Otherwise, an ``Authorization: Bearer <token>`` header is
      required; we resolve it to a principal, check that the
      principal's scopes contain ``scope``, and enforce the
      configured per-token rate limit.
    - 401 on missing/invalid/revoked token. 403 on missing scope.
      429 on rate-limit exceeded.
    """
    if scope not in ALL_SCOPES:
        raise ValueError(f"unknown scope {scope!r}")

    async def _dep(
        request: Request,
        session: DbSessionDep,
    ) -> TokenPrincipal:
        settings = get_settings()
        if not settings.auth_required:
            return TokenPrincipal(
                token_id="anonymous-debug",
                name="anonymous-debug",
                scopes=frozenset(ALL_SCOPES),
            )

        from fastapi.security.utils import get_authorization_scheme_param

        raw_auth = request.headers.get("Authorization")
        scheme, token = get_authorization_scheme_param(raw_auth)
        if not raw_auth or scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        principal = await _resolve_principal(session, token)

        if scope not in principal.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"scope '{scope}' required; got {sorted(principal.scopes)!r}",
            )

        if not _rate_check(principal.token_id, settings.auth_rate_limit_per_minute):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
            )

        return principal

    _dep.__name__ = f"require_scope_{scope}"
    return _dep


_WRITE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def require_method_scope(
    request: Request,
    session: DbSessionDep,
) -> TokenPrincipal:
    """Dependency that picks read/write based on the request method.

    GET / HEAD / OPTIONS → ``read`` scope.
    POST / PUT / PATCH / DELETE → ``write`` scope.

    Mounted on the API router so every protected route gets a uniform
    auth check without each route author having to declare the
    matching scope by hand. Routes that need ``admin`` (e.g. the
    ``/tokens`` admin endpoints) declare their own
    ``Depends(require_scope(SCOPE_ADMIN))``.
    """
    settings = get_settings()
    if not settings.auth_required:
        return TokenPrincipal(
            token_id="anonymous-debug",
            name="anonymous-debug",
            scopes=frozenset(ALL_SCOPES),
        )

    required = SCOPE_WRITE if request.method.upper() in _WRITE_METHODS else SCOPE_READ

    from fastapi.security.utils import get_authorization_scheme_param

    raw_auth = request.headers.get("Authorization")
    scheme, token = get_authorization_scheme_param(raw_auth)
    if not raw_auth or scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = await _resolve_principal(session, token)

    if required not in principal.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"scope '{required}' required; got {sorted(principal.scopes)!r}",
        )

    if not _rate_check(principal.token_id, settings.auth_rate_limit_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
        )

    return principal


__all__ = [
    "ALL_SCOPES",
    "SCOPE_ADMIN",
    "SCOPE_READ",
    "SCOPE_WRITE",
    "IssuedToken",
    "TokenPrincipal",
    "_reset_rate_buckets",
    "issue_token",
    "list_tokens",
    "require_method_scope",
    "require_scope",
    "revoke_token",
]
