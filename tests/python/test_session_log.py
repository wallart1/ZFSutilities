"""Tests for session_log.py — per-run session log helpers."""

import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk, temp_config_dir

with mock_gtk():
    import log_index
    import logging_config
    import session_log as sl


class TestCreateSessionLogFile(unittest.TestCase):
    """create_session_log_file creates timestamped log files."""

    def test_creates_gui_log_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("session_log.SESSION_LOG_DIR", tmpdir):
                path = sl.create_session_log_file("Backup")
            self.assertTrue(os.path.isfile(path))
            self.assertIn("_Backup_gui.log", path)

    def test_creates_profile_log_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("session_log.SESSION_LOG_DIR", tmpdir):
                path = sl.create_session_log_file("Backup", name="Daily #1")
            self.assertTrue(os.path.isfile(path))
            self.assertIn("_Backup_profile-Daily1.log", path)

    def test_sanitizes_special_characters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("session_log.SESSION_LOG_DIR", tmpdir):
                path = sl.create_session_log_file("Offsite Run", name="pool@two")
            filename = os.path.basename(path)
            self.assertNotIn(" ", filename)
            self.assertNotIn("@", filename)
            self.assertIn("OffsiteRun", filename)
            self.assertIn("pooltwo", filename)

    def test_returns_none_on_create_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate a write failure without depending on filesystem
            # permissions, which may be ignored when running as root or on
            # certain filesystems.
            def _failing_open(*args, **kwargs):
                raise PermissionError("simulated write failure")

            with patch("session_log.SESSION_LOG_DIR", tmpdir):
                with patch("session_log.open", side_effect=_failing_open):
                    path = sl.create_session_log_file("Backup")
            self.assertIsNone(path)


class TestWriteRawLine(unittest.TestCase):
    """write_raw_line appends timestamped lines to the log file."""

    def test_appends_timestamped_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.log")
            open(path, "a").close()
            sl.write_raw_line(path, "INFO: processing")
            with open(path) as fh:
                content = fh.read()
            self.assertIn("INFO: processing", content)
            self.assertRegex(content, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_noop_when_no_file(self):
        # Should not raise.
        sl.write_raw_line(None, "INFO: ignored")


class TestWriteSessionTrailer(unittest.TestCase):
    """write_session_trailer writes the final trailer and updates the index."""

    def _log_path(self):
        os.makedirs(sl.SESSION_LOG_DIR, exist_ok=True)
        return os.path.join(sl.SESSION_LOG_DIR, "2026-06-22_07-00-00_backup_x.log")

    def test_writes_rc_trailer(self):
        with temp_config_dir():
            path = self._log_path()
            open(path, "a").close()
            start = time.time() - 10.0
            sl.write_session_trailer(path, start, rc=0)
            with open(path) as fh:
                content = fh.read()
        self.assertIn("# END: rc=0, duration=10.0s", content)

    def test_writes_cancelled_trailer(self):
        with temp_config_dir():
            path = self._log_path()
            open(path, "a").close()
            sl.write_session_trailer(path, time.time(), cancelled=True)
            with open(path) as fh:
                content = fh.read()
        self.assertIn("# END: cancelled", content)

    def test_writes_bytes_transferred(self):
        with temp_config_dir():
            path = self._log_path()
            open(path, "a").close()
            sl.write_session_trailer(path, time.time(), rc=0, bytes_transferred=1234)
            with open(path) as fh:
                content = fh.read()
        self.assertIn("bytes=1234", content)

    def test_persists_done_to_index(self):
        with temp_config_dir():
            path = self._log_path()
            open(path, "a").close()
            sl.write_session_trailer(path, time.time(), rc=0, bytes_transferred=5678)
            entry = log_index.LogIndex.load().get(path)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "Done")
        self.assertEqual(entry["bytes_transferred"], 5678)

    def test_persists_failed_to_index(self):
        with temp_config_dir():
            path = self._log_path()
            open(path, "a").close()
            sl.write_session_trailer(path, time.time(), rc=1)
            entry = log_index.LogIndex.load().get(path)
        self.assertEqual(entry["status"], "Failed")

    def test_persists_cancelled_to_index(self):
        with temp_config_dir():
            path = self._log_path()
            open(path, "a").close()
            sl.write_session_trailer(path, time.time(), cancelled=True)
            entry = log_index.LogIndex.load().get(path)
        self.assertEqual(entry["status"], "Cancelled")

    def test_noop_when_no_file(self):
        sl.write_session_trailer(None, time.time(), rc=0)


class TestMaybeTruncateSessionLog(unittest.TestCase):
    """maybe_truncate_session_log enforces the session-log size cap."""

    def test_returns_false_when_interval_not_elapsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "small.log")
            open(path, "a").close()
            last = time.time()
            truncated, new_last = sl.maybe_truncate_session_log(path, last, interval=60)
            self.assertFalse(truncated)
            self.assertEqual(new_last, last)

    def test_resets_index_after_truncation(self):
        with temp_config_dir():
            os.makedirs(sl.SESSION_LOG_DIR, exist_ok=True)
            path = os.path.join(sl.SESSION_LOG_DIR, "huge.log")
            # Write a log larger than the small cap we patch in for the test.
            with open(path, "w") as fh:
                fh.write("line\n" * 50)
            # Pre-populate the index so we can verify it is cleared.
            idx = log_index.LogIndex.load()
            idx.set_status(path, status="Running")
            idx.save()

            with patch.object(logging_config, "_get_session_log_cap", return_value=(100, 40, 40)):
                truncated, _ = sl.maybe_truncate_session_log(path, 0.0, interval=0)
            self.assertTrue(truncated)
            self.assertLess(os.path.getsize(path), 250)
            idx = log_index.LogIndex.load()
            self.assertIsNone(idx.get(path))

    def test_noop_when_no_file(self):
        truncated, new_last = sl.maybe_truncate_session_log(None, 0.0, interval=0)
        self.assertFalse(truncated)
        self.assertEqual(new_last, 0.0)


if __name__ == "__main__":
    unittest.main()
