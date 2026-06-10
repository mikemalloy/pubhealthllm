"""
Tests for the Aurora migration — verify post-migration state via Data API.

All tests are live (call Aurora). They fail before migration runs
(relation does not exist) and pass after migrate_aurora.py completes.

Guard: skips if AURORA_CLUSTER_ARN or AURORA_SECRET_ARN not set.
"""
import os

import boto3
import pytest

AURORA_CLUSTER_ARN = os.environ.get("AURORA_CLUSTER_ARN", "")
AURORA_SECRET_ARN = os.environ.get("AURORA_SECRET_ARN", "")
AURORA_DATABASE = os.environ.get("AURORA_DATABASE", "pubhealth")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-1")


@pytest.fixture(scope="session")
def rds():
    """boto3 rds-data client; skips if Aurora env vars are absent."""
    if not AURORA_CLUSTER_ARN or not AURORA_SECRET_ARN:
        pytest.skip("AURORA_CLUSTER_ARN / AURORA_SECRET_ARN not set — skipping Aurora tests")
    return boto3.client("rds-data", region_name=AWS_REGION)


def _q(client, sql, params=None):
    """Execute a SQL statement via the Data API and return the response."""
    kwargs = dict(
        resourceArn=AURORA_CLUSTER_ARN,
        secretArn=AURORA_SECRET_ARN,
        database=AURORA_DATABASE,
        sql=sql,
    )
    if params:
        kwargs["parameters"] = params
    return client.execute_statement(**kwargs)


def _scalar(resp) -> int | float | str | None:
    """Extract the single scalar value from a Data API response."""
    field = resp["records"][0][0]
    return (
        field.get("longValue")
        or field.get("doubleValue")
        or field.get("stringValue")
        or field.get("booleanValue")
    )


# ---------------------------------------------------------------------------
# Table existence + row counts
# ---------------------------------------------------------------------------


def test_locations_row_count(rds):
    """locations must have ≥3,145 rows (3,144 counties + national + states)."""
    count = _scalar(_q(rds, "SELECT COUNT(*) FROM locations"))
    assert count >= 3145, f"Expected ≥3145 location rows, got {count}"


def test_measures_row_count(rds):
    """measures must have exactly 40 rows (one per CDC PLACES measure)."""
    count = _scalar(_q(rds, "SELECT COUNT(*) FROM measures"))
    assert count == 40, f"Expected 40 measure rows, got {count}"


def test_health_facts_row_count(rds):
    """health_facts must have ≥200,000 rows (229,298 in source, minus nulls)."""
    count = _scalar(_q(rds, "SELECT COUNT(*) FROM health_facts"))
    assert count >= 200_000, f"Expected ≥200,000 health_fact rows, got {count}"


def test_mortality_facts_row_count(rds):
    """mortality_facts must have ≥5,000 rows."""
    count = _scalar(_q(rds, "SELECT COUNT(*) FROM mortality_facts"))
    assert count >= 5_000, f"Expected ≥5,000 mortality rows, got {count}"


# ---------------------------------------------------------------------------
# geo_level integrity
# ---------------------------------------------------------------------------


def test_locations_geo_level_values(rds):
    """geo_level must only contain 'county', 'state', or 'national'."""
    resp = _q(
        rds,
        "SELECT COUNT(*) FROM locations "
        "WHERE geo_level NOT IN ('county', 'state', 'national')",
    )
    bad = _scalar(resp)
    assert bad == 0, f"{bad} rows have invalid geo_level"


def test_locations_has_state_rows(rds):
    """Must have 51 state rows (50 states + DC)."""
    count = _scalar(_q(rds, "SELECT COUNT(*) FROM locations WHERE geo_level = 'state'"))
    assert count == 51, f"Expected 51 state rows, got {count}"


def test_locations_has_national_row(rds):
    """Must have exactly 1 national row."""
    count = _scalar(_q(rds, "SELECT COUNT(*) FROM locations WHERE geo_level = 'national'"))
    assert count == 1, f"Expected 1 national row, got {count}"


# ---------------------------------------------------------------------------
# Sanity query 1: exact FIPS lookup — Travis County, TX (48453)
# ---------------------------------------------------------------------------


def test_travis_county_fips_lookup(rds):
    """Travis County TX must exist at FIPS 48453 with state_abbr='TX'."""
    resp = _q(
        rds,
        "SELECT fips, canonical_name, state_abbr, geo_level "
        "FROM locations WHERE fips = :fips",
        [{"name": "fips", "value": {"stringValue": "48453"}}],
    )
    assert resp["records"], "Travis County (48453) not found in locations"
    row = resp["records"][0]
    assert row[2]["stringValue"] == "TX", (
        f"Expected state_abbr='TX', got '{row[2]}'"
    )
    assert row[3]["stringValue"] == "county"


def test_travis_diabetes_values(rds):
    """Travis County (48453) must have CrdPrv and AgeAdjPrv diabetes rows."""
    resp = _q(
        rds,
        "SELECT value, value_type FROM health_facts "
        "WHERE location_fips = :fips AND measure_id = :mid "
        "ORDER BY value_type",
        [
            {"name": "fips", "value": {"stringValue": "48453"}},
            {"name": "mid", "value": {"stringValue": "DIABETES"}},
        ],
    )
    rows = resp["records"]
    assert len(rows) >= 2, (
        f"Expected ≥2 diabetes rows for Travis County, got {len(rows)}"
    )
    value_types = {r[1]["stringValue"] for r in rows}
    assert "CrdPrv" in value_types, f"Missing CrdPrv. Got: {value_types}"
    assert "AgeAdjPrv" in value_types, f"Missing AgeAdjPrv. Got: {value_types}"


# ---------------------------------------------------------------------------
# Sanity query 2: exact FIPS lookup — Cook County, IL (17031)
# ---------------------------------------------------------------------------


def test_cook_county_fips_lookup(rds):
    """Cook County IL must exist at FIPS 17031 with state_abbr='IL'."""
    resp = _q(
        rds,
        "SELECT fips, canonical_name, state_abbr, geo_level "
        "FROM locations WHERE fips = :fips",
        [{"name": "fips", "value": {"stringValue": "17031"}}],
    )
    assert resp["records"], "Cook County (17031) not found in locations"
    row = resp["records"][0]
    assert row[2]["stringValue"] == "IL", (
        f"Expected state_abbr='IL', got '{row[2]}'"
    )
    assert row[3]["stringValue"] == "county"


def test_cook_diabetes_values(rds):
    """Cook County (17031) must have CrdPrv and AgeAdjPrv diabetes rows."""
    resp = _q(
        rds,
        "SELECT value, value_type FROM health_facts "
        "WHERE location_fips = :fips AND measure_id = :mid "
        "ORDER BY value_type",
        [
            {"name": "fips", "value": {"stringValue": "17031"}},
            {"name": "mid", "value": {"stringValue": "DIABETES"}},
        ],
    )
    rows = resp["records"]
    assert len(rows) >= 2, (
        f"Expected ≥2 diabetes rows for Cook County, got {len(rows)}"
    )
    value_types = {r[1]["stringValue"] for r in rows}
    assert "CrdPrv" in value_types, f"Missing CrdPrv. Got: {value_types}"
    assert "AgeAdjPrv" in value_types, f"Missing AgeAdjPrv. Got: {value_types}"
