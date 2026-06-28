"""Tests for backup_runner.py — session logging and byte counting."""

import os
import signal
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


@contextmanager
def _patch_log_dirs(tmpdir):
    """Patch both backup_runner and log_index to use tmpdir as SESSION_LOG_DIR."""
    with patch("backup_runner.SESSION_LOG_DIR", tmpdir), \
            patch("log_index.SESSION_LOG_DIR", tmpdir):
        yield

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

# Mock GTK/WebKit so gi.repository imports succeed without a display.
from test_support import mock_gtk

import log_index as li

with mock_gtk():
    import backup_runner as br
    from command_builders import BashStep


class TestPrepareSessionLog(unittest.TestCase):
    """prepare_session_log() creates the file and manages the environment."""

    def _runner(self):
        return br.BackupRunner(MagicMock(), MagicMock())

    def test_creates_file_and_sets_env(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backup_runner.SESSION_LOG_DIR", tmpdir):
                runner.prepare_session_log()
                self.assertIsNotNone(runner._session_log_file)
                self.assertTrue(os.path.isfile(runner._session_log_file))
                self.assertEqual(
                    os.environ.get("ZFSUTILITIES_LOG_FILE"),
                    runner._session_log_file,
                )

    def test_idempotent(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backup_runner.SESSION_LOG_DIR", tmpdir):
                runner.prepare_session_log()
                first_file = runner._session_log_file
                runner.prepare_session_log()
                self.assertEqual(runner._session_log_file, first_file)

    def test_preserves_previous_log_file(self):
        runner = self._runner()
        previous = os.path.join(tempfile.gettempdir(), "previous.log")
        os.environ["ZFSUTILITIES_LOG_FILE"] = previous
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with _patch_log_dirs(tmpdir):
                    runner.prepare_session_log()
                    self.assertEqual(runner._session_log_prev[0], previous)
                    runner.cancel()
                    self.assertEqual(os.environ.get("ZFSUTILITIES_LOG_FILE"), previous)
        finally:
            if "ZFSUTILITIES_LOG_FILE" in os.environ:
                del os.environ["ZFSUTILITIES_LOG_FILE"]
            if "ZFSUTILITIES_LOG_INHERIT" in os.environ:
                del os.environ["ZFSUTILITIES_LOG_INHERIT"]


class TestReceivedByteCounting(unittest.TestCase):
    """Byte counting works from stderr, stdout, and drain_remaining."""

    def _runner(self):
        return br.BackupRunner(MagicMock(), MagicMock())

    def test_on_stderr_parses_received_line(self):
        runner = self._runner()
        runner._total_bytes_received = 0
        with patch("os.read", return_value=b"received 312B stream in 0.12 seconds"):
            result = runner._on_stderr(0, br.GLib.IOCondition.IN)
        self.assertEqual(runner._total_bytes_received, 312)
        self.assertTrue(result)

    def test_on_stderr_parses_gib_size(self):
        runner = self._runner()
        runner._total_bytes_received = 0
        with patch("os.read", return_value=b"received 2GiB stream in 5.00 seconds"):
            runner._on_stderr(0, br.GLib.IOCondition.IN)
        self.assertEqual(runner._total_bytes_received, 2 * 1024 ** 3)

    def test_on_stderr_parses_bare_m_size(self):
        """Bare 'M' suffix from zfs receive must be counted (regression)."""
        runner = self._runner()
        runner._total_bytes_received = 0
        with patch("os.read", return_value=b"received 319M stream in 8.46 seconds"):
            runner._on_stderr(0, br.GLib.IOCondition.IN)
        self.assertEqual(runner._total_bytes_received, 319 * 1000 ** 2)

    def test_on_stdout_parses_received_line(self):
        runner = self._runner()
        runner._total_bytes_received = 0
        with patch("os.read", return_value=b"received 1MiB stream in 1.00 seconds"):
            runner._on_stdout(0, br.GLib.IOCondition.IN)
        self.assertEqual(runner._total_bytes_received, 1024 * 1024)

    def test_drain_remaining_parses_received_line(self):
        runner = self._runner()
        runner._total_bytes_received = 0
        runner.steps = [BashStep([], "step", is_rsync=False, fatal=False)]
        fake_process = MagicMock()
        fake_process.stdout.fileno.return_value = 3
        fake_process.stdout.closed = False
        fake_process.stderr.fileno.return_value = 4
        fake_process.stderr.closed = False
        runner.process = fake_process

        stderr_calls = [0]

        def fake_read(fd, _size):
            if fd == 3:
                return b""
            if fd == 4:
                stderr_calls[0] += 1
                if stderr_calls[0] == 1:
                    return b"received 500B stream in 0.50 seconds"
                return b""
            return b""

        with patch("os.read", side_effect=fake_read):
            runner._drain_remaining()
        self.assertEqual(runner._total_bytes_received, 500)

    def test_pv_rate_lines_not_counted(self):
        runner = self._runner()
        runner._total_bytes_received = 0
        pv_line = b" 100MiB 0:00:05 [20MiB/s] [===================>] 100%"
        with patch("os.read", return_value=pv_line):
            runner._on_stderr(0, br.GLib.IOCondition.IN)
        self.assertEqual(runner._total_bytes_received, 0)


class TestAbortHandling(unittest.TestCase):
    """Operation-abort exit code (9) stops the runner cleanly."""

    def _runner(self):
        return br.BackupRunner(MagicMock(), MagicMock())

    def test_rc_nine_aborts_operation(self):
        runner = self._runner()
        on_complete = MagicMock()
        runner._on_complete = on_complete
        runner.running = True
        runner.steps = [BashStep([], "step1", is_rsync=False, fatal=False)]
        runner._finally_step = None
        runner._session_start_time = time.time()
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()

                fake_process = MagicMock()
                fake_process.poll.return_value = 9
                fake_process.stdout.fileno.return_value = 3
                fake_process.stdout.closed = True
                fake_process.stderr.fileno.return_value = 4
                fake_process.stderr.closed = True
                runner.process = fake_process

                runner._check_process()

        self.assertFalse(runner.running)
        on_complete.assert_called_once_with(cancelled=True)

    def test_cancel_sends_sigint_during_lock_wait(self):
        runner = self._runner()
        runner.running = True
        runner._in_lock_wait = True
        fake_process = MagicMock()
        fake_process.poll.return_value = None
        runner.process = fake_process
        runner.cancel()
        fake_process.send_signal.assert_called_once_with(signal.SIGINT)
        fake_process.terminate.assert_not_called()
        self.assertTrue(runner.running)

    def test_cancel_terminates_when_not_in_lock_wait(self):
        runner = self._runner()
        on_complete = MagicMock()
        runner._on_complete = on_complete
        runner.running = True
        runner._in_lock_wait = False
        fake_process = MagicMock()
        fake_process.poll.return_value = None
        runner.process = fake_process
        runner.cancel()
        fake_process.terminate.assert_called_once()
        fake_process.send_signal.assert_not_called()
        self.assertFalse(runner.running)
        on_complete.assert_called_once_with(cancelled=True)

    @patch("backup_runner.add_history_entry")
    def test_fatal_pre_backup_command_logs_abort_message(self, _mock_add):
        runner = self._runner()
        runner.label = "Backup"
        runner.running = True
        runner.current_step = 0
        runner._session_start_time = time.time()
        runner.steps = [
            BashStep([], "Pre-backup command", is_rsync=False, fatal=True)
        ]
        runner._on_complete = MagicMock()
        fake_process = MagicMock()
        fake_process.poll.return_value = 1
        fake_process.stdout.fileno.return_value = 3
        fake_process.stdout.closed = True
        fake_process.stderr.fileno.return_value = 4
        fake_process.stderr.closed = True
        runner.process = fake_process

        with patch.object(runner, "_log") as mock_log:
            runner._check_process()

        mock_log.assert_any_call(
            "FATAL: Aborting backup because pre-backup command failed"
        )


class TestHistoryEntry(unittest.TestCase):
    """History entries record the session log path."""

    def _runner(self):
        return br.BackupRunner(MagicMock(), MagicMock())

    @patch("backup_runner.add_history_entry")
    def test_finish_includes_log_file(self, mock_add):
        runner = self._runner()
        runner.label = "Backup"
        runner._total_bytes_received = 0
        runner._session_start_time = time.time()
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                log_path = runner._session_log_file
                runner._finish(rc=0)
        mock_add.assert_called_once()
        entry = mock_add.call_args[0][0]
        self.assertEqual(entry.get("log_file"), log_path)

    @patch("backup_runner.add_history_entry")
    def test_finish_omits_log_file_when_unset(self, mock_add):
        runner = self._runner()
        runner.label = "Backup"
        runner._total_bytes_received = 0
        runner._session_start_time = time.time()
        runner._session_log_file = None
        runner._finish(rc=0)
        mock_add.assert_called_once()
        entry = mock_add.call_args[0][0]
        self.assertNotIn("log_file", entry)


class TestSessionTrailer(unittest.TestCase):
    """Trailer lines are written to the session log file."""

    def _runner(self):
        return br.BackupRunner(MagicMock(), MagicMock())

    def test_trailer_includes_bytes(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                runner._session_start_time = time.time()
                runner._write_session_trailer(rc=0, bytes_transferred=1234)
                with open(runner._session_log_file) as fh:
                    content = fh.read()
        self.assertIn("# END: rc=0", content)
        self.assertIn("bytes=1234", content)

    def test_trailer_omits_bytes_when_zero(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                runner._session_start_time = time.time()
                runner._write_session_trailer(rc=0, bytes_transferred=0)
                with open(runner._session_log_file) as fh:
                    content = fh.read()
        self.assertIn("# END: rc=0", content)
        self.assertNotIn("bytes=", content)

    def test_trailer_persists_done_to_log_index(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                runner._session_start_time = time.time()
                runner._write_session_trailer(rc=0, bytes_transferred=1234)

                import log_index as li
                index = li.LogIndex.load()
                entry = index.get(runner._session_log_file)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "Done")
        self.assertEqual(entry["bytes_transferred"], 1234)
        self.assertIsNotNone(entry["duration"])

    def test_trailer_persists_failed_to_log_index(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                runner._session_start_time = time.time()
                runner._write_session_trailer(rc=1)

                import log_index as li
                index = li.LogIndex.load()
                entry = index.get(runner._session_log_file)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "Failed")

    def test_trailer_persists_cancelled_to_log_index(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                runner._session_start_time = time.time()
                runner._write_session_trailer(rc=None, cancelled=True)

                import log_index as li
                index = li.LogIndex.load()
                entry = index.get(runner._session_log_file)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "Cancelled")


class TestSessionLogReuse(unittest.TestCase):
    """Each run must get its own session log file."""

    def _runner(self):
        return br.BackupRunner(MagicMock(), MagicMock())

    @patch("backup_runner.add_history_entry")
    @patch("backup_runner.datetime")
    def test_finish_resets_session_log_file(self, mock_datetime, _mock_add):
        from datetime import datetime as _datetime
        call_times = [
            _datetime(2026, 6, 27, 22, 22, 41),
            _datetime(2026, 6, 27, 22, 22, 41),
            _datetime(2026, 6, 27, 22, 26, 35),
        ]
        mock_datetime.now.side_effect = call_times

        runner = self._runner()
        runner.label = "Prune"
        runner._total_bytes_received = 0
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                first_path = runner._session_log_file
                runner._session_start_time = time.time()
                runner._finish(rc=0)

                # After _finish the runner should be ready for a new run.
                self.assertIsNone(runner._session_log_file)
                self.assertIsNone(runner._session_start_time)

                runner.prepare_session_log()
                second_path = runner._session_log_file

                self.assertIsNotNone(first_path)
                self.assertIsNotNone(second_path)
                self.assertNotEqual(first_path, second_path)

                # The first run's file has its END trailer; the second file
                # was created fresh and has not been finished yet.
                with open(first_path, "r", encoding="utf-8") as fh:
                    first_content = fh.read()
                with open(second_path, "r", encoding="utf-8") as fh:
                    second_content = fh.read()
                self.assertEqual(first_content.count("# END:"), 1)
                self.assertEqual(second_content.count("# END:"), 0)

    @patch("backup_runner.datetime")
    def test_cancel_clears_session_log_file(self, mock_datetime):
        from datetime import datetime as _datetime
        mock_datetime.now.side_effect = [
            _datetime(2026, 6, 27, 22, 30, 0),
            _datetime(2026, 6, 27, 22, 30, 0),
            _datetime(2026, 6, 27, 22, 31, 0),
        ]

        runner = self._runner()
        runner.label = "Backup"
        runner.running = True
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                first_path = runner._session_log_file
                runner.cancel()

                self.assertIsNone(runner._session_log_file)
                self.assertIsNone(runner._session_start_time)

                runner.running = True
                runner.prepare_session_log()
                second_path = runner._session_log_file

                self.assertIsNotNone(second_path)
                self.assertNotEqual(first_path, second_path)


class TestSessionLogSizeCap(unittest.TestCase):
    """_maybe_truncate_session_log caps the shared log and resets the index."""

    def _runner(self):
        return br.BackupRunner(MagicMock(), MagicMock())

    def test_noop_when_no_session_log(self):
        runner = self._runner()
        with patch("backup_runner.truncate_session_log") as mock_truncate:
            runner._maybe_truncate_session_log()
        mock_truncate.assert_not_called()

    def test_truncate_and_index_reset(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_log_dirs(tmpdir):
                runner.prepare_session_log()
                path = runner._session_log_file
                # Seed the index with an entry for this log.
                index = li.LogIndex.load()
                index.update(path)
                index.save()

                with patch("backup_runner.truncate_session_log", return_value=True) as mock_truncate:
                    runner._maybe_truncate_session_log()

                mock_truncate.assert_called_once_with(path)
                index2 = li.LogIndex.load()
                self.assertIsNone(index2.get(path))


if __name__ == "__main__":
    unittest.main()
