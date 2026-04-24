"""
Tests for pubhealth_llm.decision_tree.simulation.

Coverage
--------
StrategyParams
    - Valid construction with typical and boundary parameter values
    - Validation rejects negative costs, out-of-range probabilities,
      and empty names

analytical_expected_values
    - Path probabilities are individually correct and sum to 1
    - Expected cost and utility match Evans 1997 Table VI reference values
    - Analytical ICER matches Evans 1997 Table VII

simulate_strategy
    - Return type and field values are correct
    - Array shapes are correct
    - Monte Carlo estimates converge to analytical values within 5 SE
    - Path frequency distribution converges to analytical probabilities
    - Paths are mutually exclusive (frequencies sum to 1)
    - Deterministic with the same RNG seed
    - Different seeds produce different results
    - All five paths appear when n is large enough
    - Boundary probability cases (p=0, p=1) eliminate the correct paths
    - All simulated costs are non-negative
    - All simulated utilities are drawn from the declared utility set
    - n_patients < 1 raises ValueError

compare_strategies
    - Returns correct number of IncrementalResult entries
    - Reference strategy is excluded from the output
    - Incremental cost and utility are numerically correct
    - ICER is within acceptable Monte Carlo range of Evans analytical value
    - Supports non-default reference index
    - Handles three-strategy comparison correctly
    - Zero incremental utility produces inf / -inf / nan ICER as appropriate
    - Fewer than 2 results raises ValueError
    - Out-of-range reference_index raises ValueError
    - Standard errors are non-negative

Reference values
----------------
Evans et al. (1997), Tables VI and VII (1995 Canadian dollars):

    Sumatriptan:  E[cost] = $22.058, E[utility] = 0.417
    Caffeine:     E[cost] =  $4.715, E[utility] = 0.201
    ΔCost        = $17.34
    ΔUtility     = 0.216
    ICER (annual)= $29,366 Can/QALY

Note on c_ed
------------
The Evans paper reports slightly different ED costs for each arm ($63.16 for
sumatriptan, $63.13 for caffeine). Tomas Aragón's reference implementation
uses $63.16 for both to simplify parameterisation; the difference in expected
cost is < $0.001. The fixtures below use $63.16 for both arms to align with
that reference implementation.
"""

import math

import numpy as np
import pytest

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

# ---------------------------------------------------------------------------
# Shared tolerance constants
# ---------------------------------------------------------------------------

# Monte Carlo results with N=500_000 converge to within ~5 standard errors
# of the analytical values.  These tolerances are generous enough to avoid
# flaky tests while still catching genuine computational errors.
COST_ATOL    = 0.10   # $0.10 absolute tolerance on expected cost
UTILITY_ATOL = 0.005  # 0.005 absolute tolerance on expected utility
ICER_RTOL    = 0.01   # 1% relative tolerance on annual ICER
FREQ_ATOL    = 0.005  # 0.5% absolute tolerance on path frequencies

# Simulation size used in convergence tests — large enough for tight CIs,
# small enough for fast test execution (< 1 s per call on a laptop).
N_SIM = 500_000


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sumatriptan() -> StrategyParams:
    """Evans 1997 sumatriptan parameters (Table VI)."""
    return StrategyParams(
        name="Sumatriptan",
        cost_drug=16.10,
        cost_ed=63.16,
        cost_hospital=1093.0,
        u_response_no_recurrence=1.0,
        u_response_recurrence=0.9,
        u_no_response_endures=-0.3,
        u_no_response_ed=0.1,
        u_no_response_hospital=-0.3,
        p_response=0.558,
        p_no_recurrence=0.594,
        p_endures=0.92,
        p_ed_relief=0.998,
    )


@pytest.fixture(scope="module")
def caffeine() -> StrategyParams:
    """Evans 1997 caffeine/ergotamine parameters (Table VI, c_ed simplified to $63.16)."""
    return StrategyParams(
        name="Caffeine/Ergotamine",
        cost_drug=1.32,
        cost_ed=63.16,
        cost_hospital=1093.0,
        u_response_no_recurrence=1.0,
        u_response_recurrence=0.9,
        u_no_response_endures=-0.3,
        u_no_response_ed=0.1,
        u_no_response_hospital=-0.3,
        p_response=0.379,
        p_no_recurrence=0.703,
        p_endures=0.92,
        p_ed_relief=0.998,
    )


