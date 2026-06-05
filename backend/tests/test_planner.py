# backend/tests/test_planner.py
"""Tests for pubhealth_llm.app.planner."""
from unittest.mock import AsyncMock, MagicMock, patch

from pubhealth_llm.app.schemas import ArtifactType, Plan
from pubhealth_llm.app.planner import _FALLBACK_PLAN, plan_request, make_plan


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

_RANKING_PLAN = Plan(
    mode="artifact",
    artifact_type=ArtifactType.ranking,
    intent="rank counties by obesity rate in Texas",
    reason="ranking request with geographic scope",
)

_COMPARISON_PLAN = Plan(
    mode="artifact",
    artifact_type=ArtifactType.comparison,
    intent="compare heart disease mortality CA vs TX",
    reason="multi-jurisdiction comparison request",
)

_DECISION_TREE_PLAN = Plan(
    mode="artifact",
    artifact_type=ArtifactType.decision_tree,
    intent="cost-effectiveness of diabetes screening in Travis County",
    reason="cost-effectiveness / intervention analysis request",
)


# ---------------------------------------------------------------------------
# Existing plan_request tests (backward compat) — all must still pass
# ---------------------------------------------------------------------------

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
    assert _FALLBACK_PLAN.intent == "fallback"
    assert _FALLBACK_PLAN.reason == "planner_error_or_low_confidence"


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


# ---------------------------------------------------------------------------
# New make_plan() tests
# ---------------------------------------------------------------------------

async def test_make_plan_chat_mode():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_CHAT_PLAN)):
        plan = await make_plan("what can you do?")

    assert plan.mode == "chat"
    assert plan.artifact_type is None


async def test_make_plan_artifact_report():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_ARTIFACT_PLAN)):
        plan = await make_plan("show me obesity stats for Cook County")

    assert plan.mode == "artifact"
    assert plan.artifact_type == ArtifactType.report


async def test_make_plan_artifact_ranking():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_RANKING_PLAN)):
        plan = await make_plan("rank the worst counties for obesity in Texas")

    assert plan.mode == "artifact"
    assert plan.artifact_type == ArtifactType.ranking


async def test_make_plan_artifact_comparison():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_COMPARISON_PLAN)):
        plan = await make_plan("compare mortality CA vs TX")

    assert plan.mode == "artifact"
    assert plan.artifact_type == ArtifactType.comparison


async def test_make_plan_artifact_decision_tree():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_DECISION_TREE_PLAN)):
        plan = await make_plan("is it cost-effective to screen for diabetes in Travis County?")

    assert plan.mode == "artifact"
    assert plan.artifact_type == ArtifactType.decision_tree


async def test_make_plan_falls_back_on_llm_error():
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with patch("pubhealth_llm.app.planner._get_planner", return_value=mock_agent):
        plan = await make_plan("Any question")

    assert plan.mode == "artifact"
    assert plan.artifact_type == ArtifactType.report
    assert plan.intent == "fallback"
    assert plan.reason == "planner_error_or_low_confidence"


async def test_make_plan_returns_plan_instance():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_ARTIFACT_PLAN)):
        plan = await make_plan("Rank counties by obesity in Texas")

    assert isinstance(plan, Plan)


async def test_make_plan_accepts_message_history():
    """message_history param is accepted without error (not forwarded to LLM)."""
    history = [{"role": "user", "content": "prior question"}]
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_ARTIFACT_PLAN)):
        plan = await make_plan("diabetes rates in Cook County", message_history=history)

    assert isinstance(plan, Plan)


def test_plan_request_is_alias_for_make_plan():
    assert plan_request is make_plan
