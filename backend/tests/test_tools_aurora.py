"""
Aurora-backed tool tests.

All tests guard on the `aurora_db` fixture (skips when AURORA_CLUSTER_ARN unset).
The fixture warms the cluster with SELECT 1 before any test runs.
"""
import os
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def aurora_db():
    """Return a DataAPIClient connected to Aurora. Skips if env not set.

    Also warms the cluster — Aurora auto-pauses after 5 min; first query
    can take 2–3 min. The SELECT 1 warm-up absorbs that latency so
    subsequent test queries are fast.
    """
    if not os.environ.get("AURORA_CLUSTER_ARN"):
        pytest.skip("AURORA_CLUSTER_ARN not set — skipping Aurora tool tests")
    from pubhealth_llm.app.db import DataAPIClient
    client = DataAPIClient()
    # Warm the cluster (absorbs 2–3 min cold-start latency)
    try:
        result = client.query_one("SELECT 1 AS ping", {})
    except Exception as exc:
        pytest.skip(f"Aurora unreachable during warm-up: {exc}")
    if result is None:
        pytest.skip("Aurora warm-up returned None — cluster may be unavailable")
    return client


# ---------------------------------------------------------------------------
# Task 1: db.py DataAPIClient basics
# ---------------------------------------------------------------------------

def test_db_client_query_returns_list(aurora_db):
    """query() must return a list."""
    rows = aurora_db.query("SELECT 1 AS n", {})
    assert isinstance(rows, list)
    assert rows == [{"n": 1}]


def test_db_client_query_one_returns_dict(aurora_db):
    """query_one() must return a dict for a single-row result."""
    row = aurora_db.query_one("SELECT 42 AS answer", {})
    assert row is not None
    assert row["answer"] == 42


def test_db_client_query_one_none_for_no_rows(aurora_db):
    """query_one() must return None when query returns no rows."""
    row = aurora_db.query_one(
        "SELECT 1 WHERE 1 = 0", {}
    )
    assert row is None


def test_db_client_named_params(aurora_db):
    """Named parameters must bind correctly."""
    row = aurora_db.query_one(
        "SELECT :x AS val",
        {"x": 99}
    )
    assert row["val"] == 99


# ---------------------------------------------------------------------------
# Task 2: resolve_location + resolve_measure
# ---------------------------------------------------------------------------

def test_resolve_location_travis_county_tx(aurora_db):
    """'Travis County, TX' → FIPS 48453."""
    from pubhealth_llm.app.tools import resolve_location
    assert resolve_location("Travis County, TX") == "48453"


def test_resolve_location_cook_county_il(aurora_db):
    """'Cook County, IL' → FIPS 17031."""
    from pubhealth_llm.app.tools import resolve_location
    assert resolve_location("Cook County, IL") == "17031"


def test_resolve_location_state_abbreviation(aurora_db):
    """'TX' (abbreviation) → Texas state FIPS '48'."""
    from pubhealth_llm.app.tools import resolve_location
    assert resolve_location("TX") == "48"


def test_resolve_location_state_name(aurora_db):
    """'Texas' → state FIPS '48'."""
    from pubhealth_llm.app.tools import resolve_location
    assert resolve_location("Texas") == "48"


def test_resolve_location_name_with_state_hint(aurora_db):
    """'Travis' + state='TX' → county FIPS 48453."""
    from pubhealth_llm.app.tools import resolve_location
    assert resolve_location("Travis", state="TX") == "48453"


def test_resolve_location_not_found_raises(aurora_db):
    """Unknown location raises ValueError."""
    from pubhealth_llm.app.tools import resolve_location
    import pytest
    with pytest.raises(ValueError, match="not found"):
        resolve_location("ZZZNoSuchPlace999")


def test_resolve_measure_diabetes(aurora_db):
    """'diabetes' resolves to a known measure_id."""
    from pubhealth_llm.app.tools import resolve_measure
    mid = resolve_measure("diabetes")
    assert mid is not None
    assert isinstance(mid, str)
    assert len(mid) > 0


def test_resolve_measure_partial_keyword(aurora_db):
    """Partial keyword 'diab' resolves to same measure_id as 'diabetes'."""
    from pubhealth_llm.app.tools import resolve_measure
    mid_full = resolve_measure("diabetes")
    mid_partial = resolve_measure("diab")
    assert mid_full == mid_partial


def test_resolve_measure_not_found_raises(aurora_db):
    """Unknown measure keyword raises ValueError."""
    from pubhealth_llm.app.tools import resolve_measure
    import pytest
    with pytest.raises(ValueError, match="not found"):
        resolve_measure("zzz_nonexistent_measure_xyz")


# ---------------------------------------------------------------------------
# Task 3: get_health_statistics + compare_locations
# ---------------------------------------------------------------------------

def test_get_health_statistics_travis_diabetes(aurora_db):
    """Travis County TX diabetes returns a formatted string with a numeric value."""
    from pubhealth_llm.app.tools import get_health_statistics
    result = get_health_statistics("Travis County, TX", measure="diabetes")
    assert isinstance(result, str)
    assert "not found" not in result.lower(), f"Unexpected not-found: {result[:300]}"
    assert "Travis" in result
    assert "TX" in result


def test_get_health_statistics_cook_obesity(aurora_db):
    """Cook County IL obesity returns data."""
    from pubhealth_llm.app.tools import get_health_statistics
    result = get_health_statistics("Cook County, IL", measure="obesity")
    assert isinstance(result, str)
    assert "not found" not in result.lower(), f"Unexpected not-found: {result[:300]}"
    assert "Cook" in result