@pytest.fixture(scope="module")
def rng_module() -> np.random.Generator:
    """Module-scoped RNG with a fixed seed for determinism across the test suite."""
    return np.random.default_rng(seed=2026)


@pytest.fixture(scope="module")
def sim_sumatriptan(sumatriptan, rng_module) -> SimulationResult:
    """Pre-computed simulation result for sumatriptan (reused across tests)."""
    return simulate_strategy(sumatriptan, N_SIM, np.random.default_rng(seed=1001))


@pytest.fixture(scope="module")
def sim_caffeine(caffeine, rng_module) -> SimulationResult:
    """Pre-computed simulation result for caffeine (reused across tests)."""
    return simulate_strategy(caffeine, N_SIM, np.random.default_rng(seed=1002))


# ---------------------------------------------------------------------------
# StrategyParams — valid construction
# ---------------------------------------------------------------------------


class TestStrategyParamsValid:

    def test_construction_with_typical_values(self, sumatriptan):
        """StrategyParams constructs without error for typical Evans parameters."""
        assert sumatriptan.name == "Sumatriptan"
        assert sumatriptan.cost_drug == 16.10
        assert sumatriptan.p_response == 0.558

    def test_name_preserved(self, caffeine):
        assert caffeine.name == "Caffeine/Ergotamine"

    def test_zero_cost_is_valid(self):
        """A zero drug cost (e.g. a free intervention) must be accepted."""
        params = StrategyParams(
            name="Free treatment",
            cost_drug=0.0, cost_ed=0.0, cost_hospital=0.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.5, p_no_recurrence=0.5,
            p_endures=0.5, p_ed_relief=0.5,
        )
        assert params.cost_drug == 0.0

    def test_negative_utility_is_valid(self):
        """Utilities may be negative (severe suffering states)."""
        params = StrategyParams(
            name="Painful treatment",
            cost_drug=10.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=-0.1,
            u_response_recurrence=-0.2,
            u_no_response_endures=-0.8,
            u_no_response_ed=-0.5,
            u_no_response_hospital=-0.9,
            p_response=0.3, p_no_recurrence=0.5,
            p_endures=0.7, p_ed_relief=0.9,
        )
        assert params.u_response_no_recurrence == -0.1

    def test_boundary_probability_zero(self):
        """p = 0.0 is a valid probability (treatment never works)."""
        params = StrategyParams(
            name="Ineffective",
            cost_drug=5.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.0, p_no_recurrence=0.5,
            p_endures=0.9, p_ed_relief=0.99,
        )
        assert params.p_response == 0.0

    def test_boundary_probability_one(self):
        """p = 1.0 is a valid probability (treatment always works)."""
        params = StrategyParams(
            name="Perfect",
            cost_drug=100.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=1.0, p_no_recurrence=1.0,
            p_endures=0.9, p_ed_relief=0.99,
        )
        assert params.p_response == 1.0

    def test_is_immutable(self, sumatriptan):
        """StrategyParams is frozen — attribute assignment must raise."""
        with pytest.raises((AttributeError, TypeError)):
            sumatriptan.cost_drug = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StrategyParams — validation failures
# ---------------------------------------------------------------------------


class TestStrategyParamsValidation:

    def _base_kwargs(self) -> dict:
        return dict(
            name="Test",
            cost_drug=10.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.5, p_no_recurrence=0.5,
            p_endures=0.5, p_ed_relief=0.5,
        )

    def test_empty_name_raises(self):
        kw = self._base_kwargs()
        kw["name"] = ""
        with pytest.raises(ValueError, match="name"):
            StrategyParams(**kw)

    def test_whitespace_name_raises(self):
        kw = self._base_kwargs()
        kw["name"] = "   "
        with pytest.raises(ValueError, match="name"):
            StrategyParams(**kw)

    def test_negative_cost_drug_raises(self):
        kw = self._base_kwargs()
        kw["cost_drug"] = -0.01
        with pytest.raises(ValueError, match="cost_drug"):
            StrategyParams(**kw)

    def test_negative_cost_ed_raises(self):
        kw = self._base_kwargs()
        kw["cost_ed"] = -1.0
        with pytest.raises(ValueError, match="cost_ed"):
            StrategyParams(**kw)

    def test_negative_cost_hospital_raises(self):
        kw = self._base_kwargs()
        kw["cost_hospital"] = -100.0
        with pytest.raises(ValueError, match="cost_hospital"):
            StrategyParams(**kw)

    def test_p_response_above_1_raises(self):
        kw = self._base_kwargs()
        kw["p_response"] = 1.001
        with pytest.raises(ValueError, match="p_response"):
            StrategyParams(**kw)

    def test_p_response_below_0_raises(self):
        kw = self._base_kwargs()
        kw["p_response"] = -0.001
        with pytest.raises(ValueError, match="p_response"):
            StrategyParams(**kw)

    def test_p_no_recurrence_above_1_raises(self):
        kw = self._base_kwargs()
        kw["p_no_recurrence"] = 1.1
        with pytest.raises(ValueError, match="p_no_recurrence"):
            StrategyParams(**kw)

    def test_p_endures_above_1_raises(self):
        kw = self._base_kwargs()
        kw["p_endures"] = 2.0
        with pytest.raises(ValueError, match="p_endures"):
            StrategyParams(**kw)

    def test_p_ed_relief_below_0_raises(self):
        kw = self._base_kwargs()
        kw["p_ed_relief"] = -0.5
        with pytest.raises(ValueError, match="p_ed_relief"):
            StrategyParams(**kw)


