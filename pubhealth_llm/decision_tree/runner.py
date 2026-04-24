"""
Subprocess runner for generated health economic decision tree scripts.

Takes a script string produced by :func:`pubhealth_llm.decision_tree.generator.generate_script`,
writes it to a temporary file, executes it with the same Python interpreter that
is running this process, and returns the captured stdout as a string.

Design constraints
------------------
* The generated script imports from ``pubhealth_llm.decision_tree``, so it must
  run in the same virtual environment.  We use ``sys.executable`` rather than a
  hard-coded ``"python"`` so this works regardless of venv activation state.
* The script is written to a ``NamedTemporaryFile`` with ``delete=False`` so that
  the path is valid when the subprocess opens it on all platforms (Windows does not
  allow two open handles on a NamedTemporaryFile).  The file is deleted in a
  ``finally`` block.
* ``stderr`` is captured separately and included in the exception message when the
  subprocess fails, giving the caller (and ultimately the student) actionable
  diagnostic information.
* A configurable ``timeout`` prevents a pathological script from hanging the
  Gradio server indefinitely.  The default (120 s) is generous for a 1 M-patient
  simulation (typically < 5 s on modern hardware) while still protecting against
  runaway processes.

Errors
------
``ScriptExecutionError``
    Raised when the subprocess exits with a non-zero return code.  Carries the
    original ``stderr`` text for diagnosis.
``subprocess.TimeoutExpired``
    Re-raised as-is if the subprocess exceeds ``timeout`` seconds.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Optional


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class ScriptExecutionError(RuntimeError):
    """
    Raised when a generated decision tree script exits with a non-zero status.

    Attributes
    ----------
    returncode : int
        The exit code returned by the subprocess.
    stderr : str
        Text captured from the script's stderr stream.
    stdout : str
        Text captured from the script's stdout stream (may be partial).
    """

    def __init__(self, returncode: int, stderr: str, stdout: str) -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        super().__init__(
            f"Generated script exited with return code {returncode}.\n"
            f"stderr:\n{stderr or '(empty)'}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_script(
    script: str,
    *,
    timeout: Optional[float] = 120.0,
    extra_env: Optional[dict[str, str]] = None,
) -> str:
    """
    Execute a generated decision tree script and return its stdout.

    The script is written to a temporary ``.py`` file and executed with
    ``sys.executable`` (the same Python interpreter running this process).
    This guarantees that ``pubhealth_llm.decision_tree`` is importable.

    Parameters
    ----------
    script : str
        Complete Python source code, as returned by
        :func:`pubhealth_llm.decision_tree.generator.generate_script`.
    timeout : float or None
        Maximum wall-clock time in seconds to allow the subprocess to run.
        Pass ``None`` to disable the timeout (not recommended in production).
        Defaults to 120 seconds.
    extra_env : dict[str, str] or None
        Optional additional environment variables to pass to the subprocess.
        Merged on top of the current process environment.  Useful in tests to
        inject ``PYTHONPATH`` or other variables.

    Returns
    -------
    str
        The complete text written to the script's stdout — the formatted
        markdown analysis report.

    Raises
    ------
    ScriptExecutionError
        If the subprocess exits with a non-zero return code.
    subprocess.TimeoutExpired
        If the subprocess does not finish within ``timeout`` seconds.
    ValueError
        If ``script`` is empty.

    Examples
    --------
    >>> from pubhealth_llm.decision_tree import StrategyParams
    >>> from pubhealth_llm.decision_tree.generator import generate_script
    >>> from pubhealth_llm.decision_tree.runner import run_script
    >>> params = StrategyParams(
    ...     name="Treatment A",
    ...     cost_drug=10.0, cost_ed=50.0, cost_hospital=500.0,
    ...     u_response_no_recurrence=1.0, u_response_recurrence=0.9,
    ...     u_no_response_endures=-0.3, u_no_response_ed=0.1,
    ...     u_no_response_hospital=-0.3,
    ...     p_response=0.5, p_no_recurrence=0.6,
    ...     p_endures=0.9, p_ed_relief=0.99,
    ... )
    >>> script = generate_script([params], n_patients=1_000, seed=42)
    >>> output = run_script(script)
    >>> "Treatment A" in output
    True
    """
    if not script or not script.strip():
        raise ValueError("script must be a non-empty string.")

    # Build environment: inherit current env, then apply extras.
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    # Ensure the project root (two levels above this file) is on PYTHONPATH so
    # that the generated script can import from pubhealth_llm regardless of
    # whether the package is installed or only on sys.path via pytest/editable
    # install.  We prepend rather than replace so any user-supplied PYTHONPATH
    # entries are preserved.
    _project_root = str(
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
    )
    existing_pypath = env.get("PYTHONPATH", "")
    if _project_root not in existing_pypath.split(os.pathsep):
        env["PYTHONPATH"] = (
            _project_root + os.pathsep + existing_pypath
            if existing_pypath
            else _project_root
        )

    tmp_path: Optional[str] = None
    try:
        # Write script to a temp file.  suffix=".py" keeps the error messages
        # readable; delete=False is required on Windows.
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write(script)
            tmp_path = fh.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        if result.returncode != 0:
            raise ScriptExecutionError(
                returncode=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout,
            )

        return result.stdout

    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass  # best-effort cleanup — not critical
