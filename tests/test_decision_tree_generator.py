"""
Tests for pubhealth_llm.decision_tree.generator.

Coverage
--------
_slugify (internal helper)
    - Converts strategy names to valid Python identifier fragments
    - Handles spaces, slashes, parentheses, numbers, mixed case
    - Empty result falls back to "strategy"

generate_script — return type and structure
    - Returns a non-empty string
    - Generated code compiles without SyntaxError
    - Contains required imports
    - Contains StrategyParams constructor call(s)
    - Contains N_PATIENTS assignment with correct value
    - Contains RANDOM_SEED assignment with correct value
    - Contains REFERENCE_INDEX assignment with correct value
    - Contains the analysis title
    - Contains the currency symbol
    - Contains each strategy name

generate_script — parameter values in generated code
    - cost_drug value appears for each strategy
    - p_response value appears for each strategy
    - u_response_no_recurrence value appears for each strategy
    - cost_ed value appears for each strategy
    - Negative utility values formatted correctly (minus sign preserved)

generate_script — multi-strategy handling
    - Single strategy: comparison section uses empty list
    - Two strategies: compare_strategies call present
    - Three strategies: compare_strategies call present
    - reference_index value in compare_strategies call

generate_script — configuration options
    - Custom title propagated into format_analysis call
    - Custom currency_symbol propagated into format_analysis call
    - Custom currency_name propagated
    - show_path_table=False propagated
    - show_confidence_intervals=False propagated
    - Custom model_citation propagated
    - n_patients value in N_PATIENTS assignment
    - seed value in RANDOM_SEED assignment

generate_script — execution correctness
    - Single strategy: exec produces non-empty stdout
    - Two strategies: exec produces stdout containing both strategy names
    - Two strategies: exec produces stdout containing "ICER"
    - Two strategies: exec output is valid markdown (contains ## headers)
    - Exec with Evans parameters produces ICER close to $29,366/QALY

generate_script — error handling
    - Empty strategies list raises ValueError
    - reference_index out of range raises ValueError
    - n_patients < 1 raises ValueError
    - Negative seed raises ValueError

generate_script — code quality
    - No snake_case path constants appear in generated code (uses imports)
    - Each parameter has its own line (one param per line style)
    - Generated code contains docstring
"""

import io
import sys
from contextlib import redirect_stdout
from typing import Generator

import pytest

from pubhealth_llm.decision_tree.generator import _slugify, generate_script
from pubhealth_llm.decision_tree.simulation import StrategyParams

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def single_script(sumatriptan) -> str:
    """Pre-generated script for single-strategy tests (small N for speed)."""
    return generate_script([sumatriptan], n_patients=10_000, seed=42)


@pytest.fixture(scope="module")
def two_strategy_script(caffeine, sumatriptan) -> str:
    """Pre-generated script for two-strategy tests (small N for speed)."""
    return generate_script(
        [caffeine, sumatriptan],
        reference_index=0,
        n_patients=10_000,
        seed=99,
        title="Evans Migraine Analysis",
        currency_symbol="$",
        currency_name="1995 Canadian dollars",
    )


