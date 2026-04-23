"""
Tests for the cdc_wonder_mortality database table.

These tests verify the database layer only — no LLM or agent calls.
All tests skip gracefully if the mortality table has not been ingested yet.

Run ingestion first:
    source .venv/bin/activate
    python -m pubhealth_llm.data_ingestion.download_mortality

NOTE: The ingested dataset (NCHS bi63-dtpu) is STATE-LEVEL only.
Parish/county-level data requires a manual CDC Wonder download.
The 'county_name' column holds state names, not parish names.
"""

import sqlite3

import pytest

from tests.conftest import DB_PATH, MORTALITY_TABLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_if_no_mortality(conn: sqlite3.Connection) -> None:
    """Skip the current test if the mortality table is absent or empty."""
    count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (MORTALITY_TABLE,),
    ).fetchone()[0]
    if count == 0:
        pytest.skip(
            f"Table '{MORTALITY_TABLE}' not found — run download_mortality first"
        )
    rows = conn.execute(f"SELECT COUNT(*) FROM {MORTALITY_TABLE}").fetchone()[0]
    if rows == 0:
        pytest.skip(f"Table '{MORTALITY_TABLE}' exists but is empty")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_mortality_table_exists(db_connection: sqlite3.Connection) -> None:
    """The cdc_wonder_mortality table must exist in healthgpt.db."""
    count = db_connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (MORTALITY_TABLE,),
    ).fetchone()[0]
    assert count == 1, (
        f"Table '{MORTALITY_TABLE}' not found — run download_mortality first"
    )


def test_mortality_table_has_data(db_connection: sqlite3.Connection) -> None:
    """The table must contain at least 1,000 rows after ingestion."""
    _skip_if_no_mortality(db_connection)
    row_count = db_connection.execute(
        f"SELECT COUNT(*) FROM {MORTALITY_TABLE}"
    ).fetchone()[0]
    assert row_count >= 1_000, (
        f"Expected ≥1,000 rows but found {row_count}. "
        "Re-run the mortality ingestion."
    )


def test_mortality_has_louisiana_data(db_connection: sqlite3.Connection) -> None:
    """Louisiana rows must be present (state-level dataset includes all 50 states)."""
    _skip_if_no_mortality(db_connection)
    rows = db_connection.execute(
        f"SELECT COUNT(*) FROM {MORTALITY_TABLE} WHERE state LIKE '%Louisiana%'"
    ).fetchone()[0]
    assert rows > 0, (
        "No Louisiana rows found in mortality table. "
        "The NCHS dataset covers all 50 states — check ingestion."
    )


def test_mortality_state_level_note(db_connection: sqlite3.Connection) -> None:
    """
    Document that the ingested dataset is STATE-LEVEL only.

    The NCHS bi63-dtpu dataset stores state names in the county_name column.
    Parish/county-level queries (e.g., 'East Baton Rouge') will return 0 rows
    unless a manual CDC Wonder county export has been loaded.
    This test confirms the state-level data is present and notes the limitation.
    """
    _skip_if_no_mortality(db_connection)

    # State-level data: 'county_name' holds the state name
    louisiana_rows = db_connection.execute(
        f"SELECT COUNT(*) FROM {MORTALITY_TABLE} WHERE county_name LIKE '%Louisiana%'"
    ).fetchone()[0]

    # Parish-level query — expected to be 0 with the default state-level dataset
    parish_rows = db_connection.execute(
        f"SELECT COUNT(*) FROM {MORTALITY_TABLE} WHERE county_name LIKE '%East Baton Rouge%'"
    ).fetchone()[0]

    assert louisiana_rows > 0, "State-level Louisiana data must be present"
    # We do not assert parish_rows == 0 — a manual county export could have been loaded
    if parish_rows == 0:
        pytest.skip(
            "Parish-level data (East Baton Rouge) not available with the default "
            "state-level NCHS dataset. To add county-level mortality data, manually "
            "download from https://wonder.cdc.gov/ucd-icd10.html and place in "
            "data/mortality/cdc_wonder_county.csv, then re-run download_mortality."
        )
    else:
        assert parish_rows > 0


