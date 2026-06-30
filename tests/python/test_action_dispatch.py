"""Tests for action_dispatch.py — action handlers and profile helpers."""

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
    import action_dispatch


class TestCollectScrubConfig(unittest.TestCase):
    """_collect_scrub_config() gathers the current scrub-manager settings."""

    def _make_app(self, selected=None, pending=None, active=None, paused=None,
                  target=2):
        app = MagicMock()
        app.config = {"scrub_manager": {
            "simultaneous": 2,
            "refresh_seconds": 30,
            "system_scrub_weekly": True,
            "system_scrub_monthly": False,
        }}
        app.scrub_view = MagicMock()
        self._selected = selected or []

        queue = MagicMock()
        queue.pending = set(pending or [])
        queue.active = set(active or [])
        queue.paused = set(paused or [])
        queue.target = target
        app.scrub_queue = queue
        return app

    def test_returns_selected_pools_when_rows_selected(self):
        app = self._make_app(selected=["tank", "backup"])
        with patch("pools_page.get_selected_pool_names",
                   return_value=["tank", "backup"]):
            cfg = action_dispatch._collect_scrub_config(app)
        self.assertEqual(cfg["pools"], ["tank", "backup"])
        self.assertEqual(cfg["simultaneous"], 2)
        self.assertEqual(cfg["refresh_seconds"], 30)
        self.assertTrue(cfg["system_scrub_weekly"])
        self.assertFalse(cfg["system_scrub_monthly"])

    def test_falls_back_to_queue_state_when_nothing_selected(self):
        app = self._make_app(pending=["tank"], active=["backup"], paused=["archive"])
        with patch("pools_page.get_selected_pool_names",
                          return_value=[]):
            cfg = action_dispatch._collect_scrub_config(app)
        self.assertEqual(cfg["pools"], ["archive", "backup", "tank"])

    def test_defaults_when_scrub_manager_config_partial(self):
        app = self._make_app(target=1)
        app.config = {"scrub_manager": {}}
        with patch("pools_page.get_selected_pool_names",
                          return_value=[]):
            cfg = action_dispatch._collect_scrub_config(app)
        self.assertEqual(cfg["simultaneous"], 1)
        self.assertEqual(cfg["refresh_seconds"], 10)
        self.assertFalse(cfg["system_scrub_weekly"])
        self.assertFalse(cfg["system_scrub_monthly"])


class TestPoolsAddProfileHandler(unittest.TestCase):
    """The Pools 'Add Profile to Schedule' handler creates a scrub profile."""

    def test_handler_creates_scrub_profile(self):
        app = MagicMock()
        app.config = {"scrub_manager": {
            "simultaneous": 1,
            "refresh_seconds": 10,
            "system_scrub_weekly": False,
            "system_scrub_monthly": False,
        }}
        app.scrub_view = MagicMock()
        app.scrub_view.get_selection.return_value.get_selected_rows.return_value = (
            MagicMock(), []
        )
        app.scrub_queue = MagicMock()
        app.scrub_queue.pending = {"tank"}
        app.scrub_queue.active = set()
        app.scrub_queue.paused = set()
        app.scrub_queue.target = 1

        handler = action_dispatch.ACTION_HANDLERS["pools"]["Add Profile to Schedule"]

        with patch.object(action_dispatch, "show_add_profile_dialog") as mock_dlg:
            handler(app)

        mock_dlg.assert_called_once()
        args = mock_dlg.call_args[0]
        kwargs = mock_dlg.call_args[1]
        self.assertEqual(args[0], app)
        self.assertEqual(args[1], "scrub")
        self.assertEqual(args[2]["pools"], ["tank"])


class TestDashboardPageSpec(unittest.TestCase):
    """Dashboard page spec exposes the View Log action."""

    def test_includes_view_log_button(self):
        buttons = action_dispatch.PAGE_SPECS["dashboard"]["buttons"]
        self.assertIn(("View Log", "text-x-generic", "_view_log_button"), buttons)