def _exec_script(script: str) -> str:
    """
    Execute a generated script and return its stdout as a string.

    Uses redirect_stdout so the print() call in the generated script is
    captured rather than written to the test runner's stdout.
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        exec(compile(script, "<generated>", "exec"), {})  # noqa: S102
    return buf.getvalue()


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:

    def test_lowercase(self):
        assert _slugify("Sumatriptan") == "sumatriptan"

    def test_slash_becomes_underscore(self):
        assert _slugify("Caffeine/Ergotamine") == "caffeine_ergotamine"

    def test_space_becomes_underscore(self):
        assert _slugify("Drug A") == "drug_a"

    def test_parens_stripped(self):
        result = _slugify("Drug A (new)")
        assert "(" not in result
        assert ")" not in result

    def test_multiple_separators_collapse(self):
        result = _slugify("Drug  A  --  New")
        assert "__" not in result

    def test_numbers_preserved(self):
        assert "4o" in _slugify("GPT-4o mini")

    def test_all_invalid_chars_fallback(self):
        result = _slugify("---")
        assert result == "strategy"

    def test_empty_string_fallback(self):
        result = _slugify("")
        assert result == "strategy"

    def test_no_leading_trailing_underscores(self):
        result = _slugify("/Ergotamine/")
        assert not result.startswith("_")
        assert not result.endswith("_")


# ---------------------------------------------------------------------------
# generate_script — return type and structure
# ---------------------------------------------------------------------------


class TestGenerateScriptStructure:

    def test_returns_string(self, single_script):
        assert isinstance(single_script, str)

    def test_non_empty(self, single_script):
        assert len(single_script) > 200

    def test_compiles_without_syntax_error_single(self, single_script):
        try:
            compile(single_script, "<generated>", "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated script has syntax error: {e}")

    def test_compiles_without_syntax_error_two_strategies(self, two_strategy_script):
        try:
            compile(two_strategy_script, "<generated>", "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated two-strategy script has syntax error: {e}")

    def test_imports_numpy(self, single_script):
        assert "import numpy as np" in single_script

    def test_imports_strategy_params(self, single_script):
        assert "StrategyParams" in single_script

    def test_imports_simulate_strategy(self, single_script):
        assert "simulate_strategy" in single_script

    def test_imports_compare_strategies(self, single_script):
        assert "compare_strategies" in single_script

    def test_imports_format_analysis(self, single_script):
        assert "format_analysis" in single_script

    def test_contains_docstring(self, single_script):
        assert '"""' in single_script

    def test_contains_strategy_name(self, single_script, sumatriptan):
        assert sumatriptan.name in single_script

    def test_contains_both_strategy_names(self, two_strategy_script, caffeine, sumatriptan):
        assert caffeine.name in two_strategy_script
        assert sumatriptan.name in two_strategy_script

    def test_n_patients_assignment_present(self, two_strategy_script):
        assert "N_PATIENTS" in two_strategy_script

    def test_n_patients_value_correct(self):
        params = StrategyParams(
            name="Test", cost_drug=1.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.5, p_no_recurrence=0.6,
            p_endures=0.9, p_ed_relief=0.99,
        )
        script = generate_script([params], n_patients=12_345, seed=0)
        assert "N_PATIENTS      = 12345" in script

    def test_seed_value_correct(self):
        params = StrategyParams(
            name="Test", cost_drug=1.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.5, p_no_recurrence=0.6,
            p_endures=0.9, p_ed_relief=0.99,
        )
        script = generate_script([params], n_patients=1000, seed=7777)
        assert "RANDOM_SEED     = 7777" in script

    def test_reference_index_assignment_present(self, two_strategy_script):
        assert "REFERENCE_INDEX" in two_strategy_script

    def test_reference_index_value_correct(self, two_strategy_script):
        assert "REFERENCE_INDEX = 0" in two_strategy_script


# ---------------------------------------------------------------------------
# generate_script — parameter values
# ---------------------------------------------------------------------------


class TestGenerateScriptParameterValues:

    def test_cost_drug_sumatriptan_present(self, two_strategy_script):
        # repr(16.10) == '16.1'
        assert "16.1" in two_strategy_script

    def test_cost_drug_caffeine_present(self, two_strategy_script):
        # repr(1.32) == '1.32'
        assert "1.32" in two_strategy_script

    def test_p_response_sumatriptan_present(self, two_strategy_script):
        assert "0.558" in two_strategy_script

    def test_p_response_caffeine_present(self, two_strategy_script):
        assert "0.379" in two_strategy_script

    def test_negative_utility_formatted_correctly(self, single_script):
        """Negative utility values must appear with minus sign."""
        assert "-0.3" in single_script

    def test_cost_ed_present(self, single_script, sumatriptan):
        assert repr(sumatriptan.cost_ed) in single_script

    def test_cost_hospital_present(self, single_script, sumatriptan):
        assert repr(sumatriptan.cost_hospital) in single_script

    def test_p_no_recurrence_present(self, single_script, sumatriptan):
        assert repr(sumatriptan.p_no_recurrence) in single_script

    def test_p_endures_present(self, single_script, sumatriptan):
        assert repr(sumatriptan.p_endures) in single_script

    def test_p_ed_relief_present(self, single_script, sumatriptan):
        assert repr(sumatriptan.p_ed_relief) in single_script

    def test_each_param_on_its_own_line(self, single_script):
        """
        Each parameter must appear on its own line with its name= prefix.
        This verifies the teaching-friendly one-param-per-line style.
        """
        required_params = [
            "cost_drug=",
            "cost_ed=",
            "cost_hospital=",
            "u_response_no_recurrence=",
            "u_response_recurrence=",
            "u_no_response_endures=",
            "u_no_response_ed=",
            "u_no_response_hospital=",
            "p_response=",
            "p_no_recurrence=",
            "p_endures=",
            "p_ed_relief=",
        ]
        for param in required_params:
            assert param in single_script, (
                f"Parameter '{param}' not found in generated script"
            )


# ---------------------------------------------------------------------------
# generate_script — multi-strategy handling
# ---------------------------------------------------------------------------


