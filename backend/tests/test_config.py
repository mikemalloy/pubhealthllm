"""
Tests for pubhealth_llm.app.config — model configuration and validation.

All tests use monkeypatch — no real env vars, no network calls.
"""

import pytest

from pubhealth_llm.app.config import DEFAULT_MODEL


# ---------------------------------------------------------------------------
# get_model()
# ---------------------------------------------------------------------------


def test_get_model_default_when_unset(monkeypatch):
    """get_model() returns the Bedrock Nova Pro default when PUBHEALTH_MODEL is unset."""
    monkeypatch.delenv("PUBHEALTH_MODEL", raising=False)
    import pubhealth_llm.app.config as cfg
    assert cfg.get_model() == DEFAULT_MODEL


def test_get_model_override(monkeypatch):
    """get_model() respects the PUBHEALTH_MODEL env var when set."""
    monkeypatch.setenv("PUBHEALTH_MODEL", "openai:gpt-4o-mini")
    import pubhealth_llm.app.config as cfg
    assert cfg.get_model() == "openai:gpt-4o-mini"


# ---------------------------------------------------------------------------
# validate_model_config()
# ---------------------------------------------------------------------------


def test_validate_model_config_valid_anthropic(monkeypatch):
    """validate_model_config() passes for a valid anthropic string with key set."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from pubhealth_llm.app.config import validate_model_config
    validate_model_config("anthropic:claude-sonnet-4-6")  # must not raise


def test_validate_model_config_unknown_provider(monkeypatch):
    """validate_model_config() raises for an unknown provider (groq is dropped)."""
    monkeypatch.setenv("GROQ_API_KEY", "gk-test")
    from pubhealth_llm.app.config import validate_model_config
    with pytest.raises(ValueError, match="not supported"):
        validate_model_config("groq:llama-3.3-70b-versatile")


def test_validate_model_config_missing_key(monkeypatch):
    """validate_model_config() raises EnvironmentError when API key is absent."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from pubhealth_llm.app.config import validate_model_config
    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        validate_model_config("anthropic:claude-sonnet-4-6")


def test_validate_model_config_none_uses_default(monkeypatch):
    """validate_model_config(None) falls back to get_model() and does not raise."""
    monkeypatch.delenv("PUBHEALTH_MODEL", raising=False)
    from pubhealth_llm.app.config import validate_model_config
    validate_model_config(None)  # must not raise


# ---------------------------------------------------------------------------
# Bedrock provider tests
# ---------------------------------------------------------------------------


def test_bedrock_in_allowed_providers():
    """'bedrock' must be in ALLOWED_PROVIDERS."""
    from pubhealth_llm.app.config import ALLOWED_PROVIDERS
    assert "bedrock" in ALLOWED_PROVIDERS


def test_default_model_is_bedrock():
    """DEFAULT_MODEL must start with 'bedrock:'."""
    from pubhealth_llm.app.config import DEFAULT_MODEL
    assert DEFAULT_MODEL.startswith("bedrock:")


def test_validate_bedrock_needs_no_api_key(monkeypatch):
    """validate_model_config must NOT raise EnvironmentError for bedrock."""
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from pubhealth_llm.app.config import validate_model_config
    # Should not raise — bedrock uses IAM, no key required
    validate_model_config("bedrock:us.amazon.nova-pro-v1:0")


def test_validate_anthropic_still_requires_key(monkeypatch):
    """Anthropic provider still requires ANTHROPIC_API_KEY."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from pubhealth_llm.app.config import validate_model_config
    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        validate_model_config("anthropic:claude-sonnet-4-6")


def test_validate_unknown_provider_raises():
    """Unknown provider raises ValueError."""
    from pubhealth_llm.app.config import validate_model_config
    with pytest.raises(ValueError, match="not supported"):
        validate_model_config("groq:mixtral")
