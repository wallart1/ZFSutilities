"""Tests for restore_page.py — Restore tab UI construction and behavior."""

import os
import sys
import unittest
from typing import ClassVar
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk

with mock_gtk():
    import restore_page as rp


class _FakeStyleContext:
    """Records style classes added to / removed from a widget."""

    def __init__(self):
        self.classes = set()

    def add_class(self, name):
        self.classes.add(name)

    def remove_class(self, name):
        self.classes.discard(name)


def _recording_style_context(widget):
    """Return the widget's style context, creating a recording one on demand."""
    context = getattr(widget, "_style_context", None)
    if context is None:
        context = _FakeStyleContext()
        widget._style_context = context
    return context


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

    def connect(self, signal, callback, *args):
        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks[signal] = callback

    def set_hexpand(self, *args):
        pass

    def set_width_chars(self, *args):
        pass

    def set_tooltip_text(self, *args):
        pass

    def set_halign(self, *args):
        pass

    def get_style_context(self):
        return _recording_style_context(self)


class _FakeCheckButton:
    """CheckButton-like fake that records its active state."""

    def __init__(self, active=False, *args, **kwargs):
        self._active = active

    def set_active(self, active):
        self._active = active

    def get_active(self):
        return self._active

    def connect(self, signal, callback, *args):
        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks[signal] = callback

    def set_tooltip_text(self, *args):
        pass

    def set_hexpand(self, *args):
        pass

    def get_style_context(self):
        return _recording_style_context(self)


class _FakeComboBoxText:
    """ComboBoxText-like fake for Y/N advanced variables."""

    def __init__(self, value="Y"):
        self._items = []
        self._active = 0 if value == "Y" else 1

    def append_text(self, text):
        self._items.append(text)

    def set_active(self, active):
        self._active = active

    def get_active(self):
        return self._active

    def get_active_text(self):
        if self._items and 0 <= self._active < len(self._items):
            return self._items[self._active]
        return "Y" if self._active == 0 else "N"

    def connect(self, *args):
        pass

    def get_style_context(self):
        return _recording_style_context(self)


class _FakeApp:
    config: ClassVar[dict] = {}
    ctx = MagicMock()
    ctx.config: ClassVar[dict] = {"pools": [{"name": "threeamigos"}, {"name": "fivebays"}]}


def _restore_app(source="", dest="", auto_dest=False, recursive=False):
    """Return an app mock with the widgets required by restore_page helpers."""
    app = _FakeApp()
    app.restore_source_entry = _FakeEntry(source)
    app.restore_dest_entry = _FakeEntry(dest)
    app.restore_auto_dest_check = _FakeCheckButton(auto_dest)
    app.restore_recursive_check = _FakeCheckButton(recursive)
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


class TestCollectRestoreConfig(unittest.TestCase):
    """Tests for collect_restore_config."""

    def test_collects_recursive_flag(self):
        app = _restore_app(recursive=True)
        app.restore_part1_check._active = True
        app.restore_part2_check._active = False
        cfg = rp.collect_restore_config(app)
        self.assertTrue(cfg["recursive"])

    def test_default_recursive_flag_is_false(self):
        app = _restore_app()
        cfg = rp.collect_restore_config(app)
        self.assertFalse(cfg["recursive"])

    def test_collects_verify_after_transfer_and_pv_rate_limit(self):
        app = _restore_app()
        app.restore_var_widgets = {
            "verify_after_transfer": _FakeComboBoxText("N"),
            "pv_rate_limit": _FakeEntry("50M"),
        }
        cfg = rp.collect_restore_config(app)
        self.assertEqual(cfg["variables"]["verify_after_transfer"], "N")
        self.assertEqual(cfg["variables"]["pv_rate_limit"], "50M")


class TestLoadRestoreConfig(unittest.TestCase):
    """Tests for load_restore_config."""

    def test_loads_recursive_flag(self):
        app = _restore_app()
        rp.load_restore_config(
            app,
            {
                "source": "a/b",
                "dest": "c/b",
                "auto_dest": False,
                "recursive": True,
                "variables": {},
                "do_part1": True,
                "do_part2": True,
                "pause_scrubs": False,
            },
        )
        self.assertTrue(app.restore_recursive_check.get_active())

    def test_loads_verify_after_transfer_and_pv_rate_limit(self):
        app = _restore_app()
        app.restore_var_widgets = {
            "verify_after_transfer": _FakeComboBoxText("Y"),
            "pv_rate_limit": _FakeEntry(),
        }
        rp.load_restore_config(
            app,
            {
                "source": "a/b",
                "dest": "c/b",
                "auto_dest": False,
                "recursive": False,
                "variables": {
                    "verify_after_transfer": "N",
                    "pv_rate_limit": "75M",
                },
                "do_part1": True,
                "do_part2": True,
                "pause_scrubs": False,
            },
        )
        self.assertEqual(app.restore_var_widgets["verify_after_transfer"].get_active_text(), "N")
        self.assertEqual(app.restore_var_widgets["pv_rate_limit"].get_text(), "75M")


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

        with (
            patch.object(rp.Gtk, "MessageDialog", return_value=dialog_mock),
            patch.object(
                rp,
                "collect_restore_config",
                return_value={
                    "source": "backuppool/threeamigos/data",
                    "dest": "threeamigos/data",
                    "auto_dest": False,
                    "recursive": False,
                    "do_part1": True,
                    "do_part2": False,
                    "variables": {},
                    "pause_scrubs": False,
                },
            ),
            patch.object(rp, "build_restore_command") as mock_build,
            patch.object(rp, "attach_step_scrub_callbacks"),
        ):
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


