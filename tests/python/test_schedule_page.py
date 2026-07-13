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

# Import schedule_page once under the GTK mock so that @patch decorators on
# test methods do not pull in the real GTK module when they resolve names.
with mock_gtk():
    import schedule_page


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


class FakeTreePath:
    """Minimal stand-in for a Gtk.TreePath."""

    def __init__(self, idx):
        self._idx = idx

    def get_indices(self):
        return [self._idx]


class FakeScheduleStore:
    """Minimal ListStore fake supporting the operations schedule_page uses."""
    def __init__(self, rows):
        self._rows = rows

    def get_iter_from_string(self, path):
        return int(path)

    def get_iter(self, path):
        """Accept either an int index or a FakeTreePath."""
        if isinstance(path, int):
            return path
        return path.get_indices()[0]

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
        app.schedule_view.get_selection.return_value.get_selected_rows.return_value = (
            app.schedule_store, [FakeTreePath(0)],
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
    def test_active_toggle_selects_only_toggled_row(self, mock_red):
        """Toggling the Active checkbox must select only that row."""
        schedule_page = self._import_schedule_page()
        rows = [[False, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows)
        saved_profile = {"profile_name": "p1", "active": False, "cron": {}}

        with patch("schedule_page.load_profile", return_value=saved_profile):
            schedule_page._on_active_toggled(None, "0", app)

        selection = app.schedule_view.get_selection()
        selection.unselect_all.assert_called_once()
        selection.select_path.assert_called_once()

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
        app.schedule_view.get_selection.return_value.get_selected_rows.return_value = (
            app.schedule_store, [FakeTreePath(0)],
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
            "active": False,
            "cron": {},
            "config": long_config,
        }

        selection = MagicMock()
        selection.get_selected_rows.return_value = (app.schedule_store, [FakeTreePath(0)])

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
            "active": False,
            "cron": {},
            "config": {"source": "tank/src"},
            "dry_run": True,
        }
        selection = MagicMock()
        selection.get_selected_rows.return_value = (app.schedule_store, [FakeTreePath(0)])

        with patch("schedule_page.load_profile", return_value=saved_profile):
            schedule_page._on_selection_changed(selection, app)

        actual = app.schedule_summary_textview.get_buffer().set_text.call_args[0][0]
        self.assertTrue(actual.startswith("Dry run: Yes\n\n"))

    @patch("schedule_page.set_button_markup_red")
    def test_crontab_entry_shown_for_active_profile(self, mock_red):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "0 2 * * *", "next", ""]]
        app = self._make_app(rows)

        saved_profile = {
            "profile_name": "p1",
            "active": True,
            "cron": {
                "minute": "0", "hour": "2",
                "day": "*", "month": "*", "weekday": "*",
            },
            "config": {"source": "tank/src"},
        }
        selection = MagicMock()
        selection.get_selected_rows.return_value = (app.schedule_store, [FakeTreePath(0)])

        with patch("schedule_page.load_profile", return_value=saved_profile), \
             patch("schedule_page._resolve_profile_runner_path",
                   return_value="/fake/profile_runner.py"):
            schedule_page._on_selection_changed(selection, app)

        actual = app.schedule_summary_textview.get_buffer().set_text.call_args[0][0]
        expected_cron_line = schedule_page.generate_cron_line(
            saved_profile, "/fake/profile_runner.py"
        )
        self.assertTrue(actual.startswith("Crontab entry:\n"))
        self.assertIn(expected_cron_line, actual)
        self.assertIn("Dry run: No\n\n", actual)

    @patch("schedule_page.set_button_markup_red")
    def test_no_crontab_entry_for_inactive_profile(self, mock_red):
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
            "config": {"source": "tank/src"},
        }
        selection = MagicMock()
        selection.get_selected_rows.return_value = (app.schedule_store, [FakeTreePath(0)])

        with patch("schedule_page.load_profile", return_value=saved_profile):
            schedule_page._on_selection_changed(selection, app)

        actual = app.schedule_summary_textview.get_buffer().set_text.call_args[0][0]
        self.assertTrue(actual.startswith("Dry run: No\n\n"))
        self.assertNotIn("Crontab entry", actual)

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


