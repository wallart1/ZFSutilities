"""Pytest bootstrap for the Python test suites.

Ensures the test directory (for ``test_support``) and the repository
``python/`` source directory are importable regardless of the invocation
directory, so ``python3 -m pytest tests/python`` works from the repo root as
well as from inside ``tests/python``.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_PYTHON = os.path.realpath(os.path.join(_HERE, "..", "..", "python"))

for _path in (_HERE, _REPO_PYTHON):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def pytest_configure(config):
    """Suppress the fork()-in-multithreaded-process DeprecationWarning.

    Single-process pytest accumulates helper threads from earlier suites, so
    the multiprocessing-based suites (test_file_locking, test_profile_integration,
    test_profile_runner_concurrency, test_backup_history) emit CPython's
    "multi-threaded, use of fork()" advisory on every child start. The fork
    children are short-lived, single-purpose lock holders that never touch
    locks inherited from other threads, and the per-file runner.py gives each
    suite a fresh process, so the advisory indicates no real defect here.
    """
    config.addinivalue_line(
        "filterwarnings",
        "ignore:This process .* is multi-threaded, use of fork\\(\\) "
        "may lead to deadlocks:DeprecationWarning",
    )