# ---------------------------------------------------------------------------
# analytical_expected_values
# ---------------------------------------------------------------------------


class TestAnalyticalExpectedValues:
    """Verify analytical calculations against Evans 1997 Tables VI and VII."""

    # Evans 1997 Table VI reference values
    SUMA_EC  = 22.058057
    SUMA_EU  = 0.4168609
    CAFF_EC  =  4.714972
    CAFF_EU  = 0.2012760

    # Evans 1997 Table VI path probabilities (sumatriptan)
    SUMA_PATHS = {
        PATH_RESPONSE_NO_RECURRENCE: 0.331452,
        PATH_RESPONSE_RECURRENCE:    0.226548,
        PATH_NO_RESPONSE_ENDURES:    0.406640,
        PATH_NO_RESPONSE_ED:         0.035289,
        PATH_NO_RESPONSE_HOSPITAL:   0.000071,
    }

    # Evans 1997 Table VI path probabilities (caffeine/ergotamine)
    CAFF_PATHS = {
        PATH_RESPONSE_NO_RECURRENCE: 0.266437,
        PATH_RESPONSE_RECURRENCE:    0.112563,
        PATH_NO_RESPONSE_ENDURES:    0.571320,
        PATH_NO_RESPONSE_ED:         0.049581,
        PATH_NO_RESPONSE_HOSPITAL:   0.000099,
    }

    def test_sumatriptan_expected_cost(self, sumatriptan):
        result = analytical_expected_values(sumatriptan)
        assert abs(result["expected_cost"] - self.SUMA_EC) < 0.001, (
            f"Expected ~{self.SUMA_EC}, got {result['expected_cost']:.6f}"
        )

    def test_sumatriptan_expected_utility(self, sumatriptan):
        result = analytical_expected_values(sumatriptan)
        assert abs(result["expected_utility"] - self.SUMA_EU) < 0.0001, (
            f"Expected ~{self.SUMA_EU}, got {result['expected_utility']:.7f}"
        )

    def test_caffeine_expected_cost(self, caffeine):
        result = analytical_expected_values(caffeine)
        assert abs(result["expected_cost"] - self.CAFF_EC) < 0.001, (
            f"Expected ~{self.CAFF_EC}, got {result['expected_cost']:.6f}"
        )

    def test_caffeine_expected_utility(self, caffeine):
        result = analytical_expected_values(caffeine)
        assert abs(result["expected_utility"] - self.CAFF_EU) < 0.0001, (
            f"Expected ~{self.CAFF_EU}, got {result['expected_utility']:.7f}"
        )

    def test_sumatriptan_path_probabilities_sum_to_1(self, sumatriptan):
        result = analytical_expected_values(sumatriptan)
        total = sum(result["path_probabilities"].values())
        assert abs(total - 1.0) < 1e-10, f"Path probabilities sum to {total}"

    def test_caffeine_path_probabilities_sum_to_1(self, caffeine):
        result = analytical_expected_values(caffeine)
        total = sum(result["path_probabilities"].values())
        assert abs(total - 1.0) < 1e-10, f"Path probabilities sum to {total}"

    def test_sumatriptan_individual_path_probabilities(self, sumatriptan):
        result = analytical_expected_values(sumatriptan)
        probs = result["path_probabilities"]
        for path, expected in self.SUMA_PATHS.items():
            assert abs(probs[path] - expected) < 0.000001, (
                f"Path {path}: expected {expected}, got {probs[path]:.6f}"
            )

    def test_caffeine_individual_path_probabilities(self, caffeine):
        result = analytical_expected_values(caffeine)
        probs = result["path_probabilities"]
        for path, expected in self.CAFF_PATHS.items():
            assert abs(probs[path] - expected) < 0.000001, (
                f"Path {path}: expected {expected}, got {probs[path]:.6f}"
            )

    def test_analytical_icer(self, sumatriptan, caffeine):
        """Analytical ICER should match Evans Table VII: ~$29,366 Can/QALY."""
        s = analytical_expected_values(sumatriptan)
        c = analytical_expected_values(caffeine)
        d_cost = s["expected_cost"] - c["expected_cost"]
        d_util = s["expected_utility"] - c["expected_utility"]
        icer = (d_cost / d_util) * 365
        evans_icer = 29366.0
        assert abs(icer - evans_icer) < 10.0, (
            f"Analytical ICER {icer:.0f} deviates from Evans reference {evans_icer}"
        )

    def test_all_paths_present_in_output(self, sumatriptan):
        """analytical_expected_values must return probabilities for all 5 paths."""
        result = analytical_expected_values(sumatriptan)
        assert set(result["path_probabilities"].keys()) == set(ALL_PATHS)

    def test_result_keys(self, sumatriptan):
        result = analytical_expected_values(sumatriptan)
        assert "expected_cost"    in result
        assert "expected_utility" in result
        assert "path_probabilities" in result


