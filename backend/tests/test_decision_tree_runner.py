"""
Tests for pubhealth_llm.decision_tree.runner
============================================

Covers:
* run_script — happy path (single strategy, two strategies)
* run_script — output content correctness (markdown headers, ICER, Evans values)
* run_script — error handling (bad script, empty input, timeout, env injection)
* ScriptExecutionError — attributes populated correctly
* cleanup — temp file is removed after execution
* Integration: generate_script → run_script round-trip
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap

import numpy as np
import pytest

from pubhealth_llm.decision_tree import (
    ScriptExecutionError,
    StrategyParams,
    run_script,
)
from pubhealth_llm.decision_tree.generator import generate_script


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

CAFFEINE = StrategyParams(
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

SUMATRIPTAN = StrategyParams(
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


def _single_script(n_patients: int = 2_000, seed: int = 42) -> str:
    return generate_script([CAFFEINE], n_patients=n_patients, seed=seed)


def _two_strategy_script(n_patients: int = 2_000, seed: int = 42) -> str:
    return generate_script(
        [CAFFEINE, SUMATRIPTAN],
        n_patients=n_patients,
        seed=seed,
        title="Evans 1997 Test",
    )


# ---------------------------------------------------------------------------
# TestScriptExecutionError
# ---------------------------------------------------------------------------


class TestScriptExecutionError:
    def test_is_runtime_error(self):
        err = ScriptExecutionError(returncode=1, stderr="boom", stdout="")
        assert isinstance(err, RuntimeError)

    def test_returncode_attribute(self):
        err = ScriptExecutionError(returncode=42, stderr="x", stdout="y")
        assert err.returncode == 42

    def test_stderr_attribute(self):
        err = ScriptExecutionError(returncode=1, stderr="bad things", stdout="")
        assert err.stderr == "bad things"

    def test_stdout_attribute(self):
        err = ScriptExecutionError(returncode=1, stderr="", stdout="partial out")
        assert err.stdout == "partial out"

    def test_str_contains_returncode(self):
        err = ScriptExecutionError(returncode=2, stderr="err msg", stdout="")
        assert "2" in str(err)

    def test_str_contains_stderr(self):
        err = ScriptExecutionError(returncode=1, stderr="err msg", stdout="")
        assert "err msg" in str(err)

    def test_empty_stderr_shows_empty_label(self):
        err = ScriptExecutionError(returncode=1, stderr="", stdout="")
        assert "(empty)" in str(err)


# ---------------------------------------------------------------------------
# TestRunScriptHappyPath
# ---------------------------------------------------------------------------


class TestRunScriptHappyPath:
    def test_returns_string(self):
        output = run_script(_single_script())
        assert isinstance(output, str)

    def test_non_empty_output(self):
        output = run_script(_single_script())
        assert len(output.strip()) > 0

    def test_single_strategy_strategy_name_in_output(self):
        output = run_script(_single_script())
        assert "Caffeine/Ergotamine" in output

    def test_two_strategy_both_names_in_output(self):
        output = run_script(_two_strategy_script())
        assert "Caffeine/Ergotamine" in output
        assert "Sumatriptan" in output

    def test_markdown_h1_in_output(self):
        output = run_script(_two_strategy_script())
        assert "# " in output

    def test_strategy_results_header(self):
        output = run_script(_two_strategy_script())
        assert "## Strategy Results" in output

    def test_incremental_header_when_two_strategies(self):
        output = run_script(_two_strategy_script())
        assert "## Incremental Cost-Effectiveness" in output

    def test_path_distribution_header(self):
        output = run_script(_two_strategy_script())
        assert "## Terminal Path Distribution" in output

    def test_methodological_notes_header(self):
        output = run_script(_two_strategy_script())
        assert "## Methodological Notes" in output

    def test_icer_value_present(self):
        # ICER line contains /QALY
        output = run_script(_two_strategy_script())
        assert "QALY" in output

    def test_output_ends_with_newline(self):
        # print() adds a trailing newline
        output = run_script(_single_script())
        assert output.endswith("\n")


# ---------------------------------------------------------------------------
# TestRunScriptEvansNumerics
# ---------------------------------------------------------------------------


class TestRunScriptEvansNumerics:
    """Check that the full pipeline reproduces Evans (1997) economics."""

    def test_evans_icer_within_10_percent(self):
        """Annualised ICER should be within 10% of the published $29,366 Can/QALY."""
        output = run_script(
            generate_script(
                [CAFFEINE, SUMATRIPTAN],
                n_patients=500_000,
                seed=2026,
            )
        )
        # Extract the numeric ICER from the output (format: +$29,366/QALY or similar)
        import re
        matches = re.findall(r"[\+\-]?\$([0-9,]+)/QALY", output)
        assert matches, f"No ICER value found in output:\n{output}"
        icer_value = float(matches[0].replace(",", ""))
        assert abs(icer_value - 29_366) / 29_366 < 0.10, (
            f"ICER {icer_value} deviates more than 10% from Evans $29,366"
        )

    def test_caffeine_lower_cost_than_sumatriptan(self):
        output = run_script(_two_strategy_script(n_patients=50_000))
        # Positive incremental cost means sumatriptan costs more (reference = caffeine)
        assert "+" in output  # signed cost in incremental table

    def test_title_in_output(self):
        script = generate_script(
            [CAFFEINE, SUMATRIPTAN],
            n_patients=2_000,
            seed=1,
            title="My Custom Title",
        )
        output = run_script(script)
        assert "My Custom Title" in output

    def test_currency_symbol_in_output(self):
        script = generate_script(
            [CAFFEINE, SUMATRIPTAN],
            n_patients=2_000,
            seed=1,
            currency_symbol="£",
        )
        output = run_script(script)
        assert "£" in output


# ---------------------------------------------------------------------------
# TestRunScriptErrorHandling
# ---------------------------------------------------------------------------


class TestRunScriptErrorHandling:
    def test_empty_script_raises_value_error(self):
        with pytest.raises(ValueError, match="non-empty"):
            run_script("")

    def test_whitespace_only_script_raises_value_error(self):
        with pytest.raises(ValueError, match="non-empty"):
            run_script("   \n\t  ")

    def test_syntax_error_script_raises_execution_error(self):
        bad_script = "def foo(\n    # unclosed\n"
        with pytest.raises(ScriptExecutionError) as exc_info:
            run_script(bad_script)
        assert exc_info.value.returncode != 0

    def test_runtime_error_script_raises_execution_error(self):
        bad_script = "raise RuntimeError('deliberate failure')\n"
        with pytest.raises(ScriptExecutionError) as exc_info:
            run_script(bad_script)
        err = exc_info.value
        assert err.returncode != 0
        assert "deliberate failure" in err.stderr

    def test_execution_error_stdout_captured(self):
        """stdout printed before a crash should still be captured."""
        script = textwrap.dedent("""\
            print("partial output before crash")
            raise RuntimeError("crash after print")
        """)
        with pytest.raises(ScriptExecutionError) as exc_info:
            run_script(script)
        assert "partial output before crash" in exc_info.value.stdout

    def test_timeout_raises_timeout_expired(self):
        """A script that sleeps forever should raise TimeoutExpired."""
        script = "import time; time.sleep(9999)\n"
        with pytest.raises(subprocess.TimeoutExpired):
            run_script(script, timeout=1.0)

    def test_import_error_script_raises_execution_error(self):
        bad_script = "import this_module_does_not_exist_xyz\n"
        with pytest.raises(ScriptExecutionError):
            run_script(bad_script)


# ---------------------------------------------------------------------------
# TestRunScriptTempFileCleanup
# ---------------------------------------------------------------------------


class TestRunScriptTempFileCleanup:
    def test_temp_file_removed_after_success(self):
        """No temp .py files should linger after a successful run."""
        tmp_dir = tempfile.gettempdir()
        before = set(f for f in os.listdir(tmp_dir) if f.endswith(".py"))
        run_script(_single_script())
        after = set(f for f in os.listdir(tmp_dir) if f.endswith(".py"))
        new_files = after - before
        assert not new_files, f"Temp files not cleaned up: {new_files}"

    def test_temp_file_removed_after_failure(self):
        """Temp file should be cleaned up even when the script fails."""
        tmp_dir = tempfile.gettempdir()
        before = set(f for f in os.listdir(tmp_dir) if f.endswith(".py"))
        with pytest.raises(ScriptExecutionError):
            run_script("raise RuntimeError('fail')\n")
        after = set(f for f in os.listdir(tmp_dir) if f.endswith(".py"))
        new_files = after - before
        assert not new_files, f"Temp files not cleaned up after failure: {new_files}"


# ---------------------------------------------------------------------------
# TestRunScriptExtraEnv
# ---------------------------------------------------------------------------


class TestRunScriptExtraEnv:
    def test_extra_env_variable_visible_in_script(self):
        """Variables passed via extra_env should be accessible in the script."""
        script = textwrap.dedent("""\
            import os
            print(os.environ.get("_TEST_PUBHEALTH_VAR", "MISSING"))
        """)
        output = run_script(script, extra_env={"_TEST_PUBHEALTH_VAR": "hello123"})
        assert "hello123" in output

    def test_extra_env_does_not_affect_process_env(self):
        """extra_env must not mutate the calling process's os.environ."""
        key = "_TEST_PUBHEALTH_MUTATION"
        assert key not in os.environ
        script = "print('ok')\n"
        run_script(script, extra_env={key: "should_not_leak"})
        assert key not in os.environ


# ---------------------------------------------------------------------------
# TestRunScriptUsesCorrectInterpreter
# ---------------------------------------------------------------------------


class TestRunScriptUsesCorrectInterpreter:
    def test_uses_current_python_executable(self):
        """The script should run under the same Python as the test process."""
        script = textwrap.dedent(f"""\
            import sys
            print(sys.executable)
        """)
        output = run_script(script)
        # Normalize both paths to resolve symlinks
        assert os.path.realpath(output.strip()) == os.path.realpath(sys.executable)
