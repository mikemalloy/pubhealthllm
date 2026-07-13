"""
PydanticAI Orchestration Agent for pubHealthLLM.

This module creates and configures the main agent that:
  1. Receives a natural language question from a public health professional
  2. Decides which combination of tools to call (MMWR search, SQL queries)
  3. Synthesizes the tool outputs into a structured PublicHealthResponse
  4. Returns the response to the FastAPI interface

Model selection is controlled by the PUBHEALTH_MODEL environment variable
(see pubhealth_llm.app.config).  Supported providers: bedrock, anthropic, openai.

Usage:
    from pubhealth_llm.app.agent import run_agent
    response = await run_agent("What is the obesity rate in Travis County, TX?")
"""

import datetime
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.bedrock import BedrockProvider
from pydantic_ai.usage import UsageLimits

from pubhealth_llm.app.config import get_model
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

## MANDATORY OUTPUT DELIVERY

After gathering data with tools, you MUST deliver your response by calling the
`final_result` tool — NEVER as plain text or markdown.

The `final_result` tool takes a JSON argument with these required fields:
- "summary": string — a compelling prose paragraph (NOT bullets)
- "evidence": array of strings — specific data findings with values
- "caveats": array of strings — data limitations
- "sources": array of strings — citations (e.g. "CDC PLACES 2023")

And optional fields:
- "statistics": array of StatisticEntry objects
- "historical_context": string
- "disclaimer": string