class TestDashboardHandlers(unittest.TestCase):
    """Dashboard action handlers are wired correctly."""

    def test_view_log_handler(self):
        handler = action_dispatch.ACTION_HANDLERS["dashboard"]["View Log"]
        self.assertIs(handler, action_dispatch.on_dashboard_view_log)


class TestLogsPageSpec(unittest.TestCase):
    """Logs page spec exposes the delete action and post-setup hook."""

    def test_delete_selected_button_has_name(self):
        buttons = action_dispatch.PAGE_SPECS["logs"]["buttons"]
        self.assertIn(
            ("Delete Selected", "edit-delete", "_logs_delete_button"),
            buttons,
        )

    def test_post_setup_is_logs_actions(self):
        post_setup = action_dispatch.PAGE_SPECS["logs"].get("post_setup")
        self.assertIs(post_setup, action_dispatch._setup_logs_actions)


class TestOffsitePageSpec(unittest.TestCase):
    """Offsite page spec no longer exposes removed Detect/Prune buttons."""

    def test_buttons_exclude_detect_pool(self):
        buttons = action_dispatch.PAGE_SPECS["offsite"]["buttons"]
        names = [b[0] for b in buttons]
        self.assertNotIn("Detect Pool", names)

    def test_buttons_exclude_prune_offsite(self):
        buttons = action_dispatch.PAGE_SPECS["offsite"]["buttons"]
        names = [b[0] for b in buttons]
        self.assertNotIn("Prune Offsite", names)

    def test_save_config_button_still_present(self):
        buttons = action_dispatch.PAGE_SPECS["offsite"]["buttons"]
        self.assertIn(("Save Config", "document-save", "_offsite_save_button"), buttons)


class TestOffsiteHandlers(unittest.TestCase):
    """Offsite action handlers no longer wire removed Detect/Prune actions."""

    def test_detect_pool_handler_not_registered(self):
        self.assertNotIn("Detect Pool", action_dispatch.ACTION_HANDLERS["offsite"])

    def test_prune_offsite_handler_not_registered(self):
        self.assertNotIn("Prune Offsite", action_dispatch.ACTION_HANDLERS["offsite"])

    def test_run_handler_still_registered(self):
        self.assertIn("Run Offsite", action_dispatch.ACTION_HANDLERS["offsite"])


class TestDatasetsPageSpec(unittest.TestCase):
    """Datasets page exposes Expand Selected next to Collapse All."""

    def test_expand_selected_button_present(self):
        buttons = action_dispatch.PAGE_SPECS["datasets"]["buttons"]
        self.assertIn(
            ("Expand Selected", "zoom-in", "_ds_expand_selected_btn"),
            buttons,
        )

    def test_collapse_all_button_still_present(self):
        buttons = action_dispatch.PAGE_SPECS["datasets"]["buttons"]
        self.assertIn(("Collapse All", "list-remove", None), buttons)


class TestSchedulePageSpec(unittest.TestCase):
    """Schedule page exposes Run Now alongside Save/Revert/Delete."""

    def test_run_now_button_present(self):
        buttons = action_dispatch.PAGE_SPECS["schedule"]["buttons"]
        self.assertIn(("Run Now", "media-playback-start", None), buttons)


class TestScheduleHandlers(unittest.TestCase):
    """Schedule action handlers are wired correctly."""

    def test_run_now_handler(self):
        handler = action_dispatch.ACTION_HANDLERS["schedule"]["Run Now"]
        self.assertIs(handler, action_dispatch.on_schedule_run_now)


class TestDatasetsHandlers(unittest.TestCase):
    """Datasets action handlers are wired correctly."""

    def test_expand_selected_handler(self):
        handler = action_dispatch.ACTION_HANDLERS["datasets"]["Expand Selected"]
        self.assertIs(handler, action_dispatch.expand_selected_datasets)

    def test_collapse_all_handler(self):
        handler = action_dispatch.ACTION_HANDLERS["datasets"]["Collapse All"]
        self.assertTrue(callable(handler))
