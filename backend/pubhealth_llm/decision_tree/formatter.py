"""
Markdown formatter for health economic decision tree analysis results.

Converts the output of ``simulate_strategy`` and ``compare_strategies``
into structured GitHub-flavoured markdown suitable for display in the
Gradio chat window.

The formatted output contains five sections:

1. **Header** — analysis title and simulation metadata
2. **Strategy results** — expected cost and utility with 95 % confidence
   intervals for each strategy
3. **Path distribution** — percentage of patients reaching each terminal
   path (validates model behaviour and teaches tree structure)
4. **Incremental analysis** — ΔCost, ΔUtility, and annualised ICER for
   each non-reference strategy vs. the reference
5. **Methodological notes** — model citation, time horizon, annualisation
   convention

The formatter is intentionally a pure function — it has no side effects,
no external dependencies, and no knowledge of the agent or Gradio.  All
inputs are plain Python objects; the output is a single ``str``.
"""

from __future__ import annotations

import math
from typing import Sequence

from pubhealth_llm.decision_tree.simulation import (
    ALL_PATHS,
    PATH_NO_RESPONSE_ED,
    PATH_NO_RESPONSE_ENDURES,
    PATH_NO_RESPONSE_HOSPITAL,
    PATH_RESPONSE_NO_RECURRENCE,
    PATH_RESPONSE_RECURRENCE,
    IncrementalResult,
    SimulationResult,
)

# ---------------------------------------------------------------------------
# Human-readable path labels
# ---------------------------------------------------------------------------

_PATH_LABELS: dict[str, str] = {
    PATH_RESPONSE_NO_RECURRENCE: "Response, no recurrence",
    PATH_RESPONSE_RECURRENCE:    "Response, recurrence (2nd dose)",
    PATH_NO_RESPONSE_ENDURES:    "No response, endures attack",
    PATH_NO_RESPONSE_ED:         "No response, ED visit (relieved)",
    PATH_NO_RESPONSE_HOSPITAL:   "No response, hospitalised",
}


def format_path_label(path: str) -> str:
    """
    Convert a path constant (e.g. ``PATH_RESPONSE_NO_RECURRENCE``) to a
    human-readable label (e.g. ``"Response, no recurrence"``).

    Parameters
    ----------
    path : str
        One of the ``PATH_*`` constants from
        :mod:`pubhealth_llm.decision_tree.simulation`.

    Returns
    -------
    str
        Human-readable label.

    Raises
    ------
    KeyError
        If ``path`` is not a recognised path constant.
    """
    if path not in _PATH_LABELS:
        raise KeyError(
            f"Unknown path constant {path!r}. "
            f"Expected one of: {list(_PATH_LABELS)}"
        )
    return _PATH_LABELS[path]


# ---------------------------------------------------------------------------
# ICER formatting
# ---------------------------------------------------------------------------


def format_icer(icer: float, currency_symbol: str = "$") -> str:
    """
    Format an ICER value as a human-readable string.

    Handles the three special cases that arise from zero or negative
    incremental utility:

    * ``+inf``  — strategy costs more and provides no additional utility
      (dominated).
    * ``-inf``  — strategy costs less *and* provides more utility
      (dominant / extended dominant).
    * ``nan``   — strategy has identical expected cost and utility to the
      reference (no meaningful comparison).

    Parameters
    ----------
    icer : float
        Annualised incremental cost-effectiveness ratio.
    currency_symbol : str
        Symbol prepended to the numeric value (default ``"$"``).

    Returns
    -------
    str
        Formatted string.
    """
    if math.isinf(icer):
        if icer > 0:
            return "Dominated — higher cost, no additional utility"
        return "Dominant — lower cost, higher utility"
    if math.isnan(icer):
        return "N/A — identical cost and utility"
    sign = "+" if icer > 0 else ""
    return f"{sign}{currency_symbol}{icer:,.0f}/QALY"


# ---------------------------------------------------------------------------
# Sign-prefixed numeric helpers
# ---------------------------------------------------------------------------


def _signed_cost(value: float, symbol: str) -> str:
    """Format an incremental cost with sign and currency symbol."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{symbol}{value:.2f}"


def _signed_utility(value: float) -> str:
    """Format an incremental utility with sign."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.4f}"


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------


