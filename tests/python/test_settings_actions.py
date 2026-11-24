"""Tests for the Settings-menu backup/restore handlers in zfsutilities_gui."""

import contextlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import requires_gi

pytestmark = requires_gi


@pytest.fixture(autouse=True)
def _ensure_real_gui_module():
    """Bind the real zfsutilities_gui before the patches resolve their targets.

    Same rationale as test_zfsutilities_gui: a mock_gtk()-bound copy can be
    left cached in sys.modules by another suite under pytest-xdist, and the
    patches below must target the same module object the test body runs
    against. The suite is skipped wholesale via pytestmark when gi is
    unavailable.
    """
    cached = sys.modules.get("zfsutilities_gui")
    if cached is not None and isinstance(getattr(cached, "Gtk", None), MagicMock):
        sys.modules.pop("zfsutilities_gui", None)
    import zfsutilities_gui  # noqa: F401


def _gui_module():
    """Return the zfsutilities_gui module the patches below target."""
    return sys.modules["zfsutilities_gui"]


def _make_window(gui):
    """Create a ZFSUtilitiesWindow with __init__ bypassed."""
    with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
        window = gui.ZFSUtilitiesWindow()
        window.config = {"old": True}
        window.on_refresh = MagicMock()
        return window


@contextlib.contextmanager
def _handler_surface(raw_replies=()):
    """Patch the module surface the settings handlers touch.

    Gtk is a MagicMock so no real widgets are built; run_dialog replies are
    given as "OK"/"CANCEL" strings mapped onto the patched ResponseType
    constants; find_script and subprocess are pinned so no real script
    runs; log_msg is captured. Yields the module plus its pinned mocks.
    """
    gui = _gui_module()
    gtk_mock = MagicMock()
    replies = [
        gtk_mock.ResponseType.OK if r == "OK" else gtk_mock.ResponseType.CANCEL for r in raw_replies
    ]
    combo = gtk_mock.ComboBoxText.return_value
    combo.get_active.return_value = 0
    patches = [
        patch.object(gui, "Gtk", gtk_mock),
        patch.object(gui, "run_dialog", side_effect=replies),
        patch.object(gui, "log_msg"),
        patch.object(gui, "find_script", return_value="/backup-settings"),
        patch.object(gui, "subprocess"),
    ]
    for p in patches:
        p.start()
    try:
        yield gui, gtk_mock, gui.subprocess, gui.log_msg
    finally:
        for p in patches:
            p.stop()


def _logged(log_mock):
    return " ".join(str(c.args[0]) for c in log_mock.call_args_list)


class TestBackupSettingsHandler(unittest.TestCase):
    """Settings -> Backup Settings: confirm, run, relay, verdict."""

    def test_backup_runs_script_after_confirm(self):
        with _handler_surface(["OK"]) as (gui, gtk_mock, subprocess_mock, log_mock):
            subprocess_mock.run.return_value = MagicMock(
                returncode=0, stdout="INFO: ok\n", stderr=""
            )
            window = _make_window(gui)
            window.on_backup_settings(None)

        subprocess_mock.run.assert_called_once()
        cmd = subprocess_mock.run.call_args[0][0]
        self.assertEqual(cmd, ["/backup-settings"])
        # The confirm dialog names the destination.
        self.assertIn("every online pool", gtk_mock.MessageDialog.call_args.kwargs["text"])
        self.assertIn("Settings backup finished", _logged(log_mock))
        # Script output lines are relayed verbatim (level token intact).
        self.assertIn("INFO: ok", _logged(log_mock))

    def test_backup_cancelled_before_running(self):
        with _handler_surface(["CANCEL"]) as (gui, _gtk, subprocess_mock, log_mock):
            window = _make_window(gui)
            window.on_backup_settings(None)
        subprocess_mock.run.assert_not_called()
        self.assertIn("Settings backup cancelled", _logged(log_mock))

    def test_backup_missing_script_warns(self):
        with _handler_surface(["OK"]) as (gui, _gtk, subprocess_mock, log_mock):
            gui.find_script.return_value = None
            window = _make_window(gui)
            window.on_backup_settings(None)
        subprocess_mock.run.assert_not_called()
        self.assertIn("backup-settings not found", _logged(log_mock))

    def test_backup_failure_is_reported(self):
        with _handler_surface(["OK"]) as (gui, _gtk, subprocess_mock, log_mock):
            subprocess_mock.run.return_value = MagicMock(
                returncode=1, stdout="", stderr="FATAL: boom\n"
            )
            window = _make_window(gui)
            window.on_backup_settings(None)
        self.assertIn("Settings backup failed (exit 1)", _logged(log_mock))
        self.assertIn("FATAL: boom", _logged(log_mock))

    def test_run_script_timeout_is_reported(self):
        import subprocess as real_subprocess

        gui = _gui_module()
        with (
            patch.object(gui, "log_msg") as log_mock,
            patch.object(gui, "find_script", return_value="/backup-settings"),
            patch.object(gui, "subprocess") as subprocess_mock,
        ):
            # The handler's except clause reads TimeoutExpired off the
            # patched module, so bind the real class there and raise a
            # real instance (a mock instance would not be raised at all).
            subprocess_mock.TimeoutExpired = real_subprocess.TimeoutExpired
            subprocess_mock.run.side_effect = real_subprocess.TimeoutExpired(cmd="x", timeout=1)
            window = _make_window(gui)
            result = window._run_settings_script([])
            self.assertIsNone(result)
            self.assertIn("did not finish", _logged(log_mock))


