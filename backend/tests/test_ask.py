"""Tests for POST /ask — Phase B1.

The conftest autouse fixture handles Clerk auth override.
run_ask is mocked — no real LLM, no DB.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from pubhealth_llm.app.schemas import AskResponse, Meta


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
