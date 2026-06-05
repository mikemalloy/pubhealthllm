# backend/tests/test_orchestrator.py
"""Tests for pubhealth_llm.app.orchestrator — run_ask() routing."""
from unittest.mock import AsyncMock, patch

from pubhealth_llm.app.schemas import (
    ArtifactType,
    AskResponse,
    Plan,
    PublicHealthResponse,
)
from pubhealth_llm.app.orchestrator import run_ask

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CHAT_PLAN = Plan(
    mode="chat",
    artifact_type=None,
    intent="user asking what the tool can do",
    reason="meta-question about capabilities",
)

_ARTIFACT_PLAN = Plan(
    mode="artifact",
    artifact_type=ArtifactType.report,
    intent="diabetes statistics in Travis County TX",
    reason="named county + disease keyword",
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


async def test_run_ask_falls_back_to_reporter_on_responder_error():
    """If responder fails, orchestrator falls back to the reporter path."""
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(side_effect=RuntimeError("LLM down")),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
    ):
        response = await run_ask("What can you do?")

    # Falls back to artifact mode via reporter
    assert response.mode == "artifact"
    assert response.artifact is not None


async def test_run_ask_artifact_teaser_truncates_long_summary():
    """chat_message in artifact mode is truncated to 200 chars + ellipsis."""
    long_summary = "A" * 300  # well over _TEASER_LENGTH
    long_phr = PublicHealthResponse(
        summary=long_summary,
        evidence=["Finding"],
        statistics=[],
        caveats=["Caveat"],
        sources=["Source"],
        disclaimer=(
            "This tool provides decision support only. All recommendations "
            "require validation by qualified public health professionals. "
            "Data reflects historical surveillance and may not capture "
            "current conditions."
        ),
    )
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=long_phr),
        ),
    ):
        response = await run_ask("Long summary question")

    assert response.chat_message == "A" * 200 + "…"
    assert len(response.chat_message) == 201
