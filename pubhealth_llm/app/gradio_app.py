"""
Gradio app for pubHealthLLM.

Two tabs inside a single gr.Blocks:

  Tab 1 — Public Health Q&A
      Wraps the PydanticAI agent that answers questions using CDC MMWR
      surveillance data and CDC PLACES county-level health statistics.

  Tab 2 — Decision Tree Analysis
      Drives the Evans acute-treatment decision tree elicitation agent.
      A multi-turn conversation collects all clinical parameters, then runs
      the vectorised Monte Carlo simulation and displays the results as
      formatted markdown.

Usage:
    from pubhealth_llm.app.gradio_app import build_app
    app = build_app()
    app.launch(share=True)
"""

import logging
from typing import Optional

import gradio as gr

from pubhealth_llm.app.agent import run_agent
from pubhealth_llm.app.schemas import PublicHealthResponse
from pubhealth_llm.decision_tree.elicitor import run_elicitor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — shared
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
    evidence-based analysis from CDC surveillance data and health economic
    models. All outputs require validation by qualified public health
    professionals before informing operational decisions.
</div>
"""

MODEL_OPTIONS = [
    ("Claude Sonnet 4.6 — Best quality (default)", "anthropic:claude-sonnet-4-6"),
    ("Claude Haiku 4.5 — Fast, lower cost",         "anthropic:claude-haiku-4"),
    ("GPT-4o mini — Reliable, low cost (OpenAI)",   "openai:gpt-4o-mini"),
    ("Llama 3.3 70B — Fast, free (Groq)",            "groq:llama-3.3-70b-versatile"),
    ("Llama 3.1 8B Instant — Fastest, free (Groq)",  "groq:llama-3.1-8b-instant"),
]
DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"
MODEL_NOTE = "Claude Sonnet recommended for best quality. Llama models are faster and free."

# ---------------------------------------------------------------------------
# Constants — Q&A tab
# ---------------------------------------------------------------------------

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
    CDC MMWR Weekly Reports 2022–2024 (outbreak surveillance) ·
    CDC NCHS Mortality 1999–2017
</div>
"""

EXAMPLE_QUESTIONS = [
    "What is the obesity rate in Travis County, Texas? How does it compare to the state average?",
    "Are there recent MMWR reports about foodborne illness outbreaks? What counties have the highest rates of preventable hospitalizations?",
    "Compare diabetes prevalence across Harris County, Dallas County, and Bexar County in Texas.",
    "What does CDC surveillance say about opioid overdose trends, and which counties in Ohio have the highest rates of mental health issues?",
    "What are the leading causes of death in Louisiana and how do cardiovascular mortality rates compare to neighboring states?",
]

# ---------------------------------------------------------------------------
# Constants — Decision Tree tab
# ---------------------------------------------------------------------------

DT_INTRO_HTML = """
<div style="
    background: #f0f7f0;
    border: 1px solid #81c784;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
    font-size: 0.875rem;
    color: #1b5e20;
">
    <strong>Health Economic Decision Tree Analysis</strong> —
    Uses the Evans (1997) acute-treatment model to compare the costs and
    outcomes of treatment strategies. The assistant will guide you through
    collecting the required parameters, then run the simulation and display
    a full cost-effectiveness report.
</div>
"""

DT_INITIAL_GREETING = (
    "Welcome! I'm here to help you set up a health economic "
    "cost-effectiveness analysis using the Evans acute-treatment decision "
    "tree model.\n\n"
    "This model compares treatment strategies along five clinical pathways — "
    "from successful response with no recurrence through to hospitalisation. "
    "I'll ask you for the clinical probabilities, costs, and quality-of-life "
    "utilities for each strategy, then run the Monte Carlo simulation and "
    "display the full results.\n\n"
    "**To get started, please tell me:**\n"
    "- What health condition or treatment decision are you analysing?\n"
    "- How many strategies would you like to compare, and what are their names?\n\n"
    "**Example:** *\"I want to compare sumatriptan 100 mg versus "
    "caffeine/ergotamine for acute migraine treatment.\"*"
)

_DT_INITIAL_MESSAGES = [
    {"role": "assistant", "content": DT_INITIAL_GREETING}
]


# ---------------------------------------------------------------------------
# Q&A tab — formatting helpers
# ---------------------------------------------------------------------------


def _format_response(response: PublicHealthResponse) -> str:
    """Convert a PublicHealthResponse to markdown for the chat UI."""
    return response.to_markdown()


