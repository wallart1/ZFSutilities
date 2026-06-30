"""Tests for the Backup tab UI."""

import os
import unittest
from unittest.mock import MagicMock, patch

from test_support import mock_gtk, temp_config_dir
from app_context import AppContext


class _NoOpDirtyTracker:
    def __init__(self, *args, **kwargs):
        pass

    def check(self, *args, **kwargs):
        pass


class _FakeWidgetBase:
    """Minimal widget stand-in for the backup page unit tests."""

    def __init__(self, *args, **kwargs):
        pass

    def set_hexpand(self, *args):
        pass

    def set_width_chars(self, *args):
        pass

    def set_placeholder_text(self, *args):
        pass

    def set_tooltip_text(self, *args):
        pass

    def connect(self, *args):
        pass


class _FakeEntry(_FakeWidgetBase):
    """Entry-like fake that records its text value."""

    def __init__(self, *args, **kwargs):
        self._text = ""

    def set_text(self, text):
        self._text = text

    def get_text(self):
        return self._text


class _FakeCheckButton(_FakeWidgetBase):
    """CheckButton-like fake that records its label and active state."""

    def __init__(self, label=None):
        self.label = label
        self._active = False

    def set_active(self, active):
        self._active = active

    def get_active(self):
        return self._active


class _FakeApp:
    config = {}
    _ui_state = MagicMock()
    _save_config_button = MagicMock()
    ctx = AppContext(
        config=config,
        script_dir="",
        parent_dir="",
        version="dev",
    )

    def log_message(self, *args):
        pass


def _backup_app():
    """Return an app mock with the widgets required by backup config helpers."""
    app = _FakeApp()
    app.backup_var_widgets = {}
    app.backup_pull_store = MagicMock()
    app.backup_sr_store = MagicMock()
    app.backup_post_snapfile = _FakeCheckButton()
    app.backup_post_retention = _FakeCheckButton()
    app.backup_pre_script_enabled = _FakeCheckButton()
    app.backup_pre_script_text = _FakeEntry()
    app.backup_post_script_enabled = _FakeCheckButton()
    app.backup_post_script_text = _FakeEntry()
    app.backup_zfs_keys_path = _FakeEntry()
    app.backup_zfs_keys_dest = _FakeEntry()
    app.backup_pull_steps_active = _FakeCheckButton()
    app.backup_pause_scrubs = _FakeCheckButton()
    return app


class TestBackupPageLabels(unittest.TestCase):
    """Verify user-visible labels on the Backup tab."""

    def test_post_step_labels_use_clear_language(self):
        with temp_config_dir():
            with mock_gtk():
                import backup_page
                import gui_helpers

                # Provide concrete widget classes so isinstance() checks pass.
                backup_page.Gtk.Entry = _FakeEntry
                backup_page.Gtk.CheckButton = _FakeCheckButton
                gui_helpers.Gtk.Entry = _FakeEntry
                gui_helpers.Gtk.CheckButton = _FakeCheckButton
                backup_page.DirtyTracker = _NoOpDirtyTracker

                app = _FakeApp()
                backup_page.create_backup_page(app, app.ctx)

                self.assertEqual(
                    app.backup_post_snapfile.label,
                    "Clear snapshot name memory",
                )
                self.assertEqual(
                    app.backup_post_retention.label,
                    "Prune snapshots",
                )
                self.assertEqual(
                    app.backup_pull_steps_active.label,
                    "Active",
                )


class TestBackupPageScriptLabels(unittest.TestCase):
    """Verify pre/post backup labels use 'command' instead of 'script'."""

    def test_pre_backup_label_says_command(self):
        with temp_config_dir():
            with mock_gtk():
                import backup_page
                import gui_helpers

                backup_page.Gtk.Entry = _FakeEntry
                backup_page.Gtk.CheckButton = _FakeCheckButton
                gui_helpers.Gtk.Entry = _FakeEntry
                gui_helpers.Gtk.CheckButton = _FakeCheckButton
                backup_page.DirtyTracker = _NoOpDirtyTracker

                app = _FakeApp()
                backup_page.create_backup_page(app, app.ctx)

                self.assertEqual(
                    app.backup_pre_script_enabled.label,
                    "Run pre-backup command",
                )

    def test_post_backup_label_says_command(self):
        with temp_config_dir():
            with mock_gtk():
                import backup_page
                import gui_helpers

                backup_page.Gtk.Entry = _FakeEntry
                backup_page.Gtk.CheckButton = _FakeCheckButton
                gui_helpers.Gtk.Entry = _FakeEntry
                gui_helpers.Gtk.CheckButton = _FakeCheckButton
                backup_page.DirtyTracker = _NoOpDirtyTracker

                app = _FakeApp()
                backup_page.create_backup_page(app, app.ctx)

                self.assertEqual(
                    app.backup_post_script_enabled.label,
                    "Run post-backup command",
                )


