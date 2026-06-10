# backend/pubhealth_llm/app/planner.py
"""
Deferred per ARCHITECTURE.md §3a — not on the request path yet.

Planner agent — classifies request intent and routes to responder or reporter.

The planner is a cheap, fast Haiku agent with structured output.
Its ONLY job is classification + routing — it never answers the question.

Public API:
    plan = await make_plan("What is the diabetes rate in Travis County?")
    # plan.mode        → "artifact"
    # plan.intent      → "diabetes statistics query"
    # plan.reason      → "named county + disease keyword"

    plan_request is an alias for make_plan (backward compat).
"""

# ============================================================================
# DORMANT — NOT ON THE LIVE REQUEST PATH
#
# This module requires ANTHROPIC_API_KEY (hardcoded to AnthropicModel).
# It is NOT used by run_agent() or any server route.
# Before activating: port to the same BedrockConverseModel pattern as agent.py.
# ============================================================================

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from pubhealth_llm.app.schemas import ArtifactType, Plan

load_dotenv()

logger = logging.getLogger(__name__)

_PLANNER_MODEL = "claude-haiku-4-5-20251001"

_PLANNER_SYSTEM_PROMPT = """\
You are a routing agent for a public health intelligence tool.
Your ONLY job is to classify the user's question and decide how to answer it.
Do NOT answer the question yourself.

ROUTE TO REPORTER (mode=artifact) when:
- The user asks for health statistics, prevalence rates, mortality data
- The user wants to compare counties, states, or jurisdictions
- The user wants a ranking of counties or areas
- The user asks about historical outbreaks, MMWR data, or disease trends
- The question can only be answered by querying data

ROUTE TO REPORTER with artifact_type=decision_tree when:
- The user asks about cost-effectiveness analysis
- The user asks for a decision tree or intervention analysis
- The user asks "is it worth it to..." type questions about health interventions

ROUTE TO RESPONDER (mode=chat) when:
- The user asks "what can you do?" or "how do I use this?"
- The user asks a purely definitional question (no data needed)
- The user asks a follow-up clarification about a prior answer
- The question is a greeting or meta-question about the tool itself

Fields to set:
- mode: "artifact" for data questions, "chat" for conversational questions
- artifact_type: "report" for most data questions; "ranking" for ranking requests;
  "comparison" for multi-jurisdiction comparisons; "decision_tree" for
  cost-effectiveness/intervention analysis; null for chat
- intent: one-phrase description of what the user wants
- reason: brief explanation of your routing decision (1 sentence, for debugging)
"""

_FALLBACK_PLAN = Plan(
    mode="artifact",
    artifact_type=ArtifactType.report,
    intent="fallback",
    reason="planner_error_or_low_confidence",
)

_planner_agent: Optional[Agent] = None


def _get_planner() -> Agent:
    """Return the planner agent, creating it once on first call.

    Thread safety note: the check-then-set is safe in asyncio (single-threaded
    event loop, no preemption between the None check and assignment). If this
    module is ever used in a multi-threaded context, add a threading.Lock.
    """
    global _planner_agent
    if _planner_agent is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        model = AnthropicModel(
            _PLANNER_MODEL,
            provider=AnthropicProvider(api_key=api_key),
        )
        _planner_agent = Agent(
            model=model,
            output_type=Plan,
            system_prompt=_PLANNER_SYSTEM_PROMPT,
        )
    return _planner_agent


async def make_plan(question: str, message_history: Optional[list] = None) -> Plan:
    """
    Classify the user's question and return a routing Plan.

    Always returns a valid Plan — falls back to the reporter on any error
    so that a planner failure never drops a user request.

    Args:
        question: The user's raw question string.
        message_history: Optional prior conversation turns. Accepted for API
            compatibility but not forwarded to the LLM — the planner only
            needs the current question for classification.

    Returns:
        Plan with mode, artifact_type, intent, and reason.
    """
    try:
        agent = _get_planner()
        result = await agent.run(question)
        return result.output
    except EnvironmentError as exc:
        logger.error("Planner configuration error — missing API key: %s", exc)
        return _FALLBACK_PLAN.model_copy()
    except Exception as exc:
        logger.warning("Planner failed (%s), using fallback plan", exc)
        return _FALLBACK_PLAN.model_copy()


# Backward-compat alias — make_plan accepts an optional message_history param
# with a default, so existing callers using plan_request(question) still work.
plan_request = make_plan
