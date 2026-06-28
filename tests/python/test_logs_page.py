"""Tests for logs_page.py — log list and viewer helpers."""

import os
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


@contextmanager
def _patch_log_dir(tmpdir):
    """Patch both logs_page and log_index to use tmpdir as SESSION_LOG_DIR."""
    with patch("logs_page.SESSION_LOG_DIR", tmpdir), \
            patch("log_index.SESSION_LOG_DIR", tmpdir):
        yield


def _make_scan_app():
    """Return a minimal mocked app for _scan_logs()."""
    return type("App", (), {})()

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk

with mock_gtk():
    import logs_page as lp


class TestFilterLogText(unittest.TestCase):

    def test_shows_all_at_debug(self):
        text = (
            "2026-06-21 10:00:00  /a:1: DEBUG: d\n"
            "2026-06-21 10:00:01  /a:1: INFO: i\n"
            "2026-06-21 10:00:02  /a:1: WARN: w\n"
            "# END: rc=0, duration=1.0s\n"
        )
        result = lp._filter_log_text(text, "DEBUG")
        self.assertIn("DEBUG: d", result)
        self.assertIn("INFO: i", result)
        self.assertIn("WARN: w", result)
        self.assertIn("# END:", result)

    def test_hides_lower_levels(self):
        text = (
            "2026-06-21 10:00:00  /a:1: DEBUG: d\n"
            "2026-06-21 10:00:01  /a:1: INFO: i\n"
            "2026-06-21 10:00:02  /a:1: WARN: w\n"
        )
        result = lp._filter_log_text(text, "WARN")
        self.assertNotIn("DEBUG: d", result)
        self.assertNotIn("INFO: i", result)
        self.assertIn("WARN: w", result)

    def test_unrecognized_lines_are_always_visible(self):
        text = (
            "2026-06-21 10:00:00  /a:1: INFO: i\n"
            "raw subprocess output\n"
            "# END: rc=0, duration=1.0s\n"
        )
        result = lp._filter_log_text(text, "FATAL")
        self.assertNotIn("INFO: i", result)
        self.assertIn("raw subprocess output", result)
        self.assertIn("# END:", result)


class TestSelectLogByPath(unittest.TestCase):

    def _make_app(self, rows):
        app = MagicMock()
        store = MagicMock()
        store.get_iter_first.side_effect = self._iter_chain(rows)
        store.get_value = lambda it, col: rows[it["idx"]][col]
        store.iter_next.side_effect = self._next_fn(rows)
        app.logs_store = store

        selection = MagicMock()
        view = MagicMock()
        view.get_selection.return_value = selection
        app.logs_view = view
        return app, selection

    def _iter_chain(self, rows):
        iters = [{"idx": i} for i in range(len(rows))]
        calls = []

        def first():
            calls.append("first")
            return iters[0] if iters else None

        def next_fn(current):
            calls.append("next")
            idx = current["idx"] + 1
            return iters[idx] if idx < len(iters) else None

        self._first = first
        self._next = next_fn
        return first

    def _next_fn(self, rows):
        def next_fn(current):
            idx = current["idx"] + 1
            return ({"idx": idx} if idx < len(rows) else None)
        return next_fn

    @patch("logs_page._sync_log_list")
    def test_selects_matching_row(self, mock_sync):
        rows = [
            ("dt", "backup", "gui", "Done", "1 MB", "", "", "/a.log"),
            ("dt", "offsite", "gui", "Done", "1 MB", "", "", "/b.log"),
        ]
        app, selection = self._make_app(rows)
        result = lp.select_log_by_path(app, "/b.log")
        self.assertTrue(result)
        mock_sync.assert_called_once_with(app)
        selection.unselect_all.assert_called_once()
        selection.select_iter.assert_called_once()
        selected = selection.select_iter.call_args[0][0]
        self.assertEqual(selected["idx"], 1)

    @patch("logs_page._sync_log_list")
    def test_returns_false_when_not_found(self, mock_sync):
        rows = [
            ("dt", "backup", "gui", "Done", "1 MB", "", "", "/a.log"),
        ]
        app, selection = self._make_app(rows)
        result = lp.select_log_by_path(app, "/missing.log")
        self.assertFalse(result)
        selection.select_iter.assert_not_called()

    @patch("logs_page._sync_log_list")
    def test_returns_false_for_empty_path(self, mock_sync):
        app, selection = self._make_app([])
        result = lp.select_log_by_path(app, "")
        self.assertFalse(result)
        mock_sync.assert_not_called()