# ---------------------------------------------------------------------------
# simulate_strategy — return type and structure
# ---------------------------------------------------------------------------


class TestSimulateStrategyStructure:

    def test_returns_simulation_result(self, sumatriptan):
        rng = np.random.default_rng(0)
        result = simulate_strategy(sumatriptan, 1000, rng)
        assert isinstance(result, SimulationResult)

    def test_strategy_name_in_result(self, sumatriptan):
        rng = np.random.default_rng(0)
        result = simulate_strategy(sumatriptan, 1000, rng)
        assert result.strategy_name == "Sumatriptan"

    def test_n_patients_in_result(self, sumatriptan):
        rng = np.random.default_rng(0)
        result = simulate_strategy(sumatriptan, 1000, rng)
        assert result.n_patients == 1000

    def test_cost_array_shape(self, sumatriptan):
        rng = np.random.default_rng(0)
        result = simulate_strategy(sumatriptan, 2000, rng)
        assert result._cost.shape == (2000,)

    def test_utility_array_shape(self, sumatriptan):
        rng = np.random.default_rng(0)
        result = simulate_strategy(sumatriptan, 2000, rng)
        assert result._utility.shape == (2000,)

    def test_paths_array_shape(self, sumatriptan):
        rng = np.random.default_rng(0)
        result = simulate_strategy(sumatriptan, 2000, rng)
        assert result._paths.shape == (2000,)

    def test_path_frequencies_has_all_paths(self, sim_sumatriptan):
        assert set(sim_sumatriptan.path_frequencies.keys()) == set(ALL_PATHS)

    def test_n_patients_zero_raises(self, sumatriptan):
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError):
            simulate_strategy(sumatriptan, 0, rng)

    def test_n_patients_negative_raises(self, sumatriptan):
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError):
            simulate_strategy(sumatriptan, -1, rng)

    def test_single_patient(self, sumatriptan):
        """simulate_strategy must work with n_patients=1."""
        rng = np.random.default_rng(0)
        result = simulate_strategy(sumatriptan, 1, rng)
        assert result.n_patients == 1
        assert result._cost.shape == (1,)


# ---------------------------------------------------------------------------
# simulate_strategy — numerical convergence
# ---------------------------------------------------------------------------


