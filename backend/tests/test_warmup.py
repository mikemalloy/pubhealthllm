"""
Tests for the fast, single-attempt Aurora warm-up path (P1 mitigation).

Two layers:
  1. warmup_aurora_db() helper (tools.py) — single execute_statement, NO retry
     loop, classifies the outcome as ready / warming / error.
  2. GET /warmup endpoint (server.py) — Clerk-guarded, never 500s, never leaks
     ARNs/config in the error detail.

All AWS access is mocked — no live calls in the default run.
"""
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _resuming_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "DatabaseResumingException", "Message": "resuming"}},
        "ExecuteStatement",
    )


# ---------------------------------------------------------------------------
# warmup_aurora_db() helper — classification + no-retry contract
# ---------------------------------------------------------------------------

def test_warmup_aurora_db_ready():
    """A successful SELECT 1 → {"database": "ready"} on a single attempt."""
    from pubhealth_llm.app import tools

    fake = MagicMock()
    fake.cluster_arn = "arn:cluster"
    fake.secret_arn = "arn:secret"
    fake.database = "pubhealth"
    fake.client.execute_statement.return_value = {"records": []}

    with patch.object(tools, "get_db", return_value=fake):
        assert tools.warmup_aurora_db() == {"database": "ready"}

    # Raw boto3 path, called exactly once (bypasses the retry loop).
    fake.client.execute_statement.assert_called_once()


def test_warmup_aurora_db_warming_no_retry():
    """DatabaseResumingException → {"database": "warming"} without retrying."""
    from pubhealth_llm.app import tools

    fake = MagicMock()
    fake.client.execute_statement.side_effect = _resuming_error()

    with patch.object(tools, "get_db", return_value=fake):
        assert tools.warmup_aurora_db() == {"database": "warming"}

    # Single attempt — the point is to return immediately, not wait 30s.
    assert fake.client.execute_statement.call_count == 1


def test_warmup_aurora_db_error_on_other_client_error():
    """A non-resuming ClientError → error with the class name only (no leak)."""
    from pubhealth_llm.app import tools

    fake = MagicMock()
    fake.client.execute_statement.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "secret arn:aws:xyz"}},
        "ExecuteStatement",
    )

    with patch.object(tools, "get_db", return_value=fake):
        result = tools.warmup_aurora_db()

    assert result["database"] == "error"
    assert result["detail"] == "ClientError"
    assert "arn:aws" not in str(result)
    assert "secret" not in str(result)


def test_warmup_aurora_db_error_on_config_missing():
    """get_db() raising (bad config) is caught → error, class name only."""
    from pubhealth_llm.app import tools

    with patch.object(
        tools, "get_db",
        side_effect=ValueError("Missing Aurora configuration arn:aws:rds:secret"),
    ):
        result = tools.warmup_aurora_db()

    assert result == {"database": "error", "detail": "ValueError"}


# ---------------------------------------------------------------------------
# GET /warmup endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from server import app
    return TestClient(app)


@pytest.fixture
def no_auth():
    """Replace the autouse always-pass Clerk override with always-401."""
    from server import app, clerk_guard

    saved = app.dependency_overrides.get(clerk_guard)

    def _reject():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[clerk_guard] = _reject
    yield
    if saved is not None:
        app.dependency_overrides[clerk_guard] = saved
    else:
        app.dependency_overrides.pop(clerk_guard, None)


def test_warmup_endpoint_ready(client):
    """Ready path → 200 {"database": "ready"}."""
    from pubhealth_llm.app import tools

    fake = MagicMock()
    fake.client.execute_statement.return_value = {"records": []}
    with patch.object(tools, "get_db", return_value=fake):
        resp = client.get("/warmup")

    assert resp.status_code == 200
    assert resp.json() == {"database": "ready"}


def test_warmup_endpoint_warming(client):
    """Warming path (mocked DatabaseResumingException) → 200 {"database": "warming"}."""
    from pubhealth_llm.app import tools

    fake = MagicMock()
    fake.client.execute_statement.side_effect = _resuming_error()
    with patch.object(tools, "get_db", return_value=fake):
        resp = client.get("/warmup")

    assert resp.status_code == 200
    assert resp.json() == {"database": "warming"}


def test_warmup_endpoint_error_never_500_no_leak(client):
    """Any other exception → 200 error, class name only, no config leak."""
    from pubhealth_llm.app import tools

    fake = MagicMock()
    fake.client.execute_statement.side_effect = RuntimeError("boom arn:aws:secret:xyz")
    with patch.object(tools, "get_db", return_value=fake):
        resp = client.get("/warmup")

    body = resp.json()
    assert resp.status_code == 200
    assert body["database"] == "error"
    assert body["detail"] == "RuntimeError"
    assert "arn:aws" not in str(body)


def test_warmup_endpoint_requires_auth(client, no_auth):
    """GET /warmup must be guarded — 401/403 without a token."""
    resp = client.get("/warmup")
    assert resp.status_code in (401, 403)