class TestDeleteSelectedLogs(unittest.TestCase):

    def _make_app(self, paths):
        """Return a mocked app and selection for the given log paths."""
        app = MagicMock()
        selection = MagicMock()
        view = MagicMock()
        view.get_selection.return_value = selection
        app.logs_view = view

        model = MagicMock()
        iters = [{"path": p} for p in paths]
        model.get_iter.side_effect = lambda p: next(
            (it for it in iters if it["path"] == p), None
        )
        model.get_value.side_effect = lambda it, col: it["path"]
        selection.get_selected_rows.return_value = (model, paths)
        return app, selection, model

    @patch("logs_page.Gtk.MessageDialog")
    def test_deletes_multiple_selected_logs(self, mock_dialog_cls):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = [
                os.path.join(tmpdir, "2026-06-21_10-00-00_backup_gui.log"),
                os.path.join(tmpdir, "2026-06-21_11-00-00_offsite_gui.log"),
            ]
            for p in paths:
                with open(p, "w") as f:
                    f.write("log content")

            mock_dialog = MagicMock()
            mock_dialog.run.return_value = lp.Gtk.ResponseType.YES
            mock_dialog_cls.return_value = mock_dialog

            app, selection, _model = self._make_app(paths)
            with patch("logs_page._sync_log_list") as mock_sync:
                lp._on_delete_selected(app)

            for p in paths:
                self.assertFalse(os.path.exists(p))
            mock_sync.assert_called_once_with(app)

    @patch("logs_page.Gtk.MessageDialog")
    def test_cancels_when_user_declines(self, mock_dialog_cls):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-21_10-00-00_backup_gui.log")
            with open(path, "w") as f:
                f.write("log content")

            mock_dialog = MagicMock()
            mock_dialog.run.return_value = lp.Gtk.ResponseType.NO
            mock_dialog_cls.return_value = mock_dialog

            app, selection, _model = self._make_app([path])
            with patch("logs_page._sync_log_list") as mock_sync:
                lp._on_delete_selected(app)

            self.assertTrue(os.path.exists(path))
            mock_sync.assert_not_called()

    def test_warns_when_no_logs_selected(self):
        app, selection, _model = self._make_app([])
        with patch("logs_page.log_msg") as mock_log_msg:
            lp._on_delete_selected(app)
        mock_log_msg.assert_called_once_with("WARN: No log selected")

    @patch("logs_page.Gtk.MessageDialog")
    def test_continues_on_partial_delete_failure(self, mock_dialog_cls):
        with tempfile.TemporaryDirectory() as tmpdir:
            path_good = os.path.join(tmpdir, "good.log")
            path_bad = os.path.join(tmpdir, "bad.log")
            with open(path_good, "w") as f:
                f.write("good")
            # path_bad is intentionally not created so os.remove fails

            mock_dialog = MagicMock()
            mock_dialog.run.return_value = lp.Gtk.ResponseType.YES
            mock_dialog_cls.return_value = mock_dialog

            app, selection, _model = self._make_app([path_good, path_bad])
            with patch("logs_page._sync_log_list") as mock_sync:
                lp._on_delete_selected(app)

            self.assertFalse(os.path.exists(path_good))
            mock_sync.assert_called_once_with(app)


