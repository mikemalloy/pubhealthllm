"""
Python script generator for health economic decision tree analyses.

Takes one or more populated :class:`StrategyParams` objects and renders a
complete, self-contained Python script that:

1. Imports from ``pubhealth_llm.decision_tree`` (the validated simulation engine)
2. Defines each strategy's parameters as explicit named arguments — making the
   generated code readable, auditable, and suitable for teaching
3. Runs the vectorised Monte Carlo simulation for every strategy
4. Compares strategies and computes ICERs
5. Formats and prints the results as structured markdown

The generated script is designed to be saved as a ``.py`` file and executed
as a subprocess.  Its stdout is the formatted markdown report.  It does not
write any files or have other side effects.

Teaching intent
---------------
The generated code is intentionally explicit — each parameter appears by name
on its own line rather than being passed as a dict or unpacked from a tuple.
This makes the script readable to a public health student who does not know
Python: the parameter names map directly to the clinical concepts (``p_response``,
``cost_drug``, ``u_response_no_recurrence``, etc.) and the structure of the
code mirrors the structure of the analysis.
"""

from __future__ import annotations

import re
from typing import Sequence

from pubhealth_llm.decision_tree.simulation import StrategyParams

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """
    Convert a strategy name to a valid Python identifier fragment.

    Used to build readable variable names in the generated script.

    Examples
    --------
    >>> _slugify("Sumatriptan")
    'sumatriptan'
    >>> _slugify("Caffeine/Ergotamine")
    'caffeine_ergotamine'
    >>> _slugify("Drug A (new formulation)")
    'drug_a_new_formulation'
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug or "strategy"


def _format_float(value: float) -> str:
    """
    Format a float for inclusion in generated Python source code.

    Uses Python's default ``repr()`` which produces the shortest string
    that round-trips exactly (e.g. ``16.1``, ``0.558``, ``-0.3``).
    """
    return repr(value)


def _render_strategy_params(params: StrategyParams, var_name: str) -> str:
    """
    Render a ``StrategyParams`` as an explicit Python assignment statement.

    Each parameter appears on its own line with its name, making the
    generated code directly legible to non-programmers.

    Parameters
    ----------
    params : StrategyParams
        The strategy to render.
    var_name : str
        The Python variable name to assign to (e.g. ``"_strategy_sumatriptan"``).

    Returns
    -------
    str
        Multi-line Python assignment statement.
    """
    lines = [
        f"{var_name} = StrategyParams(",
        f"    name={params.name!r},",
        f"",
        f"    # Costs",
        f"    cost_drug={_format_float(params.cost_drug)},",
        f"    cost_ed={_format_float(params.cost_ed)},",
        f"    cost_hospital={_format_float(params.cost_hospital)},",
        f"",
        f"    # Utilities (per-episode; can be negative for severe states)",
        f"    u_response_no_recurrence={_format_float(params.u_response_no_recurrence)},",
        f"    u_response_recurrence={_format_float(params.u_response_recurrence)},",
        f"    u_no_response_endures={_format_float(params.u_no_response_endures)},",
        f"    u_no_response_ed={_format_float(params.u_no_response_ed)},",
        f"    u_no_response_hospital={_format_float(params.u_no_response_hospital)},",
        f"",
        f"    # Probabilities",
        f"    p_response={_format_float(params.p_response)},",
        f"    p_no_recurrence={_format_float(params.p_no_recurrence)},",
        f"    p_endures={_format_float(params.p_endures)},",
        f"    p_ed_relief={_format_float(params.p_ed_relief)},",
        f")",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_script(
    strategies: Sequence[StrategyParams],
    *,
    reference_index: int = 0,
    n_patients: int = 1_000_000,
    seed: int = 2026,
    title: str = "Health Economic Decision Tree Analysis",
    currency_symbol: str = "$",
    currency_name: str = "",
    show_path_table: bool = True,
    show_confidence_intervals: bool = True,
    model_citation: str = (
        "Evans et al. (1997). PharmacoEconomics 12(5): 565\u2013577."
    ),
) -> str:
    """
    Generate a self-contained Python script that runs a decision tree analysis.

    The generated script imports from ``pubhealth_llm.decision_tree``, defines
    the strategy parameters explicitly, runs the simulation and comparison, and
    prints the formatted markdown report to stdout.

    Parameters
    ----------
    strategies : sequence of StrategyParams
        One entry per treatment strategy.  Must contain at least one entry.
        The script will simulate each strategy and — if there are two or more —
        compare all non-reference strategies against the reference.
    reference_index : int
        Index into ``strategies`` identifying the reference (comparator).
        Defaults to 0.  Must be in range.
    n_patients : int
        Number of patients to simulate per strategy.  Must be ≥ 1.
        Defaults to 1,000,000.
    seed : int
        Base random seed.  Each strategy receives ``seed + i`` so that
        strategies are simulated independently.  Must be ≥ 0.
    title : str
        Analysis title used in the formatted report header.
    currency_symbol : str
        Currency symbol prepended to cost values (e.g. ``"$"``, ``"£"``).
    currency_name : str
        Optional full currency description for the report header
        (e.g. ``"1995 Canadian dollars"``).
    show_path_table : bool
        Whether the generated script includes the path distribution table.
    show_confidence_intervals : bool
        Whether the generated script includes 95 % CI columns.
    model_citation : str
        Citation string for the methodological notes footer.

    Returns
    -------
    str
        Complete Python source code as a single string.  Save to a ``.py``
        file and execute with the project's Python interpreter to reproduce
        the analysis.

    Raises
    ------
    ValueError
        If ``strategies`` is empty, ``reference_index`` is out of range, or
        ``n_patients`` is less than 1.

    Examples
    --------
    >>> from pubhealth_llm.decision_tree import StrategyParams
    >>> from pubhealth_llm.decision_tree.generator import generate_script
    >>> params = StrategyParams(
    ...     name="Treatment A",
    ...     cost_drug=10.0, cost_ed=50.0, cost_hospital=500.0,
    ...     u_response_no_recurrence=1.0, u_response_recurrence=0.9,
    ...     u_no_response_endures=-0.3, u_no_response_ed=0.1,
    ...     u_no_response_hospital=-0.3,
    ...     p_response=0.5, p_no_recurrence=0.6,
    ...     p_endures=0.9, p_ed_relief=0.99,
    ... )
    >>> script = generate_script([params], n_patients=10_000, seed=42)
    >>> "Treatment A" in script
    True
    >>> "N_PATIENTS = 10000" in script
    True
    """
    # --- Validate inputs ---
    if not strategies:
        raise ValueError("strategies must contain at least one StrategyParams.")

    n = len(strategies)
    if not (0 <= reference_index < n):
        raise ValueError(
            f"reference_index {reference_index!r} is out of range for "
            f"{n} strateg{'y' if n == 1 else 'ies'}."
        )
    if n_patients < 1:
        raise ValueError(f"n_patients must be ≥ 1; got {n_patients!r}.")
    if seed < 0:
        raise ValueError(f"seed must be ≥ 0; got {seed!r}.")

    # --- Build variable names for each strategy ---
    # Use _strategy_0, _strategy_1, ... to guarantee uniqueness even when
    # strategy names are similar or contain characters invalid in identifiers.
    var_names = [f"_strategy_{i}_{_slugify(s.name)}" for i, s in enumerate(strategies)]

    # --- Render each StrategyParams block ---
    param_blocks = "\n\n".join(
        _render_strategy_params(s, var_names[i])
        for i, s in enumerate(strategies)
    )

    # --- Build the _STRATEGIES list literal ---
    strategies_list = "[\n    " + ",\n    ".join(var_names) + ",\n]"

    # --- Comparison section (only when there are multiple strategies) ---
    if n >= 2:
        comparison_section = (
            "# ---------------------------------------------------------------------------\n"
            "# Compare strategies\n"
            "# ---------------------------------------------------------------------------\n"
            "\n"
            f"_incremental = compare_strategies(\n"
            f"    _sim_results,\n"
            f"    reference_index={reference_index},\n"
            f")\n"
        )
    else:
        comparison_section = (
            "# Single strategy — no incremental comparison.\n"
            "_incremental = []\n"
        )

    # --- Assemble the complete script ---
    script = (
        f'"""\n'
        f"{title}\n"
        f"\n"
        f"Generated by pubHealthLLM — Evans acute-treatment decision tree engine.\n"
        f"\n"
        f"This script is self-contained and reproducible.  Run it with the project\n"
        f"Python interpreter to reproduce the analysis with identical results.\n"
        f'"""\n'
        f"\n"
        f"import numpy as np\n"
        f"\n"
        f"from pubhealth_llm.decision_tree import (\n"
        f"    StrategyParams,\n"
        f"    compare_strategies,\n"
        f"    simulate_strategy,\n"
        f")\n"
        f"from pubhealth_llm.decision_tree.formatter import format_analysis\n"
        f"\n"
        f"# ---------------------------------------------------------------------------\n"
        f"# Strategy parameters\n"
        f"# ---------------------------------------------------------------------------\n"
        f"# Each parameter is listed explicitly so that the analysis is fully\n"
        f"# auditable and can be modified directly in this file.\n"
        f"\n"
        f"{param_blocks}\n"
        f"\n"
        f"_STRATEGIES = {strategies_list}\n"
        f"\n"
        f"# ---------------------------------------------------------------------------\n"
        f"# Simulation configuration\n"
        f"# ---------------------------------------------------------------------------\n"
        f"\n"
        f"N_PATIENTS      = {n_patients}\n"
        f"RANDOM_SEED     = {seed}\n"
        f"REFERENCE_INDEX = {reference_index}\n"
        f"\n"
        f"# ---------------------------------------------------------------------------\n"
        f"# Run simulation — one call per strategy, each with an independent seed\n"
        f"# ---------------------------------------------------------------------------\n"
        f"\n"
        f"_sim_results = [\n"
        f"    simulate_strategy(s, N_PATIENTS, np.random.default_rng(RANDOM_SEED + i))\n"
        f"    for i, s in enumerate(_STRATEGIES)\n"
        f"]\n"
        f"\n"
        f"{comparison_section}\n"
        f"# ---------------------------------------------------------------------------\n"
        f"# Format and print results\n"
        f"# ---------------------------------------------------------------------------\n"
        f"\n"
        f"_output = format_analysis(\n"
        f"    _sim_results,\n"
        f"    _incremental,\n"
        f"    title={title!r},\n"
        f"    currency_symbol={currency_symbol!r},\n"
        f"    currency_name={currency_name!r},\n"
        f"    show_path_table={show_path_table!r},\n"
        f"    show_confidence_intervals={show_confidence_intervals!r},\n"
        f"    model_citation={model_citation!r},\n"
        f")\n"
        f"\n"
        f"print(_output)\n"
    )

    return script
