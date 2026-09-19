"""Pytest bootstrap for the Python test suites.

Ensures the test directory (for ``test_support``) and the repository
``python/`` source directory are importable regardless of the invocation
directory, so ``python3 -m pytest tests/python`` works from the repo root as
well as from inside ``tests/python``.
"""

import os
import sys
import warnings

# Suppress the GTK/AT-SPI "Couldn't connect to accessibility bus" warning when
# tests import real GTK modules (e.g. test_datasets_tree, test_main) in a
# headless environment. Mirrors the guard in python/docs_viewer.py and the one
# the former tests/python/runner.py set before importing test modules.
os.environ.setdefault("NO_AT_BRIDGE", "1")

# Suppress a harmless GLib IOChannel warning that occurs when mocked tests close
# file descriptors that the real GLib override still references.
warnings.filterwarnings(
    "ignore",
    message=".*Error while getting flags for FD.*",
    category=Warning,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_PYTHON = os.path.realpath(os.path.join(_HERE, "..", "..", "python"))

for _path in (_HERE, _REPO_PYTHON):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def pytest_configure(config):
    """Suppress the fork()-in-multithreaded-process DeprecationWarning.

    A pytest process accumulates helper threads from earlier suites, so the
    multiprocessing-based suites (test_file_locking, test_profile_integration,
    test_profile_runner_concurrency, test_backup_history) emit CPython's
    "multi-threaded, use of fork()" advisory on every child start. The fork
    children are short-lived, single-purpose lock holders that never touch
    locks inherited from other threads, and under pytest-xdist each worker is
    a fresh process long before it fills with threads, so the advisory
    indicates no real defect here.
    """
    config.addinivalue_line(
        "filterwarnings",
        "ignore:This process .* is multi-threaded, use of fork\\(\\) "
        "may lead to deadlocks:DeprecationWarning",
    )
