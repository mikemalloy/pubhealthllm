"""
Shared pytest configuration and fixtures for pubHealthLLM tests.
"""

import os
import sqlite3
from pathlib import Path
from typing import Generator

import pytest
from dotenv import load_dotenv

# Load .env before any test runs
load_dotenv(Path(__file__).parents[1] / ".env")

# ---------------------------------------------------------------------------
# Paths (derived from repo root, not cwd, so tests run from anywhere)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[1]
DB_PATH = REPO_ROOT / "data" / "healthgpt.db"
CHROMA_DIR = REPO_ROOT / "data" / "chroma_db"
PDF_DIR = REPO_ROOT / "data" / "mmwr_pdfs"

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
def chroma_dir() -> Path:
    """Return the ChromaDB directory, skipping if it doesn't exist."""
    if not CHROMA_DIR.exists() or not any(CHROMA_DIR.iterdir()):
        pytest.skip(f"ChromaDB not found at {CHROMA_DIR} — run ingestion first")
    return CHROMA_DIR


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
