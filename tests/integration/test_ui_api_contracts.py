# Author: Bradley R. Kinnard
"""integration tests for ui api contracts."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ironroot.main import app


@pytest.fixture
def client() -> TestClient:
    """test client for api."""
    return TestClient(app)


@pytest.fixture
def mock_run_record():
    """creates a mock run record."""
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


class TestUiApiContracts:
    """tests that ui-facing endpoints return expected shapes."""

    def test_health_shape(self, client: TestClient) -> None:
        """health response has required fields."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert "status" in data
        assert "db" in data
        assert "redis" in data
        assert "artifacts" in data

    @patch("ironroot.api.routes.runs.get_run_service")
    @patch("ironroot.api.deps.get_session_factory")
    def test_run_create_shape(
        self, mock_factory: AsyncMock, mock_service: AsyncMock, mock_run_record
    ) -> None:
        """run create response has required fields."""
        mock_svc = AsyncMock()
        mock_svc.create_run = AsyncMock(return_value=mock_run_record)
        mock_service.return_value = mock_svc

        mock_session = AsyncMock()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.post("/api/v1/runs", json={"seed": 1234})

        assert response.status_code == 201
        data = response.json()
        assert "run_id" in data
        assert "request_id" in data

    @patch("ironroot.api.routes.runs.get_run_service")
    @patch("ironroot.api.deps.get_session_factory")
    def test_run_status_shape(
        self, mock_factory: AsyncMock, mock_service: AsyncMock, mock_run_record
    ) -> None:
        """run status response has required fields."""
        mock_svc = AsyncMock()
        mock_svc.get_run = AsyncMock(return_value=mock_run_record)
        mock_service.return_value = mock_svc

        mock_session = AsyncMock()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.get("/api/v1/runs/run_test123456789")

        data = response.json()

        required_fields = [
            "run_id",
            "status",
            "phase",
            "steps_used",
            "steps_remaining",
            "tool_calls_used",
            "tool_calls_remaining",
            "gate_status",
        ]
        for field in required_fields:
            assert field in data

    @patch("ironroot.api.deps.get_session_factory")
    def test_trace_shape(self, mock_factory: AsyncMock) -> None:
        """trace response has required fields."""
        mock_session = AsyncMock()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.get("/api/v1/runs/run_test123456789/trace")

        data = response.json()
        assert "run_id" in data
        assert "events" in data
        assert isinstance(data["events"], list)

    @patch("ironroot.verification.gate_service.get_gate_service")
    @patch("ironroot.api.deps.get_session_factory")
    def test_gate_status_shape(
        self, mock_factory: AsyncMock, mock_gate_svc: AsyncMock
    ) -> None:
        """gate status response has required fields."""
        mock_svc = AsyncMock()
        mock_svc.get_gate_status = AsyncMock(
            return_value={
                "run_id": "run_test123456789",
                "status": "pending",
                "artifact_ids": [],
            }
        )
        mock_gate_svc.return_value = mock_svc

        mock_session = AsyncMock()
        mock_factory.return_value = lambda: mock_session

        with TestClient(app) as client:
            response = client.get("/api/v1/runs/run_test123456789/gates/status")

        data = response.json()
        assert "run_id" in data
        assert "status" in data
