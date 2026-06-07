"""
Phase B5 — Fail-fast startup validation tests.

Tests verify that the FastAPI lifespan handler:
1. Starts cleanly when config + data are present (success path).
2. Raises when validate_model_config() fails (model failure path).
3. Raises RuntimeError when _DATA_DIR points to a nonexistent path (data failure path).
"""

import pytest
from starlette.testclient import TestClient


def test_startup_success():
    """Lifespan starts cleanly when config and data are both present.

    The conftest autouse fixture loads .env (which has ANTHROPIC_API_KEY),
    and real data exists at backend/data/. No exception should be raised.
    """
    import server  # noqa: PLC0415

    with TestClient(server.app, raise_server_exceptions=True):
        pass  # If we get here, startup succeeded


def test_startup_model_failure(monkeypatch):
    """Lifespan raises when validate_model_config raises ValueError.

    Monkeypatches the function in server's namespace (where it was imported).
    """
    import server  # noqa: PLC0415

    def bad_model_config():
        raise ValueError("bad model config")

    monkeypatch.setattr("server.validate_model_config", bad_model_config)

    with pytest.raises(ValueError):
        with TestClient(server.app, raise_server_exceptions=True):
            pass


def test_startup_data_failure(monkeypatch, tmp_path):
    """Lifespan raises RuntimeError when _DATA_DIR points to a nonexistent path.

    Monkeypatches _DATA_DIR in server's namespace so the lifespan checks
    a directory that doesn't exist.
    """
    import server  # noqa: PLC0415

    nonexistent = tmp_path / "nonexistent"
    monkeypatch.setattr("server._DATA_DIR", nonexistent)

    with pytest.raises(RuntimeError, match="Missing required data"):
        with TestClient(server.app, raise_server_exceptions=True):
            pass


def test_startup_data_failure_chroma(monkeypatch, tmp_path):
    """Lifespan raises RuntimeError when chroma_db is absent but healthgpt.db exists.

    Creates a healthgpt.db file so the first check passes, then leaves
    chroma_db absent. Exercises the is_dir() branch and would have caught
    the exists() → is_dir() bug.
    """
    import server  # noqa: PLC0415

    # First check passes — db file is present
    (tmp_path / "healthgpt.db").touch()
    # chroma_db is intentionally absent

    monkeypatch.setattr("server._DATA_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="Missing required data"):
        with TestClient(server.app, raise_server_exceptions=True):
            pass


def test_startup_vector_store_load_failure(monkeypatch):
    """Lifespan raises RuntimeError when check_vector_store raises a load failure.

    Monkeypatches server.check_vector_store (in server's namespace) to simulate
    chromadb collection failing to load. Keeps the test fully offline.
    """
    import server  # noqa: PLC0415

    def fail_load():
        raise RuntimeError("MMWR vector store failed to load")

    monkeypatch.setattr("server.check_vector_store", fail_load)

    with pytest.raises(RuntimeError, match="vector store"):
        with TestClient(server.app, raise_server_exceptions=True):
            pass


def test_startup_vector_store_empty(monkeypatch):
    """Lifespan raises RuntimeError when check_vector_store raises an empty-store error.

    Monkeypatches server.check_vector_store (in server's namespace) to simulate
    the collection loading but having zero documents. Keeps the test fully offline.
    """
    import server  # noqa: PLC0415

    def fail_empty():
        raise RuntimeError("MMWR vector store is empty")

    monkeypatch.setattr("server.check_vector_store", fail_empty)

    with pytest.raises(RuntimeError, match="vector store"):
        with TestClient(server.app, raise_server_exceptions=True):
            pass
