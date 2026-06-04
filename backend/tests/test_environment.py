"""
Tests for environment configuration.

Verifies required API keys are loaded from .env and have plausible values.
Does NOT make network calls.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")


def test_anthropic_api_key_is_set():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    assert key, (
        "ANTHROPIC_API_KEY is not set. "
        "Copy .env.example to .env and add your Anthropic key."
    )


def test_anthropic_api_key_not_placeholder():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    assert key != "sk-ant-your-key-here", (
        "ANTHROPIC_API_KEY still has the placeholder value from .env.example."
    )


def test_anthropic_api_key_non_empty_string():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    assert len(key) > 10, f"ANTHROPIC_API_KEY is too short ({len(key)} chars)."


def test_clerk_jwks_url_is_set():
    url = os.getenv("CLERK_JWKS_URL", "")
    assert url, (
        "CLERK_JWKS_URL is not set. "
        "Copy from the Drug Discovery project .env."
    )


def test_clerk_jwks_url_looks_like_url():
    url = os.getenv("CLERK_JWKS_URL", "")
    assert url.startswith("https://"), f"CLERK_JWKS_URL must be an https URL, got: {url!r}"


def test_clerk_secret_key_is_set():
    key = os.getenv("CLERK_SECRET_KEY", "")
    assert key, "CLERK_SECRET_KEY is not set."


def test_env_file_exists():
    env_path = Path(__file__).parents[1] / ".env"
    assert env_path.exists(), ".env not found. Run: cp .env.example .env"


def test_data_directory_exists():
    data_dir = Path(__file__).parents[1] / "data"
    assert data_dir.is_dir(), "data/ directory missing from backend/."
