"""
PydanticAI elicitation agent for health economic decision tree parameters.

This agent drives a structured multi-turn conversation with a public health
student to collect all parameters required by the Evans decision tree model.
When every parameter has been supplied, it returns a fully-populated
``AnalysisConfig`` that can be passed straight to ``AnalysisConfig.run()``.

Architecture
------------
The agent uses a *discriminated union* output type with two variants:

``Eliciting``
    The agent still needs more information from the student.  The ``message``
    field contains the next question or clarification to display in the chat
    window.

``Complete``
    All parameters have been collected.  The ``config`` field is a fully
    validated ``AnalysisConfig`` ready for ``run()``.  The ``introduction``
    field is a brief sentence to display before the simulation output.

State
-----
No server-side state is maintained.  The full conversation is passed as
``message_history`` on every call, following the same pattern as the
existing ``run_agent()`` function.  The agent reconstructs its understanding
of what has been collected from the conversation history on each turn.

Teaching intent
---------------
The system prompt is written for a public health student audience.  It:
* Names each parameter in clinical language (not Python field names)
* Explains where typical values come from (clinical trials, QoL studies,
  cost databases)
* Uses Evans 1997 values as *reference* examples — not as defaults to copy
* Asks questions in a pedagogically sensible order: efficacy first, then
  what happens when treatment fails, then costs, then utilities
* Never asks about simulation mechanics (n_patients, seed) — those are
  set to sensible defaults and hidden from the student

Public API
----------
``Eliciting``
    Output variant: still collecting.
``Complete``
    Output variant: all parameters ready.
``ElicitationOutput``
    The discriminated union type used as ``output_type`` for the agent.
``SYSTEM_PROMPT``
    The system prompt (exported for testing and inspection).
``get_elicitor_agent(model_key)``
    Return a cached agent for a given model key.
``run_elicitor(user_message, message_history, model_key)``
    Main async entry point called from the Gradio tab.
"""

from __future__ import annotations

import os
from typing import Annotated, Literal, Optional, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from pubhealth_llm.decision_tree.schema import AnalysisConfig

load_dotenv()

# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


class Eliciting(BaseModel):
    """
    The agent needs more information from the student.

    Return this when at least one required parameter has not yet been
    supplied.  The ``message`` field is shown to the student as the
    next question or clarification.
    """

    status: Literal["eliciting"] = "eliciting"
    message: str = Field(
        description=(
            "The next question or clarification to show the student. "
            "Write in plain, friendly language — no Python jargon. "
            "You may ask about multiple related parameters in one message "
            "to keep the conversation efficient."
        )
    )


class Complete(BaseModel):
    """
    All parameters have been collected.

    Return this when every required field across every strategy is known.
    The ``config`` field is a fully-validated ``AnalysisConfig`` that will
    be passed directly to ``AnalysisConfig.run()`` to produce the markdown
    simulation report.
    """

    status: Literal["complete"] = "complete"
    config: AnalysisConfig = Field(
        description=(
            "Fully-populated AnalysisConfig with all strategy parameters, "
            "reference_index, and report settings. "
            "Every field in every StrategySchema must be filled — "
            "do NOT return this status if any parameter is still unknown."
        )
    )
    introduction: str = Field(
        description=(
            "One or two sentences to display above the simulation output. "
            "Briefly confirm what was analysed and tell the student the "
            "results follow below."
        )
    )


ElicitationOutput = Annotated[
    Union[Eliciting, Complete],
    Field(discriminator="status"),
]
"""Discriminated union used as ``output_type`` for the elicitor agent."""


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a health economics teaching assistant helping a public health student
set up and run a decision tree cost-effectiveness analysis using the Evans
acute-treatment model.

## YOUR ROLE

You collect the parameters needed to run the simulation, then hand off to the
simulation engine.  You do NOT run the simulation yourself — you return a
structured data object when collection is complete.

You ask questions in plain clinical language.  You never use Python variable
names like "p_response" in conversation — always use the clinical description.
When a parameter is supplied, confirm it and move on.

## THE EVANS DECISION TREE MODEL

The model compares one or more treatment strategies for an acute health
condition.  Each patient follows exactly one of five paths:

1. Treatment responds → no recurrence within 48 h  (best outcome)
2. Treatment responds → recurrence within 48 h (second dose taken)
3. Treatment fails → patient endures the attack at home
4. Treatment fails → patient visits the ED, is relieved there
5. Treatment fails → patient visits the ED, is hospitalised

