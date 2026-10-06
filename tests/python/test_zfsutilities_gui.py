"""Tests for zfsutilities_gui.py window behavior."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_subprocess, requires_gi

pytestmark = requires_gi


@pytest.fixture(autouse=True)
def _ensure_real_gui_module():
    """Bind the real zfsutilities_gui before @patch resolves its targets.

    Under pytest-xdist a worker interleaves suites, and a mock_gtk()-bound
    copy of zfsutilities_gui can be left cached in sys.modules by another
    suite. The @patch decorators on the tests below resolve and patch
    whatever module object is cached at test start; if that object differs
    from the one the test body runs against, the patches and the code under
    test refer to different objects and a test fails intermittently. This
    fixture runs before each test — hence before patch resolution — and
    evicts any mock-bound copy so both sides always use the same real
    module. The suite is skipped wholesale via pytestmark when gi is
    unavailable, so the import below never runs without real bindings.
    """
    cached = sys.modules.get("zfsutilities_gui")
    if cached is not None and isinstance(getattr(cached, "Gtk", None), MagicMock):
        sys.modules.pop("zfsutilities_gui", None)
    import zfsutilities_gui  # noqa: F401


def _gui_module():
    """Return the zfsutilities_gui module the @patch decorators patched.

    The autouse fixture above guarantees the cached module is the real
    GObject-bound import before every test starts, so this is always the
    same object the decorators patched. Looked up rather than imported:
    a fresh import here could bind a different module object than the one
    the decorators patched (the flake this fixture exists to prevent), and
    the static import guard in test_gui_infrastructure requires in-function
    GUI imports to carry their own pop.
    """
    return sys.modules["zfsutilities_gui"]


class TestCheckPeerVersionAsync(unittest.TestCase):
    """Unit tests for ZFSUtilitiesWindow._check_peer_version_async."""

    def _make_window(self, version="1.2.3"):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._version = version
            return window, gui

    @patch("zfsutilities_gui._get_peer_host", return_value=None)
    @patch("zfsutilities_gui.threading.Thread")
    def test_single_node_does_not_spawn_thread(self, mock_thread, _mock_peer):
        window, _gui = self._make_window()
        window._check_peer_version_async()
        mock_thread.assert_not_called()

    @patch("zfsutilities_gui._get_peer_host", return_value="compute1")
    @patch("zfsutilities_gui._get_host_version", return_value="1.2.3")
    @patch("zfsutilities_gui.GLib.idle_add")
    @patch("zfsutilities_gui.threading.Thread")
    def test_two_node_spawns_daemon_thread(self, mock_thread, mock_idle, _mock_host, _mock_peer):
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
    def test_two_node_mismatch_passed_to_idle(self, mock_thread, mock_idle, _mock_host, _mock_peer):
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
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
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
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
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
        box.pack_start.assert_any_call(mock_gtk.Label.return_value, False, False, 0)
        window.action_box.pack_start.assert_called_once_with(button, False, False, 0)

    def test_toggling_dry_run_persists_state_and_updates_label(self):
        window, gui = self._make_window()
        mock_gtk = MagicMock()
        with patch.object(gui, "Gtk", mock_gtk):
            button = window.add_dry_run_toggle()
        label = mock_gtk.Label.return_value
        button.get_active.return_value = True

        window._on_dry_run_toggled(button, label)

        self.assertTrue(window._dry_run_active)
        label.set_markup.assert_called_with("<span color='red'>Dry Run</span>")


class TestDatasetRunnerIntegration(unittest.TestCase):
    """Dataset action runner is created and receives forwarded stdin input."""

    def test_dataset_runner_created(self):
        gui = _gui_module()
        with (
            patch.object(gui.ZFSUtilitiesWindow, "create_sidebar_and_stack"),
            patch.object(gui.ZFSUtilitiesWindow, "create_action_panel"),
            patch("zfsutilities_gui.create_menu_bar"),
            patch("zfsutilities_gui.create_info_panel"),
            patch("zfsutilities_gui.UIStateManager"),
            patch("zfsutilities_gui.RunnerFactory") as mock_factory,
        ):
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
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._input_registry = gui.InputRequestRegistry()
            window.dataset_runner = MagicMock()
            window.dataset_runner.label = "Dataset action"
            window.dataset_runner.running = True
            window.dataset_runner.step_active = True
            window._runners = [window.dataset_runner]
            window.stdin_entry = MagicMock()
            window.stdin_entry.get_text.return_value = "yes"

            with patch("zfsutilities_gui.log_msg"):
                window._send_stdin_text()

            window.dataset_runner.send_input.assert_called_once_with("yes")


class TestDashboardTimer(unittest.TestCase):
    """Tests for ZFSUtilitiesWindow dashboard/scrub timer lifecycle."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._dashboard_timer = None
            window._scrub_timer = None
            window.stack = MagicMock()
            window.config = {"dashboard": {"refresh_seconds": 30}}
            return window

    @patch("zfsutilities_gui.GLib")
    def test_dashboard_page_starts_timer(self, mock_glib):
        """Switching to Dashboard starts a refresh timer from config."""
        window = self._make_window()
        mock_glib.timeout_add_seconds.return_value = 42
        window._start_stop_dashboard_timer("dashboard")
        mock_glib.timeout_add_seconds.assert_called_once_with(30, window._on_dashboard_timer_tick)
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
        mock_glib.timeout_add_seconds.assert_called_once_with(30, window._on_dashboard_timer_tick)
        self.assertEqual(window._dashboard_timer, 42)

    @patch("zfsutilities_gui.GLib")
    def test_dashboard_timer_uses_configured_interval(self, mock_glib):
        """Dashboard timer interval honors dashboard.refresh_seconds."""
        window = self._make_window()
        window.config = {"dashboard": {"refresh_seconds": 45}}
        mock_glib.timeout_add_seconds.return_value = 42
        window._start_stop_dashboard_timer("dashboard")
        mock_glib.timeout_add_seconds.assert_called_once_with(45, window._on_dashboard_timer_tick)

    @patch("zfsutilities_gui.GLib")
    def test_dashboard_timer_defaults_to_30_seconds(self, mock_glib):
        """Dashboard timer defaults to 30 s when config lacks refresh_seconds."""
        window = self._make_window()
        window.config = {}
        mock_glib.timeout_add_seconds.return_value = 42
        window._start_stop_dashboard_timer("dashboard")
        mock_glib.timeout_add_seconds.assert_called_once_with(30, window._on_dashboard_timer_tick)

    @patch("zfsutilities_gui.GLib")
    def test_dashboard_timer_clamps_to_minimum_one_second(self, mock_glib):
        """Dashboard timer interval is clamped to at least 1 second."""
        window = self._make_window()
        window.config = {"dashboard": {"refresh_seconds": 0}}
        mock_glib.timeout_add_seconds.return_value = 42
        window._start_stop_dashboard_timer("dashboard")
        mock_glib.timeout_add_seconds.assert_called_once_with(1, window._on_dashboard_timer_tick)


