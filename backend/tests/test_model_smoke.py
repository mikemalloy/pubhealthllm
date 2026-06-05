"""
Smoke test: one real run_agent() call to verify end-to-end model execution.

This test is SKIPPED by default. It makes a live LLM API call and costs money.
Run it after a model swap to confirm the new model works end-to-end.

To run:
    RUN_SMOKE=1 pytest tests/test_model_smoke.py -v

Or via make:
    RUN_SMOKE=1 make test-smoke   (if make target exists)
"""

import asyncio
import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_SMOKE") != "1",
    reason="Smoke test skipped by default. Set RUN_SMOKE=1 to run.",
)
def test_run_agent_smoke(anthropic_api_key):
    """
    One real run_agent() call. Asserts a valid PublicHealthResponse is returned.
    This is the tripwire after a model swap — if this fails, the model config is broken.
    """
    from pubhealth_llm.app.agent import run_agent
    from pubhealth_llm.app.schemas import PublicHealthResponse

    response = asyncio.run(
        run_agent("What is the obesity rate in Travis County, TX?")
    )

    assert isinstance(response, PublicHealthResponse), (
        f"Expected PublicHealthResponse, got {type(response)}"
    )
    assert response.summary, "Response summary must not be empty"
    assert response.evidence, "Response must have at least one evidence item"
    assert response.sources, "Response must have at least one source"
