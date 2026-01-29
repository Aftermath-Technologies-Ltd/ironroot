# Author: Bradley R. Kinnard
"""integration tests for run api."""

import pytest
from fastapi.testclient import TestClient

from ironroot.main import app


@pytest.fixture
def client() -> TestClient:
    """test client for api."""
    return TestClient(app)


class TestRunsApi:
    """integration tests for /api/v1/runs endpoints."""

    def test_create_run(self, client: TestClient) -> None:
        """POST /runs creates a run."""
        response = client.post(
            "/api/v1/runs",
            json={
                "seed": 12345,
                "max_steps": 100,
                "max_tool_calls": 50,
                "max_belief_writes": 20,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["run_id"].startswith("run_")

    def test_get_run(self, client: TestClient) -> None:
        """GET /runs/{run_id} returns run status."""
        # first create a run
        create_resp = client.post(
            "/api/v1/runs",
            json={"seed": 12345},
        )
        run_id = create_resp.json()["run_id"]

        # then get it
        response = client.get(f"/api/v1/runs/{run_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["status"] == "pending"

    def test_start_run(self, client: TestClient) -> None:
        """POST /runs/{run_id}/start starts a run."""
        create_resp = client.post(
            "/api/v1/runs",
            json={"seed": 12345},
        )
        run_id = create_resp.json()["run_id"]

        response = client.post(f"/api/v1/runs/{run_id}/start")

        assert response.status_code == 200
        assert response.json()["status"] == "started"

    def test_stop_run(self, client: TestClient) -> None:
        """POST /runs/{run_id}/stop stops a run."""
        create_resp = client.post(
            "/api/v1/runs",
            json={"seed": 12345},
        )
        run_id = create_resp.json()["run_id"]

        response = client.post(f"/api/v1/runs/{run_id}/stop")

        assert response.status_code == 200
        assert response.json()["status"] == "stopped"

    def test_get_trace(self, client: TestClient) -> None:
        """GET /runs/{run_id}/trace returns trace events."""
        create_resp = client.post(
            "/api/v1/runs",
            json={"seed": 12345},
        )
        run_id = create_resp.json()["run_id"]

        response = client.get(f"/api/v1/runs/{run_id}/trace")

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert data["run_id"] == run_id


class TestHealthApi:
    """integration tests for health endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """GET /health returns healthy status."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
