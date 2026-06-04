"""
Full Data Ingestion Pipeline Orchestrator.

Runs all ingestion steps in order:
  1. Download CDC PLACES CSV and load into SQLite
  2. Download recent MMWR PDFs from CDC website
  3. Build ChromaDB vector database from the PDFs

This is the single command users run to set up all data sources
before launching the Gradio app.

Estimated runtime: 5–15 minutes depending on internet speed.

Usage:
    python -m data_ingestion.run_ingestion
    python -m data_ingestion.run_ingestion --skip-places
    python -m data_ingestion.run_ingestion --skip-mmwr
    python -m data_ingestion.run_ingestion --force-download
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parents[2] / "data" / "healthpub.db"
PDF_DIR = Path(__file__).parents[2] / "data" / "mmwr_pdfs"
CHROMA_DIR = Path(__file__).parents[2] / "data" / "chroma_db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step runners with timing
# ---------------------------------------------------------------------------


def _banner(message: str) -> None:
    """Print a visually distinct section header."""
    width = 60
    print("\n" + "=" * width)
    print(f"  {message}")
    print("=" * width + "\n")


def step_places(force_download: bool = False) -> bool:
    """
    Run CDC PLACES download and SQLite ingestion.

    Args:
        force_download: Re-download CSV even if cached locally.

    Returns:
        True on success, False on failure.
    """
    _banner("Step 1 / 3  —  CDC PLACES → SQLite")
    from pubhealth_llm.data_ingestion import download_cdc_places

    t0 = time.time()
    try:
        download_cdc_places.run(force_download=force_download)
        elapsed = time.time() - t0
        logger.info("CDC PLACES step completed in %.1f s", elapsed)
        return True
    except Exception as exc:
        logger.error("CDC PLACES step FAILED: %s", exc, exc_info=True)
        return False


def step_mmwr(years_back: int = 3) -> bool:
    """
    Run MMWR PDF download step.

    Args:
        years_back: Number of years of reports to fetch.

    Returns:
        True on success, False on failure.
    """
    _banner("Step 2 / 3  —  MMWR PDFs → disk")
    from pubhealth_llm.data_ingestion import download_mmwr

    t0 = time.time()
    try:
        paths = download_mmwr.run(years_back=years_back)
        elapsed = time.time() - t0
        logger.info(
            "MMWR download completed in %.1f s — %d PDFs on disk",
            elapsed,
            len(paths),
        )
        return True
    except Exception as exc:
        logger.error("MMWR download step FAILED: %s", exc, exc_info=True)
        return False


def step_vector_db() -> bool:
    """
    Run ChromaDB build step.

    Returns:
        True on success, False on failure.
    """
    _banner("Step 3 / 3  —  MMWR PDFs → ChromaDB")
    from pubhealth_llm.data_ingestion import build_vector_db

    t0 = time.time()
    try:
        build_vector_db.run()
        elapsed = time.time() - t0
        logger.info("Vector DB build completed in %.1f s", elapsed)
        return True
    except Exception as exc:
        logger.error("Vector DB build FAILED: %s", exc, exc_info=True)
        return False


def step_mortality(force_download: bool = False) -> bool:
    """
    Run CDC mortality data download and SQLite ingestion.

    This step is optional — failure here does not prevent the rest of
    the app from working. The mortality tools gracefully report that
    data is unavailable if this step has not been run.

    Args:
        force_download: Re-download CSV even if cached locally.

    Returns:
        True on success, False on failure (non-fatal).
    """
    _banner("Step 4 / 4  —  CDC Mortality → SQLite  (optional)")
    from pubhealth_llm.data_ingestion import download_mortality

    t0 = time.time()
    try:
        download_mortality.run(force_download=force_download)
        elapsed = time.time() - t0
        logger.info("Mortality ingestion completed in %.1f s", elapsed)
        return True
    except Exception as exc:
        logger.error(
            "Mortality ingestion FAILED (non-fatal): %s", exc, exc_info=True
        )
        print(
            "\n  WARNING: Mortality data ingestion failed. "
            "The app will still work — mortality tools will report data unavailable.\n"
        )
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="pubHealthLLM data ingestion pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--skip-places",
        action="store_true",
        help="Skip the CDC PLACES download/load step",
    )
    parser.add_argument(
        "--skip-mmwr",
        action="store_true",
        help="Skip the MMWR PDF download step",
    )
    parser.add_argument(
        "--skip-vector-db",
        action="store_true",
        help="Skip the ChromaDB vector DB build step",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download CDC PLACES CSV even if cached",
    )
    parser.add_argument(
        "--years-back",
        type=int,
        default=3,
        help="Number of years of MMWR reports to download",
    )
    parser.add_argument(
        "--skip-mortality",
        action="store_true",
        help="Skip the CDC mortality data download/load step",
    )
    return parser.parse_args()


def main() -> None:
    """
    Orchestrate the full ingestion pipeline.

    Runs each step in sequence; a failed step is logged but does not
    abort subsequent steps so partial data is still usable.
    """
    args = parse_args()
    overall_start = time.time()

    print("\n" + "=" * 60)
    print("  pubHealthLLM — Data Ingestion Pipeline")
    print("  This will take 5–20 minutes on first run.")
    print("=" * 60)

    results: dict[str, bool] = {}

    if not args.skip_places:
        results["CDC PLACES"] = step_places(force_download=args.force_download)
    else:
        logger.info("Skipping CDC PLACES step (--skip-places)")

    if not args.skip_mmwr:
        results["MMWR PDFs"] = step_mmwr(years_back=args.years_back)
    else:
        logger.info("Skipping MMWR download step (--skip-mmwr)")

    if not args.skip_vector_db:
        results["ChromaDB"] = step_vector_db()
    else:
        logger.info("Skipping ChromaDB build step (--skip-vector-db)")

    if not args.skip_mortality:
        # Mortality failure is non-fatal — warn but don't abort
        results["CDC Mortality"] = step_mortality(
            force_download=args.force_download
        )
    else:
        logger.info("Skipping mortality download step (--skip-mortality)")

    # Summary report
    total_elapsed = time.time() - overall_start
    _banner(f"Ingestion Summary  ({total_elapsed:.0f}s total)")
    all_ok = True
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        icon = "✓" if success else "✗"
        print(f"  {icon}  {name:<20} {status}")
        if not success:
            all_ok = False

    if all_ok:
        print("\n  All steps succeeded.  Run `python main.py` to start the app.")
    else:
        print("\n  Some steps failed.  Check logs above for details.")
        print("  The app may still work with partial data.")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