class TestScheduleTimer(unittest.TestCase):
    """Tests for ZFSUtilitiesWindow schedule refresh timer lifecycle."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
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
        mock_glib.timeout_add_seconds.assert_called_once_with(60, window._on_schedule_timer_tick)
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
    def test_schedule_timer_tick_refreshes_when_visible(self, mock_refresh, mock_glib):
        """The timer callback refreshes Schedule only while it is visible."""
        window = self._make_window()
        window.stack.get_visible_child_name.return_value = "schedule"
        result = window._on_schedule_timer_tick()
        mock_refresh.assert_called_once_with(window)
        self.assertTrue(result)

    @patch("zfsutilities_gui.GLib")
    @patch("zfsutilities_gui.refresh_schedule_page")
    def test_schedule_timer_tick_skips_when_hidden(self, mock_refresh, mock_glib):
        """The timer callback does nothing when another tab is visible."""
        window = self._make_window()
        window.stack.get_visible_child_name.return_value = "backup"
        result = window._on_schedule_timer_tick()
        mock_refresh.assert_not_called()
        self.assertTrue(result)


class TestPoolsTimer(unittest.TestCase):
    """Tests for the Pools-tab pool registry refresh timer lifecycle."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._pools_timer = None
            window.stack = MagicMock()
            return window

    @patch("zfsutilities_gui.GLib")
    def test_pools_page_starts_timer(self, mock_glib):
        """Switching to Pools refreshes the registry once and starts the interval timer."""
        gui = _gui_module()
        window = self._make_window()
        mock_glib.timeout_add_seconds.return_value = 42
        with patch("pools_page.refresh_pools_page") as mock_refresh:
            window._start_stop_pools_timer("pools")
        mock_refresh.assert_called_once_with(window)
        mock_glib.timeout_add_seconds.assert_called_once_with(
            gui.POOLS_REFRESH_SECONDS, window._on_pools_timer_tick
        )
        self.assertEqual(window._pools_timer, 42)

    @patch("zfsutilities_gui.GLib")
    def test_non_pools_page_stops_timer(self, mock_glib):
        """Switching away from Pools removes the timer."""
        window = self._make_window()
        window._pools_timer = 7
        window._start_stop_pools_timer("backup")
        mock_glib.source_remove.assert_called_once_with(7)
        self.assertIsNone(window._pools_timer)

    @patch("zfsutilities_gui.GLib")
    def test_pools_timer_replaces_existing_timer(self, mock_glib):
        """Re-entering Pools cancels the old timer before starting a new one."""
        window = self._make_window()
        window._pools_timer = 7
        mock_glib.timeout_add_seconds.return_value = 42
        with patch("pools_page.refresh_pools_page"):
            window._start_stop_pools_timer("pools")
        mock_glib.source_remove.assert_called_once_with(7)
        self.assertEqual(window._pools_timer, 42)

    def test_timer_tick_refreshes_only_on_pools_page(self):
        """The tick callback refreshes the registry on Pools and stays alive."""
        window = self._make_window()
        window.stack.get_visible_child_name.return_value = "pools"
        with patch("pools_page.refresh_pools_page") as mock_refresh:
            self.assertTrue(window._on_pools_timer_tick())
        mock_refresh.assert_called_once_with(window)

        mock_refresh.reset_mock()
        window.stack.get_visible_child_name.return_value = "backup"
        with patch("pools_page.refresh_pools_page") as mock_refresh:
            self.assertTrue(window._on_pools_timer_tick())
        mock_refresh.assert_not_called()