def _strategy_results_table(
    sim_results: Sequence[SimulationResult],
    currency_symbol: str,
    show_confidence_intervals: bool,
) -> str:
    """Build the strategy results markdown table."""
    if show_confidence_intervals:
        header = (
            "| Strategy | E\\[Cost\\] | 95% CI (Cost) "
            "| E\\[Utility\\] | 95% CI (Utility) |\n"
            "|---|---|---|---|---|\n"
        )
    else:
        header = (
            "| Strategy | E\\[Cost\\] | E\\[Utility\\] |\n"
            "|---|---|---|\n"
        )

    rows: list[str] = []
    for r in sim_results:
        if show_confidence_intervals:
            lo_c, hi_c = r.ci_cost()
            lo_u, hi_u = r.ci_utility()
            rows.append(
                f"| {r.strategy_name} "
                f"| {currency_symbol}{r.expected_cost:.2f} "
                f"| ({currency_symbol}{lo_c:.2f}, {currency_symbol}{hi_c:.2f}) "
                f"| {r.expected_utility:.4f} "
                f"| ({lo_u:.4f}, {hi_u:.4f}) |"
            )
        else:
            rows.append(
                f"| {r.strategy_name} "
                f"| {currency_symbol}{r.expected_cost:.2f} "
                f"| {r.expected_utility:.4f} |"
            )

    return header + "\n".join(rows)


def _path_distribution_table(sim_results: Sequence[SimulationResult]) -> str:
    """Build the path distribution markdown table (percentages)."""
    strategy_names = [r.strategy_name for r in sim_results]
    header_cols = " | ".join(strategy_names)
    sep_cols    = " | ".join(["---"] * len(strategy_names))

    header = f"| Path | {header_cols} |\n|---|{sep_cols}|\n"

    rows: list[str] = []
    for path in ALL_PATHS:
        label = _PATH_LABELS[path]
        freq_cols = " | ".join(
            f"{r.path_frequencies[path] * 100:.1f}%"
            for r in sim_results
        )
        rows.append(f"| {label} | {freq_cols} |")

    return header + "\n".join(rows)


def _incremental_table(
    incremental_results: Sequence[IncrementalResult],
    currency_symbol: str,
) -> str:
    """Build the incremental cost-effectiveness markdown table."""
    header = (
        "| Strategy | vs. | ΔCost | ΔUtility | ICER |\n"
        "|---|---|---|---|---|\n"
    )

    rows: list[str] = []
    for r in incremental_results:
        rows.append(
            f"| {r.strategy} "
            f"| {r.reference} "
            f"| {_signed_cost(r.incremental_cost, currency_symbol)} "
            f"| {_signed_utility(r.incremental_utility)} "
            f"| {format_icer(r.icer_annual, currency_symbol)} |"
        )

    return header + "\n".join(rows)


