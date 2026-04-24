"""
Pydantic v2 schemas for the Evans health economic decision tree.

These models serve as the validated data layer between the agent elicitation
conversation (Step 6) and the simulation pipeline (Steps 1–4).  They mirror
the dataclasses in ``simulation.py`` but add:

* Field-level descriptions that explain each parameter in clinical language —
  used by the LLM agent to know what to ask the student
* Pydantic validation (ge/le constraints, cross-field checks) that catches
  errors at the boundary before they propagate into numpy
* Convenience methods (``to_strategy_params``, ``to_script``, ``run``) that
  tie the validated data directly into the pipeline without boilerplate in
  the agent layer

Design decisions
----------------
* Utilities are bounded to ``[-1, 1]`` — the standard QALY convention.
  Values below −1 or above 1 are clinically implausible and almost certainly
  represent unit errors (e.g. entering a percentage as a decimal twice).
* ``AnalysisConfig.reference_index`` is validated against the length of
  ``strategies`` by a model-level validator so the error message is clear.
* ``n_patients`` defaults to 1,000,000 and ``seed`` to 2026 — matching the
  generator defaults — so the agent only needs to ask about clinically
  meaningful parameters, not simulation mechanics.
* Both schemas are exported through ``pubhealth_llm.decision_tree.__init__``
  so callers use a single import path.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from pubhealth_llm.decision_tree.generator import generate_script
from pubhealth_llm.decision_tree.runner import run_script
from pubhealth_llm.decision_tree.simulation import StrategyParams


# ---------------------------------------------------------------------------
# StrategySchema
# ---------------------------------------------------------------------------


class StrategySchema(BaseModel):
    """
    Validated parameter set for one treatment strategy in the Evans tree.

    Every field maps 1-to-1 onto a :class:`~pubhealth_llm.decision_tree.simulation.StrategyParams`
    attribute.  Descriptions are written in plain clinical language so that
    the LLM agent can use them verbatim when asking a student for values.

    Probabilities must lie in ``[0, 1]``.  Costs must be non-negative.
    Utilities must lie in ``[-1, 1]`` (standard QALY convention).
    """

    model_config = {"frozen": True}

    # ── Identity ──────────────────────────────────────────────────────────

    name: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "Name of the treatment strategy, e.g. 'Sumatriptan 100 mg' "
                "or 'Standard care'. Used as a label in tables and reports."
            ),
        ),
    ]

    # ── Costs ─────────────────────────────────────────────────────────────

    cost_drug: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "Acquisition cost of one dose of the treatment (in the chosen "
                "currency, e.g. 1995 Canadian dollars). Non-negative."
            ),
        ),
    ]

    cost_ed: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "Cost of one emergency department visit (excluding any "
                "subsequent hospitalisation). Non-negative. "
                "This cost is shared across strategies if the ED infrastructure "
                "is the same regardless of which drug was taken."
            ),
        ),
    ]

    cost_hospital: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "Additional cost of in-patient hospitalisation, incurred on top "
                "of the ED visit cost. Non-negative."
            ),
        ),
    ]

    # ── Utilities ─────────────────────────────────────────────────────────

    u_response_no_recurrence: Annotated[
        float,
        Field(
            ge=-1.0,
            le=1.0,
            description=(
                "Utility (quality-of-life weight) for the health state where "
                "the treatment succeeds and the headache does not return within "
                "48 hours. Typically 1.0 (full health for the episode)."
            ),
        ),
    ]

    u_response_recurrence: Annotated[
        float,
        Field(
            ge=-1.0,
            le=1.0,
            description=(
                "Utility for the health state where the treatment succeeds but "
                "the headache recurs within 48 hours, requiring a second dose. "
                "Typically slightly below u_response_no_recurrence (e.g. 0.9)."
            ),
        ),
    ]

    u_no_response_endures: Annotated[
        float,
        Field(
            ge=-1.0,
            le=1.0,
            description=(
                "Utility for the health state where the treatment fails and "
                "the patient endures the attack at home without further care. "
                "Can be negative — severe migraine is highly disabling."
            ),
        ),
    ]

    u_no_response_ed: Annotated[
        float,
        Field(
            ge=-1.0,
            le=1.0,
            description=(
                "Utility for the health state where the treatment fails, "
                "the patient visits an ED, and is relieved there. "
                "Typically slightly positive (e.g. 0.1) — uncomfortable but "
                "the patient is eventually relieved."
            ),
        ),
    ]

    u_no_response_hospital: Annotated[
        float,
        Field(
            ge=-1.0,
            le=1.0,
            description=(
                "Utility for the health state where the treatment fails, "
                "the patient visits an ED, and is subsequently hospitalised. "
                "Can be negative."
            ),
        ),
    ]

    # ── Probabilities ──────────────────────────────────────────────────────

    p_response: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description=(
                "Probability that the treatment produces a clinical response "
                "(headache converts from moderate/severe to mild/none within "
                "2 hours). The primary clinical efficacy parameter. In [0, 1]."
            ),
        ),
    ]

    p_no_recurrence: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description=(
                "Probability that a patient who responded to treatment does NOT "
                "experience headache recurrence within 48 hours. "
                "In [0, 1]."
            ),
        ),
    ]

    p_endures: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description=(
                "Probability that a non-responding patient endures the attack "
                "at home rather than seeking emergency care. "
                "Typically high (most patients do not go to the ED). "
                "In [0, 1]."
            ),
        ),
    ]

    p_ed_relief: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description=(
                "Probability that a patient who visits the ED is relieved "
                "there and is NOT subsequently hospitalised. "
                "Typically very high (e.g. 0.994). In [0, 1]."
            ),
        ),
    ]

    # ── Conversion ────────────────────────────────────────────────────────

    def to_strategy_params(self) -> StrategyParams:
        """
        Convert to the simulation's immutable :class:`StrategyParams` dataclass.

        Returns
        -------
        StrategyParams
            Ready for use with :func:`simulate_strategy`.
        """
        return StrategyParams(**self.model_dump())


# ---------------------------------------------------------------------------
# AnalysisConfig
# ---------------------------------------------------------------------------


class AnalysisConfig(BaseModel):
    """
    Full configuration for a decision tree analysis run.

    Wraps one or more :class:`StrategySchema` instances together with
    simulation settings and report options.  Provides a single entry point
    (``run()``) that generates, executes, and returns the formatted markdown
    report.

    Parameters
    ----------
    strategies : list of StrategySchema
        One entry per treatment strategy.  Must contain at least one entry.
    reference_index : int
        Index of the reference (comparator) strategy. Defaults to 0.
    title : str
        Heading used in the formatted analysis report.
    n_patients : int
        Number of patients to simulate per strategy. Defaults to 1,000,000.
    seed : int
        Base random seed. Each strategy receives seed + i. Defaults to 2026.
    currency_symbol : str
        Symbol prepended to cost values (e.g. ``"$"``, ``"£"``).
    currency_name : str
        Optional full currency description for the report header.
    show_path_table : bool
        Whether to include the terminal path distribution table.
    show_confidence_intervals : bool
        Whether to include 95 % CI columns.
    model_citation : str
        Citation string for the methodological notes footer.
    """

    strategies: Annotated[
        list[StrategySchema],
        Field(
            min_length=1,
            description=(
                "List of treatment strategies to analyse. "
                "At least one strategy is required."
            ),
        ),
    ]

    reference_index: Annotated[
        int,
        Field(
            ge=0,
            default=0,
            description=(
                "Index (0-based) of the reference strategy in the strategies "
                "list. All other strategies are compared against this one. "
                "Defaults to 0 (the first strategy)."
            ),
        ),
    ]

    title: Annotated[
        str,
        Field(
            default="Health Economic Decision Tree Analysis",
            min_length=1,
            description="Title displayed at the top of the analysis report.",
        ),
    ]

    n_patients: Annotated[
        int,
        Field(
            default=1_000_000,
            ge=1,
            description=(
                "Number of patients to simulate per strategy. "
                "Larger values give tighter confidence intervals at the cost "
                "of compute time. 1,000,000 takes < 5 s on modern hardware."
            ),
        ),
    ]

    seed: Annotated[
        int,
        Field(
            default=2026,
            ge=0,
            description=(
                "Base random seed for reproducibility. "
                "Each strategy receives seed + i."
            ),
        ),
    ]

    currency_symbol: Annotated[
        str,
        Field(
            default="$",
            min_length=1,
            description=(
                "Currency symbol prepended to all cost values in the report "
                "(e.g. '$', '£', '€', 'Can$')."
            ),
        ),
    ]

    currency_name: Annotated[
        str,
        Field(
            default="",
            description=(
                "Optional full currency description shown in the report header "
                "(e.g. '1995 Canadian dollars'). Leave blank to omit."
            ),
        ),
    ]

    show_path_table: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "If True, include a table showing the percentage of patients "
                "reaching each terminal path. Useful for teaching."
            ),
        ),
    ]

    show_confidence_intervals: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "If True, include 95% confidence interval columns in the "
                "strategy results table."
            ),
        ),
    ]

    model_citation: Annotated[
        str,
        Field(
            default=(
                "Evans et al. (1997). PharmacoEconomics 12(5): 565\u2013577."
            ),
            description="Citation for the decision tree methodology.",
        ),
    ]

    @model_validator(mode="after")
    def _reference_index_in_range(self) -> "AnalysisConfig":
        n = len(self.strategies)
        if self.reference_index >= n:
            raise ValueError(
                f"reference_index {self.reference_index!r} is out of range "
                f"for {n} strateg{'y' if n == 1 else 'ies'} "
                f"(valid range: 0 to {n - 1})."
            )
        return self

    # ── Pipeline convenience methods ───────────────────────────────────────

    def to_strategy_params_list(self) -> list[StrategyParams]:
        """Return all strategies as :class:`StrategyParams` instances."""
        return [s.to_strategy_params() for s in self.strategies]

    def to_script(self) -> str:
        """
        Generate the self-contained Python simulation script.

        Returns
        -------
        str
            Complete Python source code, ready to save and execute.
        """
        return generate_script(
            strategies=self.to_strategy_params_list(),
            reference_index=self.reference_index,
            n_patients=self.n_patients,
            seed=self.seed,
            title=self.title,
            currency_symbol=self.currency_symbol,
            currency_name=self.currency_name,
            show_path_table=self.show_path_table,
            show_confidence_intervals=self.show_confidence_intervals,
            model_citation=self.model_citation,
        )

    def run(self, *, timeout: float = 120.0) -> str:
        """
        Generate and execute the simulation, returning the markdown report.

        This is the single entry point for the full pipeline:
        StrategySchema → StrategyParams → generated script → subprocess →
        formatted markdown.

        Parameters
        ----------
        timeout : float
            Maximum seconds to allow the subprocess to run. Defaults to 120.

        Returns
        -------
        str
            GitHub-flavoured markdown analysis report.

        Raises
        ------
        ScriptExecutionError
            If the generated script exits with a non-zero return code.
        subprocess.TimeoutExpired
            If the subprocess exceeds ``timeout`` seconds.
        """
        return run_script(self.to_script(), timeout=timeout)
