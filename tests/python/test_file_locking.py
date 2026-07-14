"""Tests for file_locking.py — advisory flock helpers."""

import fcntl
import multiprocessing
import os
import tempfile
import time
import unittest

import file_locking as fl


class TestLockPathDefaults(unittest.TestCase):
    """Default lock paths are root-owned for root, user-writable otherwise."""

    def _expected_default_dir(self):
        if os.geteuid() == 0:
            return "/run/lock/zfs"
        return os.path.expanduser("~/.cache/zfsutilities")

    def test_config_lock_path_default(self):
        expected = os.path.join(self._expected_default_dir(), ".config.lock")
        self.assertEqual(fl.CONFIG_LOCK_PATH, expected)

    def test_history_lock_path_default(self):
        expected = os.path.join(self._expected_default_dir(), ".history.lock")
        self.assertEqual(fl.HISTORY_LOCK_PATH, expected)

    def test_log_index_lock_path_default(self):
        expected = os.path.join(self._expected_default_dir(), ".log_index.lock")
        self.assertEqual(fl.LOG_INDEX_LOCK_PATH, expected)

    def test_scrub_state_lock_path_default(self):
        expected = os.path.join(self._expected_default_dir(), ".scrub_state.lock")
        self.assertEqual(fl.SCRUB_STATE_LOCK_PATH, expected)


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

    def _acquire_and_hold(self, lock_path, queue):
        """Helper process: acquire exclusive lock and signal, then wait."""
        import fcntl
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        queue.put("held")
        # Wait until the parent tells us to release.
        queue.get()
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    def test_exclusive_lock_blocks_another_exclusive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "test.lock")
            queue = multiprocessing.Queue()
            proc = multiprocessing.Process(
                target=self._acquire_and_hold, args=(lock_path, queue)
            )
            proc.start()
            try:
                self.assertEqual(queue.get(timeout=5), "held")
                # The lock is now held by the subprocess. Our attempt to
                # acquire it should time out quickly.
                with self.assertRaises(TimeoutError):
                    with fl.file_lock(lock_path, fcntl.LOCK_EX, timeout=0.2):
                        pass
            finally:
                queue.put("release")
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.terminate()
                    proc.join()


class TestSharedLocksAllowConcurrentReaders(unittest.TestCase):
    """Multiple shared locks can be held at the same time."""

    def _hold_shared_lock(self, lock_path, queue):
        import fcntl
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_SH)
        queue.put("held")
        queue.get()
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    def test_shared_lock_allows_another_shared(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "test.lock")
            queue = multiprocessing.Queue()
            proc = multiprocessing.Process(
                target=self._hold_shared_lock, args=(lock_path, queue)
            )
            proc.start()
            try:
                self.assertEqual(queue.get(timeout=5), "held")
                # A second shared lock should be granted immediately.
                with fl.file_lock(lock_path, fcntl.LOCK_SH):
                    pass
            finally:
                queue.put("release")
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.terminate()
                    proc.join()


class TestConvenienceContextManagers(unittest.TestCase):
    """High-level read/write helpers acquire the expected lock types."""

    def test_config_lock_write_creates_lock_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["ZFSUTILITIES_CONFIG_LOCK_PATH"] = os.path.join(
                tmpdir, "config.lock"
            )
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
            os.environ["ZFSUTILITIES_HISTORY_LOCK_PATH"] = os.path.join(
                tmpdir, "history.lock"
            )
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