class TestBackupConfigHelpers(unittest.TestCase):
    """Tests for load_backup_config and collect_backup_config."""

    def test_load_backup_config_sets_pull_steps_active(self):
        with mock_gtk():
            import backup_page
            backup_page.Gtk.Entry = _FakeEntry
            backup_page.Gtk.CheckButton = _FakeCheckButton

            app = _backup_app()
            backup_page.load_backup_config(app, {"pull_steps_active": False})
            self.assertFalse(app.backup_pull_steps_active.get_active())

    def test_load_backup_config_defaults_pull_steps_active_to_true(self):
        with mock_gtk():
            import backup_page
            backup_page.Gtk.Entry = _FakeEntry
            backup_page.Gtk.CheckButton = _FakeCheckButton

            app = _backup_app()
            backup_page.load_backup_config(app, {})
            self.assertTrue(app.backup_pull_steps_active.get_active())

    def test_collect_backup_config_includes_pull_steps_active(self):
        with mock_gtk():
            import backup_page
            backup_page.Gtk.Entry = _FakeEntry
            backup_page.Gtk.CheckButton = _FakeCheckButton

            app = _backup_app()
            app.backup_pull_steps_active.set_active(False)
            config = backup_page.collect_backup_config(app)
            self.assertFalse(config["pull_steps_active"])

    def test_collect_backup_config_includes_pause_scrubs(self):
        with mock_gtk():
            import backup_page
            backup_page.Gtk.Entry = _FakeEntry
            backup_page.Gtk.CheckButton = _FakeCheckButton

            app = _backup_app()
            app.backup_pause_scrubs.set_active(True)
            config = backup_page.collect_backup_config(app)
            self.assertTrue(config["pause_scrubs"])

    def test_load_backup_config_sets_pause_scrubs(self):
        with mock_gtk():
            import backup_page
            backup_page.Gtk.Entry = _FakeEntry
            backup_page.Gtk.CheckButton = _FakeCheckButton

            app = _backup_app()
            backup_page.load_backup_config(app, {"pause_scrubs": True})
            self.assertTrue(app.backup_pause_scrubs.get_active())

    def test_load_backup_config_defaults_pause_scrubs_to_false(self):
        with mock_gtk():
            import backup_page
            backup_page.Gtk.Entry = _FakeEntry
            backup_page.Gtk.CheckButton = _FakeCheckButton

            app = _backup_app()
            backup_page.load_backup_config(app, {})
            self.assertFalse(app.backup_pause_scrubs.get_active())


class TestBackupPageFrames(unittest.TestCase):
    """Tests for Backup page layout helpers."""

    def test_frame_box_uses_header_widget_when_provided(self):
        with mock_gtk():
            import backup_page
            parent = MagicMock()
            header = MagicMock()
            backup_page._frame_box(parent, "Pull Steps", header_widget=header)
            frame = parent.pack_start.call_args_list[0][0][0]
            frame.set_label_widget.assert_called_once()
            frame.set_label.assert_not_called()

    def test_frame_box_uses_plain_label_without_header_widget(self):
        with mock_gtk():
            import backup_page
            parent = MagicMock()
            backup_page._frame_box(parent, "Send/Receive")
            frame = parent.pack_start.call_args_list[0][0][0]
            frame.set_label.assert_not_called()
            # The frame should have its label widget set (last call with a label)
            last_call = frame.set_label_widget.call_args_list[-1]
            self.assertIn("Label()", str(last_call))


class _FakeBackupApp:
    """Minimal app stand-in for dialog-loop tests."""

    _dry_run_active = False
    config = {}
    ctx = AppContext(config=config, script_dir="", parent_dir="", version="dev")

    def clear_log_status(self):
        pass

    def update_action_buttons(self, *args):
        pass

    def __init__(self):
        self.backup_runner = MagicMock()
        self.backup_runner.running = False
        self.offsite_runner = MagicMock()
        self.offsite_runner.running = False
        self.restore_runner = MagicMock()
        self.restore_runner.running = False
        self.backup_nextsnap_entry = _FakeEntry()
        self.backup_pre_script_enabled = _FakeCheckButton()
        self.backup_pre_script_text = _FakeEntry()
        self.backup_post_script_enabled = _FakeCheckButton()
        self.backup_post_script_text = _FakeEntry()
        self.backup_pull_steps_active = _FakeCheckButton()
        self.backup_pull_store = []
        self.backup_sr_store = []
        self.backup_post_snapfile = _FakeCheckButton()
        self.backup_post_retention = _FakeCheckButton()


