# Multi-Agent Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a planner → responder / reporter multi-agent routing layer as a pure Python module, establishing the `/ask` contract before any HTTP route is wired.

**Architecture:** A cheap Haiku planner classifies every incoming question into "chat" (conversational) or "artifact" (full report) and dispatches to either a lightweight responder agent or the existing `run_agent()` reporter. The orchestrator assembles both paths into a typed `AskResponse` envelope. No server.py edits; no frontend work.

**Tech Stack:** pydantic-ai 1.86.0 · anthropic 0.96.0 (`claude-haiku-4-5-20251001` for planner + responder, `claude-sonnet-4-6` for reporter) · pytest 8.4.1 · pytest-asyncio 1.3.0 (already configured with `asyncio_mode = auto`)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `backend/pubhealth_llm/app/schemas.py` | Add `Plan`, `ArtifactEnvelope`, `AskMeta`, `AskResponse` |
| Create | `backend/pubhealth_llm/app/planner.py` | Classify intent → `Plan`; heuristic fallback |
| Create | `backend/pubhealth_llm/app/responder.py` | Conversational chat-path agent → `str` |
| Create | `backend/pubhealth_llm/app/orchestrator.py` | `run_ask()` routing + envelope assembly |
| Create | `backend/tests/test_schemas_multi_agent.py` | Unit tests for new schema types |
| Create | `backend/tests/test_planner.py` | Unit tests for `plan_request()` |
| Create | `backend/tests/test_responder.py` | Unit tests for `run_responder()` |
| Create | `backend/tests/test_orchestrator.py` | Integration tests for `run_ask()` |

All LLM calls are mocked in tests — no API key needed to run the suite.

---

### Task 1: Add Plan and AskResponse schemas

**Files:**
- Modify: `backend/pubhealth_llm/app/schemas.py` (add four new models after line 210)
- Create: `backend/tests/test_schemas_multi_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_schemas_multi_agent.py
"""Tests for multi-agent schemas: Plan, ArtifactEnvelope, AskMeta, AskResponse."""
import pytest

from pubhealth_llm.app.schemas import ArtifactEnvelope, AskMeta, AskResponse, Plan


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def test_plan_artifact_mode_requires_no_artifact_type():
    """artifact_type is optional — can be None even in artifact mode."""
    p = Plan(
        intent="look up diabetes statistics",
        mode="artifact",
        artifact_type=None,
        dispatch_target="reporter",
        confidence=0.95,
    )
    assert p.mode == "artifact"
    assert p.dispatch_target == "reporter"
    assert p.artifact_type is None


def test_plan_chat_mode_valid():
    p = Plan(
        intent="clarifying question about the tool",
        mode="chat",
        artifact_type=None,
        dispatch_target="responder",
        confidence=0.8,
    )
    assert p.mode == "chat"
    assert p.dispatch_target == "responder"


def test_plan_confidence_rejects_above_one():
    with pytest.raises(Exception):
        Plan(
            intent="x",
            mode="chat",
            dispatch_target="responder",
            confidence=1.5,
        )


def test_plan_confidence_rejects_below_zero():
    with pytest.raises(Exception):
        Plan(
            intent="x",
            mode="chat",
            dispatch_target="responder",
            confidence=-0.1,
        )


# ---------------------------------------------------------------------------
# AskResponse
# ---------------------------------------------------------------------------


def test_ask_response_chat_mode_has_no_artifact():
    r = AskResponse(
        mode="chat",
        chat_message="I can look up public health statistics.",
        artifact=None,
        meta=AskMeta(
            intent="capability question",
            tools_used=[],
            model="claude-haiku-4-5-20251001",
            timing_ms=42,
        ),
    )
    assert r.mode == "chat"
    assert r.artifact is None
    assert r.chat_message == "I can look up public health statistics."


def test_ask_response_artifact_mode_has_envelope():
    r = AskResponse(
        mode="artifact",
        chat_message="Here is your diabetes report.",
        artifact=ArtifactEnvelope(
            type="report",
            title="Diabetes in Travis County, TX",
            payload={"summary": "Rates are elevated."},
        ),
        meta=AskMeta(
            intent="diabetes statistics",
            tools_used=["tool_get_health_statistics"],
            model="claude-sonnet-4-6",
            timing_ms=1800,
        ),
    )
    assert r.artifact is not None
    assert r.artifact.type == "report"
    assert r.artifact.payload["summary"] == "Rates are elevated."
    assert r.meta.timing_ms == 1800


def test_ask_response_chat_message_always_present():
    """chat_message must be a non-empty string in both modes."""
    r = AskResponse(
        mode="artifact",
        chat_message="Brief teaser text.",
        artifact=ArtifactEnvelope(type="report", title="t", payload={}),
        meta=AskMeta(intent="x", tools_used=[], model="m", timing_ms=0),
    )
    assert isinstance(r.chat_message, str)
    assert len(r.chat_message) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest tests/test_schemas_multi_agent.py -v
```

