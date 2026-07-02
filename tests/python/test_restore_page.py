"""Tests for restore_page.py — Restore tab UI construction and behavior."""

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
    import restore_page as rp


class _FakeEntry:
    """Entry-like fake that records its text value."""

    def __init__(self, text=""):
        self._text = text

    def set_text(self, text):
        self._text = text

    def get_text(self):
        return self._text

    def set_sensitive(self, sensitive):
        self._sensitive = sensitive

    def get_sensitive(self):
        return getattr(self, "_sensitive", True)

    def connect(self, *args):
        pass

    def set_hexpand(self, *args):
        pass

    def set_width_chars(self, *args):
        pass

    def set_tooltip_text(self, *args):
        pass

    def set_halign(self, *args):
        pass


class _FakeCheckButton:
    """CheckButton-like fake that records its active state."""

    def __init__(self, active=False):
        self._active = active

    def set_active(self, active):
        self._active = active

    def get_active(self):
        return self._active

    def connect(self, *args):
        pass

    def set_tooltip_text(self, *args):
        pass


class _FakeApp:
    config = {}
    ctx = MagicMock()
    ctx.config = {"pools": [{"name": "threeamigos"}, {"name": "fivebays"}]}


def _restore_app(source="", dest="", auto_dest=False):
    """Return an app mock with the widgets required by restore_page helpers."""
    app = _FakeApp()
    app.restore_source_entry = _FakeEntry(source)
    app.restore_dest_entry = _FakeEntry(dest)
    app.restore_auto_dest_check = _FakeCheckButton(auto_dest)
    app.restore_var_widgets = {}
    app.restore_part1_check = _FakeCheckButton()
    app.restore_part2_check = _FakeCheckButton()
    app.restore_pause_scrubs = _FakeCheckButton()
    app._restore_saved_state = None
    return app


class TestRestorePageFrames(unittest.TestCase):
    """Tests for Restore page layout helpers."""

    @patch.object(rp, "_on_auto_dest_toggled")
    @patch.object(rp, "_style_restore_save_button")
    def test_frames_use_bold_label_widgets(self, _mock_style, _mock_auto):
        frames = [MagicMock() for _ in range(3)]
        expanders = [MagicMock() for _ in range(1)]
        rp.Gtk.Frame.side_effect = frames
        rp.Gtk.Expander.side_effect = expanders

        app = MagicMock()
        app.ctx = MagicMock()
        app.ctx.config = {}
        app.config = {}

        rp.create_restore_page(app, app.ctx)

        for frame in frames:
            frame.set_label.assert_not_called()
            frame.set_label_widget.assert_called_once()

        for expander in expanders:
            expander.set_label.assert_not_called()
            expander.set_label_widget.assert_called_once()


class TestRefreshRestoreDestination(unittest.TestCase):
    """Tests for refresh_restore_destination."""

    def test_computes_and_installs_destination_when_auto_active(self):
        app = _restore_app(
            source="backuppool/threeamigos/proxmox/vm-209-disk-0",
            auto_dest=True,
        )
        result = rp.refresh_restore_destination(app)
        self.assertEqual(result, "threeamigos/proxmox/vm-209-disk-0")
        self.assertEqual(
            app.restore_dest_entry.get_text(),
            "threeamigos/proxmox/vm-209-disk-0",
        )

    def test_returns_none_when_auto_inactive(self):
        app = _restore_app(
            source="backuppool/threeamigos/data",
            dest="manual-dest",
            auto_dest=False,
        )
        result = rp.refresh_restore_destination(app)
        self.assertIsNone(result)
        self.assertEqual(app.restore_dest_entry.get_text(), "manual-dest")

    def test_clears_destination_when_source_empty(self):
        app = _restore_app(source="", dest="old-dest", auto_dest=True)
        result = rp.refresh_restore_destination(app)
        self.assertIsNone(result)
        self.assertEqual(app.restore_dest_entry.get_text(), "")

    @patch.object(rp, "log_msg")
    def test_clears_destination_when_no_pool_matches(self, mock_log):
        app = _restore_app(
            source="backuppool/unknownpool/data",
            dest="old-dest",
            auto_dest=True,
        )
        result = rp.refresh_restore_destination(app)
        self.assertIsNone(result)
        self.assertEqual(app.restore_dest_entry.get_text(), "")
        mock_log.assert_called_once()
        self.assertIn("Cannot auto-determine destination", mock_log.call_args[0][0])