class TestLogsSelectionChanged(unittest.TestCase):

    def test_disables_button_when_nothing_selected(self):
        app = MagicMock()
        button = MagicMock()
        app._logs_delete_button = button
        selection = MagicMock()
        selection.get_selected_rows.return_value = (MagicMock(), [])

        lp._on_logs_selection_changed(selection, app)
        button.set_sensitive.assert_called_once_with(False)

    def test_enables_button_when_logs_selected(self):
        app = MagicMock()
        button = MagicMock()
        app._logs_delete_button = button
        selection = MagicMock()
        selection.get_selected_rows.return_value = (MagicMock(), ["/a.log", "/b.log"])

        lp._on_logs_selection_changed(selection, app)
        button.set_sensitive.assert_called_once_with(True)

    def test_ignores_missing_button(self):
        app = MagicMock()
        # No _logs_delete_button attribute
        selection = MagicMock()
        selection.get_selected_rows.return_value = (MagicMock(), ["/a.log"])

        lp._on_logs_selection_changed(selection, app)
        # Should not raise


class TestSyncLogListPreservesSelection(unittest.TestCase):

    def test_reselects_existing_paths(self):
        app = MagicMock()
        selection = MagicMock()
        app.logs_view.get_selection.return_value = selection

        rows = [
            ("dt", "backup", "gui", "Done", "1 MB", "", "", "/a.log"),
            ("dt", "offsite", "gui", "Done", "1 MB", "", "", "/b.log"),
            ("dt", "prune", "gui", "Done", "1 MB", "", "", "/c.log"),
        ]

        store = MagicMock()
        iters = [{"path": r[lp.COL_PATH]} for r in rows]
        store.get_iter_first.side_effect = self._iter_first(iters)
        store.iter_next.side_effect = self._iter_next(iters)
        store.get_iter.side_effect = lambda p: next(
            (it for it in iters if it["path"] == p), None
        )
        store.get_value.side_effect = lambda it, col: it["path"]
        app.logs_store = store

        selection.get_selected_rows.return_value = (store, ["/a.log", "/c.log"])

        with patch("logs_page._scan_logs", return_value=rows):
            with patch("logs_page._update_success_rate_label"):
                lp._sync_log_list(app)

        selected_paths = {
            call[0][0]["path"]
            for call in selection.select_iter.call_args_list
        }
        self.assertEqual(selected_paths, {"/a.log", "/c.log"})

    def _iter_first(self, iters):
        def first():
            return iters[0] if iters else None
        return first

    def _iter_next(self, iters):
        def next_fn(current):
            idx = iters.index(current) + 1
            return iters[idx] if idx < len(iters) else None
        return next_fn


class TestLoadLogIntoViewer(unittest.TestCase):
    """_load_log_into_viewer loads full small files and tails large ones."""

    def _make_app(self, path, file_size):
        app = MagicMock()
        app._logs_current_path = path
        app._logs_file_size = file_size
        app._logs_read_offset = 0
        app._logs_full_mode = False
        app.logs_viewer_level = "DEBUG"
        app.logs_show_more_btn.get_visible.return_value = False
        buf = MagicMock()
        app.logs_text.get_buffer.return_value = buf
        return app, buf

    def test_small_file_loads_full(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "small.log")
            with open(path, "w") as fh:
                fh.write("line1\nline2\n")
            app, buf = self._make_app(path, os.path.getsize(path))
            lp._load_log_into_viewer(app)
            self.assertEqual(app._logs_read_offset, os.path.getsize(path))
            inserted = "".join(call[0][1] for call in buf.insert.call_args_list)
            self.assertIn("line1", inserted)
            self.assertIn("line2", inserted)
            app.logs_load_full_btn.hide.assert_called()

    def test_large_file_loads_tail_and_shows_load_full(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "large.log")
            with open(path, "w") as fh:
                fh.write("START\n")
                for i in range(50000):
                    fh.write(f"line {i} padding to make the file large enough\n")
                fh.write("END\n")
            size = os.path.getsize(path)
            self.assertGreater(size, lp.MAX_VIEWER_FULL_READ_BYTES)
            app, buf = self._make_app(path, size)
            # Allow the chunked tail loader to read all remaining chunks.
            app.logs_show_more_btn.get_visible.side_effect = [True, True, True, True, False]
            lp._load_log_into_viewer(app)
            app.logs_load_full_btn.show.assert_called()
            inserted = "".join(call[0][1] for call in buf.insert.call_args_list)
            self.assertIn("END", inserted)
            self.assertNotIn("START", inserted)
            header = buf.set_text.call_args[0][0]
            self.assertIn("showing last", header)
            self.assertIn("Load Full Log", header)


