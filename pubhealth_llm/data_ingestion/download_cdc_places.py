"""
CDC PLACES Data Downloader and SQLite Loader.

Downloads the CDC PLACES 2023 county-level health measures dataset
(~30 MB CSV) and stores it in a local SQLite database for fast SQL
queries by the agent.

CDC PLACES documentation:
https://www.cdc.gov/places/index.html

Usage:
    python -m data_ingestion.download_cdc_places
"""

import logging
import sqlite3
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CDC_PLACES_URL = (
    "https://data.cdc.gov/api/views/cwsq-ngmh/rows.csv?accessType=DOWNLOAD"
)
DB_PATH = Path(__file__).parents[2] / "data" / "healthpub.db"
TABLE_NAME = "health_measures"
CHUNK_SIZE = 8192  # bytes per download chunk
CSV_CACHE_PATH = Path(__file__).parents[2] / "data" / "cdc_places_raw.csv"

# Columns we want to keep (reduces storage and speeds up queries).
# Full column list from the dataset — drop purely administrative fields.
KEEP_COLUMNS = [
    "Year",
    "StateAbbr",
    "StateDesc",
    "LocationName",
    "DataSource",
    "Category",
    "Measure",
    "Data_Value_Unit",
    "Data_Value_Type",
    "Data_Value",
    "Low_Confidence_Limit",
    "High_Confidence_Limit",
    "TotalPopulation",
    "LocationID",
    "CategoryID",
    "MeasureId",
    "DataValueTypeID",
    "Short_Question_Text",
    "Geolocation",
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def download_csv(url: str, dest: Path) -> Path:
    """
    Stream-download a CSV file with a progress bar.

    Args:
        url:  Source URL to download from.
        dest: Local path to write the file to.

    Returns:
        The path where the file was saved.
    """
    logger.info("Downloading CDC PLACES CSV from %s", url)
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "wb") as fh, tqdm(
        desc="CDC PLACES",
        total=total,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            fh.write(chunk)
            bar.update(len(chunk))

    logger.info("Saved raw CSV to %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


# ---------------------------------------------------------------------------
# SQLite loading
# ---------------------------------------------------------------------------


def load_csv_to_sqlite(csv_path: Path, db_path: Path) -> int:
    """
    Parse the CDC PLACES CSV and upsert rows into SQLite.

    The function is idempotent: if the table already exists and
    contains data for the same Year + LocationID + MeasureId combination,
    those rows are replaced rather than duplicated.

    Args:
        csv_path: Path to the downloaded CSV file.
        db_path:  Path to the SQLite database (created if absent).

    Returns:
        Number of rows written to the database.
    """
    logger.info("Parsing CSV — this may take a moment for ~30 MB …")
    df = pd.read_csv(csv_path, dtype=str, low_memory=False)

    # Keep only the columns we need (tolerate missing ones gracefully).
    available = [c for c in KEEP_COLUMNS if c in df.columns]
    df = df[available].copy()

    # Coerce numeric columns.
    for col in ("Data_Value", "Low_Confidence_Limit", "High_Confidence_Limit",
                "TotalPopulation", "Year"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    try:
        # Drop and recreate so re-running ingestion never duplicates rows.
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
        df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)

        # Add indexes for the columns most often filtered on.
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_state ON {TABLE_NAME}(StateAbbr)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_location ON {TABLE_NAME}(LocationName)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_measure ON {TABLE_NAME}(MeasureId)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_year ON {TABLE_NAME}(Year)"
        )
        conn.commit()
        logger.info("Wrote %d rows to table '%s' in %s", len(df), TABLE_NAME, db_path)
    finally:
        conn.close()

    return len(df)


def build_metadata_table(db_path: Path) -> None:
    """
    Create a helper table with unique measures for fast lookup.

    This allows the agent tool `get_available_measures()` to respond
    quickly without scanning the full health_measures table.

    Args:
        db_path: Path to the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS available_measures")
        conn.execute(
            """
            CREATE TABLE available_measures AS
            SELECT DISTINCT
                MeasureId,
                Measure,
                Short_Question_Text,
                Category,
                Data_Value_Unit
            FROM health_measures
            WHERE MeasureId IS NOT NULL
            ORDER BY Category, Measure
            """
        )
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM available_measures"
        ).fetchone()[0]
        logger.info("Built available_measures table with %d distinct measures", count)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(force_download: bool = False) -> None:
    """
    Full pipeline: download CSV → load SQLite → build metadata table.

    Args:
        force_download: If True, re-download even if the cache file exists.
    """
    if CSV_CACHE_PATH.exists() and not force_download:
        logger.info(
            "Using cached CSV at %s (pass force_download=True to re-fetch)",
            CSV_CACHE_PATH,
        )
    else:
        download_csv(CDC_PLACES_URL, CSV_CACHE_PATH)

    load_csv_to_sqlite(CSV_CACHE_PATH, DB_PATH)
    build_metadata_table(DB_PATH)
    logger.info("CDC PLACES ingestion complete.")


if __name__ == "__main__":
    run()
