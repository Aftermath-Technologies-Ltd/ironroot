# Author: Bradley R. Kinnard
"""Phase 3.4: API token auth + scope enforcement tests."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault("IRONROOT_DEBUG", "true")

from ironroot.api.auth import (
    SCOPE_ADMIN,
    SCOPE_READ,
    SCOPE_WRITE,
    _hash_token,
    _reset_rate_buckets,
    issue_token,
    list_tokens,
    revoke_token,
)
from ironroot.api.deps import get_db_session
from ironroot.main import app
from ironroot.settings import Settings, get_settings
from ironroot.storage.models import ApiTokenRecord
from ironroot.storage.postgres import Base


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    with tempfile.TemporaryDirectory() as tmp:
        engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{Path(tmp)/'auth.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield sf
        finally:
            await engine.dispose()


@pytest.fixture
def auth_required_client(
    factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    """TestClient with auth_required=True forced on."""
    _reset_rate_buckets()

    # Force settings to auth-required without flipping debug off
    # (which would also trip the password guard). We rebuild the
    # cached settings instance with explicit auth_enabled=True.
    from ironroot import settings as settings_module

    get_settings.cache_clear()
    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: Settings(
            debug=True,
            db_password="changeme",
            auth_enabled=True,
            _env_file=None,  # type: ignore[call-arg]
        ),
    )
    # The auth module imports `get_settings` directly into its
    # namespace — patch that, too.
    from ironroot.api import auth as auth_module

    monkeypatch.setattr(auth_module, "get_settings", settings_module.get_settings)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _session_override
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        _reset_rate_buckets()


async def _issue(
    factory: async_sessionmaker[AsyncSession], scopes: list[str], name: str = "test"
) -> str:
    async with factory() as session:
        issued = await issue_token(session, name=name, scopes=scopes)
        await session.commit()
    return issued.secret


class TestUnauthenticatedAccess:
    def test_health_does_not_require_auth(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, _ = auth_required_client
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_runs_list_without_token_is_401(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, _ = auth_required_client
        response = client.get("/api/v1/runs")
        assert response.status_code == 401
        assert "Bearer" in response.headers.get("WWW-Authenticate", "")

    def test_create_belief_without_token_is_401(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, _ = auth_required_client
        response = client.post(
            "/api/v1/beliefs",
            json={
                "run_id": "run_x",
                "agent_id": "a",
                "content": {},
                "confidence": 1.0,
            },
        )
        assert response.status_code == 401


class TestScopeEnforcement:
    async def test_read_token_can_get_but_not_post(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, fact = auth_required_client
        secret = await _issue(fact, [SCOPE_READ])
        headers = {"Authorization": f"Bearer {secret}"}

        # GET succeeds (read)
        response = client.get("/api/v1/runs", headers=headers)
        assert response.status_code == 200

        # POST requires write
        response = client.post("/api/v1/runs", json={"seed": 1}, headers=headers)
        assert response.status_code == 403
        assert "scope 'write' required" in response.json()["detail"]

    async def test_write_token_can_post(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, fact = auth_required_client
        secret = await _issue(fact, [SCOPE_READ, SCOPE_WRITE])
        response = client.post(
            "/api/v1/runs",
            json={"seed": 1},
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert response.status_code == 201

    async def test_revoked_token_is_401(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, fact = auth_required_client
        async with fact() as session:
            issued = await issue_token(session, name="rev", scopes=[SCOPE_READ])
            await session.commit()

        async with fact() as session:
            await revoke_token(session, issued.token_id)
            await session.commit()

        response = client.get("/api/v1/runs", headers={"Authorization": f"Bearer {issued.secret}"})
        assert response.status_code == 401
        assert response.json()["detail"] == "token revoked"

    async def test_unknown_token_is_401(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, _ = auth_required_client
        response = client.get(
            "/api/v1/runs",
            headers={"Authorization": "Bearer ironroot_pat_made_up_value"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "invalid token"


class TestAdminScope:
    async def test_create_token_requires_admin(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, fact = auth_required_client
        write_secret = await _issue(fact, [SCOPE_READ, SCOPE_WRITE])
        response = client.post(
            "/api/v1/tokens",
            json={"name": "x", "scopes": [SCOPE_READ]},
            headers={"Authorization": f"Bearer {write_secret}"},
        )
        assert response.status_code == 403

    async def test_create_token_with_admin_returns_secret_once(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, fact = auth_required_client
        admin_secret = await _issue(fact, [SCOPE_ADMIN, SCOPE_READ])
        response = client.post(
            "/api/v1/tokens",
            json={"name": "ci", "scopes": [SCOPE_READ, SCOPE_WRITE]},
            headers={"Authorization": f"Bearer {admin_secret}"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["secret"].startswith("ironroot_pat_")
        # The list endpoint must never expose the secret.
        response = client.get(
            "/api/v1/tokens", headers={"Authorization": f"Bearer {admin_secret}"}
        )
        assert response.status_code == 200
        rows = response.json()
        assert any(r["token_id"] == data["token_id"] for r in rows)
        assert all("secret" not in r for r in rows)

    async def test_revoke_endpoint_is_idempotent_then_404(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    ) -> None:
        client, fact = auth_required_client
        admin_secret = await _issue(fact, [SCOPE_ADMIN])
        # Create a token to revoke.
        response = client.post(
            "/api/v1/tokens",
            json={"name": "to-revoke", "scopes": [SCOPE_READ]},
            headers={"Authorization": f"Bearer {admin_secret}"},
        )
        token_id = response.json()["token_id"]

        response = client.delete(
            f"/api/v1/tokens/{token_id}",
            headers={"Authorization": f"Bearer {admin_secret}"},
        )
        assert response.status_code == 204
        response = client.delete(
            f"/api/v1/tokens/{token_id}",
            headers={"Authorization": f"Bearer {admin_secret}"},
        )
        assert response.status_code == 404


class TestRateLimiting:
    async def test_rate_limit_returns_429(
        self,
        auth_required_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client, fact = auth_required_client
        # Crank the per-minute cap down to 3 for the test.
        from ironroot.api import auth as auth_module

        monkeypatch.setattr(
            auth_module,
            "get_settings",
            lambda: Settings(
                debug=True,
                db_password="changeme",
                auth_enabled=True,
                auth_rate_limit_per_minute=3,
                _env_file=None,  # type: ignore[call-arg]
            ),
        )

        secret = await _issue(fact, [SCOPE_READ])
        headers = {"Authorization": f"Bearer {secret}"}

        for _ in range(3):
            assert client.get("/api/v1/runs", headers=headers).status_code == 200
        response = client.get("/api/v1/runs", headers=headers)
        assert response.status_code == 429
        assert response.json()["detail"] == "rate limit exceeded"


class TestServiceLayer:
    """Direct unit tests for the auth service layer (no HTTP)."""

    async def test_issue_then_lookup_by_hash(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with factory() as session:
            issued = await issue_token(session, name="svc", scopes=[SCOPE_READ, SCOPE_WRITE])
            await session.commit()
        async with factory() as session:
            tokens = await list_tokens(session)
            assert len(tokens) == 1
            assert tokens[0].token_hash == _hash_token(issued.secret)
            assert tokens[0].scopes == [SCOPE_READ, SCOPE_WRITE]
            assert tokens[0].revoked_at is None

    async def test_issue_rejects_unknown_scope(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with factory() as session:
            with pytest.raises(ValueError, match="unknown scopes"):
                await issue_token(session, name="bad", scopes=["root"])

    async def test_issue_rejects_empty_name(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with factory() as session:
            with pytest.raises(ValueError, match="token name"):
                await issue_token(session, name="   ", scopes=[SCOPE_READ])

    async def test_revoke_returns_false_for_unknown(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with factory() as session:
            ok = await revoke_token(session, "tok_does_not_exist")
            assert ok is False

    async def test_token_secret_is_unique_per_call(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with factory() as session:
            a = await issue_token(session, name="a", scopes=[SCOPE_READ])
            b = await issue_token(session, name="b", scopes=[SCOPE_READ])
            await session.commit()
        assert a.secret != b.secret
        assert a.token_id != b.token_id

    def test_hash_is_deterministic(self) -> None:
        assert _hash_token("hello") == _hash_token("hello")
        assert _hash_token("hello") != _hash_token("hellp")
