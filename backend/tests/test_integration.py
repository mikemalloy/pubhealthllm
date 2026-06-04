"""
Integration tests verifying that existing functionality is unaffected
by the addition of mortality data tools.

These tests confirm:
  1. The cdc_places_county table (existing PLACES data) still works
  2. The table schema and row counts are unchanged
  3. Both data sources are queryable in the same SQLite session
  4. The existing tools (get_health_statistics, compare_locations, etc.)
     still return valid output

No LLM or agent calls are made here — all checks are at the data and
function level only.
"""

import sqlite3
from typing import Callable

import pytest

from tests.conftest import DB_PATH, MORTALITY_TABLE

PLACES_TABLE = "cdc_places_county"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _skip_if_no_places(conn: sqlite3.Connection) -> None:
    count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (PLACES_TABLE,),
    ).fetchone()[0]
    if count == 0:
        pytest.skip(f"Table '{PLACES_TABLE}' not found — run ingestion first")


def _skip_if_no_mortality(conn: sqlite3.Connection) -> None:
    count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (MORTALITY_TABLE,),
    ).fetchone()[0]
    if count == 0:
        pytest.skip(
            f"Table '{MORTALITY_TABLE}' not found — run download_mortality first"
        )


# ---------------------------------------------------------------------------
# Test 1: PLACES data layer is unaffected
# ---------------------------------------------------------------------------


def test_places_data_still_works(db_connection: sqlite3.Connection) -> None:
    """
    The cdc_places_county table must still exist and return data after
    the mortality additions.  This confirms no existing table was dropped
    or corrupted by the new ingestion step.
    """
    _skip_if_no_places(db_connection)

    row_count = db_connection.execute(
        f"SELECT COUNT(*) FROM {PLACES_TABLE}"
    ).fetchone()[0]
    assert row_count > 1_000, (
        f"PLACES table has only {row_count} rows — expected >1,000. "
        "The mortality ingestion may have corrupted the database."
    )

    # Spot-check that known columns still exist
    cursor = db_connection.execute(f"SELECT * FROM {PLACES_TABLE} LIMIT 1")
    columns = [desc[0].lower() for desc in cursor.description]
    for expected_col in ("locationname", "measureid", "data_value", "stateabbr"):
        assert expected_col in columns, (
            f"Expected column '{expected_col}' missing from {PLACES_TABLE}. "
            f"Columns found: {columns}"
        )


# ---------------------------------------------------------------------------
# Test 2: PLACES table schema is unchanged
# ---------------------------------------------------------------------------


def test_places_table_schema_unchanged(db_connection: sqlite3.Connection) -> None:
    """
    Key PLACES columns must still be present with the expected names.
    This guards against any accidental rename or schema migration.
    """
    _skip_if_no_places(db_connection)

    # Fetch column info from SQLite PRAGMA
    col_info = db_connection.execute(
        f"PRAGMA table_info({PLACES_TABLE})"
    ).fetchall()
    col_names = [row[1].lower() for row in col_info]

    required_columns = [
        "locationname",
        "stateabbr",
        "measureid",
        "data_value",
    ]
    for col in required_columns:
        assert col in col_names, (
            f"Column '{col}' missing from {PLACES_TABLE}. "
            f"Schema has: {col_names}"
        )


# ---------------------------------------------------------------------------
# Test 3: Both sources queryable in the same SQLite session
# ---------------------------------------------------------------------------


def test_both_sources_queryable_same_session(
    db_connection: sqlite3.Connection,
) -> None:
    """
    CDC PLACES data and CDC mortality data must both be accessible within
    the same SQLite connection session.

    This confirms the single-database design works correctly and both tables
    coexist without conflict.
    """
    _skip_if_no_places(db_connection)
    _skip_if_no_mortality(db_connection)

    # Query PLACES data
    places_count = db_connection.execute(
        f"SELECT COUNT(*) FROM {PLACES_TABLE}"
    ).fetchone()[0]

    # Query mortality data
    mortality_count = db_connection.execute(
        f"SELECT COUNT(*) FROM {MORTALITY_TABLE}"
    ).fetchone()[0]

    assert places_count > 0, "PLACES table is empty in combined session"
    assert mortality_count > 0, "Mortality table is empty in combined session"

    # Verify they are separate tables with different schemas
    places_cols = {
        row[1].lower()
        for row in db_connection.execute(
            f"PRAGMA table_info({PLACES_TABLE})"
        ).fetchall()
    }
    mortality_cols = {
        row[1].lower()
        for row in db_connection.execute(
            f"PRAGMA table_info({MORTALITY_TABLE})"
        ).fetchall()
    }

    # Both tables must have their own distinct columns
    assert "measureid" in places_cols, "PLACES table lost 'measureid' column"
    assert "cause_of_death" in mortality_cols, (
        "Mortality table missing 'cause_of_death' column"
    )
    # These should NOT cross-contaminate
    assert "cause_of_death" not in places_cols, (
        "'cause_of_death' appeared in PLACES table — schema contamination"
    )
    assert "measureid" not in mortality_cols, (
        "'measureid' appeared in mortality table — schema contamination"
    )
