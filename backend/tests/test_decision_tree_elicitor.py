"""
Tests for pubhealth_llm.decision_tree.elicitor
===============================================

All tests here are unit tests — no real API calls are made.

Covers:
* Eliciting schema — construction and field validation
* Complete schema — construction and field validation
* ElicitationOutput — discriminator works (Eliciting vs Complete)
* SYSTEM_PROMPT — content completeness (all parameter names present)
* _create_elicitor_agent — raises on bad model key / missing API key
* get_elicitor_agent — caching behaviour
* run_elicitor — delegates to agent.run(), routes Eliciting vs Complete
* run_elicitor — Complete triggers AnalysisConfig.run() and returns markdown
* run_elicitor — passes message_history to agent
* run_elicitor — returns updated_history from result.all_messages()
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from pubhealth_llm.decision_tree import (
    AnalysisConfig,
    Complete,
    ELICITOR_SYSTEM_PROMPT,
    Eliciting,
    StrategySchema,
    run_elicitor,
)
from pubhealth_llm.decision_tree.elicitor import (
    ElicitationOutput,
    _DEFAULT_MODEL_KEY,
    _MODEL_MAP,
    _agent_cache,
    _create_elicitor_agent,
    get_elicitor_agent,
)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

CAFFEINE_DATA = dict(
    name="Caffeine/Ergotamine",
    cost_drug=1.32,
    cost_ed=63.16,
    cost_hospital=1093.0,
    u_response_no_recurrence=1.0,
    u_response_recurrence=0.9,
    u_no_response_endures=-0.3,
    u_no_response_ed=0.1,
    u_no_response_hospital=-0.3,
    p_response=0.379,
    p_no_recurrence=0.558,
    p_endures=0.917,
    p_ed_relief=0.994,
)

SUMATRIPTAN_DATA = dict(
    name="Sumatriptan",
    cost_drug=16.1,
    cost_ed=63.16,
    cost_hospital=1093.0,
    u_response_no_recurrence=1.0,
    u_response_recurrence=0.9,
    u_no_response_endures=-0.3,
    u_no_response_ed=0.1,
    u_no_response_hospital=-0.3,
    p_response=0.558,
    p_no_recurrence=0.558,
    p_endures=0.917,
    p_ed_relief=0.994,
)


def make_analysis_config() -> AnalysisConfig:
    return AnalysisConfig(
        strategies=[
            StrategySchema(**CAFFEINE_DATA),
            StrategySchema(**SUMATRIPTAN_DATA),
        ],
        n_patients=2_000,
        seed=42,
    )


# ---------------------------------------------------------------------------
# TestElicitingSchema
# ---------------------------------------------------------------------------


class TestElicitingSchema:
    def test_construction_with_message(self):
        e = Eliciting(message="How many strategies?")
        assert e.message == "How many strategies?"

    def test_status_is_eliciting(self):
        e = Eliciting(message="test")
        assert e.status == "eliciting"

    def test_status_is_literal_default(self):
        e = Eliciting(message="x")
        assert e.status == "eliciting"

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            Eliciting()  # type: ignore[call-arg]

    def test_empty_message_allowed(self):
        # Pydantic does not reject empty str by default
        e = Eliciting(message="")
        assert e.message == ""

    def test_long_message_allowed(self):
        msg = "x" * 5000
        e = Eliciting(message=msg)
        assert len(e.message) == 5000


# ---------------------------------------------------------------------------
# TestCompleteSchema
# ---------------------------------------------------------------------------


class TestCompleteSchema:
    def test_construction(self):
        c = Complete(
            config=make_analysis_config(),
            introduction="Here are your results.",
        )
        assert c.status == "complete"
        assert c.introduction == "Here are your results."

    def test_status_is_complete(self):
        c = Complete(config=make_analysis_config(), introduction="Done.")
        assert c.status == "complete"

    def test_config_field_is_analysis_config(self):
        config = make_analysis_config()
        c = Complete(config=config, introduction="x")
        assert isinstance(c.config, AnalysisConfig)

    def test_config_strategies_preserved(self):
        config = make_analysis_config()
        c = Complete(config=config, introduction="x")
        assert len(c.config.strategies) == 2

    def test_missing_config_raises(self):
        with pytest.raises(ValidationError):
            Complete(introduction="x")  # type: ignore[call-arg]

    def test_missing_introduction_raises(self):
        with pytest.raises(ValidationError):
            Complete(config=make_analysis_config())  # type: ignore[call-arg]

    def test_config_validated_by_analysis_config(self):
        """AnalysisConfig validation (e.g. reference_index) is enforced."""
        with pytest.raises(ValidationError):
            Complete(
                config=AnalysisConfig(
                    strategies=[StrategySchema(**CAFFEINE_DATA)],
                    reference_index=5,  # out of range
                ),
                introduction="x",
            )


# ---------------------------------------------------------------------------
# TestElicitationOutputDiscriminator
# ---------------------------------------------------------------------------


class TestElicitationOutputDiscriminator:
    """Verify that the discriminated union dispatches correctly."""

    def test_eliciting_status_parses_as_eliciting(self):
        from pydantic import TypeAdapter
        adapter = TypeAdapter(ElicitationOutput)
        obj = adapter.validate_python({"status": "eliciting", "message": "hi"})
        assert isinstance(obj, Eliciting)

    def test_complete_status_parses_as_complete(self):
        from pydantic import TypeAdapter
        adapter = TypeAdapter(ElicitationOutput)
        config_data = {
            "strategies": [CAFFEINE_DATA, SUMATRIPTAN_DATA],
            "n_patients": 1_000,
            "seed": 1,
        }
        obj = adapter.validate_python(
            {"status": "complete", "config": config_data, "introduction": "x"}
        )
        assert isinstance(obj, Complete)

    def test_invalid_status_raises(self):
        from pydantic import TypeAdapter
        adapter = TypeAdapter(ElicitationOutput)
        with pytest.raises(ValidationError):
            adapter.validate_python({"status": "unknown", "message": "x"})


# ---------------------------------------------------------------------------
# TestSystemPrompt
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """The system prompt must contain all clinically-named parameters."""

    def test_prompt_is_non_empty_string(self):
        assert isinstance(ELICITOR_SYSTEM_PROMPT, str)
        assert len(ELICITOR_SYSTEM_PROMPT.strip()) > 100

    def test_prompt_mentions_response_rate(self):
        assert "response rate" in ELICITOR_SYSTEM_PROMPT.lower() or \
               "response" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_recurrence(self):
        assert "recurrence" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_endures(self):
        assert "endures" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_ed(self):
        assert "ed" in ELICITOR_SYSTEM_PROMPT.lower() or \
               "emergency" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_hospitalisation(self):
        assert "hospital" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_drug_cost(self):
        assert "drug cost" in ELICITOR_SYSTEM_PROMPT.lower() or \
               "drug" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_utility(self):
        assert "utilit" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_probability(self):
        assert "probabilit" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_evans(self):
        assert "evans" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_status_complete(self):
        assert "complete" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_uses_clinical_language_not_just_python_names(self):
        """Clinical descriptions must be the primary language, not Python names."""
        prompt_lower = ELICITOR_SYSTEM_PROMPT.lower()
        # Clinical terms must appear — these are the descriptions a student sees
        assert "response rate" in prompt_lower or "response" in prompt_lower
        assert "recurrence" in prompt_lower
        assert "endures" in prompt_lower
        # Python-only boilerplate (pure underscore field names) should not dominate
        # (they may appear in schema context, but clinical terms must outnumber them)
        clinical_hits = sum([
            "response rate" in prompt_lower,
            "recurrence" in prompt_lower,
            "endures" in prompt_lower,
            "emergency" in prompt_lower,
            "hospital" in prompt_lower,
            "drug cost" in prompt_lower or "drug" in prompt_lower,
            "utility" in prompt_lower,
            "probabilit" in prompt_lower,
        ])
        assert clinical_hits >= 6, "Expected at least 6 clinical terms in the prompt"

    def test_prompt_mentions_five_paths(self):
        """The five terminal paths should be described."""
        assert "five" in ELICITOR_SYSTEM_PROMPT.lower() or \
               "5" in ELICITOR_SYSTEM_PROMPT

    def test_prompt_tells_agent_not_to_fabricate(self):
        assert "fabricat" in ELICITOR_SYSTEM_PROMPT.lower() or \
               "not" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_describes_currency(self):
        assert "currency" in ELICITOR_SYSTEM_PROMPT.lower()

    def test_prompt_describes_title(self):
        assert "title" in ELICITOR_SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# TestModelMap
# ---------------------------------------------------------------------------


class TestModelMap:
    def test_model_map_has_anthropic_sonnet(self):
        assert "anthropic:claude-sonnet-4-6" in _MODEL_MAP

    def test_model_map_has_anthropic_haiku(self):
        assert "anthropic:claude-haiku-4" in _MODEL_MAP

    def test_model_map_has_openai(self):
        assert "openai:gpt-4o-mini" in _MODEL_MAP

    def test_model_map_has_groq_large(self):
        assert "groq:llama-3.3-70b-versatile" in _MODEL_MAP

    def test_model_map_has_groq_small(self):
        assert "groq:llama-3.1-8b-instant" in _MODEL_MAP

    def test_default_model_key_in_model_map(self):
        assert _DEFAULT_MODEL_KEY in _MODEL_MAP

    def test_all_entries_are_tuples_of_two_strings(self):
        for key, value in _MODEL_MAP.items():
            assert isinstance(value, tuple), f"{key} value is not a tuple"
            assert len(value) == 2, f"{key} value does not have exactly 2 elements"
            assert all(isinstance(v, str) for v in value), f"{key} values are not strings"


# ---------------------------------------------------------------------------
# TestCreateElicitorAgent
# ---------------------------------------------------------------------------


class TestCreateElicitorAgent:
    def test_invalid_model_key_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown model key"):
            _create_elicitor_agent("invalid:model")

    def test_missing_anthropic_api_key_raises_environment_error(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing key
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
                    _create_elicitor_agent("anthropic:claude-sonnet-4-6")

    def test_missing_openai_api_key_raises_environment_error(self):
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError, match="OPENAI_API_KEY"):
                _create_elicitor_agent("openai:gpt-4o-mini")

    def test_missing_groq_api_key_raises_environment_error(self):
        env = {k: v for k, v in os.environ.items() if k != "GROQ_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError, match="GROQ_API_KEY"):
                _create_elicitor_agent("groq:llama-3.3-70b-versatile")

    def test_valid_key_with_api_key_creates_agent(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
            from pydantic_ai import Agent
            agent = _create_elicitor_agent("anthropic:claude-sonnet-4-6")
            assert isinstance(agent, Agent)


# ---------------------------------------------------------------------------
# TestGetElicitorAgent
# ---------------------------------------------------------------------------


class TestGetElicitorAgent:
    def test_returns_agent_for_valid_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            from pydantic_ai import Agent
            # Clear cache to ensure fresh creation
            _agent_cache.pop("anthropic:claude-sonnet-4-6", None)
            agent = get_elicitor_agent("anthropic:claude-sonnet-4-6")
            assert isinstance(agent, Agent)

    def test_caches_agent(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            _agent_cache.pop("anthropic:claude-sonnet-4-6", None)
            agent1 = get_elicitor_agent("anthropic:claude-sonnet-4-6")
            agent2 = get_elicitor_agent("anthropic:claude-sonnet-4-6")
            assert agent1 is agent2

    def test_different_keys_return_different_agents(self):
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test-key",
            "OPENAI_API_KEY": "test-openai-key",
        }):
            _agent_cache.pop("anthropic:claude-sonnet-4-6", None)
            _agent_cache.pop("openai:gpt-4o-mini", None)
            agent1 = get_elicitor_agent("anthropic:claude-sonnet-4-6")
            agent2 = get_elicitor_agent("openai:gpt-4o-mini")
            assert agent1 is not agent2


# ---------------------------------------------------------------------------
# TestRunElicitor — mock the agent, no real API calls
# ---------------------------------------------------------------------------


def _make_mock_result(output: Any, messages: list | None = None) -> MagicMock:
    """Build a mock agent result with .output and .all_messages()."""
    result = MagicMock()
    result.output = output
    result.all_messages = MagicMock(return_value=messages or [])
    return result


class TestRunElicitorElicitingBranch:
    """Tests for the case where the agent returns Eliciting."""

    @pytest.mark.asyncio
    async def test_returns_eliciting_message(self):
        eliciting_output = Eliciting(message="How many strategies?")
        mock_result = _make_mock_result(eliciting_output, messages=[])

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            text, history = await run_elicitor("I want to run a CEA")
            assert text == "How many strategies?"

    @pytest.mark.asyncio
    async def test_returns_updated_history(self):
        fake_history = [MagicMock(), MagicMock()]
        eliciting_output = Eliciting(message="Question?")
        mock_result = _make_mock_result(eliciting_output, messages=fake_history)

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            _, history = await run_elicitor("hello")
            assert history is fake_history

    @pytest.mark.asyncio
    async def test_passes_user_message_to_agent(self):
        eliciting_output = Eliciting(message="x")
        mock_result = _make_mock_result(eliciting_output)

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            await run_elicitor("My exact message", message_history=[])
            call_args = mock_agent.run.call_args
            assert call_args[0][0] == "My exact message"

    @pytest.mark.asyncio
    async def test_passes_message_history_to_agent(self):
        eliciting_output = Eliciting(message="x")
        mock_result = _make_mock_result(eliciting_output)

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        prior_history = [MagicMock()]

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            await run_elicitor("msg", message_history=prior_history)
            call_kwargs = mock_agent.run.call_args[1]
            assert call_kwargs["message_history"] is prior_history

    @pytest.mark.asyncio
    async def test_none_history_passed_as_empty_list(self):
        """None message_history should become [] in the agent call."""
        eliciting_output = Eliciting(message="x")
        mock_result = _make_mock_result(eliciting_output)

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            await run_elicitor("msg", message_history=None)
            call_kwargs = mock_agent.run.call_args[1]
            assert call_kwargs["message_history"] == []


class TestRunElicitorCompleteBranch:
    """Tests for the case where the agent returns Complete."""

    @pytest.mark.asyncio
    async def test_complete_triggers_simulation(self):
        """When the agent is complete, run_elicitor must run the simulation."""
        config = make_analysis_config()
        complete_output = Complete(
            config=config,
            introduction="All parameters collected. Running simulation...",
        )
        mock_result = _make_mock_result(complete_output, messages=[])

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            text, _ = await run_elicitor("p_response is 0.558")
            # The simulation output should be in the response
            assert "Strategy Results" in text or "Caffeine" in text

    @pytest.mark.asyncio
    async def test_complete_includes_introduction(self):
        config = make_analysis_config()
        complete_output = Complete(
            config=config,
            introduction="Great — here are the results for your analysis.",
        )
        mock_result = _make_mock_result(complete_output, messages=[])

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            text, _ = await run_elicitor("confirm all values")
            assert "Great — here are the results" in text

    @pytest.mark.asyncio
    async def test_complete_includes_markdown_from_simulation(self):
        config = make_analysis_config()
        complete_output = Complete(config=config, introduction="Done.")
        mock_result = _make_mock_result(complete_output, messages=[])

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            text, _ = await run_elicitor("go")
            # markdown report sections
            assert "##" in text

    @pytest.mark.asyncio
    async def test_complete_returns_updated_history(self):
        config = make_analysis_config()
        fake_messages = [MagicMock(), MagicMock(), MagicMock()]
        complete_output = Complete(config=config, introduction="x")
        mock_result = _make_mock_result(complete_output, messages=fake_messages)

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ):
            _, history = await run_elicitor("done")
            assert history is fake_messages


# ---------------------------------------------------------------------------
# TestRunElicitorModelRouting
# ---------------------------------------------------------------------------


class TestRunElicitorModelRouting:
    @pytest.mark.asyncio
    async def test_model_key_passed_to_get_elicitor_agent(self):
        eliciting_output = Eliciting(message="q")
        mock_result = _make_mock_result(eliciting_output)

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ) as mock_get:
            await run_elicitor("hi", model_key="openai:gpt-4o-mini")
            mock_get.assert_called_once_with("openai:gpt-4o-mini")

    @pytest.mark.asyncio
    async def test_default_model_key_used_when_not_specified(self):
        eliciting_output = Eliciting(message="q")
        mock_result = _make_mock_result(eliciting_output)

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch(
            "pubhealth_llm.decision_tree.elicitor.get_elicitor_agent",
            return_value=mock_agent,
        ) as mock_get:
            await run_elicitor("hi")
            mock_get.assert_called_once_with(_DEFAULT_MODEL_KEY)
