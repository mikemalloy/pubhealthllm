"""
CDC PLACES County-Level Data Downloader.

Migrates the existing census-tract table to a backup name, then downloads
the county-level CDC PLACES dataset and stores it as a new table in the
same SQLite database.

Why county vs. tract:
    The census-tract dataset (cwsq-ngmh) uses FIPS codes as LocationName,
    making geographic queries unreliable.  The county dataset (swc5-untb)
    uses readable names like "Alameda County", which is what the agent
    tools expect.

Idempotency:
    Safe to run multiple times.  The existing cdc_places table is renamed
    to cdc_places_tract only once (if it hasn't been renamed already).
    The cdc_places_county table is dropped and rebuilt fresh each run.

Usage:
    python -m pubhealth_llm.data_ingestion.download_county_data
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

COUNTY_URL = (
    "https://data.cdc.gov/api/views/swc5-untb/rows.csv?accessType=DOWNLOAD"
)

DB_PATH = Path(__file__).parents[2] / "data" / "healthgpt.db"
CSV_CACHE_PATH = Path(__file__).parents[2] / "data" / "cdc_places_county_raw.csv"

TABLE_TRACT = "cdc_places_tract"       # renamed backup of old census-tract data
TABLE_COUNTY = "cdc_places_county"     # new county-level table
CHUNK_SIZE = 8192                       # bytes per download chunk

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: Rename existing tract table
# ---------------------------------------------------------------------------


def rename_tract_table(db_path: Path) -> None:
    """
    Rename cdc_places → cdc_places_tract to preserve the census-tract data.

    Skips silently if:
    - cdc_places does not exist (fresh install)
    - cdc_places_tract already exists (already renamed on a prior run)

    Args:
        db_path: Path to the SQLite database.
    """
    if not db_path.exists():
        logger.info("Database not found at %s — nothing to rename.", db_path)
        return

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        if TABLE_TRACT in tables:
            logger.info(
                "Table '%s' already exists — skipping rename.", TABLE_TRACT
            )
            return

        if "cdc_places" not in tables:
            logger.info(
                "Table 'cdc_places' not found — nothing to rename."
            )
            return

        conn.execute(f"ALTER TABLE cdc_places RENAME TO {TABLE_TRACT}")
        conn.commit()
        logger.info(
            "Renamed 'cdc_places' → '%s' (census-tract data preserved).",
            TABLE_TRACT,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Step 2: Download county CSV
# ---------------------------------------------------------------------------


def download_csv(url: str, dest: Path, force: bool = False) -> Path:
    """
    Stream-download the county CSV with a progress bar.

    Args:
        url:   Source URL.
        dest:  Local destination path.
        force: If True, re-download even if the file already exists.

    Returns:
        Path to the downloaded file.
    """
    if dest.exists() and not force:
        logger.info(
            "Using cached county CSV at %s (%.1f MB)",
            dest,
            dest.stat().st_size / 1e6,
        )
        return dest

    logger.info("Downloading CDC PLACES county data from %s …", url)
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "wb") as fh, tqdm(
        desc="CDC PLACES county",
        total=total,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            fh.write(chunk)
            bar.update(len(chunk))

    logger.info(
        "Saved county CSV to %s (%.1f MB)", dest, dest.stat().st_size / 1e6
    )
    return dest


# ---------------------------------------------------------------------------
# Step 3: Load county CSV into SQLite
# ---------------------------------------------------------------------------


def load_county_to_sqlite(csv_path: Path, db_path: Path) -> int:
    """
    Parse the county CSV and write it to the cdc_places_county table.

    The table is dropped and recreated each run (idempotent).
    Indexes are added on the columns most frequently filtered by the
    agent tools.

    Args:
        csv_path: Path to the downloaded county CSV.
        db_path:  Path to the SQLite database.

    Returns:
        Number of rows written.
    """
    logger.info("Parsing county CSV …")
    df = pd.read_csv(csv_path, dtype=str, low_memory=False)

    # Coerce numeric columns so SQL comparisons work correctly
    for col in (
        "Data_Value",
        "Low_Confidence_Limit",
        "High_Confidence_Limit",
        "TotalPopulation",
        "Year",
    ):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info("Parsed %d rows, %d columns", len(df), len(df.columns))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_COUNTY}")
        df.to_sql(TABLE_COUNTY, conn, if_exists="replace", index=False)

        # Indexes for the columns the agent tools filter on most often
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_county_state "
            f"ON {TABLE_COUNTY}(StateAbbr)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_county_location "
            f"ON {TABLE_COUNTY}(LocationName)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_county_measure "
            f"ON {TABLE_COUNTY}(MeasureId)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_county_year "
            f"ON {TABLE_COUNTY}(Year)"
        )
        conn.commit()
        logger.info(
            "Wrote %d rows to table '%s' in %s", len(df), TABLE_COUNTY, db_path
        )
    finally:
        conn.close()

    return len(df)


# ---------------------------------------------------------------------------
# Step 4: Verification
# ---------------------------------------------------------------------------


def verify(db_path: Path) -> None:
    """
    Print 5 sample California county names to confirm the load worked.

    Args:
        db_path: Path to the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT DISTINCT LocationName
            FROM {TABLE_COUNTY}
            WHERE StateAbbr = 'CA'
              AND LocationName IS NOT NULL
            ORDER BY LocationName
            LIMIT 5
            """
        ).fetchall()
    finally:
        conn.close()

    print("\n--- Verification: 5 California counties in cdc_places_county ---")
    if rows:
        for (name,) in rows:
            print(f"  {name}")
    else:
        print("  WARNING: No California rows found — check the download.")
    print("-------------------------------------------------------------------\n")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(force_download: bool = False) -> None:
    """
    Full pipeline: rename tract table → download county CSV → load → verify.

    Args:
        force_download: Re-download the CSV even if cached locally.
    """
    print("\n=== CDC PLACES County Data Download ===\n")

    print("Step 1/3 — Preserving census-tract data …")
    rename_tract_table(DB_PATH)

    print("Step 2/3 — Downloading county-level CSV …")
    download_csv(COUNTY_URL, CSV_CACHE_PATH, force=force_download)

    print("Step 3/3 — Loading into SQLite …")
    row_count = load_county_to_sqlite(CSV_CACHE_PATH, DB_PATH)

    print(f"\nDone. {row_count:,} county rows loaded into '{TABLE_COUNTY}'.")
    verify(DB_PATH)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download CDC PLACES county data into SQLite"
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download the CSV even if already cached",
    )
    args = parser.parse_args()
    run(force_download=args.force_download)