class TestTailLogFileBufferCap(unittest.TestCase):
    """_tail_log_file drops old buffer content when it grows too large."""

    def _make_app(self, path, file_size, read_offset, char_count=None):
        app = MagicMock()
        app._logs_current_path = path
        app._logs_file_size = file_size
        app._logs_read_offset = read_offset
        app.logs_viewer_level = "DEBUG"
        app._logs_tail_timer = None
        app._log_index = None
        buf = MagicMock()
        if char_count is None:
            char_count = lp.MAX_VIEWER_BUFFER_CHARS
        buf.get_char_count.return_value = char_count
        app.logs_text.get_buffer.return_value = buf
        vadj = MagicMock()
        vadj.get_value.return_value = 0
        vadj.get_upper.return_value = 100
        vadj.get_page_size.return_value = 20
        app.logs_text_scroll.get_vadjustment.return_value = vadj
        return app, buf

    def test_truncates_buffer_when_it_exceeds_cap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "growing.log")
            with open(path, "w") as fh:
                fh.write("old text\n")
                fh.write("new tail line\n")
            size = os.path.getsize(path)
            # _logs_file_size must be smaller than the actual file size so the
            # tailer sees new bytes to read.
            app, buf = self._make_app(path, size - 1, 0)
            result = lp._tail_log_file(app)
            self.assertTrue(result)
            buf.delete.assert_called_once()
            inserted = "".join(call[0][1] for call in buf.insert.call_args_list)
            self.assertIn("new tail line", inserted)

    def test_does_not_truncates_buffer_when_below_cap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "small.log")
            with open(path, "w") as fh:
                fh.write("new tail line\n")
            size = os.path.getsize(path)
            app, buf = self._make_app(path, size - 1, 0, char_count=lp.MAX_VIEWER_BUFFER_CHARS // 2)
            result = lp._tail_log_file(app)
            self.assertTrue(result)
            buf.delete.assert_not_called()


class TestLoadFullLogClicked(unittest.TestCase):
    """_on_load_full_log_clicked switches tail mode to full-file mode."""

    def test_small_file_switches_without_dialog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "medium.log")
            with open(path, "w") as fh:
                for i in range(100):
                    fh.write(f"line {i}\n")
            app = MagicMock()
            app._logs_current_path = path
            app._logs_file_size = os.path.getsize(path)
            app._logs_full_mode = False
            app.logs_show_more_btn.get_visible.return_value = False
            app.logs_text.get_buffer.return_value = MagicMock()
            lp._on_load_full_log_clicked(app)
            self.assertTrue(app._logs_full_mode)

    def test_large_file_shows_confirmation_dialog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "large.log")
            with open(path, "w") as fh:
                fh.write("START\n")
                for i in range(50000):
                    fh.write(f"line {i} padding to make the file large enough\n")
                fh.write("END\n")
            app = MagicMock()
            app._logs_current_path = path
            app._logs_file_size = os.path.getsize(path)
            app._logs_full_mode = False
            app.logs_show_more_btn.get_visible.return_value = False
            app.logs_text.get_buffer.return_value = MagicMock()
            dialog = MagicMock()
            dialog.run.return_value = lp.Gtk.ResponseType.YES
            with patch("logs_page.Gtk.MessageDialog", return_value=dialog):
                lp._on_load_full_log_clicked(app)
            dialog.run.assert_called_once()
            self.assertTrue(app._logs_full_mode)