class TestLogFontHandlers(unittest.TestCase):
    """The View-menu font handlers dispatch to the matching log widget."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window.info_text = MagicMock()
            window.logs_text = MagicMock()
            return window

    def test_info_log_larger_uses_info_widget(self):
        window = self._make_window()
        controller = MagicMock()
        with patch("zfsutilities_gui.get_log_font_controller", return_value=controller) as get:
            window.on_log_font_larger(MagicMock(), "info_log")
        get.assert_called_once_with(window, "info_log", window.info_text)
        controller.larger.assert_called_once_with()

    def test_logs_viewer_smaller_and_default_dispatch(self):
        window = self._make_window()
        controller = MagicMock()
        with patch("zfsutilities_gui.get_log_font_controller", return_value=controller) as get:
            window.on_log_font_smaller(MagicMock(), "logs_viewer")
            window.on_log_font_default(MagicMock(), "logs_viewer")
        self.assertEqual(get.call_count, 2)
        for call_args in get.call_args_list:
            self.assertEqual(call_args.args, (window, "logs_viewer", window.logs_text))
        controller.smaller.assert_called_once_with()
        controller.reset.assert_called_once_with()

    def test_unknown_state_key_is_ignored(self):
        window = self._make_window()
        with patch("zfsutilities_gui.get_log_font_controller") as get:
            window.on_log_font_larger(MagicMock(), "bogus")
        get.assert_not_called()


class TestOnPageChanged(unittest.TestCase):
    """Tests for ZFSUtilitiesWindow.on_page_changed per-tab refresh hooks."""

    def _make_window(self, config=None):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            cfg = config if config is not None else {"pools": []}
            window.config = cfg
            window.ctx = MagicMock()
            window.ctx.config = cfg
            window.offsite_detected_label = MagicMock()
            window.update_action_buttons = MagicMock()
            window._start_stop_dashboard_timer = MagicMock()
            window._start_stop_scrub_timer = MagicMock()
            window._start_stop_pools_timer = MagicMock()
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

        window.offsite_detected_label.set_text.assert_called_once_with("(no candidates configured)")

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

    def test_pools_page_starts_registry_timer(self):
        """Switching to the Pools tab runs the registry timer start/stop hook."""
        window = self._make_window({"pools": []})
        stack = MagicMock()
        stack.get_visible_child_name.return_value = "pools"

        window.on_page_changed(stack, None)

        window.update_action_buttons.assert_called_once_with("pools")
        window._start_stop_pools_timer.assert_called_once_with("pools")

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

    @patch("zfsutilities_gui.refresh_disks_page")
    def test_disks_page_refreshes(self, mock_refresh):
        """Switching to the Disks tab refreshes the disk inventory and topology."""
        window = self._make_window({"pools": []})
        stack = MagicMock()
        stack.get_visible_child_name.return_value = "disks"

        window.on_page_changed(stack, None)

        window.update_action_buttons.assert_called_once_with("disks")
        mock_refresh.assert_called_once_with(window)


class TestUpdateActionButtonsGuard(unittest.TestCase):
    """update_action_buttons() only rebuilds the panel for the visible page."""

    def _make_window(self, visible_page="retention"):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
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


class TestTerminateConfirmation(unittest.TestCase):
    """Tests for the close/quit confirmation when tasks are running."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed.

        Each test imports the module freshly so it is independent of any
        cached mock-GTK import left by earlier tests.
        """
        import sys

        sys.modules.pop("zfsutilities_gui", None)
        import zfsutilities_gui as gui

        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window.dataset_runner = None
            return window, gui

    def _set_dialog_response(self, gui, response):
        """Configure the mocked MessageDialog to return *response*.

        Returns the patched MessageDialog class mock; the dialog instance is
        available as its return_value.
        """
        dialog_class = MagicMock()
        gui.Gtk.MessageDialog = dialog_class
        dialog = dialog_class.return_value
        dialog.run.return_value = response
        return dialog_class

    def test_delete_event_no_tasks_allows_close(self):
        """Closing with no running tasks does not show a warning."""
        window, gui = self._make_window()
        dialog_class = self._set_dialog_response(gui, gui.Gtk.ResponseType.YES)
        with patch.object(gui, "_collect_running_tasks", return_value=[]):
            result = window._on_delete_event(None, None)
        self.assertFalse(result)
        dialog_class.assert_not_called()

    def test_delete_event_with_running_task_shows_warning(self):
        """Closing with a running GUI runner shows the task in the dialog."""
        window, gui = self._make_window()
        dialog_class = self._set_dialog_response(gui, gui.Gtk.ResponseType.YES)
        with patch.object(
            gui,
            "_collect_running_tasks",
            return_value=[
                {"name": "Backup", "type": "GUI", "status": "Running"},
            ],
        ):
            result = window._on_delete_event(None, None)

        dialog_class.assert_called_once()
        dialog = dialog_class.return_value
        secondary = dialog.format_secondary_text.call_args[0][0]
        self.assertIn("Backup", secondary)
        self.assertFalse(result)

    def test_delete_event_no_cancels_close(self):
        """Clicking No in the warning dialog keeps the window open."""
        window, gui = self._make_window()
        self._set_dialog_response(gui, gui.Gtk.ResponseType.NO)
        with patch.object(
            gui,
            "_collect_running_tasks",
            return_value=[
                {"name": "Backup", "type": "GUI", "status": "Running"},
            ],
        ):
            result = window._on_delete_event(None, None)

        self.assertTrue(result)

    def test_delete_event_includes_dataset_runner(self):
        """The dataset runner is listed exactly once via the running-tasks collector."""
        window, gui = self._make_window()
        dialog_class = self._set_dialog_response(gui, gui.Gtk.ResponseType.YES)
        window.dataset_runner = MagicMock()
        window.dataset_runner.running = True
        window.dataset_runner.label = "Dataset action"
        with patch.object(
            gui,
            "_collect_running_tasks",
            return_value=[
                {"name": "Migrate Pool: tank", "type": "GUI", "status": "Step 1/4"},
            ],
        ):
            window._on_delete_event(None, None)

        dialog = dialog_class.return_value
        secondary = dialog.format_secondary_text.call_args[0][0]
        self.assertEqual(secondary.count("Migrate Pool: tank"), 1)

    def test_collect_abortable_tasks_filters_scrubs_and_remote_profiles(self):
        """Scrubs and non-GUI profiles are excluded from the warning list."""
        window, gui = self._make_window()
        window.dataset_runner = None
        tasks_data = [
            {"name": "Backup", "type": "GUI", "status": "Running"},
            {"name": "Scrub: pool1", "type": "Scrub", "status": "10.0% complete"},
            {"name": "Resilver: pool1", "type": "ZFS", "status": "45.2% done"},
            {"name": "Daily", "type": "Profile", "status": "PID 1234"},
            {"name": "Nightly", "type": "Profile", "status": "PID 5678"},
        ]
        with (
            patch.object(gui, "_collect_running_tasks", return_value=tasks_data),
            patch.object(gui, "_is_descendant_of_current_process") as mock_descendant,
            patch.object(gui, "_profile_tab_type", return_value="backup"),
        ):
            mock_descendant.side_effect = lambda pid: pid == 1234
            tasks = window._collect_abortable_tasks()

        names = [t["name"] for t in tasks]
        self.assertEqual(names, ["Backup", "Daily"])

    def test_collect_abortable_tasks_skips_gui_started_scrub_profiles(self):
        """GUI-started scrub-profile runs are excluded: their scrubs survive."""
        window, gui = self._make_window()
        window.dataset_runner = None
        tasks_data = [
            {"name": "Weekly Scrub", "type": "Profile", "status": "PID 1234"},
            {"name": "Scheduled: Monthly Scrub", "type": "Scheduled", "status": "PID 2345"},
        ]
        tab_types = {"Weekly Scrub": "scrub", "Monthly Scrub": "scrub"}
        with (
            patch.object(gui, "_collect_running_tasks", return_value=tasks_data),
            patch.object(gui, "_is_descendant_of_current_process", return_value=True),
            patch.object(gui, "_profile_tab_type", side_effect=lambda name: tab_types.get(name)),
        ):
            tasks = window._collect_abortable_tasks()

        self.assertEqual(tasks, [])

    def test_collect_abortable_tasks_keeps_gui_started_non_scrub_profiles(self):
        """GUI-started non-scrub profiles and unknown types stay listed."""
        window, gui = self._make_window()
        window.dataset_runner = None
        tasks_data = [
            {"name": "Daily", "type": "Profile", "status": "PID 1234"},
            {"name": "Mystery", "type": "Profile", "status": "PID 3456"},
            {"name": "Scheduled: Nightly", "type": "Scheduled", "status": "PID 5678"},
        ]
        tab_types = {"Daily": "backup", "Nightly": "offsite"}
        with (
            patch.object(gui, "_collect_running_tasks", return_value=tasks_data),
            patch.object(gui, "_is_descendant_of_current_process", return_value=True),
            patch.object(gui, "_profile_tab_type", side_effect=lambda name: tab_types.get(name)),
        ):
            tasks = window._collect_abortable_tasks()

        names = [t["name"] for t in tasks]
        self.assertEqual(names, ["Daily", "Mystery", "Scheduled: Nightly"])

    def test_collect_abortable_tasks_filters_surface_tests(self):
        """Firmware-driven surface tests are excluded; they survive GUI close."""
        window, gui = self._make_window()
        window.dataset_runner = None
        tasks_data = [
            {"name": "Backup", "type": "GUI", "status": "Running"},
            {"name": "Surface Test: /dev/sda", "type": "Surface Test", "status": "30% done"},
        ]
        with patch.object(gui, "_collect_running_tasks", return_value=tasks_data):
            tasks = window._collect_abortable_tasks()

        names = [t["name"] for t in tasks]
        self.assertEqual(names, ["Backup"])

    def test_on_quit_no_tasks_quits(self):
        """Quit menu with no running tasks invokes app.quit()."""
        window, _gui = self._make_window()
        app = MagicMock()
        window.get_application = MagicMock(return_value=app)
        with patch.object(window, "_confirm_terminate", return_value=True):
            window.on_quit(None)
        app.quit.assert_called_once()

    def test_on_quit_canceled_does_not_quit(self):
        """Quit menu with a canceled confirmation does not quit."""
        window, _gui = self._make_window()
        app = MagicMock()
        window.get_application = MagicMock(return_value=app)
        with patch.object(window, "_confirm_terminate", return_value=False):
            window.on_quit(None)
        app.quit.assert_not_called()

    def test_on_quit_confirmed_quits(self):
        """Quit menu with a confirmed warning still invokes app.quit()."""
        window, _gui = self._make_window()
        app = MagicMock()
        window.get_application = MagicMock(return_value=app)
        with patch.object(window, "_confirm_terminate", return_value=True):
            window.on_quit(None)
        app.quit.assert_called_once()


class TestDisksTimer(unittest.TestCase):
    """Tests for the Disks-tab surface-test status timer lifecycle."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._disks_timer = None
            window.stack = MagicMock()
            return window

    @patch("zfsutilities_gui.GLib")
    def test_disks_page_starts_timer(self, mock_glib):
        """Switching to Disks refreshes status once and starts a 5 s timer."""
        window = self._make_window()
        mock_glib.timeout_add_seconds.return_value = 42
        with patch("disks_page.refresh_surface_test_status") as mock_refresh:
            window._start_stop_disks_timer("disks")
        mock_refresh.assert_called_once_with(window)
        mock_glib.timeout_add_seconds.assert_called_once_with(5, window._on_disks_timer_tick)
        self.assertEqual(window._disks_timer, 42)

    @patch("zfsutilities_gui.GLib")
    def test_non_disks_page_stops_timer(self, mock_glib):
        """Switching away from Disks removes the timer."""
        window = self._make_window()
        window._disks_timer = 7
        window._start_stop_disks_timer("backup")
        mock_glib.source_remove.assert_called_once_with(7)
        self.assertIsNone(window._disks_timer)

    @patch("zfsutilities_gui.GLib")
    def test_disks_timer_replaces_existing_timer(self, mock_glib):
        """Re-entering Disks cancels the old timer before starting a new one."""
        window = self._make_window()
        window._disks_timer = 7
        mock_glib.timeout_add_seconds.return_value = 42
        with patch("disks_page.refresh_surface_test_status"):
            window._start_stop_disks_timer("disks")
        mock_glib.source_remove.assert_called_once_with(7)
        mock_glib.timeout_add_seconds.assert_called_once_with(5, window._on_disks_timer_tick)
        self.assertEqual(window._disks_timer, 42)

    def test_timer_tick_refreshes_only_on_disks_page(self):
        """The tick callback refreshes status on Disks and stays alive."""
        window = self._make_window()
        window.stack.get_visible_child_name.return_value = "disks"
        with patch("disks_page.refresh_surface_test_status") as mock_refresh:
            self.assertTrue(window._on_disks_timer_tick())
        mock_refresh.assert_called_once_with(window)

        mock_refresh.reset_mock()
        window.stack.get_visible_child_name.return_value = "backup"
        with patch("disks_page.refresh_surface_test_status") as mock_refresh:
            self.assertTrue(window._on_disks_timer_tick())
        mock_refresh.assert_not_called()


