"""Tests for log_index.py — persistent session-log metadata index."""

import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_support import mock_gtk

with mock_gtk():
    import log_index as li


class TestScanFile(unittest.TestCase):

    def _write(self, tmpdir, name, content, mtime=None):
        path = os.path.join(tmpdir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_parses_trailer_and_level(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(
                tmpdir,
                "2026-06-22_07-00-00_backup_x.log",
                "2026-06-22 07:00:00  /a:1: INFO: ok\n"
                "2026-06-22 07:00:01  /a:1: WARN: host down\n"
                "# END: rc=0, duration=123.4s, bytes=1073741824\n",
            )
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path)
        self.assertEqual(entry["status"], "Done")
        self.assertEqual(entry["duration"], 123.4)
        self.assertEqual(entry["bytes_transferred"], 1073741824)
        self.assertEqual(entry["highest_level"], "WARN")
        self.assertTrue(entry["has_trailer"])

    def test_fatal_stops_level_scan_but_keeps_trailer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(
                tmpdir,
                "2026-06-22_07-00-00_backup_x.log",
                "2026-06-22 07:00:00  /a:1: FATAL: boom\n"
                "2026-06-22 07:00:01  /a:1: WARN: later\n"
                "# END: rc=1, duration=9.0s\n",
            )
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path)
        self.assertEqual(entry["highest_level"], "FATAL")
        self.assertEqual(entry["status"], "Failed")

    def test_recent_file_without_trailer_is_running(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(
                tmpdir,
                "2026-06-22_07-00-00_backup_x.log",
                "2026-06-22 07:00:00  /a:1: INFO: ok\n",
            )
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path)
        self.assertEqual(entry["status"], "Running")
        self.assertFalse(entry["has_trailer"])

    def test_old_file_without_trailer_is_done(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_mtime = time.time() - 20
            path = self._write(
                tmpdir,
                "2026-06-22_07-00-00_backup_x.log",
                "2026-06-22 07:00:00  /a:1: INFO: ok\n",
                mtime=old_mtime,
            )
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path)
        self.assertEqual(entry["status"], "Done")


class TestUpdateEntryIncrementally(unittest.TestCase):

    def test_reads_only_new_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_x.log")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("2026-06-22 07:00:00  /a:1: INFO: ok\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path)
                initial_size = entry["size"]

                # Append more content
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("2026-06-22 07:00:01  /a:1: WARN: host down\n")
                    fh.write("# END: rc=0, duration=5.0s\n")

                entry = li.update_entry_incrementally(entry, path)

        self.assertEqual(entry["highest_level"], "WARN")
        self.assertTrue(entry["has_trailer"])
        self.assertEqual(entry["duration"], 5.0)
        self.assertGreater(entry["size"], initial_size)

    def test_truncated_file_rescans_from_scratch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_x.log")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "2026-06-22 07:00:00  /a:1: INFO: ok\n"
                    "# END: rc=0, duration=1.0s\n"
                )

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path)
                self.assertTrue(entry["has_trailer"])

                # Truncate and rewrite with shorter different content
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("/a:1: FATAL: boom\n# END: rc=1, duration=2.0s\n")

                entry = li.update_entry_incrementally(entry, path)

        self.assertEqual(entry["highest_level"], "FATAL")
        self.assertEqual(entry["status"], "Failed")

    def test_partial_final_line_left_for_next_update(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_x.log")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("2026-06-22 07:00:00  /a:1: INFO: ok\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path)
                first_size = entry["size"]
                self.assertEqual(entry["highest_level"], "INFO")

                # Append an incomplete line
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("2026-06-22 07:00:01  /a:1: WARN: host do")

                entry = li.update_entry_incrementally(entry, path)
                # Size should not advance past the incomplete line
                self.assertEqual(entry["size"], first_size)
                # The incomplete WARN line is not processed yet
                self.assertEqual(entry["highest_level"], "INFO")

                # Complete the line
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("wn\n# END: rc=0, duration=1.0s\n")

                entry = li.update_entry_incrementally(entry, path)

        self.assertEqual(entry["highest_level"], "WARN")
        self.assertTrue(entry["has_trailer"])


