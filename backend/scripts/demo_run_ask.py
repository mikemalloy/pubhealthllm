"""
Demo script — live end-to-end round-trip through run_ask.

Run from backend/ with venv active and .env present:
    python scripts/demo_run_ask.py

Calls run_ask three times with real LLM + real tools (no mocks).
Prints each AskResponse as indented JSON.
Costs a few cents in Anthropic API usage.
"""
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

from pubhealth_llm.app.orchestrator import run_ask  # noqa: E402

QUESTIONS = [
    ("greeting / capability", "What can you do?"),
    ("county data", "What is the diabetes rate in Travis County, TX?"),
    ("comparison", "Compare obesity rates in Cook County, IL and Harris County, TX"),
]


async def main() -> None:
    for label, question in QUESTIONS:
        print(f"\n{'='*70}")
        print(f"[{label}]")
        print(f"Q: {question}")
        print("─" * 70)
        response = await run_ask(question)
        print(json.dumps(response.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
