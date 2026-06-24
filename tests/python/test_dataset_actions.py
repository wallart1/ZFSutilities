"""Tests for dataset_actions.py — dataset destruction via BackupRunner."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk
from command_builders import BashStep


_MISSING_RUNNER = object()


def _make_app(runner=_MISSING_RUNNER, parent_dir="/repo"):
    """Return a minimal app mock with a dataset runner and repository."""
    app = MagicMock()
    app.parent_dir = parent_dir
    if runner is _MISSING_RUNNER:
        app.dataset_runner = MagicMock()
        app.dataset_runner.running = False
    else:
        app.dataset_runner = runner
    app.ctx.zfs_repository.list_all_snapshot_names.return_value = []
    app.ctx.zfs_repository.list_holds.return_value = []
    app.ctx.zfs_repository.get_recursive_snapshot_clones.return_value = []
    return app


def _patch_module():
    """Patch the external dependencies of dataset_actions._delete_datasets."""
    return patch.multiple(
        "dataset_actions",
        create_dialog=MagicMock(),
        add_scrolled_text_view=MagicMock(),
        refresh_datasets_page=MagicMock(),
        log_msg=MagicMock(),
    )


def _configure_dialog_ok(module):
    """Make the module's create_dialog return OK."""
    dialog = MagicMock()
    dialog.return_value.run.return_value = module.Gtk.ResponseType.OK
    module.create_dialog = dialog


def _configure_dialog_cancel(module):
    """Make the module's create_dialog return CANCEL."""
    dialog = MagicMock()
    dialog.return_value.run.return_value = module.Gtk.ResponseType.CANCEL
    module.create_dialog = dialog


class TestDeleteDatasetsRunner(unittest.TestCase):
    """_delete_datasets delegates to app.dataset_runner via BashStep."""

    def _import_under_mock(self):
        with mock_gtk():
            import dataset_actions as da
            return da

    def test_builds_bash_steps_per_dataset(self):
        da = self._import_under_mock()

        app = _make_app()
        datasets = [
            {"name": "tank/vm-100", "type": "dataset"},
            {"name": "tank/vm-200", "type": "dataset"},
        ]

        with _patch_module():
            _configure_dialog_ok(da)
            da._delete_datasets(app, datasets)

        steps = app.dataset_runner.set_steps.call_args[0][0]
        self.assertEqual(len(steps), 2)
        for step, expected_name in zip(steps, ["tank/vm-100", "tank/vm-200"]):
            self.assertIsInstance(step, BashStep)
            self.assertEqual(step.description, f"Destroy {expected_name}")
            self.assertFalse(step.is_rsync)
            self.assertFalse(step.fatal)
            self.assertEqual(step.command[0], "bash")
            self.assertEqual(step.command[1], "-c")
            self.assertIn(f'delfs "{expected_name}"', step.command[2])

    def test_starts_runner_with_on_complete_callback(self):
        da = self._import_under_mock()

        app = _make_app()
        datasets = [{"name": "tank/vm-100", "type": "dataset"}]

        with _patch_module():
            _configure_dialog_ok(da)
            da._delete_datasets(app, datasets)

        app.dataset_runner.set_steps.assert_called_once()
        runner_start_call = app.dataset_runner.start.call_args
        self.assertIn("on_complete", runner_start_call.kwargs)

    def test_refreshes_page_on_complete(self):
        da = self._import_under_mock()

        app = _make_app()
        datasets = [{"name": "tank/vm-100", "type": "dataset"}]

        with _patch_module():
            _configure_dialog_ok(da)
            da._delete_datasets(app, datasets)
            on_complete = app.dataset_runner.start.call_args.kwargs["on_complete"]
            on_complete(cancelled=False)
            patched_refresh = da.refresh_datasets_page

        patched_refresh.assert_called_once_with(app)

    def test_warns_when_runner_missing(self):
        da = self._import_under_mock()

        app = _make_app(runner=None)
        datasets = [{"name": "tank/vm-100", "type": "dataset"}]

        with _patch_module():
            _configure_dialog_ok(da)
            da._delete_datasets(app, datasets)
            patched_log_msg = da.log_msg

        patched_log_msg.assert_called_with("WARN: Dataset runner not available")
        assert app.dataset_runner is None

    def test_warns_when_runner_busy(self):
        da = self._import_under_mock()

        runner = MagicMock()
        runner.running = True
        app = _make_app(runner=runner)
        datasets = [{"name": "tank/vm-100", "type": "dataset"}]

        with _patch_module():
            _configure_dialog_ok(da)
            da._delete_datasets(app, datasets)
            patched_log_msg = da.log_msg

        patched_log_msg.assert_called_with("WARN: A dataset action is already running")
        runner.set_steps.assert_not_called()
        runner.start.assert_not_called()

    def test_does_nothing_when_dialog_cancelled(self):
        da = self._import_under_mock()

        app = _make_app()
        datasets = [{"name": "tank/vm-100", "type": "dataset"}]

        with _patch_module():
            _configure_dialog_cancel(da)
            da._delete_datasets(app, datasets)
            patched_refresh = da.refresh_datasets_page

        app.dataset_runner.set_steps.assert_not_called()
        app.dataset_runner.start.assert_not_called()
        patched_refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
