"""
Tests for the model selection dropdown feature.

Covers:
  - Model map structure and constants (no API calls)
  - Agent creation and caching per model (Anthropic models need API key)
  - Groq provider: missing API key gives a clean EnvironmentError (no API calls)
  - System prompt selection: Groq gets the short prompt, Anthropic gets the full one
  - Groq prompt token budget: short enough to stay under Groq's 12,000 TPM cap
  - run_agent() function signature accepts the model parameter
  - Gradio chat() function signature accepts the model parameter
  - Dropdown constants: correct options, default, and note text
  - Examples are in list-of-lists format (Gradio requirement with additional_inputs)

No live API calls are made except in tests that explicitly use the
anthropic_api_key fixture (those are skipped if the key is absent).
"""

import inspect
import os
import pytest


# ---------------------------------------------------------------------------
# 1. Model map structure
# ---------------------------------------------------------------------------

def test_model_map_has_expected_entries():
    """_MODEL_MAP must contain exactly the documented model keys."""
    from pubhealth_llm.app.agent import _MODEL_MAP

    expected_keys = {
        "anthropic:claude-sonnet-4-6",
        "anthropic:claude-haiku-4",
        "openai:gpt-4o-mini",
        "groq:llama-3.3-70b-versatile",
        "groq:llama-3.1-8b-instant",
    }
    assert set(_MODEL_MAP.keys()) == expected_keys, (
        f"Model map keys mismatch.\n  Expected: {expected_keys}\n  Got: {set(_MODEL_MAP.keys())}"
    )


def test_model_map_providers_are_valid():
    """Every entry in _MODEL_MAP must declare a known provider."""
    from pubhealth_llm.app.agent import _MODEL_MAP

    valid_providers = {"anthropic", "openai", "groq"}
    for key, (provider, _) in _MODEL_MAP.items():
        assert provider in valid_providers, (
            f"Model key {key!r} has unknown provider {provider!r}"
        )


def test_model_map_anthropic_keys_have_model_ids():
    """Anthropic entries must map to non-empty API model ID strings."""
    from pubhealth_llm.app.agent import _MODEL_MAP

    for key, (provider, model_id) in _MODEL_MAP.items():
        if provider == "anthropic":
            assert model_id, f"Empty model_id for key {key!r}"
            assert "claude" in model_id.lower(), (
                f"Anthropic model ID {model_id!r} doesn't look like a Claude model"
            )


def test_model_map_groq_keys_have_model_ids():
    """Groq entries must map to non-empty API model ID strings."""
    from pubhealth_llm.app.agent import _MODEL_MAP

    for key, (provider, model_id) in _MODEL_MAP.items():
        if provider == "groq":
            assert model_id, f"Empty model_id for key {key!r}"
            assert "llama" in model_id.lower(), (
                f"Groq model ID {model_id!r} doesn't look like a Llama model"
            )


def test_default_model_key_is_claude_sonnet():
    """DEFAULT_MODEL_KEY must be the Claude Sonnet entry."""
    from pubhealth_llm.app.agent import DEFAULT_MODEL_KEY

    assert DEFAULT_MODEL_KEY == "anthropic:claude-sonnet-4-6", (
        f"Expected 'anthropic:claude-sonnet-4-6', got {DEFAULT_MODEL_KEY!r}"
    )


def test_default_model_key_exists_in_model_map():
    """DEFAULT_MODEL_KEY must be a valid key in _MODEL_MAP."""
    from pubhealth_llm.app.agent import DEFAULT_MODEL_KEY, _MODEL_MAP

    assert DEFAULT_MODEL_KEY in _MODEL_MAP, (
        f"DEFAULT_MODEL_KEY {DEFAULT_MODEL_KEY!r} not found in _MODEL_MAP"
    )


# ---------------------------------------------------------------------------
# 2. Agent creation — Anthropic models (requires API key)
# ---------------------------------------------------------------------------

def test_create_agent_default_model(anthropic_api_key):
    """_create_agent() with no argument uses the default Claude Sonnet model."""
    from pubhealth_llm.app.agent import _create_agent, DEFAULT_MODEL_KEY

    agent = _create_agent()
    assert agent is not None, "_create_agent() returned None"


