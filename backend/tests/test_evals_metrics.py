# backend/tests/test_evals_metrics.py
"""Unit tests for eval metric functions. All pure — no network calls."""

import pytest


# ---------------------------------------------------------------------------
# recall_at_k
# ---------------------------------------------------------------------------

def test_recall_at_k_perfect():
    from pubhealth_llm.evals.metrics import recall_at_k
    retrieved = ["a.pdf", "b.pdf", "c.pdf"]
    expected = ["b.pdf"]
    assert recall_at_k(retrieved, expected, k=3) == 1.0


def test_recall_at_k_miss():
    from pubhealth_llm.evals.metrics import recall_at_k
    retrieved = ["a.pdf", "b.pdf", "c.pdf"]
    expected = ["z.pdf"]
    assert recall_at_k(retrieved, expected, k=3) == 0.0


def test_recall_at_k_cutoff():
    """Expected item at position 3 should miss when k=2."""
    from pubhealth_llm.evals.metrics import recall_at_k
    retrieved = ["a.pdf", "b.pdf", "c.pdf"]
    expected = ["c.pdf"]
    assert recall_at_k(retrieved, expected, k=2) == 0.0
    assert recall_at_k(retrieved, expected, k=3) == 1.0


def test_recall_at_k_multiple_expected():
    """Partial hit: 1 of 2 expected in top-3."""
    from pubhealth_llm.evals.metrics import recall_at_k
    retrieved = ["a.pdf", "b.pdf", "c.pdf"]
    expected = ["b.pdf", "z.pdf"]
    assert recall_at_k(retrieved, expected, k=3) == 0.5


def test_recall_at_k_empty_retrieved():
    from pubhealth_llm.evals.metrics import recall_at_k
    assert recall_at_k([], ["a.pdf"], k=3) == 0.0


def test_recall_at_k_empty_expected():
    """No expected sources → recall is 1.0 (vacuously satisfied)."""
    from pubhealth_llm.evals.metrics import recall_at_k
    assert recall_at_k(["a.pdf"], [], k=3) == 1.0


# ---------------------------------------------------------------------------
# mrr
# ---------------------------------------------------------------------------

def test_mrr_first_position():
    from pubhealth_llm.evals.metrics import mrr
    retrieved = ["a.pdf", "b.pdf", "c.pdf"]
    expected = ["a.pdf"]
    assert mrr(retrieved, expected) == pytest.approx(1.0)


def test_mrr_second_position():
    from pubhealth_llm.evals.metrics import mrr
    retrieved = ["a.pdf", "b.pdf", "c.pdf"]
    expected = ["b.pdf"]
    assert mrr(retrieved, expected) == pytest.approx(0.5)


def test_mrr_third_position():
    from pubhealth_llm.evals.metrics import mrr
    retrieved = ["a.pdf", "b.pdf", "c.pdf"]
    expected = ["c.pdf"]
    assert mrr(retrieved, expected) == pytest.approx(1 / 3)


def test_mrr_not_found():
    from pubhealth_llm.evals.metrics import mrr
    assert mrr(["a.pdf", "b.pdf"], ["z.pdf"]) == 0.0


def test_mrr_empty_retrieved():
    from pubhealth_llm.evals.metrics import mrr
    assert mrr([], ["a.pdf"]) == 0.0


def test_mrr_empty_expected():
    """No expected sources → MRR is 1.0 (vacuously satisfied)."""
    from pubhealth_llm.evals.metrics import mrr
    assert mrr(["a.pdf"], []) == 1.0


# ---------------------------------------------------------------------------
# tool_selection_accuracy
# ---------------------------------------------------------------------------

def test_tool_accuracy_perfect():
    from pubhealth_llm.evals.metrics import tool_selection_accuracy
    assert tool_selection_accuracy(
        tools_called=["tool_get_health_statistics", "tool_search_mmwr_reports"],
        expected_tools=["tool_get_health_statistics"],
    ) == 1.0


def test_tool_accuracy_miss():
    from pubhealth_llm.evals.metrics import tool_selection_accuracy
    assert tool_selection_accuracy(
        tools_called=["tool_get_mortality_data"],
        expected_tools=["tool_get_health_statistics"],
    ) == 0.0


def test_tool_accuracy_partial():
    from pubhealth_llm.evals.metrics import tool_selection_accuracy
    assert tool_selection_accuracy(
        tools_called=["tool_get_health_statistics"],
        expected_tools=["tool_get_health_statistics", "tool_search_mmwr_reports"],
    ) == 0.5


def test_tool_accuracy_no_expected_tools():
    """OOD items have empty expected_tools — score is 1.0."""
    from pubhealth_llm.evals.metrics import tool_selection_accuracy
    assert tool_selection_accuracy(tools_called=[], expected_tools=[]) == 1.0


def test_tool_accuracy_called_tools_but_none_expected():
    """OOD: agent called tools anyway — score is still 1.0 (no expectation)."""
    from pubhealth_llm.evals.metrics import tool_selection_accuracy
    assert tool_selection_accuracy(
        tools_called=["tool_get_health_statistics"],
        expected_tools=[],
    ) == 1.0


