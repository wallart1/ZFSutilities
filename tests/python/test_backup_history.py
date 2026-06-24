"""Tests for backup_history.py — history storage, parsing, and queries."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

import backup_history


class TestParseHumanSize(unittest.TestCase):

    def test_bytes(self):
        self.assertEqual(backup_history._parse_human_size("312B"), 312)

    def test_kib(self):
        self.assertEqual(backup_history._parse_human_size("1KiB"), 1024)

    def test_kb(self):
        self.assertEqual(backup_history._parse_human_size("1KB"), 1000)

    def test_mib(self):
        self.assertEqual(backup_history._parse_human_size("1.5MiB"), int(1.5 * 1024 ** 2))

    def test_gb(self):
        self.assertEqual(backup_history._parse_human_size("2GB"), 2 * 1000 ** 3)

    def test_gib(self):
        self.assertEqual(backup_history._parse_human_size("2GiB"), 2 * 1024 ** 3)

    def test_tb(self):
        self.assertEqual(backup_history._parse_human_size("3TB"), 3 * 1000 ** 4)

    def test_bare_m(self):
        self.assertEqual(backup_history._parse_human_size("319M"), 319 * 1000 ** 2)

    def test_bare_g_with_decimal(self):
        self.assertEqual(
            backup_history._parse_human_size("11.2G"), int(11.2 * 1000 ** 3)
        )

    def test_bare_k_with_decimal(self):
        self.assertEqual(backup_history._parse_human_size("5.2K"), 5200)

    def test_empty_and_invalid(self):
        self.assertEqual(backup_history._parse_human_size(""), 0)
        self.assertEqual(backup_history._parse_human_size("hello"), 0)
        self.assertEqual(backup_history._parse_human_size(None), 0)


class TestFormatDuration(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(backup_history.format_duration(0), "00:00:00")

    def test_seconds_only(self):
        self.assertEqual(backup_history.format_duration(45), "00:00:45")

    def test_minutes_and_seconds(self):
        self.assertEqual(backup_history.format_duration(61.5), "00:01:02")

    def test_hours_minutes_seconds(self):
        self.assertEqual(backup_history.format_duration(3665.0), "01:01:05")

    def test_negative_falls_back_to_zero(self):
        self.assertEqual(backup_history.format_duration(-5), "00:00:00")

    def test_none_falls_back_to_zero(self):
        self.assertEqual(backup_history.format_duration(None), "00:00:00")


class TestLoadSaveHistory(unittest.TestCase):

    def setUp(self):
        self._orig_path = backup_history.HISTORY_PATH
        self._tmp_dir = tempfile.TemporaryDirectory()
        backup_history.HISTORY_PATH = os.path.join(
            self._tmp_dir.name, "test-history.json"
        )

    def tearDown(self):
        backup_history.HISTORY_PATH = self._orig_path
        self._tmp_dir.cleanup()

    def test_load_missing_file_returns_empty_list(self):
        self.assertEqual(backup_history.load_history(), [])

    def test_load_corrupt_file_returns_empty_list(self):
        with open(backup_history.HISTORY_PATH, "w") as fh:
            fh.write("not json")
        self.assertEqual(backup_history.load_history(), [])

    def test_save_and_load_roundtrip(self):
        entries = [
            {"timestamp": "2026-05-20T12:00:00", "type": "backup", "name": "Daily"},
        ]
        backup_history.save_history(entries)
        loaded = backup_history.load_history()
        self.assertEqual(loaded, entries)

    def test_atomic_save_does_not_leave_temp_file(self):
        backup_history.save_history([])
        temp_files = [
            f for f in os.listdir(self._tmp_dir.name)
            if f.startswith(".")
        ]
        self.assertEqual(temp_files, [])


class TestPruneHistory(unittest.TestCase):

    def _make_entry(self, days_ago):
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        return {"timestamp": ts, "type": "backup", "name": "Daily"}

    def test_prune_removes_old_entries(self):
        entries = [
            self._make_entry(0),
            self._make_entry(10),
            self._make_entry(100),
        ]
        pruned = backup_history.prune_history(entries, days=30)
        self.assertEqual(len(pruned), 2)

    def test_prune_zero_days_keeps_all(self):
        entries = [self._make_entry(365)]
        pruned = backup_history.prune_history(entries, days=0)
        self.assertEqual(len(pruned), 1)

    def test_prune_preserves_order(self):
        entries = [
            self._make_entry(5),
            self._make_entry(1),
            self._make_entry(10),
        ]
        pruned = backup_history.prune_history(entries, days=7)
        self.assertEqual(len(pruned), 2)
        self.assertEqual(pruned[0]["timestamp"], entries[0]["timestamp"])

    def test_prune_keeps_unparseable_timestamp(self):
        entries = [{"timestamp": "bad", "type": "backup"}]
        pruned = backup_history.prune_history(entries, days=1)
        self.assertEqual(len(pruned), 1)


class TestSuccessRate(unittest.TestCase):

    def _make_entry(self, result, days_ago=0):
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        return {"timestamp": ts, "type": "backup", "result": result}

    def test_no_entries(self):
        self.assertEqual(backup_history.get_success_rate([], 30), (0, 0, 0))

    def test_all_success(self):
        entries = [
            self._make_entry("success", 1),
            self._make_entry("success", 2),
        ]
        self.assertEqual(backup_history.get_success_rate(entries, 30), (2, 2, 100))

    def test_mixed_results(self):
        entries = [
            self._make_entry("success", 1),
            self._make_entry("failed", 2),
            self._make_entry("success", 3),
            self._make_entry("cancelled", 4),
        ]
        self.assertEqual(backup_history.get_success_rate(entries, 30), (2, 4, 50))

    def test_old_entries_excluded(self):
        entries = [
            self._make_entry("success", 1),
            self._make_entry("failed", 100),
        ]
        self.assertEqual(backup_history.get_success_rate(entries, 30), (1, 1, 100))


class TestAddHistoryEntry(unittest.TestCase):

    def setUp(self):
        self._orig_path = backup_history.HISTORY_PATH
        self._tmp_dir = tempfile.TemporaryDirectory()
        backup_history.HISTORY_PATH = os.path.join(
            self._tmp_dir.name, "test-history.json"
        )

    def tearDown(self):
        backup_history.HISTORY_PATH = self._orig_path
        self._tmp_dir.cleanup()

    def test_adds_entry_to_front(self):
        entry = backup_history.build_entry(
            timestamp="2026-05-20T12:00:00",
            run_type="backup",
            name="Daily",
            duration=60.0,
            result="success",
            bytes_transferred=1024,
        )
        backup_history.add_history_entry(entry)
        loaded = backup_history.load_history()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["name"], "Daily")

    def test_auto_prunes_on_add(self):
        old_entry = backup_history.build_entry(
            timestamp=(datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
            run_type="backup",
            name="Old",
            duration=10.0,
            result="success",
        )
        backup_history.save_history([old_entry])
        new_entry = backup_history.build_entry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_type="backup",
            name="New",
            duration=10.0,
            result="success",
        )
        backup_history.add_history_entry(new_entry)
        loaded = backup_history.load_history()
        names = [e["name"] for e in loaded]
        self.assertNotIn("Old", names)
        self.assertIn("New", names)


class TestBuildEntry(unittest.TestCase):

    def test_schema(self):
        entry = backup_history.build_entry(
            timestamp="2026-05-20T12:00:00",
            run_type="backup",
            name="Daily",
            duration=123.4,
            result="success",
            bytes_transferred=4096,
        )
        self.assertEqual(entry["timestamp"], "2026-05-20T12:00:00")
        self.assertEqual(entry["type"], "backup")
        self.assertEqual(entry["name"], "Daily")
        self.assertEqual(entry["duration"], 123.4)
        self.assertEqual(entry["result"], "success")
        self.assertEqual(entry["bytes_transferred"], 4096)

    def test_default_bytes(self):
        entry = backup_history.build_entry(
            timestamp="2026-05-20T12:00:00",
            run_type="prune",
            name="Weekly",
            duration=5.0,
            result="success",
        )
        self.assertEqual(entry["bytes_transferred"], 0)

    def test_log_file_optional(self):
        entry = backup_history.build_entry(
            timestamp="2026-05-20T12:00:00",
            run_type="backup",
            name="Daily",
            duration=5.0,
            result="success",
            log_file="/var/log/zfsutilities/sessions/test.log",
        )
        self.assertEqual(entry["log_file"], "/var/log/zfsutilities/sessions/test.log")

    def test_log_file_omitted_when_none(self):
        entry = backup_history.build_entry(
            timestamp="2026-05-20T12:00:00",
            run_type="backup",
            name="Daily",
            duration=5.0,
            result="success",
        )
        self.assertNotIn("log_file", entry)

    def test_log_file_omitted_when_empty(self):
        entry = backup_history.build_entry(
            timestamp="2026-05-20T12:00:00",
            run_type="backup",
            name="Daily",
            duration=5.0,
            result="success",
            log_file="",
        )
        self.assertNotIn("log_file", entry)


if __name__ == "__main__":
    unittest.main()
