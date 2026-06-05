"""
Tests for PydanticAI agent construction and schema validation.

These tests verify the agent instantiates correctly and that the
PublicHealthResponse Pydantic model validates and renders as expected.
No live Anthropic API calls are made in this module.
"""

import pytest


def test_public_health_response_minimal(anthropic_api_key):
    """PublicHealthResponse validates with only required fields."""
    from pubhealth_llm.app.schemas import PublicHealthResponse

    resp = PublicHealthResponse(
        summary="Test summary.",
        evidence=["Finding one.", "Finding two."],
        caveats=["Data may be outdated."],
        sources=["CDC PLACES 2023"],
    )
    assert resp.summary == "Test summary."
    assert len(resp.evidence) == 2
    assert resp.disclaimer  # default disclaimer must be non-empty


def test_public_health_response_to_markdown(anthropic_api_key):
    """to_markdown() returns a non-empty string with expected sections."""
    from pubhealth_llm.app.schemas import PublicHealthResponse, StatisticEntry

    resp = PublicHealthResponse(
        summary="Obesity is elevated in this county.",
        evidence=["Obesity prevalence is 38%."],
        statistics=[
            StatisticEntry(
                metric="Obesity",
                value=38.0,
                unit="% of adults",
                location="Travis County, TX",
                year=2022,
                source="CDC PLACES 2023",
            )
        ],
        historical_context="MMWR 2023 noted increasing obesity trends.",
        caveats=["Data is from 2022 BRFSS survey."],
        sources=["CDC PLACES 2023"],
    )
    md = resp.to_markdown()
    assert "## Summary" in md
    assert "## Key Findings" in md
    assert "## Statistics" in md
    assert "## Historical Context" in md
    assert "## Caveats" in md
    assert "## Sources" in md
    assert resp.disclaimer in md


def test_agent_instantiates(anthropic_api_key):
    """
    The real _build_agent() function builds the agent without error.

    This exercises AnthropicProvider(api_key=...) + AnthropicModel +
    Agent(output_type=...) together, catching any API renames in one shot.
    """
    from pubhealth_llm.app.agent import _build_agent

    agent = _build_agent("anthropic:claude-sonnet-4-6")
    assert agent is not None


def test_agent_has_eight_tools(anthropic_api_key):
    """The agent must expose exactly the eight documented tools."""
    from pubhealth_llm.app.agent import _build_agent

    agent = _build_agent("anthropic:claude-sonnet-4-6")
    # In PydanticAI 1.x, registered tools live in _function_toolset.tools (dict)
    tool_names = set(agent._function_toolset.tools.keys())
    expected = {
        "tool_search_mmwr_reports",
        "tool_get_health_statistics",
        "tool_compare_locations",
        "tool_get_available_measures",
        "tool_get_worst_counties_by_measure",
        "tool_rank_counties_composite",
        "tool_get_mortality_data",
        "tool_compare_mortality",
    }
    assert expected == tool_names, (
        f"Tool mismatch.\n  Expected: {expected}\n  Found:    {tool_names}"
    )


def test_statistic_entry_validates():
    """StatisticEntry rejects missing required fields."""
    from pubhealth_llm.app.schemas import StatisticEntry
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        StatisticEntry()  # all fields required


def test_public_health_response_default_disclaimer():
    """Disclaimer field has a sensible default without being set explicitly."""
    from pubhealth_llm.app.schemas import PublicHealthResponse

    resp = PublicHealthResponse(
        summary="s", evidence=["e"], caveats=["c"], sources=["src"]
    )
    assert "decision support" in resp.disclaimer.lower()
    assert "qualified public health" in resp.disclaimer.lower()
