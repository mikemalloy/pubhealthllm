"""
Tests for the agent tool functions in app/tools.py.

These tests call the tool functions directly (without the agent)
to verify they return sensible output. No network calls are made —
only local SQLite and ChromaDB are accessed.
"""

import time
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# get_available_measures
# ---------------------------------------------------------------------------


def test_get_available_measures_returns_string(aurora_db):
    """get_available_measures() must return a non-empty string."""
    from pubhealth_llm.app.tools import get_available_measures

    result = get_available_measures()
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_available_measures_contains_measures(aurora_db):
    """get_available_measures() output must list at least one known measure."""
    from pubhealth_llm.app.tools import get_available_measures

    result = get_available_measures()
    # CDC PLACES always includes diabetes and obesity
    assert any(kw in result.lower() for kw in ("diabetes", "obesity", "smoking")), (
        f"Expected common measures in output. Got prefix: {result[:300]}"
    )


def test_get_available_measures_category_filter(aurora_db):
    """Category filter must narrow results."""
    from pubhealth_llm.app.tools import get_available_measures

    all_measures = get_available_measures()
    filtered = get_available_measures(category="Health Outcomes")
    # Filtered result should be shorter or equal (never longer)
    assert len(filtered) <= len(all_measures)


# ---------------------------------------------------------------------------
# get_health_statistics
# ---------------------------------------------------------------------------


def test_get_health_statistics_known_county(aurora_db):
    """Query for a well-known county returns real data.

    Aurora health_facts stores county-level PLACES data keyed by FIPS.
    Travis County, TX (FIPS 48453) has comprehensive PLACES coverage.
    """
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("Travis County, TX")
    assert isinstance(result, str)
    assert "not found" not in result.lower(), (
        f"Expected data for Travis County TX. Got: {result[:300]}"
    )
    assert "Travis" in result, (
        f"Expected 'Travis' in result. Got: {result[:300]}"
    )


def test_get_health_statistics_county_suffix_stripped(aurora_db):
    """'Cook County' should find the same rows as 'Cook' (suffix is stripped).

    Regression test: LocationName stores 'Cook', not 'Cook County'.
    Without normalization, LIKE '%Cook County%' returns zero rows.
    """
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("Cook County", state="IL")
    assert isinstance(result, str)
    assert "not found" not in result.lower(), (
        f"Expected data for Cook County IL. Got: {result[:300]}"
    )


def test_get_health_statistics_county_suffix_with_state_in_name(aurora_db):
    """'Harris County, TX' should find data (state hint extracted from name)."""
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("Harris County, TX")
    assert isinstance(result, str)
    assert "not found" not in result.lower(), (
        f"Expected data for Harris County TX. Got: {result[:300]}"
    )


def test_get_health_statistics_with_measure_filter(aurora_db):
    """Filtering by measure keyword returns rows for that measure."""
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("Los Angeles", measure="obesity")
    assert isinstance(result, str)
    assert len(result) > 50


def test_get_health_statistics_unknown_location(aurora_db):
    """An unrecognized location returns an informative 'not found' string."""
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("ZZZNonExistentPlace999")
    assert isinstance(result, str)
    assert "not found" in result.lower() or "no health" in result.lower()


# ---------------------------------------------------------------------------
# compare_locations
# ---------------------------------------------------------------------------


def test_compare_locations_county_suffix_stripped(aurora_db):
    """compare_locations must work when location names include 'County' suffix.

    Regression test for the exact query that caused infinite agent thrashing:
    'Cook County, IL' and 'Harris County, TX' both have LocationName stored
    without the ' County' suffix in the DB.
    """
    from pubhealth_llm.app.tools import compare_locations

    result = compare_locations(
        ["Cook County, IL", "Harris County, TX"],
        measure="obesity",
    )
    assert isinstance(result, str)
    assert "not found" not in result.lower(), (
        f"Expected comparison data. Got: {result[:300]}"
    )
    assert len(result) > 50


def test_compare_locations_returns_table(aurora_db):
    """compare_locations returns a formatted comparison string.

    Uses state names since LocationName contains FIPS codes in the
    census-tract level dataset.
    """
    from pubhealth_llm.app.tools import compare_locations

    result = compare_locations(
        ["Texas", "California"],
        measure="diabetes",
    )
    assert isinstance(result, str)
    assert len(result) > 50


def test_compare_locations_empty_list(aurora_db):
    """An empty location list returns a descriptive error string."""
    from pubhealth_llm.app.tools import compare_locations

    result = compare_locations([], measure="obesity")
    assert isinstance(result, str)
    assert "no locations" in result.lower() or "at least" in result.lower()


def test_compare_locations_bad_measure(aurora_db):
    """An unrecognized measure returns a 'not found' string, not an exception."""
    from pubhealth_llm.app.tools import compare_locations

    result = compare_locations(["Travis County", "Harris County"], measure="zzz_fake_measure")
    assert isinstance(result, str)
    assert "not found" in result.lower() or "no comparison" in result.lower()


