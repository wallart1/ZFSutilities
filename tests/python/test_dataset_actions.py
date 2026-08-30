"""Tests for dataset_actions.py — dataset destruction via BackupRunner."""

import os
import sys
import unittest
from unittest.mock import MagicMock, call, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import zfs_lock_manager as zlm
from command_builders import BashStep
from test_support import mock_gtk

_MISSING_RUNNER = object()


def _make_show_big_stuff_app(runner=_MISSING_RUNNER, parent_dir="/repo/bin"):
    """Return a minimal app mock for testing Show Big Stuff."""
    app = MagicMock()
    app.parent_dir = parent_dir
    if runner is _MISSING_RUNNER:
        app.dataset_runner = MagicMock()
        app.dataset_runner.running = False
    else:
        app.dataset_runner = runner
    return app


class TestShowBigStuff(unittest.TestCase):
    """on_datasets_show_big_stuff delegates to app.dataset_runner via BashStep."""

    def _import_under_mock(self):
        with mock_gtk():
            import dataset_actions as da

            return da

    def test_warns_when_not_exactly_one_pool(self):
        da = self._import_under_mock()
        app = _make_show_big_stuff_app()
        app.datasets_view = MagicMock()

        with (
            patch.object(da, "get_tree_selection_items", return_value=[]),
            patch.object(da, "log_msg") as mock_log,
        ):
            da.on_datasets_show_big_stuff(app)

        mock_log.assert_called_once_with("WARN: Select exactly one pool to show big stuff")
        app.dataset_runner.set_steps.assert_not_called()

    def test_builds_bash_step_for_selected_pool(self):
        da = self._import_under_mock()
        app = _make_show_big_stuff_app(parent_dir="/repo/bin")
        app.datasets_view = MagicMock()

        with patch.object(
            da, "get_tree_selection_items", return_value=[{"type": "pool", "name": "tank"}]
        ):
            da.on_datasets_show_big_stuff(app)

        app.dataset_runner.set_steps.assert_called_once()
        steps = app.dataset_runner.set_steps.call_args[0][0]
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertIsInstance(step, BashStep)
        self.assertEqual(step.description, "Show big stuff for tank")
        self.assertFalse(step.is_rsync)
        self.assertFalse(step.fatal)
        self.assertEqual(step.command[0], "bash")
        self.assertEqual(step.command[1], "-c")
        self.assertIn('"$mydir/zfsshowbigstuff"', step.command[2])
        self.assertIn("tank", step.command[2])
        self.assertIn('mydir="/repo/bin"', step.command[2])

    def test_starts_runner(self):
        da = self._import_under_mock()
        app = _make_show_big_stuff_app()
        app.datasets_view = MagicMock()

        with patch.object(
            da, "get_tree_selection_items", return_value=[{"type": "pool", "name": "tank"}]
        ):
            da.on_datasets_show_big_stuff(app)

        app.dataset_runner.start.assert_called_once()

    def test_warns_when_runner_missing(self):
        da = self._import_under_mock()
        app = _make_show_big_stuff_app(runner=None)
        app.datasets_view = MagicMock()

        with (
            patch.object(
                da, "get_tree_selection_items", return_value=[{"type": "pool", "name": "tank"}]
            ),
            patch.object(da, "log_msg") as mock_log,
        ):
            da.on_datasets_show_big_stuff(app)

        mock_log.assert_called_once_with("WARN: Dataset runner not available")

    def test_warns_when_runner_busy(self):
        da = self._import_under_mock()
        runner = MagicMock()
        runner.running = True
        app = _make_show_big_stuff_app(runner=runner)
        app.datasets_view = MagicMock()

        with (
            patch.object(
                da, "get_tree_selection_items", return_value=[{"type": "pool", "name": "tank"}]
            ),
            patch.object(da, "log_msg") as mock_log,
        ):
            da.on_datasets_show_big_stuff(app)

        mock_log.assert_called_once_with("WARN: A dataset action is already running")
        runner.set_steps.assert_not_called()
        runner.start.assert_not_called()


