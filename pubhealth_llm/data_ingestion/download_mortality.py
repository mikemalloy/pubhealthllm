"""
CDC NCHS Leading Causes of Death — Data Downloader.

Downloads the NCHS Leading Causes of Death dataset from data.cdc.gov and
loads it into the cdc_wonder_mortality table in data/healthgpt.db.

DATA SOURCE
-----------
Dataset: NCHS - Leading Causes of Death: United States
Socrata ID: bi63-dtpu
URL: https://data.cdc.gov/api/views/bi63-dtpu/rows.csv?accessType=DOWNLOAD
Coverage: 1999–2017, all 50 states + national totals
Granularity: STATE-LEVEL (not county/parish level).

IMPORTANT NOTE ON GEOGRAPHIC GRANULARITY
-----------------------------------------
This dataset provides state-level mortality data. Parish/county-level CDC
Wonder data requires the CDC Wonder query interface and is not available as
a simple CSV download. For county-level mortality data, users must manually
download from https://wonder.cdc.gov/ucd-icd10.html and place the resulting
CSV in data/mortality/cdc_wonder_county.csv — the ingestion will detect and
prefer that file if present.

COLUMN MAPPING
--------------
CSV column                → DB column
--------------------------------------------------
State                     → county_name  (state name; "county" is a misnomer
                                          here but kept for schema consistency)
(none available)          → county_fips  NULL
State                     → state
(none available)          → state_fips   NULL
Cause Name                → cause_of_death
113 Cause Name            → icd10_code   (ICD-10 range extracted from parens)
Deaths                    → deaths       (NULL if suppressed/unreliable)
(none available)          → population   NULL
(none available)          → crude_rate   NULL
Age-adjusted Death Rate   → age_adjusted_rate (NULL if suppressed/unreliable)
Year                      → year

SUPPRESSED VALUES
-----------------
CDC suppresses death counts under 10 for small populations. In this dataset
no suppression was observed, but the ingestion defensively converts any
non-numeric Deaths or Rate value to NULL.

IDEMPOTENCY
-----------
The cdc_wonder_mortality table is dropped and recreated on each run.
Safe to run multiple times.

Usage:
    python -m pubhealth_llm.data_ingestion.download_mortality
    python -m pubhealth_llm.data_ingestion.download_mortality --force-download
"""

import io
import logging
import re
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MORTALITY_URL = (
    "https://data.cdc.gov/api/views/bi63-dtpu/rows.csv?accessType=DOWNLOAD"
)
MANUAL_DOWNLOAD_MSG = (
    "\n  County-level CDC Wonder mortality data is not available as a "
    "direct download.\n"
    "  To add parish/county-level mortality data:\n"
    "    1. Visit https://wonder.cdc.gov/ucd-icd10.html\n"
    "    2. Run a query for your state at the County level\n"
    "    3. Export as 'Delimited' text\n"
    "    4. Save to data/mortality/cdc_wonder_county.csv\n"
    "    5. Re-run this script — it will detect and load that file instead.\n"
)

DB_PATH = Path(__file__).parents[2] / "data" / "healthgpt.db"
MANUAL_CSV_DIR = Path(__file__).parents[2] / "data" / "mortality"
MANUAL_CSV_PATH = MANUAL_CSV_DIR / "cdc_wonder_county.csv"
CSV_CACHE_PATH = Path(__file__).parents[2] / "data" / "cdc_mortality_raw.csv"

