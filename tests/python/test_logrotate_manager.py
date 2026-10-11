"""Tests for logrotate_manager.py — the logrotate drop-in for persistent logs."""

import os
import tempfile
import unittest

import logrotate_manager
from test_support import capture_logs


def _paths_cfg(**overrides):
    """Return a complete paths section with test-friendly defaults."""
    cfg = {
        "cron_log": "/var/log/zfsutilities/cron.log",
        "scrub_manager_log": "/var/log/zfsutilities/scrub-manager.log",
        "logrotate_file": "/etc/logrotate.d/zfsutilities",
    }
    cfg.update(overrides)
    return cfg


class TestBuildLogrotateContent(unittest.TestCase):
    def test_contains_stanza_per_configured_log(self):
        content = logrotate_manager.build_logrotate_content(_paths_cfg())
        for path in (
            "/var/log/zfsutilities/cron.log",
            "/var/log/zfsutilities/scrub-manager.log",
        ):
            self.assertIn(f"{path} {{", content)

    def test_rotation_policy_directives(self):
        content = logrotate_manager.build_logrotate_content(_paths_cfg())
        for directive in (
            "weekly",
            "rotate 8",
            "maxsize 100M",
            "missingok",
            "notifempty",
            "compress",
            "create 0644 root root",
        ):
            self.assertIn(directive, content)
        # Compression is enabled: the GUI viewer reads .gz rotations directly,
        # so nothing disables it.
        self.assertNotIn("nocompress", content)

    def test_configured_paths_are_honored(self):
        content = logrotate_manager.build_logrotate_content(
            _paths_cfg(cron_log="/srv/site/cron-output.log")
        )
        self.assertIn("/srv/site/cron-output.log {", content)
        self.assertNotIn("/var/log/zfsutilities/cron.log", content)


class TestWriteLogrotateFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.target = os.path.join(self.tmpdir.name, "logrotate.d", "zfsutilities")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_writes_file_with_configured_target(self):
        logrotate_manager.write_logrotate_file(_paths_cfg(logrotate_file=self.target))
        self.assertTrue(os.path.isfile(self.target))
        with open(self.target) as f:
            content = f.read()
        self.assertIn("compress", content)
        mode = os.stat(self.target).st_mode & 0o777
        self.assertEqual(mode, 0o644)

    def test_success_logs_verb(self):
        with capture_logs() as logs:
            logrotate_manager.write_logrotate_file(_paths_cfg(logrotate_file=self.target))
        # capture_logs lines carry a file:line prefix — match by containment.
        self.assertTrue(any(f"VERB: Logrotate file updated: {self.target}" in m for m in logs))

    def test_write_failure_logs_fatal_and_raises(self):
        # A file where the drop-in's parent directory should be: the
        # makedirs inside write_logrotate_file fails with OSError.
        blocker = os.path.join(self.tmpdir.name, "blocker")
        with open(blocker, "w"):
            pass
        bad_target = os.path.join(blocker, "logrotate.d", "zfsutilities")
        with capture_logs() as logs:
            with self.assertRaises(OSError):
                logrotate_manager.write_logrotate_file(_paths_cfg(logrotate_file=bad_target))
        self.assertTrue(
            any(f"FATAL: Could not write logrotate file {bad_target}" in m for m in logs)
        )


if __name__ == "__main__":
    unittest.main()
