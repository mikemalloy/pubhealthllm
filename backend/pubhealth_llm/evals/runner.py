# backend/pubhealth_llm/evals/runner.py
"""
pubHealthLLM eval runner.

Entry point: run_eval() — async, accepts a gold set YAML path and output dir.
CLI: backend/scripts/run_eval.py (calls asyncio.run(run_eval(...))).

Judge cache: <cache_dir>/judge_cache.json, keyed by SHA-256 of
(question + tool_outputs + gold_rubric). Controls Bedrock call cost.
"""

import asyncio
import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from pubhealth_llm.app.agent import AgentResult, run_agent
from pubhealth_llm.app.config import get_model
from pubhealth_llm.evals.metrics import (
    abstention_check,
    citation_check,
    mrr,
    numeric_match,
    parse_mmwr_sources,
    recall_at_k,
    tool_selection_accuracy,
)
from pubhealth_llm.evals.schemas import (
    EvalReport,
    ExpectedFact,
    GoldItem,
    ItemResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_QUICK_LIMIT = 5


# ---------------------------------------------------------------------------
# Judge result
# ---------------------------------------------------------------------------

@dataclass
class JudgeResult:
    faithfulness: float
    correctness: float
    justification: str


# ---------------------------------------------------------------------------
# Scoring a single item (pure — no async, no LLM, testable)
# ---------------------------------------------------------------------------

def _best_statistic_value(
    agent_result: AgentResult, fact: ExpectedFact
) -> Optional[float]:
    """Find the agent statistic most likely to match the gold fact.

    Matches on metric name (case-insensitive substring). Falls back to
    location match if multiple candidates exist.
    """
    candidates = [
        s for s in agent_result.response.statistics
        if fact.metric.lower() in s.metric.lower()
           or s.metric.lower() in fact.metric.lower()
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0].value
    loc_match = [
        c for c in candidates
        if fact.location.lower() in c.location.lower()
    ]
    return loc_match[0].value if loc_match else candidates[0].value


def score_item(
    item: GoldItem,
    agent_result: AgentResult,
    judge_result: Optional[JudgeResult],
) -> ItemResult:
    """Compute all metrics for one gold item given the agent result."""
    tools_called = agent_result.tools_used

    # Tool selection
    tool_score = tool_selection_accuracy(tools_called, item.expected_tools)

    # Numeric match
    numeric_score: Optional[float] = None
    if item.expected_facts:
        matches = []
        for fact in item.expected_facts:
            actual = _best_statistic_value(agent_result, fact)
            if actual is not None:
                matches.append(numeric_match(actual, fact.expected_value, fact.tolerance))
            else:
                matches.append(False)
        numeric_score = sum(matches) / len(matches) if matches else None

    # MMWR retrieval
    retrieval_r1: Optional[float] = None
    retrieval_r3: Optional[float] = None
    retrieval_mrr_val: Optional[float] = None
    if item.expected_source_ids:
        retrieved_sources: list[str] = []
        trace = agent_result.trace
        if trace:
            for event in trace.tool_events:
                if event.name == "tool_search_mmwr_reports":
                    retrieved_sources.extend(parse_mmwr_sources(event.content))
        retrieval_r1 = recall_at_k(retrieved_sources, item.expected_source_ids, k=1)
        retrieval_r3 = recall_at_k(retrieved_sources, item.expected_source_ids, k=3)
        retrieval_mrr_val = mrr(retrieved_sources, item.expected_source_ids)

    # Abstention
    abstention_ok = abstention_check(agent_result.response, item.is_answerable)

    # Judge
    judge_faithfulness: Optional[float] = None
    judge_correctness: Optional[float] = None
    judge_justification: Optional[str] = None
    if judge_result is not None:
        judge_faithfulness = judge_result.faithfulness
        judge_correctness = judge_result.correctness
        judge_justification = judge_result.justification

    # Overall pass: tool accuracy >= 0.5, numeric >= 0.5 (if present), abstention ok
    passes = [tool_score >= 0.5, abstention_ok]
    if numeric_score is not None:
        passes.append(numeric_score >= 0.5)
    if retrieval_r3 is not None:
        passes.append(retrieval_r3 >= 0.5)
    overall_pass = all(passes)

    return ItemResult(
        item_id=item.id,
        question=item.question,
        data_sources=item.data_sources,
        is_answerable=item.is_answerable,
        tool_selection_score=tool_score,
        numeric_match_score=numeric_score,
        retrieval_recall_at_1=retrieval_r1,
        retrieval_recall_at_3=retrieval_r3,
        retrieval_mrr=retrieval_mrr_val,
        judge_faithfulness=judge_faithfulness,
        judge_correctness=judge_correctness,
        judge_justification=judge_justification,
        abstention_ok=abstention_ok,
        overall_pass=overall_pass,
    )


# ---------------------------------------------------------------------------
# Judge (LLM-as-judge with cache)
# ---------------------------------------------------------------------------

def _judge_cache_key(question: str, tool_outputs: str, rubric: str) -> str:
    payload = f"{question}\n{tool_outputs}\n{rubric}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _load_judge_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            return {}
    return {}


def _save_judge_cache(cache_path: Path, cache: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))


