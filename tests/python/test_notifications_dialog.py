"""Tests for notifications_dialog.py — the File → Notifications… dialog."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs, mock_gtk, requires_gi

pytestmark = requires_gi


def _import_dialog():
    """Import notifications_dialog under a fresh mocked GTK context."""
    sys.modules.pop("notifications_dialog", None)
    with mock_gtk(fresh=True):
        import notifications_dialog

        return notifications_dialog


def _set_entry(widget, text):
    widget.get_text.return_value = text


def _refresh_widgets(dialog):
    """Give every widget a fresh mock.

    mock_gtk's default widget classes share one return_value instance, so
    without this every Entry/ComboBoxText/CheckButton would be the same
    object and per-widget assertions would collide.
    """
    for key, widget in list(dialog._widgets.items()):
        if isinstance(widget, dict):
            for run_type in widget:
                widget[run_type] = MagicMock()
        else:
            dialog._widgets[key] = MagicMock()


def _configure_widgets(dialog):
    """Give the mocked widgets concrete values covering a full settings set."""
    _refresh_widgets(dialog)
    w = dialog._widgets
    w["desktop_mode"].get_active.return_value = 2  # all
    w["email_mode"].get_active.return_value = 1  # failures
    w["smtp_security"].get_active.return_value = 1  # ssl
    for run_type, check in w["desktop_types"].items():
        check.get_active.return_value = run_type != "dataset"
    for run_type, check in w["email_types"].items():
        check.get_active.return_value = run_type == "backup"
    _set_entry(w["smtp_host"], "smtp.example.com")
    w["smtp_port"].get_value.return_value = 465.0
    _set_entry(w["smtp_username"], "user@example.com")
    _set_entry(w["smtp_password"], "hunter2")
    _set_entry(w["smtp_from"], "zfs@example.com")
    _set_entry(w["smtp_to"], "a@example.com, b@example.com")


class TestCollect(unittest.TestCase):
    """_collect reads every widget into the notifications settings shape."""

    def test_collect_maps_widget_state(self):
        module = _import_dialog()
        dialog = module.NotificationsDialog(MagicMock(), {})
        _configure_widgets(dialog)
        data = dialog._collect()

        self.assertEqual(data["desktop"]["mode"], "all")
        self.assertEqual(data["email"]["mode"], "failures")
        self.assertFalse(data["desktop"]["types"]["dataset"])
        self.assertTrue(data["desktop"]["types"]["backup"])
        self.assertTrue(data["email"]["types"]["backup"])
        self.assertFalse(data["email"]["types"]["scrub"])
        self.assertEqual(data["email"]["smtp_host"], "smtp.example.com")
        self.assertEqual(data["email"]["smtp_port"], 465)
        self.assertEqual(data["email"]["smtp_security"], "ssl")
        self.assertEqual(data["email"]["smtp_username"], "user@example.com")
        self.assertEqual(data["email"]["smtp_from"], "zfs@example.com")
        self.assertEqual(data["email"]["smtp_to"], "a@example.com, b@example.com")

    def test_collect_out_of_range_combo_falls_back_to_off(self):
        module = _import_dialog()
        dialog = module.NotificationsDialog(MagicMock(), {})
        _refresh_widgets(dialog)
        dialog._widgets["desktop_mode"].get_active.return_value = 99
        dialog._widgets["email_mode"].get_active.return_value = -1
        data = dialog._collect()
        self.assertEqual(data["desktop"]["mode"], "off")
        self.assertEqual(data["email"]["mode"], "off")


class TestLoad(unittest.TestCase):
    """_load pushes stored settings into the widgets."""

    def test_load_populates_widgets(self):
        module = _import_dialog()
        config = {
            "notifications": {
                "desktop": {"mode": "failures", "types": {"backup": False}},
                "email": {
                    "mode": "all",
                    "types": {},
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 465,
                    "smtp_security": "ssl",
                    "smtp_username": "user@example.com",
                    "smtp_from": "zfs@example.com",
                    "smtp_to": ["a@example.com", "b@example.com"],
                },
            }
        }
        with patch("notifications_dialog.load_smtp_password", return_value="stored-secret"):
            dialog = module.NotificationsDialog(MagicMock(), config)
        # Re-run _load against fresh per-widget mocks: mock_gtk shares one
        # instance per widget class, so the construction-time calls all
        # landed on shared objects and cannot be asserted per widget.
        _refresh_widgets(dialog)
        with patch("notifications_dialog.load_smtp_password", return_value="stored-secret"):
            dialog._load()

        w = dialog._widgets
        desktop_mode_indices = [c.args for c in w["desktop_mode"].set_active.call_args_list]
        self.assertIn((1,), desktop_mode_indices)  # failures
        email_mode_indices = [c.args for c in w["email_mode"].set_active.call_args_list]
        self.assertIn((2,), email_mode_indices)  # all
        w["desktop_types"]["backup"].set_active.assert_called_once_with(False)
        w["desktop_types"]["offsite"].set_active.assert_called_once_with(True)
        w["smtp_host"].set_text.assert_called_once_with("smtp.example.com")
        w["smtp_port"].set_value.assert_called_once_with(465)
        w["smtp_security"].set_active.assert_called_once_with(1)  # ssl
        w["smtp_username"].set_text.assert_called_once_with("user@example.com")
        w["smtp_password"].set_text.assert_called_once_with("stored-secret")
        w["smtp_from"].set_text.assert_called_once_with("zfs@example.com")
        w["smtp_to"].set_text.assert_called_once_with("a@example.com, b@example.com")


class TestTestButtons(unittest.TestCase):
    """The test buttons dispatch through the notifications module."""

    def _dialog(self, module):
        dialog = module.NotificationsDialog(MagicMock(), {})
        _configure_widgets(dialog)
        return dialog

    def test_desktop_test_button_dispatches(self):
        module = _import_dialog()
        dialog = self._dialog(module)
        with patch("notifications_dialog.send_desktop_test") as mock_test:
            dialog._on_test_desktop(MagicMock())
        mock_test.assert_called_once()
        on_done = mock_test.call_args.kwargs.get("on_done")
        self.assertIsNotNone(on_done)
        on_done(False)
        dialog._widgets["desktop_status"].set_text.assert_any_call(
            "Test failed — see the log panel."
        )

    def test_show_password_toggle_flips_visibility(self):
        module = _import_dialog()
        dialog = module.NotificationsDialog(MagicMock(), {})
        _refresh_widgets(dialog)
        check = MagicMock()
        check.get_active.return_value = True
        dialog._on_toggle_password_visibility(check)
        dialog._widgets["smtp_password"].set_visibility.assert_called_once_with(True)
        check.get_active.return_value = False
        dialog._on_toggle_password_visibility(check)
        dialog._widgets["smtp_password"].set_visibility.assert_called_with(False)

    def test_email_test_uses_unsaved_dialog_values(self):
        module = _import_dialog()
        dialog = self._dialog(module)
        with patch("notifications_dialog.send_email_test") as mock_test:
            dialog._on_test_email(MagicMock())
        mock_test.assert_called_once()
        kwargs = mock_test.call_args.kwargs
        self.assertEqual(kwargs.get("password"), "hunter2")
        preview = kwargs.get("config")["notifications"]
        self.assertEqual(preview["email"]["smtp_host"], "smtp.example.com")
        self.assertEqual(preview["email"]["smtp_port"], 465)
        on_done = kwargs.get("on_done")
        on_done(True)
        dialog._widgets["email_status"].set_text.assert_any_call("Test email sent.")


class TestSaveAndRun(unittest.TestCase):
    """OK persists settings and the password; Cancel leaves them alone."""

    def _dialog(self, module):
        dialog = module.NotificationsDialog(MagicMock(), {})
        _configure_widgets(dialog)
        return dialog

    def test_save_persists_settings_and_password(self):
        module = _import_dialog()
        dialog = self._dialog(module)
        with (
            patch("notifications_dialog.save_notifications_config") as mock_save,
            patch("notifications_dialog.save_smtp_password") as mock_password,
            capture_logs() as logs,
        ):
            dialog._save()
        mock_save.assert_called_once()
        _config_arg, data_arg = mock_save.call_args.args
        self.assertEqual(data_arg["desktop"]["mode"], "all")
        self.assertEqual(data_arg["email"]["smtp_port"], 465)
        mock_password.assert_called_once_with("hunter2")
        self.assertTrue(any("Notification settings saved" in line for line in logs))

    def test_run_ok_saves_and_destroys(self):
        module = _import_dialog()
        dialog = self._dialog(module)
        dialog.dialog.run.return_value = module.Gtk.ResponseType.OK
        with (
            patch("notifications_dialog.save_notifications_config"),
            patch("notifications_dialog.save_smtp_password"),
        ):
            dialog.run()
        dialog.dialog.destroy.assert_called_once()

    def test_run_cancel_skips_save(self):
        module = _import_dialog()
        dialog = self._dialog(module)
        dialog.dialog.run.return_value = module.Gtk.ResponseType.CANCEL
        with (
            patch("notifications_dialog.save_notifications_config") as mock_save,
            patch("notifications_dialog.save_smtp_password") as mock_password,
        ):
            dialog.run()
        mock_save.assert_not_called()
        mock_password.assert_not_called()
        dialog.dialog.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
