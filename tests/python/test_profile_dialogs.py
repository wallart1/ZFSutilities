"""Tests for profile_dialogs.py — Add/Recall profile dialogs."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk

with mock_gtk():
    import profile_dialogs
    import schedule_page


class TestShowAddProfileDialog(unittest.TestCase):
    """show_add_profile_dialog validates input and creates profiles."""

    def _make_app(self):
        app = MagicMock()
        app.schedule_store = MagicMock()
        return app

    def _run_add_dialog(self, app, response, name_text,
                        duplicate_response=None, **patches):
        """Patch create_dialog/Entry and call show_add_profile_dialog."""
        dialog = MagicMock()
        dialog.run.return_value = response
        entry = MagicMock()
        entry.get_text.return_value = name_text

        confirm_dialog = MagicMock()
        if duplicate_response is not None:
            confirm_dialog.run.return_value = duplicate_response

        defaults = {
            "create_dialog": patch.object(profile_dialogs, "create_dialog", return_value=dialog),
            "Entry": patch.object(profile_dialogs.Gtk, "Entry", return_value=entry),
            "MessageDialog": patch.object(profile_dialogs.Gtk, "MessageDialog", return_value=confirm_dialog),
            "get_user": patch.object(profile_dialogs, "get_user", return_value="root"),
        }
        defaults.update(patches)
        with defaults["create_dialog"], defaults["Entry"], defaults["MessageDialog"], defaults["get_user"]:
            profile_dialogs.show_add_profile_dialog(app, "backup", {"key": "value"})
        return dialog, entry, confirm_dialog

    def test_creates_profile_with_valid_name(self):
        app = self._make_app()
        on_success = MagicMock()

        with patch.object(profile_dialogs, "create_profile", return_value={
            "profile_name": "root-backup-nightly",
        }) as mock_create, \
             patch.object(profile_dialogs, "profile_exists", return_value=False), \
             patch.object(schedule_page, "_refresh_profile_list") as mock_refresh:
            dialog, _, _ = self._run_add_dialog(
                app, profile_dialogs.Gtk.ResponseType.OK, "nightly"
            )

        mock_create.assert_called_once_with(
            "backup", "nightly", {"key": "value"}, dry_run=False
        )
        on_success.assert_not_called()  # no callback passed in helper
        mock_refresh.assert_called_once_with(app)

    def test_calls_on_success_callback(self):
        app = self._make_app()
        on_success = MagicMock()

        with patch.object(profile_dialogs, "create_profile", return_value={
            "profile_name": "root-backup-nightly",
        }) as mock_create, \
             patch.object(profile_dialogs, "profile_exists", return_value=False), \
             patch.object(schedule_page, "_refresh_profile_list"):
            dialog = MagicMock()
            dialog.run.return_value = profile_dialogs.Gtk.ResponseType.OK
            entry = MagicMock()
            entry.get_text.return_value = "nightly"
            with patch.object(profile_dialogs, "create_dialog", return_value=dialog), \
                 patch.object(profile_dialogs.Gtk, "Entry", return_value=entry), \
                 patch.object(profile_dialogs.Gtk, "MessageDialog", return_value=MagicMock()):
                profile_dialogs.show_add_profile_dialog(
                    app, "backup", {"key": "value"}, on_success=on_success
                )

        on_success.assert_called_once_with({"profile_name": "root-backup-nightly"})

    def test_does_nothing_on_cancel(self):
        app = self._make_app()
        with patch.object(profile_dialogs, "create_profile") as mock_create:
            self._run_add_dialog(app, profile_dialogs.Gtk.ResponseType.CANCEL, "nightly")
        mock_create.assert_not_called()

    def test_rejects_empty_name(self):
        app = self._make_app()
        with patch.object(profile_dialogs, "create_profile") as mock_create, \
             patch.object(profile_dialogs.Gtk, "MessageDialog") as mock_error:
            self._run_add_dialog(app, profile_dialogs.Gtk.ResponseType.OK, "")
        mock_create.assert_not_called()
        mock_error.assert_not_called()

    def test_rejects_invalid_characters(self):
        app = self._make_app()
        with patch.object(profile_dialogs, "create_profile") as mock_create:
            dialog, _, _ = self._run_add_dialog(app, profile_dialogs.Gtk.ResponseType.OK, "my profile")
        mock_create.assert_not_called()
        # Error dialog was shown
        self.assertEqual(dialog.destroy.call_count, 1)

    def test_duplicate_profile_no_overwrite(self):
        app = self._make_app()
        with patch.object(profile_dialogs, "create_profile") as mock_create, \
             patch.object(profile_dialogs, "update_profile") as mock_update, \
             patch.object(profile_dialogs, "profile_exists", return_value=True):
            dialog, _, confirm = self._run_add_dialog(
                app, profile_dialogs.Gtk.ResponseType.OK, "daily",
                duplicate_response=profile_dialogs.Gtk.ResponseType.NO,
            )
        mock_create.assert_not_called()
        mock_update.assert_not_called()
        self.assertEqual(dialog.destroy.call_count, 1)
        confirm.destroy.assert_called_once()

    def test_duplicate_profile_overwrites(self):
        app = self._make_app()
        with patch.object(profile_dialogs, "create_profile") as mock_create, \
             patch.object(profile_dialogs, "update_profile", return_value={
                 "profile_name": "root-backup-daily"
             }) as mock_update, \
             patch.object(profile_dialogs, "profile_exists", return_value=True), \
             patch.object(schedule_page, "_refresh_profile_list") as mock_refresh:
            dialog, _, confirm = self._run_add_dialog(
                app, profile_dialogs.Gtk.ResponseType.OK, "daily",
                duplicate_response=profile_dialogs.Gtk.ResponseType.YES,
            )
        mock_create.assert_not_called()
        mock_update.assert_called_once_with(
            "backup", "daily", {"key": "value"}, dry_run=False
        )
        confirm.destroy.assert_called_once()
        mock_refresh.assert_called_once_with(app)

    def test_shows_error_on_create_exception(self):
        app = self._make_app()
        with patch.object(profile_dialogs, "create_profile", side_effect=ValueError("boom")), \
             patch.object(profile_dialogs, "profile_exists", return_value=False):
            dialog, _, _ = self._run_add_dialog(app, profile_dialogs.Gtk.ResponseType.OK, "bad")
        self.assertEqual(dialog.destroy.call_count, 1)


class TestShowRecallProfileDialog(unittest.TestCase):
    """show_recall_profile_dialog lists profiles and calls back on selection."""

    def _make_app(self):
        return MagicMock()

    def _make_view_mock(self, profile_name):
        selection = MagicMock()
        model = MagicMock()
        tree_iter = MagicMock()
        model.get_value.return_value = profile_name
        selection.get_selected.return_value = (model, tree_iter)
        view = MagicMock()
        view.get_selection.return_value = selection
        return view

    def test_shows_error_when_no_profiles(self):
        app = self._make_app()
        on_select = MagicMock()

        with patch.object(profile_dialogs, "list_profiles", return_value=[]), \
             patch.object(profile_dialogs.Gtk, "MessageDialog", return_value=MagicMock()) as mock_error:
            profile_dialogs.show_recall_profile_dialog(app, "backup", on_select)

        mock_error.assert_called_once()
        on_select.assert_not_called()

    def test_calls_on_select_with_chosen_profile(self):
        app = self._make_app()
        on_select = MagicMock()
        profiles = [
            {"profile_name": "root-backup-daily", "tab_type": "backup"},
        ]
        loaded = {"profile_name": "root-backup-daily", "config": {}}
        view = self._make_view_mock("root-backup-daily")
        dialog = MagicMock()
        dialog.run.return_value = profile_dialogs.Gtk.ResponseType.OK

        with patch.object(profile_dialogs, "list_profiles", return_value=profiles), \
             patch.object(profile_dialogs, "load_profile", return_value=loaded) as mock_load, \
             patch.object(profile_dialogs, "create_dialog", return_value=dialog), \
             patch.object(profile_dialogs.Gtk, "TreeView", return_value=view):
            profile_dialogs.show_recall_profile_dialog(app, "backup", on_select)

        mock_load.assert_called_once_with("root-backup-daily")
        on_select.assert_called_once_with(loaded)

    def test_does_not_call_on_select_on_cancel(self):
        app = self._make_app()
        on_select = MagicMock()
        profiles = [
            {"profile_name": "root-backup-daily", "tab_type": "backup"},
        ]
        dialog = MagicMock()
        dialog.run.return_value = profile_dialogs.Gtk.ResponseType.CANCEL

        with patch.object(profile_dialogs, "list_profiles", return_value=profiles), \
             patch.object(profile_dialogs, "create_dialog", return_value=dialog), \
             patch.object(profile_dialogs.Gtk, "TreeView", return_value=MagicMock()):
            profile_dialogs.show_recall_profile_dialog(app, "backup", on_select)

        on_select.assert_not_called()


if __name__ == "__main__":
    unittest.main()
