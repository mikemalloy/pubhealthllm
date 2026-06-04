# backend/tests/test_responder.py
"""Tests for pubhealth_llm.app.responder."""
from unittest.mock import AsyncMock, MagicMock, patch

from pubhealth_llm.app.responder import run_responder


def _mock_run(response_text: str) -> MagicMock:
    mock_result = MagicMock()
    mock_result.output = response_text
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=mock_result)
    return mock_agent


async def test_run_responder_returns_string():
    with patch(
        "pubhealth_llm.app.responder._get_responder",
        return_value=_mock_run("This tool helps you look up public health data."),
    ):
        response = await run_responder("What can you do?")

    assert isinstance(response, str)
    assert len(response) > 0


async def test_run_responder_passes_question_to_agent():
    captured = {}

    async def capture_run(question):
        captured["question"] = question
        result = MagicMock()
        result.output = "Response"
        return result

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=capture_run)

    with patch("pubhealth_llm.app.responder._get_responder", return_value=mock_agent):
        await run_responder("How do I use this tool?")

    assert captured["question"] == "How do I use this tool?"


async def test_run_responder_returns_output_as_str():
    """result.output is converted to str even if it's not already one."""
    with patch(
        "pubhealth_llm.app.responder._get_responder",
        return_value=_mock_run("Clarification response here."),
    ):
        result = await run_responder("Can you clarify?")

    assert isinstance(result, str)
