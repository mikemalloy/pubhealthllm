"""
Shared pytest configuration and fixtures for pubHealthLLM tests.
"""

import os
import sqlite3
from pathlib import Path
from typing import Generator

import boto3
import pytest
from dotenv import load_dotenv

# Load .env before any test runs
load_dotenv(Path(__file__).parents[1] / ".env")

# ---------------------------------------------------------------------------
# Paths (derived from repo root, not cwd, so tests run from anywhere)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[1]
DB_PATH = REPO_ROOT / "data" / "healthgpt.db"
PDF_DIR = REPO_ROOT / "data" / "mmwr_pdfs"

AWS_REGION = os.environ.get("AWS_REGION", "us-west-1")

MORTALITY_TABLE = "cdc_wonder_mortality"


# ---------------------------------------------------------------------------
# Existing fixtures (unchanged)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def anthropic_api_key() -> str:
    """Return the ANTHROPIC_API_KEY, skipping the test if it is absent."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set — skipping live API tests")
    return key


@pytest.fixture(scope="session")
def db_path() -> Path:
    """Return the SQLite DB path (healthgpt.db), skipping if it doesn't exist."""
    if not DB_PATH.exists():
        pytest.skip(f"SQLite DB not found at {DB_PATH} — run ingestion first")
    return DB_PATH


@pytest.fixture(scope="session")
def s3v_index():
    """Return a boto3 s3vectors client, skipping if VECTOR_BUCKET is not set."""
    vector_bucket = os.environ.get("VECTOR_BUCKET", "")
    if not vector_bucket:
        pytest.skip("VECTOR_BUCKET not set — skipping S3 Vectors tests")
    return boto3.client("s3vectors", region_name=AWS_REGION)


@pytest.fixture(scope="session")
def aurora_db():
    """Return a DataAPIClient connected to Aurora. Skips if AURORA_CLUSTER_ARN unset.

    Warms the cluster with SELECT 1 before tests run (absorbs cold-start latency).
    """
    if not os.environ.get("AURORA_CLUSTER_ARN"):
        pytest.skip("AURORA_CLUSTER_ARN not set — skipping Aurora tests")
    from pubhealth_llm.app.db import DataAPIClient
    client = DataAPIClient()
    try:
        result = client.query_one("SELECT 1 AS ping", {})
    except Exception as exc:
        pytest.skip(f"Aurora unreachable during warm-up: {exc}")
    if result is None:
        pytest.skip("Aurora warm-up returned None — cluster may be unavailable")
    return client


# ---------------------------------------------------------------------------
# Mortality fixtures (new)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Provide a SQLite connection to healthgpt.db for mortality tests.
    Skips if the database does not exist.
    """
    if not DB_PATH.exists():
        pytest.skip(f"SQLite DB not found at {DB_PATH} — run ingestion first")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def mortality_table_exists() -> bool:
    """
    Return True if the cdc_wonder_mortality table has been populated.
    Used by mortality tests to skip gracefully before ingestion is run.
    """
    if not DB_PATH.exists():
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (MORTALITY_TABLE,),
        ).fetchone()[0]
        if count == 0:
            return False
        rows = conn.execute(
            f"SELECT COUNT(*) FROM {MORTALITY_TABLE}"
        ).fetchone()[0]
        conn.close()
        return rows > 0
    except Exception:
        return False


@pytest.fixture
def mortality_tool():
    """
    Return the get_mortality_data function for direct tool testing.
    No agent or LLM involved — pure function call.
    """
    from pubhealth_llm.app.tools import get_mortality_data
    return get_mortality_data


@pytest.fixture
def compare_tool():
    """
    Return the compare_mortality function for direct tool testing.
    No agent or LLM involved — pure function call.
    """
    from pubhealth_llm.app.tools import compare_mortality
    return compare_mortality


# ---------------------------------------------------------------------------
# HTTP / auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def override_clerk_guard():
    """
    Override the Clerk auth guard for every test via FastAPI dependency_overrides.

    This makes all protected routes behave as if the user is authenticated,
    without a real Clerk token. The override is always cleaned up after the
    test, even on failure.

    Why autouse: every test that exercises the FastAPI app should get clean
    auth behavior. Tests that don't import server are unaffected (the import
    inside the fixture is deferred and cheap once server is cached).

    To test the *unauthenticated* path in a specific test:
        def test_401(override_clerk_guard):
            app.dependency_overrides.pop(clerk_guard)
            # ... make request, assert 401 ...
    """
    try:
        from server import app, clerk_guard
        app.dependency_overrides[clerk_guard] = lambda: {"sub": "test-user-id"}
        yield
    finally:
        try:
            from server import app, clerk_guard
            app.dependency_overrides.pop(clerk_guard, None)
        except ImportError:
            pass