def _make_app(runner=_MISSING_RUNNER, parent_dir="/repo/bin"):
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
    zlm_mock = MagicMock()
    zlm_mock.check.return_value = True
    zlm_mock.lock.return_value.__enter__ = MagicMock(return_value="lock-id")
    zlm_mock.lock.return_value.__exit__ = MagicMock(return_value=False)
    zlm_mock.locks.return_value.__enter__ = MagicMock(return_value=["lock-id"])
    zlm_mock.locks.return_value.__exit__ = MagicMock(return_value=False)
    return patch.multiple(
        "dataset_actions",
        create_dialog=MagicMock(),
        add_scrolled_text_view=MagicMock(),
        refresh_datasets_page=MagicMock(),
        log_msg=MagicMock(),
        zlm=zlm_mock,
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

    def setUp(self):
        zlm._lock_refcounts.clear()

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

    def test_checks_lock_before_destroying(self):
        da = self._import_under_mock()

        app = _make_app()
        datasets = [
            {"name": "tank/vm-100", "type": "dataset"},
            {"name": "tank/vm-200", "type": "dataset"},
        ]

        with _patch_module():
            _configure_dialog_ok(da)
            da._delete_datasets(app, datasets)
            zlm_mock = da.zlm

        zlm_mock.check.assert_has_calls(
            [
                call("tank/vm-100", "x"),
                call("tank/vm-200", "x"),
            ]
        )

    def test_aborts_when_dataset_locked(self):
        da = self._import_under_mock()

        app = _make_app()
        datasets = [{"name": "tank/vm-100", "type": "dataset"}]

        with _patch_module():
            _configure_dialog_ok(da)
            da.zlm.check.return_value = False
            da._delete_datasets(app, datasets)
            patched_log_msg = da.log_msg

        patched_log_msg.assert_called_with(
            "WARN: cannot destroy tank/vm-100: dataset is locked by another operation"
        )
        app.dataset_runner.set_steps.assert_not_called()
        app.dataset_runner.start.assert_not_called()


class TestUnmount(unittest.TestCase):
    """on_datasets_unmount acquires a write lock before umount."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def _import_under_mock(self):
        with mock_gtk():
            import dataset_actions as da

            return da

    def _make_app(self):
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        return app

    def test_acquires_lock_before_umount(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {"type": "snapshot", "dataset": "tank/vm-100", "name": "manual-2025-01-01"}
                ],
            ),
            patch.object(
                da,
                "get_snapshot_mountpoint",
                return_value="/tmp/mnt/tank_vm-100@manual-2025-01-01",
            ),
            patch.object(da, "get_busy_processes", return_value=[]),
            patch.object(da, "update_ds_button_sensitivity"),
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
            patch.object(da, "zlm") as mock_zlm,
        ):
            mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")
            da.on_datasets_unmount(app)

            mock_zlm.lock.assert_called_once_with(
                "tank/vm-100",
                "w",
                "umount snapshot tank/vm-100@manual-2025-01-01",
            )
            mock_subprocess.run.assert_called_once_with(
                ["sudo", "umount", "/tmp/mnt/tank_vm-100@manual-2025-01-01"],
                capture_output=True,
                text=True,
                check=False,
            )
            mock_log.assert_any_call("INFO: Unmounted snapshot tank/vm-100@manual-2025-01-01")

    def test_logs_warning_when_locked(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {"type": "snapshot", "dataset": "tank/vm-100", "name": "manual-2025-01-01"}
                ],
            ),
            patch.object(
                da,
                "get_snapshot_mountpoint",
                return_value="/tmp/mnt/tank_vm-100@manual-2025-01-01",
            ),
            patch.object(da, "get_busy_processes", return_value=[]),
            patch.object(da, "update_ds_button_sensitivity"),
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
            patch.object(da, "zlm") as mock_zlm,
        ):
            mock_zlm.lock.side_effect = RuntimeError(
                "conflict: cannot acquire w lock on tank/vm-100"
            )
            da.on_datasets_unmount(app)

            mock_zlm.lock.assert_called_once()
            mock_subprocess.run.assert_not_called()
            mock_log.assert_called_once_with(
                "WARN: cannot unmount tank/vm-100@manual-2025-01-01: "
                "conflict: cannot acquire w lock on tank/vm-100"
            )

    def test_logs_busy_when_umount_reports_busy(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {"type": "snapshot", "dataset": "tank/vm-100", "name": "manual-2025-01-01"}
                ],
            ),
            patch.object(
                da,
                "get_snapshot_mountpoint",
                return_value="/tmp/mnt/tank_vm-100@manual-2025-01-01",
            ),
            patch.object(da, "get_busy_processes", return_value=[]),
            patch.object(da, "update_ds_button_sensitivity"),
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
            patch.object(da, "zlm"),
        ):
            mock_subprocess.run.return_value = MagicMock(
                returncode=1, stderr="umount: target is busy"
            )
            da.on_datasets_unmount(app)

            mock_subprocess.run.assert_called_once()
            mock_log.assert_any_call(
                "WARN: Snapshot tank/vm-100@manual-2025-01-01 is busy. "
                "Please close any file manager windows and try again."
            )


class TestUnmountDataset(unittest.TestCase):
    """on_datasets_unmount handles filesystem datasets."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def _import_under_mock(self):
        with mock_gtk():
            import dataset_actions as da

            return da

    def _make_app(self):
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        app.ctx.zfs_repository.get_property.return_value = "/tank/vm-100"
        return app

    def test_unmounts_filesystem_dataset(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {
                        "type": "dataset",
                        "name": "tank/vm-100",
                        "zfs_type": "filesystem",
                    }
                ],
            ),
            patch.object(da, "get_busy_processes", return_value=[]),
            patch.object(da, "refresh_datasets_page") as mock_refresh,
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
            patch.object(da, "zlm") as mock_zlm,
        ):
            mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")
            da.on_datasets_unmount(app)

            mock_zlm.lock.assert_called_once_with("tank/vm-100", "w", "umount tank/vm-100")
            mock_subprocess.run.assert_called_once_with(
                ["sudo", "zfs", "unmount", "tank/vm-100"],
                capture_output=True,
                text=True,
                check=False,
            )
            mock_log.assert_any_call("INFO: Unmounted tank/vm-100")
            mock_refresh.assert_called_once_with(app)

    def test_warns_when_dataset_unmount_busy(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {
                        "type": "dataset",
                        "name": "tank/vm-100",
                        "zfs_type": "filesystem",
                    }
                ],
            ),
            patch.object(da, "get_busy_processes", return_value=[(123, "bash")]),
            patch.object(da, "refresh_datasets_page") as mock_refresh,
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
            patch.object(da, "zlm"),
            patch.object(da, "Gtk") as mock_gtk,
        ):
            da.on_datasets_unmount(app)

            mock_gtk.MessageDialog.assert_called_once()
            mock_subprocess.run.assert_not_called()
            mock_log.assert_not_called()
            mock_refresh.assert_not_called()


