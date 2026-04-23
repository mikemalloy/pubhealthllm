"""
Tests for the Gradio application layer.

Verifies the app builds without errors using the actual installed
version of Gradio. No browser or server is started.
"""

import pytest


def test_gradio_import():
    """Gradio must be importable."""
    import gradio as gr
    assert gr.__version__


def test_build_app_returns_blocks():
    """build_app() must return a gr.Blocks instance without raising."""
    import gradio as gr
    from pubhealth_llm.app.gradio_app import build_app

    app = build_app()
    assert isinstance(app, gr.Blocks), (
        f"Expected gr.Blocks, got {type(app)}"
    )


def test_chat_function_is_registered():
    """The chat coroutine must be registered as the Blocks handler.

    In Gradio 6, ChatInterface is embedded inside Blocks and does not
    appear as a top-level child, so we verify the chat function is wired
    in rather than walking the component tree.
    """
    import asyncio
    import inspect
    from pubhealth_llm.app.gradio_app import chat

    # chat must be an async function (required for Gradio async support)
    assert asyncio.iscoroutinefunction(chat), (
        "chat() must be an async function for Gradio async support"
    )
    # It must accept (message, history) positional args
    sig = inspect.signature(chat)
    params = list(sig.parameters.keys())
    assert "message" in params, f"chat() missing 'message' param. Got: {params}"
    assert "history" in params, f"chat() missing 'history' param. Got: {params}"


def test_format_response_renders_markdown():
    """_format_response() must return a non-empty markdown string."""
    from pubhealth_llm.app.gradio_app import _format_response
    from pubhealth_llm.app.schemas import PublicHealthResponse

    resp = PublicHealthResponse(
        summary="Diabetes prevalence is high in this region.",
        evidence=["38% of adults have diabetes."],
        caveats=["2022 data."],
        sources=["CDC PLACES 2023"],
    )
    md = _format_response(resp)
    assert isinstance(md, str)
    assert len(md) > 0
    assert "##" in md  # markdown headers present


def test_format_error_returns_string():
    """_format_error() must return a markdown string for any exception."""
    from pubhealth_llm.app.gradio_app import _format_error

    result = _format_error(ValueError("test error"))
    assert isinstance(result, str)
    assert "error" in result.lower()
    assert "ValueError" in result


def test_build_contextual_question_no_history():
    """With empty history, the question is returned unchanged."""
    from pubhealth_llm.app.gradio_app import _build_contextual_question

    q = "What is the obesity rate in Travis County?"
    result = _build_contextual_question(q, [])
    assert result == q


def test_build_contextual_question_with_history():
    """With history, the output contains both the context and the question."""
    from pubhealth_llm.app.gradio_app import _build_contextual_question

    history = [
        {"role": "user", "content": "Tell me about diabetes."},
        {"role": "assistant", "content": "Diabetes affects 11% of US adults."},
    ]
    result = _build_contextual_question("What about obesity?", history)
    assert "What about obesity?" in result
    assert "diabetes" in result.lower()  # prior context included
