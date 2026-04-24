"""
Gradio Chat Interface for pubHealthLLM.

Implements a ChatInterface with type="messages" for proper multi-turn
conversation history.  The interface wraps the PydanticAI agent and
formats its PublicHealthResponse output as rich markdown.

Key design decisions:
- Async chat function so the agent's async run() integrates naturally
- Message history passed to agent for multi-turn context
- Structured output rendered as formatted markdown tables and sections
- Example questions as clickable buttons for demo purposes
- Prominent disclaimer in the interface header

Usage:
    from pubhealth_llm.app.gradio_app import build_app
    app = build_app()
    app.launch(share=True)
"""

import asyncio
import logging
from typing import Optional

import gradio as gr

from pubhealth_llm.app.agent import run_agent
from pubhealth_llm.app.schemas import PublicHealthResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_TITLE = "pubHealthLLM — Public Health Decision Intelligence"

DISCLAIMER_HTML = """
<div style="
    background: #fff3cd;
    border: 1px solid #ffc107;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
    font-size: 0.875rem;
    color: #664d03;
">
    <strong>⚠️ Decision Support Tool Only</strong> — This system provides
    evidence-based analysis from CDC surveillance data. All outputs require
    validation by qualified public health professionals before informing
    operational decisions. Data reflects historical surveillance and may
    not capture current conditions.
</div>
"""

DATA_SOURCES_HTML = """
<div style="
    background: #e7f3ff;
    border: 1px solid #90caf9;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 0.8rem;
    color: #0d47a1;
">
    <strong>Data Sources:</strong>
    CDC PLACES 2023 (county-level health statistics) ·
    CDC MMWR Weekly Reports 2022–2024 (outbreak surveillance)
</div>
"""

EXAMPLE_QUESTIONS = [
    "What is the obesity rate in Travis County, Texas? How does it compare to the state average?",
    "Are there recent MMWR reports about foodborne illness outbreaks? What counties have the highest rates of preventable hospitalizations?",
    "Compare diabetes prevalence across Harris County, Dallas County, and Bexar County in Texas.",
    "What does CDC surveillance say about opioid overdose trends, and which counties in Ohio have the highest rates of mental health issues?",
    "What are the leading causes of death in Louisiana and how do cardiovascular mortality rates compare to neighboring states?",
]

# Model selector — (display label, value passed to run_agent)
MODEL_OPTIONS = [
    ("Claude Sonnet 4.6 — Best quality (default)", "anthropic:claude-sonnet-4-6"),
    ("Claude Haiku 4.5 — Fast, lower cost",         "anthropic:claude-haiku-4"),
    ("GPT-4o mini — Reliable, low cost (OpenAI)",   "openai:gpt-4o-mini"),
    ("Llama 3.3 70B — Fast, free (Groq)",            "groq:llama-3.3-70b-versatile"),
    ("Llama 3.1 8B Instant — Fastest, free (Groq)",  "groq:llama-3.1-8b-instant"),
]
DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"
MODEL_NOTE = "Claude Sonnet recommended for best quality. Llama models are faster and free."

# Map from Gradio role strings to PydanticAI message types
_ROLE_MAP = {"user": "user", "assistant": "assistant"}


# ---------------------------------------------------------------------------
# Response formatting
# ---------------------------------------------------------------------------


def _format_response(response: PublicHealthResponse) -> str:
    """
    Convert a PublicHealthResponse to rendered markdown for the chat UI.

    Args:
        response: Validated PublicHealthResponse from the agent.

    Returns:
        GitHub-flavored markdown string.
    """
    return response.to_markdown()


def _format_error(exc: Exception) -> str:
    """
    Format an unexpected exception as a user-friendly markdown message.

    Args:
        exc: The caught exception.

    Returns:
        Markdown error string.
    """
    return (
        "## Error Processing Your Question\n\n"
        f"An unexpected error occurred: `{type(exc).__name__}: {exc}`\n\n"
        "**Possible causes:**\n"
        "- The data ingestion pipeline has not been run yet\n"
        "- `GROQ_API_KEY` is missing or invalid in your `.env` file\n"
        "- The ChromaDB or SQLite database is corrupted\n\n"
        "**To resolve:** Run `python -m data_ingestion.run_ingestion` "
        "and check that your `.env` contains a valid `GROQ_API_KEY`."
    )


# ---------------------------------------------------------------------------
# Chat handler
# ---------------------------------------------------------------------------


def _extract_pydantic_history(
    gradio_history: list[dict],
) -> list:
    """
    Convert Gradio message history to PydanticAI message format.

    Gradio ChatInterface with type="messages" provides history as a
    list of {"role": ..., "content": ...} dicts.  PydanticAI expects
    its own ModelMessage objects, but passing the raw text history
    via the user turn is sufficient for context continuity.

    For simplicity we inject prior turns as a formatted context block
    in the current user message rather than parsing PydanticAI internal
    message objects — this avoids tight coupling to PydanticAI internals.

    Args:
        gradio_history: List of {"role": str, "content": str} dicts.

    Returns:
        Empty list (context is injected via the message string instead).
    """
    return []  # see _build_contextual_question below


