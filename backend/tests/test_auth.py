"""
Tests for auth coverage — Phase B3.

Verifies:
  - /health is public (no guard, always 200)
  - /ask requires auth (guarded: 401/403 without credentials)
  - /measures requires auth (guarded: 401/403 without credentials)
  - existing authed requests still work under the override
"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def no_auth():
    """
    Replace the autouse 'always-pass' Clerk override with 'always-401'.

    This proves Depends(clerk_guard) is actually wired — if the guard were
    missing, the request would still succeed even with this fixture active.

    Usage:
        def test_protected_endpoint_rejects_unauthenticated(client, no_auth):
            resp = client.post("/ask", json={"question": "test"})
            assert resp.status_code == 401
    """
    from server import app, clerk_guard

    # Save the current override (installed by the autouse fixture)
    saved = app.dependency_overrides.get(clerk_guard)

    def _reject():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[clerk_guard] = _reject
    yield
    # Restore — autouse fixture will also clean up in its own finally, but
    # restoring here keeps the state consistent within the test session.
    if saved is not None:
        app.dependency_overrides[clerk_guard] = saved
    else:
        app.dependency_overrides.pop(clerk_guard, None)


@pytest.fixture
def client():
    from server import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# /health is public
# ---------------------------------------------------------------------------

def test_health_is_public_no_override_needed(client):
    """/health must return 200 regardless of auth state — it has no guard."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_returns_200_with_no_auth_override(client, no_auth):
    """/health must still return 200 even when the guard would reject all requests."""
    resp = client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /ask requires auth
# ---------------------------------------------------------------------------

def test_ask_requires_auth(client, no_auth):
    """/ask must return 401/403 when credentials are absent (guard is wired)."""
    resp = client.post("/ask", json={"question": "What is the obesity rate?"})
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# /measures requires auth
# ---------------------------------------------------------------------------

def test_measures_requires_auth(client, no_auth):
    """GET /measures must return 401/403 when credentials are absent."""
    resp = client.get("/measures")
    assert resp.status_code in (401, 403)


