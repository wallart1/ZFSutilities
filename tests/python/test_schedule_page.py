"""Tests for schedule_page.py — cron regeneration and path logic."""

import json
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from test_support import temp_config_dir, mock_gtk, REPO_ROOT

SAMPLE_NEXT_RUN = datetime(2025, 6, 15, 10, 0, tzinfo=timezone(-timedelta(hours=4)))

GUI_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if GUI_SRC not in sys.path:
    sys.path.insert(0, GUI_SRC)

import cron_manager


class TestRegenerateCronPath(unittest.TestCase):
    """Verify _regenerate_cron picks the correct runner_path."""

    def _import_schedule_page(self):
        """Import schedule_page inside a GTK mock context."""
        with mock_gtk():
            import schedule_page
            return schedule_page

    def test_uses_current_symlink_when_deployed(self):
        schedule_page = self._import_schedule_page()
        mock_profile = [
            {
                "profile_name": "test-daily",
                "active": True,
                "cron": {
                    "minute": "0", "hour": "2",
                    "day": "*", "month": "*", "weekday": "*",
                },
            }
        ]
        with temp_config_dir():
            # Simulate running from a deployed version path
            deployed_file = os.path.join(
                "/usr/local/lib/zfsutilities/versions/0.36.0",
                "07 GTK + Python", "schedule_page.py"
            )
            with patch.object(schedule_page, "__file__", deployed_file):
                with patch.object(schedule_page, "list_profiles", return_value=mock_profile):
                    schedule_page._regenerate_cron(MagicMock())

            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            self.assertIn(
                "/usr/local/lib/zfsutilities/current/07 GTK + Python/profile_runner.py",
                content,
            )

    def test_uses_realpath_when_in_repo(self):
        schedule_page = self._import_schedule_page()
        mock_profile = [
            {
                "profile_name": "test-daily",
                "active": True,
                "cron": {
                    "minute": "0", "hour": "2",
                    "day": "*", "month": "*", "weekday": "*",
                },
            }
        ]
        with temp_config_dir():
            # Simulate running from the repository
            repo_file = os.path.join(GUI_SRC, "schedule_page.py")
            with patch.object(schedule_page, "__file__", repo_file):
                with patch.object(schedule_page, "list_profiles", return_value=mock_profile):
                    schedule_page._regenerate_cron(MagicMock())

            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            expected_path = os.path.join(GUI_SRC, "profile_runner.py")
            self.assertIn(expected_path, content)
            # Must NOT contain the generic current symlink path
            self.assertNotIn("/current/", content)




class FakeScheduleRow:
    """Stand-in for a Gtk.TreeModelRow used by the schedule ListStore."""
    def __init__(self, values, iter_idx):
        self._values = values
        self.iter = iter_idx

    def __getitem__(self, col):
        return self._values[col]


class FakeScheduleStore:
    """Minimal ListStore fake supporting the operations schedule_page uses."""
    def __init__(self, rows):
        self._rows = rows

    def get_iter_from_string(self, path):
        return int(path)

    def get_value(self, iter_idx, col):
        return self._rows[iter_idx][col]

    def set_value(self, iter_idx, col, val):
        self._rows[iter_idx][col] = val

    def __iter__(self):
        for i, row in enumerate(self._rows):
            yield FakeScheduleRow(row, i)