def _build_contextual_question(
    user_message: str,
    history: list[dict],
) -> str:
    """
    Prepend recent conversation history to the user question as context.

    Limited to the last 4 turns (8 messages) to keep the prompt concise.

    Args:
        user_message: The current question from the user.
        history:      List of prior {"role", "content"} dicts.

    Returns:
        Question string with optional prior-context prefix.
    """
    if not history:
        return user_message

    recent = history[-8:]  # last 4 exchanges
    ctx_lines = ["[Prior conversation context:]"]
    for msg in recent:
        role = msg.get("role", "user").capitalize()
        # Truncate long assistant responses to save tokens
        content = msg.get("content", "")
        if role == "Assistant" and len(content) > 400:
            content = content[:400] + " … [truncated]"
        ctx_lines.append(f"{role}: {content}")

    ctx_lines.append("[End of context]")
    ctx_lines.append(f"\nCurrent question: {user_message}")
    return "\n".join(ctx_lines)


async def chat(
    message: str,
    history: list[dict],
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Async chat handler called by Gradio on each user message.

    This function is the bridge between the Gradio UI and the
    PydanticAI agent.  It:
      1. Injects conversation history as context in the user message
      2. Calls run_agent() asynchronously with the selected model
      3. Formats the PublicHealthResponse as markdown for display

    Args:
        message: Current user message string.
        history: List of prior {"role", "content"} message dicts
                 maintained by Gradio ChatInterface.
        model:   Model key selected in the UI dropdown.

    Returns:
        Agent response formatted as a markdown string.
    """
    if not message or not message.strip():
        return "Please enter a question about public health."

    contextual_question = _build_contextual_question(message.strip(), history)

    try:
        response: PublicHealthResponse = await run_agent(
            contextual_question, model=model
        )
        return _format_response(response)
    except Exception as exc:
        logger.error("Chat handler error: %s", exc, exc_info=True)
        return _format_error(exc)


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------


def build_app() -> gr.ChatInterface:
    """
    Construct and configure the Gradio ChatInterface.

    Returns:
        A configured gr.ChatInterface instance ready to launch.
    """
    with gr.Blocks(title=APP_TITLE) as demo:

        # Header
        gr.HTML(f"<h1 style='text-align:center; margin-bottom:4px;'>{APP_TITLE}</h1>")
        gr.HTML(
            "<p style='text-align:center; color:#666; margin-top:0;'>"
            "Evidence-based answers from CDC MMWR surveillance data and "
            "CDC PLACES county-level health statistics"
            "</p>"
        )
        gr.HTML(DISCLAIMER_HTML)
        gr.HTML(DATA_SOURCES_HTML)

        # Model selector
        model_dropdown = gr.Dropdown(
            choices=MODEL_OPTIONS,
            value=DEFAULT_MODEL,
            label="Model",
            show_label=True,
            interactive=True,
            scale=1,
        )
        gr.Markdown(
            f"<p style='font-size:0.8rem; color:#666; margin-top:2px;'>{MODEL_NOTE}</p>"
        )

        # Chat interface
        # When additional_inputs are present Gradio requires examples as
        # [[message, input1, input2, ...]] — include the default model value.
        examples_with_model = [[q, DEFAULT_MODEL] for q in EXAMPLE_QUESTIONS]

        chat_interface = gr.ChatInterface(
            fn=chat,
            additional_inputs=[model_dropdown],
            examples=examples_with_model,
            cache_examples=False,
            chatbot=gr.Chatbot(
                label="Conversation",
                height=520,
                show_label=False,
                render_markdown=True,
            ),
            textbox=gr.Textbox(
                placeholder="Ask a public health question… (e.g., What is the diabetes rate in Cook County, IL?)",
                label="Your Question",
                lines=2,
                max_lines=6,
                show_label=False,
                submit_btn="Ask",
            ),
        )

        # Footer
        gr.HTML(
            "<div style='text-align:center; margin-top:12px; font-size:0.75rem; color:#999;'>"
            "pubHealthLLM v1 · "
            "Data: CDC PLACES 2023, CDC MMWR 2022–2024, CDC NCHS Mortality 1999–2017"
            "</div>"
        )

    return demo


# ---------------------------------------------------------------------------
# Direct launch (used by main.py and for quick testing)
# ---------------------------------------------------------------------------


def launch(share: bool = True, server_port: int = 7860) -> None:
    """
    Build and launch the Gradio app.

    Args:
        share:       If True, create a public Gradio share link (for demo use).
        server_port: Local port to serve the UI on.
    """
    app = build_app()
    app.launch(
        share=share,
        server_port=server_port,
        quiet=False,
        theme=gr.themes.Soft(
            primary_hue="blue",
            secondary_hue="slate",
            font=gr.themes.GoogleFont("Inter"),
        ),
        css="""
        .gradio-container { max-width: 1000px !important; }
        footer { display: none !important; }
        """,
    )
