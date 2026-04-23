"""
Tests for the agent tool functions in app/tools.py.

These tests call the tool functions directly (without the agent)
to verify they return sensible output. No network calls are made —
only local SQLite and ChromaDB are accessed.
"""

import pytest


# ---------------------------------------------------------------------------
# get_available_measures
# ---------------------------------------------------------------------------


def test_get_available_measures_returns_string(db_path):
    """get_available_measures() must return a non-empty string."""
    from pubhealth_llm.app.tools import get_available_measures

    result = get_available_measures()
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_available_measures_contains_measures(db_path):
    """get_available_measures() output must list at least one known measure."""
    from pubhealth_llm.app.tools import get_available_measures

    result = get_available_measures()
    # CDC PLACES always includes diabetes and obesity
    assert any(kw in result.lower() for kw in ("diabetes", "obesity", "smoking")), (
        f"Expected common measures in output. Got prefix: {result[:300]}"
    )


def test_get_available_measures_category_filter(db_path):
    """Category filter must narrow results."""
    from pubhealth_llm.app.tools import get_available_measures

    all_measures = get_available_measures()
    filtered = get_available_measures(category="Health Outcomes")
    # Filtered result should be shorter or equal (never longer)
    assert len(filtered) <= len(all_measures)


def test_get_available_measures_missing_db(tmp_path, monkeypatch):
    """Returns an error string (not an exception) when DB is missing."""
    import pubhealth_llm.app.tools as tools_mod
    monkeypatch.setattr(tools_mod, "DB_PATH", tmp_path / "nonexistent.db")

    from pubhealth_llm.app.tools import get_available_measures
    result = get_available_measures()
    assert "not found" in result.lower() or "run" in result.lower()


# ---------------------------------------------------------------------------
# get_health_statistics
# ---------------------------------------------------------------------------


def test_get_health_statistics_known_state(db_path):
    """Query for a well-populated state returns real data.

    The ingested dataset stores FIPS codes in LocationName, so geography
    is matched via StateDesc ('Texas') or StateAbbr ('TX').
    """
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("Texas", state="TX")
    assert isinstance(result, str)
    assert "not found" not in result.lower(), (
        f"Expected data for Texas. Got: {result[:300]}"
    )
    assert "Data_Value" in result or "Value:" in result, (
        f"Expected numeric data in result. Got: {result[:300]}"
    )


def test_get_health_statistics_with_measure_filter(db_path):
    """Filtering by measure keyword returns rows for that measure."""
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("Los Angeles", measure="obesity")
    assert isinstance(result, str)
    assert len(result) > 50


def test_get_health_statistics_unknown_location(db_path):
    """An unrecognized location returns an informative 'not found' string."""
    from pubhealth_llm.app.tools import get_health_statistics

    result = get_health_statistics("ZZZNonExistentPlace999")
    assert isinstance(result, str)
    assert "not found" in result.lower() or "no health" in result.lower()


def test_get_health_statistics_missing_db(tmp_path, monkeypatch):
    """Returns an error string (not an exception) when DB is missing."""
    import pubhealth_llm.app.tools as tools_mod
    monkeypatch.setattr(tools_mod, "DB_PATH", tmp_path / "nonexistent.db")

    from pubhealth_llm.app.tools import get_health_statistics
    result = get_health_statistics("Travis")
    assert "not found" in result.lower() or "run" in result.lower()


# ---------------------------------------------------------------------------
# compare_locations
# ---------------------------------------------------------------------------


def test_compare_locations_returns_table(db_path):
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


def test_compare_locations_empty_list(db_path):
    """An empty location list returns a descriptive error string."""
    from pubhealth_llm.app.tools import compare_locations

    result = compare_locations([], measure="obesity")
    assert isinstance(result, str)
    assert "no locations" in result.lower() or "at least" in result.lower()


def test_compare_locations_bad_measure(db_path):
    """An unrecognized measure returns a 'not found' string, not an exception."""
    from pubhealth_llm.app.tools import compare_locations

    result = compare_locations(["Travis County", "Harris County"], measure="zzz_fake_measure")
    assert isinstance(result, str)
    assert "not found" in result.lower() or "no comparison" in result.lower()


# ---------------------------------------------------------------------------
# search_mmwr_reports
# ---------------------------------------------------------------------------


def test_search_mmwr_returns_string(chroma_dir):
    """search_mmwr_reports returns a non-empty string."""
    from pubhealth_llm.app.tools import search_mmwr_reports

    result = search_mmwr_reports("infectious disease outbreak")
    assert isinstance(result, str)
    assert len(result) > 0


def test_search_mmwr_result_contains_source(chroma_dir):
    """Results must reference a source file."""
    from pubhealth_llm.app.tools import search_mmwr_reports

    result = search_mmwr_reports("influenza vaccination rates")
    assert "Source:" in result or "source" in result.lower(), (
        f"Expected source citation in result. Got: {result[:300]}"
    )


def test_search_mmwr_missing_chroma(tmp_path, monkeypatch):
    """Returns an error string (not an exception) when ChromaDB is missing."""
    import pubhealth_llm.app.tools as tools_mod
    monkeypatch.setattr(tools_mod, "CHROMA_DIR", tmp_path / "no_chroma")
    monkeypatch.setattr(tools_mod, "_chroma_collection", None)

    from pubhealth_llm.app.tools import search_mmwr_reports
    result = search_mmwr_reports("any query")
    assert isinstance(result, str)
    assert "not available" in result.lower() or "not found" in result.lower() or "run" in result.lower()


# ---------------------------------------------------------------------------
# rank_counties_composite
# ---------------------------------------------------------------------------


def test_rank_counties_composite_two_measures(db_path):
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


def test_rank_counties_composite_three_measures(db_path):
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


def test_rank_counties_composite_target_location_in_top_n(db_path):
    """Target county appears with arrow marker when it falls in top_n."""
    from pubhealth_llm.app.tools import rank_counties_composite

    # Zavala ranks #1 in TX for diabetes+obesity composite — always in top 10
    result = rank_counties_composite(
        "TX", ["diabetes", "obesity"], target_location="Zavala", top_n=10
    )
    assert isinstance(result, str)
    assert "Zavala" in result
    assert "← target" in result


def test_rank_counties_composite_target_location_outside_top_n(db_path):
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


def test_rank_counties_composite_top_n_limits_rows(db_path):
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


def test_rank_counties_composite_numeric_values(db_path):
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


def test_rank_counties_composite_missing_one_measure(db_path):
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


def test_rank_counties_composite_all_measures_missing(db_path):
    """Returns a clear error when no measures are found in the database."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["zzz_fake1", "zzz_fake2"])
    assert isinstance(result, str)
    assert "Composite" not in result
    assert "Not found" in result or "none found" in result or "0 of" in result


def test_rank_counties_composite_requires_two_measures(db_path):
    """Returns an error when fewer than 2 measures are provided."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["diabetes"])
    assert "at least 2" in result.lower()
    assert "Composite" not in result


def test_rank_counties_composite_invalid_state(db_path):
    """Returns a clear error for a non-two-letter state code."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("Texas", ["diabetes", "obesity"])
    assert "two-letter" in result.lower()
    assert "Composite" not in result


def test_rank_counties_composite_db_missing(monkeypatch, tmp_path):
    """Returns a 'not found' error string when the database is absent."""
    import pubhealth_llm.app.tools as tools_mod

    monkeypatch.setattr(tools_mod, "DB_PATH", tmp_path / "nonexistent.db")
    result = tools_mod.rank_counties_composite("TX", ["diabetes", "obesity"])
    assert "not found" in result.lower()
    assert "Composite" not in result