class TestScheduleDirtyTracking(unittest.TestCase):
    """Verify Save/Revert reflects active toggles and cron edits across rows."""

    COL_ACTIVE = 0
    COL_NAME = 1
    COL_NEXT_RUN_SORT = 5

    def _import_schedule_page(self):
        with mock_gtk():
            import schedule_page
            return schedule_page

    def _make_app(self, rows):
        app = MagicMock()
        app.schedule_store = FakeScheduleStore(rows)
        app.schedule_view.get_selection.return_value.get_selected.return_value = (
            app.schedule_store, 0,
        )
        app._schedule_save_button = MagicMock()
        app._schedule_pending = {}
        app._schedule_ignore_changes = False
        app.schedule_cron_entries = {
            "minute": MagicMock(),
            "hour": MagicMock(),
            "day": MagicMock(),
            "month": MagicMock(),
            "weekday": MagicMock(),
        }
        return app

    def _cron_text(self, app, cron):
        for key, val in cron.items():
            app.schedule_cron_entries[key].get_text.return_value = val

    @patch("schedule_page.set_button_markup_red")
    def test_active_toggle_marks_save_red(self, mock_red):
        schedule_page = self._import_schedule_page()
        rows = [[False, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows)
        saved_profile = {"profile_name": "p1", "active": False, "cron": {}}

        with patch("schedule_page.load_profile", return_value=saved_profile):
            schedule_page._on_active_toggled(None, "0", app)

        self.assertTrue(app._schedule_pending)
        self.assertEqual(app._schedule_pending["p1"]["active"], True)
        mock_red.assert_called_with(app._schedule_save_button, True)

    @patch("schedule_page.set_button_markup_red")
    def test_active_toggle_back_to_saved_clears_dirty(self, mock_red):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows)
        # The UI shows enabled but the saved profile is disabled,
        # so the row is dirty. Toggling it back to disabled clears the dirty state.
        saved_profile = {"profile_name": "p1", "active": False, "cron": {}}

        with patch("schedule_page.load_profile", return_value=saved_profile):
            schedule_page._on_active_toggled(None, "0", app)

        self.assertFalse(app._schedule_pending)
        mock_red.assert_called_with(app._schedule_save_button, False)

    @patch("schedule_page.set_button_markup_red")
    def test_cron_edit_marks_save_red(self, mock_red):
        schedule_page = self._import_schedule_page()
        rows = [[False, "p1", "backup", "0 2 * * *", "next", ""]]
        app = self._make_app(rows)
        saved_profile = {
            "profile_name": "p1",
            "active": False,
            "cron": {
                "minute": "0", "hour": "2",
                "day": "*", "month": "*", "weekday": "*",
            },
        }
        self._cron_text(app, {
            "minute": "30", "hour": "4",
            "day": "*", "month": "*", "weekday": "*",
        })

        with patch("schedule_page.load_profile", return_value=saved_profile):
            schedule_page._on_cron_entry_changed(None, app)

        self.assertIn("p1", app._schedule_pending)
        self.assertEqual(app._schedule_pending["p1"]["cron"]["minute"], "30")
        mock_red.assert_called_with(app._schedule_save_button, True)

    @patch("schedule_page.set_button_markup_red")
    def test_save_writes_all_pending_profiles(self, mock_red):
        schedule_page = self._import_schedule_page()
        rows = [
            [False, "p1", "backup", "* * * * *", "next", ""],
            [True, "p2", "offsite", "* * * * *", "next", ""],
        ]
        app = self._make_app(rows)
        app.schedule_view.get_selection.return_value.get_selected.return_value = (
            app.schedule_store, 0,
        )
        profiles = {
            "p1": {"profile_name": "p1", "active": True, "cron": {"minute": "0"}},
            "p2": {"profile_name": "p2", "active": False, "cron": {"minute": "0"}},
        }
        app._schedule_pending = {
            "p1": {"active": False},
            "p2": {"active": True, "cron": {"minute": "30", "hour": "*", "day": "*", "month": "*", "weekday": "*"}},
        }
        saved = []

        def fake_load(profile_name):
            return dict(profiles.get(profile_name, {}))

        def fake_save(profile):
            saved.append(dict(profile))

        with patch("schedule_page.load_profile", side_effect=fake_load), \
             patch("schedule_page.save_profile", side_effect=fake_save), \
             patch("schedule_page.list_profiles", return_value=list(profiles.values())), \
             patch("schedule_page.write_cron_file") as mock_write_cron, \
             patch("schedule_page.next_run_times", return_value=[SAMPLE_NEXT_RUN]):
            schedule_page.on_schedule_save(app)

        self.assertEqual(len(saved), 2)
        self.assertFalse(saved[0]["active"])   # p1 disabled
        self.assertEqual(saved[1]["cron"]["minute"], "30")
        self.assertTrue(saved[1]["active"])
        mock_write_cron.assert_called_once()
        self.assertFalse(app._schedule_pending)
        mock_red.assert_called_with(app._schedule_save_button, False)

    @patch("schedule_page.set_button_markup_red")
    def test_revert_restores_all_pending_profiles(self, mock_red):
        schedule_page = self._import_schedule_page()
        rows = [
            [False, "p1", "backup", "changed", "next", ""],
            [True, "p2", "offsite", "changed", "next", ""],
        ]
        app = self._make_app(rows)
        profiles = {
            "p1": {"profile_name": "p1", "active": True, "cron": {}},
            "p2": {"profile_name": "p2", "active": False, "cron": {}},
        }
        app._schedule_pending = {
            "p1": {"active": False},
            "p2": {"active": True},
        }

        with patch("schedule_page.load_profile", side_effect=lambda n: profiles.get(n)), \
             patch("schedule_page.next_run_times", return_value=[SAMPLE_NEXT_RUN]):
            schedule_page.on_schedule_revert(app)

        self.assertEqual(rows[0][self.COL_ACTIVE], True)
        self.assertEqual(rows[1][self.COL_ACTIVE], False)
        self.assertFalse(app._schedule_pending)
        mock_red.assert_called_with(app._schedule_save_button, False)


