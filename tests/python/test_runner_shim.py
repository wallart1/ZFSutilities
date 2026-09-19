"""Tests for tests/python/runner.py — the deprecated pytest forwarding shim."""

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
if TEST_DIR not in sys.path:
    sys.path.insert(0, TEST_DIR)

import runner


class TestTranslateArgs(unittest.TestCase):
    """_translate_args maps legacy runner.py arguments to pytest arguments."""

    def _assert_cases(self, cases):
        for argv, expected in cases:
            with self.subTest(argv=argv):
                self.assertEqual(runner._translate_args(argv), expected)

    def test_suite_name_maps_to_suite_file(self):
        self._assert_cases(
            [
                (
                    ["backup_config"],
                    ["tests/python/test_backup_config.py", "-x", "--tb=short", "-q"],
                ),
                (
                    ["zfs_lock_manager"],
                    ["tests/python/test_zfs_lock_manager.py", "-x", "--tb=short", "-q"],
                ),
            ]
        )

    def test_explicit_test_name_kept_as_is(self):
        self.assertEqual(
            runner._translate_args(["test_foo"]),
            ["tests/python/test_foo.py", "-x", "--tb=short", "-q"],
        )

    def test_list_and_count_map_to_collect_only(self):
        self._assert_cases(
            [
                (["--list"], ["--collect-only", "-q"]),
                (["--count"], ["--collect-only", "-q"]),
                (
                    ["--list", "backup_config"],
                    ["--collect-only", "-q", "tests/python/test_backup_config.py"],
                ),
            ]
        )

    def test_verbosity_flags(self):
        self._assert_cases(
            [
                (["-q"], ["tests/python", "-n", "auto", "-q"]),
                (["-v"], ["tests/python", "-n", "auto", "-v"]),
                (
                    ["-q", "backup_config"],
                    ["tests/python/test_backup_config.py", "-x", "--tb=short", "-q"],
                ),
                (
                    ["-v", "backup_config"],
                    ["tests/python/test_backup_config.py", "-x", "--tb=short", "-v"],
                ),
                (
                    ["-v", "-q", "backup_config"],
                    ["tests/python/test_backup_config.py", "-x", "--tb=short", "-v", "-q"],
                ),
            ]
        )

    def test_buffer_flag_is_dropped(self):
        self.assertEqual(runner._translate_args(["-b"]), ["tests/python", "-n", "auto", "-q"])

    def test_failures_only_maps_to_quiet(self):
        self.assertEqual(
            runner._translate_args(["--failures-only"]),
            ["tests/python", "-n", "auto", "-q"],
        )

    def test_unknown_flags_pass_through(self):
        self._assert_cases(
            [
                (["--random-flag"], ["tests/python", "-n", "auto", "--random-flag"]),
                (
                    ["-j4", "backup_config"],
                    ["tests/python/test_backup_config.py", "-x", "--tb=short", "-j4"],
                ),
            ]
        )

    def test_no_targets_runs_full_suite_with_xdist(self):
        self.assertEqual(runner._translate_args([]), ["tests/python", "-n", "auto", "-q"])


class TestMain(unittest.TestCase):
    """main() warns on stderr and execs pytest with the translated arguments."""

    def test_main_prints_deprecation_notice_and_execs_pytest(self):
        stderr = io.StringIO()
        with patch.object(runner.os, "execvp") as execvp:
            with redirect_stderr(stderr):
                runner.main(["backup_config"])

        self.assertIn("deprecated", stderr.getvalue())
        self.assertIn("pytest", stderr.getvalue())
        execvp.assert_called_once_with(
            "python3",
            ["python3", "-m", "pytest"] + runner._translate_args(["backup_config"]),
        )


if __name__ == "__main__":
    unittest.main()