class TestRunNow(unittest.TestCase):
    """Verify the Run Now button launches selected profiles immediately."""

    def _import_schedule_page(self):
        with mock_gtk():
            import schedule_page
            return schedule_page

    def _make_app(self, rows, selected_paths):
        app = MagicMock()
        app.schedule_store = FakeScheduleStore(rows)
        app.schedule_view.get_selection.return_value.get_selected_rows.return_value = (
            app.schedule_store, [FakeTreePath(p) for p in selected_paths]
        )
        app._running_profiles = set()
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

    def _make_popen(self, stdout_data="", stderr_data=""):
        process = MagicMock()
        process.stdout.fileno.return_value = 10
        process.stderr.fileno.return_value = 11
        process.pid = 12345
        process.stdout.read.side_effect = [stdout_data.encode(), b""]
        process.stderr.read.side_effect = [stderr_data.encode(), b""]
        return process

    def test_treeview_uses_multiple_selection(self):
        schedule_page = self._import_schedule_page()
        app = MagicMock()
        app._ui_state = MagicMock()

        with patch.object(schedule_page, "list_profiles", return_value=[]), \
             patch.object(schedule_page, "set_button_markup_red"), \
             patch.object(schedule_page, "Gtk") as mock_gtk_module:
            schedule_page.create_schedule_page(app)

        selection = app.schedule_view.get_selection()
        selection.set_mode.assert_called_once_with(
            mock_gtk_module.SelectionMode.MULTIPLE
        )

    @patch("schedule_page.set_button_markup_red")
    def test_run_now_with_no_selection_warns(self, _mock_red):
        schedule_page = self._import_schedule_page()
        app = self._make_app([], [])

        with patch("schedule_page.subprocess.Popen") as mock_popen, \
             patch("schedule_page.log_msg") as mock_log:
            schedule_page.on_schedule_run_now(app)

        mock_popen.assert_not_called()
        mock_log.assert_called_once_with("WARN: No profile selected")

    @patch("schedule_page.set_button_markup_red")
    @patch("schedule_page.os.set_blocking")
    @patch("schedule_page.GLib.io_add_watch")
    @patch("schedule_page.GLib.child_watch_add")
    def test_run_now_launches_selected_profiles(self, mock_child_watch,
                                                 mock_io_add_watch,
                                                 _mock_set_blocking,
                                                 _mock_red):
        schedule_page = self._import_schedule_page()
        rows = [
            [False, "p1", "backup", "* * * * *", "next", ""],
            [False, "p2", "offsite", "* * * * *", "next", ""],
        ]
        app = self._make_app(rows, [0, 1])

        process1 = self._make_popen(stdout_data="out1")
        process2 = self._make_popen(stdout_data="out2")
        mock_popen = MagicMock(side_effect=[process1, process2])

        with patch("schedule_page.subprocess.Popen", mock_popen), \
             patch("schedule_page._resolve_profile_runner_path",
                   return_value="/fake/profile_runner.py"):
            schedule_page.on_schedule_run_now(app)

        self.assertEqual(mock_popen.call_count, 2)
        self.assertEqual(
            mock_popen.call_args_list[0][0][0],
            [sys.executable, "/fake/profile_runner.py", "run", "p1"],
        )
        self.assertEqual(
            mock_popen.call_args_list[1][0][0],
            [sys.executable, "/fake/profile_runner.py", "run", "p2"],
        )
        self.assertEqual(app._running_profiles, {"p1", "p2"})
        self.assertEqual(mock_io_add_watch.call_count, 4)
        mock_child_watch.assert_called()

    @patch("schedule_page.set_button_markup_red")
    @patch("schedule_page.os.set_blocking")
    @patch("schedule_page.GLib.io_add_watch")
    @patch("schedule_page.GLib.child_watch_add")
    def test_run_now_ignores_active_flag(self, _mock_child_watch,
                                         _mock_io_add_watch,
                                         _mock_set_blocking,
                                         _mock_red):
        schedule_page = self._import_schedule_page()
        rows = [[False, "inactive", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows, [0])
        process = self._make_popen()

        with patch("schedule_page.subprocess.Popen", return_value=process), \
             patch("schedule_page._resolve_profile_runner_path",
                   return_value="/fake/profile_runner.py"):
            schedule_page.on_schedule_run_now(app)

        self.assertIn("inactive", app._running_profiles)

    @patch("schedule_page.set_button_markup_red")
    @patch("schedule_page.os.set_blocking")
    def test_run_now_logs_profile_output_with_prefix(self, _mock_set_blocking,
                                                     _mock_red):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows, [0])
        process = self._make_popen(stdout_data="line1\nline2")

        captured = []
        with patch("schedule_page.subprocess.Popen", return_value=process), \
             patch("schedule_page._resolve_profile_runner_path",
                   return_value="/fake/profile_runner.py"), \
             patch("schedule_page.log_msg", side_effect=captured.append), \
             patch("schedule_page.os.read",
                   return_value=b"line1\nline2\n"):
            schedule_page.on_schedule_run_now(app)
            # Simulate the io_add_watch callback directly
            callback = schedule_page._log_profile_line
            callback(process.stdout.fileno(),
                     schedule_page.GLib.IOCondition.IN,
                     app, "p1", "[p1] ")

        self.assertTrue(
            any("[p1] line1" in msg for msg in captured),
            f"Expected prefixed line1 in {captured}"
        )
        self.assertTrue(
            any("[p1] line2" in msg for msg in captured),
            f"Expected prefixed line2 in {captured}"
        )

    @patch("schedule_page.set_button_markup_red")
    @patch("schedule_page.os.set_blocking")
    @patch("schedule_page.GLib.io_add_watch")
    @patch("schedule_page.GLib.child_watch_add")
    def test_run_now_child_watch_uses_new_signature(self, mock_child_watch,
                                                    mock_io_add_watch,
                                                    _mock_set_blocking,
                                                    _mock_red):
        """Regression: child_watch_add must use the modern GLib signature."""
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows, [0])
        process = self._make_popen()

        with patch("schedule_page.subprocess.Popen", return_value=process), \
             patch("schedule_page._resolve_profile_runner_path",
                   return_value="/fake/profile_runner.py"):
            schedule_page.on_schedule_run_now(app)

        self.assertEqual(mock_child_watch.call_count, 1)
        args = mock_child_watch.call_args[0]
        self.assertEqual(args[0], schedule_page.GLib.PRIORITY_DEFAULT)
        self.assertEqual(args[1], process.pid)
        self.assertIs(args[2], schedule_page._on_profile_finished)
        self.assertIs(args[3][0], app)
        self.assertEqual(args[3][1], "p1")
        self.assertIs(args[3][2], process)

    @patch("schedule_page.log_msg")
    def test_on_profile_finished_reaps_and_updates_state(self, mock_log):
        """_on_profile_finished must unpack the tuple user_data correctly."""
        schedule_page = self._import_schedule_page()
        app = self._make_app([], [])
        app._running_profiles.add("p1")
        process = MagicMock()

        schedule_page._on_profile_finished(12345, 0, (app, "p1", process))

        process.wait.assert_called_once()
        self.assertNotIn("p1", app._running_profiles)
        mock_log.assert_called_once_with("INFO: Profile finished: p1")
        app.update_action_buttons.assert_called_once_with("schedule")

    @patch("schedule_page.set_button_markup_red")
    @patch("schedule_page.os.set_blocking")
    @patch("schedule_page.GLib.io_add_watch")
    @patch("schedule_page.GLib.child_watch_add")
    @patch("schedule_page.log_msg")
    def test_run_now_watch_failure_is_fatal(self, mock_log, mock_child_watch,
                                            _mock_io_add_watch,
                                            _mock_set_blocking, _mock_red):
        """If GLib watch setup fails, the run aborts and a FATAL is logged."""
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows, [0])
        process = self._make_popen()
        mock_child_watch.side_effect = TypeError(
            "expected at most 4 positional arguments"
        )

        with patch("schedule_page.subprocess.Popen", return_value=process), \
             patch("schedule_page._resolve_profile_runner_path",
                   return_value="/fake/profile_runner.py"):
            schedule_page.on_schedule_run_now(app)

        process.terminate.assert_called_once()
        self.assertNotIn("p1", app._running_profiles)
        app.update_action_buttons.assert_called_with("schedule")
        fatal_calls = [
            c for c in mock_log.call_args_list
            if c[0] and c[0][0].startswith("FATAL:")
        ]
        self.assertEqual(len(fatal_calls), 1)
        self.assertIn(
            "expected at most 4 positional arguments",
            fatal_calls[0][0][0],
        )