class TestConfigSummary(unittest.TestCase):
    """Verify the Config Summary text view shows the full profile config."""

    def _import_schedule_page(self):
        with mock_gtk():
            import schedule_page
            return schedule_page

    def _make_app(self, rows):
        app = MagicMock()
        app.schedule_store = FakeScheduleStore(rows)
        app.schedule_view.get_selection.return_value.get_selected.return_value = (
            app.schedule_store, 0,
        )
        app._schedule_save_button = MagicMock()
        app._schedule_pending = {}
        app._schedule_ignore_changes = False
        app.schedule_cron_entries = {
            "minute": MagicMock(),
            "hour": MagicMock(),
            "day": MagicMock(),
            "month": MagicMock(),
            "weekday": MagicMock(),
        }
        return app

    @patch("schedule_page.set_button_markup_red")
    def test_long_config_not_truncated(self, mock_red):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows)

        long_config = {
            "source": "threeamigos/proxmox",
            "dest": "fivebays/proxmox",
            "entries": [{"id": i, "data": "x" * 50} for i in range(50)],
        }
        full_summary = json.dumps(long_config, indent=2)
        self.assertGreater(len(full_summary), 2000)

        saved_profile = {
            "profile_name": "p1",
            "active": True,
            "cron": {},
            "config": long_config,
        }

        selection = MagicMock()
        selection.get_selected.return_value = (app.schedule_store, 0)

        with patch("schedule_page.load_profile", return_value=saved_profile):
            schedule_page._on_selection_changed(selection, app)

        actual = app.schedule_summary_textview.get_buffer().set_text.call_args[0][0]
        expected = f"Dry run: No\n\n{full_summary}"
        self.assertEqual(actual, expected)
        self.assertNotIn("truncated", actual)

    @patch("schedule_page.set_button_markup_red")
    def test_dry_run_shown_in_summary(self, mock_red):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows)

        saved_profile = {
            "profile_name": "p1",
            "active": True,
            "cron": {},
            "config": {"source": "tank/src"},
            "dry_run": True,
        }
        selection = MagicMock()
        selection.get_selected.return_value = (app.schedule_store, 0)

        with patch("schedule_page.load_profile", return_value=saved_profile):
            schedule_page._on_selection_changed(selection, app)

        actual = app.schedule_summary_textview.get_buffer().set_text.call_args[0][0]
        self.assertTrue(actual.startswith("Dry run: Yes\n\n"))

    @patch("schedule_page.Gtk")
    @patch("schedule_page.enable_textview_copy")
    @patch("schedule_page.list_profiles", return_value=[])
    def test_config_summary_uses_textview_with_copy_menu(self, _lst, mock_enable_copy, _mock_gtk):
        schedule_page = self._import_schedule_page()
        app = MagicMock()
        app._ui_state = MagicMock()

        schedule_page.create_schedule_page(app)

        self.assertTrue(hasattr(app, "schedule_summary_textview"))
        mock_enable_copy.assert_called_once_with(app.schedule_summary_textview)