Expected: `ERROR` — `ImportError: cannot import name 'Plan' from 'pubhealth_llm.app.schemas'`

- [ ] **Step 3: Add the four new models to schemas.py**

Append to `backend/pubhealth_llm/app/schemas.py` after line 214 (after `ComparisonResult`):

```python
# ---------------------------------------------------------------------------
# Multi-agent routing schemas (planner → responder / reporter)
# ---------------------------------------------------------------------------


class Plan(BaseModel):
    """
    Routing decision produced by the planner agent.

    The planner classifies the incoming question and chooses where to send it:
      - mode="chat"     → responder (conversational path)
      - mode="artifact" → run_agent reporter (structured report path)
    """

    intent: str = Field(description="One-phrase description of the user's intent")
    mode: Literal["chat", "artifact"] = Field(
        description="Render surface: 'chat' for conversational, 'artifact' for reports"
    )
    artifact_type: Optional[Literal["report", "comparison", "ranking", "mortality"]] = Field(
        None,
        description="Artifact sub-type when mode='artifact'. None is valid.",
    )
    dispatch_target: Literal["responder", "reporter"] = Field(
        description="'responder' for chat path, 'reporter' for full structured report"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Planner's confidence in this routing decision (0.0–1.0)",
    )


class ArtifactEnvelope(BaseModel):
    """
    Wraps a structured artifact for the frontend artifact panel.

    For type='report', payload is a serialized PublicHealthResponse (model_dump()).
    Other types (comparison, ranking, mortality) carry their own payload shapes
    — defined by future artifact renderers.
    """

    type: str = Field(
        description="Artifact sub-type: 'report', 'comparison', 'ranking', 'mortality'"
    )
    title: str = Field(description="Short title shown in the artifact panel header")
    payload: dict = Field(description="Serialized artifact data")


class AskMeta(BaseModel):
    """Execution metadata attached to every AskResponse."""

    intent: str = Field(description="Classified intent string from the planner")
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tool names called during this request",
    )
    model: str = Field(description="Model(s) used, e.g. 'planner+reporter'")
    timing_ms: int = Field(description="Wall-clock time from request to response")


class AskResponse(BaseModel):
    """
    Envelope returned by run_ask() — the /ask contract.

    chat_message is always present. artifact is present only when mode='artifact'.

    Wire format (JSON):
        {
          "mode": "chat" | "artifact",
          "chat_message": "...",
          "artifact": { "type": "...", "title": "...", "payload": {...} } | null,
          "meta": { "intent": "...", "tools_used": [], "model": "...", "timing_ms": 0 }
        }
    """

    mode: Literal["chat", "artifact"] = Field(
        description="Render surface chosen by the planner"
    )
    chat_message: str = Field(
        description="Always present. For chat: the full response. "
        "For artifact: a one-sentence teaser (first 200 chars of summary)."
    )
    artifact: Optional[ArtifactEnvelope] = Field(
        None,
        description="Present when mode='artifact', null when mode='chat'",
    )
    meta: AskMeta
```

Also add `Literal` to the existing import at the top of schemas.py. The current import is:
```python
from typing import Optional
```
Change it to:
```python
from typing import Literal, Optional
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest tests/test_schemas_multi_agent.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
cd /Volumes/Hub/dev/pubHealthLLM
git add backend/pubhealth_llm/app/schemas.py backend/tests/test_schemas_multi_agent.py
git commit -m "feat: add Plan, ArtifactEnvelope, AskMeta, AskResponse schemas"
```

---

### Task 2: planner.py