# ---------------------------------------------------------------------------
# numeric_match
# ---------------------------------------------------------------------------

def test_numeric_match_exact():
    from pubhealth_llm.evals.metrics import numeric_match
    assert numeric_match(actual=9.0, expected=9.0, tolerance=0.5) is True


def test_numeric_match_within_tolerance():
    from pubhealth_llm.evals.metrics import numeric_match
    assert numeric_match(actual=9.3, expected=9.0, tolerance=0.5) is True


def test_numeric_match_outside_tolerance():
    from pubhealth_llm.evals.metrics import numeric_match
    assert numeric_match(actual=10.0, expected=9.0, tolerance=0.5) is False


def test_numeric_match_boundary():
    # Exactly at boundary — should pass (<=, not <)
    from pubhealth_llm.evals.metrics import numeric_match
    assert numeric_match(actual=9.5, expected=9.0, tolerance=0.5) is True


# ---------------------------------------------------------------------------
# citation_check
# ---------------------------------------------------------------------------

def test_citation_check_all_grounded():
    from pubhealth_llm.evals.metrics import citation_check
    score = citation_check(
        cited_sources=["CDC PLACES 2023"],
        retrieved_source_ids=["mm7301a1-H.pdf", "CDC PLACES 2023"],
    )
    assert score == 1.0


def test_citation_check_partial():
    from pubhealth_llm.evals.metrics import citation_check
    score = citation_check(
        cited_sources=["CDC PLACES 2023", "made_up_source"],
        retrieved_source_ids=["CDC PLACES 2023"],
    )
    assert score == 0.5


def test_citation_check_empty_cited():
    from pubhealth_llm.evals.metrics import citation_check
    assert citation_check(cited_sources=[], retrieved_source_ids=["a"]) == 1.0


def test_citation_check_empty_retrieved():
    from pubhealth_llm.evals.metrics import citation_check
    # Citations present but nothing was retrieved → all ungrounded
    assert citation_check(cited_sources=["CDC PLACES 2023"], retrieved_source_ids=[]) == 0.0


# ---------------------------------------------------------------------------
# abstention_check
# ---------------------------------------------------------------------------

def test_abstention_ood_no_stats():
    """OOD item: agent returned no statistics → correct abstention."""
    from pubhealth_llm.evals.metrics import abstention_check
    from pubhealth_llm.app.schemas import PublicHealthResponse
    resp = PublicHealthResponse(
        summary="I don't have crime data.",
        evidence=["No relevant data found."],
        statistics=[],
        sources=[],
        caveats=["Data not available."],
    )
    assert abstention_check(resp, is_answerable=False) is True


def test_abstention_ood_with_stats_fails():
    """OOD item: agent fabricated statistics → abstention fails."""
    from pubhealth_llm.evals.metrics import abstention_check
    from pubhealth_llm.app.schemas import PublicHealthResponse, StatisticEntry
    resp = PublicHealthResponse(
        summary="The crime rate is 15%.",
        evidence=["Crime rate: 15%."],
        statistics=[
            StatisticEntry(
                metric="Crime rate",
                value=15.0,
                unit="%",
                location="Harris County, TX",
                source="Made up",
            )
        ],
        sources=["Made up"],
        caveats=[],
    )
    assert abstention_check(resp, is_answerable=False) is False


def test_abstention_answerable_always_passes():
    """Answerable items never fail abstention check."""
    from pubhealth_llm.evals.metrics import abstention_check
    from pubhealth_llm.app.schemas import PublicHealthResponse
    resp = PublicHealthResponse(
        summary="No data found.",
        evidence=[],
        statistics=[],
        sources=[],
        caveats=[],
    )
    assert abstention_check(resp, is_answerable=True) is True


# ---------------------------------------------------------------------------
# parse_mmwr_sources (helper)
# ---------------------------------------------------------------------------

def test_parse_mmwr_sources_extracts_filenames():
    from pubhealth_llm.evals.metrics import parse_mmwr_sources
    tool_content = (
        "MMWR Search Results for: 'antifungal'\n"
        "[Result 1 | Source: mm7301a1-H.pdf | Relevance: 0.92]\n"
        "text about antifungals...\n"
        "---\n"
        "[Result 2 | Source: mm7303a1-H.pdf | Relevance: 0.81]\n"
        "more text...\n"
    )
    sources = parse_mmwr_sources(tool_content)
    assert sources == ["mm7301a1-H.pdf", "mm7303a1-H.pdf"]


def test_parse_mmwr_sources_empty():
    from pubhealth_llm.evals.metrics import parse_mmwr_sources
    assert parse_mmwr_sources("No results found") == []


def test_parse_mmwr_sources_deduplicates():
    from pubhealth_llm.evals.metrics import parse_mmwr_sources
    content = (
        "[Result 1 | Source: mm7301a1-H.pdf | Relevance: 0.90]\n"
        "[Result 2 | Source: mm7301a1-H.pdf | Relevance: 0.85]\n"
    )
    sources = parse_mmwr_sources(content)
    assert sources == ["mm7301a1-H.pdf"]