class TestSimulateStrategyConvergence:
    """
    Verify that Monte Carlo estimates converge to analytical values.

    Tolerance rationale: with N=500_000 and typical standard deviations of
    ~8 for cost and ~0.4 for utility, the standard errors are ~0.011 and
    ~0.0006 respectively. A tolerance of 5× SE guarantees P(failure) < 3×10⁻⁷
    under normality — effectively never failing due to random chance.
    """

    def test_sumatriptan_expected_cost(self, sim_sumatriptan):
        analytical = 22.058057
        assert abs(sim_sumatriptan.expected_cost - analytical) < COST_ATOL, (
            f"E[cost|Sumatriptan] = {sim_sumatriptan.expected_cost:.4f}, "
            f"expected ≈ {analytical}"
        )

    def test_sumatriptan_expected_utility(self, sim_sumatriptan):
        analytical = 0.4168609
        assert abs(sim_sumatriptan.expected_utility - analytical) < UTILITY_ATOL, (
            f"E[utility|Sumatriptan] = {sim_sumatriptan.expected_utility:.6f}, "
            f"expected ≈ {analytical}"
        )

    def test_caffeine_expected_cost(self, sim_caffeine):
        analytical = 4.714972
        assert abs(sim_caffeine.expected_cost - analytical) < COST_ATOL, (
            f"E[cost|Caffeine] = {sim_caffeine.expected_cost:.4f}, "
            f"expected ≈ {analytical}"
        )

    def test_caffeine_expected_utility(self, sim_caffeine):
        analytical = 0.2012760
        assert abs(sim_caffeine.expected_utility - analytical) < UTILITY_ATOL, (
            f"E[utility|Caffeine] = {sim_caffeine.expected_utility:.6f}, "
            f"expected ≈ {analytical}"
        )

    def test_sumatriptan_path_frequencies(self, sim_sumatriptan, sumatriptan):
        """Simulated path frequencies must be close to analytical path probabilities."""
        analytical = analytical_expected_values(sumatriptan)["path_probabilities"]
        for path in ALL_PATHS:
            simulated = sim_sumatriptan.path_frequencies[path]
            expected  = analytical[path]
            assert abs(simulated - expected) < FREQ_ATOL, (
                f"Path {path}: simulated {simulated:.5f}, analytical {expected:.6f}"
            )

    def test_caffeine_path_frequencies(self, sim_caffeine, caffeine):
        analytical = analytical_expected_values(caffeine)["path_probabilities"]
        for path in ALL_PATHS:
            simulated = sim_caffeine.path_frequencies[path]
            expected  = analytical[path]
            assert abs(simulated - expected) < FREQ_ATOL, (
                f"Path {path}: simulated {simulated:.5f}, analytical {expected:.6f}"
            )

    def test_path_frequencies_sum_to_1_sumatriptan(self, sim_sumatriptan):
        total = sum(sim_sumatriptan.path_frequencies.values())
        assert abs(total - 1.0) < 1e-10, f"Path frequencies sum to {total}"

    def test_path_frequencies_sum_to_1_caffeine(self, sim_caffeine):
        total = sum(sim_caffeine.path_frequencies.values())
        assert abs(total - 1.0) < 1e-10

    def test_cost_se_is_positive(self, sim_sumatriptan):
        assert sim_sumatriptan.cost_se > 0.0

    def test_utility_se_is_positive(self, sim_sumatriptan):
        assert sim_sumatriptan.utility_se > 0.0

    def test_cost_se_decreases_with_larger_n(self, sumatriptan):
        """Larger N produces a tighter SE — law of large numbers."""
        rng_a = np.random.default_rng(42)
        rng_b = np.random.default_rng(42)
        small = simulate_strategy(sumatriptan, 1_000,  rng_a)
        large = simulate_strategy(sumatriptan, 100_000, rng_b)
        assert large.cost_se < small.cost_se


# ---------------------------------------------------------------------------
# simulate_strategy — physical constraints
# ---------------------------------------------------------------------------


class TestSimulateStrategyPhysicalConstraints:

    def test_all_costs_nonnegative(self, sim_sumatriptan):
        """Costs are always ≥ 0 (drug cost + optional add-ons)."""
        assert np.all(sim_sumatriptan._cost >= 0.0), (
            "Found negative cost values in simulation output."
        )

    def test_all_utilities_from_declared_set(self, sumatriptan, sim_sumatriptan):
        """Every simulated utility must be one of the five declared utility values."""
        declared = {
            sumatriptan.u_response_no_recurrence,
            sumatriptan.u_response_recurrence,
            sumatriptan.u_no_response_endures,
            sumatriptan.u_no_response_ed,
            sumatriptan.u_no_response_hospital,
        }
        unique_simulated = set(np.unique(sim_sumatriptan._utility).tolist())
        assert unique_simulated <= declared, (
            f"Simulated utilities {unique_simulated} not a subset of declared {declared}"
        )

    def test_no_nan_in_costs(self, sim_sumatriptan):
        assert not np.any(np.isnan(sim_sumatriptan._cost))

    def test_no_nan_in_utilities(self, sim_sumatriptan):
        assert not np.any(np.isnan(sim_sumatriptan._utility))

    def test_all_five_paths_appear_with_large_n(self, sumatriptan):
        """With realistic parameters and large N, all five terminal paths are reached."""
        rng = np.random.default_rng(99)
        result = simulate_strategy(sumatriptan, 200_000, rng)
        for path in ALL_PATHS:
            assert result.path_frequencies[path] > 0.0, (
                f"Path '{path}' was never reached in 200,000 patients."
            )