class TestRestoreSettingsHandler(unittest.TestCase):
    """Settings -> Restore Settings: list, pick, confirm, run, reload."""

    LIST_STDOUT = "20261124T110000|fivebays|7\n20261123T110000|NVME1|7\n"

    def test_restore_runs_and_reloads_config(self):
        sentinel = {"restored": True}
        with _handler_surface(["OK", "OK"]) as (gui, gtk_mock, subprocess_mock, log_mock):
            subprocess_mock.run.side_effect = [
                MagicMock(returncode=0, stdout=self.LIST_STDOUT, stderr=""),
                MagicMock(returncode=0, stdout="INFO: done\n", stderr=""),
            ]
            window = _make_window(gui)
            with patch.object(gui, "load_config", return_value=sentinel):
                window.on_restore_settings(None)

        # The picker offered one row per backup.
        combo = gtk_mock.ComboBoxText.return_value
        texts = [c.args[0] for c in combo.append_text.call_args_list]
        self.assertEqual(len(texts), 2)
        self.assertIn("20261124T110000", texts[0])
        # The list ran first, then the restore of the chosen timestamp.
        cmds = [c.args[0] for c in subprocess_mock.run.call_args_list]
        self.assertEqual(
            cmds,
            [
                ["/backup-settings", "--list"],
                ["/backup-settings", "--restore", "20261124T110000"],
            ],
        )
        # The restored config replaced the in-memory dict and the visible
        # page was refreshed.
        self.assertIs(window.config, sentinel)
        window.on_refresh.assert_called_once()
        self.assertIn("Settings restored", _logged(log_mock))

    def test_restore_no_backups_warns(self):
        with _handler_surface([]) as (gui, gtk_mock, subprocess_mock, log_mock):
            subprocess_mock.run.return_value = MagicMock(returncode=0, stdout="\n", stderr="")
            window = _make_window(gui)
            window.on_restore_settings(None)

        self.assertEqual(subprocess_mock.run.call_count, 1)
        gtk_mock.ComboBoxText.return_value.append_text.assert_not_called()
        self.assertIn("No settings backups found", _logged(log_mock))

    def test_restore_cancelled_at_confirm(self):
        with _handler_surface(["OK", "CANCEL"]) as (gui, _gtk, subprocess_mock, log_mock):
            subprocess_mock.run.return_value = MagicMock(
                returncode=0, stdout=self.LIST_STDOUT, stderr=""
            )
            window = _make_window(gui)
            window.on_restore_settings(None)

        # Only the --list ran; no restore, no reload.
        self.assertEqual(subprocess_mock.run.call_count, 1)
        window.on_refresh.assert_not_called()
        self.assertIn("Settings restore cancelled", _logged(log_mock))
