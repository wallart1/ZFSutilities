"""Tests for runner_factory.py."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs, import_or_skip_gi, requires_gi

pytestmark = requires_gi

# runner_factory no longer imports backup_runner at module level (see
# RunnerFactory.create), so importing it here binds no GTK mocks. The
# BackupRunner class itself needs the real gi; import it unmocked.
import runner_factory as rf

backup_runner = import_or_skip_gi("backup_runner")
BackupRunner = backup_runner.BackupRunner


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


class _FakeRunner:
    """Minimal BackupRunner stand-in: start stores the completion callback."""

    def __init__(self, label):
        self.label = label
        self.running = False
        self.operation_detail = None
        self.steps = []
        self.started_callbacks = []

    def set_steps(self, steps):
        self.steps = steps

    def start(self, on_complete=None):
        if self.running:
            return
        self.running = True
        self.started_callbacks.append(on_complete)

    def finish(self, cancelled=False, rc=0):
        """Mirror BackupRunner._finish: running flips False before on_complete."""
        self.running = False
        callback = self.started_callbacks[-1]
        if callback is not None:
            callback(cancelled=cancelled, rc=rc)


class _FakeFactory:
    """Factory stand-in returning labeled fake runners."""

    def __init__(self):
        self.created = []

    def create(self, label, on_start=None):
        runner = _FakeRunner(label)
        self.created.append(runner)
        return runner


class TestDatasetActionRunnersTracker(unittest.TestCase):
    """One runner per dataset action; live runners tracked for shared surfaces."""

    def setUp(self):
        self.factory = _FakeFactory()
        self.tracker = rf.DatasetActionRunners(self.factory)

    def test_new_runner_uses_factory_with_dataset_label(self):
        runner = self.tracker.new_runner()
        self.assertIs(runner, self.factory.created[0])
        self.assertEqual(runner.label, "Dataset action")
        self.assertEqual(len(self.factory.created), 1)

    def test_unstarted_runner_is_not_tracked(self):
        self.tracker.new_runner()
        self.assertEqual(self.tracker.live_runners(), [])
        self.assertFalse(self.tracker.any_running())

    def test_start_tracks_and_completion_deregisters(self):
        runner = self.tracker.new_runner()
        runner.start(on_complete=lambda **kwargs: None)
        self.assertEqual(self.tracker.live_runners(), [runner])
        self.assertTrue(self.tracker.any_running())
        runner.finish()
        self.assertEqual(self.tracker.live_runners(), [])
        self.assertFalse(self.tracker.any_running())

    def test_chained_restart_inside_completion_keeps_runner(self):
        runner = self.tracker.new_runner()

        def _phase_one(cancelled=False, rc=None):
            runner.start(on_complete=lambda **kwargs: None)  # chained phase

        runner.start(on_complete=_phase_one)
        runner.finish()
        self.assertEqual(self.tracker.live_runners(), [runner])
        runner.finish()
        self.assertEqual(self.tracker.live_runners(), [])

    def test_cancelled_completion_deregisters(self):
        runner = self.tracker.new_runner()
        seen = {}
        runner.start(on_complete=lambda cancelled, rc=None: seen.update(cancelled=cancelled))
        runner.finish(cancelled=True)
        self.assertTrue(seen["cancelled"])
        self.assertEqual(self.tracker.live_runners(), [])

    def test_completion_callback_exception_still_deregisters(self):
        runner = self.tracker.new_runner()

        def _boom(cancelled=False, rc=None):
            raise ValueError("handler bug")

        runner.start(on_complete=_boom)
        with self.assertRaises(ValueError):
            runner.finish()
        self.assertEqual(self.tracker.live_runners(), [])

    def test_two_concurrent_runners_tracked_with_distinct_ids(self):
        one = self.tracker.new_runner()
        two = self.tracker.new_runner()
        one.start(on_complete=lambda **kwargs: None)
        two.start(on_complete=lambda **kwargs: None)
        self.assertEqual(self.tracker.live_runners(), [one, two])
        ids = [action_id for action_id, _ in self.tracker.running_entries()]
        self.assertEqual(len(ids), 2)
        self.assertNotEqual(ids[0], ids[1])
        self.assertEqual(
            sorted(id(r) for r in self.tracker.live_runners()),
            sorted(id(r) for _, r in self.tracker.running_entries()),
        )
        one.finish()
        self.assertEqual(self.tracker.live_runners(), [two])
        self.assertEqual([r for _, r in self.tracker.running_entries()], [two])

    def test_runner_by_id_resolves_and_releases(self):
        runner = self.tracker.new_runner()
        runner.start(on_complete=lambda **kwargs: None)
        (action_id, _running) = self.tracker.running_entries()[0]
        self.assertIs(self.tracker.runner_by_id(action_id), runner)
        self.assertIsNone(self.tracker.runner_by_id(999))
        runner.finish()
        self.assertIsNone(self.tracker.runner_by_id(action_id))

    def test_idle_between_chained_phases_not_in_running_entries(self):
        runner = self.tracker.new_runner()
        runner.start(on_complete=lambda **kwargs: None)
        runner.running = False  # the idle gap inside _finish, before on_complete
        self.assertEqual(self.tracker.running_entries(), [])
        self.assertEqual(self.tracker.live_runners(), [runner])


class TestNewDatasetActionRunnerHelper(unittest.TestCase):
    """The call-site helper hides the tracker lookup; no busy gate remains."""

    def test_returns_tracker_runner(self):
        app = SimpleNamespace(dataset_actions=rf.DatasetActionRunners(_FakeFactory()))
        runner = rf.new_dataset_action_runner(app)
        self.assertEqual(runner.label, "Dataset action")

    def test_missing_tracker_warns_and_returns_none(self):
        app = SimpleNamespace()
        with capture_logs() as logs:
            runner = rf.new_dataset_action_runner(app)
        self.assertIsNone(runner)
        self.assertTrue(any("WARN: Dataset runner not available" in line for line in logs), logs)


class TestFormatLockHolders(unittest.TestCase):
    """zfs_lock_manager.format_lock_holders renders holder details for WARNs."""

    def _zlm(self):
        sys.modules.pop("zfs_lock_manager", None)
        import zfs_lock_manager as zlm

        return zlm

    def test_joins_holder_fragments(self):
        zlm = self._zlm()
        holders = [
            {
                "dataset": "tank/vm-211-disk-1",
                "type": "write",
                "pid": 4242,
                "script": "zfsdailybackup",
                "acquired": "",
                "description": "daily backup",
            },
            {
                "dataset": "tank",
                "type": "destroy",
                "pid": 99,
                "script": "",
                "acquired": "2026-11-04T10:00:00",
                "description": "",
            },
        ]
        text = zlm.format_lock_holders(holders)
        self.assertIn("dataset='tank/vm-211-disk-1' type=write pid=4242", text)
        self.assertIn("script='zfsdailybackup'", text)
        self.assertIn("description='daily backup'", text)
        self.assertIn("dataset='tank' type=destroy pid=99", text)
        self.assertIn("; ", text)
        second = text.split("; ", 1)[1]
        self.assertNotIn("script=", second)

    def test_empty_holders_render_empty(self):
        zlm = self._zlm()
        self.assertEqual(zlm.format_lock_holders([]), "")


if __name__ == "__main__":
    unittest.main()