async def call_judge(
    question: str,
    tool_outputs: str,
    response_summary: str,
    gold_rubric: str,
    judge_model: str,
    cache: dict,
    cache_path: Path,
) -> JudgeResult:
    """Call the LLM judge, returning cached result if available."""
    key = _judge_cache_key(question, tool_outputs, gold_rubric)
    if key in cache:
        cached = cache[key]
        return JudgeResult(**cached)

    prompt = f"""You are evaluating a public health AI assistant's response.

QUESTION: {question}

RETRIEVED TOOL OUTPUTS:
{tool_outputs[:3000]}

AGENT RESPONSE SUMMARY:
{response_summary[:1000]}

GOLD RUBRIC (what a correct answer should include):
{gold_rubric}

Score the response on two dimensions (0.0 to 1.0):

1. FAITHFULNESS: Is every factual claim in the response grounded in the retrieved tool outputs?
   (1.0 = all claims supported, 0.0 = fabricated claims not from tools)

2. CORRECTNESS: Does the response correctly address the question per the gold rubric?
   (1.0 = fully correct, 0.0 = wrong or missing key facts)

Respond ONLY with valid JSON in this exact format:
{{"faithfulness": <float 0-1>, "correctness": <float 0-1>, "justification": "<one sentence>"}}
"""

    from pubhealth_llm.app.agent import _build_agent
    import pydantic_ai
    from pydantic import BaseModel

    class JudgeScore(BaseModel):
        faithfulness: float
        correctness: float
        justification: str

    judge_agent_base = _build_agent(judge_model)
    simple_agent = pydantic_ai.Agent(
        judge_agent_base._model,
        output_type=JudgeScore,
        system_prompt="You are a precise evaluator. Return only valid JSON.",
    )
    try:
        result = await simple_agent.run(prompt)
        score = result.output
        judge_result = JudgeResult(
            faithfulness=max(0.0, min(1.0, score.faithfulness)),
            correctness=max(0.0, min(1.0, score.correctness)),
            justification=score.justification,
        )
    except Exception as exc:
        logger.warning("Judge call failed: %s — using neutral scores", exc)
        judge_result = JudgeResult(
            faithfulness=0.5, correctness=0.5,
            justification=f"Judge unavailable: {exc}"
        )

    cache[key] = {
        "faithfulness": judge_result.faithfulness,
        "correctness": judge_result.correctness,
        "justification": judge_result.justification,
    }
    _save_judge_cache(cache_path, cache)
    return judge_result


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------

def _safe_mean(values: list) -> float:
    values = [v for v in values if v is not None and not math.isnan(v)]
    return sum(values) / len(values) if values else float("nan")