class TestSchedulePageWidgets(unittest.TestCase):
    """Verify UI widget configuration for cron entries and sortable columns."""

    def _import_schedule_page(self):
        """Import schedule_page inside a GTK mock context."""
        with mock_gtk():
            import schedule_page
            return schedule_page

    @patch("schedule_page.Gtk")
    @patch("schedule_page.list_profiles", return_value=[])
    def test_cron_entries_are_fifteen_chars_wide(self, _lst, mock_gtk):
        schedule_page = self._import_schedule_page()
        app = MagicMock()
        app._ui_state = MagicMock()

        schedule_page.create_schedule_page(app)

        calls = mock_gtk.Entry.return_value.set_width_chars.call_args_list
        self.assertTrue(calls, "Expected set_width_chars to be called for cron entries")
        for call in calls:
            width = call[0][0]
            self.assertEqual(width, 15)

    @patch("schedule_page.Gtk")
    @patch("schedule_page.list_profiles", return_value=[])
    def test_next_run_profile_name_and_type_columns_are_sortable(self, _lst, mock_gtk):
        schedule_page = self._import_schedule_page()
        app = MagicMock()
        app._ui_state = MagicMock()

        schedule_page.create_schedule_page(app)

        sort_calls = mock_gtk.TreeViewColumn.return_value.set_sort_column_id.call_args_list
        sort_ids = {call[0][0] for call in sort_calls}
        self.assertIn(schedule_page.COL_NAME, sort_ids)
        self.assertIn(schedule_page.COL_TYPE, sort_ids)
        self.assertIn(schedule_page.COL_NEXT_RUN_SORT, sort_ids)

        clickable_calls = mock_gtk.TreeViewColumn.return_value.set_clickable.call_args_list
        self.assertTrue(
            any(call[0] == (True,) for call in clickable_calls),
            "Expected at least one sortable column to be marked clickable",
        )


class TestNextRunStrings(unittest.TestCase):
    """Verify _next_run_strings formatting and fallback behavior."""

    def _import_schedule_page(self):
        """Import schedule_page inside a GTK mock context."""
        with mock_gtk():
            import schedule_page
            return schedule_page

    @patch("schedule_page.next_run_times", return_value=[SAMPLE_NEXT_RUN])
    def test_next_run_strings_formats_datetime(self, _mock_next):
        schedule_page = self._import_schedule_page()
        display, sort_str = schedule_page._next_run_strings({})
        self.assertEqual(display, "Sun Jun 15 2025 10:00")
        self.assertEqual(sort_str, "2025-06-15 10:00")

    @patch("schedule_page.next_run_times", return_value=[])
    def test_next_run_strings_returns_fallback_when_no_runs(self, _mock_next):
        schedule_page = self._import_schedule_page()
        display, sort_str = schedule_page._next_run_strings({})
        self.assertEqual(
            display,
            "No upcoming runs found (schedule may be invalid or too restrictive.)",
        )
        self.assertEqual(sort_str, "")


class TestUpdateNextRunForIter(unittest.TestCase):
    """Verify _update_next_run_for_iter updates both display and sort columns."""

    def _import_schedule_page(self):
        """Import schedule_page inside a GTK mock context."""
        with mock_gtk():
            import schedule_page
            return schedule_page

    @patch("schedule_page.next_run_times", return_value=[SAMPLE_NEXT_RUN])
    @patch("schedule_page.load_profile")
    def test_update_next_run_for_iter_sets_both_columns(
        self, mock_load, _mock_next
    ):
        schedule_page = self._import_schedule_page()
        mock_load.return_value = {"profile_name": "p1", "cron": {}}
        rows = [[True, "p1", "backup", "* * * * *", "old", ""]]
        app = MagicMock()
        app.schedule_store = FakeScheduleStore(rows)

        schedule_page._update_next_run_for_iter(app, 0)

        self.assertEqual(
            app.schedule_store.get_value(0, schedule_page.COL_NEXT_RUN),
            "Sun Jun 15 2025 10:00",
        )
        self.assertEqual(
            app.schedule_store.get_value(0, schedule_page.COL_NEXT_RUN_SORT),
            "2025-06-15 10:00",
        )


class TestSchedulePageFrames(unittest.TestCase):
    """Tests for Schedule page layout helpers."""

    def _import_schedule_page(self):
        """Import schedule_page inside a GTK mock context."""
        with mock_gtk():
            import schedule_page
            return schedule_page

    @patch("schedule_page.Gtk")
    @patch("schedule_page._refresh_profile_list")
    @patch("schedule_page.list_profiles", return_value=[])
    def test_cron_frame_and_summary_expander_use_bold_label(
        self, _lst, _refresh, mock_gtk_module
    ):
        schedule_page = self._import_schedule_page()

        frame = MagicMock()
        expander = MagicMock()
        mock_gtk_module.Frame.side_effect = [frame]
        mock_gtk_module.Expander.side_effect = [expander]

        app = MagicMock()
        app._ui_state.bind_treeview = MagicMock()

        schedule_page.create_schedule_page(app)

        frame.set_label.assert_not_called()
        frame.set_label_widget.assert_called_once()
        expander.set_label.assert_not_called()
        expander.set_label_widget.assert_called_once()


if __name__ == "__main__":
    unittest.main()
