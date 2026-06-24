"""Tests for runner_factory.py."""

import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk

with mock_gtk():
    import runner_factory as rf
    from backup_runner import BackupRunner


class TestRunnerFactory(unittest.TestCase):
    """RunnerFactory creates BackupRunner instances with shared callbacks."""

    def _factory(self):
        log_func = MagicMock()
        set_stdin = MagicMock()
        progress = MagicMock()
        return rf.RunnerFactory(log_func, set_stdin, progress), log_func, set_stdin, progress

    def test_create_returns_backup_runner(self):
        factory, _, _, _ = self._factory()
        runner = factory.create("Backup")
        self.assertIsInstance(runner, BackupRunner)

    def test_create_sets_label(self):
        factory, _, _, _ = self._factory()
        runner = factory.create("Offsite backup")
        self.assertEqual(runner.label, "Offsite backup")

    def test_create_passes_callables(self):
        factory, log_func, set_stdin, progress = self._factory()
        runner = factory.create("Restore")
        self.assertIs(runner.log, log_func)
        self.assertIs(runner.set_stdin_enabled, set_stdin)
        self.assertIs(runner.progress, progress)

    def test_create_passes_on_start(self):
        factory, _, _, _ = self._factory()
        on_start = MagicMock()
        runner = factory.create("Prune", on_start=on_start)
        self.assertIs(runner.on_start, on_start)
