"""Tests for profile_runner.py per-profile locking."""

import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import profile_runner
from test_support import temp_config_dir, capture_logs


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

    def test_release_none_is_safe(self):
        profile_runner.release_profile_lock(None, "/nonexistent/lock")


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
                with patch.object(profile_runner.sys, "argv", ["profile_runner.py", "run", "Daily"]):
                    with patch("profile_runner.load_profile", return_value=profile):
                        with patch("profile_runner.SESSION_LOG_DIR", session_dir):
                            with patch("profile_runner.load_config", return_value={}):
                                with patch("profile_runner.prune_old_logs"):
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
                            with patch("profile_runner.run_backup_profile", return_value=0) as mock_run:
                                with patch("profile_runner.add_history_entry"):
                                    with patch("profile_runner._write_session_trailer"):
                                        with patch("profile_runner.sys.exit") as mock_exit:
                                            profile_runner.main()
            mock_run.assert_called_once()
            mock_exit.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
