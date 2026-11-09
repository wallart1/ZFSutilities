"""Tests for file_locking.py — advisory flock helpers."""

import contextlib
import fcntl
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import file_locking as fl

# The cross-process tests hold their lock in a FRESH interpreter
# (tests/python/lock_child.py), never a multiprocessing fork of this
# worker: a forked child of a loaded pytest-xdist worker can deadlock in
# inherited locks before it reaches its first queue.put() (CI
# 2026-11-08..09, both daily runs at a commit green the day before). The
# ceiling below only guards against a starved runner — xdist workers can
# starve a freshly spawned child long past 5s (60s proved too tight once
# under peak load, observed 2026-10-10). A child that dies is detected
# immediately through its exit status instead of waiting out the ceiling.
HANDSHAKE_TIMEOUT = 300
# Ceiling for the child to exit after the parent signals release.
EXIT_TIMEOUT = 10
_POLL_SECONDS = 0.01

_LOCK_CHILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lock_child.py")


@contextlib.contextmanager
def _child_holding_flock(test, lock_path, mode):
    """Hold an flock on *lock_path* in a fresh-interpreter child.

    The child writes a marker once the lock is held and releases it when
    the parent writes the release marker (tests/python/lock_child.py,
    "flock" mode). Yields with the lock held; on exit the child must
    leave cleanly with exit status 0.
    """
    marker_dir = tempfile.mkdtemp(prefix="lockchild-")
    held_marker = os.path.join(marker_dir, "held")
    release_marker = os.path.join(marker_dir, "release")
    proc = subprocess.Popen(
        [sys.executable, _LOCK_CHILD, "flock", lock_path, mode, held_marker, release_marker],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + HANDSHAKE_TIMEOUT
        while not os.path.exists(held_marker):
            if proc.poll() is not None:
                stderr = proc.stderr.read() if proc.stderr else ""
                test.fail(f"lock child exited {proc.returncode} before holding: {stderr.strip()}")
            if time.monotonic() > deadline:
                test.fail("lock child never reported the lock held")
            time.sleep(_POLL_SECONDS)
        try:
            yield
        finally:
            # Signal release on every path out of the held section.
            if proc.poll() is None:
                with open(release_marker, "w"):
                    pass
    finally:
        if proc.poll() is None:
            try:
                proc.wait(timeout=EXIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=EXIT_TIMEOUT)
        else:
            proc.wait()
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                pipe.close()
        shutil.rmtree(marker_dir, ignore_errors=True)
    test.assertEqual(proc.returncode, 0, "lock child exited uncleanly")


class TestLockPathDefaults(unittest.TestCase):
    """Default lock paths live under the centralized lock directory."""

    # conftest.py redirects ZFSUTILITIES_LOCK_DIR to an isolated directory
    # for test runs, so the defaults only bind when file_locking is reloaded
    # with the overrides cleared. Only the import-time constants are
    # inspected here — no locks are created.
    _ENV_VARS = (
        "ZFSUTILITIES_LOCK_DIR",
        "ZFSUTILITIES_CONFIG_LOCK_PATH",
        "ZFSUTILITIES_HISTORY_LOCK_PATH",
        "ZFSUTILITIES_LOG_INDEX_LOCK_PATH",
        "ZFSUTILITIES_SCRUB_STATE_LOCK_PATH",
        "ZFSUTILITIES_SURFACE_STATE_LOCK_PATH",
    )

    def _expected_default_dir(self):
        return "/run/lock/zfsutilities"

    @contextlib.contextmanager
    def _defaults_bound(self):
        """Reload file_locking with the environment overrides cleared."""
        saved = {var: os.environ.get(var) for var in self._ENV_VARS}
        for var in self._ENV_VARS:
            os.environ.pop(var, None)
        try:
            yield importlib.reload(fl)
        finally:
            for var, value in saved.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value
            importlib.reload(fl)

    def test_config_lock_path_default(self):
        expected = os.path.join(self._expected_default_dir(), ".config.lock")
        with self._defaults_bound() as mod:
            self.assertEqual(mod.CONFIG_LOCK_PATH, expected)

    def test_history_lock_path_default(self):
        expected = os.path.join(self._expected_default_dir(), ".history.lock")
        with self._defaults_bound() as mod:
            self.assertEqual(mod.HISTORY_LOCK_PATH, expected)

    def test_log_index_lock_path_default(self):
        expected = os.path.join(self._expected_default_dir(), ".log_index.lock")
        with self._defaults_bound() as mod:
            self.assertEqual(mod.LOG_INDEX_LOCK_PATH, expected)

    def test_scrub_state_lock_path_default(self):
        expected = os.path.join(self._expected_default_dir(), ".scrub_state.lock")
        with self._defaults_bound() as mod:
            self.assertEqual(mod.SCRUB_STATE_LOCK_PATH, expected)


class TestEnvironmentOverrides(unittest.TestCase):
    """Lock paths can be redirected via environment variables."""

    def test_config_lock_path_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "custom.lock")
            os.environ["ZFSUTILITIES_CONFIG_LOCK_PATH"] = path
            try:
                # Reloading the module is the simplest way to verify the
                # environment-variable resolution at import time.
                import importlib

                mod = importlib.reload(fl)
                self.assertEqual(mod.CONFIG_LOCK_PATH, path)
            finally:
                del os.environ["ZFSUTILITIES_CONFIG_LOCK_PATH"]
                import importlib

                importlib.reload(fl)


class TestFileLockExclusivity(unittest.TestCase):
    """Exclusive locks block other exclusive locks."""

    def test_exclusive_lock_blocks_another_exclusive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "test.lock")
            with _child_holding_flock(self, lock_path, "ex"):
                # The lock is now held by the child process. Our attempt
                # to acquire it should time out quickly.
                with self.assertRaises(TimeoutError):
                    with fl.file_lock(lock_path, fcntl.LOCK_EX, timeout=0.2):
                        pass


class TestSharedLocksAllowConcurrentReaders(unittest.TestCase):
    """Multiple shared locks can be held at the same time."""

    def test_shared_lock_allows_another_shared(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "test.lock")
            with _child_holding_flock(self, lock_path, "sh"):
                # A second shared lock should be granted immediately.
                with fl.file_lock(lock_path, fcntl.LOCK_SH):
                    pass


class TestConvenienceContextManagers(unittest.TestCase):
    """High-level read/write helpers acquire the expected lock types."""

    def test_config_lock_write_creates_lock_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["ZFSUTILITIES_CONFIG_LOCK_PATH"] = os.path.join(tmpdir, "config.lock")
            try:
                import importlib

                mod = importlib.reload(fl)
                self.assertFalse(os.path.exists(mod.CONFIG_LOCK_PATH))
                with mod.config_lock_write():
                    self.assertTrue(os.path.exists(mod.CONFIG_LOCK_PATH))
            finally:
                del os.environ["ZFSUTILITIES_CONFIG_LOCK_PATH"]
                import importlib

                importlib.reload(fl)

    def test_history_lock_read_creates_lock_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["ZFSUTILITIES_HISTORY_LOCK_PATH"] = os.path.join(tmpdir, "history.lock")
            try:
                import importlib

                mod = importlib.reload(fl)
                self.assertFalse(os.path.exists(mod.HISTORY_LOCK_PATH))
                with mod.history_lock_read():
                    self.assertTrue(os.path.exists(mod.HISTORY_LOCK_PATH))
            finally:
                del os.environ["ZFSUTILITIES_HISTORY_LOCK_PATH"]
                import importlib

                importlib.reload(fl)


if __name__ == "__main__":
    unittest.main()
