# backend/pubhealth_llm/app/orchestrator.py
"""
Orchestrator — entry point for /ask requests.

run_ask() is the single public function in this module. It:
  1. Calls run_agent exactly once to retrieve a PublicHealthResponse.
  2. Derives render mode heuristically: statistics present → artifact, else → chat.
  3. Assembles and returns a typed AskResponse envelope.

This module is intentionally free of FastAPI and HTTP concerns — it is a
pure Python coroutine that server.py will call from a POST /ask route.

Usage:
    from pubhealth_llm.app.orchestrator import run_ask

    response = await run_ask("What is the diabetes rate in Travis County, TX?")
    # response.mode       → "artifact"
    # response.artifact   → Artifact(type=ArtifactType.report, ...)
    # response.meta       → Meta(intent="...", timing_ms=1234)

Design note:
    Planner and responder are parked per ARCHITECTURE.md §3a — not on the
    request path. The _is_report_worthy() function is the swap point: replace
    its body with a planner LLM call when §3a re-introduces the planner.
"""

import logging
import time
from typing import Optional

from pubhealth_llm.app import config
from pubhealth_llm.app.agent import run_agent
from pubhealth_llm.app.schemas import (
    Artifact,
    ArtifactType,
    AskResponse,
    Meta,
    PublicHealthResponse,
)

logger = logging.getLogger(__name__)

# Characters of the reporter summary to surface as chat_message teaser
_TEASER_LENGTH = 200

# Characters of the reporter summary to use in artifact title
_TITLE_LENGTH = 80


def _is_report_worthy(resp: PublicHealthResponse) -> bool:
    """Return True when resp.statistics is non-empty.

    Swap point for a future planner LLM — replace this function body when
    ARCHITECTURE.md §3a re-introduces the planner in a later phase.
    """
    return bool(resp.statistics)


async def run_ask(
    question: str,
    message_history: Optional[list] = None,
) -> AskResponse:
    """
    Route a user question through the lean single-agent path.

    Makes exactly one LLM call (run_agent). Derives render mode from the
    payload heuristically: statistics present → artifact, else → chat.

    Args:
        question:        The user's natural language question.
        message_history: Optional prior conversation turns for context.

    Returns:
        AskResponse with mode, chat_message, optional artifact, and meta.
        Never raises — exceptions produce a graceful chat fallback.
    """
    start_ms = int(time.monotonic() * 1000)

    try:
        agent_result = await run_agent(question, message_history=message_history)
    except Exception as exc:
        logger.error("Agent failed (%s), returning apologetic chat response", exc)
        timing_ms = int(time.monotonic() * 1000) - start_ms
        return AskResponse(
            mode="chat",
            chat_message=(
                "I'm sorry — I wasn't able to retrieve data for your question right now. "
                "Please try again in a moment."
            ),
            artifact=None,
            meta=Meta(
                intent=question[:200],
                tools_used=[],
                model=config.get_model(),
                timing_ms=timing_ms,
            ),
        )

    result = agent_result.response
    tools_used = agent_result.tools_used
    timing_ms = int(time.monotonic() * 1000) - start_ms

    if _is_report_worthy(result):
        summary = result.summary
        teaser = (summary[:_TEASER_LENGTH] + "…" if len(summary) > _TEASER_LENGTH else summary) or "No summary available."
        title = (summary[:_TITLE_LENGTH].rstrip() if len(summary) > _TITLE_LENGTH else summary) or "No summary available."
        return AskResponse(
            mode="artifact",
            chat_message=teaser,
            artifact=Artifact(
                type=ArtifactType.report,
                title=title,
                payload=result.model_dump(),
            ),
            meta=Meta(
                intent=question[:200],
                tools_used=tools_used,
                model=config.get_model(),
                timing_ms=timing_ms,
            ),
        )
    else:
        return AskResponse(
            mode="chat",
            chat_message=result.summary or "No data summary available for this query.",
            artifact=None,
            meta=Meta(
                intent=question[:200],
                tools_used=tools_used,
                model=config.get_model(),
                timing_ms=timing_ms,
            ),
        )
