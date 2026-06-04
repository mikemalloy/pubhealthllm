"""
Tests for Anthropic API connectivity and PydanticAI model/provider setup.

These tests make real network calls to the Anthropic API to verify
the key is valid and the model responds. They are skipped if
ANTHROPIC_API_KEY is not set.
"""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")


def test_anthropic_provider_instantiates(anthropic_api_key):
    """AnthropicProvider accepts api_key without raising."""
    from pydantic_ai.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key=anthropic_api_key)
    assert provider is not None


def test_anthropic_model_instantiates(anthropic_api_key):
    """AnthropicModel accepts model name + AnthropicProvider without raising."""
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key=anthropic_api_key)
    model = AnthropicModel("claude-sonnet-4-5", provider=provider)
    assert model is not None


def test_anthropic_raw_client_live_call(anthropic_api_key):
    """
    Make a minimal live call to Anthropic using the raw anthropic client.

    This verifies the API key is accepted and the endpoint responds —
    without going through PydanticAI, so failures here point directly
    to the key or network rather than the agent framework.

    FAILS WITH 401: Your ANTHROPIC_API_KEY is invalid.
    Anthropic keys start with 'sk-ant-'. Get one at https://console.anthropic.com
    """
    import anthropic

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the single word: healthy"}],
        )
    except anthropic.AuthenticationError:
        pytest.fail(
            "Anthropic API rejected your key (401 Unauthorized).\n"
            f"  Key in .env starts with: {anthropic_api_key[:12]}...\n"
            "  Anthropic keys must start with 'sk-ant-'.\n"
            "  Get a key at: https://console.anthropic.com"
        )
    assert message.content, "Anthropic API returned no content"
    text = message.content[0].text.strip()
    assert len(text) > 0, "Anthropic API returned an empty response"


def test_pydantic_ai_agent_creates(anthropic_api_key):
    """
    PydanticAI Agent instantiates correctly with output_type and AnthropicProvider.

    Validates that our agent.py _create_agent() logic works with the
    installed version of pydantic-ai.
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
    from pydantic import BaseModel

    class _TestOutput(BaseModel):
        answer: str

    provider = AnthropicProvider(api_key=anthropic_api_key)
    model = AnthropicModel("claude-sonnet-4-5", provider=provider)
    agent = Agent(model=model, output_type=_TestOutput, system_prompt="You are a test agent.")
    assert agent is not None


@pytest.mark.asyncio
async def test_pydantic_ai_agent_live_run(anthropic_api_key):
    """
    End-to-end: PydanticAI agent makes a live Anthropic call and returns
    a validated structured output.

    This is the closest proxy to what happens when a user submits a
    question in the Gradio interface.
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
    from pydantic import BaseModel

    class _HealthFact(BaseModel):
        fact: str
        confidence: str

    provider = AnthropicProvider(api_key=anthropic_api_key)
    model = AnthropicModel("claude-sonnet-4-5", provider=provider)
    agent = Agent(
        model=model,
        output_type=_HealthFact,
        system_prompt="Return a simple public health fact.",
    )

    result = await agent.run("Name one well-known public health fact about hand washing.")

    output = result.output
    assert isinstance(output, _HealthFact), f"Expected _HealthFact, got {type(output)}"
    assert output.fact, "fact field is empty"
    assert output.confidence, "confidence field is empty"
