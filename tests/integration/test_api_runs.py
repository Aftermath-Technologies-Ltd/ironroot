# Author: Bradley R. Kinnard
"""integration tests for run api."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ironroot.main import app


def _empty_result() -> MagicMock:
    """Sync Result-like mock: ``execute()`` returns an awaitable result
    whose ``.scalar_one_or_none()`` returns None and ``.all()`` returns []."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    return result


def _make_session() -> AsyncMock:
    """A mock AsyncSession whose ``execute()`` returns an empty result.

    The Phase 3.2 routes call ``session.execute(...)`` to look up
    the latest gate record and the trace beliefs. The legacy mock
    pattern in this file doesn't model that, so we give every
    ``execute`` call an empty result object. ``__aenter__`` returns
    the same session so the dependency's ``async with factory() as
    session`` produces the configured mock, not a child AsyncMock.
    """
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_result())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.fixture
def client() -> TestClient:
    """test client for api with mocked db session."""
    return TestClient(app)


@pytest.fixture
def mock_run_record():
    """creates a mock run record."""
    from unittest.mock import MagicMock

    record = MagicMock()
    record.id = "run_test123456789"
    record.seed = 12345
    record.status = "pending"
    record.phase = "init"
    record.config = {
        "budgets": {"max_steps": 240, "max_tool_calls": 500, "max_belief_writes": 200}
    }
    record.steps_used = 0
    record.tool_calls_used = 0
    record.belief_writes_used = 0
    record.failure_reason = None
    return record


class TestRunsApi:
    """integration tests for /api/v1/runs endpoints."""

    @patch("ironroot.api.routes.runs.get_run_service")
    @patch("ironroot.api.deps.get_session_factory")
    def test_create_run(
        self, mock_factory: AsyncMock, mock_service: AsyncMock, mock_run_record
    ) -> None:
        """POST /runs creates a run."""
        mock_svc = AsyncMock()
        mock_svc.create_run = AsyncMock(return_value=mock_run_record)
        mock_service.return_value = mock_svc

        # mock session factory
        mock_session = _make_session()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/runs",
                json={"seed": 12345},
            )

        assert response.status_code == 201
        data = response.json()
        assert "run_id" in data

    @patch("ironroot.api.routes.runs.get_run_service")
    @patch("ironroot.api.deps.get_session_factory")
    def test_get_run(
        self, mock_factory: AsyncMock, mock_service: AsyncMock, mock_run_record
    ) -> None:
        """GET /runs/{run_id} returns run status."""
        mock_svc = AsyncMock()
        mock_svc.get_run = AsyncMock(return_value=mock_run_record)
        mock_service.return_value = mock_svc

        mock_session = _make_session()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.get("/api/v1/runs/run_test123456789")

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "run_test123456789"
        assert data["status"] == "pending"
        assert data["phase"] == "init"

    @patch("ironroot.api.routes.runs.get_run_service")
    @patch("ironroot.api.deps.get_session_factory")
    def test_start_run(
        self, mock_factory: AsyncMock, mock_service: AsyncMock, mock_run_record
    ) -> None:
        """POST /runs/{run_id}/start starts a run."""
        mock_run_record.status = "running"
        mock_run_record.phase = "propose"

        mock_svc = AsyncMock()
        mock_svc.start_run = AsyncMock(return_value=mock_run_record)
        mock_service.return_value = mock_svc

        mock_session = _make_session()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.post("/api/v1/runs/run_test123456789/start")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["phase"] == "propose"

    @patch("ironroot.api.routes.runs.get_run_service")
    @patch("ironroot.api.deps.get_session_factory")
    def test_stop_run(
        self, mock_factory: AsyncMock, mock_service: AsyncMock, mock_run_record
    ) -> None:
        """POST /runs/{run_id}/stop stops a run."""
        mock_run_record.status = "stopped"
        mock_run_record.phase = "stopped"

        mock_svc = AsyncMock()
        mock_svc.stop_run = AsyncMock(return_value=mock_run_record)
        mock_service.return_value = mock_svc

        mock_session = _make_session()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.post("/api/v1/runs/run_test123456789/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"

    @patch("ironroot.api.deps.get_session_factory")
    def test_get_trace(self, mock_factory: AsyncMock) -> None:
        """GET /runs/{run_id}/trace returns trace events."""
        mock_session = _make_session()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.get("/api/v1/runs/run_test123456789/trace")

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert data["offset"] == 0

    @patch("ironroot.api.routes.runs.get_run_service")
    @patch("ironroot.api.deps.get_session_factory")
    def test_run_not_found(self, mock_factory: AsyncMock, mock_service: AsyncMock) -> None:
        """GET /runs/{run_id} returns 404 for nonexistent run."""
        mock_svc = AsyncMock()
        mock_svc.get_run = AsyncMock(return_value=None)
        mock_service.return_value = mock_svc

        mock_session = _make_session()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.get("/api/v1/runs/run_nonexistent")

        assert response.status_code == 404


class TestHealthApi:
    """Smoke test for the health route surface.

    The Phase 3.1 probe is exercised in detail by
    ``tests/integration/test_health_real.py`` against a real session.
    Here we only assert the route is wired and the response shape is
    stable — using the no-session client would make the DB probe
    error and that's fine, the endpoint never raises.
    """

    def test_health_check_returns_documented_shape(self, client: TestClient) -> None:
        from unittest.mock import AsyncMock

        from ironroot.api.deps import get_db_session
        from ironroot.main import app

        async def _session_override() -> AsyncMock:
            session = AsyncMock()
            session.execute = AsyncMock(side_effect=RuntimeError("no db in this test"))
            yield session

        app.dependency_overrides[get_db_session] = _session_override
        try:
            response = client.get("/api/v1/health")
        finally:
            app.dependency_overrides.pop(get_db_session, None)

        assert response.status_code == 200
        data = response.json()
        for field in ("status", "db", "redis", "artifacts", "chain", "replay", "gates", "worker"):
            assert field in data, f"missing field {field}"