class TestMemoryTimer(unittest.TestCase):
    """Tests for the Performance-tab refresh timer lifecycle."""

    def _make_window(self):
        """Create a ZFSUtilitiesWindow with __init__ bypassed."""
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._memory_timer = None
            window.stack = MagicMock()
            window.config = {"memory": {"refresh_seconds": 5}}
            return window

    @patch("zfsutilities_gui.GLib")
    def test_memory_page_starts_timer(self, mock_glib):
        """Switching to Performance refreshes once and starts the configured timer."""
        window = self._make_window()
        mock_glib.timeout_add_seconds.return_value = 42
        with patch("zfsutilities_gui.refresh_memory_page") as mock_refresh:
            window._start_stop_memory_timer("memory")
        mock_refresh.assert_called_once_with(window)
        mock_glib.timeout_add_seconds.assert_called_once_with(5, window._on_memory_timer_tick)
        self.assertEqual(window._memory_timer, 42)

    @patch("zfsutilities_gui.GLib")
    def test_non_memory_page_stops_timer(self, mock_glib):
        """Switching away from Performance removes the timer."""
        window = self._make_window()
        window._memory_timer = 7
        window._start_stop_memory_timer("backup")
        mock_glib.source_remove.assert_called_once_with(7)
        self.assertIsNone(window._memory_timer)

    def test_timer_tick_refreshes_only_on_memory_page(self):
        """The tick callback refreshes on Performance and stays alive."""
        window = self._make_window()
        window.stack.get_visible_child_name.return_value = "memory"
        with patch("zfsutilities_gui.refresh_memory_page") as mock_refresh:
            self.assertTrue(window._on_memory_timer_tick())
        mock_refresh.assert_called_once_with(window)

        mock_refresh.reset_mock()
        window.stack.get_visible_child_name.return_value = "backup"
        with patch("zfsutilities_gui.refresh_memory_page") as mock_refresh:
            self.assertTrue(window._on_memory_timer_tick())
        mock_refresh.assert_not_called()

    def test_destroy_removes_memory_timer(self):
        window = self._make_window()
        window._memory_timer = 9
        window.popout_window = None
        with patch("zfsutilities_gui.GLib") as mock_glib:
            window._on_main_destroy(None)
        mock_glib.source_remove.assert_called_once_with(9)
        self.assertIsNone(window._memory_timer)


