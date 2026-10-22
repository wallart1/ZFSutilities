"""Pytest bootstrap for the Python test suites.

Ensures the test directory (for ``test_support``) and the repository
``python/`` source directory are importable regardless of the invocation
directory, so ``python3 -m pytest tests/python`` works from the repo root as
well as from inside ``tests/python``.

Also fences the whole batch (controller and every xdist worker) onto a
private Xvfb when an ambient display exists, so no test process ever
connects to the operator's display — see ``_fence_display``.
"""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings

# Suppress the GTK/AT-SPI "Couldn't connect to accessibility bus" warning when
# tests import real GTK modules (e.g. test_datasets_tree, test_main) in a
# headless environment. Mirrors the guard in python/docs_viewer.py and the one
# the former tests/python/runner.py set before importing test modules.
os.environ.setdefault("NO_AT_BRIDGE", "1")

# Redirect advisory locks into an isolated, per-process temporary directory.
# file_locking/cron_manager/feature_config bind lock paths at import time from
# ZFSUTILITIES_LOCK_DIR (default /run/lock/zfsutilities), and tests must never
# touch the host's real lock directory: it may be root-owned (breaking
# non-root runs) or held by a live instance. pytest imports this module before
# any test module, so the import-time bindings pick the temporary location up;
# under pytest-xdist each worker gets its own directory. An explicitly
# exported value is respected for manual debugging.
if "ZFSUTILITIES_LOCK_DIR" not in os.environ:
    _isolated_lock_dir = tempfile.mkdtemp(prefix="zfsutilities-test-locks-")
    os.environ["ZFSUTILITIES_LOCK_DIR"] = _isolated_lock_dir
    atexit.register(shutil.rmtree, _isolated_lock_dir, ignore_errors=True)

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
    _fence_display()


# --- Private-display fence -------------------------------------------------
#
# xdist workers are `python -c <bootstrap>` processes; the one real-GTK
# suite (test_datasets_tree) makes each worker that runs it open the
# ambient X display, and GDK then creates its per-connection client-leader
# window — an unmapped 10x10 window named after the `-c` argv. It is
# destroyed at worker exit, but the class of leak is structural: test
# processes connecting to the operator's display. Give the whole batch
# (controller plus every execnet worker, which inherit the controller's
# environment) a private Xvfb — the same fence alignment_realized_check
# applies to itself. Display numbers 89..80 stay clear of the realized
# check's own 99..90 so its independently started Xvfb never collides.

_XVFB_PROC = None


def _start_private_xvfb():
    """Start a private Xvfb; return (proc, display) or (None, None)."""
    if not os.path.exists("/usr/bin/Xvfb"):
        return None, None
    for number in range(89, 79, -1):
        socket_path = f"/tmp/.X11-unix/X{number}"
        if os.path.exists(socket_path):
            continue
        try:
            proc = subprocess.Popen(
                [
                    "/usr/bin/Xvfb",
                    f":{number}",
                    "-nolisten",
                    "tcp",
                    "-screen",
                    "0",
                    "1024x768x24",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return None, None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if os.path.exists(socket_path):
                return proc, f":{number}"
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        proc.terminate()
    return None, None


def _stop_private_xvfb():
    global _XVFB_PROC
    if _XVFB_PROC is not None:
        _XVFB_PROC.terminate()
        try:
            _XVFB_PROC.wait(timeout=5)
        except Exception:
            _XVFB_PROC.kill()
        _XVFB_PROC = None


def _fence_display():
    """Redirect DISPLAY to a private Xvfb when an ambient display exists.

    Headless runs (no DISPLAY) keep their behavior. When no private Xvfb
    can be started (Xvfb missing, no free display number) the run degrades
    to the previous behavior and uses the ambient display. The
    ZFSUTILITIES_TEST_DISPLAY marker stops xdist workers (which run this
    same conftest after inheriting the controller's redirected DISPLAY)
    from starting their own.
    """
    global _XVFB_PROC
    if os.environ.get("ZFSUTILITIES_TEST_DISPLAY") == "private":
        return
    if not os.environ.get("DISPLAY"):
        return
    proc, display = _start_private_xvfb()
    if proc is None or display is None:
        return
    os.environ["DISPLAY"] = display
    os.environ["ZFSUTILITIES_TEST_DISPLAY"] = "private"
    _XVFB_PROC = proc
    atexit.register(_stop_private_xvfb)