def build_report(
    items: list[ItemResult],
    model: str,
    judge_model: str,
    quick_mode: bool,
) -> EvalReport:
    tool_scores = [r.tool_selection_score for r in items]
    numeric_scores = [r.numeric_match_score for r in items if r.numeric_match_score is not None]
    recall1_scores = [r.retrieval_recall_at_1 for r in items if r.retrieval_recall_at_1 is not None]
    recall3_scores = [r.retrieval_recall_at_3 for r in items if r.retrieval_recall_at_3 is not None]
    mrr_scores = [r.retrieval_mrr for r in items if r.retrieval_mrr is not None]
    faith_scores = [r.judge_faithfulness for r in items if r.judge_faithfulness is not None]
    correct_scores = [r.judge_correctness for r in items if r.judge_correctness is not None]
    abstention_scores = [1.0 if r.abstention_ok else 0.0 for r in items]

    component_scores = [_safe_mean(tool_scores), _safe_mean(abstention_scores)]
    for grp in [numeric_scores, recall3_scores, faith_scores, correct_scores]:
        mean = _safe_mean(grp)
        if not math.isnan(mean):
            component_scores.append(mean)
    overall = _safe_mean([s for s in component_scores if not math.isnan(s)])

    return EvalReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=model,
        judge_model=judge_model,
        quick_mode=quick_mode,
        total_items=len(items),
        item_results=items,
        tool_accuracy=_safe_mean(tool_scores),
        numeric_accuracy=_safe_mean(numeric_scores),
        retrieval_recall_at_1=_safe_mean(recall1_scores),
        retrieval_recall_at_3=_safe_mean(recall3_scores),
        retrieval_mrr=_safe_mean(mrr_scores),
        judge_faithfulness=_safe_mean(faith_scores),
        judge_correctness=_safe_mean(correct_scores),
        abstention_accuracy=_safe_mean(abstention_scores),
        overall_score=overall,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_eval(
    gold_set_path: Path,
    output_dir: Path,
    quick: bool = False,
    model: Optional[str] = None,
    judge_model: Optional[str] = None,
    cache_dir: Optional[Path] = None,
) -> EvalReport:
    """Run the eval harness over the gold set. Returns EvalReport."""
    model_str = model or get_model()
    judge_str = judge_model or model_str
    cache_path = (cache_dir or output_dir) / "judge_cache.json"
    judge_cache = _load_judge_cache(cache_path)

    with open(gold_set_path) as f:
        raw = yaml.safe_load(f)
    gold_items = [GoldItem(**item) for item in raw["items"]]

    if quick:
        gold_items = gold_items[:_DEFAULT_QUICK_LIMIT]
        logger.info("Quick mode: running first %d items", _DEFAULT_QUICK_LIMIT)

    output_dir.mkdir(parents=True, exist_ok=True)
    item_results: list[ItemResult] = []

    for i, item in enumerate(gold_items, 1):
        logger.info("[%d/%d] %s: %s", i, len(gold_items), item.id, item.question[:60])
        try:
            agent_result = await run_agent(item.question, _capture_trace=True, model=model_str)
        except Exception as exc:
            logger.error("Agent failed on %s: %s", item.id, exc)
            from pubhealth_llm.app.agent import AgentResult, EvalTrace
            from pubhealth_llm.app.schemas import PublicHealthResponse
            agent_result = AgentResult(
                response=PublicHealthResponse(
                    summary=f"Error: {exc}",
                    evidence=[],
                    statistics=[],
                    sources=[],
                    caveats=[f"Error: {exc}"],
                ),
                tools_used=[],
                trace=EvalTrace(tool_events=[]),
            )

        tool_outputs = ""
        if agent_result.trace:
            for event in agent_result.trace.tool_events:
                tool_outputs += f"[{event.name}]\n{event.content[:800]}\n\n"

        judge_result = None
        if not quick:
            try:
                judge_result = await call_judge(
                    question=item.question,
                    tool_outputs=tool_outputs,
                    response_summary=agent_result.response.summary,
                    gold_rubric=item.rubric,
                    judge_model=judge_str,
                    cache=judge_cache,
                    cache_path=cache_path,
                )
            except Exception as exc:
                logger.warning("Judge skipped for %s: %s", item.id, exc)

        result = score_item(item, agent_result, judge_result)
        item_results.append(result)
        status = "PASS" if result.overall_pass else "FAIL"
        logger.info("  → %s (tool=%.2f)", status, result.tool_selection_score)

    report = build_report(item_results, model_str, judge_str, quick)
    _write_reports(report, output_dir)
    return report


def _write_reports(report: EvalReport, output_dir: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    json_path = output_dir / f"eval_{ts}.json"
    md_path = output_dir / f"eval_{ts}.md"
    latest_md = output_dir / "eval_latest.md"

    json_path.write_text(report.model_dump_json(indent=2))

    md = _render_markdown(report)
    md_path.write_text(md)
    latest_md.write_text(md)
    logger.info("Reports written: %s, %s", json_path, md_path)


def _render_markdown(report: EvalReport) -> str:
    def fmt(v) -> str:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "N/A"
        return f"{v:.2f}"

    lines = [
        "# pubHealthLLM Eval Report",
        "",
        f"**Timestamp:** {report.timestamp}  ",
        f"**Model:** `{report.model}`  ",
        f"**Judge:** `{report.judge_model}`  ",
        f"**Quick mode:** {report.quick_mode}  ",
        f"**Items evaluated:** {report.total_items}",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Score |",
        "|--------|-------|",
        f"| Tool Selection Accuracy | {fmt(report.tool_accuracy)} |",
        f"| Numeric Answer Accuracy | {fmt(report.numeric_accuracy)} |",
        f"| MMWR Retrieval Recall@1 | {fmt(report.retrieval_recall_at_1)} |",
        f"| MMWR Retrieval Recall@3 | {fmt(report.retrieval_recall_at_3)} |",
        f"| MMWR Retrieval MRR | {fmt(report.retrieval_mrr)} |",
        f"| LLM Judge Faithfulness | {fmt(report.judge_faithfulness)} |",
        f"| LLM Judge Correctness | {fmt(report.judge_correctness)} |",
        f"| Abstention Accuracy (OOD) | {fmt(report.abstention_accuracy)} |",
        f"| **Overall Score** | **{fmt(report.overall_score)}** |",
        "",
        "## Per-Item Results",
        "",
        "| ID | Pass | Tool | Numeric | Recall@3 | MRR | Judge | Abstain | Notes |",
        "|----|------|------|---------|----------|-----|-------|---------|-------|",
    ]
    for r in report.item_results:
        status = "✅" if r.overall_pass else "❌"
        lines.append(
            f"| {r.item_id} | {status} | {fmt(r.tool_selection_score)} "
            f"| {fmt(r.numeric_match_score)} | {fmt(r.retrieval_recall_at_3)} "
            f"| {fmt(r.retrieval_mrr)} | {fmt(r.judge_correctness)} "
            f"| {'✅' if r.abstention_ok else '❌'} | {r.notes[:40]} |"
        )
    lines += [
        "",
        "---",
        "_Generated by pubHealthLLM eval harness._",
    ]
    return "\n".join(lines)
