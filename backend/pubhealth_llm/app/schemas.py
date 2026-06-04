"""
Pydantic output schemas for pubHealthLLM agent responses.

All agent responses are validated against PublicHealthResponse before
being returned to the UI.  This ensures the Gradio interface always
receives a predictable structure it can render as formatted markdown.

Usage:
    from pubhealth_llm.app.schemas import PublicHealthResponse
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------


class StatisticEntry(BaseModel):
    """A single named statistic with its value, units, source, and year."""

    metric: str = Field(description="Human-readable name of the health measure")
    value: float = Field(description="Numeric value of the statistic")
    unit: str = Field(description="Units (e.g. '% of adults', 'per 100k')")
    location: str = Field(description="Geographic scope (county, state, national)")
    year: Optional[int] = Field(None, description="Data collection year if known")
    source: str = Field(description="Dataset or report the value came from")


class EvidenceItem(BaseModel):
    """A single piece of evidence retrieved from a data source."""

    finding: str = Field(description="The key finding or fact")
    source_type: str = Field(
        description="'mmwr_report' or 'cdc_places' or 'comparison'",
    )
    confidence: str = Field(
        description="'high', 'moderate', or 'low' based on data quality",
    )


# ---------------------------------------------------------------------------
# Primary response model
# ---------------------------------------------------------------------------


class PublicHealthResponse(BaseModel):
    """
    Structured response from the pubHealthLLM agent.

    Every field is populated from actual tool call results — the agent
    is instructed never to fabricate values not returned by its tools.

    This model is rendered as formatted markdown in the Gradio interface.
    """

    summary: str = Field(
        description=(
            "A compelling narrative paragraph written for a fiscally conservative, "
            "non-technical decision maker — a county commissioner, a budget director, "
            "a department head who did not read the briefing packet. Do not open with "
            "a statistic. Open with the human reality or the fiscal consequence, then "
            "ground it in the retrieved data. Use a vivid analogy where it makes the "
            "scale concrete. Give them a line they can say out loud in a room. Write "
            "as a seasoned public health official would speak — authoritative, clear, "
            "persuasive — not as a database report. All claims must come from tool "
            "results; never invent figures. Do not use bullet points or sub-headers "
            "in this field."
        )
    )

    evidence: list[str] = Field(description="Key findings from data sources, one per item.")

    statistics: list[StatisticEntry] = Field(
        default_factory=list,
        description="Numeric statistics from CDC PLACES. Empty list if none retrieved.",
    )

    historical_context: Optional[str] = Field(
        None,
        description="Relevant MMWR outbreak history or trends. Null if not searched.",
    )

    caveats: list[str] = Field(
        default_factory=list,
        description="Data limitations and uncertainties. Include at least one.",
    )

    sources: list[str] = Field(
        default_factory=list,
        description="Citations for all data used.",
    )

    recommendations: Optional[str] = Field(
        None,
        description="Evidence-based next steps, only if clearly supported by data.",
    )

    disclaimer: str = Field(
        default=(
            "This tool provides decision support only. All recommendations "
            "require validation by qualified public health professionals. "
            "Data reflects historical surveillance and may not capture "
            "current conditions."
        ),
        description="Standard disclaimer.",
    )

    # -----------------------------------------------------------------------
    # Rendering helpers
    # -----------------------------------------------------------------------

    def to_markdown(self) -> str:
        """
        Render this response as a GitHub-flavored markdown string.

        Used by the Gradio interface to display agent output in a
        structured, readable format for public health professionals.

        Returns:
            Multi-section markdown string.
        """
        lines: list[str] = []

        # Summary
        lines.append(f"## Summary\n{self.summary}\n")

        # Key Findings
        if self.evidence:
            lines.append("## Key Findings")
            for item in self.evidence:
                lines.append(f"- {item}")
            lines.append("")

        # Statistics table
        if self.statistics:
            lines.append("## Statistics")
            lines.append("| Metric | Value | Location | Year | Source |")
            lines.append("|--------|-------|----------|------|--------|")
            for s in self.statistics:
                year_str = str(s.year) if s.year else "N/A"
                lines.append(
                    f"| {s.metric} | {s.value} {s.unit} "
                    f"| {s.location} | {year_str} | {s.source} |"
                )
            lines.append("")

        # Historical context
        if self.historical_context:
            lines.append(f"## Historical Context\n{self.historical_context}\n")

        # Recommendations
        if self.recommendations:
            lines.append(f"## Recommendations\n{self.recommendations}\n")

        # Caveats
        if self.caveats:
            lines.append("## Caveats & Limitations")
            for caveat in self.caveats:
                lines.append(f"- {caveat}")
            lines.append("")

        # Sources
        if self.sources:
            lines.append("## Sources")
            for source in self.sources:
                lines.append(f"- {source}")
            lines.append("")

        # Disclaimer
        lines.append(f"---\n*{self.disclaimer}*")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool output models (intermediate structures used by tools.py)
# ---------------------------------------------------------------------------


class MMWRSearchResult(BaseModel):
    """A single result from the MMWR ChromaDB vector search."""

    chunk_text: str = Field(description="The retrieved text passage")
    source_file: str = Field(description="MMWR PDF filename")
    relevance_score: float = Field(description="Cosine similarity score (0–1)")
    chunk_index: int = Field(description="Position of chunk within source document")


class HealthStatResult(BaseModel):
    """Result from a CDC PLACES SQL query for a specific location/measure."""

    location_name: str
    state_abbr: str
    measure: str
    measure_id: str
    data_value: Optional[float]
    data_value_unit: str
    data_value_type: str
    year: Optional[int]
    low_ci: Optional[float] = Field(None, description="Lower confidence interval")
    high_ci: Optional[float] = Field(None, description="Upper confidence interval")
    total_population: Optional[float]


class ComparisonResult(BaseModel):
    """Result from a multi-location comparison query."""

    measure: str
    rows: list[HealthStatResult]
    summary: str = Field(description="Plain-language summary of the comparison")


# ---------------------------------------------------------------------------
# Multi-agent routing schemas (planner → responder / reporter)
# ---------------------------------------------------------------------------


class Plan(BaseModel):
    """
    Routing decision produced by the planner agent.

    The planner classifies the incoming question and chooses where to send it:
      - mode="chat"     → responder (conversational path)
      - mode="artifact" → run_agent reporter (structured report path)
    """

    intent: str = Field(description="One-phrase description of the user's intent")
    mode: Literal["chat", "artifact"] = Field(
        description="Render surface: 'chat' for conversational, 'artifact' for reports"
    )
    artifact_type: Optional[Literal["report", "comparison", "ranking", "mortality"]] = Field(
        None,
        description="Artifact sub-type when mode='artifact'. None is valid.",
    )
    dispatch_target: Literal["responder", "reporter"] = Field(
        description="'responder' for chat path, 'reporter' for full structured report"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Planner's confidence in this routing decision (0.0–1.0)",
    )

    @model_validator(mode="after")
    def _validate_mode_matches_target(self) -> "Plan":
        chat_mode = self.mode == "chat"
        responder_target = self.dispatch_target == "responder"
        if chat_mode != responder_target:
            raise ValueError(
                f"mode='{self.mode}' is incompatible with dispatch_target='{self.dispatch_target}'. "
                "Use mode='chat' with dispatch_target='responder', "
                "or mode='artifact' with dispatch_target='reporter'."
            )
        return self


class ArtifactEnvelope(BaseModel):
    """
    Wraps a structured artifact for the frontend artifact panel.

    For type='report', payload is a serialized PublicHealthResponse (model_dump()).
    Other types (comparison, ranking, mortality) carry their own payload shapes
    — defined by future artifact renderers.
    """

    type: Literal["report", "comparison", "ranking", "mortality"] = Field(
        description="Artifact sub-type"
    )
    title: str = Field(description="Short title shown in the artifact panel header")
    payload: dict = Field(description="Serialized artifact data")


class AskMeta(BaseModel):
    """Execution metadata attached to every AskResponse."""

    intent: str = Field(description="Classified intent string from the planner")
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tool names called during this request",
    )
    model: str = Field(description="Model(s) used, e.g. 'planner+reporter'")
    timing_ms: int = Field(ge=0, description="Wall-clock time from request to response")


class AskResponse(BaseModel):
    """
    Envelope returned by run_ask() — the /ask contract.

    chat_message is always present. artifact is present only when mode='artifact'.

    Wire format (JSON):
        {
          "mode": "chat" | "artifact",
          "chat_message": "...",
          "artifact": { "type": "...", "title": "...", "payload": {...} } | null,
          "meta": { "intent": "...", "tools_used": [], "model": "...", "timing_ms": 0 }
        }
    """

    mode: Literal["chat", "artifact"] = Field(
        description="Render surface chosen by the planner"
    )
    chat_message: str = Field(
        min_length=1,
        description="Always present. For chat: the full response. "
        "For artifact: a one-sentence teaser (first 200 chars of summary)."
    )
    artifact: Optional[ArtifactEnvelope] = Field(
        None,
        description="Present when mode='artifact', null when mode='chat'",
    )
    meta: AskMeta