def _format_error(exc: Exception) -> str:
    """Format an unexpected Q&A agent exception as user-friendly markdown."""
    return (
        "## Error Processing Your Question\n\n"
        f"An unexpected error occurred: `{type(exc).__name__}: {exc}`\n\n"
        "**Possible causes:**\n"
        "- The data ingestion pipeline has not been run yet\n"
        "- A required API key is missing or invalid in your `.env` file\n"
        "- The ChromaDB or SQLite database is corrupted\n\n"
        "**To resolve:** Run `python -m data_ingestion.run_ingestion` "
        "and check that your `.env` contains valid API keys."
    )


def _build_contextual_question(user_message: str, history: list[dict]) -> str:
    """
    Prepend recent conversation history to the user question as context.

    Limited to the last 4 turns (8 messages) to keep the prompt concise.
    """
    if not history:
        return user_message

    recent = history[-8:]
    ctx_lines = ["[Prior conversation context:]"]
    for msg in recent:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        if role == "Assistant" and len(content) > 400:
            content = content[:400] + " … [truncated]"
        ctx_lines.append(f"{role}: {content}")
    ctx_lines.append("[End of context]")
    ctx_lines.append(f"\nCurrent question: {user_message}")
    return "\n".join(ctx_lines)


# ---------------------------------------------------------------------------
# Q&A tab — chat handler
# ---------------------------------------------------------------------------