# ---------------------------------------------------------------------------
# simulate_strategy — boundary probability cases
# ---------------------------------------------------------------------------


class TestSimulateStrategyBoundaryProbabilities:

    def _base_params(self, **overrides) -> StrategyParams:
        kwargs = dict(
            name="Test",
            cost_drug=10.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.5, p_no_recurrence=0.5,
            p_endures=0.9, p_ed_relief=0.99,
        )
        kwargs.update(overrides)
        return StrategyParams(**kwargs)

    def test_p_response_zero_eliminates_paths_1_and_2(self):
        """When p_response=0, all patients fail treatment → paths 1 & 2 impossible."""
        params = self._base_params(p_response=0.0)
        rng = np.random.default_rng(0)
        result = simulate_strategy(params, 10_000, rng)
        assert result.path_frequencies[PATH_RESPONSE_NO_RECURRENCE] == 0.0
        assert result.path_frequencies[PATH_RESPONSE_RECURRENCE]    == 0.0

    def test_p_response_one_eliminates_paths_3_4_5(self):
        """When p_response=1, all patients respond → paths 3, 4, 5 impossible."""
        params = self._base_params(p_response=1.0)
        rng = np.random.default_rng(0)
        result = simulate_strategy(params, 10_000, rng)
        assert result.path_frequencies[PATH_NO_RESPONSE_ENDURES]  == 0.0
        assert result.path_frequencies[PATH_NO_RESPONSE_ED]       == 0.0
        assert result.path_frequencies[PATH_NO_RESPONSE_HOSPITAL] == 0.0

    def test_p_no_recurrence_one_eliminates_path_2(self):
        """When p_no_recurrence=1, no recurrences → path 2 impossible."""
        params = self._base_params(p_no_recurrence=1.0, p_response=0.8)
        rng = np.random.default_rng(0)
        result = simulate_strategy(params, 10_000, rng)
        assert result.path_frequencies[PATH_RESPONSE_RECURRENCE] == 0.0

    def test_p_endures_one_eliminates_paths_4_and_5(self):
        """When p_endures=1, no one seeks ED care → paths 4 & 5 impossible."""
        params = self._base_params(p_endures=1.0, p_response=0.3)
        rng = np.random.default_rng(0)
        result = simulate_strategy(params, 10_000, rng)
        assert result.path_frequencies[PATH_NO_RESPONSE_ED]       == 0.0
        assert result.path_frequencies[PATH_NO_RESPONSE_HOSPITAL] == 0.0

    def test_p_ed_relief_one_eliminates_path_5(self):
        """When p_ed_relief=1, no hospitalisations → path 5 impossible."""
        params = self._base_params(p_ed_relief=1.0, p_response=0.3, p_endures=0.5)
        rng = np.random.default_rng(0)
        result = simulate_strategy(params, 10_000, rng)
        assert result.path_frequencies[PATH_NO_RESPONSE_HOSPITAL] == 0.0


# ---------------------------------------------------------------------------
# simulate_strategy — reproducibility
# ---------------------------------------------------------------------------


class TestSimulateStrategyReproducibility:

    def test_same_seed_gives_same_expected_cost(self, sumatriptan):
        r1 = simulate_strategy(sumatriptan, 50_000, np.random.default_rng(7))
        r2 = simulate_strategy(sumatriptan, 50_000, np.random.default_rng(7))
        assert r1.expected_cost == r2.expected_cost

    def test_same_seed_gives_same_expected_utility(self, sumatriptan):
        r1 = simulate_strategy(sumatriptan, 50_000, np.random.default_rng(7))
        r2 = simulate_strategy(sumatriptan, 50_000, np.random.default_rng(7))
        assert r1.expected_utility == r2.expected_utility

    def test_different_seeds_give_different_results(self, sumatriptan):
        r1 = simulate_strategy(sumatriptan, 50_000, np.random.default_rng(7))
        r2 = simulate_strategy(sumatriptan, 50_000, np.random.default_rng(8))
        # Extremely unlikely to be identical by chance at N=50,000
        assert r1.expected_cost != r2.expected_cost


