"""
Tests for pubhealth_llm.decision_tree.formatter.

Coverage
--------
format_path_label
    - Returns human-readable string for every known path constant
    - Raises KeyError for unknown path strings
    - Output contains no underscores (snake_case is gone)

format_icer
    - Positive finite ICER formatted with currency symbol and commas
    - Negative finite ICER formatted with minus sign
    - +inf produces "Dominated" message
    - -inf produces "Dominant" message
    - nan produces "N/A" message
    - Custom currency symbol used correctly

format_analysis — return type and presence of key content
    - Returns a non-empty string
    - Contains the analysis title
    - Contains every strategy name
    - Contains E[cost] values (to 2 d.p.) for each strategy
    - Contains E[utility] values for each strategy
    - Contains ICER value when comparison present
    - Contains path distribution table when show_path_table=True
    - Path table absent when show_path_table=False
    - Contains 95% CI when show_confidence_intervals=True
    - CI absent when show_confidence_intervals=False
    - Contains all five path labels (human-readable)
    - Contains methodological notes section
    - Contains disclaimer warning
    - Currency symbol appears in cost values
    - Currency name appears in header when provided
    - Model citation appears in methodological notes
    - Simulation count formatted with commas (1,000,000)
    - Markdown section separators (---) are present
    - Markdown headers (##) are present

format_analysis — incremental content
    - ΔCost shown with sign prefix
    - ΔUtility shown with sign prefix
    - Dominant strategy produces "dominant" in interpretation
    - Dominated strategy produces "dominated" in interpretation
    - No incremental section when incremental_results is empty

format_analysis — edge cases
    - Single strategy with no comparison renders without error
    - Three strategies renders all three names
    - Empty sim_results raises ValueError
    - Very long strategy name does not raise
    - Custom title appears in output
"""

import math

import numpy as np
import pytest

from pubhealth_llm.decision_tree.formatter import (
    format_analysis,
    format_icer,
    format_path_label,
)
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
    compare_strategies,
    simulate_strategy,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

N_SIM = 50_000   # small N for fast formatter tests — precision not important here


@pytest.fixture(scope="module")
def sumatriptan() -> StrategyParams:
    return StrategyParams(
        name="Sumatriptan",
        cost_drug=16.10, cost_ed=63.16, cost_hospital=1093.0,
        u_response_no_recurrence=1.0, u_response_recurrence=0.9,
        u_no_response_endures=-0.3, u_no_response_ed=0.1,
        u_no_response_hospital=-0.3,
        p_response=0.558, p_no_recurrence=0.594,
        p_endures=0.92, p_ed_relief=0.998,
    )


@pytest.fixture(scope="module")
def caffeine() -> StrategyParams:
    return StrategyParams(
        name="Caffeine/Ergotamine",
        cost_drug=1.32, cost_ed=63.16, cost_hospital=1093.0,
        u_response_no_recurrence=1.0, u_response_recurrence=0.9,
        u_no_response_endures=-0.3, u_no_response_ed=0.1,
        u_no_response_hospital=-0.3,
        p_response=0.379, p_no_recurrence=0.703,
        p_endures=0.92, p_ed_relief=0.998,
    )


@pytest.fixture(scope="module")
def sim_caffeine(caffeine) -> SimulationResult:
    return simulate_strategy(caffeine, N_SIM, np.random.default_rng(2001))


@pytest.fixture(scope="module")
def sim_sumatriptan(sumatriptan) -> SimulationResult:
    return simulate_strategy(sumatriptan, N_SIM, np.random.default_rng(2002))


@pytest.fixture(scope="module")
def two_strategy_comparison(
    sim_caffeine, sim_sumatriptan
) -> tuple[list[SimulationResult], list[IncrementalResult]]:
    sims = [sim_caffeine, sim_sumatriptan]
    incremental = compare_strategies(sims, reference_index=0)
    return sims, incremental


@pytest.fixture(scope="module")
def formatted_two_strategy(two_strategy_comparison) -> str:
    sims, incremental = two_strategy_comparison
    return format_analysis(
        sims,
        incremental,
        title="Migraine Treatment Analysis",
        currency_symbol="$",
        currency_name="1995 Canadian dollars",
    )


def _make_minimal_result(
    name: str,
    expected_cost: float,
    expected_utility: float,
) -> SimulationResult:
    """Construct a SimulationResult with fixed values for formatter tests."""
    n = 1_000
    cost_arr    = np.full(n, expected_cost)
    utility_arr = np.full(n, expected_utility)
    paths_arr   = np.full(n, PATH_RESPONSE_NO_RECURRENCE)
    return SimulationResult(
        strategy_name=name,
        n_patients=n,
        expected_cost=expected_cost,
        expected_utility=expected_utility,
        cost_se=0.01,
        utility_se=0.001,
        path_frequencies={
            p: (1.0 if p == PATH_RESPONSE_NO_RECURRENCE else 0.0)
            for p in ALL_PATHS
        },
        _cost=cost_arr,
        _utility=utility_arr,
        _paths=paths_arr,
    )


