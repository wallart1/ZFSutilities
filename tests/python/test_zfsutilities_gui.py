"""Tests for zfsutilities_gui.py window behavior."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk, mock_subprocess


def _import_gui_under_mock():
    """Import zfsutilities_gui while GTK is mocked.

    Importing at module level would load real gi.repository modules and
    break other GUI tests in the same process.  This helper keeps the import
    scoped inside mock_gtk().
    """
    with mock_gtk():
        import zfsutilities_gui as gui
        return gui


class TestCheckPeerVersionAsync(unittest.TestCase):
    """Unit tests for ZFSUtilitiesWindow._check_peer_version_async."""

    def _make_window(self, version="1.2.3"):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _import_gui_under_mock()
        with patch.object(
            gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None
        ):
            window = gui.ZFSUtilitiesWindow()
            window._version = version
            return window, gui

    @patch("zfsutilities_gui._get_peer_host", return_value=None)
    @patch("zfsutilities_gui.threading.Thread")
    def test_single_node_does_not_spawn_thread(self, mock_thread, _mock_peer):
        window, gui = self._make_window()
        window._check_peer_version_async()
        mock_thread.assert_not_called()

    @patch("zfsutilities_gui._get_peer_host", return_value="compute1")
    @patch("zfsutilities_gui._get_host_version", return_value="1.2.3")
    @patch("zfsutilities_gui.GLib.idle_add")
    @patch("zfsutilities_gui.threading.Thread")
    def test_two_node_spawns_daemon_thread(
        self, mock_thread, mock_idle, _mock_host, _mock_peer
    ):
        window, gui = self._make_window("1.2.3")
        window._check_peer_version_async()

        mock_thread.assert_called_once()
        self.assertTrue(mock_thread.call_args.kwargs.get("daemon"))

        # Run the thread target synchronously to verify the idle callback.
        target = mock_thread.call_args.kwargs["target"]
        target()
        mock_idle.assert_called_once_with(
            gui._log_peer_version_result, "1.2.3", "compute1", "1.2.3"
        )

    @patch("zfsutilities_gui._get_peer_host", return_value="compute1")
    @patch("zfsutilities_gui._get_host_version", return_value="1.2.4")
    @patch("zfsutilities_gui.GLib.idle_add")
    @patch("zfsutilities_gui.threading.Thread")
    def test_two_node_mismatch_passed_to_idle(
        self, mock_thread, mock_idle, _mock_host, _mock_peer
    ):
        window, gui = self._make_window("1.2.3")
        window._check_peer_version_async()

        target = mock_thread.call_args.kwargs["target"]
        target()
        mock_idle.assert_called_once_with(
            gui._log_peer_version_result, "1.2.3", "compute1", "1.2.4"
        )

    @patch("zfsutilities_gui._get_peer_host", return_value="compute1")
    @patch("zfsutilities_gui._get_host_version", return_value="unknown")
    @patch("zfsutilities_gui.GLib.idle_add")
    @patch("zfsutilities_gui.threading.Thread")
    def test_two_node_unreachable_passed_to_idle(
        self, mock_thread, mock_idle, _mock_host, _mock_peer
    ):
        window, gui = self._make_window("1.2.3")
        window._check_peer_version_async()

        target = mock_thread.call_args.kwargs["target"]
        target()
        mock_idle.assert_called_once_with(
            gui._log_peer_version_result, "1.2.3", "compute1", "unknown"
        )


class TestLogMessageDisplayFilter(unittest.TestCase):
    """Tests for ZFSUtilitiesWindow.log_message display filtering."""

    def _make_window(self):
        gui = _import_gui_under_mock()
        with patch.object(
            gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None
        ):
            window = gui.ZFSUtilitiesWindow()
            buffer_mock = MagicMock()
            buffer_mock.get_tag_table.return_value = MagicMock()
            text_view = MagicMock()
            text_view.get_buffer.return_value = buffer_mock
            window.info_text = text_view
            window.log_scrolled = MagicMock()
            window._info_panel_level = "INFO"
            window._info_panel_short_prefix = True
            window._info_panel_lines = []
            window._log_status_level = None
            return window, buffer_mock

    def _prefix(self, msg):
        return f"/path/file:10: {msg}"

    def test_stores_all_lines(self):
        window, _buf = self._make_window()
        window.log_message(self._prefix("INFO: one"))
        window.log_message(self._prefix("DEBUG: two"))
        self.assertEqual(len(window._info_panel_lines), 2)

    def test_inserts_visible_lines(self):
        window, buf = self._make_window()
        window.log_message(self._prefix("INFO: one"))
        window.log_message(self._prefix("DEBUG: two"))
        self.assertEqual(buf.insert.call_count, 1)
        self.assertIn("INFO: one", buf.insert.call_args[0][1])

    def test_hides_filtered_lines(self):
        window, buf = self._make_window()
        window._info_panel_level = "WARN"
        window.log_message(self._prefix("INFO: one"))
        window.log_message(self._prefix("WARN: two"))
        self.assertEqual(buf.insert.call_count, 1)
        self.assertIn("WARN: two", buf.insert.call_args[0][1])

    def test_raw_lines_are_always_visible(self):
        window, buf = self._make_window()
        window._info_panel_level = "FATAL"
        window.log_message("raw subprocess output")
        self.assertEqual(buf.insert.call_count, 1)
        self.assertIn("raw subprocess output", buf.insert.call_args[0][1])

    def test_updates_status_for_hidden_warnings(self):
        window, _buf = self._make_window()
        window._info_panel_level = "FATAL"
        window.log_message(self._prefix("WARN: hidden"))
        self.assertEqual(window._log_status_level, "WARN")

    def test_render_info_panel_re_filters(self):
        window, buf = self._make_window()
        window.log_message(self._prefix("DEBUG: one"))
        window.log_message(self._prefix("INFO: two"))
        window._info_panel_level = "DEBUG"
        buf.insert.reset_mock()
        buf.set_text.reset_mock()
        with patch("zfsutilities_gui.GLib.idle_add"):
            window._render_info_panel()
        self.assertEqual(buf.set_text.call_count, 1)
        self.assertEqual(buf.insert.call_count, 2)

    def test_default_short_prefix_strips_file_line(self):
        window, buf = self._make_window()
        window.log_message(self._prefix("INFO: one"))
        inserted = buf.insert.call_args[0][1]
        self.assertIn("2026-", inserted)
        self.assertIn("INFO: one", inserted)
        self.assertNotIn("/path/file:10:", inserted)

    def test_long_prefix_shows_file_line(self):
        window, buf = self._make_window()
        window._info_panel_short_prefix = False
        window.log_message(self._prefix("INFO: one"))
        inserted = buf.insert.call_args[0][1]
        self.assertIn("/path/file:10:", inserted)
        self.assertIn("INFO: one", inserted)

    def test_short_prefix_toggle_re_renders(self):
        window, buf = self._make_window()
        window.log_message(self._prefix("INFO: one"))
        buf.set_text.reset_mock()
        buf.insert.reset_mock()
        button = MagicMock()
        button.get_active.return_value = False
        with patch("zfsutilities_gui.GLib.idle_add"):
            window._on_info_short_prefix_toggled(button)
        self.assertFalse(window._info_panel_short_prefix)
        self.assertEqual(buf.set_text.call_count, 1)
        inserted = "".join(call[0][1] for call in buf.insert.call_args_list)
        self.assertIn("/path/file:10:", inserted)


class TestDryRunToggle(unittest.TestCase):
    """Tests for the Dry Run toggle button."""

    def _make_window(self):
        gui = _import_gui_under_mock()
        with patch.object(
            gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None
        ):
            window = gui.ZFSUtilitiesWindow()
            window.action_box = MagicMock()
            return window, gui

    def test_add_dry_run_toggle_creates_button_with_image_and_label(self):
        window, gui = self._make_window()
        mock_gtk = MagicMock()
        with patch.object(gui, "Gtk", mock_gtk):
            button = window.add_dry_run_toggle()

        self.assertIs(button, mock_gtk.ToggleButton.return_value)
        box = mock_gtk.Box.return_value
        box.pack_start.assert_any_call(
            mock_gtk.Image.new_from_icon_name.return_value, False, False, 0
        )
        box.pack_start.assert_any_call(
            mock_gtk.Label.return_value, False, False, 0
        )
        window.action_box.pack_start.assert_called_once_with(
            button, False, False, 0
        )

    def test_toggling_dry_run_persists_state_and_updates_label(self):
        window, gui = self._make_window()
        mock_gtk = MagicMock()
        with patch.object(gui, "Gtk", mock_gtk):
            button = window.add_dry_run_toggle()
        label = mock_gtk.Label.return_value
        button.get_active.return_value = True

        window._on_dry_run_toggled(button, label)

        self.assertTrue(window._dry_run_active)
        label.set_markup.assert_called_with(
            "<span color='red'>Dry Run</span>"
        )


class TestDatasetRunnerIntegration(unittest.TestCase):
    """Dataset action runner is created and receives forwarded stdin input."""

    def test_dataset_runner_created(self):
        gui = _import_gui_under_mock()
        with patch.object(gui.ZFSUtilitiesWindow, "create_sidebar_and_stack"), \
             patch.object(gui.ZFSUtilitiesWindow, "create_action_panel"), \
             patch("zfsutilities_gui.create_menu_bar"), \
             patch("zfsutilities_gui.create_info_panel"), \
             patch("zfsutilities_gui.UIStateManager"), \
             patch("zfsutilities_gui.RunnerFactory") as mock_factory:

            mock_factory_instance = MagicMock()
            mock_factory.return_value = mock_factory_instance

            def _make_runner(label):
                runner = MagicMock()
                runner.label = label
                return runner

            mock_factory_instance.create.side_effect = _make_runner

            window = gui.ZFSUtilitiesWindow(application=None)

        labels = [c.args[0] for c in mock_factory_instance.create.call_args_list]
        self.assertIn("Dataset action", labels)
        self.assertEqual(window.dataset_runner.label, "Dataset action")

    def test_input_forwarded_to_dataset_runner(self):
        gui = _import_gui_under_mock()
        with patch.object(
            gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None
        ):
            window = gui.ZFSUtilitiesWindow()
            window.backup_runner = None
            window.offsite_runner = None
            window.restore_runner = None
            window.retention_runner = None
            window.dataset_runner = MagicMock()
            window.dataset_runner.running = True
            window.stdin_entry = MagicMock()
            window.stdin_entry.get_text.return_value = "yes\n"

            with patch("zfsutilities_gui.log_msg"):
                window._send_stdin_text()

            window.dataset_runner.send_input.assert_called_once_with("yes\n")


class TestDashboardTimer(unittest.TestCase):
    """Tests for ZFSUtilitiesWindow dashboard/scrub timer lifecycle."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _import_gui_under_mock()
        with patch.object(
            gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None
        ):
            window = gui.ZFSUtilitiesWindow()
            window._dashboard_timer = None
            window._scrub_timer = None
            window.stack = MagicMock()
            return window

    @patch("zfsutilities_gui.GLib")
    def test_dashboard_page_starts_timer(self, mock_glib):
        """Switching to Dashboard starts a 30-second refresh timer."""
        window = self._make_window()
        mock_glib.timeout_add_seconds.return_value = 42
        window._start_stop_dashboard_timer("dashboard")
        mock_glib.timeout_add_seconds.assert_called_once_with(
            30, window._on_dashboard_timer_tick
        )
        self.assertEqual(window._dashboard_timer, 42)

    @patch("zfsutilities_gui.GLib")
    def test_non_dashboard_page_stops_timer(self, mock_glib):
        """Switching away from Dashboard removes the timer."""
        window = self._make_window()
        window._dashboard_timer = 7
        window._start_stop_dashboard_timer("backup")
        mock_glib.source_remove.assert_called_once_with(7)
        self.assertIsNone(window._dashboard_timer)

    @patch("zfsutilities_gui.GLib")
    def test_dashboard_timer_replaces_existing_timer(self, mock_glib):
        """Re-entering Dashboard cancels the old timer before starting a new one."""
        window = self._make_window()
        window._dashboard_timer = 7
        mock_glib.timeout_add_seconds.return_value = 42
        window._start_stop_dashboard_timer("dashboard")
        mock_glib.source_remove.assert_called_once_with(7)
        mock_glib.timeout_add_seconds.assert_called_once_with(
            30, window._on_dashboard_timer_tick
        )
        self.assertEqual(window._dashboard_timer, 42)


