#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_tests.sh — pubHealthLLM test runner
#
# Activates the project virtual environment and runs the full pytest suite,
# or a specific subset if arguments are passed.
#
# Usage:
#   ./run_tests.sh                        # run all tests
#   ./run_tests.sh tests/test_mortality_db.py   # run one file
#   ./run_tests.sh -k "mortality"         # run tests matching a keyword
#   ./run_tests.sh --no-live             # skip tests needing API keys/data
#
# Prerequisites:
#   python -m pubhealth_llm.data_ingestion.download_mortality  # ingest mortality data
#   ANTHROPIC_API_KEY set in .env for live API tests
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_ROOT/.venv"

# Activate virtual environment
if [[ -f "$VENV/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
else
    echo "ERROR: Virtual environment not found at $VENV"
    echo "       Create it with: python -m venv .venv && pip install -e .[dev]"
    exit 1
fi

echo "=========================================================="
echo "  pubHealthLLM Test Suite"
echo "  Python: $(python --version)"
echo "  pytest: $(python -m pytest --version 2>&1 | head -1)"
echo "=========================================================="
echo ""

# Default test targets — all three mortality test files + the existing suite
MORTALITY_TESTS=(
    "tests/test_mortality_db.py"
    "tests/test_mortality_tools.py"
    "tests/test_integration.py"
)

if [[ $# -gt 0 ]]; then
    # Pass all arguments directly to pytest
    python -m pytest "$@" -v
else
    # Run mortality-specific tests first for quick feedback
    echo "--- Mortality DB tests ---"
    python -m pytest "${MORTALITY_TESTS[@]}" -v --tb=short 2>&1 || true

    echo ""
    echo "--- Full suite ---"
    python -m pytest tests/ -v --tb=short
fi