**Files:**
- Create: `backend/pubhealth_llm/app/planner.py`
- Create: `backend/tests/test_planner.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_planner.py
"""Tests for pubhealth_llm.app.planner."""
from unittest.mock import AsyncMock, MagicMock, patch

from pubhealth_llm.app.schemas import Plan
from pubhealth_llm.app.planner import _FALLBACK_PLAN, plan_request


def _mock_run(plan: Plan) -> AsyncMock:
    """Return a mock agent whose .run() resolves to the given Plan."""
    mock_result = MagicMock()
    mock_result.output = plan
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=mock_result)
    return mock_agent


_ARTIFACT_PLAN = Plan(
    intent="get diabetes statistics for Travis County TX",
    mode="artifact",
    artifact_type="report",
    dispatch_target="reporter",
    confidence=0.95,
)

_CHAT_PLAN = Plan(
    intent="user asking what the tool can do",
    mode="chat",
    artifact_type=None,
    dispatch_target="responder",
    confidence=0.9,
)


async def test_plan_request_routes_data_question_to_artifact():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_ARTIFACT_PLAN)):
        plan = await plan_request("What is the diabetes rate in Travis County TX?")

    assert plan.mode == "artifact"
    assert plan.dispatch_target == "reporter"
    assert plan.confidence > 0.0


async def test_plan_request_routes_conversational_to_chat():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_CHAT_PLAN)):
        plan = await plan_request("What can this tool do?")

    assert plan.mode == "chat"
    assert plan.dispatch_target == "responder"


async def test_plan_request_falls_back_on_llm_error():
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with patch("pubhealth_llm.app.planner._get_planner", return_value=mock_agent):
        plan = await plan_request("Any question")

    assert plan.dispatch_target == "reporter"
    assert plan.confidence == 0.0
    assert plan.mode == "artifact"


def test_fallback_plan_defaults_to_reporter():
    assert _FALLBACK_PLAN.dispatch_target == "reporter"
    assert _FALLBACK_PLAN.mode == "artifact"
    assert _FALLBACK_PLAN.confidence == 0.0


async def test_plan_request_returns_plan_instance():
    with patch("pubhealth_llm.app.planner._get_planner", return_value=_mock_run(_ARTIFACT_PLAN)):
        plan = await plan_request("Rank counties by obesity in Texas")

    assert isinstance(plan, Plan)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest tests/test_planner.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'pubhealth_llm.app.planner'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest tests/test_planner.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd /Volumes/Hub/dev/pubHealthLLM
git add backend/pubhealth_llm/app/planner.py backend/tests/test_planner.py
git commit -m "feat: add planner agent with heuristic fallback"
```

---

### Task 3: responder.py

**Files:**
- Create: `backend/pubhealth_llm/app/responder.py`
- Create: `backend/tests/test_responder.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_responder.py
"""Tests for pubhealth_llm.app.responder."""
from unittest.mock import AsyncMock, MagicMock, patch

from pubhealth_llm.app.responder import run_responder


def _mock_run(response_text: str) -> MagicMock:
    mock_result = MagicMock()
    mock_result.output = response_text
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=mock_result)
    return mock_agent


async def test_run_responder_returns_string():
    with patch(
        "pubhealth_llm.app.responder._get_responder",
        return_value=_mock_run("This tool helps you look up public health data."),
    ):
        response = await run_responder("What can you do?")

    assert isinstance(response, str)
    assert len(response) > 0


async def test_run_responder_passes_question_to_agent():
    captured = {}

    async def capture_run(question):
        captured["question"] = question
        result = MagicMock()
        result.output = "Response"
        return result

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=capture_run)

    with patch("pubhealth_llm.app.responder._get_responder", return_value=mock_agent):
        await run_responder("How do I use this tool?")

    assert captured["question"] == "How do I use this tool?"


async def test_run_responder_returns_output_as_str():
    """result.output is converted to str even if it's not already one."""
    with patch(
        "pubhealth_llm.app.responder._get_responder",
        return_value=_mock_run("Clarification response here."),
    ):
        result = await run_responder("Can you clarify?")

    assert isinstance(result, str)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest tests/test_responder.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'pubhealth_llm.app.responder'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/pubhealth_llm/app/responder.py
"""
Responder agent — handles conversational / chat-path responses.

The responder answers simple questions about the tool, clarifications,
and any follow-up that does not require data retrieval. It does not
call CDC tools — that is the reporter's job.

Public API:
    message = await run_responder("What can this tool do?")
    # returns a plain string
"""

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
    """Return the responder agent, creating it once on first call."""
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


async def run_responder(question: str) -> str:
    """
    Run the responder agent on a conversational question.

    Args:
        question: The user's question (routed here by the planner).

    Returns:
        Plain text response string.

    Raises:
        Exception: Propagated from PydanticAI on fatal errors.
                   The orchestrator should catch and fall back to the reporter.
    """
    agent = _get_responder()
    result = await agent.run(question)
    return str(result.output)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest tests/test_responder.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
cd /Volumes/Hub/dev/pubHealthLLM
git add backend/pubhealth_llm/app/responder.py backend/tests/test_responder.py
git commit -m "feat: add responder agent for chat-path conversational responses"
```

