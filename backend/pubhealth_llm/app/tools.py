"""
PydanticAI Tool Definitions for pubHealthLLM.

Each function in this module is registered as a tool on the
PydanticAI agent.  The agent decides which tools to call based on
the user's question and the detailed docstrings.

Tools:
    search_mmwr_reports          — semantic search over MMWR vector DB
    get_health_statistics        — SQL query for a location + measure
    compare_locations            — comparative SQL across multiple locations
    get_available_measures       — list all queryable CDC PLACES measures
    get_worst_counties_by_measure — rank counties in a state worst-to-best
    rank_counties_composite      — z-score composite ranking across N measures

All tools return structured data; the agent synthesizes them into a
PublicHealthResponse.  Errors are caught and returned as informative
strings rather than raising exceptions, so a bad query never crashes
the demo.

Data source: CDC PLACES county-level dataset (swc5-untb), stored in
the cdc_places_county table of data/healthgpt.db.
LocationName contains readable county names (e.g. "Alameda County").
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parents[2] / "data" / "healthgpt.db"
CHROMA_DIR = Path(__file__).parents[2] / "data" / "chroma_db"
COLLECTION_NAME = "mmwr_reports"

# County-level table name (census-tract backup lives in cdc_places_tract)
TABLE_COUNTY = "cdc_places_county"

# Number of MMWR chunks to retrieve per search
MMWR_TOP_K = 5

# Maximum rows returned by a single SQL query (prevents huge responses)
SQL_MAX_ROWS = 20

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ChromaDB singleton (avoid re-loading embeddings on each tool call)
# ---------------------------------------------------------------------------

_chroma_collection = None


def _get_chroma_collection():
    """
    Return the ChromaDB MMWR collection, initializing it if needed.

    Uses a module-level singleton so the embedding model is loaded
    only once per process.

    Returns:
        chromadb.Collection, or None if the DB doesn't exist yet.
    """
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    if not CHROMA_DIR.exists():
        logger.warning("ChromaDB directory not found: %s", CHROMA_DIR)
        return None

    try:
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        _chroma_collection = client.get_collection(
            name=COLLECTION_NAME, embedding_function=ef
        )
        logger.info(
            "ChromaDB collection '%s' loaded (%d documents)",
            COLLECTION_NAME,
            _chroma_collection.count(),
        )
    except Exception as exc:
        logger.error("Failed to load ChromaDB collection: %s", exc)
        return None

    return _chroma_collection


# ---------------------------------------------------------------------------
# Public startup check — fail-fast vector store validation
# ---------------------------------------------------------------------------


def check_vector_store() -> None:
    """Verify the MMWR ChromaDB collection is loadable and non-empty.

    Called from the FastAPI lifespan handler so the server fails at boot
    rather than on the first tool call.

    Raises:
        RuntimeError: If the collection cannot be loaded (chromadb missing,
                      data/chroma_db absent, or collection not found), or if
                      the collection loaded but contains zero documents.
    """
    collection = _get_chroma_collection()
    if collection is None:
        raise RuntimeError(
            "MMWR vector store failed to load — check chromadb installation "
            "and data/chroma_db/"
        )
    if collection.count() == 0:
        raise RuntimeError(
            "MMWR vector store is empty — run ingestion before starting the server"
        )


# ---------------------------------------------------------------------------
# SQLite helper
# ---------------------------------------------------------------------------


def _query_db(sql: str, params: tuple = ()) -> list[dict]:
    """
    Execute a SQL query against the SQLite health database.

    Args:
        sql:    SQL query string with ? placeholders.
        params: Positional parameters for the query.

    Returns:
        List of row dicts.  Empty list if DB not found or query fails.
    """
    if not DB_PATH.exists():
        logger.warning("SQLite DB not found at %s", DB_PATH)
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql, params)
        rows = [dict(row) for row in cursor.fetchall()]
        return rows
    except sqlite3.Error as exc:
        logger.error("SQL error: %s | query: %s", exc, sql)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool: search_mmwr_reports
# ---------------------------------------------------------------------------


def search_mmwr_reports(query: str, top_k: int = MMWR_TOP_K) -> str:
    """
    Semantically search CDC MMWR weekly outbreak reports.

    USE THIS TOOL WHEN:
    - The question asks about historical outbreaks, epidemics, or disease events
    - The user wants context about how a disease has spread in the past
    - The question involves trends, seasonal patterns, or surveillance findings
    - The user asks for background on a public health emergency or response
    - The question requires qualitative context beyond bare statistics

    DO NOT USE THIS TOOL WHEN:
    - The user needs precise current statistics for a specific county or state
      (use get_health_statistics instead)
    - The user wants to compare prevalence numbers across locations
      (use compare_locations instead)

    COMBINING WITH OTHER TOOLS:
    - For a complete answer, combine with get_health_statistics to pair
      historical context with current local data.

    Args:
        query: Natural language query describing the information needed.
               Be specific — include disease names, geographic terms, or
               time periods when relevant.
        top_k: Number of report passages to retrieve (default 5).

    Returns:
        Formatted string with retrieved passages and their source files.
        Returns a descriptive error message if the vector DB is unavailable.
    """
    collection = _get_chroma_collection()
    if collection is None:
        return (
            "MMWR vector database is not available. "
            "Please run the data ingestion pipeline first: "
            "`python -m data_ingestion.run_ingestion`"
        )

    if collection.count() == 0:
        return "MMWR vector database is empty. Run ingestion to populate it."

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.error("ChromaDB query failed: %s", exc)
        return f"Vector search failed: {exc}"

    documents: list[str] = results["documents"][0]
    metadatas: list[dict] = results["metadatas"][0]
    distances: list[float] = results["distances"][0]

    if not documents:
        return f"No MMWR passages found for query: '{query}'"

    # Format results for the agent
    parts: list[str] = [f"MMWR Search Results for: '{query}'\n"]
    for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances), 1):
        relevance = max(0.0, 1.0 - dist)  # convert distance to similarity
        source = meta.get("source", "unknown")
        parts.append(
            f"[Result {i} | Source: {source} | Relevance: {relevance:.2f}]\n"
            f"{doc.strip()}\n"
        )

    return "\n---\n".join(parts)


# ---------------------------------------------------------------------------
# Tool: get_health_statistics
# ---------------------------------------------------------------------------


def get_health_statistics(
    location: str,
    measure: Optional[str] = None,
    state: Optional[str] = None,
) -> str:
    """
    Query CDC PLACES county-level health statistics for a location.

    USE THIS TOOL WHEN:
    - The user asks for specific health statistics in a city, county, or state
    - The question involves current prevalence rates (diabetes, obesity,
      smoking, hypertension, mental health, physical inactivity, etc.)
    - The user needs numbers to support a public health assessment

    DO NOT USE THIS TOOL WHEN:
    - The user wants historical outbreak narrative (use search_mmwr_reports)
    - The user wants side-by-side comparison of multiple locations
      (use compare_locations — it's cleaner for that use case)

    LOCATION FORMAT TIPS:
    - Use county name only: "King County", "Los Angeles", "Cook"
    - Use city or place name: "Seattle", "Chicago", "Houston"
    - Use state name for state-level: "Washington", "California", "Texas"
    - Partial matches work — "Los Angeles" matches "Los Angeles County"

    MEASURE TIPS:
    - Leave measure=None to get all available measures for the location
    - Use get_available_measures() to see all valid measure names
    - Partial measure name works: "diabetes", "obesity", "smoking"

    Args:
        location: City, county, or state name to query.
        measure:  Optional health measure name or partial name filter.
        state:    Optional two-letter state abbreviation to narrow results
                  when the location name is ambiguous (e.g. "TX").

    Returns:
        Formatted table of health statistics, or an error message.
    """
    if not DB_PATH.exists():
        return (
            "Health statistics database not found. "
            "Run: `python -m pubhealth_llm.data_ingestion.download_county_data`"
        )

    # LocationName in cdc_places_county contains readable county names
    # (e.g. "Alameda County"), so we search it directly.
    # StateDesc and StateAbbr are also searched so state-level queries work.
    conditions = ["(LocationName LIKE ? OR StateDesc LIKE ? OR StateAbbr LIKE ?)"]
    params: list = [f"%{location}%", f"%{location}%", f"%{location}%"]

    if state:
        conditions.append("StateAbbr = ?")
        params.append(state.upper())

    if measure:
        # Short_Question_Text has the most readable measure names (e.g.
        # "Diabetes" vs the longer Measure column).  We also match Measure
        # and MeasureId for completeness.
        conditions.append(
            "(Short_Question_Text LIKE ? OR Measure LIKE ? OR MeasureId LIKE ?)"
        )
        params.extend([f"%{measure}%", f"%{measure}%", f"%{measure}%"])

    where_clause = " AND ".join(conditions)
    sql = f"""
        SELECT
            LocationName,
            StateAbbr,
            Measure,
            Short_Question_Text,
            Data_Value,
            Data_Value_Unit,
            Data_Value_Type,
            Year,
            Low_Confidence_Limit,
            High_Confidence_Limit,
            TotalPopulation
        FROM {TABLE_COUNTY}
        WHERE {where_clause}
          AND Data_Value IS NOT NULL
        ORDER BY Year DESC, Measure
        LIMIT {SQL_MAX_ROWS}
    """

    rows = _query_db(sql, tuple(params))

    if not rows:
        return (
            f"No health statistics found for location='{location}'"
            + (f", measure='{measure}'" if measure else "")
            + (f", state='{state}'" if state else "")
            + ". Try a broader search term or check get_available_measures()."
        )

    # Format output
    lines = [
        f"CDC PLACES Health Statistics — {location}"
        + (f" ({state})" if state else ""),
        f"Showing {len(rows)} result(s):\n",
    ]
    for row in rows:
        ci_str = ""
        if row.get("Low_Confidence_Limit") and row.get("High_Confidence_Limit"):
            ci_str = f" (95% CI: {row['Low_Confidence_Limit']}–{row['High_Confidence_Limit']})"
        pop_str = ""
        if row.get("TotalPopulation"):
            pop_str = f" | Pop: {int(row['TotalPopulation']):,}"
        lines.append(
            f"  • {row['Measure']}"
            f"\n    Value: {row['Data_Value']} {row['Data_Value_Unit']}"
            f"{ci_str}"
            f"\n    Type: {row['Data_Value_Type']}"
            f" | Year: {row.get('Year', 'N/A')}"
            f"{pop_str}"
            f"\n    Location: {row['LocationName']}, {row['StateAbbr']}\n"
        )

    lines.append("Source: CDC PLACES 2023, https://www.cdc.gov/places")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: compare_locations
# ---------------------------------------------------------------------------


def compare_locations(locations: list[str], measure: str) -> str:
    """
    Compare a specific health measure across multiple locations.

    USE THIS TOOL WHEN:
    - The user explicitly asks to compare cities, counties, or states
    - The question asks "which area has higher/lower X"
    - The user wants a ranked table of health outcomes
    - You need to provide geographic context for an outlier location

    DO NOT USE THIS TOOL WITH:
    - A single location (use get_health_statistics instead)
    - Vague measure names — be specific so the SQL filter returns results

    USAGE EXAMPLE:
        compare_locations(
            locations=["Travis County", "Harris County", "Bexar County"],
            measure="diabetes"
        )

    Args:
        locations: List of location names (cities, counties, or states).
                   Each is searched with LIKE so partial names work.
        measure:   Health measure name or keyword (e.g. "obesity",
                   "Current smoking", "Physical inactivity").

    Returns:
        Ranked comparison table as formatted text, or an error message.
    """
    if not DB_PATH.exists():
        return "Health statistics database not found. Run ingestion first."

    if not locations:
        return "No locations provided. Pass a list of at least 2 location names."

    if len(locations) > 10:
        locations = locations[:10]
        logger.warning("compare_locations truncated to 10 locations")

    location_conditions = " OR ".join(
        ["LocationName LIKE ? OR StateDesc LIKE ? OR StateAbbr LIKE ?"] * len(locations)
    )
    location_params: list[str] = []
    for loc in locations:
        location_params.extend([f"%{loc}%", f"%{loc}%", f"%{loc}%"])

    sql = f"""
        SELECT
            LocationName,
            StateAbbr,
            Measure,
            Data_Value,
            Data_Value_Unit,
            Data_Value_Type,
            Year
        FROM {TABLE_COUNTY}
        WHERE ({location_conditions})
          AND (Short_Question_Text LIKE ? OR Measure LIKE ? OR MeasureId LIKE ?)
          AND Data_Value IS NOT NULL
        ORDER BY Data_Value DESC
        LIMIT {SQL_MAX_ROWS}
    """
    params = location_params + [f"%{measure}%", f"%{measure}%", f"%{measure}%"]

    rows = _query_db(sql, tuple(params))

    if not rows:
        return (
            f"No comparison data found for measure='{measure}' "
            f"across locations: {', '.join(locations)}. "
            "Try get_available_measures() to see valid measure names."
        )

    # Deduplicate to one row per location (most recent year)
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        key = row["LocationName"] + row["StateAbbr"]
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    lines = [
        f"Comparison: '{deduped[0]['Measure']}' across {len(deduped)} location(s)\n",
        f"{'Rank':<5} {'Location':<30} {'State':<6} {'Value':<12} {'Unit':<20} {'Year':<6}",
        "-" * 80,
    ]
    for rank, row in enumerate(deduped, 1):
        lines.append(
            f"{rank:<5} {row['LocationName']:<30} {row['StateAbbr']:<6} "
            f"{row['Data_Value']:<12} {row['Data_Value_Unit']:<20} "
            f"{row.get('Year', 'N/A'):<6}"
        )

    lines.append("\nSource: CDC PLACES 2023, https://www.cdc.gov/places")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: get_available_measures
# ---------------------------------------------------------------------------


def get_available_measures(category: Optional[str] = None) -> str:
    """
    Return all health measures available in the CDC PLACES database.

    USE THIS TOOL WHEN:
    - You are uncertain whether a measure name is valid before querying
    - The user asks "what health data do you have?" or "what can you look up?"
    - You need the exact MeasureId to construct a precise SQL query
    - The user's question mentions a condition and you want to confirm
      it exists in the database before calling get_health_statistics

    Args:
        category: Optional category filter (e.g., "Chronic Disease",
                  "Health Outcomes", "Prevention", "Health Risk Behaviors").
                  Pass None to return all measures.

    Returns:
        Formatted list of available measures grouped by category.
    """
    if not DB_PATH.exists():
        return "Health statistics database not found. Run ingestion first."

    if category:
        sql = f"""
            SELECT DISTINCT MeasureId, Measure, Short_Question_Text,
                            Category, Data_Value_Unit
            FROM {TABLE_COUNTY}
            WHERE Category LIKE ?
              AND MeasureId IS NOT NULL
            ORDER BY Category, Measure
        """
        rows = _query_db(sql, (f"%{category}%",))
    else:
        sql = f"""
            SELECT DISTINCT MeasureId, Measure, Short_Question_Text,
                            Category, Data_Value_Unit
            FROM {TABLE_COUNTY}
            WHERE MeasureId IS NOT NULL
            ORDER BY Category, Measure
        """
        rows = _query_db(sql)

    if not rows:
        return (
            "No measures found"
            + (f" for category '{category}'" if category else "")
            + ". The database may need to be rebuilt."
        )

    # Group by category
    from collections import defaultdict
    by_category: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_category[row["Category"]].append(row)

    lines = [
        f"Available CDC PLACES Health Measures ({len(rows)} total):\n"
    ]
    for cat, measures in sorted(by_category.items()):
        lines.append(f"## {cat}")
        for m in measures:
            unit = m.get("Data_Value_Unit", "")
            lines.append(
                f"  • [{m['MeasureId']}] {m['Short_Question_Text']} "
                f"({unit})"
            )
        lines.append("")

    return "\n".join(lines)


def list_available_measures(category: str | None = None) -> list[dict]:
    """
    Return structured measure data for UI autocomplete / API consumers.

    Unlike get_available_measures(), this function returns raw dicts instead
    of a formatted string. It is the data source for the GET /measures endpoint.

    Args:
        category: Optional filter string (case-insensitive, partial match).
                  Pass None to return all measures.

    Returns:
        List of dicts with keys: measure_id, measure, short_text, category.
        Returns an empty list if the DB is absent or no rows match.
    """
    if not DB_PATH.exists():
        return []

    if category:
        sql = f"""
            SELECT DISTINCT MeasureId, Measure, Short_Question_Text, Category
            FROM {TABLE_COUNTY}
            WHERE Category LIKE ?
              AND MeasureId IS NOT NULL
            ORDER BY Category, Measure
        """
        rows = _query_db(sql, (f"%{category}%",))
    else:
        sql = f"""
            SELECT DISTINCT MeasureId, Measure, Short_Question_Text, Category
            FROM {TABLE_COUNTY}
            WHERE MeasureId IS NOT NULL
            ORDER BY Category, Measure
        """
        rows = _query_db(sql)

    return [
        {
            "measure_id": row["MeasureId"],
            "measure": row["Measure"],
            "short_text": row["Short_Question_Text"],
            "category": row["Category"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Tool: get_worst_counties_by_measure
# ---------------------------------------------------------------------------


def get_worst_counties_by_measure(
    state: str,
    measure: str,
    top_n: int = 10,
) -> str:
    """
    Rank counties in a state from worst to best for a given health measure.

    USE THIS TOOL WHEN:
    - The user asks which counties have the highest burden of a disease
    - The question uses words like "worst", "highest", "most affected",
      "top 10", or "greatest burden"
    - The user wants to identify priority areas for intervention in a state
    - The question is about within-state geographic disparities

    DO NOT USE THIS TOOL WHEN:
    - The user wants data for a specific named county (use get_health_statistics)
    - The user wants to compare specific counties across states
      (use compare_locations)
    - No state is specified — this tool requires a state to avoid returning
      thousands of rows

    INTERPRETING RESULTS:
    - For disease prevalence measures (diabetes, obesity, hypertension, smoking),
      higher values = worse outcomes, so results are ranked highest-first.
    - For protective measures (cholesterol screening, dental visits), higher
      values are better — the ranking will still show highest-first, so
      interpret accordingly and note this in your response.

    Args:
        state:   Two-letter state abbreviation (e.g. "TX", "CA", "OH").
                 Required — do not pass a full state name here.
        measure: Plain-text health measure keyword (e.g. "diabetes",
                 "obesity", "smoking", "depression", "hypertension").
                 Matched against Short_Question_Text with LIKE.
        top_n:   Number of counties to return, ranked worst-to-best
                 (default 10, max 50).

    Returns:
        Formatted ranked table of counties with prevalence values,
        confidence intervals, and population. Returns an error string
        if no data is found.
    """
    if not DB_PATH.exists():
        return (
            "Health statistics database not found. "
            "Run: `python -m pubhealth_llm.data_ingestion.download_county_data`"
        )

    if not state or len(state.strip()) != 2:
        return (
            "A two-letter state abbreviation is required (e.g. 'TX'). "
            "For multi-state queries, call this tool once per state."
        )

    top_n = min(max(1, top_n), 50)  # clamp to [1, 50]

    sql = f"""
        SELECT
            LocationName,
            StateAbbr,
            Short_Question_Text,
            Measure,
            Data_Value,
            Data_Value_Unit,
            Low_Confidence_Limit,
            High_Confidence_Limit,
            TotalPopulation,
            Year
        FROM {TABLE_COUNTY}
        WHERE StateAbbr = ?
          AND (Short_Question_Text LIKE ? OR Measure LIKE ?)
          AND Data_Value IS NOT NULL
        ORDER BY Data_Value DESC
        LIMIT ?
    """
    params = (
        state.upper().strip(),
        f"%{measure}%",
        f"%{measure}%",
        top_n,
    )

    rows = _query_db(sql, params)

    if not rows:
        return (
            f"No data found for measure='{measure}' in state='{state.upper()}'. "
            "Try get_available_measures() to see valid measure keywords."
        )

    measure_label = rows[0].get("Short_Question_Text") or rows[0].get("Measure", measure)
    unit = rows[0].get("Data_Value_Unit", "%")
    state_upper = state.upper().strip()

    lines = [
        f"Worst Counties by '{measure_label}' in {state_upper} "
        f"(ranked highest-to-lowest, n={len(rows)})\n",
        f"{'Rank':<5} {'County':<35} {'Value':>10} {'95% CI':>18} "
        f"{'Population':>14} {'Year':<6}",
        "-" * 88,
    ]

    for rank, row in enumerate(rows, 1):
        county = row.get("LocationName", "Unknown")
        value = row.get("Data_Value", "N/A")
        lo = row.get("Low_Confidence_Limit")
        hi = row.get("High_Confidence_Limit")
        pop = row.get("TotalPopulation")
        year = row.get("Year", "N/A")

        ci_str = f"({lo}–{hi})" if lo and hi else "N/A"
        pop_str = f"{int(pop):,}" if pop else "N/A"
        value_str = f"{value} {unit}" if value != "N/A" else "N/A"

        lines.append(
            f"{rank:<5} {county:<35} {value_str:>10} "
            f"{ci_str:>18} {pop_str:>14} {str(year):<6}"
        )

    lines.append("\nSource: CDC PLACES 2023, https://www.cdc.gov/places")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: rank_counties_composite
# ---------------------------------------------------------------------------


def rank_counties_composite(
    state: str,
    measures: list[str],
    target_location: Optional[str] = None,
    top_n: int = 10,
) -> str:
    """
    Rank counties in a state by their COMBINED burden across multiple health
    measures using z-score normalization and a composite score.

    USE THIS TOOL WHEN:
    - The user asks which counties to PRIORITIZE for a program targeting
      multiple health conditions simultaneously (e.g. diabetes + obesity +
      physical inactivity combined)
    - The question involves words like "combined burden", "co-occurring",
      "cascade", "integrated", "prioritize across", or "rank on multiple"
    - The user wants to know which counties rank worst on SEVERAL measures at once
    - The question asks for a composite or overall score across conditions

    DO NOT USE THIS TOOL WHEN:
    - Only one measure is needed — use get_worst_counties_by_measure instead
    - The user wants data for a specific named county — use get_health_statistics
    - The question is about outbreak history — use search_mmwr_reports

    HOW THE COMPOSITE SCORE WORKS:
    - For each measure, every county receives a z-score:
        z = (county value − state mean) / state standard deviation
    - A county with z = +1.5 for diabetes is 1.5 standard deviations above
      the state mean — a significant burden
    - The composite score is the sum of z-scores across all measures
    - Higher composite = greater combined burden across all measures
    - Only counties with data for ALL requested measures are included

    Args:
        state:           Two-letter state abbreviation (e.g. "TX", "LA").
        measures:        List of 2–5 health measure keywords (e.g.
                         ["diabetes", "obesity", "physical inactivity"]).
                         Uses the same LIKE matching as other tools.
        target_location: Optional county name to highlight in the output
                         (e.g. "Travis County"). Shows its rank even if
                         outside the top_n.
        top_n:           Number of highest-burden counties to display
                         (default 10, max 50).

    Returns:
        Ranked table with per-measure values and composite score,
        plus the target county's position if specified. Returns a
        descriptive error string if inputs are invalid or data is missing.
    """
    import statistics as _stats

    if not DB_PATH.exists():
        return (
            "Health statistics database not found. "
            "Run: `python -m pubhealth_llm.data_ingestion.download_county_data`"
        )

    if not state or len(state.strip()) != 2:
        return "A two-letter state abbreviation is required (e.g. 'TX')."

    if not measures or len(measures) < 2:
        return (
            "At least 2 measures are required for composite ranking. "
            "For a single measure use get_worst_counties_by_measure."
        )

    if len(measures) > 5:
        measures = measures[:5]
        logger.warning("rank_counties_composite truncated to 5 measures")

    top_n = min(max(1, top_n), 50)
    state_upper = state.upper().strip()

    # ------------------------------------------------------------------
    # Fetch all-county data per measure (most recent year, no LIMIT)
    # ------------------------------------------------------------------
    # measure_rows[kw] = {county_name: row_dict}
    measure_rows: dict[str, dict[str, dict]] = {}
    resolved: list[tuple[str, str, str, int]] = []  # (kw, label, unit, year)
    missing: list[str] = []

    for kw in measures:
        sql = f"""
            SELECT LocationName, Data_Value, Short_Question_Text,
                   Data_Value_Unit, Year, Data_Value_Type
            FROM {TABLE_COUNTY}
            WHERE StateAbbr = ?
              AND (Short_Question_Text LIKE ? OR Measure LIKE ?)
              AND Data_Value IS NOT NULL
              AND Year = (
                  SELECT MAX(Year) FROM {TABLE_COUNTY}
                  WHERE StateAbbr = ?
                    AND (Short_Question_Text LIKE ? OR Measure LIKE ?)
                    AND Data_Value IS NOT NULL
              )
            ORDER BY LocationName, Data_Value_Type
        """
        params = (
            state_upper, f"%{kw}%", f"%{kw}%",
            state_upper, f"%{kw}%", f"%{kw}%",
        )
        rows = _query_db(sql, params)

        if not rows:
            missing.append(kw)
            continue

        # Deduplicate: one row per county (first Data_Value_Type alphabetically
        # so "Age-adjusted" is consistently preferred over "Crude" prevalence)
        county_vals: dict[str, dict] = {}
        for row in rows:
            if row["LocationName"] not in county_vals:
                county_vals[row["LocationName"]] = row

        first = next(iter(county_vals.values()))
        label = first.get("Short_Question_Text") or kw
        unit = first.get("Data_Value_Unit", "%")
        year = first.get("Year", "N/A")

        measure_rows[kw] = county_vals
        resolved.append((kw, label, unit, year))

    if len(resolved) < 2:
        return (
            f"Only {len(resolved)} of {len(measures)} requested measures "
            f"found in {state_upper} "
            f"({', '.join(r[1] for r in resolved) or 'none found'}). "
            f"Not found: {', '.join(missing)}. "
            "Need at least 2 resolved measures to compute a composite. "
            "Use get_available_measures() to verify exact measure names."
        )

    # ------------------------------------------------------------------
    # County universe: intersection across all resolved measures
    # ------------------------------------------------------------------
    universe: set[str] = set(measure_rows[resolved[0][0]].keys())
    for kw, _, _, _ in resolved[1:]:
        universe &= set(measure_rows[kw].keys())

    if len(universe) < 2:
        return (
            f"Only {len(universe)} county/counties have data for all "
            f"{len(resolved)} measures in {state_upper}. "
            "Cannot compute meaningful z-scores with fewer than 2 data points."
        )

    county_list = sorted(universe)

    # ------------------------------------------------------------------
    # Z-scores and composite score
    # ------------------------------------------------------------------
    z: dict[str, dict[str, float]] = {}
    for kw, _, _, _ in resolved:
        values = [measure_rows[kw][c]["Data_Value"] for c in county_list]
        mean = _stats.mean(values)
        pstd = _stats.pstdev(values)
        if pstd == 0:
            z[kw] = {c: 0.0 for c in county_list}
        else:
            z[kw] = {
                c: (measure_rows[kw][c]["Data_Value"] - mean) / pstd
                for c in county_list
            }

    composite = {
        c: sum(z[kw][c] for kw, _, _, _ in resolved)
        for c in county_list
    }
    ranked = sorted(county_list, key=lambda c: composite[c], reverse=True)
    county_rank = {c: i + 1 for i, c in enumerate(ranked)}

    # ------------------------------------------------------------------
    # Format output
    # ------------------------------------------------------------------
    col_w = 10

    lines = [
        f"Composite County Ranking — {state_upper}",
        f"County universe: {len(universe)} counties with complete data for all measures",
        f"Measures ({len(resolved)}):",
    ]
    for kw, label, unit, year in resolved:
        lines.append(f"  • {label} ({unit}, {year})")
    if missing:
        lines.append(f"  ✗ Not found in database: {', '.join(missing)}")
    lines.append("")

    # Table header (truncate measure labels to col_w chars)
    header = f"{'Rank':<5} {'County':<33}"
    for _, label, _, _ in resolved:
        header += f" {label[:col_w]:>{col_w}}"
    header += f" {'Composite':>{col_w}}"
    lines += [header, "-" * len(header)]

    # Find target county (case-insensitive, bidirectional partial match).
    # Handles cases where the user passes "Webb County" but the DB stores "Webb",
    # or vice versa.  We strip common geographic suffixes before comparing.
    target_name: Optional[str] = None
    if target_location:
        t_lower = target_location.lower()
        t_stripped = (
            t_lower
            .replace(" county", "")
            .replace(" parish", "")
            .replace(" borough", "")
            .strip()
        )
        for c in ranked:
            c_lower = c.lower()
            if t_lower in c_lower or c_lower in t_lower or t_stripped in c_lower:
                target_name = c
                break

    top_counties = ranked[:top_n]

    for c in top_counties:
        row_str = f"{county_rank[c]:<5} {c:<33}"
        for kw, _, _, _ in resolved:
            row_str += f" {measure_rows[kw][c]['Data_Value']:>{col_w}.1f}"
        row_str += f" {composite[c]:>{col_w}.2f}"
        if c == target_name:
            row_str += "  ← target"
        lines.append(row_str)

    # Show target if it falls outside top_n
    if target_name and target_name not in top_counties:
        lines.append("  ...")
        c = target_name
        row_str = f"{county_rank[c]:<5} {c:<33}"
        for kw, _, _, _ in resolved:
            row_str += f" {measure_rows[kw][c]['Data_Value']:>{col_w}.1f}"
        row_str += f" {composite[c]:>{col_w}.2f}  ← target"
        lines.append(row_str)
    elif target_location and not target_name:
        lines.append(
            f"\nNOTE: '{target_location}' not found among counties with "
            f"complete data for all measures in {state_upper}."
        )

    lines.append(
        "\nComposite = sum of z-scores across all measures "
        "(higher = greater combined burden)."
    )
    lines.append("z-score = (county value − state mean) / state std dev.")
    lines.append("Source: CDC PLACES 2023, https://www.cdc.gov/places")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mortality DB constant (shared by mortality tools)
# ---------------------------------------------------------------------------

TABLE_MORTALITY = "cdc_wonder_mortality"

_MORTALITY_NO_DATA_MSG = (
    "Mortality data is not available. "
    "Run: `python -m pubhealth_llm.data_ingestion.download_mortality` to load "
    "CDC Leading Causes of Death data. "
    "NOTE: The available dataset is state-level (1999–2017). For county/parish-level "
    "mortality data, see the manual download instructions in download_mortality.py."
)


def _mortality_table_exists() -> bool:
    """Return True if the cdc_wonder_mortality table exists and has rows."""
    if not DB_PATH.exists():
        return False
    conn = sqlite3.connect(DB_PATH)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name=?",
            (TABLE_MORTALITY,),
        ).fetchone()[0]
        if count == 0:
            return False
        rows = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE_MORTALITY}"
        ).fetchone()[0]
        return rows > 0
    except sqlite3.Error:
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool: get_mortality_data
# ---------------------------------------------------------------------------


def get_mortality_data(
    location: str,
    cause: Optional[str] = None,
    year: Optional[int] = None,
) -> str:
    """
    Retrieve CDC mortality statistics for a location and optional cause.

    USE THIS TOOL WHEN:
    - The question involves death rates, leading causes of death, or
      mortality comparisons at the state or national level
    - The user needs to quantify the ultimate health impact: deaths,
      age-adjusted mortality rates, or years of life lost
    - The question asks "how many people die from X in Y" or
      "what are the leading killers in Z"
    - You need the most compelling data point for a budget argument —
      mortality rates are more persuasive than prevalence rates

    DO NOT USE THIS TOOL WHEN:
    - The user wants prevalence rates, screening rates, or health behaviors
      (use get_health_statistics for those — it has county-level detail)
    - The user wants to compare specific named counties on a health measure
      (use compare_locations or rank_counties_composite)

    GEOGRAPHIC NOTE:
    - The available CDC mortality dataset is STATE-LEVEL (1999–2017).
    - Queries for a parish/county name (e.g. "East Baton Rouge") will
      automatically fall back to state-level data for that state with a note.
    - Pass state name or abbreviation for direct state queries: "Louisiana", "LA"
    - Pass "United States" for national-level data

    Args:
        location: State name (e.g. "Louisiana"), abbreviation (e.g. "LA"),
                  or parish/county name (falls back to state level).
        cause:    Plain-text cause keyword (e.g. "diabetes", "heart disease",
                  "cancer", "stroke", "all causes"). None returns top 10 causes.
        year:     Specific year (1999–2017). None returns most recent available.

    Returns:
        Formatted mortality table as a string, or a descriptive error message.
    """
    if not _mortality_table_exists():
        return _MORTALITY_NO_DATA_MSG

    # --- Resolve location to what's in the DB ---
    # The DB stores state names in county_name and state columns.
    # We try increasingly broad matches so that e.g. "LA" finds "Louisiana"
    # and "East Baton Rouge" falls back to "Louisiana".

    STATE_ABBR_MAP = {
        "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
        "CA": "California", "CO": "Colorado", "CT": "Connecticut",
        "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
        "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
        "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
        "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
        "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
        "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
        "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
        "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
        "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
        "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
        "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
        "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
        "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    }

    location_note = ""
    resolved_location = location.strip()

    # If two-letter abbreviation, expand to full state name
    abbr_upper = resolved_location.upper()
    if abbr_upper in STATE_ABBR_MAP:
        resolved_location = STATE_ABBR_MAP[abbr_upper]

    # Build SQL — try exact/partial match on county_name (= state name in our data)
    year_sql = ""
    year_params: list = []
    if year:
        year_sql = "AND year = ?"
        year_params = [year]
    else:
        year_sql = "AND year = (SELECT MAX(year) FROM " + TABLE_MORTALITY + ")"

    cause_sql = ""
    cause_params: list = []
    if cause:
        cause_sql = "AND (cause_of_death LIKE ? OR icd10_code LIKE ?)"
        cause_params = [f"%{cause}%", f"%{cause}%"]

    limit_sql = "LIMIT 10" if not cause else "LIMIT 20"

    sql = f"""
        SELECT county_name, cause_of_death, icd10_code,
               deaths, crude_rate, age_adjusted_rate, year
        FROM {TABLE_MORTALITY}
        WHERE county_name LIKE ?
          {year_sql}
          {cause_sql}
        ORDER BY age_adjusted_rate DESC NULLS LAST, deaths DESC NULLS LAST
        {limit_sql}
    """
    params = [f"%{resolved_location}%"] + year_params + cause_params
    rows = _query_db(sql, tuple(params))

    # Fallback: if no rows found and input looks like a county/parish,
    # try to infer state from context (not feasible without a full FIPS map)
    # — just report clearly that only state-level data exists
    if not rows:
        location_note = (
            f"\nNOTE: No mortality data found for '{location}'. "
            "This dataset is state-level only (1999–2017). "
            "Try the full state name (e.g. 'Louisiana') or 'United States'."
        )
        # Try United States as a last resort if no location match at all
        if not cause:
            return (
                f"No mortality data found for location='{location}'.\n"
                "Available locations are U.S. state names and 'United States'.\n"
                "Example: get_mortality_data('Louisiana') or get_mortality_data('Texas', cause='diabetes')"
            )
        return (
            f"No mortality data found for location='{location}', cause='{cause}'.\n"
            "This dataset covers U.S. state-level data. Try a state name like 'Louisiana'.\n"
            + location_note
        )

    # Check if location was resolved from something sub-state (e.g. parish name)
    first_location = rows[0].get("county_name", resolved_location)
    if first_location.lower() != resolved_location.lower():
        location_note = (
            f"\nNOTE: '{location}' resolved to state-level data for '{first_location}'. "
            "Parish/county-level mortality data requires manual download from "
            "https://wonder.cdc.gov/ucd-icd10.html"
        )

    cause_label = cause if cause else "all causes (top 10 by age-adjusted rate)"
    title_location = first_location
    year_val = rows[0].get("year", "N/A")

    lines = [
        f"CDC Mortality Data — {title_location} | {cause_label} | Year: {year_val}",
        f"{'Cause of Death':<40} {'Deaths':>8} {'Crude Rate':>12} {'Age-Adj Rate':>14}",
        "-" * 78,
    ]

    for row in rows:
        cod = (row.get("cause_of_death") or "Unknown")[:38]
        deaths = row.get("deaths")
        crude = row.get("crude_rate")
        aadj = row.get("age_adjusted_rate")

        deaths_str = f"{int(deaths):,}" if deaths is not None else "Suppressed"
        crude_str = f"{crude:.1f}" if crude is not None else "N/A"
        aadj_str = f"{aadj:.1f}" if aadj is not None else "N/A"

        lines.append(
            f"{cod:<40} {deaths_str:>8} {crude_str:>12} {aadj_str:>14}"
        )

    if location_note:
        lines.append(location_note)

    lines.append(
        "\nRates per 100,000 population. Age-adjusted to 2000 U.S. standard."
    )
    lines.append(
        "Source: NCHS Leading Causes of Death: United States, "
        "https://data.cdc.gov/resource/bi63-dtpu"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: compare_mortality
# ---------------------------------------------------------------------------


def compare_mortality(locations: list[str], cause: str) -> str:
    """
    Compare mortality rates for a specific cause across multiple locations.

    USE THIS TOOL WHEN:
    - The user wants to compare death rates between states or jurisdictions
    - The question asks which areas have the highest mortality for a cause
    - You need to rank locations by mortality burden for policy arguments
    - You want to contrast a target area's death rate against peers or
      national average

    DO NOT USE THIS TOOL FOR:
    - Prevalence comparisons (use compare_locations)
    - Single-location queries (use get_mortality_data)

    GEOGRAPHIC NOTE:
    - Data is available at the STATE level (1999–2017).
    - Pass state names (e.g. ["Louisiana", "Mississippi", "Alabama"]) or
      include "United States" for the national benchmark.

    Args:
        locations: List of state names or "United States" for national benchmark.
                   Parish/county names will fall back to state-level lookup.
        cause:     Plain-text cause keyword (e.g. "diabetes", "heart disease",
                   "cancer", "stroke", "suicide", "drug overdose").

    Returns:
        Ranked comparison table sorted by age-adjusted rate descending,
        or a descriptive error message.
    """
    if not _mortality_table_exists():
        return _MORTALITY_NO_DATA_MSG

    if not locations:
        return "No locations provided. Pass a list of state names to compare."

    if not cause:
        return "A cause of death is required for comparison. E.g. 'heart disease'."

    if len(locations) > 15:
        locations = locations[:15]
        logger.warning("compare_mortality truncated to 15 locations")

    # Build OR conditions for all locations
    loc_conditions = " OR ".join(["county_name LIKE ?"] * len(locations))
    loc_params = [f"%{loc}%" for loc in locations]

    sql = f"""
        SELECT county_name, cause_of_death,
               deaths, crude_rate, age_adjusted_rate, year
        FROM {TABLE_MORTALITY}
        WHERE ({loc_conditions})
          AND (cause_of_death LIKE ? OR icd10_code LIKE ?)
          AND year = (SELECT MAX(year) FROM {TABLE_MORTALITY})
        ORDER BY age_adjusted_rate DESC NULLS LAST, deaths DESC NULLS LAST
        LIMIT 30
    """
    params = loc_params + [f"%{cause}%", f"%{cause}%"]
    rows = _query_db(sql, tuple(params))

    if not rows:
        return (
            f"No mortality data found for cause='{cause}' across "
            f"locations: {', '.join(locations)}.\n"
            "Data is state-level. Try full state names like 'Louisiana', 'Texas'.\n"
            "Use get_mortality_data('United States', cause='{cause}') for national data."
        )

    # Deduplicate — one row per location (most recent, highest-burden match)
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        key = row.get("county_name", "")
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    cause_label = deduped[0].get("cause_of_death", cause)
    year_val = deduped[0].get("year", "N/A")

    lines = [
        f"Mortality Comparison: '{cause_label}' | Year: {year_val}",
        f"{'Rank':<5} {'Location':<30} {'Deaths':>8} {'Crude Rate':>12} {'Age-Adj Rate':>14}",
        "-" * 73,
    ]

    for rank, row in enumerate(deduped, 1):
        loc = (row.get("county_name") or "Unknown")[:28]
        deaths = row.get("deaths")
        crude = row.get("crude_rate")
        aadj = row.get("age_adjusted_rate")

        deaths_str = f"{int(deaths):,}" if deaths is not None else "Suppressed"
        crude_str = f"{crude:.1f}" if crude is not None else "N/A"
        aadj_str = f"{aadj:.1f}" if aadj is not None else "N/A"

        lines.append(
            f"{rank:<5} {loc:<30} {deaths_str:>8} {crude_str:>12} {aadj_str:>14}"
        )

    lines.append(
        "\nRates per 100,000 population. Age-adjusted to 2000 U.S. standard. "
        "Data is state-level (1999–2017)."
    )
    lines.append(
        "Source: NCHS Leading Causes of Death: United States, "
        "https://data.cdc.gov/resource/bi63-dtpu"
    )
    return "\n".join(lines)
