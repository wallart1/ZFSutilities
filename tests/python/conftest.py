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
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings

import pytest

# Suppress the GTK/AT-SPI "Couldn't connect to accessibility bus" warning when
# tests import real GTK modules (e.g. test_datasets_tree, test_main) in a
# headless environment. Mirrors the guard in python/docs_viewer.py and the one
# the former tests/python/runner.py set before importing test modules.
os.environ.setdefault("NO_AT_BRIDGE", "1")

# Redirect advisory locks into an isolated, per-process temporary directory.
# file_locking/cron_manager/feature_config bind lock paths at import time from
# ZFSUTILITIES_LOCK_DIR (default /run/lock/zfsutilities), and
# zfs_lock_manager binds from ZFSLOCK_DIR; tests must never
# touch the host's real lock directory: it may be root-owned (breaking
# non-root runs) or held by a live instance. pytest imports this module before
# any test module, so the import-time bindings pick the temporary location up;
# under pytest-xdist each worker gets its own directory. An explicitly
# exported value is respected for manual debugging.
if "ZFSUTILITIES_LOCK_DIR" not in os.environ:
    _isolated_lock_dir = tempfile.mkdtemp(prefix="zfsutilities-test-locks-")
    os.environ["ZFSUTILITIES_LOCK_DIR"] = _isolated_lock_dir
    atexit.register(shutil.rmtree, _isolated_lock_dir, ignore_errors=True)
if "ZFSLOCK_DIR" not in os.environ:
    os.environ["ZFSLOCK_DIR"] = os.environ["ZFSUTILITIES_LOCK_DIR"]

# Redirect bytecode caching out of the checkout for sudo test legs. A root
# pytest run that imports a module with a missing or stale .pyc would leave
# a root-owned __pycache__ file in the user-owned tree — unwritable for the
# user and recurring after every sweep. Set at conftest import time, before
# collection imports any test or product module; python/zfsutilities_gui.py
# carries the same block for sudo GUI launches. An interpreter-level
# PYTHONPYCACHEPREFIX is respected and left alone.
if os.geteuid() == 0 and sys.pycache_prefix is None:
    _pycache_dir = os.environ.get("ZFSUTILITIES_PYCACHE_DIR", "/var/cache/zfsutilities/pycache")
    os.makedirs(_pycache_dir, exist_ok=True)
    sys.pycache_prefix = _pycache_dir

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


# --- Dataset-lock leak reset -------------------------------------------------
#
# GUI handlers acquire real zfs_lock_manager locks. A test that starts an
# action without driving its fake runner to completion leaves a lock file
# whose recorded PID is the live worker process, so stale-lock detection
# can never reap it — and every later real-lock acquisition in the same
# worker for that dataset conflicts (the enrollment-offer suites hit this
# as soon as the offers began locking the pool root). Reset the isolated
# lock directory's leftovers and the module's bookkeeping after each test.


@pytest.fixture(autouse=True)
def _reset_dataset_lock_state():
    yield
    try:
        import zfs_lock_manager as _zlm

        for _pattern in (
            os.path.join(_zlm.ZFSLOCK_LOCKS_DIR, "*.lock"),
            os.path.join(_zlm.ZFSLOCK_LOCKS_DIR, ".remote-conflict.*"),
            os.path.join(_zlm.ZFSLOCK_PIDS_DIR, "*"),
        ):
            for _path in glob.glob(_pattern):
                try:
                    os.unlink(_path)
                except OSError:
                    pass
        _zlm._lock_refcounts.clear()
        _zlm._remote_holds.clear()
    except Exception:  # noqa: S110 - pragma: no cover; best-effort hygiene
        pass


# --- Run-history isolation ---------------------------------------------------
#
# backup_history binds HISTORY_PATH from the state directory at import time
# (default /var/lib/zfsutilities/history.json). Runner endings — finish and
# both cancellation paths — append history entries, so a test that drives a
# runner to any ending must never write the host's real history (a sudo
# test leg could). Point the bound path at a per-test temporary file; suites
# that set their own path inside the test keep working, and the original is
# restored afterwards.


@pytest.fixture(autouse=True)
def _isolate_run_history(tmp_path, monkeypatch):
    history_module = sys.modules.get("backup_history")
    if history_module is not None:
        monkeypatch.setattr(history_module, "HISTORY_PATH", str(tmp_path / "history.json"))
    yield


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


# --- Dashboard refresh-thread drain -----------------------------------------
#
# refresh_dashboard_page() defaults to async: it launches a daemon worker
# whose gather calls the iscsi/fence/pool-identity TTL-cache getters. A
# real-GUI test that triggers a refresh (the page-switch handler does) can
# leave that worker running past the test's end. On CI runners the gather's
# ssh/zpool subprocesses time out over seconds instead of failing fast, so
# the straggler's cache writes landed INSIDE later tests on the same xdist
# worker — defeating their setUp resets (observed on the v0.136.0 CI runs:
# compute-mocks with 0 calls, one `[] is not None`). Wrap the worker so its
# threads are tracked, then join them and reset the caches after EVERY test.

_REFRESH_THREADS = []
_ORIG_REFRESH_WORKER = None

# Generously above the gather's own bound (its subprocesses run with 5-10s
# timeouts), so a live straggler is always reaped, never just abandoned.
_REFRESH_JOIN_TIMEOUT = 70.0


def _reset_dashboard_caches(dp):
    """Leave the three TTL caches cold, as at module import."""
    dp._iscsi_luns_cache["time"] = 0.0
    dp._iscsi_luns_cache["value"] = []
    dp._fence_cache["time"] = 0.0
    dp._fence_cache["warning"] = None
    dp._pool_identity_cache["time"] = 0.0
    dp._pool_identity_cache["value"] = []


@pytest.fixture(autouse=True)
def _drain_dashboard_refresh_threads():
    """Join leaked dashboard refresh workers; reset the TTL caches.

    Installs the tracking wrapper once dashboard_page first appears in
    sys.modules (a suite that never imports it pays nothing), and drains
    after every test so no cache write can land inside a later test.
    """
    global _ORIG_REFRESH_WORKER
    import threading

    dp = sys.modules.get("dashboard_page")
    if dp is not None and _ORIG_REFRESH_WORKER is None and hasattr(dp, "_dashboard_refresh_worker"):
        _ORIG_REFRESH_WORKER = dp._dashboard_refresh_worker

        def _tracking_refresh_worker(*args, **kwargs):
            thread = threading.current_thread()
            _REFRESH_THREADS.append(thread)
            try:
                return _ORIG_REFRESH_WORKER(*args, **kwargs)
            finally:
                _REFRESH_THREADS.remove(thread)

        dp._dashboard_refresh_worker = _tracking_refresh_worker
    try:
        yield
    finally:
        # Snapshot: each joined worker's finally removes itself from
        # _REFRESH_THREADS from its own thread, so the drain must not
        # iterate the live list while the joins mutate it.
        for thread in list(_REFRESH_THREADS):  # noqa: PERF101
            thread.join(timeout=_REFRESH_JOIN_TIMEOUT)
        if dp is not None:
            _reset_dashboard_caches(dp)
