"""
Tests for the SQLite CDC PLACES database (county-level).

Verifies the database exists, has the expected schema, contains
meaningful data, and responds correctly to the kinds of queries
the agent tools issue at runtime.

Active table: cdc_places_county (county-level dataset swc5-untb)
  - LocationName contains readable county names like "Travis County"
  - StateAbbr, Short_Question_Text, MeasureId, Data_Value, Year, etc.
"""

import sqlite3
from pathlib import Path

import pytest


TABLE = "cdc_places_county"


def test_db_file_exists(db_path):
    """SQLite database file must exist and be non-trivially sized."""
    assert db_path.exists(), f"DB not found: {db_path}"
    size_mb = db_path.stat().st_size / 1e6
    assert size_mb > 1, f"DB is suspiciously small: {size_mb:.2f} MB"


def test_county_table_exists(db_path):
    """cdc_places_county table must exist."""
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    assert TABLE in tables, (
        f"'{TABLE}' table missing. Found: {tables}\n"
        "Run: python -m pubhealth_llm.data_ingestion.download_county_data"
    )


def test_county_table_row_count(db_path):
    """cdc_places_county must contain a substantial number of rows."""
    conn = sqlite3.connect(db_path)
    count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    conn.close()
    assert count > 100_000, (
        f"{TABLE} has only {count:,} rows — expected 800k+. "
        "Re-run: python -m pubhealth_llm.data_ingestion.download_county_data"
    )


def test_county_table_expected_columns(db_path):
    """cdc_places_county must have the core columns the tools query."""
    required = {
        "LocationName", "StateAbbr", "MeasureId", "Short_Question_Text",
        "Data_Value", "Data_Value_Unit", "Year",
    }
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})").fetchall()}
    conn.close()
    missing = required - cols
    assert not missing, f"{TABLE} is missing columns: {missing}"


def test_location_names_are_readable(db_path):
    """LocationName must contain readable county names, not FIPS codes."""
    conn = sqlite3.connect(db_path)
    sample = [
        r[0] for r in conn.execute(
            f"SELECT DISTINCT LocationName FROM {TABLE} WHERE LocationName IS NOT NULL LIMIT 10"
        ).fetchall()
    ]
    conn.close()
    assert sample, f"No LocationName values found in {TABLE}"
    # Readable county names contain letters; FIPS codes are pure digits
    has_readable = any(any(c.isalpha() for c in name) for name in sample)
    assert has_readable, (
        f"LocationName values look like FIPS codes (not county names): {sample}\n"
        "The county-level dataset was not loaded. Run download_county_data."
    )


def test_query_by_state_abbreviation(db_path):
    """SQL query by StateAbbr returns Texas rows."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        f"SELECT * FROM {TABLE} WHERE StateAbbr = ? AND Data_Value IS NOT NULL LIMIT 5",
        ("TX",),
    ).fetchall()
    conn.close()
    assert rows, f"Query for StateAbbr='TX' returned no rows in {TABLE}"


def test_query_by_county_name(db_path):
    """SQL query by LocationName LIKE returns Travis County rows."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE LocationName LIKE ? AND Data_Value IS NOT NULL",
        ("%Travis%",),
    ).fetchone()
    conn.close()
    assert rows[0] > 0, (
        f"No rows for 'Travis County' in {TABLE} — check that county-level data is loaded"
    )


def test_query_diabetes_measure(db_path):
    """SQL query filtering by diabetes measure returns rows."""
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE Short_Question_Text LIKE ? AND Data_Value IS NOT NULL",
        ("%diabetes%",),
    ).fetchone()[0]
    conn.close()
    assert count > 0, f"No diabetes rows found in {TABLE}"


def test_query_obesity_measure(db_path):
    """SQL query filtering by obesity measure returns rows."""
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE Short_Question_Text LIKE ? AND Data_Value IS NOT NULL",
        ("%obes%",),
    ).fetchone()[0]
    conn.close()
    assert count > 0, f"No obesity rows found in {TABLE}"


def test_county_indexes_exist(db_path):
    """Performance indexes created by download_county_data must be present."""
    conn = sqlite3.connect(db_path)
    indexes = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()]
    conn.close()
    expected = {"idx_county_state", "idx_county_location", "idx_county_measure", "idx_county_year"}
    missing = expected - set(indexes)
    assert not missing, (
        f"Missing indexes: {missing}\n"
        "Re-run: python -m pubhealth_llm.data_ingestion.download_county_data"
    )


def test_worst_counties_query(db_path):
    """Direct SQL for worst counties by obesity in TX returns ordered results."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        f"""
        SELECT LocationName, Data_Value
        FROM {TABLE}
        WHERE StateAbbr = 'TX'
          AND Short_Question_Text LIKE '%obes%'
          AND Data_Value IS NOT NULL
        ORDER BY Data_Value DESC
        LIMIT 5
        """,
    ).fetchall()
    conn.close()
    assert rows, "No obesity data for TX counties found — check the county table"
    assert len(rows) >= 1
    # Values should be between 0 and 100 (percentage)
    for name, val in rows:
        assert 0 < val <= 100, f"Suspicious obesity value for {name}: {val}"