# ---------------------------------------------------------------------------
# SimulationResult — confidence interval helpers
# ---------------------------------------------------------------------------


class TestSimulationResultHelpers:

    def test_ci_cost_contains_expected_cost(self, sim_sumatriptan):
        lo, hi = sim_sumatriptan.ci_cost()
        assert lo < sim_sumatriptan.expected_cost < hi

    def test_ci_utility_contains_expected_utility(self, sim_sumatriptan):
        lo, hi = sim_sumatriptan.ci_utility()
        assert lo < sim_sumatriptan.expected_utility < hi

    def test_ci_wider_with_larger_z(self, sim_sumatriptan):
        lo_95, hi_95 = sim_sumatriptan.ci_cost(z=1.96)
        lo_99, hi_99 = sim_sumatriptan.ci_cost(z=2.576)
        assert (hi_99 - lo_99) > (hi_95 - lo_95)


# ---------------------------------------------------------------------------
# compare_strategies — structure and error handling
# ---------------------------------------------------------------------------


class TestCompareStrategiesStructure:

    def test_two_strategies_returns_one_result(self, sim_sumatriptan, sim_caffeine):
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        assert len(comparisons) == 1

    def test_returns_list_of_incremental_results(self, sim_sumatriptan, sim_caffeine):
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        assert all(isinstance(c, IncrementalResult) for c in comparisons)

    def test_reference_excluded_from_output(self, sim_sumatriptan, sim_caffeine):
        """The reference strategy's name must not appear as strategy in any result."""
        comparisons = compare_strategies(
            [sim_caffeine, sim_sumatriptan], reference_index=0
        )
        reference_name = sim_caffeine.strategy_name
        for c in comparisons:
            assert c.strategy != reference_name

    def test_strategy_name_in_result(self, sim_sumatriptan, sim_caffeine):
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        assert comparisons[0].strategy == sim_sumatriptan.strategy_name

    def test_reference_name_in_result(self, sim_sumatriptan, sim_caffeine):
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        assert comparisons[0].reference == sim_caffeine.strategy_name

    def test_fewer_than_two_results_raises(self, sim_sumatriptan):
        with pytest.raises(ValueError):
            compare_strategies([sim_sumatriptan])

    def test_out_of_range_reference_index_raises(self, sim_sumatriptan, sim_caffeine):
        with pytest.raises(ValueError):
            compare_strategies([sim_caffeine, sim_sumatriptan], reference_index=5)

    def test_negative_reference_index_raises(self, sim_sumatriptan, sim_caffeine):
        with pytest.raises(ValueError):
            compare_strategies([sim_caffeine, sim_sumatriptan], reference_index=-1)

    def test_three_strategies_returns_two_results(self, sumatriptan, caffeine):
        """Three strategies vs. one reference → two IncrementalResult entries."""
        # Create a third "placebo" strategy
        placebo = StrategyParams(
            name="Placebo",
            cost_drug=0.50, cost_ed=63.16, cost_hospital=1093.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.15, p_no_recurrence=0.60,
            p_endures=0.92, p_ed_relief=0.998,
        )
        rng = np.random.default_rng(55)
        r_placebo   = simulate_strategy(placebo,      50_000, np.random.default_rng(55))
        r_caffeine  = simulate_strategy(caffeine,     50_000, np.random.default_rng(56))
        r_sumatript = simulate_strategy(sumatriptan,  50_000, np.random.default_rng(57))

        comparisons = compare_strategies(
            [r_placebo, r_caffeine, r_sumatript], reference_index=0
        )
        assert len(comparisons) == 2

    def test_non_default_reference_index(self, sim_sumatriptan, sim_caffeine):
        """Using reference_index=1 should set sumatriptan as the reference."""
        comparisons = compare_strategies(
            [sim_caffeine, sim_sumatriptan], reference_index=1
        )
        assert len(comparisons) == 1
        assert comparisons[0].reference == sim_sumatriptan.strategy_name
        assert comparisons[0].strategy  == sim_caffeine.strategy_name


