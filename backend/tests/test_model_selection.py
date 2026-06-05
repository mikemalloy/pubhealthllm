"""
Tests for model selection in pubHealthLLM.

Covers:
  - SYSTEM_PROMPT content (writing quality section must be present)
  - run_agent() function signature: accepts 'model' kwarg, defaults to None
  - get_model() returns a sensible default and respects PUBHEALTH_MODEL override

No live API calls are made. Tests that build a real agent are gated by
the anthropic_api_key fixture and skipped when the key is absent.
"""

import inspect
import importlib

import pytest


# ---------------------------------------------------------------------------
# 1. System prompt content
# ---------------------------------------------------------------------------


def test_full_prompt_contains_writing_quality_section():
    """SYSTEM_PROMPT must contain the WRITING QUALITY instructions."""
    from pubhealth_llm.app.agent import SYSTEM_PROMPT

    assert "WRITING QUALITY" in SYSTEM_PROMPT, (
        "SYSTEM_PROMPT is missing the WRITING QUALITY section"
    )


# ---------------------------------------------------------------------------
# 2. run_agent() function signature
# ---------------------------------------------------------------------------


def test_run_agent_accepts_model_parameter():
    """run_agent() must accept a 'model' keyword argument."""
    from pubhealth_llm.app.agent import run_agent

    sig = inspect.signature(run_agent)
    assert "model" in sig.parameters, (
        f"run_agent() missing 'model' parameter. Got: {list(sig.parameters.keys())}"
    )


def test_run_agent_model_parameter_defaults_to_none():
    """run_agent()'s 'model' parameter must default to None."""
    from pubhealth_llm.app.agent import run_agent

    sig = inspect.signature(run_agent)
    default = sig.parameters["model"].default
    assert default is None, (
        f"run_agent() 'model' default should be None, got {default!r}"
    )


# ---------------------------------------------------------------------------
# 3. get_model() integration (via agent module's use of config)
# ---------------------------------------------------------------------------


def test_get_model_default_returns_claude_sonnet(monkeypatch):
    """get_model() returns the Claude Sonnet default when PUBHEALTH_MODEL is unset."""
    monkeypatch.delenv("PUBHEALTH_MODEL", raising=False)
    import pubhealth_llm.app.config as cfg
    importlib.reload(cfg)
    assert cfg.get_model() == "anthropic:claude-sonnet-4-6"


def test_get_model_env_override(monkeypatch):
    """get_model() respects PUBHEALTH_MODEL when set."""
    monkeypatch.setenv("PUBHEALTH_MODEL", "openai:gpt-4o-mini")
    import pubhealth_llm.app.config as cfg
    importlib.reload(cfg)
    assert cfg.get_model() == "openai:gpt-4o-mini"


# ---------------------------------------------------------------------------
# 4. _build_agent() — requires ANTHROPIC_API_KEY (skipped if absent)
# ---------------------------------------------------------------------------


def test_build_agent_instantiates(anthropic_api_key):
    """_build_agent() constructs a valid agent for the default Anthropic model."""
    from pubhealth_llm.app.agent import _build_agent

    agent = _build_agent("anthropic:claude-sonnet-4-6")
    assert agent is not None


def test_build_agent_has_eight_tools(anthropic_api_key):
    """Each agent built by _build_agent() must expose all eight tools."""
    from pubhealth_llm.app.agent import _build_agent

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
    agent = _build_agent("anthropic:claude-sonnet-4-6")
    tool_names = set(agent._function_toolset.tools.keys())
    assert tool_names == expected, (
        f"Tool mismatch.\n  Expected: {expected}\n  Got: {tool_names}"
    )


def test_build_agent_invalid_string_raises():
    """_build_agent() raises ValueError for a string missing a colon."""
    from pubhealth_llm.app.agent import _build_agent

    with pytest.raises(ValueError, match="Invalid model string"):
        _build_agent("not-a-valid-model-string")


def test_build_agent_unknown_provider_raises(monkeypatch):
    """_build_agent() raises ValueError for an unsupported provider."""
    monkeypatch.setenv("GROQ_API_KEY", "gk-fake")
    from pubhealth_llm.app.agent import _build_agent

    with pytest.raises(ValueError, match="groq"):
        _build_agent("groq:llama-3.3-70b-versatile")


def test_build_agent_missing_anthropic_key_raises(monkeypatch):
    """_build_agent() raises EnvironmentError when ANTHROPIC_API_KEY is absent."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from pubhealth_llm.app.agent import _build_agent

    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        _build_agent("anthropic:claude-sonnet-4-6")