# ---------------------------------------------------------------------------
# search_mmwr_reports
# ---------------------------------------------------------------------------


def test_search_mmwr_returns_string(s3v_index):
    """search_mmwr_reports returns a non-empty string."""
    from pubhealth_llm.app.tools import search_mmwr_reports

    result = search_mmwr_reports("infectious disease outbreak")
    assert isinstance(result, str)
    assert len(result) > 0


def test_search_mmwr_result_contains_source(s3v_index):
    """Results must reference a source file."""
    from pubhealth_llm.app.tools import search_mmwr_reports

    result = search_mmwr_reports("influenza vaccination rates")
    assert "Source:" in result or "source" in result.lower(), (
        f"Expected source citation in result. Got: {result[:300]}"
    )


def test_search_mmwr_missing_chroma(monkeypatch):
    """Returns an error string (not an exception) when vector store is unavailable."""
    import pubhealth_llm.app.tools as tools_mod
    monkeypatch.setattr(tools_mod, "VECTOR_BUCKET", "")

    from pubhealth_llm.app.tools import search_mmwr_reports
    result = search_mmwr_reports("any query")
    assert isinstance(result, str)
    assert "not available" in result.lower() or "not found" in result.lower() or "run" in result.lower()


# ---------------------------------------------------------------------------
# rank_counties_composite
# ---------------------------------------------------------------------------


def test_rank_counties_composite_two_measures(aurora_db):
    """Returns a ranked composite table for 2 measures in TX."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["diabetes", "obesity"])
    assert isinstance(result, str)
    assert len(result) > 200
    assert "Composite" in result
    assert "County" in result
    # Should list measure names in the preamble
    assert "Diabetes" in result or "diabetes" in result
    assert "Obesity" in result or "obesity" in result


def test_rank_counties_composite_three_measures(aurora_db):
    """Returns composite output for 3 measures including physical inactivity."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite(
        "TX", ["diabetes", "obesity", "physical inactivity"]
    )
    assert isinstance(result, str)
    assert "Composite" in result
    assert "County" in result
    # All 3 measures should resolve — "Not found" should not appear for any of them
    assert "✗ Not found" not in result, (
        f"One or more measures not found in DB:\n{result[:500]}"
    )


def test_rank_counties_composite_target_location_in_top_n(aurora_db):
    """Target county appears with arrow marker when it falls in top_n."""
    from pubhealth_llm.app.tools import rank_counties_composite

    # Zavala ranks #1 in TX for diabetes+obesity composite — always in top 10
    result = rank_counties_composite(
        "TX", ["diabetes", "obesity"], target_location="Zavala", top_n=10
    )
    assert isinstance(result, str)
    assert "Zavala" in result
    assert "← target" in result


def test_rank_counties_composite_target_location_outside_top_n(aurora_db):
    """Target county is appended below the table when outside top_n."""
    from pubhealth_llm.app.tools import rank_counties_composite

    # Travis (Austin) is consistently near the bottom for diabetes+obesity in TX;
    # top_n=3 guarantees it is outside the table regardless of exact ranking
    result = rank_counties_composite(
        "TX", ["diabetes", "obesity"], target_location="Travis", top_n=3
    )
    assert isinstance(result, str)
    assert "Travis" in result
    assert "← target" in result


def test_rank_counties_composite_top_n_limits_rows(aurora_db):
    """top_n=5 produces at most 5 ranked rows (plus optional target row)."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["diabetes", "obesity"], top_n=5)
    # Count lines that start with a rank number (digit in first 5 chars)
    data_lines = [
        ln for ln in result.split("\n")
        if ln and ln[0].isdigit()
    ]
    # top_n=5 with no target → exactly 5 data rows
    assert len(data_lines) == 5, (
        f"Expected 5 data rows for top_n=5, got {len(data_lines)}:\n{result}"
    )


def test_rank_counties_composite_numeric_values(aurora_db):
    """Composite score column contains real numbers (not all zeros)."""
    from pubhealth_llm.app.tools import rank_counties_composite
    import re

    result = rank_counties_composite("TX", ["diabetes", "obesity"], top_n=5)
    # Extract all decimal numbers from data lines
    data_lines = [ln for ln in result.split("\n") if ln and ln[0].isdigit()]
    numbers = []
    for ln in data_lines:
        numbers.extend(float(x) for x in re.findall(r"-?\d+\.\d+", ln))

    assert numbers, "No decimal numbers found in output"
    # Composite scores should not all be zero (would indicate a math bug)
    composites = [float(x) for x in re.findall(r"-?\d+\.\d+", data_lines[-1])]
    assert any(c != 0.0 for c in composites), (
        "All composite scores are zero — likely a z-score computation bug"
    )


def test_rank_counties_composite_missing_one_measure(aurora_db):
    """One invalid measure is noted; composite still runs on the valid two."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite(
        "TX", ["diabetes", "obesity", "zzz_nonexistent_measure"]
    )
    assert isinstance(result, str)
    # Should still produce a composite (2 valid measures remain)
    assert "Composite" in result
    # The invalid measure should be flagged
    assert "zzz_nonexistent_measure" in result or "Not found" in result


