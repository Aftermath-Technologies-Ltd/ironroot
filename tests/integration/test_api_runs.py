# Author: Bradley R. Kinnard
"""integration tests for run api."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ironroot.main import app


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
        mock_session = AsyncMock()
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

        mock_session = AsyncMock()
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

        mock_session = AsyncMock()
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

        mock_session = AsyncMock()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.post("/api/v1/runs/run_test123456789/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"

    @patch("ironroot.api.deps.get_session_factory")
    def test_get_trace(self, mock_factory: AsyncMock) -> None:
        """GET /runs/{run_id}/trace returns trace events."""
        mock_session = AsyncMock()
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

        mock_session = AsyncMock()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.get("/api/v1/runs/run_nonexistent")

        assert response.status_code == 404


class TestHealthApi:
    """integration tests for health endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """GET /health returns healthy status."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
