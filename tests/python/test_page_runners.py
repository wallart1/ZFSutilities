"""Tests for backup/offsite/restore run handlers."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk
from app_context import AppContext
from command_builders import BashStep


def _mock_app_with_runner():
    """Return a minimal app mock with backup/offsite/restore runners."""
    app = MagicMock()
    app.backup_runner = MagicMock()
    app.backup_runner.running = False
    app.offsite_runner = MagicMock()
    app.offsite_runner.running = False
    app.restore_runner = MagicMock()
    app.restore_runner.running = False
    app.config = {}
    app._dry_run_active = False
    app.ctx = AppContext(
        config=app.config,
        script_dir="",
        parent_dir=REPO_ROOT,
        version="dev",
    )
    return app


def _configure_dialog_ok(module):
    """Make the module's Gtk.MessageDialog.run() return OK."""
    module.Gtk.MessageDialog.return_value.run.return_value = module.Gtk.ResponseType.OK


class TestRestorePageRun(unittest.TestCase):
    """restore_page.on_restore_run() calls prepare_session_log."""

    def _patch_dependencies(self, auto_dest=False, dest="tank/dest"):
        return patch.multiple(
            "restore_page",
            collect_restore_config=MagicMock(return_value={
                "source": "backuppool/tank/source",
                "dest": dest,
                "auto_dest": auto_dest,
                "do_part1": True,
                "do_part2": False,
                "variables": {},
            }),
            get_pool_names=MagicMock(return_value=["tank", "backuppool"]),
            compute_auto_destination=MagicMock(return_value="tank/source"),
            compute_restore_params=MagicMock(return_value=(1, "tank")),
            build_restore_command=MagicMock(return_value=BashStep(["echo", "restore"], "Restore step")),
        )

    def test_prepare_session_log_called(self):
        with mock_gtk():
            import restore_page
        _configure_dialog_ok(restore_page)
        app = _mock_app_with_runner()
        app.parent_dir = REPO_ROOT

        with self._patch_dependencies():
            restore_page.on_restore_run(app, app.ctx)

        app.restore_runner.prepare_session_log.assert_called_once()

    def test_auto_destination_computes_dest(self):
        with mock_gtk():
            import restore_page
        _configure_dialog_ok(restore_page)
        app = _mock_app_with_runner()
        app.parent_dir = REPO_ROOT

        with patch.object(restore_page, "compute_auto_destination",
                          return_value="tank/source") as mock_auto, \
             patch.object(restore_page, "get_pool_names",
                          return_value=["tank", "backuppool"]), \
             patch.object(restore_page, "collect_restore_config",
                          return_value={
                              "source": "backuppool/tank/source",
                              "dest": "",
                              "auto_dest": True,
                              "do_part1": True,
                              "do_part2": False,
                              "variables": {},
                          }), \
             patch.object(restore_page, "compute_restore_params",
                          return_value=(1, "tank")), \
             patch.object(restore_page, "build_restore_command",
                          return_value=BashStep(["echo", "restore"], "Restore step")):
            restore_page.on_restore_run(app, app.ctx)

        mock_auto.assert_called_once_with(
            "backuppool/tank/source", ["tank", "backuppool"]
        )
        app.restore_runner.prepare_session_log.assert_called_once()
        app.restore_runner.set_steps.assert_called_once()


class TestOffsitePageRun(unittest.TestCase):
    """offsite_page.on_offsite_run() calls prepare_session_log."""

    def _patch_dependencies(self):
        return patch.multiple(
            "offsite_page",
            collect_offsite_config=MagicMock(return_value={
                "steps": [],
                "variables": {},
            }),
            do_detect_offsite_pool=MagicMock(return_value="offsitepool"),
            build_offsite_step_command=MagicMock(return_value=BashStep(["echo", "offsite"], "Offsite step")),
        )

    def test_prepare_session_log_called(self):
        with mock_gtk():
            import offsite_page
        _configure_dialog_ok(offsite_page)
        app = _mock_app_with_runner()
        app.offsite_nextsnap_entry.get_text.return_value = "@offsite-2026-06-11T12:00-s"
        app.offsite_pool_store = MagicMock()

        with self._patch_dependencies():
            offsite_page.on_offsite_run(app, app.ctx)

        app.offsite_runner.prepare_session_log.assert_called_once()


class TestBackupPageRun(unittest.TestCase):
    """backup_page.on_backup_run() calls prepare_session_log."""

    def _patch_dependencies(self):
        return patch.multiple(
            "backup_page",
            collect_backup_config=MagicMock(return_value={
                "steps": [],
                "variables": {},
                "post_steps": {"remove_snapfile": False, "run_retention": False},
            }),
            build_pre_backup_command=MagicMock(return_value=BashStep(["echo", "pre"], "Pre-backup")),
            build_rsync_command=MagicMock(return_value=BashStep(["echo", "rsync"], "Rsync step", is_rsync=True)),
            build_send_receive_command=MagicMock(return_value=BashStep(["echo", "zfs"], "ZFS step")),
            build_post_backup_command=MagicMock(return_value=BashStep(["echo", "post"], "Post-backup")),
            build_retention_command=MagicMock(return_value=BashStep(["echo", "retain"], "Retention")),
        )

    def test_prepare_session_log_called(self):
        with mock_gtk():
            import backup_page
        _configure_dialog_ok(backup_page)
        app = _mock_app_with_runner()
        app.backup_nextsnap_entry.get_text.return_value = "@daily-2026-06-11T12:00-d"
        app.backup_pull_store = []
        app.config = {"retention": {"enabled": False}}

        with self._patch_dependencies():
            backup_page.on_backup_run(app, app.ctx)

        app.backup_runner.prepare_session_log.assert_called_once()

    def test_backup_run_skips_pull_steps_when_inactive(self):
        with mock_gtk():
            import backup_page
        _configure_dialog_ok(backup_page)
        app = _mock_app_with_runner()
        app.backup_nextsnap_entry.get_text.return_value = "@daily-2026-06-11T12:00-d"
        app.backup_pull_store = [[True, "remote:/src", "/dst"]]
        app.backup_sr_store = [[True, "tank/src", "tank/dst"]]
        app.backup_pull_steps_active.get_active.return_value = False
        app.config = {"retention": {"enabled": False}}

        with self._patch_dependencies():
            backup_page.on_backup_run(app, app.ctx)
            backup_page.build_rsync_command.assert_not_called()
            backup_page.build_send_receive_command.assert_called_once()

    def test_backup_run_includes_pull_steps_when_active(self):
        with mock_gtk():
            import backup_page
        _configure_dialog_ok(backup_page)
        app = _mock_app_with_runner()
        app.backup_nextsnap_entry.get_text.return_value = "@daily-2026-06-11T12:00-d"
        app.backup_pull_store = [[True, "remote:/src", "/dst"]]
        app.backup_sr_store = []
        app.backup_pull_steps_active.get_active.return_value = True
        app.config = {"retention": {"enabled": False}}

        with self._patch_dependencies():
            backup_page.on_backup_run(app, app.ctx)
            backup_page.build_rsync_command.assert_called_once_with("remote:/src", "/dst")


if __name__ == "__main__":
    unittest.main()