class TestAutoDestToggle(unittest.TestCase):
    """Tests for _on_auto_dest_toggled."""

    def test_toggled_on_computes_and_installs_destination(self):
        app = _restore_app(
            source="backuppool/threeamigos/data",
            dest="manual-dest",
            auto_dest=True,
        )
        rp._on_auto_dest_toggled(app)
        self.assertEqual(app.restore_dest_entry.get_text(), "threeamigos/data")
        self.assertEqual(app._restore_manual_dest, "manual-dest")
        self.assertFalse(app.restore_dest_entry.get_sensitive())

    def test_toggled_off_restores_manual_destination(self):
        app = _restore_app(
            source="backuppool/threeamigos/data",
            dest="computed-dest",
            auto_dest=False,
        )
        app._restore_manual_dest = "my-manual-dest"
        rp._on_auto_dest_toggled(app)
        self.assertEqual(app.restore_dest_entry.get_text(), "my-manual-dest")
        self.assertTrue(app.restore_dest_entry.get_sensitive())


class TestSourceChanged(unittest.TestCase):
    """Tests for _on_restore_source_changed."""

    def test_recomputes_destination_when_auto_active(self):
        app = _restore_app(
            source="backuppool/threeamigos/data",
            auto_dest=True,
        )
        rp._on_restore_source_changed(app)
        self.assertEqual(app.restore_dest_entry.get_text(), "threeamigos/data")

    def test_leaves_manual_destination_when_auto_inactive(self):
        app = _restore_app(
            source="backuppool/threeamigos/data",
            dest="manual-dest",
            auto_dest=False,
        )
        rp._on_restore_source_changed(app)
        self.assertEqual(app.restore_dest_entry.get_text(), "manual-dest")


class TestRestoreRunDialog(unittest.TestCase):
    """Tests for on_restore_run() confirmation and start behaviour."""

    def _make_app(self):
        app = _restore_app(
            source="backuppool/threeamigos/data",
            dest="threeamigos/data",
        )
        app.backup_runner = MagicMock()
        app.backup_runner.running = False
        app.offsite_runner = MagicMock()
        app.offsite_runner.running = False
        app.restore_runner = MagicMock()
        app.restore_runner.running = False
        app.restore_runner._runner_log = MagicMock()
        app.clear_log_status = MagicMock()
        app.update_action_buttons = MagicMock()
        app._dry_run_active = False
        return app

    def test_restore_runs_while_backup_active(self):
        """Restore should not bail out just because backup is running."""
        app = self._make_app()
        app.backup_runner.running = True
        app.restore_part1_check._active = True

        dialog_mock = MagicMock()
        dialog_mock.run.return_value = rp.Gtk.ResponseType.OK

        with patch.object(rp.Gtk, "MessageDialog", return_value=dialog_mock), \
             patch.object(rp, "collect_restore_config", return_value={
                 "source": "backuppool/threeamigos/data",
                 "dest": "threeamigos/data",
                 "auto_dest": False,
                 "do_part1": True,
                 "do_part2": False,
                 "variables": {},
                 "pause_scrubs": False,
             }), \
             patch.object(rp, "build_restore_command") as mock_build, \
             patch.object(rp, "attach_step_scrub_callbacks"):
            mock_build.return_value = MagicMock()
            with patch.object(rp, "log_msg") as mock_log:
                rp.on_restore_run(app, app.ctx)

        app.restore_runner.prepare_session_log.assert_called_once()
        app.restore_runner.set_steps.assert_called_once()
        app.restore_runner.start.assert_called_once()
        for call in mock_log.call_args_list:
            msg = call[0][0].lower()
            self.assertNotIn("while backup", msg)
            self.assertNotIn("cannot start", msg)


if __name__ == "__main__":
    unittest.main()