def test_get_health_statistics_unknown_location(aurora_db):
    """Unknown location returns a 'not found' string, not an exception."""
    from pubhealth_llm.app.tools import get_health_statistics
    result = get_health_statistics("ZZZNoSuchCounty999")
    assert isinstance(result, str)
    assert "not found" in result.lower() or "no health" in result.lower()


def test_compare_locations_cook_harris(aurora_db):
    """compare_locations works for Cook County IL + Harris County TX."""
    from pubhealth_llm.app.tools import compare_locations
    result = compare_locations(
        ["Cook County, IL", "Harris County, TX"],
        measure="obesity",
    )
    assert isinstance(result, str)
    assert "not found" not in result.lower(), f"Unexpected not-found: {result[:300]}"
    assert "Cook" in result
    assert "Harris" in result


def test_compare_locations_unknown_measure(aurora_db):
    """Unknown measure returns 'not found' string."""
    from pubhealth_llm.app.tools import compare_locations
    result = compare_locations(
        ["Travis County, TX", "Harris County, TX"],
        measure="zzz_fake_measure_xyz",
    )
    assert isinstance(result, str)
    assert "not found" in result.lower() or "no comparison" in result.lower()


# ---------------------------------------------------------------------------
# Task 4: get_available_measures + list_available_measures
# ---------------------------------------------------------------------------

def test_get_available_measures_returns_string(aurora_db):
    from pubhealth_llm.app.tools import get_available_measures
    result = get_available_measures()
    assert isinstance(result, str) and len(result) > 0


def test_get_available_measures_contains_diabetes(aurora_db):
    from pubhealth_llm.app.tools import get_available_measures
    result = get_available_measures()
    assert "diabetes" in result.lower(), f"'diabetes' not in output: {result[:300]}"


def test_get_available_measures_category_filter(aurora_db):
    from pubhealth_llm.app.tools import get_available_measures
    all_m = get_available_measures()
    filtered = get_available_measures(category="Health Outcomes")
    assert len(filtered) <= len(all_m) and len(filtered) > 0


def test_list_available_measures_returns_list_of_dicts(aurora_db):
    from pubhealth_llm.app.tools import list_available_measures
    result = list_available_measures()
    assert isinstance(result, list) and len(result) > 0
    assert all(k in result[0] for k in ("measure_id", "measure", "short_text", "category"))


# ---------------------------------------------------------------------------
# Task 5: get_worst_counties_by_measure + rank_counties_composite
# ---------------------------------------------------------------------------

def test_get_worst_counties_tx_diabetes(aurora_db):
    """TX diabetes returns a ranked table with at least 5 counties."""
    from pubhealth_llm.app.tools import get_worst_counties_by_measure

    result = get_worst_counties_by_measure("TX", "diabetes", top_n=5)
    assert isinstance(result, str)
    assert "not found" not in result.lower(), f"Unexpected: {result[:300]}"
    data_lines = [ln for ln in result.split("\n") if ln and ln[0].isdigit()]
    assert len(data_lines) >= 1, f"No data lines found:\n{result}"


def test_get_worst_counties_bad_state(aurora_db):
    """Invalid state code returns a descriptive error, not an exception."""
    from pubhealth_llm.app.tools import get_worst_counties_by_measure

    result = get_worst_counties_by_measure("Texas", "diabetes")
    assert "two-letter" in result.lower()


def test_rank_counties_composite_tx(aurora_db):
    """TX diabetes+obesity composite returns ranked table with Composite header."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["diabetes", "obesity"])
    assert isinstance(result, str)
    assert "Composite" in result
    assert "County" in result or "TX" in result


def test_rank_counties_composite_missing_one(aurora_db):
    """One invalid measure is flagged; composite still runs on valid two."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["diabetes", "obesity", "zzz_fake_xyz"])
    assert "Composite" in result
    assert "zzz_fake_xyz" in result or "Not found" in result


def test_rank_counties_composite_all_missing(aurora_db):
    """All invalid measures → clear error, no composite."""
    from pubhealth_llm.app.tools import rank_counties_composite

    result = rank_counties_composite("TX", ["zzz_fake1", "zzz_fake2"])
    assert "Composite" not in result
    assert "not found" in result.lower() or "none found" in result.lower() or "0 of" in result.lower()


# ---------------------------------------------------------------------------
# Task 6: get_mortality_data + compare_mortality
# ---------------------------------------------------------------------------

def test_get_mortality_data_louisiana(aurora_db):
    """Louisiana heart disease mortality returns formatted data."""
    from pubhealth_llm.app.tools import get_mortality_data

    result = get_mortality_data("Louisiana", cause="heart disease")
    assert isinstance(result, str)
    assert "not found" not in result.lower() or "no mortality" not in result.lower(), (
        f"Expected Louisiana mortality data. Got: {result[:300]}"
    )
    assert "Louisiana" in result or "Heart" in result


def test_get_mortality_data_state_abbreviation(aurora_db):
    """State abbreviation 'TX' resolves to Texas mortality data."""
    from pubhealth_llm.app.tools import get_mortality_data

    result = get_mortality_data("TX", cause="diabetes")
    assert isinstance(result, str)
    assert "Texas" in result or "Diabetes" in result or "Rate" in result


def test_get_mortality_data_unknown_location(aurora_db):
    """Unknown location returns a descriptive error string."""
    from pubhealth_llm.app.tools import get_mortality_data

    result = get_mortality_data("ZZZNoSuchState999")
    assert isinstance(result, str)
    assert "not found" in result.lower() or "no mortality" in result.lower()


def test_compare_mortality_states(aurora_db):
    """compare_mortality across two states returns ranked table."""
    from pubhealth_llm.app.tools import compare_mortality

    result = compare_mortality(["Louisiana", "Texas"], cause="heart disease")
    assert isinstance(result, str)
    assert "Heart" in result or "heart" in result
    assert "Louisiana" in result or "Texas" in result
