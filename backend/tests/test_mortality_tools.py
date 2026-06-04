"""
Tests for get_mortality_data and compare_mortality tool functions.

These tests call the Python functions directly — no agent or LLM involved.
All tests skip gracefully if the mortality table has not been ingested yet.

Run ingestion first:
    source .venv/bin/activate
    python -m pubhealth_llm.data_ingestion.download_mortality
"""

from typing import Callable

import pytest

from tests.conftest import MORTALITY_TABLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_tool_available(mortality_table_exists: bool) -> None:
    """Skip the test if the mortality table isn't populated yet."""
    if not mortality_table_exists:
        pytest.skip(
            f"Table '{MORTALITY_TABLE}' not populated — run download_mortality first"
        )


# ---------------------------------------------------------------------------
# get_mortality_data tests
# ---------------------------------------------------------------------------


def test_get_mortality_data_returns_string(
    mortality_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """The tool must always return a string, even if no data is available."""
    result = mortality_tool("Louisiana")
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result) > 0, "Tool returned an empty string"


def test_get_mortality_data_with_known_state(
    mortality_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """Querying a known state must return actual data rows."""
    _assert_tool_available(mortality_table_exists)
    result = mortality_tool("Louisiana")
    assert "Louisiana" in result or "louisiana" in result.lower(), (
        "Result does not mention Louisiana:\n" + result[:500]
    )
    # Should contain tabular data, not just the no-data message
    assert "No mortality data" not in result, (
        "Tool returned no-data message for Louisiana, which should be in the dataset.\n"
        + result
    )


def test_get_mortality_data_filters_by_cause(
    mortality_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """Filtering by cause must return only matching rows."""
    _assert_tool_available(mortality_table_exists)
    result = mortality_tool("Texas", cause="diabetes")
    # Should mention diabetes-related content
    assert "diabetes" in result.lower() or "Diabetes" in result, (
        "Result does not mention diabetes when filtering by cause:\n" + result[:500]
    )
    assert "No mortality data" not in result, (
        "Tool returned no-data message for Texas/diabetes.\n" + result
    )


def test_get_mortality_data_state_abbreviation(
    mortality_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """Two-letter state abbreviation must resolve to the full state name."""
    _assert_tool_available(mortality_table_exists)
    result_abbrev = mortality_tool("LA")
    result_full = mortality_tool("Louisiana")
    # Both should return data (not the no-data message)
    assert "No mortality data" not in result_abbrev, (
        "Abbreviation 'LA' did not resolve to Louisiana:\n" + result_abbrev[:400]
    )
    assert "No mortality data" not in result_full


def test_get_mortality_data_unknown_location(
    mortality_tool: Callable,
) -> None:
    """An unknown location must return a graceful no-data message, not raise."""
    result = mortality_tool("Nonexistent County That Does Not Exist XYZ123")
    assert isinstance(result, str), "Tool must return str even for unknown locations"
    # Should not raise — must return the no-data string
    lower = result.lower()
    assert (
        "no mortality data" in lower
        or "not found" in lower
        or "no data" in lower
        or "unavailable" in lower
    ), f"Expected a graceful no-data message, got:\n{result[:400]}"


def test_get_mortality_data_unknown_cause(
    mortality_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """Filtering by an unknown cause must return a graceful message, not raise."""
    _assert_tool_available(mortality_table_exists)
    result = mortality_tool("Louisiana", cause="flying spaghetti monster disease")
    assert isinstance(result, str)
    lower = result.lower()
    assert (
        "no mortality data" in lower
        or "not found" in lower
        or "no data" in lower
        or "no rows" in lower
        or "0 rows" in lower
    ), f"Expected graceful no-data message for unknown cause, got:\n{result[:400]}"


def test_get_mortality_data_handles_null_deaths(
    mortality_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """Tool must return valid output even for rows where deaths is NULL."""
    _assert_tool_available(mortality_table_exists)
    # Query for United States national data, which is always present
    result = mortality_tool("United States")
    assert isinstance(result, str)
    assert len(result) > 50, "Tool returned suspiciously short output for 'United States'"


# ---------------------------------------------------------------------------
# compare_mortality tests
# ---------------------------------------------------------------------------


def test_compare_mortality_returns_results(
    compare_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """Comparing two states must return a non-empty result string."""
    _assert_tool_available(mortality_table_exists)
    result = compare_tool(["Louisiana", "Mississippi"], "heart disease")
    assert isinstance(result, str)
    assert len(result) > 50, (
        "compare_mortality returned a suspiciously short result:\n" + result
    )
    assert "No mortality data" not in result, (
        "compare_mortality returned no-data message for Louisiana/Mississippi:\n"
        + result
    )


def test_compare_mortality_sorted_by_rate(
    compare_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """Results must be ordered from highest to lowest age-adjusted rate."""
    _assert_tool_available(mortality_table_exists)
    result = compare_tool(
        ["Louisiana", "Mississippi", "Texas", "California"],
        "heart disease",
    )
    assert isinstance(result, str)
    # Extract numeric rate values from the result to verify ordering
    import re
    rates = [float(m) for m in re.findall(r"\b(\d+\.\d+)\b", result)]
    if len(rates) >= 2:
        # Rates should be non-increasing (DESC order)
        for i in range(len(rates) - 1):
            assert rates[i] >= rates[i + 1] - 0.01, (
                f"Rates out of order at positions {i} and {i+1}: "
                f"{rates[i]} vs {rates[i+1]}\nFull result:\n{result}"
            )


def test_compare_mortality_includes_locations(
    compare_tool: Callable,
    mortality_table_exists: bool,
) -> None:
    """Each queried location must appear in the comparison output."""
    _assert_tool_available(mortality_table_exists)
    locations = ["Louisiana", "Mississippi"]
    result = compare_tool(locations, "diabetes")
    for loc in locations:
        assert loc in result, (
            f"Location '{loc}' not found in comparison output:\n{result[:500]}"
        )
