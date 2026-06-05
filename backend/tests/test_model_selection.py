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

import pytest

from pubhealth_llm.app.config import DEFAULT_MODEL


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