Each path has a cost and a quality-of-life utility (QALY weight).

## PARAMETERS YOU MUST COLLECT

For EACH strategy you need all 13 of the following.  Collect them in this
order — it follows the clinical narrative:

### Probabilities (all must be between 0 and 1)

1. **Response rate** — probability that the treatment converts a
   moderate-to-severe episode to mild or none within 2 hours.
   Source: primary endpoint from the treatment's clinical trial.
   Evans reference: 0.558 for sumatriptan, 0.379 for caffeine/ergotamine.

2. **No-recurrence rate** — among patients who responded, the probability
   that the headache does NOT return within 48 hours.
   Source: clinical trial follow-up data.
   Evans reference: 0.558 for both treatments.

3. **Endures-attack rate** — among non-responders, the probability that the
   patient stays home and endures the attack rather than going to the ED.
   Source: published pharmacoeconomic models or expert elicitation.
   Evans reference: 0.917 for both treatments.

4. **ED-relief rate** — among patients who visit the ED, the probability of
   being relieved there (rather than being admitted to hospital).
   Source: hospital administrative data or published models.
   Evans reference: 0.994 for both treatments.

### Costs (must be non-negative, in a consistent currency)

5. **Drug cost** — acquisition cost of one dose of the treatment.
   Source: pharmacy cost database or drug pricing reference.
   Evans reference: Can$16.10 for sumatriptan, Can$1.32 for caffeine/ergotamine.

6. **ED visit cost** — cost of one emergency department visit, excluding
   any hospitalisation.
   Source: local hospital cost or published cost-of-illness study.
   Evans reference: Can$63.16 (same for both treatments).

7. **Hospitalisation cost** — additional cost of in-patient admission,
   on top of the ED visit cost.
   Source: local hospital cost or published DRG/HRG data.
   Evans reference: Can$1,093.00 (same for both treatments).

### Utilities (quality-of-life weights; can be negative for severe states)

Utilities are QALY weights for a 48-hour episode, on a scale from −1 (worst
imaginable health) to +1 (full health).  They come from published preference
studies (e.g. time trade-off or EQ-5D studies for the condition).
Evans reference values for migraine:

8. **Utility: response, no recurrence** — typically 1.0 (full health for the
   episode once the headache resolves and stays resolved).

9. **Utility: response, recurrence** — slightly below perfect health; the
   patient needed a second dose.  Evans: 0.9.

10. **Utility: no response, endures** — severe and disabling; can be
    negative.  Evans: −0.3.

11. **Utility: no response, ED visit (relieved)** — uncomfortable but
    eventually relieved.  Evans: 0.1.

12. **Utility: no response, hospitalised** — most severe outcome; can be
    negative.  Evans: −0.3.

### Analysis metadata (ask once, after all strategies are collected)

13. **Title** — a short title for the analysis report.
    Default: "Health Economic Decision Tree Analysis" (accept if student
    does not specify).

14. **Currency** — what currency are the costs in?  Ask for the symbol
    (e.g. "$", "£", "€", "Can$") and optionally a full description
    (e.g. "1995 Canadian dollars").  Default: "$" with no description.

15. **Reference strategy** — which strategy is the comparator (the one all
    others are compared against)?  Default: the first strategy named.
    Only ask if there are two or more strategies.

## CONVERSATION GUIDELINES

- Start by asking: how many strategies does the student want to compare,
  and what are their names?
- Work through one strategy at a time, collecting all 12 clinical parameters
  before moving to the next strategy.
- You MAY ask about multiple closely-related parameters in a single message
  (e.g. ED cost and hospitalisation cost together, or the four utilities
  together) to keep the conversation efficient.
- Offer the Evans reference values as examples to help the student calibrate
  their own values — but make clear the student should use values appropriate
  to their specific analysis, not just copy Evans.
- When a student provides a value, confirm it explicitly before asking the
  next question.
- If a student provides an implausible value (e.g. a probability > 1, or a
  negative cost), gently flag this and ask them to confirm or correct it.
- After all clinical parameters are collected for all strategies, ask
  about the analysis metadata (title, currency, reference strategy).
- Only set status="complete" when every single required parameter is known.

## WHAT YOU MUST NOT DO

- Do not mention Python, JSON, or variable names in conversation.
- Do not fabricate parameter values — every value must come from the student.
- Do not set status="complete" until ALL parameters for ALL strategies are
  filled, including all 12 clinical parameters and the analysis metadata.
- Do not ask about simulation mechanics (number of patients, random seed) —
  these are fixed at sensible defaults.

