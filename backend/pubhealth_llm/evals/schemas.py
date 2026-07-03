# backend/pubhealth_llm/evals/schemas.py
"""Pydantic schemas for the pubHealthLLM eval harness."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ExpectedFact(BaseModel):
    """A single numeric fact to verify against the agent response."""
    metric: str = Field(description="Human-readable metric name, e.g. 'Diabetes'")
    location: str
    expected_value: float
    tolerance: float = Field(description="Max abs deviation before failing")
    unit: str = Field(default="% of adults")
    year: Optional[int] = None


class GoldItem(BaseModel):
    """One labeled evaluation item."""
    id: str
    question: str
    data_sources: list[str] = Field(description="['cdc_places','mmwr','mortality','none']")
    expected_tools: list[str] = Field(description="Tool names that MUST be called")
    expected_facts: list[ExpectedFact] = Field(default_factory=list)
    expected_source_ids: list[str] = Field(
        default_factory=list,
        description="MMWR PDF filenames expected in retrieved results, e.g. ['mm7301a1-H.pdf']",
    )
    is_answerable: bool = Field(
        default=True,
        description="False for out-of-domain items where abstention is correct",
    )
    rubric: str = Field(description="Short note for human review / judge context")


class ToolEvent(BaseModel):
    """One tool call + return captured during an eval run."""
    name: str
    args: dict[str, Any]
    content: str


class ItemResult(BaseModel):
    """Eval result for a single gold item."""
    item_id: str
    question: str
    data_sources: list[str]
    is_answerable: bool

    # Tool selection (all data sources)
    tool_selection_score: float = Field(description="Fraction of expected tools actually called")

    # Numeric match (cdc_places + mortality items only)
    numeric_match_score: Optional[float] = None

    # Retrieval (mmwr items only)
    retrieval_recall_at_1: Optional[float] = None
    retrieval_recall_at_3: Optional[float] = None
    retrieval_mrr: Optional[float] = None

    # LLM judge (skipped when --quick or no creds)
    judge_faithfulness: Optional[float] = None
    judge_correctness: Optional[float] = None
    judge_justification: Optional[str] = None

    # Abstention (ood items)
    abstention_ok: bool = True

    # Derived
    overall_pass: bool
    notes: str = ""


class EvalReport(BaseModel):
    """Aggregate eval report for one run."""
    timestamp: str
    model: str
    judge_model: str
    quick_mode: bool
    total_items: int
    item_results: list[ItemResult]

    # Aggregate metrics (NaN if no items of that type)
    tool_accuracy: float
    numeric_accuracy: float
    retrieval_recall_at_1: float
    retrieval_recall_at_3: float
    retrieval_mrr: float
    judge_faithfulness: float
    judge_correctness: float
    abstention_accuracy: float
    overall_score: float
