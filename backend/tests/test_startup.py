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


def test_startup_aurora_failure(monkeypatch):
    """Lifespan raises RuntimeError when check_aurora_db raises.

    Monkeypatches server.check_aurora_db to simulate Aurora connectivity failure.
    """
    import server  # noqa: PLC0415

    def fail_aurora():
        raise RuntimeError("Aurora connectivity check failed")

    monkeypatch.setattr("server.check_aurora_db", fail_aurora)

    with pytest.raises(RuntimeError, match="Aurora"):
        with TestClient(server.app, raise_server_exceptions=True):
            pass


def test_startup_data_failure_missing_vector_bucket(monkeypatch):
    """Lifespan raises RuntimeError when VECTOR_BUCKET is unset.

    Aurora check passes (monkeypatched), then VECTOR_BUCKET is empty
    so check_vector_store() raises.
    """
    import server  # noqa: PLC0415
    import pubhealth_llm.app.tools as tools_mod

    # Aurora check passes
    monkeypatch.setattr("server.check_aurora_db", lambda: None)
    monkeypatch.setattr(tools_mod, "VECTOR_BUCKET", "")

    with pytest.raises(RuntimeError, match="VECTOR_BUCKET"):
        with TestClient(server.app, raise_server_exceptions=True):
            pass


def test_startup_vector_store_load_failure(monkeypatch):
    """Lifespan raises RuntimeError when check_vector_store raises a load failure.

    Monkeypatches both Aurora and vector store checks to stay fully offline.
    """
    import server  # noqa: PLC0415

    monkeypatch.setattr("server.check_aurora_db", lambda: None)

    def fail_load():
        raise RuntimeError("MMWR vector store failed to load")

    monkeypatch.setattr("server.check_vector_store", fail_load)

    with pytest.raises(RuntimeError, match="vector store"):
        with TestClient(server.app, raise_server_exceptions=True):
            pass


def test_startup_vector_store_empty(monkeypatch):
    """Lifespan raises RuntimeError when check_vector_store raises an empty-store error.

    Monkeypatches both Aurora and vector store checks to stay fully offline.
    """
    import server  # noqa: PLC0415

    monkeypatch.setattr("server.check_aurora_db", lambda: None)

    def fail_empty():
        raise RuntimeError("MMWR vector store is empty")

    monkeypatch.setattr("server.check_vector_store", fail_empty)

    with pytest.raises(RuntimeError, match="vector store"):
        with TestClient(server.app, raise_server_exceptions=True):
            pass
