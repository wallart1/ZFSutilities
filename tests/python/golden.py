"""Golden-file comparison helper for command/argv-builder tests.

Builder tests assert exact command lines; golden files hold the expected
command text so legitimate refactors regenerate expectations instead of
hand-repairing assertion clusters.

Layout: ``tests/golden/<module>/<Class>.<test>.golden``. Canonical form is
exactly one trailing newline; list/tuple actuals are serialized one element
per line so argv diffs read per-argument.

Workflow: after a legitimate refactor, run
``UPDATE_GOLDEN=1 tests/run-tests <suite>``, then ``git diff`` the goldens
and review them like code. In update mode, updated tests appear as skips;
the harness 'skipped' total then includes golden updates in addition to any
environment skips. Compare-mode skips are environment or marker skips only.
"""

import difflib
import os
from pathlib import Path

_GOLDEN_ROOT = Path(__file__).resolve().parent.parent / "golden"


def _default_name(testcase):
    return f"{type(testcase).__name__}.{testcase._testMethodName}"


def _canonical(actual):
    if isinstance(actual, (list, tuple)):
        text = "\n".join(str(item) for item in actual)
    else:
        text = str(actual)
    return text.rstrip("\n") + "\n"


def golden_path(testcase, name=None):
    suite = type(testcase).__module__.rsplit(".", 1)[-1]
    return _GOLDEN_ROOT / suite / f"{name or _default_name(testcase)}.golden"


def check(testcase, actual, name=None):
    """Compare ``actual`` against this test's golden file.

    With ``UPDATE_GOLDEN=1`` a differing golden is rewritten and the test is
    skipped ("golden updated: ..."); identical content passes and leaves the
    file untouched. Without it, a mismatch raises ``AssertionError`` with a
    unified diff, and a missing golden names the command that creates it.
    """
    path = golden_path(testcase, name)
    actual_text = _canonical(actual)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        existing = path.read_text() if path.exists() else None
        if existing != actual_text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual_text)
            testcase.skipTest(f"golden updated: {path.stem}")
        return
    if not path.exists():
        suite = type(testcase).__module__.rsplit(".", 1)[-1]
        raise AssertionError(
            f"golden {path} missing — run UPDATE_GOLDEN=1 tests/run-tests {suite}"
        )
    expected_text = path.read_text()
    if expected_text != actual_text:
        diff = "\n".join(
            difflib.unified_diff(
                expected_text.splitlines(),
                actual_text.splitlines(),
                fromfile=f"{path.name} (golden)",
                tofile="actual",
                lineterm="",
            )
        )
        raise AssertionError(f"golden mismatch for {path.stem}:\n{diff}")
