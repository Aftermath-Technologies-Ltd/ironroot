# Author: Bradley R. Kinnard
"""integration tests for ui api contracts."""

import pytest
from fastapi.testclient import TestClient

from ironroot.main import app


@pytest.fixture
def client() -> TestClient:
    """test client for api."""
    return TestClient(app)


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

    def test_run_create_shape(self, client: TestClient) -> None:
        """run create response has required fields."""
        response = client.post(
            "/api/v1/runs",
            json={"seed": 1234},
        )
        data = response.json()

        assert "run_id" in data
        assert "request_id" in data

    def test_run_status_shape(self, client: TestClient) -> None:
        """run status response has required fields."""
        create_resp = client.post("/api/v1/runs", json={"seed": 1234})
        run_id = create_resp.json()["run_id"]

        response = client.get(f"/api/v1/runs/{run_id}")
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

    def test_trace_shape(self, client: TestClient) -> None:
        """trace response has required fields."""
        create_resp = client.post("/api/v1/runs", json={"seed": 1234})
        run_id = create_resp.json()["run_id"]

        response = client.get(f"/api/v1/runs/{run_id}/trace")
        data = response.json()

        assert "run_id" in data
        assert "events" in data
        assert isinstance(data["events"], list)

    def test_gate_status_shape(self, client: TestClient) -> None:
        """gate status response has required fields."""
        create_resp = client.post("/api/v1/runs", json={"seed": 1234})
        run_id = create_resp.json()["run_id"]

        response = client.get(f"/api/v1/runs/{run_id}/gates/status")
        data = response.json()

        assert "run_id" in data
        assert "status" in data
        assert "artifact_ids" in data