class TestScheduleTimer(unittest.TestCase):
    """Tests for ZFSUtilitiesWindow schedule refresh timer lifecycle."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _import_gui_under_mock()
        with patch.object(
            gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None
        ):
            window = gui.ZFSUtilitiesWindow()
            window._schedule_timer = None
            window.stack = MagicMock()
            return window

    @patch("zfsutilities_gui.GLib")
    def test_schedule_page_starts_timer(self, mock_glib):
        """Switching to Schedule starts a 60-second refresh timer."""
        window = self._make_window()
        mock_glib.timeout_add_seconds.return_value = 42
        window._start_stop_schedule_timer("schedule")
        mock_glib.timeout_add_seconds.assert_called_once_with(
            60, window._on_schedule_timer_tick
        )
        self.assertEqual(window._schedule_timer, 42)

    @patch("zfsutilities_gui.GLib")
    def test_non_schedule_page_stops_timer(self, mock_glib):
        """Switching away from Schedule removes the timer."""
        window = self._make_window()
        window._schedule_timer = 7
        window._start_stop_schedule_timer("backup")
        mock_glib.source_remove.assert_called_once_with(7)
        self.assertIsNone(window._schedule_timer)

    @patch("zfsutilities_gui.GLib")
    @patch("zfsutilities_gui.refresh_schedule_page")
    def test_schedule_timer_tick_refreshes_when_visible(
        self, mock_refresh, mock_glib
    ):
        """The timer callback refreshes Schedule only while it is visible."""
        window = self._make_window()
        window.stack.get_visible_child_name.return_value = "schedule"
        result = window._on_schedule_timer_tick()
        mock_refresh.assert_called_once_with(window)
        self.assertTrue(result)

    @patch("zfsutilities_gui.GLib")
    @patch("zfsutilities_gui.refresh_schedule_page")
    def test_schedule_timer_tick_skips_when_hidden(
        self, mock_refresh, mock_glib
    ):
        """The timer callback does nothing when another tab is visible."""
        window = self._make_window()
        window.stack.get_visible_child_name.return_value = "backup"
        result = window._on_schedule_timer_tick()
        mock_refresh.assert_not_called()
        self.assertTrue(result)


class TestOnPageChanged(unittest.TestCase):
    """Tests for ZFSUtilitiesWindow.on_page_changed per-tab refresh hooks."""

    def _make_window(self, config=None):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _import_gui_under_mock()
        with patch.object(
            gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None
        ):
            window = gui.ZFSUtilitiesWindow()
            cfg = config if config is not None else {"pools": []}
            window.config = cfg
            window.ctx = MagicMock()
            window.ctx.config = cfg
            window.offsite_detected_label = MagicMock()
            window.update_action_buttons = MagicMock()
            window._start_stop_dashboard_timer = MagicMock()
            window._start_stop_scrub_timer = MagicMock()
            window._start_stop_schedule_timer = MagicMock()
            return window

    def test_offsite_page_refreshes_detected_pool(self):
        """Switching to the Offsite tab re-runs offsite pool detection."""
        config = {
            "pools": [{"name": "z40tb", "offsite_candidate": True}],
        }
        window = self._make_window(config)
        stack = MagicMock()
        stack.get_visible_child_name.return_value = "offsite"

        with mock_subprocess() as m:
            m.add_zpool_list([{"name": "z40tb", "health": "ONLINE"}])
            window.on_page_changed(stack, None)

        window.update_action_buttons.assert_called_once_with("offsite")
        window.offsite_detected_label.set_markup.assert_called_once()
        args = window.offsite_detected_label.set_markup.call_args[0]
        self.assertIn("z40tb", args[0])

    def test_offsite_page_shows_no_candidates(self):
        """Switching to Offsite shows 'no candidates' when none are configured."""
        window = self._make_window({"pools": []})
        stack = MagicMock()
        stack.get_visible_child_name.return_value = "offsite"

        window.on_page_changed(stack, None)

        window.offsite_detected_label.set_text.assert_called_once_with(
            "(no candidates configured)"
        )

    @patch("restore_page.refresh_restore_destination")
    def test_restore_page_refreshes_destination(self, mock_refresh):
        """Switching to the Restore tab refreshes the auto-computed destination."""
        window = self._make_window({"pools": []})
        stack = MagicMock()
        stack.get_visible_child_name.return_value = "restore"

        window.on_page_changed(stack, None)

        window.update_action_buttons.assert_called_once_with("restore")
        mock_refresh.assert_called_once_with(window)

    @patch("zfsutilities_gui.refresh_schedule_page")
    def test_schedule_page_refreshes(self, mock_refresh):
        """Switching to the Schedule tab refreshes the profile list."""
        window = self._make_window({"pools": []})
        stack = MagicMock()
        stack.get_visible_child_name.return_value = "schedule"

        window.on_page_changed(stack, None)

        window.update_action_buttons.assert_called_once_with("schedule")
        mock_refresh.assert_called_once_with(window)
        window._start_stop_schedule_timer.assert_called_once_with("schedule")

    @patch("zfsutilities_gui.refresh_dashboard_page")
    def test_dashboard_page_refreshes(self, mock_refresh):
        """Switching to the Dashboard tab refreshes the dashboard immediately."""
        window = self._make_window({"pools": []})
        stack = MagicMock()
        stack.get_visible_child_name.return_value = "dashboard"

        window.on_page_changed(stack, None)

        window.update_action_buttons.assert_called_once_with("dashboard")
        window._start_stop_dashboard_timer.assert_called_once_with("dashboard")
        mock_refresh.assert_called_once_with(window)


class TestUpdateActionButtonsGuard(unittest.TestCase):
    """update_action_buttons() only rebuilds the panel for the visible page."""

    def _make_window(self, visible_page="retention"):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _import_gui_under_mock()
        with patch.object(
            gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None
        ):
            window = gui.ZFSUtilitiesWindow()
            window.action_box = MagicMock()
            window.action_box.get_children.return_value = [MagicMock()]
            window.stack = MagicMock()
            window.stack.get_visible_child_name.return_value = visible_page
            window._dry_run_active = False
            return window, gui

    def test_rebuilds_when_requested_page_is_visible(self):
        """A synchronous call for the current page rebuilds the action panel."""
        window, gui = self._make_window("retention")
        fake_specs = {
            "retention": {
                "buttons": [("Save", "document-save", "_ret_save_button")],
            },
        }
        with patch.object(gui, "PAGE_SPECS", fake_specs):
            window.update_action_buttons("retention")

        window.action_box.remove.assert_called_once()
        window.action_box.show_all.assert_called_once()

    def test_ignores_stale_request_for_hidden_page(self):
        """An async callback for a page no longer visible must not overwrite
        the current page's action buttons."""
        window, gui = self._make_window("logs")
        fake_specs = {
            "retention": {
                "buttons": [("Save", "document-save", "_ret_save_button")],
            },
        }
        with patch.object(gui, "PAGE_SPECS", fake_specs):
            window.update_action_buttons("retention")

        window.action_box.remove.assert_not_called()
        window.action_box.show_all.assert_not_called()

    def test_rebuilds_after_switching_back_to_page(self):
        """When the user returns to the original page, the panel refreshes."""
        window, gui = self._make_window("logs")
        fake_specs = {
            "retention": {
                "buttons": [("Save", "document-save", "_ret_save_button")],
            },
        }
        with patch.object(gui, "PAGE_SPECS", fake_specs):
            window.update_action_buttons("retention")
            window.action_box.remove.assert_not_called()

            window.stack.get_visible_child_name.return_value = "retention"
            window.update_action_buttons("retention")

        window.action_box.remove.assert_called()
        window.action_box.show_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()
