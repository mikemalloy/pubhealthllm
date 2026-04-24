"""
Tests for pubhealth_llm.app.gradio_app
=======================================

No real API calls or browser rendering — all agent/elicitor interactions
are mocked.

Covers:
* build_app() — returns gr.Blocks, contains expected tab structure
* Q&A tab helpers — _format_response, _format_error, _build_contextual_question
* Q&A chat handler — delegates to run_agent, handles errors gracefully
* DT tab helpers — _format_dt_error
* dt_clear() — resets to initial state
* dt_chat() — delegates to run_elicitor, updates display and state correctly
* dt_chat() — error handling (elicitor raises, display shows error message)
* dt_chat() — empty message is a no-op
* Constants — initial greeting content, MODEL_OPTIONS completeness
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import gradio as gr
import pytest

from pubhealth_llm.app.gradio_app import (
    DEFAULT_MODEL,
    DT_INITIAL_GREETING,
    MODEL_OPTIONS,
    _DT_INITIAL_MESSAGES,
    _build_contextual_question,
    _format_dt_error,
    _format_error,
    _format_response,
    build_app,
    chat,
    dt_chat,
    dt_clear,
)
from pubhealth_llm.app.schemas import PublicHealthResponse


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def make_response(**kwargs) -> PublicHealthResponse:
    defaults = dict(
        summary="Test summary.",
        evidence=["Evidence A."],
        caveats=["Caveat A."],
        sources=["Source A."],
    )
    defaults.update(kwargs)
    return PublicHealthResponse(**defaults)


# ---------------------------------------------------------------------------
# TestBuildApp
# ---------------------------------------------------------------------------


class TestBuildApp:
    def test_returns_blocks(self):
        app = build_app()
        assert isinstance(app, gr.Blocks)

    def test_title_set(self):
        app = build_app()
        assert "pubHealthLLM" in app.title

    def test_app_has_tabs(self):
        app = build_app()
        tabs = [c for c in app.blocks.values() if isinstance(c, gr.Tab)]
        assert len(tabs) >= 2

    def test_qa_tab_present(self):
        app = build_app()
        tab_labels = [
            c.label for c in app.blocks.values() if isinstance(c, gr.Tab)
        ]
        assert any("Q&A" in (label or "") for label in tab_labels)

    def test_dt_tab_present(self):
        app = build_app()
        tab_labels = [
            c.label for c in app.blocks.values() if isinstance(c, gr.Tab)
        ]
        assert any("Decision Tree" in (label or "") for label in tab_labels)

    def test_chatbot_components_present(self):
        app = build_app()
        chatbots = [c for c in app.blocks.values() if isinstance(c, gr.Chatbot)]
        assert len(chatbots) >= 2

    def test_dt_chatbot_has_initial_greeting(self):
        app = build_app()
        chatbots = [c for c in app.blocks.values() if isinstance(c, gr.Chatbot)]
        initial_values = [c.value for c in chatbots if c.value]
        assert initial_values, "No chatbot has an initial value"

    def test_model_dropdowns_present(self):
        app = build_app()
        dropdowns = [c for c in app.blocks.values() if isinstance(c, gr.Dropdown)]
        assert len(dropdowns) >= 2

    def test_model_dropdowns_have_correct_options(self):
        app = build_app()
        dropdowns = [c for c in app.blocks.values() if isinstance(c, gr.Dropdown)]
        for dd in dropdowns:
            choices = dd.choices or []
            values = [v if isinstance(v, str) else v[1] for v in choices]
            assert "anthropic:claude-sonnet-4-6" in values

    def test_chat_function_is_async(self):
        assert asyncio.iscoroutinefunction(chat)

    def test_chat_function_has_message_param(self):
        sig = inspect.signature(chat)
        assert "message" in sig.parameters

    def test_chat_function_has_history_param(self):
        sig = inspect.signature(chat)
        assert "history" in sig.parameters

    def test_dt_chat_function_is_async(self):
        assert asyncio.iscoroutinefunction(dt_chat)


# ---------------------------------------------------------------------------
# TestModelOptions
# ---------------------------------------------------------------------------


class TestModelOptions:
    def test_has_five_options(self):
        assert len(MODEL_OPTIONS) == 5

    def test_default_model_in_options(self):
        values = [v for _, v in MODEL_OPTIONS]
        assert DEFAULT_MODEL in values

    def test_anthropic_sonnet_present(self):
        values = [v for _, v in MODEL_OPTIONS]
        assert "anthropic:claude-sonnet-4-6" in values

    def test_groq_present(self):
        values = [v for _, v in MODEL_OPTIONS]
        assert any(v.startswith("groq:") for v in values)

    def test_openai_present(self):
        values = [v for _, v in MODEL_OPTIONS]
        assert any(v.startswith("openai:") for v in values)


# ---------------------------------------------------------------------------
# TestInitialGreeting
# ---------------------------------------------------------------------------


class TestInitialGreeting:
    def test_initial_messages_is_list(self):
        assert isinstance(_DT_INITIAL_MESSAGES, list)

    def test_initial_messages_has_one_entry(self):
        assert len(_DT_INITIAL_MESSAGES) == 1

    def test_initial_message_is_assistant(self):
        assert _DT_INITIAL_MESSAGES[0]["role"] == "assistant"

    def test_initial_greeting_non_empty(self):
        assert len(DT_INITIAL_GREETING.strip()) > 50

    def test_initial_greeting_mentions_decision_tree(self):
        assert "decision tree" in DT_INITIAL_GREETING.lower()

    def test_initial_greeting_asks_for_strategies(self):
        assert "strateg" in DT_INITIAL_GREETING.lower()

    def test_initial_greeting_gives_example(self):
        assert "example" in DT_INITIAL_GREETING.lower() or \
               "sumatriptan" in DT_INITIAL_GREETING.lower()


# ---------------------------------------------------------------------------
# TestFormatResponse (Q&A)
# ---------------------------------------------------------------------------


class TestFormatResponse:
    def test_returns_string(self):
        result = _format_response(make_response())
        assert isinstance(result, str)

    def test_contains_summary(self):
        result = _format_response(make_response(summary="Unique summary text."))
        assert "Unique summary text." in result

    def test_non_empty(self):
        result = _format_response(make_response())
        assert len(result.strip()) > 0

    def test_contains_markdown_headers(self):
        result = _format_response(make_response())
        assert "##" in result


# ---------------------------------------------------------------------------
# TestFormatError (Q&A)
# ---------------------------------------------------------------------------


class TestFormatError:
    def test_returns_string(self):
        result = _format_error(ValueError("oops"))
        assert isinstance(result, str)

    def test_contains_error_type(self):
        result = _format_error(ValueError("oops"))
        assert "ValueError" in result

    def test_contains_error_message(self):
        result = _format_error(RuntimeError("something broke"))
        assert "something broke" in result

    def test_contains_markdown_header(self):
        result = _format_error(Exception("x"))
        assert "##" in result


# ---------------------------------------------------------------------------
# TestFormatDtError
# ---------------------------------------------------------------------------


class TestFormatDtError:
    def test_returns_string(self):
        result = _format_dt_error(ValueError("bad param"))
        assert isinstance(result, str)

    def test_contains_error_type(self):
        result = _format_dt_error(RuntimeError("crash"))
        assert "RuntimeError" in result

    def test_contains_markdown_header(self):
        result = _format_dt_error(Exception("x"))
        assert "##" in result

    def test_mentions_new_analysis(self):
        result = _format_dt_error(Exception("x"))
        assert "New Analysis" in result or "new analysis" in result.lower()


# ---------------------------------------------------------------------------
# TestBuildContextualQuestion
# ---------------------------------------------------------------------------


class TestBuildContextualQuestion:
    def test_no_history_returns_message(self):
        result = _build_contextual_question("What is diabetes?", [])
        assert result == "What is diabetes?"

    def test_with_history_includes_context(self):
        history = [
            {"role": "user", "content": "Prior question"},
            {"role": "assistant", "content": "Prior answer"},
        ]
        result = _build_contextual_question("New question", history)
        assert "Prior question" in result
        assert "New question" in result

    def test_with_history_includes_current_question(self):
        history = [{"role": "user", "content": "old"}]
        result = _build_contextual_question("current", history)
        assert "current" in result

    def test_long_assistant_response_truncated(self):
        long_answer = "A" * 1000
        history = [{"role": "assistant", "content": long_answer}]
        result = _build_contextual_question("q", history)
        assert len(result) < len(long_answer) + 200

    def test_limited_to_last_8_messages(self):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
            for i in range(20)
        ]
        result = _build_contextual_question("latest", history)
        assert "msg0" not in result
        assert "msg12" in result or "msg19" in result


# ---------------------------------------------------------------------------
# TestQAChatHandler
# ---------------------------------------------------------------------------


class TestQAChatHandler:
    @pytest.mark.asyncio
    async def test_empty_message_returns_prompt(self):
        result = await chat("", [], DEFAULT_MODEL)
        assert "question" in result.lower()

    @pytest.mark.asyncio
    async def test_whitespace_message_returns_prompt(self):
        result = await chat("   ", [], DEFAULT_MODEL)
        assert "question" in result.lower()

    @pytest.mark.asyncio
    async def test_delegates_to_run_agent(self):
        mock_response = make_response(summary="Agent worked.")
        with patch(
            "pubhealth_llm.app.gradio_app.run_agent",
            new=AsyncMock(return_value=mock_response),
        ):
            result = await chat("What is diabetes?", [], DEFAULT_MODEL)
            assert "Agent worked." in result

    @pytest.mark.asyncio
    async def test_handles_run_agent_exception(self):
        with patch(
            "pubhealth_llm.app.gradio_app.run_agent",
            new=AsyncMock(side_effect=RuntimeError("API down")),
        ):
            result = await chat("question", [], DEFAULT_MODEL)
            assert "Error" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_passes_model_to_run_agent(self):
        mock_response = make_response()
        with patch(
            "pubhealth_llm.app.gradio_app.run_agent",
            new=AsyncMock(return_value=mock_response),
        ) as mock_run:
            await chat("q", [], "groq:llama-3.3-70b-versatile")
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("model") == "groq:llama-3.3-70b-versatile"

    @pytest.mark.asyncio
    async def test_returns_string(self):
        mock_response = make_response()
        with patch(
            "pubhealth_llm.app.gradio_app.run_agent",
            new=AsyncMock(return_value=mock_response),
        ):
            result = await chat("q", [], DEFAULT_MODEL)
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# TestDtClear
# ---------------------------------------------------------------------------


class TestDtClear:
    def test_returns_tuple_of_four(self):
        result = dt_clear()
        assert len(result) == 4

    def test_chatbot_value_is_list(self):
        chatbot_val, _, _, _ = dt_clear()
        assert isinstance(chatbot_val, list)

    def test_chatbot_has_initial_greeting(self):
        chatbot_val, _, _, _ = dt_clear()
        assert len(chatbot_val) == 1
        assert chatbot_val[0]["role"] == "assistant"

    def test_display_state_matches_chatbot(self):
        chatbot_val, display_state, _, _ = dt_clear()
        assert chatbot_val == display_state

    def test_pydantic_history_is_empty_list(self):
        _, _, pydantic_history, _ = dt_clear()
        assert pydantic_history == []

    def test_textbox_is_empty_string(self):
        _, _, _, textbox = dt_clear()
        assert textbox == ""

    def test_returns_independent_lists(self):
        chatbot_val, display_state, _, _ = dt_clear()
        assert chatbot_val is not display_state


# ---------------------------------------------------------------------------
# TestDtChatHandler
# ---------------------------------------------------------------------------


class TestDtChatHandler:
    def _make_elicitor_patch(self, response_text: str, updated_history=None):
        return patch(
            "pubhealth_llm.app.gradio_app.run_elicitor",
            new=AsyncMock(return_value=(response_text, updated_history or [])),
        )

    @pytest.mark.asyncio
    async def test_empty_message_is_noop(self):
        initial_display = [{"role": "assistant", "content": "hi"}]
        initial_pydantic = [MagicMock()]
        chatbot, display, pydantic, textbox = await dt_chat(
            "", initial_display, initial_pydantic, DEFAULT_MODEL
        )
        assert display is initial_display
        assert pydantic is initial_pydantic
        assert textbox == ""

    @pytest.mark.asyncio
    async def test_whitespace_message_is_noop(self):
        initial_display = [{"role": "assistant", "content": "hi"}]
        chatbot, display, pydantic, textbox = await dt_chat(
            "   ", initial_display, [], DEFAULT_MODEL
        )
        assert display is initial_display

    @pytest.mark.asyncio
    async def test_user_message_added_to_display(self):
        with self._make_elicitor_patch("Agent response"):
            chatbot, display, _, _ = await dt_chat(
                "My message", [], [], DEFAULT_MODEL
            )
        user_msgs = [m for m in display if m["role"] == "user"]
        assert any("My message" in m["content"] for m in user_msgs)

    @pytest.mark.asyncio
    async def test_assistant_response_added_to_display(self):
        with self._make_elicitor_patch("The agent's reply"):
            chatbot, display, _, _ = await dt_chat(
                "question", [], [], DEFAULT_MODEL
            )
        assistant_msgs = [m for m in display if m["role"] == "assistant"]
        assert any("The agent's reply" in m["content"] for m in assistant_msgs)

    @pytest.mark.asyncio
    async def test_chatbot_value_matches_display_state(self):
        with self._make_elicitor_patch("reply"):
            chatbot, display, _, _ = await dt_chat("q", [], [], DEFAULT_MODEL)
        assert chatbot == display

    @pytest.mark.asyncio
    async def test_pydantic_history_updated(self):
        new_pydantic = [MagicMock(), MagicMock()]
        with self._make_elicitor_patch("reply", updated_history=new_pydantic):
            _, _, pydantic, _ = await dt_chat("q", [], [], DEFAULT_MODEL)
        assert pydantic is new_pydantic

    @pytest.mark.asyncio
    async def test_textbox_cleared_after_submit(self):
        with self._make_elicitor_patch("reply"):
            _, _, _, textbox = await dt_chat("q", [], [], DEFAULT_MODEL)
        assert textbox == ""

    @pytest.mark.asyncio
    async def test_passes_model_key_to_elicitor(self):
        with patch(
            "pubhealth_llm.app.gradio_app.run_elicitor",
            new=AsyncMock(return_value=("reply", [])),
        ) as mock_elicitor:
            await dt_chat("q", [], [], "groq:llama-3.3-70b-versatile")
            call_kwargs = mock_elicitor.call_args[1]
            assert call_kwargs.get("model_key") == "groq:llama-3.3-70b-versatile"

    @pytest.mark.asyncio
    async def test_passes_pydantic_history_to_elicitor(self):
        prior_history = [MagicMock()]
        with patch(
            "pubhealth_llm.app.gradio_app.run_elicitor",
            new=AsyncMock(return_value=("reply", prior_history)),
        ) as mock_elicitor:
            await dt_chat("q", [], prior_history, DEFAULT_MODEL)
            call_kwargs = mock_elicitor.call_args[1]
            assert call_kwargs.get("message_history") is prior_history

    @pytest.mark.asyncio
    async def test_elicitor_exception_shows_error_message(self):
        with patch(
            "pubhealth_llm.app.gradio_app.run_elicitor",
            new=AsyncMock(side_effect=RuntimeError("API down")),
        ):
            chatbot, display, pydantic, _ = await dt_chat(
                "q", [], [], DEFAULT_MODEL
            )
        assistant_msgs = [m for m in display if m["role"] == "assistant"]
        assert assistant_msgs, "No assistant message added after error"
        error_content = assistant_msgs[-1]["content"]
        assert "Error" in error_content or "error" in error_content.lower()

    @pytest.mark.asyncio
    async def test_elicitor_exception_preserves_pydantic_history(self):
        prior_pydantic = [MagicMock()]
        with patch(
            "pubhealth_llm.app.gradio_app.run_elicitor",
            new=AsyncMock(side_effect=RuntimeError("crash")),
        ):
            _, _, pydantic, _ = await dt_chat(
                "q", [], prior_pydantic, DEFAULT_MODEL
            )
        assert pydantic is prior_pydantic

    @pytest.mark.asyncio
    async def test_prior_display_history_preserved(self):
        existing = [
            {"role": "assistant", "content": "Initial greeting"},
            {"role": "user", "content": "First question"},
        ]
        with self._make_elicitor_patch("Second reply"):
            chatbot, display, _, _ = await dt_chat(
                "Second question", existing, [], DEFAULT_MODEL
            )
        content = " ".join(m["content"] for m in display)
        assert "Initial greeting" in content
        assert "First question" in content
        assert "Second question" in content
        assert "Second reply" in content

    @pytest.mark.asyncio
    async def test_returns_four_tuple(self):
        with self._make_elicitor_patch("reply"):
            result = await dt_chat("q", [], [], DEFAULT_MODEL)
        assert len(result) == 4