def _make_minimal_incremental(
    strategy: str,
    reference: str,
    incremental_cost: float,
    incremental_utility: float,
    icer_annual: float,
) -> IncrementalResult:
    return IncrementalResult(
        strategy=strategy,
        reference=reference,
        incremental_cost=incremental_cost,
        incremental_utility=incremental_utility,
        icer_annual=icer_annual,
        incremental_cost_se=0.01,
        incremental_utility_se=0.001,
    )


# ---------------------------------------------------------------------------
# format_path_label
# ---------------------------------------------------------------------------


class TestFormatPathLabel:

    def test_response_no_recurrence(self):
        label = format_path_label(PATH_RESPONSE_NO_RECURRENCE)
        assert "Response" in label
        assert "recurrence" in label.lower()

    def test_response_recurrence(self):
        label = format_path_label(PATH_RESPONSE_RECURRENCE)
        assert "Response" in label
        assert "recurrence" in label.lower()

    def test_no_response_endures(self):
        label = format_path_label(PATH_NO_RESPONSE_ENDURES)
        assert "No response" in label or "no response" in label.lower()

    def test_no_response_ed(self):
        label = format_path_label(PATH_NO_RESPONSE_ED)
        assert "ED" in label or "emergency" in label.lower()

    def test_no_response_hospital(self):
        label = format_path_label(PATH_NO_RESPONSE_HOSPITAL)
        assert "hospital" in label.lower()

    def test_all_paths_have_labels(self):
        """Every path constant must produce a non-empty label."""
        for path in ALL_PATHS:
            label = format_path_label(path)
            assert isinstance(label, str) and len(label) > 0

    def test_no_underscores_in_output(self):
        """Human-readable labels must not contain snake_case underscores."""
        for path in ALL_PATHS:
            label = format_path_label(path)
            assert "_" not in label, (
                f"Path label for '{path}' contains underscore: {label!r}"
            )

    def test_unknown_path_raises_key_error(self):
        with pytest.raises(KeyError):
            format_path_label("not_a_real_path")


# ---------------------------------------------------------------------------
# format_icer
# ---------------------------------------------------------------------------


class TestFormatIcer:

    def test_positive_icer_includes_currency_symbol(self):
        result = format_icer(29_366.0, "$")
        assert "$" in result

    def test_positive_icer_includes_qaly(self):
        result = format_icer(29_366.0, "$")
        assert "QALY" in result

    def test_positive_icer_formatted_with_commas(self):
        result = format_icer(29_366.0, "$")
        assert "29,366" in result

    def test_positive_icer_has_plus_sign(self):
        result = format_icer(29_366.0, "$")
        assert "+" in result

    def test_negative_icer_has_minus_sign(self):
        result = format_icer(-7_507.0, "$")
        assert "-" in result or "−" in result

    def test_zero_icer_formatted(self):
        result = format_icer(0.0, "$")
        assert "QALY" in result

    def test_positive_inf_gives_dominated_message(self):
        result = format_icer(float("inf"), "$")
        assert "dominated" in result.lower() or "Dominated" in result

    def test_negative_inf_gives_dominant_message(self):
        result = format_icer(float("-inf"), "$")
        assert "dominant" in result.lower() or "Dominant" in result

    def test_nan_gives_na_message(self):
        result = format_icer(float("nan"), "$")
        assert "N/A" in result or "n/a" in result.lower()

    def test_custom_currency_symbol(self):
        result = format_icer(10_000.0, "£")
        assert "£" in result

    def test_euro_symbol(self):
        result = format_icer(50_000.0, "€")
        assert "€" in result


# ---------------------------------------------------------------------------
# format_analysis — return type and structure
# ---------------------------------------------------------------------------


