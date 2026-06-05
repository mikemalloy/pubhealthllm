# backend/pubhealth_llm/app/orchestrator.py
"""
Orchestrator — entry point for /ask requests.

run_ask() is the single public function in this module. It:
  1. Calls the planner to classify the question and choose a render surface.
  2. Routes to run_responder (chat) or run_agent (artifact/reporter).
  3. Assembles and returns a typed AskResponse envelope.

This module is intentionally free of FastAPI and HTTP concerns — it is a
pure Python coroutine that server.py will call from a POST /ask route.

Usage:
    from pubhealth_llm.app.orchestrator import run_ask

    response = await run_ask("What is the diabetes rate in Travis County, TX?")
    # response.mode       → "artifact"
    # response.artifact   → Artifact(type=ArtifactType.report, ...)
    # response.meta       → Meta(intent="...", timing_ms=1234)
"""

import logging
import time
from typing import Optional

from pubhealth_llm.app.agent import run_agent
from pubhealth_llm.app.planner import plan_request
from pubhealth_llm.app.responder import run_responder
from pubhealth_llm.app.schemas import Artifact, ArtifactType, AskResponse, Meta

logger = logging.getLogger(__name__)

# Characters of the reporter summary to surface as chat_message teaser
_TEASER_LENGTH = 200


async def run_ask(
    question: str,
    message_history: Optional[list] = None,
) -> AskResponse:
    """
    Route a user question through the multi-agent layer.

    Args:
        question:        The user's natural language question.
        message_history: Optional prior conversation turns for context.

    Returns:
        AskResponse with mode, chat_message, optional artifact, and meta.
    """
    start_ms = int(time.monotonic() * 1000)

    plan = await plan_request(question)

    if plan.mode == "chat":
        try:
            chat_message = await run_responder(question, message_history=message_history)
            timing_ms = int(time.monotonic() * 1000) - start_ms
            return AskResponse(
                mode="chat",
                chat_message=chat_message,
                artifact=None,
                meta=Meta(
                    intent=plan.intent,
                    tools_used=[],  # TODO: populate from agent result.all_messages() in a follow-up
                    model="planner+responder",
                    timing_ms=timing_ms,
                ),
            )
        except Exception as exc:
            logger.warning(
                "Responder failed (%s), falling back to reporter", exc
            )
            # Fall through to artifact/reporter path below

    # artifact path — full reporter
    pub_health_response = await run_agent(question, message_history=message_history)

    summary = pub_health_response.summary
    teaser = summary[:_TEASER_LENGTH] + "…" if len(summary) > _TEASER_LENGTH else summary

    timing_ms = int(time.monotonic() * 1000) - start_ms
    return AskResponse(
        mode="artifact",
        chat_message=teaser,
        artifact=Artifact(
            type=plan.artifact_type or ArtifactType.report,
            title=plan.intent,
            payload=pub_health_response.model_dump(),
        ),
        meta=Meta(
            intent=plan.intent,
            tools_used=[],  # TODO: populate from agent result.all_messages() in a follow-up
            model="planner+reporter",
            timing_ms=timing_ms,
        ),
    )
