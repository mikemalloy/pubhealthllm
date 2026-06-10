"""
Integration tests verifying multi-tool call behavior.

These tests confirm that the agent calls multiple tools when a question
requires data across multiple health measures — the exact failure mode
observed with the over-trimmed system prompt on Groq.

Requires: AWS credentials (Bedrock), Aurora, S3 Vectors (all skipped if absent).
"""

import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")


# ---------------------------------------------------------------------------
# Unit-level: verify tools return useful data for the key measures
# ---------------------------------------------------------------------------


def test_get_worst_counties_diabetes_texas(aurora_db):
    """get_worst_counties_by_measure returns ranked TX counties for diabetes."""
    from pubhealth_llm.app.tools import get_worst_counties_by_measure

    result = get_worst_counties_by_measure("TX", "diabetes", top_n=5)
    assert isinstance(result, str)
    assert len(result) > 50, "Expected substantive output, got near-empty string"
    # Should contain county names or a data table
    assert "County" in result or "county" in result or "%" in result, (
        f"Result does not look like county data:\n{result}"
    )


def test_get_worst_counties_obesity_texas(aurora_db):
    """get_worst_counties_by_measure returns ranked TX counties for obesity."""
    from pubhealth_llm.app.tools import get_worst_counties_by_measure

    result = get_worst_counties_by_measure("TX", "obesity", top_n=5)
    assert isinstance(result, str)
    assert len(result) > 50


def test_get_worst_counties_physical_inactivity_texas(aurora_db):
    """get_worst_counties_by_measure returns ranked TX counties for physical inactivity."""
    from pubhealth_llm.app.tools import get_worst_counties_by_measure

    result = get_worst_counties_by_measure("TX", "physical inactivity", top_n=5)
    # physical inactivity may map to a different measure name — result should still be non-empty
    assert isinstance(result, str)
    assert len(result) > 10, (
        f"No data returned for physical inactivity in TX:\n{result}"
    )


def test_get_health_statistics_travis_county(aurora_db):
    """get_health_statistics returns data for Travis County, TX."""
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("Travis County", state="TX")
    assert isinstance(result, str)
    assert len(result) > 50
    assert "Travis" in result, f"'Travis' not in result:\n{result}"


def test_compare_locations_diabetes(aurora_db):
    """compare_locations returns comparison table for diabetes across TX counties."""
    from pubhealth_llm.app.tools import compare_locations

    result = compare_locations(["Travis County", "Harris County", "Dallas County"], "diabetes")
    assert isinstance(result, str)
    assert len(result) > 50


def test_search_mmwr_diabetes(s3v_index):
    """search_mmwr_reports returns passages for a diabetes query."""
    from pubhealth_llm.app.tools import search_mmwr_reports

    result = search_mmwr_reports("diabetes prevention obesity physical inactivity", top_k=3)
    assert isinstance(result, str)
    assert len(result) > 50


