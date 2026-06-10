# backend/pubhealth_llm/app/responder.py
"""
Deferred per ARCHITECTURE.md §3a — not on the request path yet.

Responder agent — handles conversational / chat-path responses.

The responder answers simple questions about the tool, clarifications,
and any follow-up that does not require data retrieval. It does not
call CDC tools — that is the reporter's job.

Public API:
    message = await respond("What can this tool do?")
    # returns a plain string
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

load_dotenv()

logger = logging.getLogger(__name__)

_RESPONDER_MODEL = "claude-haiku-4-5-20251001"

_RESPONDER_SYSTEM_PROMPT = """\
You are a conversational assistant for pubHealthLLM, a public health data tool.

Answer the user's question helpfully and concisely. Keep responses to 2–3
sentences for clarifications and capability questions.

If the user is asking about data (statistics, comparisons, county rankings,
disease trends), let them know the tool can generate a full structured report
and suggest they ask their data question directly.

You do NOT have access to any data tools — refer data questions to the reporter.
"""

_responder_agent: Optional[Agent] = None


def _get_responder() -> Agent:
    """Return the responder agent, creating it once on first call.

    Thread safety note: the check-then-set is safe in asyncio (single-threaded
    event loop, no preemption between the None check and assignment). If this
    module is ever used in a multi-threaded context, add a threading.Lock.
    """
    global _responder_agent
    if _responder_agent is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        model = AnthropicModel(
            _RESPONDER_MODEL,
            provider=AnthropicProvider(api_key=api_key),
        )
        _responder_agent = Agent(
            model=model,
            system_prompt=_RESPONDER_SYSTEM_PROMPT,
        )
    return _responder_agent


async def run_responder(question: str, message_history: Optional[list] = None) -> str:
    """
    Run the responder agent on a conversational question.

    Args:
        question:        The user's question (routed here by the planner).
        message_history: Optional prior conversation turns for context.

    Returns:
        Plain text response string.

    Raises:
        Exception: Propagated from PydanticAI on fatal errors.
                   The orchestrator should catch and fall back to the reporter.
    """
    agent = _get_responder()
    result = await agent.run(question, message_history=message_history or [])
    return str(result.output)


respond = run_responder  # public API alias
