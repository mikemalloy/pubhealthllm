"""
Tests for GET /health.

The health endpoint is public (no auth), returns 200 with a small
JSON status payload. Clerk guard is wired at startup but does not
protect this route.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(scope="module")
def client():
    # Patch Clerk guard init to avoid needing a live JWKS URL in tests
    with patch("server.ClerkHTTPBearer") as mock_guard:
        mock_guard.return_value = lambda: None
        from fastapi.testclient import TestClient
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