# ---------------------------------------------------------------------------
# compare_strategies — numerical correctness
# ---------------------------------------------------------------------------


class TestCompareStrategiesNumerics:
    """
    Evans 1997 Table VII reference values (health-departmental perspective):

        ΔCost    ≈ $17.34
        ICER     ≈ $29,366 Can/QALY

    Monte Carlo results with N=500,000 should be within 1% of these values.
    """

    DELTA_COST_EVANS = 17.34
    ICER_EVANS       = 29_366.0

    def test_incremental_cost_close_to_evans(self, sim_sumatriptan, sim_caffeine):
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        d_cost = comparisons[0].incremental_cost
        assert abs(d_cost - self.DELTA_COST_EVANS) < 0.15, (
            f"ΔCost = {d_cost:.4f}, expected ≈ {self.DELTA_COST_EVANS}"
        )

    def test_incremental_utility_positive(self, sim_sumatriptan, sim_caffeine):
        """Sumatriptan must have higher utility than caffeine/ergotamine."""
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        assert comparisons[0].incremental_utility > 0.0

    def test_icer_close_to_evans(self, sim_sumatriptan, sim_caffeine):
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        icer = comparisons[0].icer_annual
        assert abs(icer - self.ICER_EVANS) / self.ICER_EVANS < ICER_RTOL, (
            f"ICER = ${icer:.0f}/QALY, expected ≈ ${self.ICER_EVANS:.0f}/QALY"
        )

    def test_incremental_cost_se_nonnegative(self, sim_sumatriptan, sim_caffeine):
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        assert comparisons[0].incremental_cost_se >= 0.0

    def test_incremental_utility_se_nonnegative(self, sim_sumatriptan, sim_caffeine):
        comparisons = compare_strategies([sim_caffeine, sim_sumatriptan])
        assert comparisons[0].incremental_utility_se >= 0.0

    def test_annualise_false_gives_smaller_icer(self, sim_sumatriptan, sim_caffeine):
        """With annualise=False the ICER should be 1/365 of the annualised value."""
        annual   = compare_strategies([sim_caffeine, sim_sumatriptan], annualise=True)
        daily    = compare_strategies([sim_caffeine, sim_sumatriptan], annualise=False)
        ratio = annual[0].icer_annual / daily[0].icer_annual
        assert abs(ratio - 365.0) < 1.0, (
            f"Expected ratio of ~365; got {ratio:.2f}"
        )


# ---------------------------------------------------------------------------
# compare_strategies — ICER edge cases
# ---------------------------------------------------------------------------


class TestCompareStrategiesICEREdgeCases:

    def _make_result(self, name: str, ec: float, eu: float) -> SimulationResult:
        """Construct a minimal SimulationResult with pre-set mean values."""
        n = 1_000
        cost_arr    = np.full(n, ec)
        utility_arr = np.full(n, eu)
        paths_arr   = np.full(n, PATH_RESPONSE_NO_RECURRENCE)
        return SimulationResult(
            strategy_name=name,
            n_patients=n,
            expected_cost=ec,
            expected_utility=eu,
            cost_se=0.0,
            utility_se=0.0,
            path_frequencies={p: (1.0 if p == PATH_RESPONSE_NO_RECURRENCE else 0.0)
                              for p in ALL_PATHS},
            _cost=cost_arr,
            _utility=utility_arr,
            _paths=paths_arr,
        )

    def test_zero_incremental_utility_positive_cost_gives_inf(self):
        ref = self._make_result("Ref", ec=10.0, eu=0.5)
        exp = self._make_result("Exp", ec=20.0, eu=0.5)   # same utility, more costly
        comparisons = compare_strategies([ref, exp])
        assert comparisons[0].icer_annual == float("inf")

    def test_zero_incremental_utility_negative_cost_gives_neg_inf(self):
        ref = self._make_result("Ref", ec=20.0, eu=0.5)
        exp = self._make_result("Exp", ec=10.0, eu=0.5)   # same utility, less costly
        comparisons = compare_strategies([ref, exp])
        assert comparisons[0].icer_annual == float("-inf")

    def test_zero_incremental_utility_zero_cost_gives_nan(self):
        ref = self._make_result("Ref", ec=10.0, eu=0.5)
        exp = self._make_result("Exp", ec=10.0, eu=0.5)   # identical
        comparisons = compare_strategies([ref, exp])
        assert math.isnan(comparisons[0].icer_annual)