class TestLogIndex(unittest.TestCase):

    def test_load_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                index = li.LogIndex()
                index._data = {
                    "foo.log": {
                        "size": 100,
                        "mtime": 123.0,
                        "status": "Done",
                        "duration": 1.0,
                        "bytes_transferred": None,
                        "highest_level": "WARN",
                        "has_trailer": True,
                    }
                }
                index._dirty = True
                index.save()

                loaded = li.LogIndex.load()
                self.assertEqual(loaded.get("foo.log")["status"], "Done")
                self.assertEqual(loaded.get("foo.log")["highest_level"], "WARN")

    def test_update_creates_and_increments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_x.log")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("2026-06-22 07:00:00  /a:1: INFO: ok\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                index = li.LogIndex.load()
                entry = index.update(path)
                self.assertEqual(entry["status"], "Running")

                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("# END: rc=0, duration=1.0s\n")

                entry = index.update(path)
                self.assertTrue(entry["has_trailer"])

    def test_set_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_x.log")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("2026-06-22 07:00:00  /a:1: INFO: ok\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                index = li.LogIndex.load()
                index.set_status(path, status="Done", duration=2.5, bytes_transferred=1024)
                entry = index.get(path)

        self.assertEqual(entry["status"], "Done")
        self.assertEqual(entry["duration"], 2.5)
        self.assertEqual(entry["bytes_transferred"], 1024)

    def test_remove_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                index = li.LogIndex()
                index._data = {"gone.log": {}, "keep.log": {}}
                index._dirty = False
                index.remove_missing([os.path.join(tmpdir, "keep.log")])
                self.assertNotIn("gone.log", index._data)
                self.assertIn("keep.log", index._data)
                self.assertTrue(index._dirty)

    def test_load_returns_empty_index_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                index = li.LogIndex.load()
                self.assertEqual(index._data, {})

    def test_load_recovers_from_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                with open(os.path.join(tmpdir, ".log_index.json"), "w") as fh:
                    fh.write("not json")
                with patch("log_index.log_msg") as mock_log:
                    index = li.LogIndex.load()
                self.assertEqual(index._data, {})
                mock_log.assert_called_once()
                self.assertIn("Could not load log index", mock_log.call_args[0][0])

    def test_remove_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                index = li.LogIndex()
                index._data = {"gone.log": {}}
                index._dirty = False
                index.remove(os.path.join(tmpdir, "gone.log"))
                self.assertNotIn("gone.log", index._data)
                self.assertTrue(index._dirty)

    def test_remove_missing_entry_is_noop(self):
        index = li.LogIndex()
        index._data = {"keep.log": {}}
        index._dirty = False
        index.remove("/tmp/missing.log")
        self.assertEqual(index._data, {"keep.log": {}})
        self.assertFalse(index._dirty)

    def test_save_is_noop_when_not_dirty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                index = li.LogIndex()
                index._data = {"foo.log": {}}
                index._dirty = False
                index.save()
                self.assertFalse(
                    os.path.exists(os.path.join(tmpdir, ".log_index.json"))
                )

    def test_save_is_noop_when_session_log_dir_missing(self):
        missing_dir = "/nonexistent/zfsutilities/sessions"
        with patch("log_index.SESSION_LOG_DIR", missing_dir):
            index = li.LogIndex()
            index._set("foo.log", li._empty_entry())
            # Should not raise and should not write a file.
            index.save()

    def test_set_status_overwrites_existing_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_x.log")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("2026-06-22 07:00:00  /a:1: INFO: ok\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                index = li.LogIndex.load()
                index.set_status(path, status="Done", duration=1.0)
                index.set_status(path, status="Failed", duration=2.0, bytes_transferred=2048)
                entry = index.get(path)

        self.assertEqual(entry["status"], "Failed")
        self.assertEqual(entry["duration"], 2.0)
        self.assertEqual(entry["bytes_transferred"], 2048)

    def test_large_file_scans_tail_for_trailer(self):
        """scan_file must not read the whole file; tail scan finds trailer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "big.log")
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(200):
                    fh.write(f"2026-06-22 07:00:{i:02d}  /a:1: INFO: line {i}\n")
                fh.write("2026-06-22 07:03:20  /a:1: WARN: near end\n")
                fh.write("# END: rc=0, duration=123.4s, bytes=1073741824\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                # Force tail-only scan with a small window.
                entry = li.scan_file(path, max_tail_bytes=200)

        self.assertEqual(entry["status"], "Done")
        self.assertEqual(entry["duration"], 123.4)
        self.assertEqual(entry["bytes_transferred"], 1073741824)
        self.assertTrue(entry["has_trailer"])

    def test_large_file_without_trailer_recent_is_running(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "big_running.log")
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(200):
                    fh.write(f"2026-06-22 07:00:{i:02d}  /a:1: INFO: line {i}\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path, max_tail_bytes=200)

        self.assertEqual(entry["status"], "Running")
        self.assertFalse(entry["has_trailer"])

    def test_large_file_highest_level_from_tail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "big.log")
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(200):
                    fh.write(f"2026-06-22 07:00:{i:02d}  /a:1: INFO: line {i}\n")
                fh.write("2026-06-22 07:03:20  /a:1: FATAL: near end\n")
                fh.write("# END: rc=1, duration=1.0s\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path, max_tail_bytes=200)

        self.assertEqual(entry["highest_level"], "FATAL")
        self.assertEqual(entry["status"], "Failed")

    def test_scan_file_returns_defaults_when_missing(self):
        entry = li.scan_file("/tmp/does-not-exist.log")
        self.assertEqual(entry["size"], 0)
        self.assertEqual(entry["status"], "Done")
        self.assertFalse(entry["has_trailer"])

    def test_update_entry_incrementally_no_size_change_updates_mtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_x.log")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("2026-06-22 07:00:00  /a:1: INFO: ok\n")

            with patch("log_index.SESSION_LOG_DIR", tmpdir):
                entry = li.scan_file(path)
                original_size = entry["size"]
                original_mtime = entry["mtime"]
                # Ensure mtime will differ.
                time.sleep(0.05)
                os.utime(path, None)
                entry = li.update_entry_incrementally(entry, path)

        self.assertEqual(entry["size"], original_size)
        self.assertNotEqual(entry["mtime"], original_mtime)


class TestParseLines(unittest.TestCase):

    def test_empty_text_returns_no_lines(self):
        lines, consumed = li._parse_lines("")
        self.assertEqual(lines, [])
        self.assertEqual(consumed, 0)

    def test_no_newline_returns_no_lines(self):
        lines, consumed = li._parse_lines("no newline")
        self.assertEqual(lines, [])
        self.assertEqual(consumed, 0)

    def test_splits_on_newlines_and_counts_consumed(self):
        text = "line one\nline two\npartial"
        lines, consumed = li._parse_lines(text)
        self.assertEqual(lines, ["line one", "line two"])
        # consumed includes the trailing newline after the last complete line.
        self.assertEqual(consumed, len("line one\nline two\n"))

    def test_trailing_fragment_preserved(self):
        text = "complete line\nincomplete"
        lines, consumed = li._parse_lines(text)
        self.assertEqual(lines, ["complete line"])
        self.assertEqual(consumed, len("complete line\n"))


if __name__ == "__main__":
    unittest.main()
