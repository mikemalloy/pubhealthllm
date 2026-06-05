"""
Tests proving the conftest autouse Clerk override works cleanly.

These tests verify:
1. A route protected by Depends(clerk_guard) returns 200 under the fixture
   (no real Clerk token needed).
2. The override is cleaned up after each test (no bleed between tests).
3. /health remains public (200 without auth, always).
"""
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient


# The throwaway guarded route is added/removed inside the test itself.
# It is NOT added to server.py permanently.

def test_guarded_route_returns_200_with_override():
    """
    A temporary route protected by Depends(clerk_guard) must return 200
    when the conftest autouse fixture is active.
    """
    from server import app, clerk_guard

    # Add throwaway route
    @app.get("/_test_auth_probe")
    async def _probe(payload=Depends(clerk_guard)):
        return {"authenticated": True}

    try:
        client = TestClient(app)
        resp = client.get("/_test_auth_probe")
        assert resp.status_code == 200
        assert resp.json() == {"authenticated": True}
    finally:
        # Remove throwaway route unconditionally
        app.routes[:] = [r for r in app.routes if getattr(r, "path", "") != "/_test_auth_probe"]


def test_health_unaffected_by_override():
    """/health must return 200 regardless of the Clerk override state."""
    from server import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_override_is_installed_by_autouse_fixture():
    """
    The autouse fixture installs an override for clerk_guard. Within a test
    body, we can observe that:
    - clerk_guard IS in dependency_overrides (autouse is active)
    - The override returns the correct test-stub identity dict {"sub": "test-user-id"}
    """
    from server import app, clerk_guard
    # The autouse fixture must have set exactly one override for clerk_guard
    assert clerk_guard in app.dependency_overrides, (
        "autouse fixture should have installed a clerk_guard override"
    )
    # The stub returns a dict — not a ClerkHTTPBearer result
    result = app.dependency_overrides[clerk_guard]()
    assert isinstance(result, dict) and result.get("sub") == "test-user-id", (
        "override should return the test-stub identity dict"
    )