class TestScheduleDelete(unittest.TestCase):
    """Verify the Delete button works with the MULTIPLE-selection TreeView."""

    def _import_schedule_page(self):
        with mock_gtk():
            import schedule_page
            return schedule_page

    def _make_app(self, rows, selected_paths):
        app = MagicMock()
        app.schedule_store = FakeScheduleStore(rows)
        app.schedule_view.get_selection.return_value.get_selected_rows.return_value = (
            app.schedule_store, [FakeTreePath(p) for p in selected_paths],
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
    @patch("schedule_page._refresh_profile_list")
    @patch("schedule_page._regenerate_cron")
    @patch("schedule_page.delete_profile")
    @patch("schedule_page.Gtk.MessageDialog")
    def test_delete_removes_first_selected_profile(
        self, mock_dialog, mock_delete, mock_regenerate, mock_refresh, _mock_red
    ):
        schedule_page = self._import_schedule_page()
        rows = [
            [True, "p1", "backup", "0 2 * * *", "next", ""],
            [False, "p2", "offsite", "0 3 * * *", "next", ""],
        ]
        app = self._make_app(rows, [0, 1])
        mock_dialog.return_value.run.return_value = schedule_page.Gtk.ResponseType.YES

        schedule_page.on_schedule_delete(app)

        mock_delete.assert_called_once_with("p1")
        mock_regenerate.assert_called_once_with(app)
        mock_refresh.assert_called_once_with(app)

    @patch("schedule_page.set_button_markup_red")
    @patch("schedule_page._refresh_profile_list")
    @patch("schedule_page._regenerate_cron")
    @patch("schedule_page.delete_profile")
    @patch("schedule_page.Gtk.MessageDialog")
    def test_delete_cancel_does_nothing(
        self, mock_dialog, mock_delete, mock_regenerate, mock_refresh, _mock_red
    ):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "0 2 * * *", "next", ""]]
        app = self._make_app(rows, [0])
        mock_dialog.return_value.run.return_value = schedule_page.Gtk.ResponseType.NO

        schedule_page.on_schedule_delete(app)

        mock_delete.assert_not_called()
        mock_regenerate.assert_not_called()
        mock_refresh.assert_not_called()

    @patch("schedule_page.set_button_markup_red")
    @patch("schedule_page._refresh_profile_list")
    @patch("schedule_page._regenerate_cron")
    @patch("schedule_page.delete_profile")
    @patch("schedule_page.log_msg")
    def test_delete_with_no_selection_warns(
        self, mock_log, mock_delete, mock_regenerate, mock_refresh, _mock_red
    ):
        schedule_page = self._import_schedule_page()
        app = self._make_app([], [])

        schedule_page.on_schedule_delete(app)

        mock_log.assert_called_once_with("WARN: No profile selected")
        mock_delete.assert_not_called()
        mock_regenerate.assert_not_called()
        mock_refresh.assert_not_called()


