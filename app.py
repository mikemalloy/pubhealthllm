"""
HuggingFace Spaces entry point for pubHealthLLM.

HuggingFace Spaces expects the Gradio app to be in a file called app.py
at the repo root and to be served on 0.0.0.0:7860.

This file is a thin wrapper — all application logic lives in
pubhealth_llm/app/gradio_app.py.
"""

from pubhealth_llm.app.gradio_app import build_app

app = build_app()

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
