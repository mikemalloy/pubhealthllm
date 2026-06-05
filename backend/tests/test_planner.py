# backend/tests/test_planner.py
"""Tests for pubhealth_llm.app.planner."""
from unittest.mock import AsyncMock, MagicMock, patch

from pubhealth_llm.app.schemas import ArtifactType, Plan
from pubhealth_llm.app.planner import _FALLBACK_PLAN, plan_request


def _mock_run(plan: Plan) -> AsyncMock:
    """Return a mock agent whose .run() resolves to the given Plan."""
    mock_result = MagicMock()
    mock_result.output = plan
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=mock_result)
    return mock_agent


_ARTIFACT_PLAN = Plan(
    mode="artifact",
    artifact_type=ArtifactType.report,
    intent="get diabetes statistics for Travis County TX",
    reason="named county + disease keyword",
)

_CHAT_PLAN = Plan(
    mode="chat",
    artifact_type=None,
    intent="user asking what the tool can do",
    reason="meta-question about capabilities",
)


async def test_plan_request_routes_data_question_to_artifact():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_ARTIFACT_PLAN)):
        plan = await plan_request("What is the diabetes rate in Travis County TX?")

    assert plan.mode == "artifact"
    assert isinstance(plan.reason, str)
    assert len(plan.reason) > 0


async def test_plan_request_routes_conversational_to_chat():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_CHAT_PLAN)):
        plan = await plan_request("What can this tool do?")

    assert plan.mode == "chat"
    assert plan.artifact_type is None


async def test_plan_request_falls_back_on_llm_error():
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with patch("pubhealth_llm.app.planner._get_planner", return_value=mock_agent):
        plan = await plan_request("Any question")

    assert plan.mode == "artifact"
    assert plan.artifact_type == ArtifactType.report


def test_fallback_plan_is_artifact_mode():
    assert _FALLBACK_PLAN.mode == "artifact"
    assert _FALLBACK_PLAN.artifact_type == ArtifactType.report
    assert "fallback" in _FALLBACK_PLAN.reason.lower()


async def test_plan_request_returns_plan_instance():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_ARTIFACT_PLAN)):
        plan = await plan_request("Rank counties by obesity in Texas")

    assert isinstance(plan, Plan)


async def test_plan_request_falls_back_on_env_error():
    """EnvironmentError (missing API key) is caught and returns fallback."""
    mock_agent_factory = MagicMock(side_effect=EnvironmentError("ANTHROPIC_API_KEY not set"))

    with patch("pubhealth_llm.app.planner._get_planner", mock_agent_factory):
        plan = await plan_request("Any question")

    assert plan.mode == "artifact"
    assert plan.artifact_type == ArtifactType.report