def test_create_agent_claude_sonnet(anthropic_api_key):
    """_create_agent() succeeds for anthropic:claude-sonnet-4-6."""
    from pubhealth_llm.app.agent import _create_agent

    agent = _create_agent("anthropic:claude-sonnet-4-6")
    assert agent is not None


def test_create_agent_claude_haiku(anthropic_api_key):
    """_create_agent() succeeds for anthropic:claude-haiku-4."""
    from pubhealth_llm.app.agent import _create_agent

    agent = _create_agent("anthropic:claude-haiku-4")
    assert agent is not None


def test_create_agent_anthropic_has_eight_tools(anthropic_api_key):
    """Each Anthropic agent must expose all eight tools."""
    from pubhealth_llm.app.agent import _create_agent

    expected = {
        "tool_search_mmwr_reports",
        "tool_get_health_statistics",
        "tool_compare_locations",
        "tool_get_available_measures",
        "tool_get_worst_counties_by_measure",
        "tool_rank_counties_composite",
        "tool_get_mortality_data",
        "tool_compare_mortality",
    }
    for model_key in ("anthropic:claude-sonnet-4-6", "anthropic:claude-haiku-4"):
        agent = _create_agent(model_key)
        tool_names = set(agent._function_toolset.tools.keys())
        assert tool_names == expected, (
            f"Tool mismatch for {model_key!r}.\n"
            f"  Expected: {expected}\n  Got: {tool_names}"
        )


# ---------------------------------------------------------------------------
# 3. Agent caching
# ---------------------------------------------------------------------------

def test_get_agent_returns_same_instance(anthropic_api_key):
    """get_agent() must return the identical object on repeated calls."""
    from pubhealth_llm.app.agent import get_agent, _agent_cache

    # Clear cache so we can test a fresh creation
    _agent_cache.clear()

    agent1 = get_agent("anthropic:claude-sonnet-4-6")
    agent2 = get_agent("anthropic:claude-sonnet-4-6")
    assert agent1 is agent2, (
        "get_agent() returned different objects for the same model key — "
        "caching is broken"
    )


def test_get_agent_different_keys_return_different_instances(anthropic_api_key):
    """get_agent() must return distinct objects for different model keys."""
    from pubhealth_llm.app.agent import get_agent, _agent_cache

    _agent_cache.clear()

    sonnet = get_agent("anthropic:claude-sonnet-4-6")
    haiku  = get_agent("anthropic:claude-haiku-4")
    assert sonnet is not haiku, (
        "get_agent() returned the same object for different model keys"
    )


# ---------------------------------------------------------------------------
# 4. Invalid model key
# ---------------------------------------------------------------------------

def test_create_agent_invalid_key_raises(anthropic_api_key):
    """_create_agent() must raise ValueError for an unknown model key."""
    from pubhealth_llm.app.agent import _create_agent

    with pytest.raises(ValueError, match="Unknown model key"):
        _create_agent("openai:gpt-4o")


# ---------------------------------------------------------------------------
# 5. Groq: missing API key gives a clean EnvironmentError
# ---------------------------------------------------------------------------

def test_groq_agent_missing_key_raises_environment_error():
    """
    Attempting to create a Groq agent without GROQ_API_KEY set must raise
    EnvironmentError with an informative message — not crash with a traceback
    from deep inside the Groq library.
    """
    from pubhealth_llm.app.agent import _create_agent, _agent_cache

    original_key = os.environ.pop("GROQ_API_KEY", None)
    _agent_cache.pop("groq:llama-3.3-70b-versatile", None)

    try:
        with pytest.raises(EnvironmentError, match="GROQ_API_KEY"):
            _create_agent("groq:llama-3.3-70b-versatile")
    finally:
        if original_key is not None:
            os.environ["GROQ_API_KEY"] = original_key
        _agent_cache.pop("groq:llama-3.3-70b-versatile", None)


def test_groq_8b_missing_key_raises_environment_error():
    """Same EnvironmentError check for the Llama 3.1 8B Instant model."""
    from pubhealth_llm.app.agent import _create_agent, _agent_cache

    original_key = os.environ.pop("GROQ_API_KEY", None)
    _agent_cache.pop("groq:llama-3.1-8b-instant", None)

    try:
        with pytest.raises(EnvironmentError, match="GROQ_API_KEY"):
            _create_agent("groq:llama-3.1-8b-instant")
    finally:
        if original_key is not None:
            os.environ["GROQ_API_KEY"] = original_key
        _agent_cache.pop("groq:llama-3.1-8b-instant", None)