class TestGenerateScriptMultiStrategy:

    def test_single_strategy_no_compare_call(self, single_script):
        """Single strategy: _incremental must be set to empty list, not a compare call."""
        assert "_incremental = []" in single_script

    def test_two_strategies_compare_call_present(self, two_strategy_script):
        assert "compare_strategies(" in two_strategy_script

    def test_three_strategies_compare_call_present(self, sumatriptan, caffeine):
        placebo = StrategyParams(
            name="Placebo",
            cost_drug=0.10, cost_ed=63.16, cost_hospital=1093.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.10, p_no_recurrence=0.60,
            p_endures=0.92, p_ed_relief=0.998,
        )
        script = generate_script(
            [placebo, caffeine, sumatriptan], n_patients=1000, seed=0
        )
        assert "compare_strategies(" in script
        assert "Placebo" in script
        assert "Caffeine/Ergotamine" in script
        assert "Sumatriptan" in script

    def test_reference_index_in_compare_call(self, caffeine, sumatriptan):
        script = generate_script(
            [caffeine, sumatriptan], reference_index=1, n_patients=1000, seed=0
        )
        assert "reference_index=1" in script

    def test_non_zero_reference_index_propagated(self, caffeine, sumatriptan):
        script = generate_script(
            [caffeine, sumatriptan], reference_index=1, n_patients=1000, seed=0
        )
        assert "REFERENCE_INDEX = 1" in script


# ---------------------------------------------------------------------------
# generate_script — configuration options
# ---------------------------------------------------------------------------


class TestGenerateScriptConfiguration:

    def _minimal_params(self, name: str = "Test") -> StrategyParams:
        return StrategyParams(
            name=name, cost_drug=5.0, cost_ed=50.0, cost_hospital=500.0,
            u_response_no_recurrence=1.0, u_response_recurrence=0.9,
            u_no_response_endures=-0.3, u_no_response_ed=0.1,
            u_no_response_hospital=-0.3,
            p_response=0.5, p_no_recurrence=0.6,
            p_endures=0.9, p_ed_relief=0.99,
        )

    def test_custom_title_in_script(self):
        script = generate_script(
            [self._minimal_params()], n_patients=100, seed=0,
            title="My Custom Analysis"
        )
        assert "My Custom Analysis" in script

    def test_custom_currency_symbol_in_script(self):
        script = generate_script(
            [self._minimal_params()], n_patients=100, seed=0,
            currency_symbol="£"
        )
        assert "£" in script

    def test_custom_currency_name_in_script(self):
        script = generate_script(
            [self._minimal_params()], n_patients=100, seed=0,
            currency_name="British pounds"
        )
        assert "British pounds" in script

    def test_show_path_table_false_in_script(self):
        script = generate_script(
            [self._minimal_params()], n_patients=100, seed=0,
            show_path_table=False
        )
        assert "show_path_table=False" in script

    def test_show_confidence_intervals_false_in_script(self):
        script = generate_script(
            [self._minimal_params()], n_patients=100, seed=0,
            show_confidence_intervals=False
        )
        assert "show_confidence_intervals=False" in script

    def test_custom_model_citation_in_script(self):
        script = generate_script(
            [self._minimal_params()], n_patients=100, seed=0,
            model_citation="Smith et al. (2024). NEJM."
        )
        assert "Smith et al. (2024). NEJM." in script

    def test_default_show_values_in_script(self):
        script = generate_script([self._minimal_params()], n_patients=100, seed=0)
        assert "show_path_table=True" in script
        assert "show_confidence_intervals=True" in script


# ---------------------------------------------------------------------------
# generate_script — execution correctness
# ---------------------------------------------------------------------------


