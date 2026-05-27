"""Tests for the JSON API routes (FastAPI endpoints)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked DB pool."""
    with (
        patch("ai_visibility.web.db.init_pool"),
        patch("ai_visibility.web.db.close_pool"),
        patch("ai_visibility.web.db.get_pool", return_value=MagicMock()),
    ):
        from ai_visibility.web.app import create_app

        app = create_app()
        yield TestClient(app, raise_server_exceptions=False)


SAMPLE_DOCTOR = {
    "id": str(uuid4()),
    "name": "Dr. Teste",
    "specialty": "Dermatologia",
    "city": "Campinas",
    "state": "SP",
    "neighborhood": None,
    "crm": "123456",
    "crm_state": "SP",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "run_count": 2,
    "latest_score": 75.0,
}


class TestListDoctors:
    def test_returns_empty_list(self, client):
        with patch("ai_visibility.web.api_routes.list_doctors_with_counts", return_value=[]):
            resp = client.get("/api/doctors")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_returns_doctors(self, client):
        with patch("ai_visibility.web.api_routes.list_doctors_with_counts", return_value=[SAMPLE_DOCTOR]):
            resp = client.get("/api/doctors")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["name"] == "Dr. Teste"


class TestGetDoctor:
    def test_not_found(self, client):
        with patch("ai_visibility.web.api_routes.get_doctor", return_value=None):
            resp = client.get(f"/api/doctors/{uuid4()}")
            assert resp.status_code == 404

    def test_found(self, client):
        with (
            patch("ai_visibility.web.api_routes.get_doctor", return_value=SAMPLE_DOCTOR),
            patch("ai_visibility.web.api_routes.list_runs_for_doctor", return_value=[]),
        ):
            resp = client.get(f"/api/doctors/{SAMPLE_DOCTOR['id']}")
            assert resp.status_code == 200
            assert resp.json()["name"] == "Dr. Teste"


class TestCreateRun:
    def test_doctor_not_found(self, client):
        with patch("ai_visibility.web.api_routes.get_doctor", return_value=None):
            resp = client.post(
                "/api/runs",
                json={"doctor_id": str(uuid4())},
            )
            assert resp.status_code == 404

    def test_duplicate_run_returns_409(self, client):
        with (
            patch("ai_visibility.web.api_routes.get_doctor", return_value=SAMPLE_DOCTOR),
            patch("ai_visibility.web.api_routes.has_active_run", return_value=True),
        ):
            resp = client.post(
                "/api/runs",
                json={"doctor_id": SAMPLE_DOCTOR["id"]},
            )
            assert resp.status_code == 409
            assert "pending or running" in resp.json()["detail"]


class TestRunStatus:
    def test_not_found(self, client):
        with patch("ai_visibility.web.api_routes.get_run", return_value=None):
            resp = client.get(f"/api/runs/{uuid4()}/status")
            assert resp.status_code == 404


class TestAuthRequired:
    def test_create_doctor_requires_api_key(self, client):
        """When ADMIN_API_KEY is set, POST without header should return 401."""
        with patch("ai_visibility.config.settings.admin_api_key", "test-secret-key"):
            resp = client.post(
                "/api/doctors",
                json={
                    "name": "Dr. Test",
                    "specialty": "Cardiologia",
                    "city": "SP",
                },
            )
            assert resp.status_code == 401

    def test_create_doctor_succeeds_with_valid_key(self, client):
        """With the correct API key, creation should proceed."""
        new_id = str(uuid4())
        new_doctor = {**SAMPLE_DOCTOR, "id": new_id, "run_count": 0, "latest_score": None}
        with (
            patch("ai_visibility.config.settings.admin_api_key", "test-secret-key"),
            patch("ai_visibility.web.api_routes.create_doctor", return_value=new_id),
            patch("ai_visibility.web.api_routes.get_doctor", return_value=new_doctor),
        ):
            resp = client.post(
                "/api/doctors",
                json={
                    "name": "Dr. Test",
                    "specialty": "Cardiologia",
                    "city": "SP",
                },
                headers={"X-API-Key": "test-secret-key"},
            )
            assert resp.status_code == 201

    def test_delete_doctor_requires_api_key(self, client):
        with patch("ai_visibility.config.settings.admin_api_key", "test-secret-key"):
            resp = client.delete(f"/api/doctors/{uuid4()}")
            assert resp.status_code == 401