## SPECIAL CASE: THE STUDENT PROVIDES A PUBLISHED REFERENCE

If the student says "use the Evans 1997 values" or "use the values from
[paper]", you may populate the parameters from that reference — but confirm
the values with the student before setting status="complete".
"""

# ---------------------------------------------------------------------------
# Agent factory and cache
# ---------------------------------------------------------------------------

_DEFAULT_MODEL_KEY = "anthropic:claude-sonnet-4-6"

_MODEL_MAP: dict[str, tuple[str, str]] = {
    "anthropic:claude-sonnet-4-6":      ("anthropic", "claude-sonnet-4-6"),
    "anthropic:claude-haiku-4":         ("anthropic", "claude-haiku-4-5-20251001"),
    "openai:gpt-4o-mini":               ("openai",    "gpt-4o-mini"),
    "groq:llama-3.3-70b-versatile":     ("groq",      "llama-3.3-70b-versatile"),
    "groq:llama-3.1-8b-instant":        ("groq",      "llama-3.1-8b-instant"),
}

_agent_cache: dict[str, Agent] = {}


def _create_elicitor_agent(model_key: str) -> Agent:
    """
    Instantiate a new elicitor agent for the given model key.

    Parameters
    ----------
    model_key : str
        One of the keys in ``_MODEL_MAP``.

    Returns
    -------
    Agent
        Configured PydanticAI agent with ``ElicitationOutput`` as the
        output type and the Evans parameter-collection system prompt.

    Raises
    ------
    ValueError
        If ``model_key`` is not in ``_MODEL_MAP``.
    EnvironmentError
        If the required API key environment variable is not set.
    """
    if model_key not in _MODEL_MAP:
        raise ValueError(
            f"Unknown model key {model_key!r}. "
            f"Valid options: {list(_MODEL_MAP)}"
        )

    provider, api_model_id = _MODEL_MAP[model_key]

    if provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider
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
        raise ValueError(f"Unknown provider {provider!r}")

    return Agent(
        model=model,
        output_type=ElicitationOutput,
        system_prompt=SYSTEM_PROMPT,
    )


def get_elicitor_agent(model_key: str = _DEFAULT_MODEL_KEY) -> Agent:
    """
    Return a cached elicitor agent for the given model key.

    Agents are heavyweight objects (they hold the model connection and schema).
    Each unique model key creates one agent at most.

    Parameters
    ----------
    model_key : str
        Model key from ``_MODEL_MAP``.  Defaults to
        ``"anthropic:claude-sonnet-4-6"``.

    Returns
    -------
    Agent
    """
    if model_key not in _agent_cache:
        _agent_cache[model_key] = _create_elicitor_agent(model_key)
    return _agent_cache[model_key]


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------


async def run_elicitor(
    user_message: str,
    message_history: Optional[list] = None,
    model_key: str = _DEFAULT_MODEL_KEY,
) -> tuple[str, list]:
    """
    Advance the elicitation conversation by one turn.

    Called from the Gradio Decision Tree tab each time the student sends
    a message.  Passes the full conversation history to the agent so it
    can reconstruct what has already been collected.

    When the agent returns ``status="eliciting"``, the next question is
    returned to the chat window.  When the agent returns ``status="complete"``,
    the simulation is run immediately and the formatted markdown report is
    returned.

    Parameters
    ----------
    user_message : str
        The student's latest message.
    message_history : list or None
        PydanticAI message history from all previous turns.  Pass ``None``
        or ``[]`` to start a new conversation.
    model_key : str
        Model to use for this elicitation session.

    Returns
    -------
    response_text : str
        Either the agent's next question (while eliciting) or the full
        markdown simulation report (when complete).
    updated_history : list
        Updated PydanticAI message history including this turn.  Store in
        Gradio state and pass back on the next call.

    Raises
    ------
    EnvironmentError
        If the required API key is not set.
    ScriptExecutionError
        If the generated simulation script exits with a non-zero return code.
    subprocess.TimeoutExpired
        If the simulation exceeds 120 seconds.
    """
    agent = get_elicitor_agent(model_key)
    result = await agent.run(
        user_message,
        message_history=message_history or [],
    )
    output: ElicitationOutput = result.output

    if isinstance(output, Eliciting):
        return output.message, result.all_messages()

    # status == "complete" — run the simulation pipeline
    markdown = output.config.run()
    full_response = f"{output.introduction}\n\n{markdown}"
    return full_response, result.all_messages()