---

### Task 4: orchestrator.py

**Files:**
- Create: `backend/pubhealth_llm/app/orchestrator.py`
- Create: `backend/tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_orchestrator.py
"""Tests for pubhealth_llm.app.orchestrator — run_ask() routing."""
from unittest.mock import AsyncMock, patch

from pubhealth_llm.app.schemas import (
    AskResponse,
    Plan,
    PublicHealthResponse,
)
from pubhealth_llm.app.orchestrator import run_ask

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CHAT_PLAN = Plan(
    intent="user asking what the tool can do",
    mode="chat",
    artifact_type=None,
    dispatch_target="responder",
    confidence=0.9,
)

_ARTIFACT_PLAN = Plan(
    intent="diabetes statistics in Travis County TX",
    mode="artifact",
    artifact_type="report",
    dispatch_target="reporter",
    confidence=0.95,
)

_MINIMAL_PHR = PublicHealthResponse(
    summary="Diabetes rates in Travis County are elevated at 11.2% of adults.",
    evidence=["Travis County diabetes rate: 11.2% (CDC PLACES 2022)"],
    statistics=[],
    caveats=["Survey-based estimates; may lag 1–2 years."],
    sources=["CDC PLACES 2023, https://www.cdc.gov/places"],
    disclaimer=(
        "This tool provides decision support only. All recommendations "
        "require validation by qualified public health professionals. "
        "Data reflects historical surveillance and may not capture "
        "current conditions."
    ),
)

# ---------------------------------------------------------------------------
# Chat path
# ---------------------------------------------------------------------------


async def test_run_ask_chat_mode_returns_chat_response():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(return_value="This tool looks up public health data."),
        ),
    ):
        response = await run_ask("What can you do?")

    assert response.mode == "chat"
    assert response.artifact is None
    assert response.chat_message == "This tool looks up public health data."
    assert response.meta.intent == _CHAT_PLAN.intent


async def test_run_ask_chat_mode_does_not_call_run_agent():
    run_agent_mock = AsyncMock()
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(return_value="Hi"),
        ),
        patch("pubhealth_llm.app.orchestrator.run_agent", run_agent_mock),
    ):
        await run_ask("Hello")

    run_agent_mock.assert_not_called()

# ---------------------------------------------------------------------------
# Artifact path
# ---------------------------------------------------------------------------


async def test_run_ask_artifact_mode_returns_artifact_response():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
    ):
        response = await run_ask("What is the diabetes rate in Travis County TX?")

    assert response.mode == "artifact"
    assert response.artifact is not None
    assert response.artifact.type == "report"
    assert response.meta.intent == _ARTIFACT_PLAN.intent


async def test_run_ask_artifact_payload_contains_public_health_response():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
    ):
        response = await run_ask("Diabetes in Travis County")

    payload = response.artifact.payload
    assert payload["summary"] == _MINIMAL_PHR.summary
    assert payload["evidence"] == _MINIMAL_PHR.evidence
    assert payload["caveats"] == _MINIMAL_PHR.caveats


async def test_run_ask_artifact_mode_does_not_call_responder():
    responder_mock = AsyncMock()
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
        patch("pubhealth_llm.app.orchestrator.run_responder", responder_mock),
    ):
        await run_ask("County data question")

    responder_mock.assert_not_called()

# ---------------------------------------------------------------------------
# Envelope contract
# ---------------------------------------------------------------------------


async def test_run_ask_chat_message_always_present_in_artifact_mode():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_agent",
            new=AsyncMock(return_value=_MINIMAL_PHR),
        ),
    ):
        response = await run_ask("Any question")

    assert isinstance(response.chat_message, str)
    assert len(response.chat_message) > 0


async def test_run_ask_meta_timing_ms_is_non_negative():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(return_value="Hi"),
        ),
    ):
        response = await run_ask("Hello")

    assert response.meta.timing_ms >= 0


async def test_run_ask_returns_ask_response_instance():
    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_CHAT_PLAN),
        ),
        patch(
            "pubhealth_llm.app.orchestrator.run_responder",
            new=AsyncMock(return_value="Response"),
        ),
    ):
        response = await run_ask("Q")

    assert isinstance(response, AskResponse)


async def test_run_ask_forwards_message_history_to_run_agent():
    run_agent_mock = AsyncMock(return_value=_MINIMAL_PHR)
    history = [{"role": "user", "content": "prior turn"}]

    with (
        patch(
            "pubhealth_llm.app.orchestrator.plan_request",
            new=AsyncMock(return_value=_ARTIFACT_PLAN),
        ),
        patch("pubhealth_llm.app.orchestrator.run_agent", run_agent_mock),
    ):
        await run_ask("Follow-up question", message_history=history)

    run_agent_mock.assert_called_once_with("Follow-up question", message_history=history)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest tests/test_orchestrator.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'pubhealth_llm.app.orchestrator'`