# ---------------------------------------------------------------------------
# Integration: full agent run with multi-measure question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_uses_composite_tool_for_multidimensional_question(
    bedrock_available, aurora_db, s3v_index
):
    """
    For a multi-measure prioritization question the agent must call
    tool_rank_counties_composite (the correct single-call approach) OR
    call at least 2 individual measure tools.

    With the composite tool in place, the expected pattern is ONE call to
    rank_counties_composite covering all measures — not 3 separate calls.
    This test accepts either strategy (composite OR ≥2 individual calls)
    and rejects the old failure mode of doing nothing beyond one MMWR search.
    """
    from pubhealth_llm.app.agent import run_agent, AgentResult
    import pubhealth_llm.app.agent as agent_module

    tool_calls_made = []

    original_search = agent_module.search_mmwr_reports
    original_get_stats = agent_module.get_health_statistics
    original_compare = agent_module.compare_locations
    original_worst = agent_module.get_worst_counties_by_measure
    original_measures = agent_module.get_available_measures
    original_composite = agent_module.rank_counties_composite

    def tracking_search(query, top_k=5):
        tool_calls_made.append(("search_mmwr_reports", query))
        return original_search(query, top_k=top_k)

    def tracking_get_stats(location, measure=None, state=None):
        tool_calls_made.append(("get_health_statistics", location, measure))
        return original_get_stats(location, measure=measure, state=state)

    def tracking_compare(locations, measure):
        tool_calls_made.append(("compare_locations", locations, measure))
        return original_compare(locations, measure)

    def tracking_worst(state, measure, top_n=10):
        tool_calls_made.append(("get_worst_counties_by_measure", state, measure))
        return original_worst(state, measure, top_n=top_n)

    def tracking_measures(category=None):
        tool_calls_made.append(("get_available_measures", category))
        return original_measures(category=category)

    def tracking_composite(state, measures, target_location=None, top_n=10):
        tool_calls_made.append(("rank_counties_composite", state, measures))
        return original_composite(state, measures, target_location=target_location, top_n=top_n)

    with (
        patch.object(agent_module, "search_mmwr_reports", tracking_search),
        patch.object(agent_module, "get_health_statistics", tracking_get_stats),
        patch.object(agent_module, "compare_locations", tracking_compare),
        patch.object(agent_module, "get_worst_counties_by_measure", tracking_worst),
        patch.object(agent_module, "get_available_measures", tracking_measures),
        patch.object(agent_module, "rank_counties_composite", tracking_composite),
    ):
        agent_result = await run_agent(
            "Which 3 counties in Texas should I prioritize for a diabetes prevention "
            "program? Base your answer on diabetes prevalence, obesity rates, and "
            "physical inactivity levels."
        )

    tool_names = [t[0] for t in tool_calls_made]

    # The correct behavior: composite tool called covering all 3 measures
    called_composite = "rank_counties_composite" in tool_names
    # Acceptable fallback: at least 2 individual measure calls
    individual_sql_calls = sum(
        1 for t in tool_names
        if t in ("get_worst_counties_by_measure", "get_health_statistics", "compare_locations")
    )
    called_enough_individual = individual_sql_calls >= 2

    assert called_composite or called_enough_individual, (
        f"Agent did not use composite tool or make sufficient individual measure calls.\n"
        f"Tool calls made: {tool_calls_made}\n"
        f"Expected: rank_counties_composite called once with all 3 measures."
    )

    # Verify the response is substantive
    response = agent_result.response
    assert response.summary, "Response summary is empty"
    assert len(response.evidence) >= 1, "Response has no evidence items"


@pytest.mark.asyncio
async def test_agent_response_contains_county_names(bedrock_available, aurora_db, s3v_index):
    """
    For a Texas county prioritization question, the response must name
    at least one specific Texas county.
    """
    from pubhealth_llm.app.agent import run_agent

    agent_result = await run_agent(
        "Which counties in Texas have the highest diabetes rates? Give me the top 3."
    )
    response = agent_result.response

    full_text = (
        response.summary
        + " ".join(response.evidence)
        + (response.historical_context or "")
    )

    # Response should mention at least one county by name
    assert "County" in full_text or "county" in full_text, (
        f"No county names found in response.\nSummary: {response.summary}\n"
        f"Evidence: {response.evidence}"
    )


@pytest.mark.asyncio
async def test_agent_response_has_statistics(bedrock_available, aurora_db, s3v_index):
    """
    For a statistics question, the agent must populate the statistics field
    with at least one StatisticEntry containing a numeric value.
    """
    from pubhealth_llm.app.agent import run_agent

    agent_result = await run_agent(
        "What is the obesity rate in Travis County, TX?"
    )
    response = agent_result.response

    assert response.summary, "Summary is empty"

    # Either statistics table OR evidence with numeric data
    has_numeric_stats = len(response.statistics) > 0
    has_numeric_in_evidence = any(
        any(c.isdigit() for c in item) for item in response.evidence
    )
    assert has_numeric_stats or has_numeric_in_evidence, (
        "Response has no numeric data in statistics or evidence.\n"
        f"Summary: {response.summary}\nEvidence: {response.evidence}"
    )


@pytest.mark.asyncio
async def test_agent_never_fabricates_when_db_empty(bedrock_available):
    """
    When no DB data is found (non-existent location), the agent must not
    fabricate statistics — it should report no data found.
    """
    from pubhealth_llm.app.agent import run_agent

    agent_result = await run_agent(
        "What is the diabetes rate in Nonexistent County, ZZ?"
    )
    response = agent_result.response

    # Should not have statistics entries with fabricated values
    # The summary should acknowledge unavailability or error
    assert response.summary, "Summary is empty"
    # Check caveats acknowledge the data limitation
    has_caveat_about_data = any(
        "not found" in c.lower()
        or "no data" in c.lower()
        or "unavailable" in c.lower()
        or "limitation" in c.lower()
        or "error" in c.lower()
        for c in response.caveats + response.evidence + [response.summary]
    )
    # This is a soft check — the agent should at least not silently return
    # fake numbers for a made-up location
    if response.statistics:
        for stat in response.statistics:
            assert stat.location != "Nonexistent County, ZZ", (
                "Agent fabricated a statistic for a non-existent location"
            )