TABLE_NAME = "cdc_wonder_mortality"
CHUNK_SIZE = 8192

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ICD-10 codes live inside parentheses at the end of "113 Cause Name"
# e.g. "Diseases of heart (I00-I09,I11,I13,I20-I51)" → "I00-I09,I11,I13,I20-I51"
_ICD10_PATTERN = re.compile(r"\(([A-Z][^)]+)\)\s*$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_icd10(raw: str) -> Optional[str]:
    """
    Pull the ICD-10 code range out of the '113 Cause Name' column.

    Example:
        "Accidents (unintentional injuries) (V01-X59,Y85-Y86)"
        → "V01-X59,Y85-Y86"

    Args:
        raw: Full string from the 113 Cause Name column.

    Returns:
        ICD-10 code string, or None if not parseable.
    """
    m = _ICD10_PATTERN.search(raw or "")
    return m.group(1) if m else None


def _to_float_or_none(value) -> Optional[float]:
    """
    Convert a value to float, returning None for suppressed/unreliable entries.

    CDC Wonder can return strings like 'Suppressed', 'Unreliable',
    'Not Applicable', or blank for privacy/statistical reasons.

    Args:
        value: Raw cell value from the CSV.

    Returns:
        Float, or None if the value is non-numeric.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int_or_none(value) -> Optional[int]:
    """Convert to int, returning None for suppressed/non-numeric values."""
    f = _to_float_or_none(value)
    return int(f) if f is not None else None


# ---------------------------------------------------------------------------
# Step 1: Download or detect CSV
# ---------------------------------------------------------------------------


def _detect_manual_csv() -> Optional[Path]:
    """
    Check if a manually-placed county-level CSV exists in data/mortality/.

    Returns:
        Path if found, None otherwise.
    """
    if MANUAL_CSV_PATH.exists() and MANUAL_CSV_PATH.stat().st_size > 1000:
        logger.info("Manual county-level CSV found at %s", MANUAL_CSV_PATH)
        return MANUAL_CSV_PATH
    return None


def download_csv(force: bool = False) -> Path:
    """
    Download the NCHS mortality CSV from data.cdc.gov with progress bar.

    Args:
        force: Re-download even if a cached copy exists.

    Returns:
        Path to the local CSV file.
    """
    if CSV_CACHE_PATH.exists() and not force:
        logger.info(
            "Using cached mortality CSV at %s (%.1f MB)",
            CSV_CACHE_PATH,
            CSV_CACHE_PATH.stat().st_size / 1e6,
        )
        return CSV_CACHE_PATH

    logger.info("Downloading NCHS Leading Causes of Death from %s ...", MORTALITY_URL)
    resp = requests.get(MORTALITY_URL, stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    CSV_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(CSV_CACHE_PATH, "wb") as fh, tqdm(
        desc="CDC Mortality",
        total=total,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            fh.write(chunk)
            bar.update(len(chunk))

    logger.info(
        "Saved to %s (%.1f MB)",
        CSV_CACHE_PATH,
        CSV_CACHE_PATH.stat().st_size / 1e6,
    )
    return CSV_CACHE_PATH


# ---------------------------------------------------------------------------
# Step 2: Parse and normalise
# ---------------------------------------------------------------------------


def _parse_nchs_state_level(csv_path: Path) -> pd.DataFrame:
    """
    Parse the NCHS Leading Causes CSV (state-level format).

    Expected columns: Year, 113 Cause Name, Cause Name, State, Deaths,
    Age-adjusted Death Rate

    Args:
        csv_path: Path to downloaded CSV.

    Returns:
        Normalised DataFrame matching the cdc_wonder_mortality schema.
    """
    logger.info("Parsing NCHS mortality CSV ...")
    df_raw = pd.read_csv(csv_path, dtype=str)
    logger.info("Raw columns: %s", list(df_raw.columns))
    logger.info("Raw rows: %d", len(df_raw))

    # Build normalised DataFrame matching our DB schema
    df = pd.DataFrame()

    # location — use State as the most granular field available
    df["county_name"] = df_raw["State"].str.strip()
    df["county_fips"] = None                          # not in this dataset
    df["state"] = df_raw["State"].str.strip()
    df["state_fips"] = None                           # not in this dataset

    # cause of death
    df["cause_of_death"] = df_raw["Cause Name"].str.strip()
    df["icd10_code"] = df_raw["113 Cause Name"].apply(_extract_icd10)

    # mortality counts & rates (handle suppressed/unreliable as NULL)
    df["deaths"] = df_raw["Deaths"].apply(_to_int_or_none)
    df["population"] = None                           # not in this dataset
    df["crude_rate"] = None                           # not in this dataset
    df["age_adjusted_rate"] = df_raw["Age-adjusted Death Rate"].apply(_to_float_or_none)

    # year
    df["year"] = df_raw["Year"].apply(_to_int_or_none)

    logger.info(
        "Parsed %d rows — %d distinct states/territories, %d distinct causes",
        len(df),
        df["state"].nunique(),
        df["cause_of_death"].nunique(),
    )
    return df


def _parse_manual_county_csv(csv_path: Path) -> pd.DataFrame:
    """
    Attempt to parse a manually-placed CDC Wonder county-level export.

    CDC Wonder county exports vary by query configuration; this parser
    handles the most common 'Delimited' export format from the
    Underlying Cause of Death (ICD-10) query.

    If parsing fails, logs an error and returns an empty DataFrame so
    the calling code can fall back to the state-level download.

    Args:
        csv_path: Path to the manually-placed CSV.

    Returns:
        Normalised DataFrame, or empty DataFrame on failure.
    """
    try:
        df_raw = pd.read_csv(csv_path, dtype=str, sep="\t", comment="#")
        logger.info("Manual CSV columns: %s", list(df_raw.columns))

        # CDC Wonder county exports typically have these column names:
        # County, County Code, State, State Code, Cause of death,
        # Cause of death Code, Deaths, Population, Crude Rate, Age Adjusted Rate, Year
        col_map = {
            "County": "county_name",
            "County Code": "county_fips",
            "State": "state",
            "State Code": "state_fips",
            "Cause of death": "cause_of_death",
            "Cause of death Code": "icd10_code",
            "Deaths": "deaths",
            "Population": "population",
            "Crude Rate": "crude_rate",
            "Age Adjusted Rate": "age_adjusted_rate",
            "Year": "year",
        }
        df_raw = df_raw.rename(columns=col_map)
        df = df_raw[[c for c in col_map.values() if c in df_raw.columns]].copy()

        for col in ("deaths", "population", "year"):
            if col in df.columns:
                df[col] = df[col].apply(_to_int_or_none)
        for col in ("crude_rate", "age_adjusted_rate"):
            if col in df.columns:
                df[col] = df[col].apply(_to_float_or_none)

        # Fill missing schema columns
        for col in ("county_fips", "state_fips", "population", "crude_rate"):
            if col not in df.columns:
                df[col] = None

        logger.info("Parsed manual county CSV: %d rows", len(df))
        return df

    except Exception as exc:
        logger.error("Failed to parse manual county CSV: %s", exc)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Step 3: Load into SQLite
# ---------------------------------------------------------------------------


def load_to_sqlite(df: pd.DataFrame, db_path: Path) -> int:
    """
    Write the normalised DataFrame to the cdc_wonder_mortality table.

    Drops and recreates the table on each run (idempotent).
    Creates indexes on the columns the tools filter most frequently.

    Args:
        df:      Normalised mortality DataFrame.
        db_path: Path to healthgpt.db.

    Returns:
        Number of rows written.
    """
    if df.empty:
        logger.warning("Empty DataFrame — nothing to write to SQLite.")
        return 0

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
        df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)

        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_mort_state "
            f"ON {TABLE_NAME}(state)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_mort_county "
            f"ON {TABLE_NAME}(county_name)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_mort_cause "
            f"ON {TABLE_NAME}(cause_of_death)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_mort_year "
            f"ON {TABLE_NAME}(year)"
        )
        conn.commit()
        logger.info(
            "Wrote %d rows to table '%s' in %s",
            len(df), TABLE_NAME, db_path,
        )
    finally:
        conn.close()

    return len(df)


# ---------------------------------------------------------------------------
# Step 4: Verification
# ---------------------------------------------------------------------------


def verify(db_path: Path) -> None:
    """
    Print verification output: Louisiana rows, distinct causes.

    Args:
        db_path: Path to healthgpt.db.
    """
    conn = sqlite3.connect(db_path)
    try:
        # Louisiana sample
        la_rows = conn.execute(
            f"""
            SELECT county_name, cause_of_death, deaths, age_adjusted_rate, year
            FROM {TABLE_NAME}
            WHERE state LIKE '%Louisiana%'
              AND year = (SELECT MAX(year) FROM {TABLE_NAME})
            ORDER BY age_adjusted_rate DESC NULLS LAST
            LIMIT 5
            """
        ).fetchall()

        print("\n--- Verification: Top 5 Louisiana causes of death (most recent year) ---")
        if la_rows:
            for row in la_rows:
                name, cause, deaths, rate, year = row
                rate_str = f"{rate:.1f}" if rate else "N/A"
                print(f"  {name} | {cause:<35} deaths={deaths} rate={rate_str} ({year})")
        else:
            print("  WARNING: No Louisiana rows found — check the download.")

        # Distinct causes
        causes = [
            r[0] for r in conn.execute(
                f"SELECT DISTINCT cause_of_death FROM {TABLE_NAME} "
                f"WHERE cause_of_death IS NOT NULL ORDER BY cause_of_death"
            ).fetchall()
        ]
        print(f"\n--- {len(causes)} distinct causes of death available ---")
        for c in causes[:20]:
            print(f"  • {c}")
        if len(causes) > 20:
            print(f"  ... and {len(causes) - 20} more")

        print("------------------------------------------------------------------------\n")

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(force_download: bool = False) -> None:
    """
    Full pipeline: detect/download CSV → parse → load → verify.

    Prefers a manually-placed county-level CSV in data/mortality/ if present;
    otherwise downloads the state-level NCHS dataset from data.cdc.gov.

    Args:
        force_download: Re-download from CDC even if cached locally.
    """
    print("\n=== CDC Mortality Data Ingestion ===\n")

    # Check for manually-placed county-level CSV first
    manual_path = _detect_manual_csv()
    if manual_path:
        print(f"  Using manual county-level CSV: {manual_path}")
        df = _parse_manual_county_csv(manual_path)
        if df.empty:
            print("  Manual CSV parsing failed — falling back to state-level download.")
            manual_path = None

    if not manual_path:
        print("  No county-level CSV found. Downloading state-level NCHS data...")
        print(MANUAL_DOWNLOAD_MSG)
        csv_path = download_csv(force=force_download)
        df = _parse_nchs_state_level(csv_path)

    row_count = load_to_sqlite(df, DB_PATH)
    print(f"\n  Done. {row_count:,} rows loaded into '{TABLE_NAME}'.")
    verify(DB_PATH)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download CDC mortality data into SQLite"
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download the CSV even if already cached",
    )
    args = parser.parse_args()
    run(force_download=args.force_download)