class TestFormatAnalysisStructure:

    def test_returns_string(self, formatted_two_strategy):
        assert isinstance(formatted_two_strategy, str)

    def test_non_empty_output(self, formatted_two_strategy):
        assert len(formatted_two_strategy) > 100

    def test_contains_title(self, formatted_two_strategy):
        assert "Migraine Treatment Analysis" in formatted_two_strategy

    def test_contains_caffeine_name(self, formatted_two_strategy):
        assert "Caffeine/Ergotamine" in formatted_two_strategy

    def test_contains_sumatriptan_name(self, formatted_two_strategy):
        assert "Sumatriptan" in formatted_two_strategy

    def test_contains_markdown_section_headers(self, formatted_two_strategy):
        assert "##" in formatted_two_strategy

    def test_contains_section_separators(self, formatted_two_strategy):
        assert "---" in formatted_two_strategy

    def test_contains_methodological_notes(self, formatted_two_strategy):
        assert "Methodological" in formatted_two_strategy

    def test_contains_disclaimer(self, formatted_two_strategy):
        assert "⚠️" in formatted_two_strategy or "warning" in formatted_two_strategy.lower()

    def test_contains_strategy_results_header(self, formatted_two_strategy):
        assert "Strategy Results" in formatted_two_strategy

    def test_contains_incremental_header(self, formatted_two_strategy):
        assert "Incremental" in formatted_two_strategy

    def test_contains_path_distribution_header(self, formatted_two_strategy):
        assert "Path Distribution" in formatted_two_strategy or "Terminal Path" in formatted_two_strategy

    def test_empty_sim_results_raises(self):
        with pytest.raises(ValueError):
            format_analysis([], [])


# ---------------------------------------------------------------------------
# format_analysis — cost and utility values
# ---------------------------------------------------------------------------


class TestFormatAnalysisValues:

    def test_caffeine_expected_cost_present(self, sim_caffeine, formatted_two_strategy):
        """Expected cost (to 2 d.p.) must appear in the output."""
        cost_str = f"${sim_caffeine.expected_cost:.2f}"
        assert cost_str in formatted_two_strategy, (
            f"Expected '{cost_str}' in output"
        )

    def test_sumatriptan_expected_cost_present(self, sim_sumatriptan, formatted_two_strategy):
        cost_str = f"${sim_sumatriptan.expected_cost:.2f}"
        assert cost_str in formatted_two_strategy

    def test_icer_value_present(self, two_strategy_comparison, formatted_two_strategy):
        _, incremental = two_strategy_comparison
        icer = incremental[0].icer_annual
        # The ICER is in the tens of thousands — check that a substring of it appears
        icer_int = int(abs(icer))
        icer_str = f"{icer_int:,}"[:4]   # first 4 chars of e.g. "29,4"
        assert icer_str in formatted_two_strategy, (
            f"ICER substring '{icer_str}' not found in output"
        )

    def test_currency_symbol_in_costs(self, formatted_two_strategy):
        assert "$" in formatted_two_strategy

    def test_currency_name_in_header(self, formatted_two_strategy):
        assert "1995 Canadian dollars" in formatted_two_strategy

    def test_simulation_count_formatted_with_commas(self, formatted_two_strategy):
        assert "50,000" in formatted_two_strategy


# ---------------------------------------------------------------------------
# format_analysis — path distribution table
# ---------------------------------------------------------------------------


class TestFormatAnalysisPathTable:

    def test_path_table_present_by_default(self, formatted_two_strategy):
        assert "Response, no recurrence" in formatted_two_strategy

    def test_all_five_path_labels_present(self, formatted_two_strategy):
        """All five human-readable path labels must appear in the output."""
        for path in ALL_PATHS:
            label = format_path_label(path)
            # Check first word (enough to verify presence without exact match)
            assert label.split(",")[0] in formatted_two_strategy, (
                f"Path label starting with '{label.split(',')[0]}' not found"
            )

    def test_path_table_absent_when_disabled(self, sim_caffeine, sim_sumatriptan):
        sims = [sim_caffeine, sim_sumatriptan]
        incremental = compare_strategies(sims)
        output = format_analysis(sims, incremental, show_path_table=False)
        assert "Path Distribution" not in output
        assert "Terminal Path" not in output

    def test_path_percentages_shown(self, formatted_two_strategy):
        """Path distribution must show percentages (% symbol)."""
        assert "%" in formatted_two_strategy

    def test_no_snake_case_in_path_table(self, formatted_two_strategy):
        """Snake_case path constants must not appear in the formatted output."""
        for path in ALL_PATHS:
            assert path not in formatted_two_strategy, (
                f"Raw path constant '{path}' found in output — should be human-readable"
            )


# ---------------------------------------------------------------------------
# format_analysis — confidence intervals
# ---------------------------------------------------------------------------


class TestFormatAnalysisConfidenceIntervals:

    def test_ci_present_by_default(self, formatted_two_strategy):
        assert "95%" in formatted_two_strategy

    def test_ci_absent_when_disabled(self, sim_caffeine, sim_sumatriptan):
        sims = [sim_caffeine, sim_sumatriptan]
        incremental = compare_strategies(sims)
        output = format_analysis(sims, incremental, show_confidence_intervals=False)
        assert "95%" not in output

    def test_ci_columns_in_table_when_enabled(self, formatted_two_strategy):
        assert "95% CI" in formatted_two_strategy