class TestGenerateScriptExecution:
    """
    Execute the generated script in-process (via exec) to verify it produces
    correct output.  Uses small N for speed; numerical precision is not the
    focus here — that is covered by the simulation tests.
    """

    def test_single_strategy_exec_produces_output(self, sumatriptan):
        script = generate_script([sumatriptan], n_patients=5_000, seed=42)
        output = _exec_script(script)
        assert len(output) > 100

    def test_two_strategy_exec_produces_both_names(self, caffeine, sumatriptan):
        script = generate_script(
            [caffeine, sumatriptan], n_patients=5_000, seed=42
        )
        output = _exec_script(script)
        assert "Caffeine/Ergotamine" in output
        assert "Sumatriptan" in output

    def test_two_strategy_exec_contains_icer(self, caffeine, sumatriptan):
        script = generate_script(
            [caffeine, sumatriptan], n_patients=5_000, seed=42
        )
        output = _exec_script(script)
        assert "ICER" in output or "QALY" in output

    def test_two_strategy_exec_contains_markdown_headers(self, caffeine, sumatriptan):
        script = generate_script(
            [caffeine, sumatriptan], n_patients=5_000, seed=42
        )
        output = _exec_script(script)
        assert "##" in output

    def test_two_strategy_exec_contains_path_table(self, caffeine, sumatriptan):
        script = generate_script(
            [caffeine, sumatriptan], n_patients=5_000, seed=42,
            show_path_table=True
        )
        output = _exec_script(script)
        assert "Response, no recurrence" in output

    def test_two_strategy_exec_icer_close_to_evans(self, caffeine, sumatriptan):
        """
        With N=100,000 the ICER should be within 5% of Evans $29,366/QALY.
        Tolerance is wider than the simulation tests because the focus here
        is on correct script generation, not simulation precision.
        """
        script = generate_script(
            [caffeine, sumatriptan], n_patients=100_000, seed=42
        )
        output = _exec_script(script)
        # Extract the ICER from output — look for pattern like "$29,xxx/QALY"
        import re
        icer_match = re.search(r"\+\$([0-9,]+)/QALY", output)
        assert icer_match is not None, (
            f"Could not find ICER pattern in output:\n{output[:500]}"
        )
        icer_value = float(icer_match.group(1).replace(",", ""))
        evans_icer = 29_366.0
        assert abs(icer_value - evans_icer) / evans_icer < 0.05, (
            f"ICER {icer_value:.0f} deviates more than 5% from Evans {evans_icer:.0f}"
        )

    def test_exec_title_appears_in_output(self, sumatriptan):
        script = generate_script(
            [sumatriptan], n_patients=1_000, seed=0,
            title="My Special Analysis"
        )
        output = _exec_script(script)
        assert "My Special Analysis" in output

    def test_exec_currency_symbol_appears_in_output(self, sumatriptan):
        script = generate_script(
            [sumatriptan], n_patients=1_000, seed=0,
            currency_symbol="£"
        )
        output = _exec_script(script)
        assert "£" in output


# ---------------------------------------------------------------------------
# generate_script — error handling
# ---------------------------------------------------------------------------


class TestGenerateScriptErrorHandling:

    def test_empty_strategies_raises(self):
        with pytest.raises(ValueError, match="strategies"):
            generate_script([])

    def test_reference_index_out_of_range_raises(self, sumatriptan):
        with pytest.raises(ValueError, match="reference_index"):
            generate_script([sumatriptan], reference_index=1)

    def test_reference_index_negative_raises(self, sumatriptan):
        with pytest.raises(ValueError, match="reference_index"):
            generate_script([sumatriptan], reference_index=-1)

    def test_n_patients_zero_raises(self, sumatriptan):
        with pytest.raises(ValueError, match="n_patients"):
            generate_script([sumatriptan], n_patients=0)

    def test_n_patients_negative_raises(self, sumatriptan):
        with pytest.raises(ValueError, match="n_patients"):
            generate_script([sumatriptan], n_patients=-100)

    def test_negative_seed_raises(self, sumatriptan):
        with pytest.raises(ValueError, match="seed"):
            generate_script([sumatriptan], seed=-1)


# ---------------------------------------------------------------------------
# generate_script — code quality
# ---------------------------------------------------------------------------


class TestGenerateScriptCodeQuality:

    def test_no_raw_path_constants_in_generated_code(self, single_script):
        """
        Raw path constants (response_no_recurrence, etc.) should not appear
        as string literals in the generated code — they are internal to the
        simulation engine and should not leak into generated scripts.
        """
        from pubhealth_llm.decision_tree.simulation import ALL_PATHS
        for path in ALL_PATHS:
            # They may appear inside quoted strings — check for bare usage
            # by looking for them as Python identifiers, not inside quotes.
            # A simple heuristic: they should not appear without quotes
            # or as dict keys in the generated script.
            assert f'"{path}"' not in single_script, (
                f"Raw path constant '{path}' appears as string literal"
            )

    def test_generated_code_uses_pubhealth_llm_imports(self, single_script):
        assert "from pubhealth_llm" in single_script

    def test_strategies_list_built_from_variables(self, two_strategy_script):
        """The _STRATEGIES list must reference the named strategy variables."""
        assert "_STRATEGIES" in two_strategy_script
        assert "_strategy_" in two_strategy_script

    def test_sim_results_uses_enumerate(self, single_script):
        """The simulation loop must use enumerate for independent seeds."""
        assert "enumerate(_STRATEGIES)" in single_script
