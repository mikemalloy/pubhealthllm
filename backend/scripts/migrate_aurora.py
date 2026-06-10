"""
Curate and migrate health data from SQLite to Aurora Serverless v2.

Reads backend/data/healthgpt.db (cdc_places_county + cdc_wonder_mortality),
normalizes into 4 Aurora tables, and writes via the RDS Data API.

Idempotent: DROPs and re-creates all tables on each run.

Usage:
    cd backend && uv run python scripts/migrate_aurora.py

Environment (from .env or shell):
    AURORA_CLUSTER_ARN   — ARN of the Aurora cluster
    AURORA_SECRET_ARN    — ARN of the Secrets Manager secret
    AURORA_DATABASE      — database name (default: pubhealth)
    AWS_REGION           — default: us-west-1
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
DATABASE = os.environ.get("AURORA_DATABASE", "pubhealth")
REGION = os.environ.get("AWS_REGION", "us-west-1")
SQLITE_PATH = Path(__file__).parents[1] / "data" / "healthgpt.db"

_BATCH_SIZE = 500   # Data API: max 1000 parameterSets, keep 500 for safety

# ---------------------------------------------------------------------------
# State FIPS + abbreviation mapping (50 states + DC; "United States" → None)
# ---------------------------------------------------------------------------

_STATE_FIPS: dict[str, str | None] = {
    "Alabama": "01", "Alaska": "02", "Arizona": "04", "Arkansas": "05",
    "California": "06", "Colorado": "08", "Connecticut": "09", "Delaware": "10",
    "District of Columbia": "11", "Florida": "12", "Georgia": "13", "Hawaii": "15",
    "Idaho": "16", "Illinois": "17", "Indiana": "18", "Iowa": "19", "Kansas": "20",
    "Kentucky": "21", "Louisiana": "22", "Maine": "23", "Maryland": "24",
    "Massachusetts": "25", "Michigan": "26", "Minnesota": "27", "Mississippi": "28",
    "Missouri": "29", "Montana": "30", "Nebraska": "31", "Nevada": "32",
    "New Hampshire": "33", "New Jersey": "34", "New Mexico": "35", "New York": "36",
    "North Carolina": "37", "North Dakota": "38", "Ohio": "39", "Oklahoma": "40",
    "Oregon": "41", "Pennsylvania": "42", "Rhode Island": "44", "South Carolina": "45",
    "South Dakota": "46", "Tennessee": "47", "Texas": "48", "Utah": "49",
    "Vermont": "50", "Virginia": "51", "Washington": "53", "West Virginia": "54",
    "Wisconsin": "55", "Wyoming": "56",
    "United States": None,
}

_STATE_ABBR: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
}

# ---------------------------------------------------------------------------
# Data API helpers
# ---------------------------------------------------------------------------


def _client():
    return boto3.client("rds-data", region_name=REGION)


def _exec(client, sql: str, params: list | None = None) -> dict:
    kwargs: dict = dict(
        resourceArn=CLUSTER_ARN,
        secretArn=SECRET_ARN,
        database=DATABASE,
        sql=sql,
    )
    if params:
        kwargs["parameters"] = params
    return client.execute_statement(**kwargs)


def _batch(client, sql: str, param_sets: list[list]) -> None:
    """Run BatchExecuteStatement in chunks of _BATCH_SIZE."""
    for i in range(0, len(param_sets), _BATCH_SIZE):
        chunk = param_sets[i : i + _BATCH_SIZE]
        client.batch_execute_statement(
            resourceArn=CLUSTER_ARN,
            secretArn=SECRET_ARN,
            database=DATABASE,
            sql=sql,
            parameterSets=chunk,
        )
    log.info("  inserted %d rows", len(param_sets))


def _sv(v: str | None) -> dict:
    return {"stringValue": v} if v is not None else {"isNull": True}


def _dv(v: float | None) -> dict:
    return {"doubleValue": float(v)} if v is not None else {"isNull": True}


def _lv(v: int | None) -> dict:
    return {"longValue": int(v)} if v is not None else {"isNull": True}


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Each statement is separated by a sentinel comment so we can split correctly.
_SCHEMA_STATEMENTS = [
    "DROP TABLE IF EXISTS mortality_facts",
    "DROP TABLE IF EXISTS health_facts",
    "DROP TABLE IF EXISTS measures",
    "DROP TABLE IF EXISTS locations",
    """CREATE TABLE locations (
    fips           TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    state_abbr     TEXT,
    state_fips     TEXT,
    geo_level      TEXT NOT NULL
        CHECK (geo_level IN ('county', 'state', 'national'))
)""",
    """CREATE TABLE measures (
    measure_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    short_text TEXT,
    category   TEXT,
    unit       TEXT
)""",
    """CREATE TABLE health_facts (
    id             SERIAL PRIMARY KEY,
    location_fips  TEXT NOT NULL REFERENCES locations(fips),
    measure_id     TEXT NOT NULL REFERENCES measures(measure_id),
    year           INTEGER NOT NULL,
    value          REAL,
    value_type     TEXT NOT NULL,
    low_ci         REAL,
    high_ci        REAL,
    population     INTEGER,
    source         TEXT
)""",
    "CREATE INDEX idx_hf_loc_measure ON health_facts(location_fips, measure_id)",
    """CREATE TABLE mortality_facts (
    id                SERIAL PRIMARY KEY,
    state_fips        TEXT,
    county_fips       TEXT,
    cause             TEXT,
    icd10             TEXT,
    deaths            INTEGER,
    crude_rate        REAL,
    age_adjusted_rate REAL,
    year              INTEGER
)""",
]


def create_schema(client) -> None:
    """Drop + recreate all 4 tables."""
    log.info("Creating schema …")
    for stmt in _SCHEMA_STATEMENTS:
        _exec(client, stmt)
    log.info("Schema ready.")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_locations(client, sqlite: sqlite3.Connection) -> None:
    """
    Populate locations from three sources:
      1. County rows from cdc_places_county (5-digit LocationID).
      2. State rows derived from _STATE_FIPS mapping (50 states + DC).
      3. One national row (fips='00').
    """
    log.info("Loading locations …")
    params: list[list] = []

    # --- County rows ---
    sql = """
        SELECT DISTINCT LocationID, LocationName, StateAbbr
        FROM cdc_places_county
        WHERE LENGTH(LocationID) = 5
    """
    for loc_id, loc_name, state_abbr in sqlite.execute(sql):
        state_fips = loc_id[:2]
        canonical = f"{loc_name} County, {state_abbr}"
        params.append([
            {"name": "fips",           "value": _sv(loc_id)},
            {"name": "name",           "value": _sv(loc_name)},
            {"name": "canonical_name", "value": _sv(canonical)},
            {"name": "state_abbr",     "value": _sv(state_abbr)},
            {"name": "state_fips",     "value": _sv(state_fips)},
            {"name": "geo_level",      "value": _sv("county")},
        ])

    # --- State rows ---
    for state_name, state_fips in _STATE_FIPS.items():
        if state_name == "United States" or state_fips is None:
            continue
        abbr = _STATE_ABBR.get(state_name)
        params.append([
            {"name": "fips",           "value": _sv(state_fips)},
            {"name": "name",           "value": _sv(state_name)},
            {"name": "canonical_name", "value": _sv(state_name)},
            {"name": "state_abbr",     "value": _sv(abbr)},
            {"name": "state_fips",     "value": _sv(state_fips)},
            {"name": "geo_level",      "value": _sv("state")},
        ])

    # --- National row ---
    params.append([
        {"name": "fips",           "value": _sv("00")},
        {"name": "name",           "value": _sv("United States")},
        {"name": "canonical_name", "value": _sv("United States")},
        {"name": "state_abbr",     "value": {"isNull": True}},
        {"name": "state_fips",     "value": {"isNull": True}},
        {"name": "geo_level",      "value": _sv("national")},
    ])

    insert_sql = """
        INSERT INTO locations (fips, name, canonical_name, state_abbr, state_fips, geo_level)
        VALUES (:fips, :name, :canonical_name, :state_abbr, :state_fips, :geo_level)
        ON CONFLICT (fips) DO NOTHING
    """
    _batch(client, insert_sql, params)


def load_measures(client, sqlite: sqlite3.Connection) -> None:
    """Populate measures from the 40 distinct PLACES measures."""
    log.info("Loading measures …")
    sql = """
        SELECT DISTINCT MeasureId, Measure, Short_Question_Text, Category, Data_Value_Unit
        FROM cdc_places_county
        ORDER BY MeasureId
    """
    params = [
        [
            {"name": "measure_id", "value": _sv(mid)},
            {"name": "name",       "value": _sv(name)},
            {"name": "short_text", "value": _sv(short)},
            {"name": "category",   "value": _sv(cat)},
            {"name": "unit",       "value": _sv(unit)},
        ]
        for mid, name, short, cat, unit in sqlite.execute(sql)
    ]
    insert_sql = """
        INSERT INTO measures (measure_id, name, short_text, category, unit)
        VALUES (:measure_id, :name, :short_text, :category, :unit)
        ON CONFLICT (measure_id) DO NOTHING
    """
    _batch(client, insert_sql, params)


def load_health_facts(client, sqlite: sqlite3.Connection) -> None:
    """
    Load health_facts from cdc_places_county.

    - 5-digit LocationID rows → location_fips directly.
    - 2-char LocationID='59' (national) → location_fips='00'.
    - Skips rows where Data_Value is NULL.
    """
    log.info("Loading health_facts (this may take several minutes) …")
    sql = """
        SELECT
            CASE WHEN LENGTH(LocationID)=2 THEN '00' ELSE LocationID END,
            MeasureId,
            Year,
            Data_Value,
            DataValueTypeID,
            Low_Confidence_Limit,
            High_Confidence_Limit,
            TotalPopulation,
            DataSource
        FROM cdc_places_county
        WHERE Data_Value IS NOT NULL
    """
    params: list[list] = []
    for row in sqlite.execute(sql):
        loc_fips, mid, year, val, vtype, low, high, pop, source = row
        params.append([
            {"name": "location_fips", "value": _sv(loc_fips)},
            {"name": "measure_id",    "value": _sv(mid)},
            {"name": "year",          "value": _lv(year)},
            {"name": "value",         "value": _dv(val)},
            {"name": "value_type",    "value": _sv(vtype)},
            {"name": "low_ci",        "value": _dv(_safe_float(low))},
            {"name": "high_ci",       "value": _dv(_safe_float(high))},
            {"name": "population",    "value": _lv(int(pop) if pop else None)},
            {"name": "source",        "value": _sv(source)},
        ])
        if len(params) % 10_000 == 0:
            log.info("  … %d rows queued", len(params))

    insert_sql = """
        INSERT INTO health_facts
            (location_fips, measure_id, year, value, value_type,
             low_ci, high_ci, population, source)
        VALUES
            (:location_fips, :measure_id, :year, :value, :value_type,
             :low_ci, :high_ci, :population, :source)
    """
    _batch(client, insert_sql, params)


def load_mortality_facts(client, sqlite: sqlite3.Connection) -> None:
    """
    Load mortality_facts from cdc_wonder_mortality.

    Source is entirely state/national level — county_fips is always NULL.
    state_fips is derived from the state name via _STATE_FIPS mapping.
    'United States' rows get state_fips=NULL (national aggregate).
    crude_rate is stored as TEXT in SQLite (may be 'Not Applicable') — cast safely.
    """
    log.info("Loading mortality_facts …")
    sql = """
        SELECT state, cause_of_death, icd10_code, deaths, crude_rate,
               age_adjusted_rate, year
        FROM cdc_wonder_mortality
    """
    params: list[list] = []
    for state, cause, icd10, deaths, crude_rate, age_adj, year in sqlite.execute(sql):
        state_fips = _STATE_FIPS.get(state)
        params.append([
            {"name": "state_fips",        "value": _sv(state_fips)},
            {"name": "county_fips",       "value": {"isNull": True}},
            {"name": "cause",             "value": _sv(cause)},
            {"name": "icd10",             "value": _sv(icd10)},
            {"name": "deaths",            "value": _lv(deaths)},
            {"name": "crude_rate",        "value": _dv(_safe_float(crude_rate))},
            {"name": "age_adjusted_rate", "value": _dv(_safe_float(age_adj))},
            {"name": "year",              "value": _lv(year)},
        ])

    insert_sql = """
        INSERT INTO mortality_facts
            (state_fips, county_fips, cause, icd10, deaths, crude_rate, age_adjusted_rate, year)
        VALUES
            (:state_fips, :county_fips, :cause, :icd10, :deaths, :crude_rate, :age_adjusted_rate, :year)
    """
    _batch(client, insert_sql, params)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    client = _client()
    sqlite_conn = sqlite3.connect(SQLITE_PATH)

    create_schema(client)
    load_locations(client, sqlite_conn)
    load_measures(client, sqlite_conn)
    load_health_facts(client, sqlite_conn)
    load_mortality_facts(client, sqlite_conn)

    sqlite_conn.close()

    # Row counts
    log.info("─" * 50)
    for table in ("locations", "measures", "health_facts", "mortality_facts"):
        resp = _exec(client, f"SELECT COUNT(*) FROM {table}")
        count = resp["records"][0][0]["longValue"]
        log.info("  %-20s %d rows", table, count)
    log.info("Migration complete.")


if __name__ == "__main__":
    run()
