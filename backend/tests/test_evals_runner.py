# backend/tests/test_evals_runner.py
"""Unit tests for eval runner (mocked agent — no live LLM calls)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import yaml


GOLD_PATH = Path(__file__).parents[1] / "pubhealth_llm" / "evals" / "gold_set.yaml"


def _make_agent_result(tools_called, stats_values=None, sources=None):
    """Build a minimal AgentResult for testing."""
    from pubhealth_llm.app.agent import AgentResult, EvalTrace, ToolEvent
    from pubhealth_llm.app.schemas import PublicHealthResponse, StatisticEntry
    stats = []
    if stats_values:
        for v in stats_values:
            stats.append(StatisticEntry(
                metric=v["metric"], value=v["value"], unit=v.get("unit", "%"),
                location=v.get("location", "Unknown"), source="CDC PLACES 2023",
            ))
    return AgentResult(
        response=PublicHealthResponse(
            summary="Test summary.",
            evidence=["Finding 1"],
            statistics=stats,
            sources=sources or ["CDC PLACES 2023"],
            caveats=["Data is from surveys."],
        ),
        tools_used=tools_called,
        trace=EvalTrace(tool_events=[
            ToolEvent(name=t, args={}, content="") for t in tools_called
        ]),
    )


def test_score_item_tool_accuracy_correct():
    from pubhealth_llm.evals.runner import score_item
    from pubhealth_llm.evals.schemas import GoldItem
    item = GoldItem(
        id="test_001",
        question="Diabetes in Travis County?",
        data_sources=["cdc_places"],
        expected_tools=["tool_get_health_statistics"],
        expected_facts=[],
        is_answerable=True,
        rubric="test",
    )
    agent_result = _make_agent_result(["tool_get_health_statistics"])
    result = score_item(item, agent_result, judge_result=None)
    assert result.tool_selection_score == 1.0


def test_score_item_tool_accuracy_wrong_tool():
    from pubhealth_llm.evals.runner import score_item
    from pubhealth_llm.evals.schemas import GoldItem
    item = GoldItem(
        id="test_002",
        question="Diabetes in Travis County?",
        data_sources=["cdc_places"],
        expected_tools=["tool_get_health_statistics"],
        expected_facts=[],
        is_answerable=True,
        rubric="test",
    )
    agent_result = _make_agent_result(["tool_get_mortality_data"])
    result = score_item(item, agent_result, judge_result=None)
    assert result.tool_selection_score == 0.0


def test_score_item_numeric_match_pass():
    from pubhealth_llm.evals.runner import score_item
    from pubhealth_llm.evals.schemas import GoldItem, ExpectedFact
    item = GoldItem(
        id="test_003",
        question="Diabetes in Travis County?",
        data_sources=["cdc_places"],
        expected_tools=["tool_get_health_statistics"],
        expected_facts=[
            ExpectedFact(metric="Diabetes", location="Travis County, TX",
                         expected_value=9.0, tolerance=0.5)
        ],
        is_answerable=True,
        rubric="test",
    )
    agent_result = _make_agent_result(
        ["tool_get_health_statistics"],
        stats_values=[{"metric": "Diabetes", "value": 9.0, "location": "Travis County, TX"}],
    )
    result = score_item(item, agent_result, judge_result=None)
    assert result.numeric_match_score == 1.0


def test_score_item_numeric_match_fail():
    from pubhealth_llm.evals.runner import score_item
    from pubhealth_llm.evals.schemas import GoldItem, ExpectedFact
    item = GoldItem(
        id="test_004",
        question="Diabetes in Travis County?",
        data_sources=["cdc_places"],
        expected_tools=["tool_get_health_statistics"],
        expected_facts=[
            ExpectedFact(metric="Diabetes", location="Travis County, TX",
                         expected_value=9.0, tolerance=0.5)
        ],
        is_answerable=True,
        rubric="test",
    )
    agent_result = _make_agent_result(
        ["tool_get_health_statistics"],
        stats_values=[{"metric": "Diabetes", "value": 20.0, "location": "Travis County, TX"}],
    )
    result = score_item(item, agent_result, judge_result=None)
    assert result.numeric_match_score == 0.0


def test_score_item_abstention_ood_correct():
    from pubhealth_llm.evals.runner import score_item
    from pubhealth_llm.evals.schemas import GoldItem
    item = GoldItem(
        id="ood_001",
        question="What is the GDP of China?",
        data_sources=["none"],
        expected_tools=[],
        is_answerable=False,
        rubric="OOD",
    )
    agent_result = _make_agent_result([], stats_values=[])
    result = score_item(item, agent_result, judge_result=None)
    assert result.abstention_ok is True


def test_gold_set_loads():
    """Gold set YAML loads into 27 GoldItem objects."""
    from pubhealth_llm.evals.schemas import GoldItem
    with open(GOLD_PATH) as f:
        data = yaml.safe_load(f)
    items = [GoldItem(**item) for item in data["items"]]
    assert len(items) == 27
    ids = [item.id for item in items]
    assert "places_001" in ids
    assert "mmwr_001" in ids
    assert "mort_001" in ids
    assert "ood_001" in ids
