"""
Tests for run_agent thrash mitigation:
  1. A bounded per-run request_limit (via UsageLimits) — so a non-converging
     agent fails fast (~40s) instead of burning the default 50 round-trips
     (~162s observed in prod) before UsageLimitExceeded.
  2. A single automatic retry on failure — the loop is non-deterministic, so
     one fresh attempt converts most intermittent failures into successes.

All model calls are mocked — no live Bedrock.
"""
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch


@dataclass
class FakeRunResult:
    """Minimal stand-in for a pydantic-ai AgentRunResult."""
    output: object
    _output_tool_name: str = "final_result"

    def new_messages(self):
        return []


def _make_agent(run_side_effect: list):
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=run_side_effect)
    return agent


async def test_run_agent_passes_bounded_request_limit():
    """run_agent must pass usage_limits with a request_limit well below the
    pydantic-ai default of 50, so a thrash is bounded."""
    from pubhealth_llm.app import agent as agent_mod

    ok = FakeRunResult(output=MagicMock(summary="ok"))
    fake_agent = _make_agent([ok])
    with patch.object(agent_mod, "_build_agent", return_value=fake_agent):
        await agent_mod.run_agent("q")

    _, kwargs = fake_agent.run.call_args
    ul = kwargs.get("usage_limits")
    assert ul is not None, "run_agent must pass usage_limits to agent.run"
    assert ul.request_limit == agent_mod._REQUEST_LIMIT
    assert agent_mod._REQUEST_LIMIT <= 20, "request_limit must be bounded below the default 50"


async def test_run_agent_retries_once_then_succeeds():
    """A first-attempt failure followed by a converging retry returns the
    retry's successful response."""
    from pubhealth_llm.app import agent as agent_mod

    ok = FakeRunResult(output=MagicMock(summary="recovered"))
    fake_agent = _make_agent([RuntimeError("thrash"), ok])
    with patch.object(agent_mod, "_build_agent", return_value=fake_agent):
        result = await agent_mod.run_agent("q")

    assert fake_agent.run.call_count == 2
    assert result.response.summary == "recovered"


async def test_run_agent_retries_at_most_once_then_degrades():
    """If both the initial attempt and the single retry fail, run_agent must
    NOT keep retrying — it returns the graceful error response after exactly
    two attempts."""
    from pubhealth_llm.app import agent as agent_mod

    fake_agent = _make_agent([RuntimeError("thrash-1"), RuntimeError("thrash-2")])
    with patch.object(agent_mod, "_build_agent", return_value=fake_agent):
        result = await agent_mod.run_agent("q")

    assert fake_agent.run.call_count == 2
    assert "error" in result.response.summary.lower()
    assert result.tools_used == []


async def test_run_agent_no_retry_on_first_success():
    """A converging first attempt must not trigger a retry."""
    from pubhealth_llm.app import agent as agent_mod

    ok = FakeRunResult(output=MagicMock(summary="fine"))
    fake_agent = _make_agent([ok])
    with patch.object(agent_mod, "_build_agent", return_value=fake_agent):
        result = await agent_mod.run_agent("q")

    assert fake_agent.run.call_count == 1
    assert result.response.summary == "fine"
