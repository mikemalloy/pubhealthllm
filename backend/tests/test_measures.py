"""Tests for GET /measures — Phase B2.

Two groups:
1. Route tests  — mock list_available_measures, no DB needed.
2. Data-function tests — use real DB via db_path fixture (skip if absent).
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


_FAKE_ROWS = [
    {"measure_id": "DIABETES", "measure": "Diabetes among adults", "short_text": "Diabetes", "category": "Chronic Disease"},
    {"measure_id": "OBESITY", "measure": "Obesity among adults",  "short_text": "Obesity",  "category": "Chronic Disease"},
]


@pytest.fixture
def client():
    from server import app
    return TestClient(app)


@pytest.fixture
def mock_list():
    """Patch list_available_measures so no DB is touched."""
    with patch("server.list_available_measures", return_value=_FAKE_ROWS) as m:
        yield m


# ---------------------------------------------------------------------------
# Route tests (offline)
# ---------------------------------------------------------------------------

def test_measures_returns_200(client, mock_list):
    resp = client.get("/measures")
    assert resp.status_code == 200


def test_measures_returns_list(client, mock_list):
    resp = client.get("/measures")
    assert isinstance(resp.json(), list)


def test_measures_items_have_required_keys(client, mock_list):
    resp = client.get("/measures")
    for item in resp.json():
        assert "measure_id" in item
        assert "measure" in item
        assert "short_text" in item
        assert "category" in item


def test_measures_returns_correct_count(client, mock_list):
    resp = client.get("/measures")
    assert len(resp.json()) == 2


def test_measures_category_filter_passed_through(client):
    with patch("server.list_available_measures", return_value=[_FAKE_ROWS[0]]) as m:
        resp = client.get("/measures?category=Chronic+Disease")
    assert resp.status_code == 200
    m.assert_called_once_with("Chronic Disease")


def test_measures_no_category_passes_none(client, mock_list):
    client.get("/measures")
    mock_list.assert_called_once_with(None)


def test_measures_returns_empty_list_when_no_data(client):
    """GET /measures returns 200 [] when the data function returns an empty list."""
    with patch("server.list_available_measures", return_value=[]):
        resp = client.get("/measures")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Data-function tests (require real DB — skipped offline)
# ---------------------------------------------------------------------------

def test_list_available_measures_returns_nonempty(db_path):
    from pubhealth_llm.app.tools import list_available_measures
    result = list_available_measures()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_available_measures_items_have_required_keys(db_path):
    from pubhealth_llm.app.tools import list_available_measures
    result = list_available_measures()
    for item in result:
        assert "measure_id" in item
        assert "measure" in item
        assert "short_text" in item
        assert "category" in item


def test_list_available_measures_category_filter(db_path):
    from pubhealth_llm.app.tools import list_available_measures
    filtered = list_available_measures(category="Chronic")
    assert all("hronic" in item["category"] for item in filtered)


def test_list_available_measures_returns_empty_list_on_aurora_error(monkeypatch):
    """Returns [] (not an exception) when Aurora returns no data."""
    import pubhealth_llm.app.tools as tools_module
    monkeypatch.setattr(tools_module, "_query_db", lambda *_a, **_kw: [])
    result = tools_module.list_available_measures()
    assert result == []
