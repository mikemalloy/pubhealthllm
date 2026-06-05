# backend/tests/test_orchestrator.py
"""Tests for pubhealth_llm.app.orchestrator — run_ask() lean heuristic routing.

Phase A: single LLM call (run_agent only). Mode derived heuristically from
PublicHealthResponse.statistics — non-empty → artifact, empty → chat.

No planner, no responder on the request path.
"""
from unittest.mock import AsyncMock, patch

import pytest

from pubhealth_llm.app.schemas import (
    ArtifactType,
    AskResponse,
    PublicHealthResponse,
    StatisticEntry,
)
from pubhealth_llm.app.orchestrator import run_ask

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RICH_PHR = PublicHealthResponse(
    summary="Travis County diabetes rate is 11.2% of adults.",
    evidence=["Travis County diabetes rate: 11.2% (CDC PLACES 2022)"],
    statistics=[
        StatisticEntry(
            metric="Diabetes",
            value=11.2,
            unit="% of adults",
            location="Travis County, TX",
            year=2022,
            source="CDC PLACES 2022",
        )
    ],
    caveats=["Survey-based estimates; may lag 1–2 years."],
    sources=["CDC PLACES 2023"],
)

_THIN_PHR = PublicHealthResponse(
    summary="I can help you look up public health statistics.",
    evidence=["Tool capability explanation"],
    statistics=[],  # empty = chat mode
    caveats=[],
    sources=[],
)

# ---------------------------------------------------------------------------
# Test 1 — rich PHR (has statistics) → artifact mode
# ---------------------------------------------------------------------------


async def test_run_ask_rich_phr_returns_artifact_mode():
    with patch(
        "pubhealth_llm.app.orchestrator.run_agent",
        new=AsyncMock(return_value=_RICH_PHR),
    ):
        response = await run_ask("What is the diabetes rate in Travis County, TX?")

    assert response.mode == "artifact"
    assert response.artifact is not None
    assert response.artifact.type == ArtifactType.report
    assert response.artifact.payload == _RICH_PHR.model_dump()


# ---------------------------------------------------------------------------
# Test 2 — thin PHR (no statistics) → chat mode
# ---------------------------------------------------------------------------


async def test_run_ask_thin_phr_returns_chat_mode():
    with patch(
        "pubhealth_llm.app.orchestrator.run_agent",
        new=AsyncMock(return_value=_THIN_PHR),
    ):
        response = await run_ask("What can you do?")

    assert response.mode == "chat"
    assert response.chat_message == _THIN_PHR.summary
    assert response.artifact is None


# ---------------------------------------------------------------------------
# Test 3 — run_agent called exactly once
# ---------------------------------------------------------------------------


async def test_run_ask_calls_run_agent_exactly_once():
    run_agent_mock = AsyncMock(return_value=_RICH_PHR)
    with patch("pubhealth_llm.app.orchestrator.run_agent", run_agent_mock):
        await run_ask("Travis County diabetes stats")

    run_agent_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4 — plan_request and run_responder are NEVER called
# ---------------------------------------------------------------------------


async def test_run_ask_never_calls_plan_request_or_run_responder():
    plan_request_mock = AsyncMock()
    run_responder_mock = AsyncMock()

    with (
        patch("pubhealth_llm.app.orchestrator.run_agent", new=AsyncMock(return_value=_RICH_PHR)),
        patch("pubhealth_llm.app.planner.plan_request", plan_request_mock),
        patch("pubhealth_llm.app.responder.run_responder", run_responder_mock),
    ):
        await run_ask("Travis County diabetes stats")

    plan_request_mock.assert_not_called()
    run_responder_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5 — run_agent raises → graceful chat fallback, never raises
# ---------------------------------------------------------------------------


async def test_run_ask_graceful_fallback_on_agent_error():
    with patch(
        "pubhealth_llm.app.orchestrator.run_agent",
        new=AsyncMock(side_effect=RuntimeError("DB unavailable")),
    ):
        response = await run_ask("Diabetes rates in Cook County")

    assert isinstance(response, AskResponse)
    assert response.mode == "chat"
    assert response.artifact is None
    assert "sorry" in response.chat_message.lower()


# ---------------------------------------------------------------------------
# Test 6 — message_history forwarded to run_agent
# ---------------------------------------------------------------------------


async def test_run_ask_forwards_message_history_to_run_agent():
    run_agent_mock = AsyncMock(return_value=_RICH_PHR)
    history = [{"role": "user", "content": "prior turn"}]

    with patch("pubhealth_llm.app.orchestrator.run_agent", run_agent_mock):
        await run_ask("Follow-up question", message_history=history)

    run_agent_mock.assert_called_once_with("Follow-up question", message_history=history)


# ---------------------------------------------------------------------------
# Test 7 — artifact.title is a non-empty string (derived from summary)
# ---------------------------------------------------------------------------


async def test_run_ask_artifact_title_is_non_empty_string():
    with patch(
        "pubhealth_llm.app.orchestrator.run_agent",
        new=AsyncMock(return_value=_RICH_PHR),
    ):
        response = await run_ask("Travis County diabetes")

    assert isinstance(response.artifact.title, str)
    assert len(response.artifact.title) > 0


# ---------------------------------------------------------------------------
# Test 8 — artifact chat_message is teaser: first 200 chars + "…" when long
# ---------------------------------------------------------------------------


async def test_run_ask_artifact_chat_message_is_teaser_when_summary_long():
    long_summary = "B" * 300  # well over _TEASER_LENGTH
    long_phr = PublicHealthResponse(
        summary=long_summary,
        evidence=["Finding"],
        statistics=[
            StatisticEntry(
                metric="Test",
                value=1.0,
                unit="%",
                location="Somewhere",
                year=2022,
                source="CDC",
            )
        ],
        caveats=["Caveat"],
        sources=["Source"],
    )
    with patch(
        "pubhealth_llm.app.orchestrator.run_agent",
        new=AsyncMock(return_value=long_phr),
    ):
        response = await run_ask("Long summary question")

    assert response.chat_message == "B" * 200 + "…"
    assert len(response.chat_message) == 201


# ---------------------------------------------------------------------------
# Test 9 — meta.timing_ms >= 0
# ---------------------------------------------------------------------------


async def test_run_ask_meta_timing_ms_is_non_negative():
    with patch(
        "pubhealth_llm.app.orchestrator.run_agent",
        new=AsyncMock(return_value=_THIN_PHR),
    ):
        response = await run_ask("Hello")

    assert response.meta.timing_ms >= 0


# ---------------------------------------------------------------------------
# Test 10 — meta.model is non-empty string
# ---------------------------------------------------------------------------


async def test_run_ask_meta_model_is_non_empty():
    with patch(
        "pubhealth_llm.app.orchestrator.run_agent",
        new=AsyncMock(return_value=_THIN_PHR),
    ):
        response = await run_ask("Any question")

    assert isinstance(response.meta.model, str)
    assert len(response.meta.model) > 0


# ---------------------------------------------------------------------------
# Test 11 — return value is AskResponse instance
# ---------------------------------------------------------------------------


async def test_run_ask_returns_ask_response_instance():
    with patch(
        "pubhealth_llm.app.orchestrator.run_agent",
        new=AsyncMock(return_value=_THIN_PHR),
    ):
        response = await run_ask("Q")

    assert isinstance(response, AskResponse)
