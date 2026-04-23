"""
PydanticAI Orchestration Agent for pubHealthLLM.

This module creates and configures the main agent that:
  1. Receives a natural language question from a public health professional
  2. Decides which combination of tools to call (MMWR search, SQL queries)
  3. Synthesizes the tool outputs into a structured PublicHealthResponse
  4. Returns the response to the Gradio interface

The agent uses Anthropic's claude-sonnet-4-5 model via PydanticAI's
Anthropic provider integration.

Usage:
    from pubhealth_llm.app.agent import run_agent
    response = await run_agent("What is the obesity rate in Travis County, TX?")
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from pubhealth_llm.app.schemas import PublicHealthResponse
from pubhealth_llm.app.tools import (
    compare_locations,
    compare_mortality,
    get_available_measures,
    get_health_statistics,
    get_mortality_data,
    get_worst_counties_by_measure,
    rank_counties_composite,
    search_mmwr_reports,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

load_dotenv()

ANTHROPIC_MODEL_NAME = "claude-sonnet-4-5"
LOG_FILE = "query_log.txt"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are pubHealthLLM, a public health decision support assistant.
You combine CDC MMWR surveillance reports with CDC PLACES county-level health
statistics to answer questions from public health professionals.

## MANDATORY TOOL USE RULES

You MUST call tools before generating any response. Never fabricate statistics.

### Tool selection:
- Named location stats (county/state): call tool_get_health_statistics
- "Worst counties" for ONE measure in a state: call tool_get_worst_counties_by_measure
- Comparing specific named locations: call tool_compare_locations
- Outbreak history, disease trends, epidemiology background: call tool_search_mmwr_reports
- Unclear what measures exist: call tool_get_available_measures first
- Combined burden / prioritize across MULTIPLE measures: call tool_rank_counties_composite

### Multi-measure prioritization — use the composite tool:
When the user asks which counties to PRIORITIZE or which have the HIGHEST COMBINED
BURDEN across 2 or more health measures, call tool_rank_counties_composite ONCE
with all measures listed. This tool computes z-scores and a deterministic composite
score across the full county universe — do NOT substitute multiple calls to
tool_get_worst_counties_by_measure for this purpose.

Example triggers for tool_rank_counties_composite:
  - "prioritize counties for diabetes, obesity, AND physical inactivity"
  - "which counties have the highest combined burden"
  - "integrated prevention program" / "co-occurring conditions"
  - "rank counties across multiple conditions"

After calling tool_rank_counties_composite you may additionally call
tool_search_mmwr_reports for historical context, but do NOT also call
tool_get_worst_counties_by_measure per measure — the composite output already
contains those individual values.

### Always:
- Cite exact data values and the year they were collected
- Note confidence intervals when available
- Acknowledge data limitations (survey-based, may lag by 1-2 years)
- State that this is decision SUPPORT — all recommendations require validation
  by qualified public health professionals

## WRITING QUALITY

You are not generating a database report. You are briefing people who make
consequential decisions about budgets, programs, and communities. Write
accordingly.

### Voice and register:
Write with the authority and clarity of a seasoned public health official who
has testified before county commissioners and spoken at community town halls.
You know the data cold. You also know that data alone does not move people —
framing does. Use both.

### The summary field is your most important sentence:
The summary will be read by people who may not read anything else. Do not open
it with a statistic. Open with the human or fiscal reality, then anchor it in
the numbers. Make the scale vivid — if 1 in 3 adults in a county has diabetes,
say so in a way that lands. Give the reader a line they can actually say out
loud in a budget meeting or a board presentation. Write it as a single flowing
paragraph, never as bullets or sub-headers.

### Prose fields — write beautifully, not clinically:
Within the constraints of evidence-based response, write well. Vary your
sentence length. Use concrete analogies when they make abstract rates tangible.
Do not default to bullet-point thinking when you are writing prose. A reader
should feel informed and moved to act, not feel like they received a form letter.

### What never changes regardless of writing style:
- Every figure cited must come from a tool result — never invented
- Confidence intervals and data years must be acknowledged where material
- The disclaimer that this is decision support, not clinical guidance, must
  always be present

You also have access to CDC Wonder mortality data which provides death counts
and age-adjusted mortality rates by cause of death at the state level. Use
mortality data when you need to quantify the ultimate health consequences
beyond prevalence — death rates are the most compelling data point in budget
arguments.
"""

# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------


def _create_agent() -> Agent:
    """
    Instantiate and configure the PydanticAI agent with all tools.

    Called once at module load time.  The agent is a module-level
    singleton; Gradio's async event loop calls run_agent() which
    invokes agent.run() on it.

    Returns:
        Configured PydanticAI Agent instance.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file and restart."
        )

    model = AnthropicModel(ANTHROPIC_MODEL_NAME, provider=AnthropicProvider(api_key=api_key))

    agent: Agent[None, PublicHealthResponse] = Agent(
        model=model,
        output_type=PublicHealthResponse,
        system_prompt=SYSTEM_PROMPT,
    )

    # -----------------------------------------------------------------------
    # Register tools via decorators
    # -----------------------------------------------------------------------

    @agent.tool_plain
    def tool_search_mmwr_reports(query: str, top_k: int = 5) -> str:
        """Search CDC MMWR outbreak reports for historical context and disease trends.

        Args:
            query: Search query including disease names and geographic terms.
            top_k: Number of passages to retrieve (default 5).
        """
        logger.info("Tool call: search_mmwr_reports(query=%r, top_k=%d)", query, top_k)
        return search_mmwr_reports(query, top_k=top_k)

    @agent.tool_plain
    def tool_get_health_statistics(
        location: str,
        measure: Optional[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """Get CDC PLACES health statistics for a named county, city, or state.

        Args:
            location: County or state name (partial names work, e.g. "Alameda").
            measure:  Health measure keyword (e.g. "diabetes"). None returns all.
            state:    Two-letter state abbreviation to narrow results (e.g. "CA").
        """
        logger.info(
            "Tool call: get_health_statistics(location=%r, measure=%r, state=%r)",
            location, measure, state,
        )
        return get_health_statistics(location, measure=measure, state=state)

    @agent.tool_plain
    def tool_compare_locations(locations: list[str], measure: str) -> str:
        """Compare a health measure across multiple named counties or states.

        Args:
            locations: List of location names (e.g. ["Travis County", "Harris County"]).
            measure:   Health measure keyword (e.g. "obesity", "diabetes").
        """
        logger.info(
            "Tool call: compare_locations(locations=%r, measure=%r)",
            locations, measure,
        )
        return compare_locations(locations, measure)

    @agent.tool_plain
    def tool_get_available_measures(category: Optional[str] = None) -> str:
        """List all queryable CDC PLACES health measures.

        Args:
            category: Optional filter (e.g. "Chronic Disease"). None returns all.
        """
        logger.info("Tool call: get_available_measures(category=%r)", category)
        return get_available_measures(category=category)

    @agent.tool_plain
    def tool_get_worst_counties_by_measure(
        state: str,
        measure: str,
        top_n: int = 10,
    ) -> str:
        """Rank counties in a state from worst to best for a health measure.
        Use for "which counties are worst/highest/most affected" questions
        about a SINGLE measure.

        Args:
            state:   Two-letter state abbreviation (e.g. "TX").
            measure: Health measure keyword (e.g. "diabetes", "obesity").
            top_n:   Counties to return (default 10, max 50).
        """
        logger.info(
            "Tool call: get_worst_counties_by_measure(state=%r, measure=%r, top_n=%d)",
            state, measure, top_n,
        )
        return get_worst_counties_by_measure(state, measure, top_n=top_n)

    @agent.tool_plain
    def tool_rank_counties_composite(
        state: str,
        measures: list[str],
        target_location: Optional[str] = None,
        top_n: int = 10,
    ) -> str:
        """Rank counties by their COMBINED burden across 2–5 health measures
        using z-score normalization and a composite score. Use this for
        prioritization questions that span multiple conditions simultaneously.

        Args:
            state:           Two-letter state abbreviation (e.g. "TX").
            measures:        List of 2–5 health measure keywords
                             (e.g. ["diabetes", "obesity", "physical inactivity"]).
            target_location: Optional county name to highlight in results.
            top_n:           Counties to show (default 10, max 50).
        """
        logger.info(
            "Tool call: rank_counties_composite(state=%r, measures=%r, "
            "target=%r, top_n=%d)",
            state, measures, target_location, top_n,
        )
        return rank_counties_composite(
            state, measures, target_location=target_location, top_n=top_n
        )

    @agent.tool_plain
    def tool_get_mortality_data(
        location: str,
        cause: Optional[str] = None,
        year: Optional[int] = None,
    ) -> str:
        """Retrieve CDC mortality statistics (death counts and age-adjusted rates)
        for a state or the nation. Use when the question involves death rates,
        leading causes of death, or when mortality data strengthens a budget
        argument beyond prevalence figures. Data is state-level, 1999–2017.

        Args:
            location: State name (e.g. "Louisiana"), two-letter abbreviation
                      (e.g. "LA"), or "United States" for national data.
            cause:    Cause keyword (e.g. "diabetes", "heart disease", "cancer",
                      "stroke", "all causes"). None returns top 10 causes.
            year:     Specific year (1999–2017). None uses most recent available.
        """
        logger.info(
            "Tool call: get_mortality_data(location=%r, cause=%r, year=%r)",
            location, cause, year,
        )
        return get_mortality_data(location, cause=cause, year=year)

    @agent.tool_plain
    def tool_compare_mortality(locations: list[str], cause: str) -> str:
        """Compare mortality rates for a specific cause across multiple states.
        Use when the user wants to rank states by mortality burden or contrast
        a target state against peers and national average.

        Args:
            locations: List of state names or "United States" for national
                       benchmark (e.g. ["Louisiana", "Mississippi", "United States"]).
            cause:     Cause keyword (e.g. "diabetes", "heart disease", "cancer").
        """
        logger.info(
            "Tool call: compare_mortality(locations=%r, cause=%r)",
            locations, cause,
        )
        return compare_mortality(locations, cause)

    return agent


# Module-level agent singleton
_agent: Optional[Agent] = None


def get_agent() -> Agent:
    """
    Return the module-level agent singleton, creating it if needed.

    Lazy initialization allows importing this module without a
    GROQ_API_KEY (useful for testing tools.py independently).

    Returns:
        The configured PydanticAI Agent.

    Raises:
        EnvironmentError: If GROQ_API_KEY is not set.
    """
    global _agent
    if _agent is None:
        _agent = _create_agent()
    return _agent


# ---------------------------------------------------------------------------
# Query logging
# ---------------------------------------------------------------------------


def _log_query(question: str, response_summary: str) -> None:
    """
    Append a query and its summary to the log file for debugging.

    Args:
        question:         The user's original question.
        response_summary: First line of the agent's response summary.
    """
    import datetime

    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    entry = f"[{timestamp}] Q: {question!r}\n             A: {response_summary!r}\n"
    try:
        with open(LOG_FILE, "a") as fh:
            fh.write(entry)
    except OSError as exc:
        logger.warning("Could not write to query log: %s", exc)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def run_agent(
    question: str,
    message_history: Optional[list] = None,
) -> PublicHealthResponse:
    """
    Run the pubHealthLLM agent on a user question.

    This is the primary entry point called by the Gradio interface.
    It runs the PydanticAI agent, which calls tools as needed and
    returns a structured PublicHealthResponse.

    Args:
        question:        The user's natural language question.
        message_history: Optional list of prior conversation messages
                         for multi-turn context.

    Returns:
        A validated PublicHealthResponse with summary, evidence,
        statistics, historical context, and citations.

    Raises:
        Exception: Propagated from PydanticAI on fatal errors.
                   The Gradio layer catches these and shows a user message.
    """
    agent = get_agent()
    logger.info("Running agent for question: %r", question)

    try:
        result = await agent.run(
            question,
            message_history=message_history or [],
        )
        response: PublicHealthResponse = result.output
        _log_query(question, response.summary[:200])
        return response

    except Exception as exc:
        logger.error("Agent run failed: %s", exc, exc_info=True)
        # Return a structured error response rather than raising
        return PublicHealthResponse(
            summary=(
                "I encountered an error while processing your question. "
                "Please try rephrasing or check that the data pipeline has been run."
            ),
            evidence=[f"Error details: {str(exc)[:300]}"],
            caveats=[
                "The data ingestion pipeline may not have been run yet.",
                "Check that ANTHROPIC_API_KEY is set correctly in your .env file.",
            ],
            sources=["No data retrieved due to error."],
        )