Call `final_result` once with all gathered data. Do NOT output text. Do NOT
output markdown. The ONLY way to complete a turn is to call `final_result`.
"""

# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def _build_agent(model_str: str) -> Agent:
    """Build a PydanticAI agent for the given provider:model string.

    Args:
        model_str: A string in the form "provider:model-id", e.g.
                   "anthropic:claude-sonnet-4-6" or "openai:gpt-4o-mini".

    Returns:
        Configured PydanticAI Agent with all eight tools registered.

    Raises:
        ValueError:       If model_str is not in "provider:model-id" format,
                          or if the provider is not supported.
        EnvironmentError: If the required API key for the provider is not set.
    """
    parts = model_str.split(":", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid model string {model_str!r}. Expected 'provider:model-id'."
        )
    provider, api_model_id = parts

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file and restart."
            )
        model = AnthropicModel(api_model_id, provider=AnthropicProvider(api_key=api_key))

    elif provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY not set. Add it to your .env file to use OpenAI models."
            )
        model = OpenAIChatModel(api_model_id, provider=OpenAIProvider(api_key=api_key))

    elif provider == "bedrock":
        model = BedrockConverseModel(
            api_model_id,
            provider=BedrockProvider(
                region_name=os.getenv("AWS_REGION", "us-west-1")
            ),
        )

    else:
        raise ValueError(
            f"Provider {provider!r} is not supported. "
            f"Set PUBHEALTH_MODEL to 'bedrock:<model-id>', "
            f"'anthropic:<model>', or 'openai:<model>'."
        )

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
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    entry = f"[{timestamp}] Q: {question!r}\n             A: {response_summary!r}\n"
    try:
        with open(LOG_FILE, "a") as fh:
            fh.write(entry)
    except OSError as exc:
        logger.warning("Could not write to query log: %s", exc)


# ---------------------------------------------------------------------------
# Result type and tool extraction
# ---------------------------------------------------------------------------


@dataclass
class ToolEvent:
    """One tool call + return, captured during an eval run."""
    name: str
    args: dict
    content: str


@dataclass
class EvalTrace:
    """Tool-call telemetry captured when _capture_trace=True. Not populated in production."""
    tool_events: list[ToolEvent]

    @property
    def tool_names(self) -> list[str]:
        return [e.name for e in self.tool_events]


@dataclass
class AgentResult:
    """Result returned by run_agent, bundling the structured response and tool telemetry."""
    response: PublicHealthResponse
    tools_used: list[str]
    trace: Optional[EvalTrace] = None


def _extract_tools_used(result) -> list[str]:
    """Extract unique domain tool names from an AgentRunResult, excluding the synthetic output tool.

    Args:
        result: An AgentRunResult (or compatible object with new_messages() and _output_tool_name).

    Returns:
        Deduplicated list of tool names in first-occurrence order, excluding the output tool.
    """
    # _output_tool_name is a private PydanticAI attribute (pydantic-ai 1.86.0).
    # It holds the name of the synthetic structured-output tool ("final_result").
    # Verify on pydantic-ai upgrades: pydantic_ai._output.DEFAULT_OUTPUT_TOOL_NAME.
    output_tool_name = result._output_tool_name
    seen: set[str] = set()
    tools: list[str] = []
    for msg in result.new_messages():
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    name = part.tool_name
                    if name != output_tool_name and name not in seen:
                        seen.add(name)
                        tools.append(name)
    return tools


def _extract_trace(result) -> EvalTrace:
    """Extract full tool call+return telemetry from a PydanticAI AgentRunResult.

    Pairs ToolCallPart (args) with subsequent ToolReturnPart (content) by tool_call_id.
    Falls back to positional pairing if tool_call_id is absent.
    """
    output_tool_name = result._output_tool_name

    calls: dict[str, tuple[str, dict]] = {}
    call_order: list[str] = []
    call_idx = 0

    for msg in result.new_messages():
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart) and part.tool_name != output_tool_name:
                    key = part.tool_call_id or f"__pos_{call_idx}__"
                    if isinstance(part.args, dict):
                        args = part.args
                    else:
                        try:
                            args = json.loads(part.args)
                        except (json.JSONDecodeError, TypeError):
                            args = {"_raw": str(part.args)}
                    calls[key] = (part.tool_name, args)
                    call_order.append(key)
                    call_idx += 1

    returns: dict[str, str] = {}
    return_idx = 0
    for msg in result.new_messages():
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolReturnPart):
                key = getattr(part, "tool_call_id", None) or f"__pos_{return_idx}__"
                returns[key] = str(part.content)
                return_idx += 1

    events: list[ToolEvent] = []
    for key in call_order:
        name, args = calls[key]
        content = returns.get(key, "")
        events.append(ToolEvent(name=name, args=args, content=content))

    return EvalTrace(tool_events=events)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


# Bounded per-run request limit. pydantic-ai defaults to 50, which lets a
# non-converging ("thrashing") agent burn ~50 model round-trips / ~162s before
# raising UsageLimitExceeded (observed in prod). A legitimate answer needs only
# a handful of round-trips, so cap it low: a thrash then fails fast (~40s) and
# at ~1/4 the wasted token spend. Env-overridable via PUBHEALTH_REQUEST_LIMIT.
_REQUEST_LIMIT = int(os.environ.get("PUBHEALTH_REQUEST_LIMIT", "12"))

# The agent loop is non-deterministic — an intermittent thrash usually converges
# on a fresh attempt (confirmed: the same question that thrashed succeeded on a
# manual re-ask). Retry once (2 attempts total) before degrading gracefully.
_AGENT_MAX_RETRIES = 1


async def run_agent(
    question: str,
    message_history: Optional[list] = None,
    model: Optional[str] = None,
    _capture_trace: bool = False,
) -> AgentResult:
    """
    Run the pubHealthLLM agent on a user question.

    This is the primary entry point called by the FastAPI interface.
    It runs the PydanticAI agent, which calls tools as needed and
    returns an AgentResult bundling the structured PublicHealthResponse
    with the list of domain tools actually called during the run.

    Args:
        question:        The user's natural language question.
        message_history: Optional list of prior conversation messages
                         for multi-turn context.
        model:           Provider:model-id string (e.g. "bedrock:us.amazon.nova-pro-v1:0").
                         Defaults to the value of PUBHEALTH_MODEL env var, or
                         "bedrock:us.amazon.nova-pro-v1:0" if that var is unset.

    Returns:
        AgentResult with a validated PublicHealthResponse (summary, evidence,
        statistics, historical context, citations) and the list of domain
        tool names invoked during the run.

    Raises:
        Exception: Propagated from PydanticAI on fatal errors.
                   The FastAPI layer catches these and shows a user message.
    """
    model_str = model if model is not None else get_model()
    agent = _build_agent(model_str)
    logger.info("Running agent (model=%r) for question: %r", model_str, question)

    max_attempts = 1 + _AGENT_MAX_RETRIES
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await agent.run(
                question,
                message_history=message_history or [],
                usage_limits=UsageLimits(request_limit=_REQUEST_LIMIT),
            )
            response: PublicHealthResponse = result.output
            tools_used = _extract_tools_used(result)
            trace = _extract_trace(result) if _capture_trace else None
            _log_query(question, response.summary[:200])
            return AgentResult(response=response, tools_used=tools_used, trace=trace)

        except Exception as exc:
            last_exc = exc
            logger.error(
                "Agent run failed (attempt %d/%d): %s",
                attempt, max_attempts, exc, exc_info=True,
            )
            # Fall through: retry if attempts remain, else degrade gracefully.

    # All attempts exhausted — return a structured error response rather than raising.
    return AgentResult(
        response=PublicHealthResponse(
            summary=(
                "I encountered an error while processing your question. "
                "Please try rephrasing or check that the data pipeline has been run."
            ),
            evidence=[f"Error details: {str(last_exc)[:300]}"],
            caveats=[
                "The data ingestion pipeline may not have been run yet.",
                "Check that the required API key for the selected model is set in your .env file.",
            ],
            sources=["No data retrieved due to error."],
        ),
        tools_used=[],
        trace=None,
    )
