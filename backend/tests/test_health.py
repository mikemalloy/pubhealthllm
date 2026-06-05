"""
Tests for GET /health.

The health endpoint is public (no auth), returns 200 with a small
JSON status payload. The Clerk guard does not protect this route.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """HTTP test client. Clerk guard is overridden by the conftest autouse fixture."""
    from server import app
    return TestClient(app)


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_status_is_ok(client):
    resp = client.get("/health")
    assert resp.json()["status"] == "ok"


def test_health_has_version_key(client):
    resp = client.get("/health")
    assert "version" in resp.json()


def test_health_has_data_key(client):
    resp = client.get("/health")
    assert "data" in resp.json()


def test_health_data_has_db_and_chroma(client):
    resp = client.get("/health")
    data = resp.json()["data"]
    assert "db" in data
    assert "chroma" in data
