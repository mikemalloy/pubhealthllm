"""
Application layer for pubHealthLLM.

Modules:
    schemas     — Pydantic models for structured agent output
    tools       — PydanticAI tool definitions (MMWR search, SQL queries)
    agent       — orchestration agent that selects and calls tools
    gradio_app  — Gradio ChatInterface for the demo UI
"""