class TestSidebarPageOrder(unittest.TestCase):
    """The sidebar exposes the pages in the agreed order."""

    def test_infrastructure_tabs_are_last(self):
        """Disks/Pools/Datasets are the final three tabs, Performance just before.

        The Performance page keeps the internal stack name "memory" (it is
        also the persisted config key), so only the sidebar title changed.
        """
        gui = _gui_module()
        names = [name for name, _title, _builder in gui.PAGE_BUILDERS]
        self.assertEqual(names[-4:], ["memory", "disks", "pools", "datasets"])
        titles = {name: title for name, title, _builder in gui.PAGE_BUILDERS}
        self.assertEqual(titles["memory"], "Performance")

    def test_all_pages_present_exactly_once(self):
        gui = _gui_module()
        names = [name for name, _title, _builder in gui.PAGE_BUILDERS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(
            set(names),
            {
                "dashboard",
                "backup",
                "offsite",
                "restore",
                "schedule",
                "retention",
                "checkagainst",
                "logs",
                "memory",
                "disks",
                "pools",
                "datasets",
            },
        )

    def test_memory_page_has_documentation_anchor(self):
        gui = _gui_module()
        self.assertEqual(gui.ZFSUtilitiesWindow._PAGE_ANCHORS["memory"], "performance-tab")


class TestInputRoutingLadder(unittest.TestCase):
    """Operator input routes to the task that asked (MVS console model)."""

    def _make_window(self):
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._input_registry = gui.InputRequestRegistry()
            window.stdin_entry = MagicMock()
            window.stdin_send_btn = MagicMock()
            window.log_message = MagicMock()
            window.input_strip = MagicMock()
            window.input_strip.get_children.return_value = []
            window.input_strip_frame = MagicMock()
            return window, gui

    def _runner(self, window, label, running=False, step_active=False):
        runner = MagicMock()
        runner.label = label
        runner.running = running
        runner.step_active = step_active
        return runner

    def _set_input(self, window, text):
        window.stdin_entry.get_text.return_value = text

    def test_numbered_reply_routes_to_issuing_runner(self):
        window, _ = self._make_window()
        runner_a = self._runner(window, "Backup")
        runner_b = self._runner(window, "Restore")
        window._input_registry.register(runner_a, "u1", "First?")
        request_b = window._input_registry.register(runner_b, "u2", "Second?")
        self._set_input(window, f"{request_b.number} y")
        window._send_stdin_text()
        runner_b.send_input.assert_called_once_with("y")
        runner_a.send_input.assert_not_called()

    def test_cross_routed_answers_reach_both_runners(self):
        """Two simultaneous prompts: each reply lands on its own task."""
        window, _ = self._make_window()
        runner_a = self._runner(window, "Backup")
        runner_b = self._runner(window, "Dataset action")
        first = window._input_registry.register(runner_a, "u1", "Proceed?")
        second = window._input_registry.register(runner_b, "u2", "Approve deletion?")
        for number, runner, answer in [
            (second.number, runner_b, "y"),
            (first.number, runner_a, "n"),
        ]:
            self._set_input(window, f"{number} {answer}")
            window._send_stdin_text()
        runner_b.send_input.assert_called_once_with("y")
        runner_a.send_input.assert_called_once_with("n")

    def test_unknown_number_rejected_with_warning(self):
        window, _ = self._make_window()
        runner = self._runner(window, "Backup")
        window._input_registry.register(runner, "u1", "Proceed?")
        self._set_input(window, "9 y")
        window._send_stdin_text()
        runner.send_input.assert_not_called()
        warned = [c.args[0] for c in window.log_message.call_args_list]
        self.assertTrue(any("numbered 9" in msg for msg in warned))

    def test_bare_text_answers_sole_outstanding(self):
        window, _ = self._make_window()
        runner = self._runner(window, "Prune")
        window._input_registry.register(runner, "u1", "Approve deletion?")
        self._set_input(window, "y")
        window._send_stdin_text()
        runner.send_input.assert_called_once_with("y")

    def test_bare_text_with_two_holds_rejected(self):
        window, _ = self._make_window()
        runner_a = self._runner(window, "Backup")
        runner_b = self._runner(window, "Restore")
        window._input_registry.register(runner_a, "u1", "One?")
        window._input_registry.register(runner_b, "u2", "Two?")
        self._set_input(window, "y")
        window._send_stdin_text()
        runner_a.send_input.assert_not_called()
        runner_b.send_input.assert_not_called()
        warned = [c.args[0] for c in window.log_message.call_args_list]
        self.assertTrue(any("WARN:" in msg for msg in warned))

    def test_bare_text_falls_back_to_sole_live_step(self):
        window, _ = self._make_window()
        live = self._runner(window, "Backup", running=True, step_active=True)
        idle = self._runner(window, "Restore", running=True, step_active=False)
        window._runners = [live, idle]
        self._set_input(window, "hello")
        window._send_stdin_text()
        live.send_input.assert_called_once_with("hello")
        idle.send_input.assert_not_called()

    def test_bare_text_with_two_live_steps_rejected(self):
        window, _ = self._make_window()
        live_a = self._runner(window, "Backup", running=True, step_active=True)
        live_b = self._runner(window, "Restore", running=True, step_active=True)
        window._runners = [live_a, live_b]
        self._set_input(window, "hello")
        window._send_stdin_text()
        live_a.send_input.assert_not_called()
        live_b.send_input.assert_not_called()

    def test_bare_text_with_nothing_live_rejected(self):
        window, _ = self._make_window()
        window._runners = []
        self._set_input(window, "hello")
        window._send_stdin_text()
        warned = [c.args[0] for c in window.log_message.call_args_list]
        self.assertTrue(any("Input ignored" in msg for msg in warned))

    def test_numbered_reply_echoes_via_runner_log(self):
        window, _ = self._make_window()
        runner = self._runner(window, "Restore")
        request = window._input_registry.register(runner, "u1", "Proceed?")
        self._set_input(window, f"{request.number} y")
        window._send_stdin_text()
        echoed = [c.args[0] for c in runner.log_input.call_args_list]
        self.assertEqual(echoed, [f"VERB: > {request.number} y"])


class TestInputEventLifecycle(unittest.TestCase):
    """Input-hold events maintain the registry and the action strip."""

    def _make_window(self):
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._input_registry = gui.InputRequestRegistry()
            window.stdin_entry = MagicMock()
            window.stdin_entry.get_sensitive.return_value = False
            window.stdin_send_btn = MagicMock()
            window._runners = []
            window.input_strip = MagicMock()
            window.input_strip.get_children.return_value = []
            window.input_strip_frame = MagicMock()
            return window, gui

    def _runner(self, label):
        runner = MagicMock()
        runner.label = label
        runner.running = False
        runner.step_active = False
        return runner

    def test_req_registers_hold_and_logs_numbered_line(self):
        window, _ = self._make_window()
        runner = self._runner("Restore")
        window._on_input_event(runner, "req", "u1", "Proceed?")
        request = window._input_registry.by_uuid("u1")
        self.assertIsNotNone(request)
        self.assertEqual(request.number, 1)
        logged = [c.args[0] for c in runner.log_input.call_args_list]
        self.assertEqual(logged, ["INFO: [Input 1][Restore] Proceed?"])

    def test_ack_releases_hold(self):
        window, _ = self._make_window()
        runner = self._runner("Restore")
        window._on_input_event(runner, "req", "u1", "Proceed?")
        window._on_input_event(runner, "ack", "u1", None)
        self.assertIsNone(window._input_registry.by_uuid("u1"))
        logged = [c.args[0] for c in runner.log_input.call_args_list]
        self.assertIn("VERB: [Input 1] closed", logged)

    def test_clear_withdraws_all_runner_holds(self):
        window, _ = self._make_window()
        runner_a = self._runner("Restore")
        runner_b = self._runner("Backup")
        window._on_input_event(runner_a, "req", "u1", "One?")
        window._on_input_event(runner_b, "req", "u2", "Two?")
        window._on_input_event(runner_a, "clear", None, None)
        self.assertIsNone(window._input_registry.by_uuid("u1"))
        self.assertIsNotNone(window._input_registry.by_uuid("u2"))

    def test_rereq_updates_prompt_keeps_number(self):
        window, _ = self._make_window()
        runner = self._runner("Restore")
        window._on_input_event(runner, "req", "u1", "Proceed?")
        window._on_input_event(runner, "req", "u1", "Proceed? (re-asked)")
        request = window._input_registry.by_uuid("u1")
        self.assertEqual(request.number, 1)
        self.assertEqual(request.prompt, "Proceed? (re-asked)")
        self.assertEqual(len(window._input_registry.outstanding()), 1)

    def test_strip_refreshed_and_framed_by_holds(self):
        window, gui = self._make_window()
        with patch.object(gui, "Gtk") as mock_gtk:
            window.input_strip.get_children.return_value = ["stale"]
            window._on_input_event(self._runner("Restore"), "req", "u1", "Proceed?")
        window.input_strip.remove.assert_called_once_with("stale")
        mock_gtk.ListBoxRow.assert_called_once()
        window.input_strip_frame.set_visible.assert_called_once_with(True)


class TestStdinEnableRecompute(unittest.TestCase):
    """Entry sensitivity is recomputed, never last-writer-wins."""

    def _make_window(self):
        gui = _gui_module()
        with patch.object(gui.ZFSUtilitiesWindow, "__init__", lambda self, **kwargs: None):
            window = gui.ZFSUtilitiesWindow()
            window._input_registry = gui.InputRequestRegistry()
            window.stdin_entry = MagicMock()
            window.stdin_entry.get_sensitive.return_value = False
            window.stdin_send_btn = MagicMock()
            return window, gui

    def _runner(self, running):
        runner = MagicMock()
        runner.running = running
        return runner

    def test_hold_keeps_entry_live_when_no_runner_runs(self):
        window, _ = self._make_window()
        window._runners = [self._runner(False)]
        window._input_registry.register(self._runner(True), "u1", "Proceed?")
        window._set_stdin_enabled(False)
        window.stdin_entry.set_sensitive.assert_called_with(True)

    def test_all_idle_and_no_holds_disables(self):
        window, _ = self._make_window()
        window._runners = [self._runner(False), self._runner(False)]
        window._set_stdin_enabled(True)
        window.stdin_entry.set_sensitive.assert_called_with(False)

    def test_any_running_runner_enables(self):
        window, _ = self._make_window()
        window._runners = [self._runner(False), self._runner(True)]
        window._set_stdin_enabled(False)
        window.stdin_entry.set_sensitive.assert_called_with(True)


if __name__ == "__main__":
    unittest.main()