# ---------------------------------------------------------------------------
# format_analysis — incremental section content
# ---------------------------------------------------------------------------


class TestFormatAnalysisIncrementalContent:

    def test_delta_cost_sign_prefix(self, formatted_two_strategy):
        """Incremental cost must include a sign prefix (+ or -)."""
        assert "+$" in formatted_two_strategy or "-$" in formatted_two_strategy

    def test_delta_utility_sign_prefix(self, formatted_two_strategy):
        assert "+0." in formatted_two_strategy or "-0." in formatted_two_strategy

    def test_no_incremental_section_when_no_comparison(self, sim_sumatriptan):
        """Single strategy with no comparison must not include incremental section."""
        output = format_analysis([sim_sumatriptan], [])
        assert "Incremental Cost-Effectiveness" not in output

    def test_dominant_strategy_interpretation(self):
        """When new strategy dominates (lower cost, higher utility) → dominant message."""
        ref = _make_minimal_result("Reference", expected_cost=20.0, expected_utility=0.3)
        new = _make_minimal_result("NewDrug",   expected_cost=10.0, expected_utility=0.5)
        incremental = [_make_minimal_incremental(
            "NewDrug", "Reference",
            incremental_cost=-10.0,
            incremental_utility=0.2,
            icer_annual=float("-inf"),
        )]
        output = format_analysis([ref, new], incremental)
        assert "dominant" in output.lower()

    def test_dominated_strategy_interpretation(self):
        """When new strategy is dominated (higher cost, lower utility) → dominated message."""
        ref = _make_minimal_result("Reference", expected_cost=10.0, expected_utility=0.5)
        new = _make_minimal_result("Worse",     expected_cost=20.0, expected_utility=0.3)
        incremental = [_make_minimal_incremental(
            "Worse", "Reference",
            incremental_cost=10.0,
            incremental_utility=-0.2,
            icer_annual=float("inf"),
        )]
        output = format_analysis([ref, new], incremental)
        assert "dominated" in output.lower()


# ---------------------------------------------------------------------------
# format_analysis — edge cases
# ---------------------------------------------------------------------------


class TestFormatAnalysisEdgeCases:

    def test_single_strategy_no_comparison(self, sim_sumatriptan):
        output = format_analysis([sim_sumatriptan], [])
        assert isinstance(output, str)
        assert "Sumatriptan" in output
        assert len(output) > 50

    def test_three_strategies_all_names_present(self, sumatriptan, caffeine):
        placebo = StrategyParams(
            name="Placebo",
            cost_drug=0.10, cost_ed=63.16, cost_hospital=1093.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.10, p_no_recurrence=0.60,
            p_endures=0.92, p_ed_relief=0.998,
        )
        sims = [
            simulate_strategy(placebo,      10_000, np.random.default_rng(3001)),
            simulate_strategy(caffeine,     10_000, np.random.default_rng(3002)),
            simulate_strategy(sumatriptan,  10_000, np.random.default_rng(3003)),
        ]
        incremental = compare_strategies(sims, reference_index=0)
        output = format_analysis(sims, incremental)
        assert "Placebo"             in output
        assert "Caffeine/Ergotamine" in output
        assert "Sumatriptan"         in output

    def test_custom_title_appears(self, sim_sumatriptan):
        output = format_analysis(
            [sim_sumatriptan], [],
            title="My Custom Analysis Title"
        )
        assert "My Custom Analysis Title" in output

    def test_custom_model_citation_appears(self, sim_sumatriptan):
        output = format_analysis(
            [sim_sumatriptan], [],
            model_citation="Smith et al. (2024). NEJM."
        )
        assert "Smith et al. (2024)" in output

    def test_very_long_strategy_name_does_not_raise(self):
        params = StrategyParams(
            name="A" * 80,
            cost_drug=10.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.5, p_no_recurrence=0.6,
            p_endures=0.9, p_ed_relief=0.99,
        )
        result = simulate_strategy(params, 1_000, np.random.default_rng(0))
        output = format_analysis([result], [])
        assert "A" * 10 in output

    def test_pound_currency_symbol(self, sim_sumatriptan):
        output = format_analysis([sim_sumatriptan], [], currency_symbol="£")
        assert "£" in output
        assert "$" not in output

    def test_no_currency_name_omits_it(self, sim_sumatriptan):
        output = format_analysis([sim_sumatriptan], [], currency_name="")
        # Without a currency name, the header should not contain "dollars"
        assert "dollars" not in output

    def test_methodological_notes_contain_citation(self, formatted_two_strategy):
        assert "Evans" in formatted_two_strategy

    def test_methodological_notes_mention_annualisation(self, formatted_two_strategy):
        assert "365" in formatted_two_strategy or "annuali" in formatted_two_strategy.lower()
