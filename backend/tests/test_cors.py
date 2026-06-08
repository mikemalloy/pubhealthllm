"""Tests for CORS origin configuration — Phase F2a task 2.

Tests for get_cors_origins() helper and CORS header behavior.
"""
import pytest


# ---------------------------------------------------------------------------
# Unit tests for get_cors_origins() — pure function, no app startup needed
# ---------------------------------------------------------------------------

DEFAULTS = ["http://localhost:3000", "http://localhost:5173"]


def test_get_cors_origins_defaults(monkeypatch):
    """No CORS_ORIGINS env var → returns exactly the two default origins."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    from server import get_cors_origins
    result = get_cors_origins()
    assert result == DEFAULTS


def test_get_cors_origins_adds_env_origins(monkeypatch):
    """CORS_ORIGINS set → result includes defaults plus the extra origin."""
    monkeypatch.setenv("CORS_ORIGINS", "https://app.vercel.app")
    from server import get_cors_origins
    result = get_cors_origins()
    assert "http://localhost:3000" in result
    assert "http://localhost:5173" in result
    assert "https://app.vercel.app" in result


def test_get_cors_origins_dedupes(monkeypatch):
    """Origin already in defaults is not duplicated in the result."""
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://other.com")
    from server import get_cors_origins
    result = get_cors_origins()
    assert result.count("http://localhost:3000") == 1
    assert "https://other.com" in result


def test_get_cors_origins_strips_whitespace(monkeypatch):
    """Whitespace around each origin in CORS_ORIGINS is stripped and deduped."""
    monkeypatch.setenv("CORS_ORIGINS", " https://app.vercel.app , http://localhost:3000 ")
    from server import get_cors_origins
    result = get_cors_origins()
    assert "https://app.vercel.app" in result
    assert " https://app.vercel.app " not in result
    assert result.count("http://localhost:3000") == 1


# ---------------------------------------------------------------------------
# Integration test — CORS header on a real (test-client) request
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """HTTP test client. Clerk guard is overridden by the conftest autouse fixture."""
    from server import app
    return __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)


def test_cors_header_on_allowed_origin(client):
    """GET /health with an allowed Origin → response includes the ACAO header."""
    resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
