# backend/tests/test_orchestrator.py
"""Tests for pubhealth_llm.app.orchestrator — run_ask() routing."""
from unittest.mock import AsyncMock, patch

from pubhealth_llm.app.schemas import (
    AskResponse,
    Plan,
    PublicHealthResponse,
)
from pubhealth_llm.app.orchestrator import run_ask

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CHAT_PLAN = Plan(
    intent="user asking what the tool can do",
    mode="chat",
    artifact_type=None,
    dispatch_target="responder",
    confidence=0.9,
)

_ARTIFACT_PLAN = Plan(
    intent="diabetes statistics in Travis County TX",
    mode="artifact",
    artifact_type="report",
    dispatch_target="reporter",
    confidence=0.95,
)

_MINIMAL_PHR = PublicHealthResponse(
    summary="Diabetes rates in Travis County are elevated at 11.2% of adults.",
    evidence=["Travis County diabetes rate: 11.2% (CDC PLACES 2022)"],
    statistics=[],
    caveats=["Survey-based estimates; may lag 1–2 years."],
    sources=["CDC PLACES 2023, https://www.cdc.gov/places"],
    disclaimer=(
        "This tool provides decision support only. All recommendations "
        "require validation by qualified public health professionals. "
        "Data reflects historical surveillance and may not capture "
        "current conditions."
    ),
)

# ---------------------------------------------------------------------------
# Chat path
# ---------------------------------------------------------------------------


async def test_run_ask_chat_mode_returns_chat_response():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(return_value="This tool looks up public health data."),
        ),
    ):
        response = await run_ask("What can you do?")

    assert response.mode == "chat"
    assert response.artifact is None
    assert response.chat_message == "This tool looks up public health data."
    assert response.meta.intent == _CHAT_PLAN.intent


async def test_run_ask_chat_mode_does_not_call_run_agent():
    run_agent_mock = AsyncMock()
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(return_value="Hi"),
        ),
        patch("pubhealth_llm.app.orchestrator.run_agent", run_agent_mock),
    ):
        await run_ask("Hello")

    run_agent_mock.assert_not_called()

# ---------------------------------------------------------------------------
# Artifact path
# ---------------------------------------------------------------------------


async def test_run_ask_artifact_mode_returns_artifact_response():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
    ):
        response = await run_ask("What is the diabetes rate in Travis County TX?")

    assert response.mode == "artifact"
    assert response.artifact is not None
    assert response.artifact.type == "report"
    assert response.meta.intent == _ARTIFACT_PLAN.intent


async def test_run_ask_artifact_payload_contains_public_health_response():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
    ):
        response = await run_ask("Diabetes in Travis County")

    payload = response.artifact.payload
    assert payload["summary"] == _MINIMAL_PHR.summary
    assert payload["evidence"] == _MINIMAL_PHR.evidence
    assert payload["caveats"] == _MINIMAL_PHR.caveats


async def test_run_ask_artifact_mode_does_not_call_responder():
    responder_mock = AsyncMock()
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
        patch("pubhealth_llm.app.orchestrator.run_responder", responder_mock),
    ):
        await run_ask("County data question")

    responder_mock.assert_not_called()

# ---------------------------------------------------------------------------
# Envelope contract
# ---------------------------------------------------------------------------


async def test_run_ask_chat_message_always_present_in_artifact_mode():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
    ):
        response = await run_ask("Any question")

    assert isinstance(response.chat_message, str)
    assert len(response.chat_message) > 0


async def test_run_ask_meta_timing_ms_is_non_negative():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(return_value="Hi"),
        ),
    ):
        response = await run_ask("Hello")

    assert response.meta.timing_ms >= 0


async def test_run_ask_returns_ask_response_instance():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(return_value="Response"),
        ),
    ):
        response = await run_ask("Q")

    assert isinstance(response, AskResponse)


async def test_run_ask_forwards_message_history_to_run_agent():
    run_agent_mock = AsyncMock(return_value=_MINIMAL_PHR)
    history = [{"role": "user", "content": "prior turn"}]

    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch("pubhealth_llm.app.orchestrator.run_agent", run_agent_mock),
    ):
        await run_ask("Follow-up question", message_history=history)

    run_agent_mock.assert_called_once_with("Follow-up question", message_history=history)