class TestLogsLevelChanged(unittest.TestCase):

    def test_changes_level_and_reloads(self):
        app = MagicMock()
        app.logs_viewer_level = "DEBUG"
        app._logs_current_path = "/tmp/test.log"
        app._logs_read_offset = 100
        app._logs_file_size = 200
        app.logs_show_more_btn.get_visible.return_value = False
        app.logs_text_scroll.get_vadjustment.return_value = MagicMock(
            get_value=lambda: 10, get_upper=lambda: 100, get_page_size=lambda: 20
        )

        combo = MagicMock()
        combo.get_active_text.return_value = "WARN"

        with patch("logs_page._load_log_into_viewer") as mock_load:
            with patch("logs_page.GLib.idle_add") as mock_idle:
                lp._on_logs_level_changed(combo, app)

        self.assertEqual(app.logs_viewer_level, "WARN")
        app.logs_text.get_buffer().set_text.assert_called_once_with("")
        mock_load.assert_called_once_with(app)
        mock_idle.assert_called_once()


class TestScanLogStatus(unittest.TestCase):

    def _write_log(self, tmpdir, name, content):
        path = os.path.join(tmpdir, name)
        with open(path, "w") as fh:
            fh.write(content)
        return path

    def test_rc0_no_warnings_shows_done(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: INFO: ok\n# END: rc=0, duration=1.0s\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][lp.COL_STATUS], "Done")

    def test_rc0_with_warn_shows_warn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: WARN: host down\n"
                "# END: rc=0, duration=1.0s\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Warn")

    def test_rc255_with_warn_shows_warn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: WARN: step exited with rc=255\n"
                "# END: rc=255, duration=1.0s\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Warn")

    def test_rc255_no_warnings_shows_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: INFO: ok\n"
                "# END: rc=255, duration=1.0s\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Failed")

    def test_rc1_with_fatal_shows_fatal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: FATAL: abort\n"
                "# END: rc=1, duration=1.0s\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Fatal")

    def test_cancelled_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: INFO: ok\n"
                "# END: cancelled, duration=1.0s\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Cancelled")

    def test_running_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: WARN: something\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Running")

    def test_both_warn_and_fatal_shows_fatal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: WARN: host down\n"
                "2026-06-22 07:00:01  /a:1: FATAL: abort\n"
                "# END: rc=255, duration=1.0s\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Fatal")

    def test_info_level_uses_trailer_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_log(
                tmpdir, "2026-06-22_07-00-00_backup_profile-x.log",
                "2026-06-22 07:00:00  /a:1: DEBUG: detail\n"
                "2026-06-22 07:00:01  /a:1: VERB: detail\n"
                "2026-06-22 07:00:02  /a:1: INFO: ok\n"
                "# END: rc=0, duration=1.0s\n",
            )
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Done")

    def test_old_log_without_trailer_with_warn_shows_warn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_profile-x.log")
            with open(path, "w") as fh:
                fh.write("2026-06-22 07:00:00  /a:1: WARN: something\n")
            # Make the file older than the 10-second "running" window
            old_mtime = time.time() - 20
            os.utime(path, (old_mtime, old_mtime))
            with _patch_log_dir(tmpdir):
                rows = lp._scan_logs(_make_scan_app())
            self.assertEqual(rows[0][lp.COL_STATUS], "Warn")


