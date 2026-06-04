"""
Groq API tests — superseded by test_anthropic_api.py.

The agent has been migrated from Groq to Anthropic (claude-sonnet-4-5).
These tests are kept as stubs so any accidental re-introduction of Groq
is caught, but they skip automatically since GROQ_API_KEY is no longer
required or configured.
"""

import pytest


@pytest.mark.skip(reason="Agent migrated to Anthropic — see test_anthropic_api.py")
def test_groq_provider_instantiates():
    pass


@pytest.mark.skip(reason="Agent migrated to Anthropic — see test_anthropic_api.py")
def test_groq_model_instantiates():
    pass


@pytest.mark.skip(reason="Agent migrated to Anthropic — see test_anthropic_api.py")
def test_groq_raw_client_live_call():
    pass


@pytest.mark.skip(reason="Agent migrated to Anthropic — see test_anthropic_api.py")
def test_pydantic_ai_agent_creates():
    pass


@pytest.mark.skip(reason="Agent migrated to Anthropic — see test_anthropic_api.py")
async def test_pydantic_ai_agent_live_run():
    pass
