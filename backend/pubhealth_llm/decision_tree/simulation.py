"""
Vectorised Monte Carlo simulation engine for health economic decision trees.

Implements the Evans acute-treatment decision tree (Evans et al.,
PharmacoEconomics 12(5): 565–577, 1997), generalised to support any number
of treatment strategies rather than the original two-arm comparison.

Tree structure
--------------
Each strategy follows the same branching structure:

    Treatment
    ├── Response            (p_response)
    │   ├── No recurrence   (p_no_recurrence)  → Path 1: drug cost,      high utility
    │   └── Recurrence      (1−p_no_recurrence) → Path 2: 2×drug cost,  moderate utility
    └── No response         (1−p_response)
        ├── Endures attack  (p_endures)          → Path 3: drug cost,      low utility
        └── ED visit        (1−p_endures)
            ├── ED relief   (p_ed_relief)        → Path 4: drug+ED cost,   moderate utility
            └── Hospitalised (1−p_ed_relief)     → Path 5: drug+ED+hosp,  low utility

The simulation is fully vectorised: all N patients are processed in a single
numpy operation rather than a per-patient Python loop, making 1 M patients
per strategy practical in under a second.

Key references
--------------
Evans, K. W., et al. (1997). Economic Evaluation of Oral Sumatriptan Compared
with Oral Caffeine/Ergotamine for Migraine. PharmacoEconomics, 12(5), 565–577.

Briggs, A. H., Claxton, K., & Sculpher, M. (2011). Decision Modelling for
Health Economic Evaluation. Oxford University Press.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final, Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Path label constants
# ---------------------------------------------------------------------------

PATH_RESPONSE_NO_RECURRENCE: Final[str] = "response_no_recurrence"
"""Terminal path: treatment succeeds, no recurrence within 48 h."""

PATH_RESPONSE_RECURRENCE: Final[str] = "response_recurrence"
"""Terminal path: treatment succeeds, recurrence occurs within 48 h."""

PATH_NO_RESPONSE_ENDURES: Final[str] = "no_response_endures"
"""Terminal path: treatment fails, patient endures the attack."""

PATH_NO_RESPONSE_ED: Final[str] = "no_response_ed"
"""Terminal path: treatment fails, patient visits ED and is relieved."""

PATH_NO_RESPONSE_HOSPITAL: Final[str] = "no_response_hospital"
"""Terminal path: treatment fails, patient visits ED and is hospitalised."""

ALL_PATHS: Final[tuple[str, ...]] = (
    PATH_RESPONSE_NO_RECURRENCE,
    PATH_RESPONSE_RECURRENCE,
    PATH_NO_RESPONSE_ENDURES,
    PATH_NO_RESPONSE_ED,
    PATH_NO_RESPONSE_HOSPITAL,
)
"""Ordered tuple of all five terminal path labels."""

# Internal integer index for each path — used by np.select for fast labelling.
_PATH_INDEX: Final[dict[str, int]] = {p: i for i, p in enumerate(ALL_PATHS)}


# ---------------------------------------------------------------------------
# StrategyParams
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyParams:
    """
    Immutable parameter set for one treatment strategy.

    Encapsulates all 13 inputs required by the Evans acute-treatment decision
    tree: 3 cost parameters, 5 utility parameters, and 4 probability
    parameters. Each strategy in a multi-strategy analysis has its own
    ``StrategyParams`` instance.

    Parameters
    ----------
    name : str
        Human-readable label for this strategy (e.g. ``"Sumatriptan"``).

    cost_drug : float
        Acquisition cost of one dose of the treatment, in any consistent
        currency unit. Non-negative.

    cost_ed : float
        Cost of one emergency department visit (excluding hospitalisation).
        Non-negative.

    cost_hospital : float
        Additional cost of hospitalisation, incurred on top of ``cost_ed``.
        Non-negative.

    u_response_no_recurrence : float
        Utility assigned to the health state where treatment succeeds and
        there is no recurrence. Typically 1.0 (full health).

    u_response_recurrence : float
        Utility assigned to the health state where treatment succeeds but
        a recurrence occurs within 48 h. Typically 0.9.

    u_no_response_endures : float
        Utility assigned to the health state where treatment fails and the
        patient endures the attack without seeking further care. Can be
        negative (severe suffering).

    u_no_response_ed : float
        Utility assigned to the health state where treatment fails, the
        patient visits an ED, and is relieved there. Typically slightly
        positive (0.1).

    u_no_response_hospital : float
        Utility assigned to the health state where treatment fails, the
        patient visits an ED, and is hospitalised. Can be negative.

    p_response : float
        Probability that the treatment converts a moderate-or-severe episode
        to mild-or-none within 2 hours (primary efficacy measure). In [0, 1].

    p_no_recurrence : float
        Probability that a patient who responded to treatment does NOT
        experience recurrence within 48 h. In [0, 1].

    p_endures : float
        Probability that a non-responding patient endures the attack at home
        rather than seeking emergency care. In [0, 1].

    p_ed_relief : float
        Probability that a patient who visits the ED is relieved there (and
        therefore not hospitalised). In [0, 1].

    Raises
    ------
    ValueError
        If ``name`` is empty or whitespace-only, any cost is negative, or
        any probability is outside [0, 1].
    """

    name: str

    # --- Costs (non-negative) ---
    cost_drug: float
    cost_ed: float
    cost_hospital: float

    # --- Utilities (real-valued; can be negative) ---
    u_response_no_recurrence: float
    u_response_recurrence: float
    u_no_response_endures: float
    u_no_response_ed: float
    u_no_response_hospital: float

    # --- Probabilities (in [0, 1]) ---
    p_response: float
    p_no_recurrence: float
    p_endures: float
    p_ed_relief: float

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("name must be a non-empty, non-whitespace string.")

        for attr, value in (
            ("cost_drug", self.cost_drug),
            ("cost_ed", self.cost_ed),
            ("cost_hospital", self.cost_hospital),
        ):
            if value < 0.0:
                raise ValueError(f"{attr} must be non-negative; got {value!r}.")

        for attr, value in (
            ("p_response", self.p_response),
            ("p_no_recurrence", self.p_no_recurrence),
            ("p_endures", self.p_endures),
            ("p_ed_relief", self.p_ed_relief),
        ):
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"{attr} must be in [0, 1]; got {value!r}."
                )


# ---------------------------------------------------------------------------
# SimulationResult
# ---------------------------------------------------------------------------


@dataclass
class SimulationResult:
    """
    Output of :func:`simulate_strategy` for a single treatment strategy.

    Aggregate statistics are pre-computed from the raw arrays and should
    be used for reporting. The raw arrays (prefixed with ``_``) are retained
    for downstream computation such as bootstrap confidence intervals and
    probabilistic sensitivity analysis.

    Attributes
    ----------
    strategy_name : str
        Name of the strategy, taken from :attr:`StrategyParams.name`.
    n_patients : int
        Number of patients simulated.
    expected_cost : float
        Monte Carlo estimate of mean cost per patient.
    expected_utility : float
        Monte Carlo estimate of mean utility per patient.
    cost_se : float
        Standard error of ``expected_cost`` (= std / sqrt(n)).
    utility_se : float
        Standard error of ``expected_utility``.
    path_frequencies : dict[str, float]
        Proportion of patients reaching each terminal path.
        Keys are the ``PATH_*`` constants; values sum to 1.0.
    """

    strategy_name: str
    n_patients: int
    expected_cost: float
    expected_utility: float
    cost_se: float
    utility_se: float
    path_frequencies: dict[str, float]

    # Raw arrays — excluded from repr to keep output readable.
    _cost: np.ndarray = field(repr=False)
    _utility: np.ndarray = field(repr=False)
    _paths: np.ndarray = field(repr=False)

    def ci_cost(self, z: float = 1.96) -> tuple[float, float]:
        """Return a z-based confidence interval for expected cost."""
        half = z * self.cost_se
        return (self.expected_cost - half, self.expected_cost + half)

    def ci_utility(self, z: float = 1.96) -> tuple[float, float]:
        """Return a z-based confidence interval for expected utility."""
        half = z * self.utility_se
        return (self.expected_utility - half, self.expected_utility + half)


# ---------------------------------------------------------------------------
# IncrementalResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncrementalResult:
    """
    Incremental cost-effectiveness analysis for one strategy vs. a reference.

    Attributes
    ----------
    strategy : str
        Name of the strategy being evaluated.
    reference : str
        Name of the reference (comparator) strategy.
    incremental_cost : float
        E[cost | strategy] − E[cost | reference].
    incremental_utility : float
        E[utility | strategy] − E[utility | reference].
    icer_annual : float
        Incremental cost-effectiveness ratio, annualised by multiplying
        by 365 (one simulation period = one 24-h attack episode).
        Expressed in currency units per QALY.
        ``float("inf")`` when incremental utility ≤ 0 and incremental cost > 0
        (dominated or weakly dominated strategy).
    incremental_cost_se : float
        Standard error of ``incremental_cost``.
    incremental_utility_se : float
        Standard error of ``incremental_utility``.
    """

    strategy: str
    reference: str
    incremental_cost: float
    incremental_utility: float
    icer_annual: float
    incremental_cost_se: float
    incremental_utility_se: float


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def analytical_expected_values(params: StrategyParams) -> dict[str, float | dict[str, float]]:
    """
    Compute exact expected cost and utility for a strategy analytically.

    Uses closed-form probability products rather than simulation. Results
    are exact (subject only to floating-point rounding) and serve as the
    ground truth against which :func:`simulate_strategy` results are
    validated.

    Parameters
    ----------
    params : StrategyParams
        Strategy parameters.

    Returns
    -------
    dict with keys:
        ``"expected_cost"`` : float
            Exact expected cost per patient.
        ``"expected_utility"`` : float
            Exact expected utility per patient.
        ``"path_probabilities"`` : dict[str, float]
            Exact probability of each terminal path.

    Examples
    --------
    >>> from pubhealth_llm.decision_tree import StrategyParams, analytical_expected_values
    >>> sumatriptan = StrategyParams(
    ...     name="Sumatriptan",
    ...     cost_drug=16.10, cost_ed=63.16, cost_hospital=1093.0,
    ...     u_response_no_recurrence=1.0, u_response_recurrence=0.9,
    ...     u_no_response_endures=-0.3, u_no_response_ed=0.1,
    ...     u_no_response_hospital=-0.3,
    ...     p_response=0.558, p_no_recurrence=0.594,
    ...     p_endures=0.92, p_ed_relief=0.998,
    ... )
    >>> result = analytical_expected_values(sumatriptan)
    >>> round(result["expected_cost"], 2)
    22.06
    """
    p_r = params.p_response
    p_nr = params.p_no_recurrence
    p_e = params.p_endures
    p_er = params.p_ed_relief

    # Terminal path probabilities (product of branch probabilities along each path)
    p_path: dict[str, float] = {
        PATH_RESPONSE_NO_RECURRENCE: p_r * p_nr,
        PATH_RESPONSE_RECURRENCE:    p_r * (1.0 - p_nr),
        PATH_NO_RESPONSE_ENDURES:    (1.0 - p_r) * p_e,
        PATH_NO_RESPONSE_ED:         (1.0 - p_r) * (1.0 - p_e) * p_er,
        PATH_NO_RESPONSE_HOSPITAL:   (1.0 - p_r) * (1.0 - p_e) * (1.0 - p_er),
    }

    c = params.cost_drug
    e = params.cost_ed
    h = params.cost_hospital

    # Expected cost: sum over all paths of P(path) × cost(path)
    # Path costs:
    #   1 (response, no rec):  c          — one drug dose
    #   2 (response, rec):     2c         — second dose for recurrence
    #   3 (no response, ends): c          — drug paid regardless of outcome
    #   4 (no response, ED):   c + e      — drug plus ED visit
    #   5 (no response, hosp): c + e + h  — drug plus ED plus hospitalisation
    expected_cost: float = (
        p_path[PATH_RESPONSE_NO_RECURRENCE] * c
        + p_path[PATH_RESPONSE_RECURRENCE]    * (2.0 * c)
        + p_path[PATH_NO_RESPONSE_ENDURES]    * c
        + p_path[PATH_NO_RESPONSE_ED]         * (c + e)
        + p_path[PATH_NO_RESPONSE_HOSPITAL]   * (c + e + h)
    )

    # Expected utility: sum over all paths of P(path) × utility(path)
    expected_utility: float = (
        p_path[PATH_RESPONSE_NO_RECURRENCE] * params.u_response_no_recurrence
        + p_path[PATH_RESPONSE_RECURRENCE]    * params.u_response_recurrence
        + p_path[PATH_NO_RESPONSE_ENDURES]    * params.u_no_response_endures
        + p_path[PATH_NO_RESPONSE_ED]         * params.u_no_response_ed
        + p_path[PATH_NO_RESPONSE_HOSPITAL]   * params.u_no_response_hospital
    )

    return {
        "expected_cost": expected_cost,
        "expected_utility": expected_utility,
        "path_probabilities": p_path,
    }


def simulate_strategy(
    params: StrategyParams,
    n_patients: int,
    rng: np.random.Generator,
) -> SimulationResult:
    """
    Run a vectorised Monte Carlo simulation for a single treatment strategy.

    All N patients are processed simultaneously using NumPy array operations.
    No Python-level patient loop is used — the simulation scales to millions
    of patients in sub-second time.

    The simulation draws a single (n_patients × 4) random matrix; each
    column represents one chance node in the decision tree:

    ======  ===============================================================
    Column  Chance node
    ======  ===============================================================
    0       Did the patient respond to treatment?
    1       If responded: did recurrence occur within 48 h?
    2       If no response: did patient endure the attack (no ED)?
    3       If no response and ED: was the patient relieved at the ED?
    ======  ===============================================================

    Boolean masks derived from column thresholds identify which terminal
    path each patient reaches. ``np.where`` and ``np.select`` then assign
    costs and utilities element-wise across the full array.

    Parameters
    ----------
    params : StrategyParams
        Parameters for the strategy to simulate.
    n_patients : int
        Number of patients to simulate. Must be ≥ 1.
    rng : numpy.random.Generator
        A seeded NumPy random generator (e.g. ``np.random.default_rng(42)``).
        Pass the same generator across multiple calls to ensure independence
        between strategies without sharing random draws.

    Returns
    -------
    SimulationResult
        Aggregate statistics and raw per-patient arrays.

    Raises
    ------
    ValueError
        If ``n_patients`` < 1.

    Examples
    --------
    >>> import numpy as np
    >>> from pubhealth_llm.decision_tree import StrategyParams, simulate_strategy
    >>> params = StrategyParams(
    ...     name="Sumatriptan",
    ...     cost_drug=16.10, cost_ed=63.16, cost_hospital=1093.0,
    ...     u_response_no_recurrence=1.0, u_response_recurrence=0.9,
    ...     u_no_response_endures=-0.3, u_no_response_ed=0.1,
    ...     u_no_response_hospital=-0.3,
    ...     p_response=0.558, p_no_recurrence=0.594,
    ...     p_endures=0.92, p_ed_relief=0.998,
    ... )
    >>> rng = np.random.default_rng(42)
    >>> result = simulate_strategy(params, n_patients=500_000, rng=rng)
    >>> abs(result.expected_cost - 22.058) < 0.05
    True
    """
    if n_patients < 1:
        raise ValueError(f"n_patients must be ≥ 1; got {n_patients!r}.")

    # ── Draw all random numbers in one call ────────────────────────────────
    # Shape: (n_patients, 4) — one row per patient, one column per chance node.
    # Comparing a column against a scalar produces a boolean array of length
    # n_patients: True for patients whose draw falls below the probability
    # threshold, meaning the corresponding event occurred.
    r = rng.random((n_patients, 4))

    responded  = r[:, 0] < params.p_response
    no_rec     = r[:, 1] < params.p_no_recurrence
    endures    = r[:, 2] < params.p_endures
    ed_relief  = r[:, 3] < params.p_ed_relief

    # ── Terminal path masks (mutually exclusive, collectively exhaustive) ──
    # Each patient satisfies exactly one of these five conditions.
    path_1 = responded  &  no_rec                        # response, no recurrence
    path_2 = responded  & ~no_rec                        # response, recurrence
    path_3 = ~responded &  endures                       # no response, endures
    path_4 = ~responded & ~endures &  ed_relief          # no response, ED relief
    path_5 = ~responded & ~endures & ~ed_relief          # no response, hospitalised

    # ── Costs ─────────────────────────────────────────────────────────────
    # Every patient pays for their drug dose regardless of outcome.
    # Additional costs are added element-wise based on their path.
    cost = np.full(n_patients, params.cost_drug, dtype=np.float64)
    cost += np.where(path_2, params.cost_drug,    0.0)   # second dose on recurrence
    cost += np.where(path_4 | path_5, params.cost_ed,       0.0)   # ED visit
    cost += np.where(path_5,          params.cost_hospital,  0.0)   # hospitalisation

    # ── Utilities ─────────────────────────────────────────────────────────
    # np.select scans conditions left-to-right and assigns the matching
    # choice to each element — equivalent to a vectorised if/elif/else.
    utility = np.select(
        condlist=[path_1, path_2, path_3, path_4, path_5],
        choicelist=[
            params.u_response_no_recurrence,
            params.u_response_recurrence,
            params.u_no_response_endures,
            params.u_no_response_ed,
            params.u_no_response_hospital,
        ],
        default=np.nan,
    )

    # ── Path labels ───────────────────────────────────────────────────────
    # Assign integer indices via np.select, then index into ALL_PATHS array
    # to produce string labels — all without a Python loop.
    path_indices = np.select(
        condlist=[path_1, path_2, path_3, path_4, path_5],
        choicelist=[0, 1, 2, 3, 4],
        default=-1,
    )
    path_label_array = np.array(ALL_PATHS)
    paths = path_label_array[path_indices]

    # ── Aggregate statistics ───────────────────────────────────────────────
    expected_cost    = float(cost.mean())
    expected_utility = float(utility.mean())
    n_float          = float(n_patients)
    cost_se          = float(cost.std(ddof=1) / math.sqrt(n_float))
    utility_se       = float(utility.std(ddof=1) / math.sqrt(n_float))

    path_frequencies: dict[str, float] = {
        path: float((paths == path).sum()) / n_patients
        for path in ALL_PATHS
    }

    return SimulationResult(
        strategy_name=params.name,
        n_patients=n_patients,
        expected_cost=expected_cost,
        expected_utility=expected_utility,
        cost_se=cost_se,
        utility_se=utility_se,
        path_frequencies=path_frequencies,
        _cost=cost,
        _utility=utility,
        _paths=paths,
    )


def compare_strategies(
    results: Sequence[SimulationResult],
    reference_index: int = 0,
    annualise: bool = True,
    days_per_period: float = 1.0,
) -> list[IncrementalResult]:
    """
    Compute incremental cost-effectiveness ratios for each strategy vs. a
    reference strategy.

    Parameters
    ----------
    results : sequence of SimulationResult
        One entry per strategy. Must contain at least two entries.
    reference_index : int
        Index into ``results`` identifying the reference (comparator) strategy.
        Defaults to 0 (the first strategy).
    annualise : bool
        If ``True`` (default), multiply the raw ICER by ``365 / days_per_period``
        to express cost per QALY on an annual basis.  The Evans model covers
        a 24-h episode, so the simulation utility is per-day; multiplying by
        365 converts to per-year (per-QALY) as reported in the paper.
    days_per_period : float
        Duration of one simulation period in days. Default 1.0 (one 24-h
        attack). Ignored when ``annualise=False``.

    Returns
    -------
    list of IncrementalResult
        One entry per non-reference strategy. The reference strategy itself
        is excluded from the output.

    Raises
    ------
    ValueError
        If ``results`` has fewer than 2 entries, or ``reference_index`` is
        out of range.

    Notes
    -----
    Standard errors of incremental quantities are computed assuming
    independent simulations across strategies (zero covariance):

        SE(ΔC) = sqrt(SE(C_a)² + SE(C_ref)²)

    The ICER standard error is not computed (it requires the delta method
    or bootstrap and is left to the caller for the probabilistic sensitivity
    analysis step).
    """
    if len(results) < 2:
        raise ValueError(
            f"compare_strategies requires at least 2 results; got {len(results)}."
        )
    if not (0 <= reference_index < len(results)):
        raise ValueError(
            f"reference_index {reference_index!r} is out of range for "
            f"{len(results)} results."
        )

    reference = results[reference_index]
    annualisation_factor = (365.0 / days_per_period) if annualise else 1.0

    comparisons: list[IncrementalResult] = []

    for result in results:
        if result is reference:
            continue

        d_cost = result.expected_cost    - reference.expected_cost
        d_util = result.expected_utility - reference.expected_utility

        # ICER = ΔCost / ΔUtility × annualisation factor.
        # Special cases: zero or negative incremental utility.
        if d_util == 0.0:
            if d_cost > 0.0:
                icer_annual = float("inf")
            elif d_cost < 0.0:
                icer_annual = float("-inf")
            else:
                icer_annual = float("nan")
        else:
            icer_annual = (d_cost / d_util) * annualisation_factor

        # SE of incremental cost and utility (independent arms)
        d_cost_se = math.sqrt(result.cost_se    ** 2 + reference.cost_se    ** 2)
        d_util_se = math.sqrt(result.utility_se ** 2 + reference.utility_se ** 2)

        comparisons.append(
            IncrementalResult(
                strategy=result.strategy_name,
                reference=reference.strategy_name,
                incremental_cost=d_cost,
                incremental_utility=d_util,
                icer_annual=icer_annual,
                incremental_cost_se=d_cost_se,
                incremental_utility_se=d_util_se,
            )
        )

    return comparisons