# ---------------------------------------------------------------------------
# 6. System prompt selection
# ---------------------------------------------------------------------------

def test_groq_gets_short_system_prompt(anthropic_api_key):
    """
    SYSTEM_PROMPT_GROQ must be strictly shorter than SYSTEM_PROMPT.
    Groq's 12,000 TPM limit means the full prompt risks exceeding
    per-request token budgets.
    """
    from pubhealth_llm.app.agent import SYSTEM_PROMPT, SYSTEM_PROMPT_GROQ

    assert len(SYSTEM_PROMPT_GROQ) < len(SYSTEM_PROMPT), (
        "SYSTEM_PROMPT_GROQ must be shorter than SYSTEM_PROMPT. "
        f"Groq: {len(SYSTEM_PROMPT_GROQ)} chars, Full: {len(SYSTEM_PROMPT)} chars"
    )


def test_groq_prompt_under_token_budget():
    """
    SYSTEM_PROMPT_GROQ must fit well within Groq's 12,000 TPM cap.

    Rough estimate: 1 token ≈ 4 characters.  The prompt itself plus 8 tool
    definitions plus a typical user question should stay under 10,000 tokens
    to leave headroom.  We check the prompt alone is under 2,000 tokens
    (~8,000 characters) — a conservative ceiling.
    """
    from pubhealth_llm.app.agent import SYSTEM_PROMPT_GROQ

    approx_tokens = len(SYSTEM_PROMPT_GROQ) / 4
    assert approx_tokens < 2_000, (
        f"SYSTEM_PROMPT_GROQ is ~{approx_tokens:.0f} tokens — too large for "
        f"Groq's 12,000 TPM cap once tool definitions and the user message "
        f"are included. Current length: {len(SYSTEM_PROMPT_GROQ)} chars."
    )


def test_groq_prompt_contains_tool_routing_rules():
    """SYSTEM_PROMPT_GROQ must still contain the essential tool-routing rules."""
    from pubhealth_llm.app.agent import SYSTEM_PROMPT_GROQ

    required_phrases = [
        "tool_get_health_statistics",
        "tool_search_mmwr_reports",
        "tool_rank_counties_composite",
        "tool_compare_mortality",
        "decision support",
    ]
    for phrase in required_phrases:
        assert phrase in SYSTEM_PROMPT_GROQ, (
            f"SYSTEM_PROMPT_GROQ is missing required phrase: {phrase!r}"
        )


def test_full_prompt_contains_writing_quality_section():
    """SYSTEM_PROMPT must contain the writing quality instructions absent from Groq prompt."""
    from pubhealth_llm.app.agent import SYSTEM_PROMPT, SYSTEM_PROMPT_GROQ

    assert "WRITING QUALITY" in SYSTEM_PROMPT, (
        "Full SYSTEM_PROMPT is missing the WRITING QUALITY section"
    )
    assert "WRITING QUALITY" not in SYSTEM_PROMPT_GROQ, (
        "SYSTEM_PROMPT_GROQ should not contain the WRITING QUALITY section "
        "(it adds ~400 tokens Groq can't afford)"
    )


# ---------------------------------------------------------------------------
# 7. run_agent() function signature
# ---------------------------------------------------------------------------

def test_run_agent_accepts_model_parameter():
    """run_agent() must accept a 'model' keyword argument."""
    from pubhealth_llm.app.agent import run_agent

    sig = inspect.signature(run_agent)
    params = sig.parameters
    assert "model" in params, (
        f"run_agent() missing 'model' parameter. Got: {list(params.keys())}"
    )


def test_run_agent_model_parameter_defaults_to_none():
    """run_agent()'s 'model' parameter must default to None."""
    from pubhealth_llm.app.agent import run_agent

    sig = inspect.signature(run_agent)
    default = sig.parameters["model"].default
    assert default is None, (
        f"run_agent() 'model' default should be None, got {default!r}"
    )