class TestRefreshSchedulePage(unittest.TestCase):
    """Verify refresh_schedule_page updates Next Run and preserves state."""

    COL_ACTIVE = 0
    COL_NAME = 1
    COL_TYPE = 2
    COL_SCHEDULE = 3
    COL_NEXT_RUN = 4
    COL_NEXT_RUN_SORT = 5

    def _import_schedule_page(self):
        with mock_gtk():
            import schedule_page
            return schedule_page

    def _make_app(self, rows, selected_paths=None):
        app = MagicMock()
        app.schedule_store = FakeScheduleStore(rows)
        selection = MagicMock()
        if selected_paths is None:
            selection.get_selected_rows.return_value = (app.schedule_store, [])
        else:
            selection.get_selected_rows.return_value = (
                app.schedule_store, [FakeTreePath(p) for p in selected_paths]
            )
        app.schedule_view.get_selection.return_value = selection
        app._schedule_save_button = MagicMock()
        app._schedule_pending = {}
        app._schedule_ignore_changes = False
        return app

    @patch("schedule_page.log_msg")
    @patch("schedule_page.next_run_times", return_value=[SAMPLE_NEXT_RUN])
    @patch("schedule_page.load_profile")
    @patch("schedule_page.set_button_markup_red")
    def test_refresh_updates_next_run_in_place(
        self, _mock_red, mock_load, _mock_next, _mock_log
    ):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "old run", ""]]
        app = self._make_app(rows)
        profile = {
            "profile_name": "p1",
            "active": True,
            "tab_type": "backup",
            "cron": {"minute": "*", "hour": "*", "day": "*", "month": "*", "weekday": "*"},
        }
        mock_load.return_value = profile

        with patch("schedule_page.list_profiles", return_value=[profile]):
            schedule_page.refresh_schedule_page(app)

        self.assertEqual(
            app.schedule_store.get_value(0, self.COL_NEXT_RUN),
            "Sun Jun 15 2025 10:00",
        )
        self.assertEqual(
            app.schedule_store.get_value(0, self.COL_NEXT_RUN_SORT),
            "2025-06-15 10:00",
        )

    @patch("schedule_page.log_msg")
    @patch("schedule_page._refresh_profile_list")
    @patch("schedule_page.set_button_markup_red")
    def test_refresh_rebuilds_when_profile_list_changes(
        self, _mock_red, mock_refresh, _mock_log
    ):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows)
        profiles = [
            {
                "profile_name": "p1",
                "active": True,
                "tab_type": "backup",
                "cron": {"minute": "*", "hour": "*", "day": "*", "month": "*", "weekday": "*"},
            },
            {
                "profile_name": "p2",
                "active": False,
                "tab_type": "offsite",
                "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
            },
        ]

        with patch("schedule_page.list_profiles", return_value=profiles):
            schedule_page.refresh_schedule_page(app)

        mock_refresh.assert_called_once_with(app)

    @patch("schedule_page.log_msg")
    @patch("schedule_page.next_run_times", return_value=[SAMPLE_NEXT_RUN])
    @patch("schedule_page.load_profile")
    @patch("schedule_page.set_button_markup_red")
    def test_refresh_preserves_pending_changes(
        self, _mock_red, mock_load, _mock_next, _mock_log
    ):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "old run", ""]]
        app = self._make_app(rows)
        app._schedule_pending = {"p1": {"active": False}}
        profile = {
            "profile_name": "p1",
            "active": True,
            "tab_type": "backup",
            "cron": {"minute": "*", "hour": "*", "day": "*", "month": "*", "weekday": "*"},
        }
        mock_load.return_value = profile

        with patch("schedule_page.list_profiles", return_value=[profile]):
            schedule_page.refresh_schedule_page(app)

        self.assertEqual(app._schedule_pending, {"p1": {"active": False}})

    @patch("schedule_page.log_msg")
    @patch("schedule_page._refresh_profile_list")
    @patch("schedule_page.set_button_markup_red")
    def test_refresh_clears_pending_for_deleted_profile(
        self, mock_red, mock_refresh, _mock_log
    ):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "next", ""]]
        app = self._make_app(rows)
        app._schedule_pending = {"p1": {"active": False}, "p2": {"active": True}}
        profiles = [
            {
                "profile_name": "p2",
                "active": True,
                "tab_type": "offsite",
                "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
            },
        ]

        with patch("schedule_page.list_profiles", return_value=profiles):
            schedule_page.refresh_schedule_page(app)

        self.assertEqual(app._schedule_pending, {"p2": {"active": True}})
        mock_red.assert_called_once_with(app._schedule_save_button, True)

    @patch("schedule_page.log_msg")
    @patch("schedule_page.next_run_times", return_value=[SAMPLE_NEXT_RUN])
    @patch("schedule_page.load_profile")
    def test_refresh_restores_selection(
        self, mock_load, _mock_next, _mock_log
    ):
        schedule_page = self._import_schedule_page()
        rows = [[True, "p1", "backup", "* * * * *", "old run", ""]]
        app = self._make_app(rows, selected_paths=[0])
        profile = {
            "profile_name": "p1",
            "active": True,
            "tab_type": "backup",
            "cron": {"minute": "*", "hour": "*", "day": "*", "month": "*", "weekday": "*"},
        }
        mock_load.return_value = profile

        with patch("schedule_page.list_profiles", return_value=[profile]):
            schedule_page.refresh_schedule_page(app)

        selection = app.schedule_view.get_selection()
        selection.unselect_all.assert_called_once()
        selection.select_iter.assert_called_once()


if __name__ == "__main__":
    unittest.main()
