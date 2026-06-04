"""
Tests for pubhealth_llm.decision_tree.schema
============================================

Covers:
* StrategySchema — field validation (probabilities, costs, utilities, name)
* StrategySchema — to_strategy_params() round-trip
* StrategySchema — frozen (immutable)
* StrategySchema — field descriptions exist and are informative
* AnalysisConfig — basic construction
* AnalysisConfig — reference_index cross-field validation
* AnalysisConfig — defaults
* AnalysisConfig — to_strategy_params_list()
* AnalysisConfig — to_script() integration with generator
* AnalysisConfig — run() end-to-end pipeline
* AnalysisConfig — field metadata (descriptions present)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pubhealth_llm.decision_tree import AnalysisConfig, StrategySchema
from pubhealth_llm.decision_tree.simulation import StrategyParams


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

CAFFEINE_DATA = dict(
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
    p_no_recurrence=0.558,
    p_endures=0.917,
    p_ed_relief=0.994,
)

SUMATRIPTAN_DATA = dict(
    name="Sumatriptan",
    cost_drug=16.1,
    cost_ed=63.16,
    cost_hospital=1093.0,
    u_response_no_recurrence=1.0,
    u_response_recurrence=0.9,
    u_no_response_endures=-0.3,
    u_no_response_ed=0.1,
    u_no_response_hospital=-0.3,
    p_response=0.558,
    p_no_recurrence=0.558,
    p_endures=0.917,
    p_ed_relief=0.994,
)


def make_caffeine() -> StrategySchema:
    return StrategySchema(**CAFFEINE_DATA)


def make_sumatriptan() -> StrategySchema:
    return StrategySchema(**SUMATRIPTAN_DATA)


def make_config(**overrides) -> AnalysisConfig:
    defaults = dict(
        strategies=[make_caffeine(), make_sumatriptan()],
        n_patients=2_000,
        seed=42,
    )
    defaults.update(overrides)
    return AnalysisConfig(**defaults)


# ---------------------------------------------------------------------------
# TestStrategySchemaConstruction
# ---------------------------------------------------------------------------


class TestStrategySchemaConstruction:
    def test_valid_construction(self):
        s = make_caffeine()
        assert s.name == "Caffeine/Ergotamine"

    def test_all_fields_accessible(self):
        s = make_caffeine()
        assert s.cost_drug == 1.32
        assert s.cost_ed == 63.16
        assert s.cost_hospital == 1093.0
        assert s.u_response_no_recurrence == 1.0
        assert s.u_response_recurrence == 0.9
        assert s.u_no_response_endures == -0.3
        assert s.u_no_response_ed == 0.1
        assert s.u_no_response_hospital == -0.3
        assert s.p_response == 0.379
        assert s.p_no_recurrence == 0.558
        assert s.p_endures == 0.917
        assert s.p_ed_relief == 0.994

    def test_frozen_cannot_mutate(self):
        s = make_caffeine()
        with pytest.raises(ValidationError):
            s.name = "Changed"  # type: ignore[misc]

    def test_boundary_probability_zero(self):
        data = {**CAFFEINE_DATA, "p_response": 0.0}
        s = StrategySchema(**data)
        assert s.p_response == 0.0

    def test_boundary_probability_one(self):
        data = {**CAFFEINE_DATA, "p_response": 1.0}
        s = StrategySchema(**data)
        assert s.p_response == 1.0

    def test_boundary_utility_minus_one(self):
        data = {**CAFFEINE_DATA, "u_no_response_endures": -1.0}
        s = StrategySchema(**data)
        assert s.u_no_response_endures == -1.0

    def test_boundary_utility_plus_one(self):
        data = {**CAFFEINE_DATA, "u_response_no_recurrence": 1.0}
        s = StrategySchema(**data)
        assert s.u_response_no_recurrence == 1.0

    def test_zero_cost_allowed(self):
        data = {**CAFFEINE_DATA, "cost_drug": 0.0}
        s = StrategySchema(**data)
        assert s.cost_drug == 0.0


# ---------------------------------------------------------------------------
# TestStrategySchemaValidation
# ---------------------------------------------------------------------------


class TestStrategySchemaValidation:
    def test_empty_name_raises(self):
        data = {**CAFFEINE_DATA, "name": ""}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_negative_cost_drug_raises(self):
        data = {**CAFFEINE_DATA, "cost_drug": -0.01}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_negative_cost_ed_raises(self):
        data = {**CAFFEINE_DATA, "cost_ed": -1.0}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_negative_cost_hospital_raises(self):
        data = {**CAFFEINE_DATA, "cost_hospital": -100.0}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_probability_above_one_raises(self):
        data = {**CAFFEINE_DATA, "p_response": 1.001}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_probability_below_zero_raises(self):
        data = {**CAFFEINE_DATA, "p_no_recurrence": -0.001}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_p_endures_above_one_raises(self):
        data = {**CAFFEINE_DATA, "p_endures": 1.1}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_p_ed_relief_below_zero_raises(self):
        data = {**CAFFEINE_DATA, "p_ed_relief": -0.5}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_utility_above_one_raises(self):
        data = {**CAFFEINE_DATA, "u_response_no_recurrence": 1.01}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_utility_below_minus_one_raises(self):
        data = {**CAFFEINE_DATA, "u_no_response_endures": -1.01}
        with pytest.raises(ValidationError):
            StrategySchema(**data)

    def test_missing_required_field_raises(self):
        data = {k: v for k, v in CAFFEINE_DATA.items() if k != "p_response"}
        with pytest.raises(ValidationError):
            StrategySchema(**data)


# ---------------------------------------------------------------------------
# TestStrategySchemaToStrategyParams
# ---------------------------------------------------------------------------


class TestStrategySchemaToStrategyParams:
    def test_returns_strategy_params_instance(self):
        result = make_caffeine().to_strategy_params()
        assert isinstance(result, StrategyParams)

    def test_name_preserved(self):
        result = make_caffeine().to_strategy_params()
        assert result.name == "Caffeine/Ergotamine"

    def test_cost_drug_preserved(self):
        result = make_caffeine().to_strategy_params()
        assert result.cost_drug == pytest.approx(1.32)

    def test_p_response_preserved(self):
        result = make_caffeine().to_strategy_params()
        assert result.p_response == pytest.approx(0.379)

    def test_negative_utility_preserved(self):
        result = make_caffeine().to_strategy_params()
        assert result.u_no_response_endures == pytest.approx(-0.3)

    def test_all_14_fields_match(self):
        schema = make_caffeine()
        params = schema.to_strategy_params()
        for field_name in CAFFEINE_DATA:
            assert getattr(params, field_name) == pytest.approx(
                getattr(schema, field_name), rel=1e-9
            )


# ---------------------------------------------------------------------------
# TestStrategySchemaFieldDescriptions
# ---------------------------------------------------------------------------


class TestStrategySchemaFieldDescriptions:
    """Every field must have a non-empty description for the LLM agent."""

    def _field_description(self, field_name: str) -> str:
        info = StrategySchema.model_fields[field_name]
        return info.description or ""

    def test_name_has_description(self):
        assert len(self._field_description("name")) > 10

    def test_cost_drug_has_description(self):
        assert len(self._field_description("cost_drug")) > 10

    def test_cost_ed_has_description(self):
        assert len(self._field_description("cost_ed")) > 10

    def test_cost_hospital_has_description(self):
        assert len(self._field_description("cost_hospital")) > 10

    def test_u_response_no_recurrence_has_description(self):
        assert len(self._field_description("u_response_no_recurrence")) > 10

    def test_u_response_recurrence_has_description(self):
        assert len(self._field_description("u_response_recurrence")) > 10

    def test_u_no_response_endures_has_description(self):
        assert len(self._field_description("u_no_response_endures")) > 10

    def test_u_no_response_ed_has_description(self):
        assert len(self._field_description("u_no_response_ed")) > 10

    def test_u_no_response_hospital_has_description(self):
        assert len(self._field_description("u_no_response_hospital")) > 10

    def test_p_response_has_description(self):
        assert len(self._field_description("p_response")) > 10

    def test_p_no_recurrence_has_description(self):
        assert len(self._field_description("p_no_recurrence")) > 10

    def test_p_endures_has_description(self):
        assert len(self._field_description("p_endures")) > 10

    def test_p_ed_relief_has_description(self):
        assert len(self._field_description("p_ed_relief")) > 10


# ---------------------------------------------------------------------------
# TestAnalysisConfigConstruction
# ---------------------------------------------------------------------------


class TestAnalysisConfigConstruction:
    def test_single_strategy_valid(self):
        config = AnalysisConfig(
            strategies=[make_caffeine()],
            n_patients=1_000,
            seed=1,
        )
        assert len(config.strategies) == 1

    def test_two_strategies_valid(self):
        config = make_config()
        assert len(config.strategies) == 2

    def test_default_reference_index(self):
        config = make_config()
        assert config.reference_index == 0

    def test_default_title(self):
        config = AnalysisConfig(strategies=[make_caffeine()])
        assert "Decision Tree" in config.title

    def test_default_n_patients(self):
        config = AnalysisConfig(strategies=[make_caffeine()])
        assert config.n_patients == 1_000_000

    def test_default_seed(self):
        config = AnalysisConfig(strategies=[make_caffeine()])
        assert config.seed == 2026

    def test_default_currency_symbol(self):
        config = AnalysisConfig(strategies=[make_caffeine()])
        assert config.currency_symbol == "$"

    def test_default_currency_name_empty(self):
        config = AnalysisConfig(strategies=[make_caffeine()])
        assert config.currency_name == ""

    def test_default_show_path_table_true(self):
        config = AnalysisConfig(strategies=[make_caffeine()])
        assert config.show_path_table is True

    def test_default_show_confidence_intervals_true(self):
        config = AnalysisConfig(strategies=[make_caffeine()])
        assert config.show_confidence_intervals is True

    def test_custom_values_accepted(self):
        config = AnalysisConfig(
            strategies=[make_caffeine(), make_sumatriptan()],
            reference_index=1,
            title="My Analysis",
            n_patients=5_000,
            seed=99,
            currency_symbol="£",
            currency_name="2024 GBP",
            show_path_table=False,
            show_confidence_intervals=False,
        )
        assert config.reference_index == 1
        assert config.title == "My Analysis"
        assert config.n_patients == 5_000
        assert config.currency_symbol == "£"
        assert config.show_path_table is False


# ---------------------------------------------------------------------------
# TestAnalysisConfigValidation
# ---------------------------------------------------------------------------


class TestAnalysisConfigValidation:
    def test_empty_strategies_raises(self):
        with pytest.raises(ValidationError):
            AnalysisConfig(strategies=[])

    def test_reference_index_out_of_range_raises(self):
        with pytest.raises(ValidationError, match="out of range"):
            AnalysisConfig(
                strategies=[make_caffeine()],
                reference_index=1,
            )

    def test_reference_index_equal_to_length_raises(self):
        with pytest.raises(ValidationError, match="out of range"):
            AnalysisConfig(
                strategies=[make_caffeine(), make_sumatriptan()],
                reference_index=2,
            )

    def test_reference_index_negative_raises(self):
        with pytest.raises(ValidationError):
            AnalysisConfig(
                strategies=[make_caffeine()],
                reference_index=-1,
            )

    def test_n_patients_zero_raises(self):
        with pytest.raises(ValidationError):
            AnalysisConfig(strategies=[make_caffeine()], n_patients=0)

    def test_n_patients_negative_raises(self):
        with pytest.raises(ValidationError):
            AnalysisConfig(strategies=[make_caffeine()], n_patients=-1)

    def test_seed_negative_raises(self):
        with pytest.raises(ValidationError):
            AnalysisConfig(strategies=[make_caffeine()], seed=-1)

    def test_empty_title_raises(self):
        with pytest.raises(ValidationError):
            AnalysisConfig(strategies=[make_caffeine()], title="")

    def test_empty_currency_symbol_raises(self):
        with pytest.raises(ValidationError):
            AnalysisConfig(strategies=[make_caffeine()], currency_symbol="")

    def test_reference_index_zero_is_valid_for_single_strategy(self):
        config = AnalysisConfig(strategies=[make_caffeine()], reference_index=0)
        assert config.reference_index == 0

    def test_reference_index_one_is_valid_for_two_strategies(self):
        config = make_config(reference_index=1)
        assert config.reference_index == 1


# ---------------------------------------------------------------------------
# TestAnalysisConfigToStrategyParamsList
# ---------------------------------------------------------------------------


class TestAnalysisConfigToStrategyParamsList:
    def test_returns_list(self):
        result = make_config().to_strategy_params_list()
        assert isinstance(result, list)

    def test_length_matches_strategies(self):
        result = make_config().to_strategy_params_list()
        assert len(result) == 2

    def test_all_items_are_strategy_params(self):
        result = make_config().to_strategy_params_list()
        for item in result:
            assert isinstance(item, StrategyParams)

    def test_names_preserved_in_order(self):
        result = make_config().to_strategy_params_list()
        assert result[0].name == "Caffeine/Ergotamine"
        assert result[1].name == "Sumatriptan"


# ---------------------------------------------------------------------------
# TestAnalysisConfigToScript
# ---------------------------------------------------------------------------


class TestAnalysisConfigToScript:
    def test_returns_string(self):
        script = make_config().to_script()
        assert isinstance(script, str)

    def test_non_empty(self):
        script = make_config().to_script()
        assert len(script.strip()) > 0

    def test_strategy_names_in_script(self):
        script = make_config().to_script()
        assert "Caffeine/Ergotamine" in script
        assert "Sumatriptan" in script

    def test_n_patients_in_script(self):
        config = make_config(n_patients=5_000)
        script = config.to_script()
        # Generator pads with spaces: "N_PATIENTS      = 5000"
        assert "N_PATIENTS" in script and "5000" in script

    def test_title_in_script(self):
        config = make_config(title="My Custom Analysis")
        script = config.to_script()
        assert "My Custom Analysis" in script

    def test_currency_symbol_in_script(self):
        config = make_config(currency_symbol="£")
        script = config.to_script()
        assert "£" in script

    def test_compiles_without_error(self):
        script = make_config().to_script()
        compile(script, "<generated>", "exec")  # raises SyntaxError on failure


# ---------------------------------------------------------------------------
# TestAnalysisConfigRun
# ---------------------------------------------------------------------------


class TestAnalysisConfigRun:
    """End-to-end pipeline: schema → generate → subprocess → markdown."""

    def test_run_returns_string(self):
        output = make_config().run()
        assert isinstance(output, str)

    def test_run_contains_both_strategy_names(self):
        output = make_config().run()
        assert "Caffeine/Ergotamine" in output
        assert "Sumatriptan" in output

    def test_run_contains_markdown_headers(self):
        output = make_config().run()
        assert "## Strategy Results" in output
        assert "## Incremental Cost-Effectiveness" in output

    def test_run_contains_icer(self):
        output = make_config().run()
        assert "QALY" in output

    def test_run_single_strategy_no_icer(self):
        config = AnalysisConfig(
            strategies=[make_caffeine()],
            n_patients=2_000,
            seed=1,
        )
        output = config.run()
        assert "Caffeine/Ergotamine" in output
        assert "## Incremental" not in output

    def test_run_custom_title_in_output(self):
        config = make_config(title="Evans 1997 Replication")
        output = config.run()
        assert "Evans 1997 Replication" in output

    def test_run_custom_currency_in_output(self):
        config = make_config(currency_symbol="Can$")
        output = config.run()
        assert "Can$" in output

    def test_run_evans_icer_within_10_percent(self):
        """Full pipeline should reproduce Evans (1997) within 10%."""
        import re
        config = AnalysisConfig(
            strategies=[make_caffeine(), make_sumatriptan()],
            n_patients=500_000,
            seed=2026,
        )
        output = config.run()
        matches = re.findall(r"[\+\-]?\$([0-9,]+)/QALY", output)
        assert matches, f"No ICER found in output:\n{output}"
        icer_value = float(matches[0].replace(",", ""))
        assert abs(icer_value - 29_366) / 29_366 < 0.10
