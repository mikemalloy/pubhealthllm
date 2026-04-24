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

LOG_FILE = "query_log.txt"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

# Maps dropdown key → (provider, actual API model ID)
_MODEL_MAP: dict[str, tuple[str, str]] = {
    "anthropic:claude-sonnet-4-6":      ("anthropic", "claude-sonnet-4-6"),
    "anthropic:claude-haiku-4":         ("anthropic", "claude-haiku-4-5-20251001"),
    "openai:gpt-4o-mini":               ("openai",    "gpt-4o-mini"),
    "groq:llama-3.3-70b-versatile":     ("groq",      "llama-3.3-70b-versatile"),
    "groq:llama-3.1-8b-instant":        ("groq",      "llama-3.1-8b-instant"),
}

DEFAULT_MODEL_KEY = "anthropic:claude-sonnet-4-6"

# Per-model agent cache — agents are heavyweight; create each once
_agent_cache: dict[str, Agent] = {}

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

# Condensed prompt for Groq models — same tool-routing rules, no verbose
# writing instructions.  Groq free tier caps at 12,000 TPM; the full prompt
# plus 8 tool definitions pushes requests over that limit.
SYSTEM_PROMPT_GROQ = """
You are pubHealthLLM, a public health decision support assistant.
Answer questions using CDC MMWR surveillance reports and CDC PLACES county-level
health statistics. Always call tools — never fabricate statistics.

## TOOL SELECTION

- Named location stats (county/state): tool_get_health_statistics
- Worst counties for ONE measure: tool_get_worst_counties_by_measure
- Comparing named locations: tool_compare_locations
- Outbreak history or disease trends: tool_search_mmwr_reports
- Unclear what measures exist: tool_get_available_measures first
- Combined burden across 2+ measures: tool_rank_counties_composite (call ONCE)
- Death rates / leading causes / mortality comparisons: tool_get_mortality_data or tool_compare_mortality

For multi-measure prioritization use tool_rank_counties_composite with all
measures in one call — do NOT substitute repeated tool_get_worst_counties_by_measure calls.

## ALWAYS
- Cite exact values and collection year
- Note confidence intervals where available
- Acknowledge data limitations (survey-based, may lag 1-2 years)
- Every response must include a disclaimer that outputs are decision support only
  and require validation by qualified public health professionals
"""

# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------


def _create_agent(model_key: str = DEFAULT_MODEL_KEY) -> Agent:
    """
    Instantiate and configure the PydanticAI agent with all tools.

    Creates an agent for the given model key (e.g. "anthropic:claude-sonnet-4-6").
    Results are cached in _agent_cache — this function is called at most once
    per unique model key.

    Args:
        model_key: One of the keys defined in _MODEL_MAP.

    Returns:
        Configured PydanticAI Agent instance.

    Raises:
        EnvironmentError: If the required API key for the provider is not set.
        ValueError:       If model_key is not in _MODEL_MAP.
    """
    if model_key not in _MODEL_MAP:
        raise ValueError(
            f"Unknown model key {model_key!r}. "
            f"Valid options: {list(_MODEL_MAP)}"
        )

    provider, api_model_id = _MODEL_MAP[model_key]

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file and restart."
            )
        model = AnthropicModel(api_model_id, provider=AnthropicProvider(api_key=api_key))

    elif provider == "openai":
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY not set. Add it to your .env file to use OpenAI models."
            )
        model = OpenAIModel(api_model_id, provider=OpenAIProvider(api_key=api_key))

    elif provider == "groq":
        from pydantic_ai.models.groq import GroqModel
        from pydantic_ai.providers.groq import GroqProvider
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not set. Add it to your .env file to use Groq models."
            )
        model = GroqModel(api_model_id, provider=GroqProvider(api_key=api_key))

    else:
        raise ValueError(f"Unknown provider {provider!r} in model key {model_key!r}")

    # Groq free tier: 12,000 TPM limit. Use the condensed prompt to keep
    # requests under the limit. Anthropic models use the full rich prompt.
    system_prompt = SYSTEM_PROMPT_GROQ if provider == "groq" else SYSTEM_PROMPT

    agent: Agent[None, PublicHealthResponse] = Agent(
        model=model,
        output_type=PublicHealthResponse,
        system_prompt=system_prompt,
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


def get_agent(model_key: str = DEFAULT_MODEL_KEY) -> Agent:
    """
    Return a cached agent for the given model key, creating it if needed.

    Lazy initialization means importing this module never triggers an API
    key check — useful for testing tools.py independently.

    Args:
        model_key: One of the keys defined in _MODEL_MAP.

    Returns:
        The configured PydanticAI Agent for that model.
    """
    if model_key not in _agent_cache:
        _agent_cache[model_key] = _create_agent(model_key)
    return _agent_cache[model_key]


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
    model: Optional[str] = None,
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
        model:           Model key from _MODEL_MAP (e.g. "anthropic:claude-sonnet-4-6").
                         Defaults to DEFAULT_MODEL_KEY if not provided.

    Returns:
        A validated PublicHealthResponse with summary, evidence,
        statistics, historical context, and citations.

    Raises:
        Exception: Propagated from PydanticAI on fatal errors.
                   The Gradio layer catches these and shows a user message.
    """
    model_key = model or DEFAULT_MODEL_KEY
    agent = get_agent(model_key)
    logger.info("Running agent (model=%r) for question: %r", model_key, question)

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
                "Check that the required API key for the selected model is set in your .env file.",
            ],
            sources=["No data retrieved due to error."],
        )
