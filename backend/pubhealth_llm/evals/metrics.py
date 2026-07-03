# backend/pubhealth_llm/evals/metrics.py
"""Pure metric functions for the pubHealthLLM eval harness."""

import re
from typing import Optional

from pubhealth_llm.app.schemas import PublicHealthResponse

_MMWR_SOURCE_RE = re.compile(r"Source:\s*(mm[\w-]+\.pdf)")


def recall_at_k(retrieved: list[str], expected: list[str], k: int) -> float:
    """Fraction of expected sources found in retrieved[:k]. 1.0 if expected is empty."""
    if not expected:
        return 1.0
    if not retrieved:
        return 0.0
    top_k = set(retrieved[:k])
    hits = sum(1 for e in expected if e in top_k)
    return hits / len(expected)


def mrr(retrieved: list[str], expected: list[str]) -> float:
    """Mean Reciprocal Rank: 1/rank of first expected source. 1.0 if expected empty."""
    if not expected:
        return 1.0
    expected_set = set(expected)
    for rank, doc in enumerate(retrieved, 1):
        if doc in expected_set:
            return 1.0 / rank
    return 0.0


def tool_selection_accuracy(tools_called: list[str], expected_tools: list[str]) -> float:
    """Fraction of expected tools that appear in tools_called. 1.0 if expected empty."""
    if not expected_tools:
        return 1.0
    called_set = set(tools_called)
    hits = sum(1 for t in expected_tools if t in called_set)
    return hits / len(expected_tools)


def numeric_match(actual: float, expected: float, tolerance: float) -> bool:
    """True iff abs(actual - expected) <= tolerance."""
    return abs(actual - expected) <= tolerance


def citation_check(cited_sources: list[str], retrieved_source_ids: list[str]) -> float:
    """Fraction of cited_sources that appear in retrieved_source_ids. 1.0 if empty."""
    if not cited_sources:
        return 1.0
    retrieved_set = set(retrieved_source_ids)
    hits = sum(1 for s in cited_sources if s in retrieved_set)
    return hits / len(cited_sources)


def abstention_check(response: PublicHealthResponse, is_answerable: bool) -> bool:
    """For unanswerable (OOD) items: passes if statistics is empty.
    For answerable items: always passes (abstention not required)."""
    if is_answerable:
        return True
    return len(response.statistics) == 0


def parse_mmwr_sources(tool_content: str) -> list[str]:
    """Extract ordered, deduplicated MMWR PDF filenames from tool return content.

    Parses lines like: '[Result 1 | Source: mm7301a1-H.pdf | Relevance: 0.92]'
    """
    seen: set[str] = set()
    result: list[str] = []
    for match in _MMWR_SOURCE_RE.finditer(tool_content):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result
