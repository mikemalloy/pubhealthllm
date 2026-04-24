"""
pubhealth_llm.decision_tree — Health economic decision tree simulation.

Public API
----------
StrategyParams
    Immutable parameter set for one treatment strategy.

SimulationResult
    Output of simulate_strategy(): aggregate statistics and raw arrays.

IncrementalResult
    Output of compare_strategies(): incremental cost, utility, and ICER
    for one strategy relative to a reference.

simulate_strategy(params, n_patients, rng)
    Run a vectorised Monte Carlo simulation for a single strategy.

compare_strategies(results, reference_index, annualise)
    Compute pairwise incremental cost-effectiveness ratios.

analytical_expected_values(params)
    Compute exact expected cost and utility without simulation (for
    validation and as a fast alternative when n is large).
"""

from pubhealth_llm.decision_tree.simulation import (
    ALL_PATHS,
    PATH_NO_RESPONSE_ED,
    PATH_NO_RESPONSE_ENDURES,
    PATH_NO_RESPONSE_HOSPITAL,
    PATH_RESPONSE_NO_RECURRENCE,
    PATH_RESPONSE_RECURRENCE,
    IncrementalResult,
    SimulationResult,
    StrategyParams,
    analytical_expected_values,
    compare_strategies,
    simulate_strategy,
)
from pubhealth_llm.decision_tree.formatter import (
    format_analysis,
    format_icer,
    format_path_label,
)

__all__ = [
    # Simulation
    "StrategyParams",
    "SimulationResult",
    "IncrementalResult",
    "simulate_strategy",
    "compare_strategies",
    "analytical_expected_values",
    # Path constants
    "ALL_PATHS",
    "PATH_RESPONSE_NO_RECURRENCE",
    "PATH_RESPONSE_RECURRENCE",
    "PATH_NO_RESPONSE_ENDURES",
    "PATH_NO_RESPONSE_ED",
    "PATH_NO_RESPONSE_HOSPITAL",
    # Formatter
    "format_analysis",
    "format_icer",
    "format_path_label",
]
