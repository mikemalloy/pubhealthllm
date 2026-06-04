# backend/pubhealth_llm/app/planner.py
"""
Planner agent — classifies request intent and routes to responder or reporter.

The planner is a cheap, fast Haiku agent with structured output.
Its ONLY job is classification + routing — it never answers the question.

Public API:
    plan = await plan_request("What is the diabetes rate in Travis County?")
    # plan.mode        → "artifact"
    # plan.dispatch_target → "reporter"
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from pubhealth_llm.app.schemas import Plan

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

ROUTE TO RESPONDER (mode=chat) when:
- The user asks "what can you do?" or "how do I use this?"
- The user asks a purely definitional question (no data needed)
- The user asks a follow-up clarification about a prior answer
- The question is a greeting or meta-question about the tool itself

Set confidence to your routing certainty (0.0–1.0).
Set intent to a brief one-phrase description of what the user wants.
Set artifact_type to 'report' for most data questions.
"""

_FALLBACK_PLAN = Plan(
    intent="unknown — planner error, defaulting to reporter",
    mode="artifact",
    artifact_type="report",
    dispatch_target="reporter",
    confidence=0.0,
)

_planner_agent: Optional[Agent] = None


def _get_planner() -> Agent:
    """Return the planner agent, creating it once on first call."""
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


async def plan_request(question: str) -> Plan:
    """
    Classify the user's question and return a routing Plan.

    Always returns a valid Plan — falls back to the reporter on any error
    so that a planner failure never drops a user request.

    Args:
        question: The user's raw question string.

    Returns:
        Plan with mode, dispatch_target, artifact_type, confidence, intent.
    """
    try:
        agent = _get_planner()
        result = await agent.run(question)
        return result.output
    except Exception as exc:
        logger.warning("Planner failed (%s), using fallback plan", exc)
        return _FALLBACK_PLAN
