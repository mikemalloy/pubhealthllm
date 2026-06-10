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