async def chat(
    message: str,
    history: list[dict],
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Async chat handler for the Public Health Q&A tab.

    Called by Gradio ChatInterface on each user message.

    Args:
        message: Current user message.
        history: Prior conversation as a list of {role, content} dicts.
        model:   Model key from MODEL_OPTIONS.

    Returns:
        Agent response as a markdown string.
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
        logger.error("Q&A chat handler error: %s", exc, exc_info=True)
        return _format_error(exc)


# ---------------------------------------------------------------------------
# Decision Tree tab — formatting helpers
# ---------------------------------------------------------------------------


def _format_dt_error(exc: Exception) -> str:
    """Format a decision tree pipeline exception as user-friendly markdown."""
    return (
        "## Error Running Analysis\n\n"
        f"Something went wrong: `{type(exc).__name__}: {exc}`\n\n"
        "**Possible causes:**\n"
        "- A required API key is missing or invalid in your `.env` file\n"
        "- The simulation script failed (check parameter values are valid)\n\n"
        "Please check your parameters and try again. "
        "If the problem persists, try clicking **Start New Analysis** to reset."
    )


# ---------------------------------------------------------------------------
# Decision Tree tab — event handlers
# ---------------------------------------------------------------------------


async def dt_chat(
    message: str,
    display_history: list[dict],
    pydantic_history: list,
    model: str,
) -> tuple[list[dict], list[dict], list, str]:
    """
    Async handler for each student message in the Decision Tree tab.

    Advances the elicitation conversation by one turn.  When the agent has
    collected all parameters, it runs the simulation and returns the full
    markdown report.

    Args:
        message:         The student's latest message.
        display_history: Current chatbot display history (list of
                         {role, content} dicts stored in gr.State).
        pydantic_history: PydanticAI message history from all prior turns
                          (stored in gr.State).
        model:           Model key from MODEL_OPTIONS.

    Returns:
        A 4-tuple: (chatbot_value, new_display_history, new_pydantic_history,
                    textbox_clear_value).
    """
    if not message or not message.strip():
        return display_history, display_history, pydantic_history, ""

    new_display = display_history + [{"role": "user", "content": message.strip()}]

    try:
        response_text, updated_pydantic = await run_elicitor(
            message.strip(),
            message_history=pydantic_history,
            model_key=model,
        )
        new_display = new_display + [{"role": "assistant", "content": response_text}]
        return new_display, new_display, updated_pydantic, ""

    except Exception as exc:
        logger.error("Decision tree handler error: %s", exc, exc_info=True)
        error_text = _format_dt_error(exc)
        new_display = new_display + [{"role": "assistant", "content": error_text}]
        return new_display, new_display, pydantic_history, ""


def dt_clear() -> tuple[list[dict], list[dict], list, str]:
    """
    Reset the Decision Tree tab to its initial state.

    Returns:
        A 4-tuple: (chatbot_value, new_display_history, new_pydantic_history,
                    textbox_clear_value).
    """
    return list(_DT_INITIAL_MESSAGES), list(_DT_INITIAL_MESSAGES), [], ""


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------


def build_app() -> gr.Blocks:
    """
    Construct and configure the Gradio application.

    Returns a gr.Blocks instance containing two tabs:
      - Public Health Q&A (existing agent)
      - Decision Tree Analysis (new elicitation agent)

    Returns:
        Configured gr.Blocks instance ready to launch.
    """
    with gr.Blocks(title=APP_TITLE) as demo:

        # ── Shared header ──────────────────────────────────────────────────
        gr.HTML(
            f"<h1 style='text-align:center; margin-bottom:4px;'>{APP_TITLE}</h1>"
        )
        gr.HTML(DISCLAIMER_HTML)

        # ── Tabs ───────────────────────────────────────────────────────────
        with gr.Tabs():

            # ── Tab 1: Public Health Q&A ───────────────────────────────────
            with gr.Tab("Public Health Q&A"):

                gr.HTML(
                    "<p style='text-align:center; color:#666; margin:4px 0 8px;'>"
                    "Evidence-based answers from CDC MMWR surveillance data and "
                    "CDC PLACES county-level health statistics"
                    "</p>"
                )
                gr.HTML(DATA_SOURCES_HTML)

                qa_model_dropdown = gr.Dropdown(
                    choices=MODEL_OPTIONS,
                    value=DEFAULT_MODEL,
                    label="Model",
                    show_label=True,
                    interactive=True,
                    scale=1,
                )
                gr.Markdown(
                    f"<p style='font-size:0.8rem; color:#666; margin-top:2px;'>"
                    f"{MODEL_NOTE}</p>"
                )

                examples_with_model = [[q, DEFAULT_MODEL] for q in EXAMPLE_QUESTIONS]

                gr.ChatInterface(
                    fn=chat,
                    additional_inputs=[qa_model_dropdown],
                    examples=examples_with_model,
                    cache_examples=False,
                    chatbot=gr.Chatbot(
                        label="Conversation",
                        height=520,
                        show_label=False,
                        render_markdown=True,
                    ),
                    textbox=gr.Textbox(
                        placeholder=(
                            "Ask a public health question… "
                            "(e.g., What is the diabetes rate in Cook County, IL?)"
                        ),
                        label="Your Question",
                        lines=2,
                        max_lines=6,
                        show_label=False,
                        submit_btn="Ask",
                    ),
                )

            # ── Tab 2: Decision Tree Analysis ──────────────────────────────
            with gr.Tab("Decision Tree Analysis"):

                gr.HTML(DT_INTRO_HTML)

                dt_model_dropdown = gr.Dropdown(
                    choices=MODEL_OPTIONS,
                    value=DEFAULT_MODEL,
                    label="Model",
                    show_label=True,
                    interactive=True,
                )
                gr.Markdown(
                    f"<p style='font-size:0.8rem; color:#666; margin-top:2px;'>"
                    f"{MODEL_NOTE}</p>"
                )

                # Chatbot display — initial greeting pre-loaded
                dt_chatbot = gr.Chatbot(
                    value=list(_DT_INITIAL_MESSAGES),
                    label="Decision Tree Analysis",
                    height=520,
                    show_label=False,
                    render_markdown=True,
                )

                # Input row
                with gr.Row():
                    dt_textbox = gr.Textbox(
                        placeholder=(
                            "Describe your analysis or answer the question above…"
                        ),
                        label="Your message",
                        lines=2,
                        max_lines=6,
                        show_label=False,
                        scale=8,
                    )
                    dt_submit = gr.Button("Send", scale=1, variant="primary")

                dt_clear_btn = gr.Button(
                    "Start New Analysis", variant="secondary", size="sm"
                )

                # Hidden state: display history and PydanticAI message history
                dt_display_state = gr.State(list(_DT_INITIAL_MESSAGES))
                dt_pydantic_state = gr.State([])

                # Wire up submit (button click and Enter key)
                _dt_inputs = [
                    dt_textbox,
                    dt_display_state,
                    dt_pydantic_state,
                    dt_model_dropdown,
                ]
                _dt_outputs = [
                    dt_chatbot,
                    dt_display_state,
                    dt_pydantic_state,
                    dt_textbox,
                ]

                dt_submit.click(
                    fn=dt_chat,
                    inputs=_dt_inputs,
                    outputs=_dt_outputs,
                )
                dt_textbox.submit(
                    fn=dt_chat,
                    inputs=_dt_inputs,
                    outputs=_dt_outputs,
                )

                # Wire up clear button
                dt_clear_btn.click(
                    fn=dt_clear,
                    inputs=[],
                    outputs=_dt_outputs,
                )

        # ── Shared footer ──────────────────────────────────────────────────
        gr.HTML(
            "<div style='text-align:center; margin-top:12px; "
            "font-size:0.75rem; color:#999;'>"
            "pubHealthLLM v1 · "
            "Data: CDC PLACES 2023, CDC MMWR 2022–2024, CDC NCHS Mortality 1999–2017"
            "</div>"
        )

    return demo


# ---------------------------------------------------------------------------
# Direct launch
# ---------------------------------------------------------------------------


def launch(share: bool = True, server_port: int = 7860) -> None:
    """
    Build and launch the Gradio app.

    Args:
        share:       If True, create a public Gradio share link.
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