- [ ] **Step 3: Write minimal implementation**

```python
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
    # response.artifact   → ArtifactEnvelope(type="report", ...)
    # response.meta       → AskMeta(intent="...", timing_ms=1234)
"""

import logging
import time
from typing import Optional

from pubhealth_llm.app.agent import run_agent
from pubhealth_llm.app.planner import plan_request
from pubhealth_llm.app.responder import run_responder
from pubhealth_llm.app.schemas import ArtifactEnvelope, AskMeta, AskResponse

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
        chat_message = await run_responder(question)
        timing_ms = int(time.monotonic() * 1000) - start_ms
        return AskResponse(
            mode="chat",
            chat_message=chat_message,
            artifact=None,
            meta=AskMeta(
                intent=plan.intent,
                tools_used=[],
                model="planner+responder",
                timing_ms=timing_ms,
            ),
        )

    # artifact path — full reporter
    pub_health_response = await run_agent(question, message_history=message_history)

    summary = pub_health_response.summary
    teaser = summary[:_TEASER_LENGTH] + "…" if len(summary) > _TEASER_LENGTH else summary

    timing_ms = int(time.monotonic() * 1000) - start_ms
    return AskResponse(
        mode="artifact",
        chat_message=teaser,
        artifact=ArtifactEnvelope(
            type=plan.artifact_type or "report",
            title=plan.intent,
            payload=pub_health_response.model_dump(),
        ),
        meta=AskMeta(
            intent=plan.intent,
            tools_used=[],
            model="planner+reporter",
            timing_ms=timing_ms,
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest tests/test_orchestrator.py -v
```

Expected: `9 passed`

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend
.venv/bin/pytest -v
```

Expected: all previously passing tests still pass; new tests also pass.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/Hub/dev/pubHealthLLM
git add backend/pubhealth_llm/app/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: add orchestrator run_ask() routing planner → responder/reporter"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task that implements it |
|-----------------|------------------------|
| Envelope + Plan schemas | Task 1 |
| Planner — classifies intent, picks render surface | Task 2 |
| Planner — deterministic heuristic fallback if error | Task 2 (`_FALLBACK_PLAN`) |
| Planner — does not re-summarize specialist output | Task 2 system prompt |
| Responder — chat path for simple Q&A | Task 3 |
| Orchestrator `run_ask()` — routes planner → responder OR run_agent | Task 4 |
| Orchestrator — assembles `AskResponse` envelope | Task 4 |
| Test strategy — mock LLM calls, fast offline tests | All test files (unittest.mock) |
| Artifact `type` enum drives frontend renderers | `ArtifactEnvelope.type` field |
| `chat_message` always present | `AskResponse.chat_message` + test |
| `meta` with intent, tools_used, model, timing_ms | `AskMeta` model |

### Notes for `/ask` wiring (next plan)

- `server.py` will add `POST /ask` → `run_ask(body.question, body.message_history)`
- The response is already JSON-serializable via `AskResponse.model_dump()`
- `tools_used` is empty in this plan — a follow-up can populate it by parsing `result.all_messages()` from `agent.run()`