class TestBackupRunDialog(unittest.TestCase):
    """Tests for on_backup_run() confirmation dialog loop."""

    def _patch_run(self, backup_page):
        return patch.multiple(
            backup_page,
            collect_backup_config=MagicMock(return_value={
                "steps": [],
                "variables": {},
                "post_steps": {"remove_snapfile": False, "run_retention": False},
            }),
            build_pre_backup_command=MagicMock(),
            build_rsync_command=MagicMock(),
            build_send_receive_command=MagicMock(),
            build_post_backup_command=MagicMock(),
            build_retention_command=MagicMock(),
            _do_generate_snap=MagicMock(),
        )

    def test_cancel_logs_cancellation_and_returns(self):
        with mock_gtk():
            import backup_page

        app = _FakeBackupApp()
        app.backup_nextsnap_entry.set_text("@daily-2026-06-11T12:00-d")
        dialog_mock = MagicMock()
        dialog_mock.run.return_value = backup_page.Gtk.ResponseType.CANCEL
        backup_page.Gtk.MessageDialog.return_value = dialog_mock

        with self._patch_run(backup_page):
            with patch.object(backup_page, "log_msg") as mock_log:
                backup_page.on_backup_run(app, app.ctx)

        app.backup_runner.prepare_session_log.assert_not_called()
        mock_log.assert_called_once_with("INFO: Backup cancelled")

    def test_generate_reruns_snapshot_and_redisplays_dialog(self):
        with mock_gtk():
            import backup_page

        app = _FakeBackupApp()
        app.backup_nextsnap_entry.set_text("@daily-2026-06-11T12:00-d")

        def _generate_new_snap(_app):
            _app.backup_nextsnap_entry.set_text("@daily-2026-06-11T13:00-d")

        dialog_mock = MagicMock()
        dialog_mock.run.side_effect = [
            backup_page.Gtk.ResponseType.APPLY,
            backup_page.Gtk.ResponseType.OK,
        ]
        backup_page.Gtk.MessageDialog.return_value = dialog_mock

        with self._patch_run(backup_page):
            backup_page._do_generate_snap.side_effect = _generate_new_snap
            backup_page.on_backup_run(app, app.ctx)

            backup_page._do_generate_snap.assert_called_once()
            self.assertEqual(dialog_mock.run.call_count, 2)
            app.backup_runner.prepare_session_log.assert_called_once()

    def test_ok_proceeds_without_regeneration(self):
        with mock_gtk():
            import backup_page

        app = _FakeBackupApp()
        app.backup_nextsnap_entry.set_text("@daily-2026-06-11T12:00-d")
        dialog_mock = MagicMock()
        dialog_mock.run.return_value = backup_page.Gtk.ResponseType.OK
        backup_page.Gtk.MessageDialog.return_value = dialog_mock

        with self._patch_run(backup_page):
            backup_page.on_backup_run(app, app.ctx)

            backup_page._do_generate_snap.assert_not_called()
            dialog_mock.run.assert_called_once()
            app.backup_runner.prepare_session_log.assert_called_once()

    def test_retention_step_uses_pool_registry_order(self):
        with mock_gtk():
            import backup_page

        app = _FakeBackupApp()
        app.backup_nextsnap_entry.set_text("@daily-2026-06-11T12:00-d")
        app.ctx.config = {
            "pools": [
                {"name": "z2", "offsite_candidate": False},
                {"name": "z1", "offsite_candidate": False},
            ]
        }
        dialog_mock = MagicMock()
        dialog_mock.run.return_value = backup_page.Gtk.ResponseType.OK
        backup_page.Gtk.MessageDialog.return_value = dialog_mock

        with self._patch_run(backup_page):
            backup_page.collect_backup_config.return_value = {
                "variables": {"label": "dailybackup"},
                "post_steps": {"run_retention": True, "remove_snapfile": False},
            }
            backup_page.on_backup_run(app, app.ctx)

            backup_page.build_retention_command.assert_called_once_with(
                app.ctx.parent_dir,
                "dailybackup",
                pools=["z2", "z1"],
                dryrun=False,
                fatal=False,
            )


if __name__ == "__main__":
    unittest.main()
