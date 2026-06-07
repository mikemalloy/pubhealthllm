"""Tests for POST /ask — Phase B1 + B6.

The conftest autouse fixture handles Clerk auth override.
run_ask is mocked — no real LLM, no DB.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from pubhealth_llm.app.schemas import AskResponse, Artifact, ArtifactType, Meta


# A minimal valid AskResponse for mocking
_MOCK_RESPONSE = AskResponse(
    mode="chat",
    chat_message="Obesity rates in Travis County are elevated.",
    artifact=None,
    meta=Meta(intent="obesity in travis county", model="anthropic:claude-sonnet-4-6", timing_ms=42),
)


@pytest.fixture
def client():
    from server import app
    return TestClient(app)


@pytest.fixture
def mock_run_ask():
    """Patch run_ask so no real LLM or DB is touched."""
    with patch(
        "server.run_ask",
        new=AsyncMock(return_value=_MOCK_RESPONSE),
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_ask_returns_200(client, mock_run_ask):
    resp = client.post("/ask", json={"question": "What is the obesity rate in Travis County?"})
    assert resp.status_code == 200


def test_ask_response_has_mode(client, mock_run_ask):
    resp = client.post("/ask", json={"question": "Obesity rates?"})
    assert "mode" in resp.json()


def test_ask_response_has_chat_message(client, mock_run_ask):
    resp = client.post("/ask", json={"question": "Obesity rates?"})
    assert "chat_message" in resp.json()
    assert resp.json()["chat_message"]  # non-empty


def test_ask_response_has_meta(client, mock_run_ask):
    resp = client.post("/ask", json={"question": "Obesity rates?"})
    assert "meta" in resp.json()


def test_ask_calls_run_ask_once(client, mock_run_ask):
    client.post("/ask", json={"question": "What is the diabetes rate?"})
    mock_run_ask.assert_called_once()


def test_ask_passes_question_to_run_ask(client, mock_run_ask):
    client.post("/ask", json={"question": "What is the diabetes rate?"})
    args, kwargs = mock_run_ask.call_args
    assert args[0] == "What is the diabetes rate?"


def test_ask_passes_message_history_when_provided(client, mock_run_ask):
    history = [{"role": "user", "content": "prior turn"}]
    client.post("/ask", json={"question": "Follow-up?", "message_history": history})
    args, kwargs = mock_run_ask.call_args
    # message_history is the second positional arg or keyword arg
    passed_history = args[1] if len(args) > 1 else kwargs.get("message_history")
    assert passed_history == history


def test_ask_passes_none_message_history_by_default(client, mock_run_ask):
    client.post("/ask", json={"question": "Basic question"})
    args, kwargs = mock_run_ask.call_args
    passed_history = args[1] if len(args) > 1 else kwargs.get("message_history")
    assert passed_history is None


# ---------------------------------------------------------------------------
# Validation — Pydantic handles these as 422
# ---------------------------------------------------------------------------

def test_ask_missing_question_returns_422(client):
    resp = client.post("/ask", json={})
    assert resp.status_code == 422


def test_ask_empty_question_returns_422(client):
    resp = client.post("/ask", json={"question": ""})
    assert resp.status_code == 422


def test_ask_empty_body_returns_422(client):
    resp = client.post("/ask", content=b"", headers={"Content-Type": "application/json"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Mode shape — chat vs artifact (Phase B6)
# ---------------------------------------------------------------------------

# NOTE: AskResponse.chat_message has min_length=1 — it is ALWAYS present.
# In artifact mode the schema docstring says it carries a one-sentence teaser,
# not null.  The artifact field is what distinguishes the two modes.

_MOCK_ARTIFACT_RESPONSE = AskResponse(
    mode="artifact",
    chat_message="Obesity rates are elevated.",  # teaser; required by schema
    artifact=Artifact(
        type=ArtifactType.report,
        title="Obesity Report",
        payload={},
    ),
    meta=Meta(intent="obesity report", model="anthropic:claude-sonnet-4-6", timing_ms=99),
)


@pytest.fixture
def mock_run_ask_artifact():
    """Patch run_ask to return an artifact-mode AskResponse."""
    with patch(
        "server.run_ask",
        new=AsyncMock(return_value=_MOCK_ARTIFACT_RESPONSE),
    ) as m:
        yield m


def test_ask_chat_mode_has_null_artifact(client, mock_run_ask):
    """Chat mode: artifact field must be null, mode must be 'chat'."""
    resp = client.post("/ask", json={"question": "What is the obesity rate?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "chat"
    assert body["artifact"] is None


def test_ask_artifact_mode_has_artifact(client, mock_run_ask_artifact):
    """Artifact mode: artifact field must be non-null, mode must be 'artifact'."""
    resp = client.post("/ask", json={"question": "Give me an obesity report."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "artifact"
    assert body["artifact"] is not None
    assert body["artifact"]["type"] == "report"
    assert body["artifact"]["title"] == "Obesity Report"