def _icer_interpretation(
    incremental_results: Sequence[IncrementalResult],
    currency_symbol: str,
) -> str:
    """
    Generate a plain-English interpretation of each incremental result.

    Uses the Laupacis et al. (1992) grades of recommendation as a rough
    guide, expressed in generic terms rather than 1995 Canadian dollar
    thresholds (which should be updated for the specific currency and year
    of the analysis).
    """
    if not incremental_results:
        return ""

    lines: list[str] = []
    for r in incremental_results:
        d_c = r.incremental_cost
        d_u = r.incremental_utility
        icer = r.icer_annual

        if math.isinf(icer) and icer > 0:
            verdict = (
                f"**{r.strategy}** costs more than **{r.reference}** and provides "
                f"no additional utility — this is a *dominated* strategy."
            )
        elif math.isinf(icer) and icer < 0:
            verdict = (
                f"**{r.strategy}** costs less than **{r.reference}** and provides "
                f"equal or greater utility — this is a *dominant* strategy "
                f"(compelling evidence for adoption)."
            )
        elif math.isnan(icer):
            verdict = (
                f"**{r.strategy}** and **{r.reference}** have identical expected "
                f"cost and utility — no meaningful incremental comparison."
            )
        elif d_u > 0 and d_c < 0:
            verdict = (
                f"**{r.strategy}** costs *less* ({currency_symbol}{abs(d_c):.2f} savings) "
                f"and delivers *better* outcomes (+{d_u:.4f} utility) vs. "
                f"**{r.reference}** — dominant strategy."
            )
        elif d_u > 0 and d_c >= 0:
            verdict = (
                f"**{r.strategy}** costs more (+{currency_symbol}{d_c:.2f}) and "
                f"delivers better outcomes (+{d_u:.4f} utility) vs. "
                f"**{r.reference}**. "
                f"ICER: {format_icer(icer, currency_symbol)}."
            )
        elif d_u <= 0 and d_c >= 0:
            verdict = (
                f"**{r.strategy}** costs more and delivers equal or worse outcomes "
                f"vs. **{r.reference}** — this is a *dominated* strategy."
            )
        else:
            verdict = (
                f"**{r.strategy}** vs. **{r.reference}**: "
                f"ΔCost = {_signed_cost(d_c, currency_symbol)}, "
                f"ΔUtility = {_signed_utility(d_u)}, "
                f"ICER = {format_icer(icer, currency_symbol)}."
            )

        lines.append(verdict)

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_analysis(
    sim_results: Sequence[SimulationResult],
    incremental_results: Sequence[IncrementalResult],
    *,
    title: str = "Health Economic Decision Tree Analysis",
    currency_symbol: str = "$",
    currency_name: str = "",
    show_path_table: bool = True,
    show_confidence_intervals: bool = True,
    model_citation: str = (
        "Evans et al. (1997). PharmacoEconomics 12(5): 565–577."
    ),
) -> str:
    """
    Format decision tree analysis results as structured markdown.

    Produces a five-section report: header, strategy results, path
    distribution, incremental analysis, and methodological notes.  The
    output is ready to be returned directly to a Gradio ChatInterface.

    Parameters
    ----------
    sim_results : sequence of SimulationResult
        One entry per strategy, in the order they should appear in the
        tables.  Typically the reference strategy is listed first.
    incremental_results : sequence of IncrementalResult
        Output of :func:`compare_strategies`.  May be empty if only one
        strategy was analysed (no comparison).
    title : str
        Heading for the analysis report.
    currency_symbol : str
        Symbol prepended to cost values (e.g. ``"$"``, ``"£"``, ``"€"``).
    currency_name : str
        Optional currency description appended to the header metadata
        (e.g. ``"1995 Canadian dollars"``).  Empty string omits it.
    show_path_table : bool
        If ``True`` (default), include the path distribution section.
    show_confidence_intervals : bool
        If ``True`` (default), include 95 % CI columns in the strategy
        results table.
    model_citation : str
        Citation shown in the methodological notes footer.

    Returns
    -------
    str
        GitHub-flavoured markdown string.

    Raises
    ------
    ValueError
        If ``sim_results`` is empty.

    Examples
    --------
    >>> from pubhealth_llm.decision_tree import (
    ...     StrategyParams, simulate_strategy, compare_strategies
    ... )
    >>> from pubhealth_llm.decision_tree.formatter import format_analysis
    >>> import numpy as np
    >>> params = StrategyParams(
    ...     name="Treatment A",
    ...     cost_drug=10.0, cost_ed=50.0, cost_hospital=500.0,
    ...     u_response_no_recurrence=1.0, u_response_recurrence=0.9,
    ...     u_no_response_endures=-0.3, u_no_response_ed=0.1,
    ...     u_no_response_hospital=-0.3,
    ...     p_response=0.5, p_no_recurrence=0.6,
    ...     p_endures=0.9, p_ed_relief=0.99,
    ... )
    >>> result = simulate_strategy(params, 10_000, np.random.default_rng(0))
    >>> md = format_analysis([result], [], title="Demo")
    >>> "Treatment A" in md
    True
    """
    if not sim_results:
        raise ValueError("sim_results must contain at least one SimulationResult.")

    sections: list[str] = []

    # ── 1. Header ─────────────────────────────────────────────────────────
    n_patients = sim_results[0].n_patients
    n_strategies = len(sim_results)
    currency_note = f" · {currency_name}" if currency_name else ""

    header = (
        f"# {title}\n\n"
        f"**Simulation:** {n_patients:,} patients per strategy "
        f"· {n_strategies} strateg{'y' if n_strategies == 1 else 'ies'}"
        f"{currency_note}"
    )
    sections.append(header)

    # ── 2. Strategy results ────────────────────────────────────────────────
    sections.append(
        "## Strategy Results\n\n"
        + _strategy_results_table(sim_results, currency_symbol, show_confidence_intervals)
    )

    # ── 3. Path distribution ───────────────────────────────────────────────
    if show_path_table:
        sections.append(
            "## Terminal Path Distribution\n\n"
            "_Percentage of patients reaching each terminal outcome._\n\n"
            + _path_distribution_table(sim_results)
        )

    # ── 4. Incremental analysis ────────────────────────────────────────────
    if incremental_results:
        interpretation = _icer_interpretation(incremental_results, currency_symbol)
        sections.append(
            "## Incremental Cost-Effectiveness Analysis\n\n"
            + _incremental_table(incremental_results, currency_symbol)
            + "\n\n"
            + interpretation
        )

    # ── 5. Methodological notes ────────────────────────────────────────────
    strategy_names = " · ".join(r.strategy_name for r in sim_results)
    ci_note = "- **Confidence intervals:** 95% (z = 1.96)\n" if show_confidence_intervals else ""
    sections.append(
        "## Methodological Notes\n\n"
        f"- **Model:** {model_citation}\n"
        f"- **Strategies:** {strategy_names}\n"
        f"- **Patients simulated:** {n_patients:,} per strategy "
        f"(vectorised Monte Carlo)\n"
        "- **Time horizon:** 48 hours per episode; "
        "ICER annualised (×365) to express cost per QALY\n"
        f"{ci_note}"
        "\n> ⚠️ This analysis is a decision-support tool. Results depend on "
        "the quality of the input parameters. All outputs require review "
        "by a qualified health economist before informing policy decisions."
    )

    return "\n\n---\n\n".join(sections)
