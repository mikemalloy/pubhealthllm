"""
pubHealthLLM — Main Entry Point.

Launches the Gradio public health decision intelligence interface.

Before launching, this script:
  1. Loads environment variables from .env
  2. Verifies GROQ_API_KEY is set
  3. Checks that the data pipeline has been run (SQLite + ChromaDB exist)
  4. Warns (but does not block) if data is missing

Usage:
    python main.py
    python main.py --port 7861 --no-share
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = Path("data") / "healthgpt.db"
CHROMA_DIR = Path("data") / "chroma_db"
PDF_DIR = Path("data") / "mmwr_pdfs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pre-launch checks
# ---------------------------------------------------------------------------


def check_environment() -> bool:
    """
    Verify that required environment variables are present.

    Returns:
        True if all required variables are set, False otherwise.
    """
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "\n[ERROR] ANTHROPIC_API_KEY is not set.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Add your Anthropic API key (https://console.anthropic.com)\n"
            "  3. Re-run: python main.py\n"
        )
        return False
    logger.info("ANTHROPIC_API_KEY detected.")
    return True


def check_data_pipeline() -> dict[str, bool]:
    """
    Check which components of the data pipeline have been built.

    Returns:
        Dict mapping component name → exists (bool).
    """
    status = {
        "SQLite DB (CDC PLACES)": DB_PATH.exists() and DB_PATH.stat().st_size > 1_000_000,
        "ChromaDB (MMWR vectors)": CHROMA_DIR.exists() and any(CHROMA_DIR.iterdir()),
        "MMWR PDFs": PDF_DIR.exists() and any(PDF_DIR.glob("*.pdf")),
    }
    return status


def print_data_status(status: dict[str, bool]) -> bool:
    """
    Print the data pipeline status to the terminal.

    Args:
        status: Dict from check_data_pipeline().

    Returns:
        True if all components are ready, False if any are missing.
    """
    all_ready = all(status.values())
    print("\n--- Data Pipeline Status ---")
    for name, ready in status.items():
        icon = "✓" if ready else "✗"
        label = "Ready" if ready else "NOT FOUND"
        print(f"  {icon}  {name:<35} {label}")

    if not all_ready:
        missing = [k for k, v in status.items() if not v]
        print(
            f"\n  WARNING: {len(missing)} component(s) not ready: {', '.join(missing)}"
        )
        print(
            "  The app will launch but may return incomplete responses.\n"
            "  Run the full pipeline first:\n"
            "      python -m pubhealth_llm.data_ingestion.run_ingestion\n"
        )
    else:
        print("\n  All data components ready.")

    print("----------------------------\n")
    return all_ready


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the app launcher."""
    parser = argparse.ArgumentParser(
        description="Launch the pubHealthLLM Gradio interface",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Local port for the Gradio server",
    )
    parser.add_argument(
        "--no-share",
        action="store_true",
        help="Disable the public Gradio share link (local demo only)",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip pre-launch environment and data checks",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Main entry point: validate environment, check data, launch Gradio.
    """
    args = parse_args()

    print("\n" + "=" * 55)
    print("  pubHealthLLM — Public Health Decision Intelligence")
    print("=" * 55)

    if not args.skip_checks:
        # 1. Environment check
        if not check_environment():
            sys.exit(1)

        # 2. Data pipeline check (warn, don't exit)
        data_status = check_data_pipeline()
        print_data_status(data_status)
    else:
        load_dotenv()
        logger.info("Skipping pre-launch checks (--skip-checks)")

    # 3. Import and launch — deferred so dotenv is loaded first
    print(f"  Launching Gradio on port {args.port} …")
    share = not args.no_share
    if share:
        print("  A public share link will be created (use --no-share to disable).")
    print()

    from pubhealth_llm.app.gradio_app import launch
    launch(share=share, server_port=args.port)


if __name__ == "__main__":
    main()
