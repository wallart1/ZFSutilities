"""Tests for profile_runner.py per-profile locking."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import profile_runner
from test_support import capture_logs, temp_config_dir

# The cross-process lock holder runs as a fresh interpreter, never a
# multiprocessing fork of this worker (a forked child of a loaded
# pytest-xdist worker can deadlock before it reaches its first
# queue.put(); CI 2026-11-08..09).
_LOCK_CHILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lock_child.py")
_MARKER_POLL_SECONDS = 0.01


class TestProfileLockHelpers(unittest.TestCase):
    def setUp(self):
        self.lock_dir = tempfile.mkdtemp()
        self.orig_dir = profile_runner.PROFILE_LOCK_DIR
        profile_runner.PROFILE_LOCK_DIR = self.lock_dir

    def tearDown(self):
        profile_runner.PROFILE_LOCK_DIR = self.orig_dir

    def test_acquire_and_release(self):
        fd, lock_path = profile_runner.acquire_profile_lock("daily", timeout=0.5)
        self.assertIsNotNone(fd)
        self.assertTrue(os.path.exists(lock_path))
        profile_runner.release_profile_lock(fd, lock_path)
        self.assertFalse(os.path.exists(lock_path))

    def test_second_acquire_fails(self):
        fd1, lock_path1 = profile_runner.acquire_profile_lock("daily", timeout=0.5)
        self.assertIsNotNone(fd1)
        try:
            fd2, lock_path2 = profile_runner.acquire_profile_lock("daily", timeout=0.1)
            self.assertIsNone(fd2)
            self.assertEqual(lock_path1, lock_path2)
        finally:
            profile_runner.release_profile_lock(fd1, lock_path1)

    def test_different_profiles_can_lock(self):
        fd1, path1 = profile_runner.acquire_profile_lock("daily", timeout=0.5)
        fd2, path2 = profile_runner.acquire_profile_lock("weekly", timeout=0.5)
        self.assertIsNotNone(fd1)
        self.assertIsNotNone(fd2)
        self.assertNotEqual(path1, path2)
        profile_runner.release_profile_lock(fd1, path1)
        profile_runner.release_profile_lock(fd2, path2)

    def test_lock_file_contains_metadata(self):
        fd, lock_path = profile_runner.acquire_profile_lock("daily", timeout=0.5)
        self.assertIsNotNone(fd)
        try:
            with open(lock_path) as f:
                import json

                data = json.load(f)
            self.assertEqual(data["profile"], "daily")
            self.assertEqual(data["pid"], os.getpid())
            self.assertIn("started", data)
        finally:
            profile_runner.release_profile_lock(fd, lock_path)

    def test_lock_file_records_log_file(self):
        fd, lock_path = profile_runner.acquire_profile_lock(
            "daily", timeout=0.5, log_file="/var/log/test.log"
        )
        self.assertIsNotNone(fd)
        try:
            with open(lock_path) as f:
                import json

                data = json.load(f)
            self.assertEqual(data["log_file"], "/var/log/test.log")
        finally:
            profile_runner.release_profile_lock(fd, lock_path)

    def test_release_none_is_safe(self):
        profile_runner.release_profile_lock(None, "/nonexistent/lock")

    def test_acquire_waits_then_acquires(self):
        """A blocked acquire_profile_lock should succeed once the lock is released."""
        held_marker = os.path.join(self.lock_dir, "child-held")
        released_marker = os.path.join(self.lock_dir, "child-released")
        proc = subprocess.Popen(
            [
                sys.executable,
                _LOCK_CHILD,
                "profile-hold",
                self.lock_dir,
                "daily",
                held_marker,
                released_marker,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:

            def _await_marker(path, what):
                deadline = time.monotonic() + 2
                while not os.path.exists(path):
                    if proc.poll() is not None:
                        stderr = proc.stderr.read() if proc.stderr else ""
                        self.fail(
                            f"lock child exited {proc.returncode} before {what}: {stderr.strip()}"
                        )
                    self.assertLess(
                        time.monotonic(),
                        deadline,
                        f"lock child never reported {what}",
                    )
                    time.sleep(_MARKER_POLL_SECONDS)

            _await_marker(held_marker, "holding")
            with open(held_marker) as f:
                lock_path = f.read().strip()
            waiting_path = os.path.join(self.lock_dir, "daily.waiting")
            fd2, path2 = profile_runner.acquire_profile_lock("daily", timeout=2.0)
            self.assertIsNotNone(fd2)
            self.assertEqual(lock_path, path2)
            self.assertFalse(
                os.path.exists(waiting_path),
                "waiting file should be removed once the lock is acquired",
            )
            profile_runner.release_profile_lock(fd2, path2)
            _await_marker(released_marker, "releasing")
        finally:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=10)
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()

    def test_waiting_file_removed_on_timeout(self):
        """A blocked acquire removes its .waiting file when the timeout expires."""
        fd1, lock_path1 = profile_runner.acquire_profile_lock("daily", timeout=0.5)
        self.assertIsNotNone(fd1)
        waiting_path = os.path.join(self.lock_dir, "daily.waiting")
        try:
            fd2, _ = profile_runner.acquire_profile_lock("daily", timeout=0.1)
            self.assertIsNone(fd2)
            self.assertFalse(
                os.path.exists(waiting_path),
                "waiting file should be removed after timeout",
            )
        finally:
            profile_runner.release_profile_lock(fd1, lock_path1)


class TestMainDuplicateInvocation(unittest.TestCase):
    def setUp(self):
        self.lock_dir = tempfile.mkdtemp()
        self.orig_dir = profile_runner.PROFILE_LOCK_DIR
        profile_runner.PROFILE_LOCK_DIR = self.lock_dir

    def tearDown(self):
        profile_runner.PROFILE_LOCK_DIR = self.orig_dir

    def test_second_main_exits_zero_when_profile_running(self):
        profile = {
            "tab_type": "backup",
            "config": {"variables": {"label": "dailybackup"}},
        }
        fd, lock_path = profile_runner.acquire_profile_lock("Daily", timeout=0.5)
        self.assertIsNotNone(fd)
        try:
            with tempfile.TemporaryDirectory() as session_dir:
                with patch.object(
                    profile_runner.sys, "argv", ["profile_runner.py", "run", "Daily"]
                ):
                    with patch("profile_runner.load_profile", return_value=profile):
                        with patch("session_log.SESSION_LOG_DIR", session_dir):
                            with patch("profile_runner.load_config", return_value={}):
                                with patch("profile_runner.prune_old_logs"):
                                    with patch.object(profile_runner, "PROFILE_LOCK_TIMEOUT", 0.0):
                                        with capture_logs() as logs:
                                            with self.assertRaises(SystemExit) as cm:
                                                profile_runner.main()
            self.assertEqual(cm.exception.code, 0)
            self.assertTrue(
                any("already running" in msg for msg in logs),
                logs,
            )
        finally:
            profile_runner.release_profile_lock(fd, lock_path)

    def test_main_loads_profile_when_lock_free(self):
        profile = {
            "tab_type": "backup",
            "config": {"variables": {"label": "dailybackup"}},
        }
        with temp_config_dir():
            with patch.object(profile_runner.sys, "argv", ["profile_runner.py", "run", "Daily"]):
                with patch("profile_runner.load_profile", return_value=profile):
                    with patch("profile_runner.load_config", return_value={}):
                        with patch("profile_runner.prune_old_logs"):
                            with patch(
                                "profile_runner.run_backup_profile", return_value=0
                            ) as mock_run:
                                with patch("profile_runner.add_history_entry"):
                                    with patch("session_log.write_session_trailer"):
                                        with patch("profile_runner.sys.exit") as mock_exit:
                                            profile_runner.main()
            mock_run.assert_called_once()
            mock_exit.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
