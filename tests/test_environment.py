"""
Tests for environment configuration and API key presence.

These tests do NOT make network calls — they only verify that
required variables are loaded from .env and have plausible values.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")


def test_groq_api_key_is_set():
    """GROQ_API_KEY must be present in the environment."""
    key = os.getenv("GROQ_API_KEY", "")
    assert key, (
        "GROQ_API_KEY is not set. "
        "Copy .env.example to .env and add your Groq API key."
    )


def test_groq_api_key_not_placeholder():
    """GROQ_API_KEY must not be the template placeholder value."""
    key = os.getenv("GROQ_API_KEY", "")
    assert key != "gsk_your_groq_api_key_here", (
        "GROQ_API_KEY still contains the placeholder value from .env.example. "
        "Replace it with your actual Groq API key."
    )


def test_groq_api_key_non_empty_string():
    """GROQ_API_KEY must have meaningful length (not a 1-char typo)."""
    key = os.getenv("GROQ_API_KEY", "")
    assert len(key) > 10, (
        f"GROQ_API_KEY is too short ({len(key)} chars) — likely malformed."
    )


def test_env_file_exists():
    """The .env file itself must be present (not just .env.example)."""
    env_path = Path(__file__).parents[1] / ".env"
    assert env_path.exists(), (
        ".env file not found. Run: cp .env.example .env  then add your API key."
    )


def test_data_directory_exists():
    """The data/ directory must exist (created by directory setup)."""
    data_dir = Path(__file__).parents[1] / "data"
    assert data_dir.is_dir(), "data/ directory is missing from the project root."
