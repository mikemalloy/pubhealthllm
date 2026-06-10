"""
Smoke test: one real run_agent() call to verify end-to-end model execution.

Gated by:
- bedrock_available fixture (AWS IAM credentials must be configured)
- aurora_db fixture (Aurora cluster must be reachable)
- pytest -m slow (excluded from default runs — makes a live LLM API call)

To run:
    pytest tests/test_model_smoke.py -v -m slow

This is the tripwire after a model swap: if this fails, the model + data
pipeline integration is broken.
"""

import asyncio
import pytest


@pytest.mark.slow
def test_run_agent_smoke(bedrock_available, aurora_db):
    """
    One real run_agent() call via Bedrock Nova Pro + Aurora.
    Asserts a valid PublicHealthResponse is returned.
    This is the tripwire after a model swap — if this fails, the model config is broken.
    """
    from pubhealth_llm.app.agent import run_agent, AgentResult
    from pubhealth_llm.app.schemas import PublicHealthResponse

    agent_result = asyncio.run(
        run_agent("What is the obesity rate in Travis County, TX?")
    )

    assert isinstance(agent_result, AgentResult), (
        f"Expected AgentResult, got {type(agent_result)}"
    )
    response = agent_result.response
    assert isinstance(response, PublicHealthResponse), (
        f"Expected PublicHealthResponse, got {type(response)}"
    )
    assert response.summary, "Response summary must not be empty"
    assert response.evidence, "Response must have at least one evidence item"
    assert response.sources, "Response must have at least one source"
    assert "error" not in response.summary.lower(), (
        f"Agent returned error response: {response.summary[:200]}"
    )