def test_mortality_has_cause_of_death(db_connection: sqlite3.Connection) -> None:
    """The cause_of_death column must contain recognisable cause names."""
    _skip_if_no_mortality(db_connection)
    causes = [
        row[0]
        for row in db_connection.execute(
            f"SELECT DISTINCT cause_of_death FROM {MORTALITY_TABLE} "
            f"WHERE cause_of_death IS NOT NULL LIMIT 50"
        ).fetchall()
    ]
    assert len(causes) >= 5, f"Expected ≥5 distinct causes, found {len(causes)}"

    # At least one recognisable major cause must be present
    lower_causes = [c.lower() for c in causes]
    known = {"heart disease", "cancer", "diabetes", "stroke", "all causes"}
    found = known.intersection(lower_causes)
    assert found, (
        f"None of the expected causes {known} appear in the table. "
        f"Causes found: {causes[:10]}"
    )


def test_mortality_rates_are_numeric(db_connection: sqlite3.Connection) -> None:
    """Age-adjusted rates must be numeric (REAL) where not NULL."""
    _skip_if_no_mortality(db_connection)
    bad_rows = db_connection.execute(
        f"""
        SELECT age_adjusted_rate FROM {MORTALITY_TABLE}
        WHERE age_adjusted_rate IS NOT NULL
          AND CAST(age_adjusted_rate AS TEXT) LIKE '%Suppressed%'
        LIMIT 5
        """
    ).fetchall()
    assert len(bad_rows) == 0, (
        "Found non-numeric 'Suppressed' values in age_adjusted_rate — "
        "ingestion should convert these to NULL."
    )

    # Sanity-check that rates exist and are in a plausible range
    sample = db_connection.execute(
        f"""
        SELECT MIN(age_adjusted_rate), MAX(age_adjusted_rate), AVG(age_adjusted_rate)
        FROM {MORTALITY_TABLE}
        WHERE age_adjusted_rate IS NOT NULL
        """
    ).fetchone()
    min_rate, max_rate, avg_rate = sample
    assert min_rate is not None, "No non-NULL age_adjusted_rate values found"
    assert min_rate >= 0, f"Negative age_adjusted_rate: {min_rate}"
    assert max_rate < 10_000, f"Implausibly high rate: {max_rate} — check units"


def test_mortality_suppressed_values_are_null(db_connection: sqlite3.Connection) -> None:
    """
    CDC-suppressed death counts must be stored as NULL, not as strings.

    The ingestion converts 'Suppressed', 'Unreliable', etc. to NULL via
    _to_int_or_none / _to_float_or_none. Verify no string sentinels remain.
    """
    _skip_if_no_mortality(db_connection)
    bad_deaths = db_connection.execute(
        f"""
        SELECT deaths FROM {MORTALITY_TABLE}
        WHERE TYPEOF(deaths) = 'text'
          AND deaths != ''
        LIMIT 5
        """
    ).fetchall()
    assert len(bad_deaths) == 0, (
        f"Found text values in deaths column (should be INTEGER or NULL): "
        f"{bad_deaths}"
    )


def test_mortality_no_duplicate_rows(db_connection: sqlite3.Connection) -> None:
    """
    No duplicate (state, cause_of_death, year) combinations should exist.

    The ingestion drops and recreates the table on each run (idempotent),
    so duplicates indicate a parsing bug in the CSV normalisation.
    """
    _skip_if_no_mortality(db_connection)
    dupe_count = db_connection.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT county_name, cause_of_death, year, COUNT(*) AS cnt
            FROM {MORTALITY_TABLE}
            GROUP BY county_name, cause_of_death, year
            HAVING cnt > 1
        )
        """
    ).fetchone()[0]
    assert dupe_count == 0, (
        f"Found {dupe_count} duplicate (county_name, cause_of_death, year) groups. "
        "The ingestion should drop and recreate the table — check for partial loads."
    )