class TestLogIndexIntegration(unittest.TestCase):

    def test_scan_logs_creates_persistent_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_profile-x.log")
            with open(path, "w") as fh:
                fh.write(
                    "2026-06-22 07:00:00  /a:1: WARN: host down\n"
                    "# END: rc=0, duration=5.5s, bytes=2048\n"
                )

            with _patch_log_dir(tmpdir):
                app = _make_scan_app()
                rows = lp._scan_logs(app)
                index_path = os.path.join(tmpdir, ".log_index.json")
                self.assertTrue(os.path.exists(index_path))

                # Second scan should reuse the cached index and produce the same row.
                rows2 = lp._scan_logs(app)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][lp.COL_STATUS], "Warn")
        self.assertEqual(rows[0][lp.COL_DURATION], "00:00:06")
        self.assertEqual(rows[0][lp.COL_BYTES], "2.0 KB")
        self.assertEqual(rows, rows2)

    def test_delete_selected_removes_index_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "2026-06-22_07-00-00_backup_gui.log")
            with open(path, "w") as f:
                f.write("log content\n# END: rc=0, duration=1.0s\n")

            with _patch_log_dir(tmpdir):
                app = _make_scan_app()
                lp._scan_logs(app)

                # Set up a selection pointing to the log file.
                selection = MagicMock()
                view = MagicMock()
                view.get_selection.return_value = selection
                app.logs_view = view
                model = MagicMock()
                iters = [{"path": path}]
                model.get_iter.side_effect = lambda p: next(
                    (it for it in iters if it["path"] == p), None
                )
                model.get_value.side_effect = lambda it, col: it["path"]
                selection.get_selected_rows.return_value = (model, [path])

                with patch("logs_page.Gtk.MessageDialog") as mock_dialog_cls:
                    mock_dialog = MagicMock()
                    mock_dialog.run.return_value = lp.Gtk.ResponseType.YES
                    mock_dialog_cls.return_value = mock_dialog
                    with patch("logs_page._sync_log_list"):
                        lp._on_delete_selected(app)

                import log_index as li
                index = li.LogIndex.load()
                self.assertIsNone(index.get(path))


class TestCreateLogsPage(unittest.TestCase):
    """Tests for create_logs_page layout."""

    @patch("logs_page._sync_log_list")
    @patch("logs_page._update_success_rate_label")
    def test_log_viewer_frame_uses_bold_label(self, _mock_update, _mock_sync):
        app = MagicMock()
        app.config = {}
        app._ui_state.bind_treeview = MagicMock()

        frame = MagicMock()
        lp.Gtk.Frame.side_effect = [frame]

        lp.create_logs_page(app)

        frame.set_label.assert_not_called()
        frame.set_label_widget.assert_called_once()

    @patch("logs_page._sync_log_list")
    @patch("logs_page._update_success_rate_label")
    def test_column_headers_use_label_tooltips(self, _mock_update, _mock_sync):
        """TreeViewColumn tooltips must live on the header label widget."""
        app = MagicMock()
        app.config = {}
        app._ui_state.bind_treeview = MagicMock()

        # Isolate this test from any earlier Gtk mock calls.
        lp.Gtk.TreeViewColumn.reset_mock()
        lp.Gtk.TreeViewColumn.return_value.reset_mock()

        labels_by_text = {}

        def fake_label(*args, **kwargs):
            lbl = MagicMock()
            lbl._text = kwargs.get("label") or (args[0] if args else None)
            labels_by_text[lbl._text] = lbl
            return lbl

        lp.Gtk.Label.side_effect = fake_label

        lp.create_logs_page(app)

        expected = {
            "Date/Time": "Session log timestamp",
            "Type": "Log type: backup, offsite, restore, prune, or gui",
            "Name": "Name of the operation or profile",
            "Status": "Completion status",
            "Log Size": "Size of the log file on disk",
            "Duration": "Elapsed run time",
            "Transfer": "Bytes transferred during the operation",
        }

        # Only the column header labels are passed to TreeViewColumn.set_widget().
        set_widgets = [
            call[0][0]
            for call in lp.Gtk.TreeViewColumn.return_value.set_widget.call_args_list
        ]
        self.assertEqual(len(set_widgets), len(expected))

        for widget in set_widgets:
            text = widget._text
            self.assertIn(text, expected)
            widget.set_tooltip_text.assert_called_once_with(expected[text])
            widget.show_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()