class _AppNamespace:
    """Real attribute bag so page-assigned callbacks are retrievable."""

    _ui_state = MagicMock()

    def __init__(self):
        self.ctx = MagicMock()
        self.ctx.config = {}
        self.config = {}


class TestRestoreAdvancedLabel(unittest.TestCase):
    """The Advanced expander label turns orange when a child value is non-default."""

    def _create_page(self):
        expander = MagicMock()
        rp.Gtk.Expander.side_effect = [expander]
        rp.Gtk.Frame.side_effect = [MagicMock() for _ in range(3)]

        app = _AppNamespace()

        with (
            patch.object(rp, "_on_auto_dest_toggled"),
            patch.object(rp, "_style_restore_save_button"),
        ):
            rp.create_restore_page(app, app.ctx)
        return app, expander

    def _install_default_widgets(self, app):
        """Replace the advanced widgets with fakes holding default values."""
        defaults = rp.RESTORE_DEFAULTS["variables"]
        widgets = {}
        for key in list(app.restore_var_widgets):
            if key == "verify_after_transfer":
                combo = _StatefulComboBoxText()
                combo.append_text("Y")
                combo.append_text("N")
                combo.set_active(0 if defaults.get(key) == "Y" else 1)
                widgets[key] = combo
            else:
                widgets[key] = _FakeEntry()
                widgets[key].set_text(defaults.get(key, ""))
        app.restore_var_widgets = widgets
        app.restore_pause_scrubs = _FakeCheckButton()
        return app

    def _label_markup(self, expander):
        return expander.get_label_widget.return_value.set_markup.call_args[0][0]

    def test_changed_signals_connected_to_updater(self):
        app, _expander = self._create_page()
        original_widgets = dict(app.restore_var_widgets)
        self._install_default_widgets(app)
        for widget in original_widgets.values():
            _assert_changed_connected(self, widget, app._restore_update_advanced_label)

    def test_default_values_give_plain_label(self):
        app, expander = self._create_page()
        self._install_default_widgets(app)
        app._restore_update_advanced_label()
        self.assertEqual(self._label_markup(expander), "<b>Advanced</b>")

    def test_non_default_var_turns_label_orange(self):
        app, expander = self._create_page()
        self._install_default_widgets(app)
        app.restore_var_widgets["pv_rate_limit"].set_text("50M")
        app._restore_update_advanced_label()
        self.assertIn('foreground="orange"', self._label_markup(expander))

    def test_reverting_var_restores_plain_label(self):
        app, expander = self._create_page()
        self._install_default_widgets(app)
        widget = app.restore_var_widgets["depth"]
        widget.set_text("2")
        app._restore_update_advanced_label()
        widget.set_text("")
        app._restore_update_advanced_label()
        self.assertEqual(self._label_markup(expander), "<b>Advanced</b>")

    def test_pause_scrubs_turns_label_orange(self):
        app, expander = self._create_page()
        self._install_default_widgets(app)
        app.restore_pause_scrubs.set_active(True)
        app._restore_update_advanced_label()
        self.assertIn('foreground="orange"', self._label_markup(expander))

    def test_non_default_var_value_turns_orange(self):
        app, _expander = self._create_page()
        self._install_default_widgets(app)
        app.restore_var_widgets["pv_rate_limit"].set_text("50M")
        app._restore_update_advanced_label()
        context = app.restore_var_widgets["pv_rate_limit"].get_style_context()
        self.assertIn("zfsu-nondefault", context.classes)
        other = app.restore_var_widgets["depth"].get_style_context()
        self.assertNotIn("zfsu-nondefault", other.classes)

    def test_reverting_var_value_removes_orange(self):
        app, _expander = self._create_page()
        self._install_default_widgets(app)
        widget = app.restore_var_widgets["pv_rate_limit"]
        widget.set_text("50M")
        app._restore_update_advanced_label()
        widget.set_text("")
        app._restore_update_advanced_label()
        self.assertNotIn("zfsu-nondefault", widget.get_style_context().classes)

    def test_pause_scrubs_value_turns_orange(self):
        app, _expander = self._create_page()
        self._install_default_widgets(app)
        app.restore_pause_scrubs.set_active(True)
        app._restore_update_advanced_label()
        self.assertIn("zfsu-nondefault", app.restore_pause_scrubs.get_style_context().classes)

    def test_load_config_refreshes_label(self):
        app, expander = self._create_page()
        self._install_default_widgets(app)
        with patch.object(rp, "_on_auto_dest_toggled"):
            rp.load_restore_config(app, {"variables": {"pv_rate_limit": "50M"}})
        self.assertIn('foreground="orange"', self._label_markup(expander))


def _assert_changed_connected(testcase, widget, updater):
    """Assert a widget's "changed" signal is wired to the updater.

    Works both when the widget is a MagicMock (records connect calls) and
    when it is a recording fake (stores the last callback per signal).
    """
    connect = widget.connect
    if hasattr(connect, "call_args_list"):
        connect.assert_any_call("changed", updater)
    else:
        testcase.assertIs(widget._callbacks.get("changed"), updater)


class _StatefulComboBoxText:
    """ComboBoxText stand-in that records items and the active index."""

    def __init__(self, *args, **kwargs):
        self._items = []
        self._active = -1

    def append_text(self, text):
        self._items.append(text)

    def set_active(self, index):
        self._active = index

    def get_active_text(self):
        if 0 <= self._active < len(self._items):
            return self._items[self._active]
        return None

    def connect(self, signal, callback, *args):
        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks[signal] = callback

    def get_style_context(self):
        return _recording_style_context(self)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None


if __name__ == "__main__":
    unittest.main()
