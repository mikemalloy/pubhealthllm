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
    result = client.query_one("SELECT 1 AS ping", {})
    assert result is not None, "Aurora warm-up failed: SELECT 1 returned None"
    return client


# ---------------------------------------------------------------------------
# Task 1: db.py DataAPIClient basics
# ---------------------------------------------------------------------------

def test_db_client_instantiates(aurora_db):
    """DataAPIClient must instantiate without error when env vars are set."""
    assert aurora_db is not None


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