class TestMount(unittest.TestCase):
    """on_datasets_mount handles filesystems and snapshots."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def _import_under_mock(self):
        with mock_gtk():
            import dataset_actions as da

            return da

    def _make_app(self):
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        return app

    def test_mounts_filesystem_dataset(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {
                        "type": "dataset",
                        "name": "tank/vm-100",
                        "zfs_type": "filesystem",
                    }
                ],
            ),
            patch.object(da, "refresh_datasets_page") as mock_refresh,
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
            patch.object(da, "zlm") as mock_zlm,
        ):
            mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")
            da.on_datasets_mount(app)

            mock_zlm.lock.assert_called_once_with("tank/vm-100", "w", "mount tank/vm-100")
            mock_subprocess.run.assert_called_once_with(
                ["sudo", "zfs", "mount", "tank/vm-100"],
                capture_output=True,
                text=True,
                check=False,
            )
            mock_log.assert_any_call("INFO: Mounted tank/vm-100")
            mock_refresh.assert_called_once_with(app)

    def test_warns_when_filesystem_mount_fails(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {
                        "type": "dataset",
                        "name": "tank/vm-100",
                        "zfs_type": "filesystem",
                    }
                ],
            ),
            patch.object(da, "refresh_datasets_page") as mock_refresh,
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
            patch.object(da, "zlm"),
        ):
            mock_subprocess.run.return_value = MagicMock(
                returncode=1, stderr="cannot mount 'tank/vm-100': mountpoint or dataset is busy"
            )
            da.on_datasets_mount(app)

            mock_log.assert_any_call(
                "WARN: Error mounting tank/vm-100: cannot mount 'tank/vm-100': "
                "mountpoint or dataset is busy"
            )
            mock_refresh.assert_not_called()

    def test_warns_when_filesystem_mount_lock_conflicts(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {
                        "type": "dataset",
                        "name": "tank/vm-100",
                        "zfs_type": "filesystem",
                    }
                ],
            ),
            patch.object(da, "refresh_datasets_page") as mock_refresh,
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
            patch.object(da, "zlm") as mock_zlm,
        ):
            mock_zlm.lock.side_effect = RuntimeError(
                "conflict: cannot acquire w lock on tank/vm-100"
            )
            da.on_datasets_mount(app)

            mock_zlm.lock.assert_called_once_with("tank/vm-100", "w", "mount tank/vm-100")
            mock_subprocess.run.assert_not_called()
            mock_log.assert_called_once_with(
                "WARN: cannot mount tank/vm-100: conflict: cannot acquire w lock on tank/vm-100"
            )
            mock_refresh.assert_not_called()

    def test_mounts_snapshot_by_auto_mount_path(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[{"type": "snapshot", "dataset": "tank/vm-100", "name": "snap1"}],
            ),
            patch.object(
                da,
                "get_snapshot_mountpoint",
                return_value="/tank/vm-100/.zfs/snapshot/snap1",
            ),
            patch.object(da, "update_ds_button_sensitivity") as mock_update,
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess"),
            patch.object(da, "zlm") as mock_zlm,
            patch.object(da.os.path, "isdir", return_value=False),
            patch.object(da.os, "listdir", return_value=[]),
        ):
            app.ctx.zfs_repository.get_property.return_value = "yes"
            da.on_datasets_mount(app)

            mock_zlm.lock.assert_called_once_with(
                "tank/vm-100", "w", "mount snapshot tank/vm-100@snap1"
            )
            mock_log.assert_any_call("INFO: Mounted snapshot tank/vm-100@snap1")
            mock_update.assert_called_once_with(app)

    def test_warns_when_snapshot_parent_not_mounted(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[{"type": "snapshot", "dataset": "tank/vm-100", "name": "snap1"}],
            ),
            patch.object(
                da,
                "get_snapshot_mountpoint",
                return_value="/tank/vm-100/.zfs/snapshot/snap1",
            ),
            patch.object(da, "update_ds_button_sensitivity"),
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "zlm") as mock_zlm,
            patch.object(da.os.path, "isdir", return_value=False),
        ):
            app.ctx.zfs_repository.get_property.return_value = "no"
            da.on_datasets_mount(app)

            mock_log.assert_any_call(
                "WARN: Cannot mount tank/vm-100@snap1: parent dataset "
                "tank/vm-100 is not mounted. Mount the parent first."
            )
            mock_zlm.lock.assert_called_once()

    def test_warns_when_snapshot_mountpoint_resolution_fails(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[{"type": "snapshot", "dataset": "tank/vm-100", "name": "snap1"}],
            ),
            patch.object(
                da,
                "get_snapshot_mountpoint",
                side_effect=FileNotFoundError("no such snapshot path"),
            ),
            patch.object(da, "update_ds_button_sensitivity"),
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "zlm"),
        ):
            da.on_datasets_mount(app)

            mock_log.assert_called_once_with(
                "WARN: Error mounting snapshot tank/vm-100@snap1: no such snapshot path"
            )


class TestBrowse(unittest.TestCase):
    """on_datasets_browse opens filesystems and snapshots."""

    def _import_under_mock(self):
        with mock_gtk():
            import dataset_actions as da

            return da

    def _make_app(self):
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        return app

    def test_opens_filesystem_mountpoint(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[
                    {
                        "type": "dataset",
                        "name": "tank/vm-100",
                        "zfs_type": "filesystem",
                    }
                ],
            ),
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
        ):
            app.ctx.zfs_repository.get_property.return_value = "/tank/vm-100"
            da.on_datasets_browse(app)

            mock_subprocess.Popen.assert_called_once_with(["xdg-open", "/tank/vm-100"])
            mock_log.assert_any_call("VERB: Opened /tank/vm-100")

    def test_browses_snapshot_via_zfs_path(self):
        da = self._import_under_mock()
        app = self._make_app()

        with (
            patch.object(
                da,
                "get_tree_selection_items",
                return_value=[{"type": "snapshot", "dataset": "tank/vm-100", "name": "snap1"}],
            ),
            patch.object(
                da,
                "get_snapshot_mountpoint",
                return_value="/tank/vm-100/.zfs/snapshot/snap1",
            ),
            patch.object(da, "update_ds_button_sensitivity") as mock_update,
            patch.object(da, "log_msg") as mock_log,
            patch.object(da, "subprocess") as mock_subprocess,
        ):
            da.on_datasets_browse(app)

            mock_subprocess.Popen.assert_called_once_with(
                ["xdg-open", "/tank/vm-100/.zfs/snapshot/snap1"]
            )
            mock_log.assert_any_call("VERB: Browsing snapshot tank/vm-100@snap1")
            mock_update.assert_called_once_with(app)


class TestDeleteSnapshots(unittest.TestCase):
    """_delete_snapshots releases selected holds before deleting snapshots."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def _import_under_mock(self):
        with mock_gtk():
            import dataset_actions as da

            return da

    def test_releases_selected_holds_then_deletes(self):
        da = self._import_under_mock()
        app = _make_app()
        snap = {"dataset": "tank/vm-100", "name": "snap-1", "type": "snapshot"}
        hold = {"dataset": "tank/vm-100", "snapshot": "snap-1", "tag": "keep"}
        app.ctx.zfs_repository.list_holds.return_value = [
            MagicMock(snapshot="tank/vm-100@snap-1", tag="keep")
        ]
        app.ctx.zfs_repository.release.return_value = True
        app.ctx.zfs_repository.destroy.return_value = True

        with _patch_module(), patch.object(da, "_confirm_yes_no", return_value=True):
            da._delete_snapshots(app, [snap], selected_holds=[hold])
            patched_log = da.log_msg

        app.ctx.zfs_repository.release.assert_called_once_with("keep", "tank/vm-100@snap-1")
        app.ctx.zfs_repository.destroy.assert_called_once_with("tank/vm-100@snap-1")
        patched_log.assert_any_call("INFO: Released 'keep' on tank/vm-100@snap-1")
        patched_log.assert_any_call("INFO: Deleted: tank/vm-100@snap-1")

    def test_aborts_when_unselected_hold_exists(self):
        da = self._import_under_mock()
        app = _make_app()
        snap = {"dataset": "tank/vm-100", "name": "snap-1", "type": "snapshot"}
        hold = {"dataset": "tank/vm-100", "snapshot": "snap-1", "tag": "keep"}
        app.ctx.zfs_repository.list_holds.return_value = [
            MagicMock(snapshot="tank/vm-100@snap-1", tag="keep"),
            MagicMock(snapshot="tank/vm-100@snap-1", tag="other"),
        ]

        with _patch_module(), patch.object(da, "_confirm_yes_no", return_value=True):
            da._delete_snapshots(app, [snap], selected_holds=[hold])
            patched_log = da.log_msg

        app.ctx.zfs_repository.release.assert_not_called()
        app.ctx.zfs_repository.destroy.assert_not_called()
        warning = patched_log.call_args[0][0]
        self.assertIn("tank/vm-100@snap-1", warning)
        self.assertIn("other", warning)

    def test_aborts_when_holds_exist_and_none_selected(self):
        da = self._import_under_mock()
        app = _make_app()
        snap = {"dataset": "tank/vm-100", "name": "snap-1", "type": "snapshot"}
        app.ctx.zfs_repository.list_holds.return_value = [
            MagicMock(snapshot="tank/vm-100@snap-1", tag="keep"),
        ]

        with _patch_module():
            da._delete_snapshots(app, [snap])
            patched_log = da.log_msg

        app.ctx.zfs_repository.release.assert_not_called()
        app.ctx.zfs_repository.destroy.assert_not_called()
        warning = patched_log.call_args[0][0]
        self.assertIn("tank/vm-100@snap-1", warning)
        self.assertIn("keep", warning)

    def test_deletes_snapshot_and_releases_holds_on_other_snapshots(self):
        da = self._import_under_mock()
        app = _make_app()
        snap = {"dataset": "tank/vm-100", "name": "snap-1", "type": "snapshot"}
        hold = {"dataset": "tank/vm-100", "snapshot": "snap-2", "tag": "keep"}
        app.ctx.zfs_repository.list_holds.return_value = []
        app.ctx.zfs_repository.release.return_value = True
        app.ctx.zfs_repository.destroy.return_value = True

        with _patch_module(), patch.object(da, "_confirm_yes_no", return_value=True):
            da._delete_snapshots(app, [snap], selected_holds=[hold])

        app.ctx.zfs_repository.release.assert_called_once_with("keep", "tank/vm-100@snap-2")
        app.ctx.zfs_repository.destroy.assert_called_once_with("tank/vm-100@snap-1")

    def test_locks_include_both_snapshot_and_hold_parents(self):
        da = self._import_under_mock()
        app = _make_app()
        snap = {"dataset": "tank/vm-100", "name": "snap-1", "type": "snapshot"}
        hold = {"dataset": "tank/vm-200", "snapshot": "snap-2", "tag": "keep"}
        app.ctx.zfs_repository.list_holds.return_value = []
        app.ctx.zfs_repository.release.return_value = True
        app.ctx.zfs_repository.destroy.return_value = True

        with _patch_module(), patch.object(da, "_confirm_yes_no", return_value=True):
            da._delete_snapshots(app, [snap], selected_holds=[hold])
            zlm_mock = da.zlm

        zlm_mock.locks.assert_called_once()
        parents = zlm_mock.locks.call_args[0][1]
        self.assertIn("tank/vm-100", parents)
        self.assertIn("tank/vm-200", parents)


if __name__ == "__main__":
    unittest.main()