def test_rank_counties_composite_all_measures_missing(aurora_db):
    """Returns a clear error when no measures are found in the database."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["zzz_fake1", "zzz_fake2"])
    assert isinstance(result, str)
    assert "Composite" not in result
    assert "Not found" in result or "none found" in result or "0 of" in result


def test_rank_counties_composite_requires_two_measures(aurora_db):
    """Returns an error when fewer than 2 measures are provided."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["diabetes"])
    assert "at least 2" in result.lower()
    assert "Composite" not in result


def test_rank_counties_composite_invalid_state(aurora_db):
    """Returns a clear error for a non-two-letter state code."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("Texas", ["diabetes", "obesity"])
    assert "two-letter" in result.lower()
    assert "Composite" not in result


# ---------------------------------------------------------------------------
# get_worst_counties_by_measure — NULL field robustness
# ---------------------------------------------------------------------------


def test_get_worst_counties_null_location_name(monkeypatch):
    """get_worst_counties_by_measure must not crash when LocationName is NULL.

    Regression test for TypeError: unsupported format string passed to
    NoneType.__format__ — dict.get(key, default) returns None (not the
    default) when the key is present but its value is NULL/None.
    """
    import pubhealth_llm.app.tools as tools_mod

    null_row = {
        "LocationName": None,        # NULL in DB → triggers the bug
        "StateAbbr": "TX",
        "Short_Question_Text": "Diabetes",
        "Measure": "Diabetes among adults",
        "Data_Value": 12.5,
        "Data_Value_Unit": "%",
        "Low_Confidence_Limit": 11.0,
        "High_Confidence_Limit": 14.0,
        "TotalPopulation": 50000,
        "Year": 2022,
    }
    monkeypatch.setattr(tools_mod, "resolve_measure", lambda kw: "DIABETES")
    monkeypatch.setattr(tools_mod, "_query_db", lambda *_a, **_kw: [null_row])

    result = tools_mod.get_worst_counties_by_measure("TX", "diabetes", top_n=1)
    assert isinstance(result, str)
    assert "Unknown" in result  # None → "Unknown" fallback


# ---------------------------------------------------------------------------
# check_aurora_db — DatabaseResumingException retry logic
# ---------------------------------------------------------------------------


def test_check_aurora_db_retries_on_resuming_then_succeeds(monkeypatch):
    """check_aurora_db retries when Aurora raises DatabaseResumingException.

    Aurora Serverless v2 raises DatabaseResumingException when the cluster
    is resuming from auto-pause. check_aurora_db must retry rather than
    propagating immediately.
    """
    from botocore.exceptions import ClientError

    import pubhealth_llm.app.tools as tools_mod
    from pubhealth_llm.app.tools import check_aurora_db

    call_count = 0

    def mock_query_one(sql, params):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ClientError(
                {"Error": {"Code": "DatabaseResumingException", "Message": "resuming"}},
                "ExecuteStatement",
            )
        return {"ping": 1}

    mock_db = MagicMock()
    mock_db.query_one.side_effect = mock_query_one
    monkeypatch.setattr(tools_mod, "get_db", lambda: mock_db)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    check_aurora_db()  # must not raise
    assert call_count == 3


def test_check_aurora_db_raises_after_max_retries(monkeypatch):
    """check_aurora_db raises RuntimeError after exhausting all retries."""
    from botocore.exceptions import ClientError

    import pubhealth_llm.app.tools as tools_mod
    from pubhealth_llm.app.tools import check_aurora_db

    def always_resuming(sql, params):
        raise ClientError(
            {"Error": {"Code": "DatabaseResumingException", "Message": "resuming"}},
            "ExecuteStatement",
        )

    mock_db = MagicMock()
    mock_db.query_one.side_effect = always_resuming
    monkeypatch.setattr(tools_mod, "get_db", lambda: mock_db)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="Aurora"):
        check_aurora_db()


def test_check_aurora_db_non_resuming_clienterror_raises_immediately(monkeypatch):
    """check_aurora_db does not retry on non-DatabaseResumingException ClientErrors."""
    from botocore.exceptions import ClientError

    import pubhealth_llm.app.tools as tools_mod
    from pubhealth_llm.app.tools import check_aurora_db

    call_count = 0

    def bad_credentials(sql, params):
        nonlocal call_count
        call_count += 1
        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "ExecuteStatement",
        )

    mock_db = MagicMock()
    mock_db.query_one.side_effect = bad_credentials
    monkeypatch.setattr(tools_mod, "get_db", lambda: mock_db)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="Aurora"):
        check_aurora_db()
    assert call_count == 1  # no retry
