"""Tests for pool_watch.py — per-pool dataset watch window."""

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
    import pool_watch
    from pool_watch import PoolWatchWindow


class TestPoolWatchWindow(unittest.TestCase):
    """PoolWatchWindow lifecycle and refresh behavior."""

    def _make_parent(self):
        parent = MagicMock()
        parent.ctx.zfs_repository = MagicMock()
        parent._watch_windows = {}
        return parent

    def test_init_builds_ui_and_starts_timer(self):
        parent = self._make_parent()
        with patch.object(PoolWatchWindow, "refresh") as mock_refresh, \
             patch.object(PoolWatchWindow, "_start_timer") as mock_start:
            win = PoolWatchWindow("tank", parent)
        self.assertEqual(win.pool_name, "tank")
        self.assertIs(win.parent_window, parent)
        self.assertTrue(hasattr(win, "store"))
        self.assertTrue(hasattr(win, "view"))
        mock_refresh.assert_called_once()
        mock_start.assert_called_once()

    def test_refresh_clears_and_seeds_store(self):
        parent = self._make_parent()
        with patch.object(PoolWatchWindow, "_start_timer"), \
             patch.object(PoolWatchWindow, "refresh") as mock_refresh:
            win = PoolWatchWindow("tank", parent)

        # Replace mocked store with a fake to inspect behavior
        store = MagicMock()
        store.append.return_value = MagicMock()
        win.store = store
        win.scrolled = MagicMock()
        win.summary_label = MagicMock()
        win.view = MagicMock()

        # Call real refresh, bypassing expansion helpers that need a real store
        with patch.object(pool_watch, "get_expanded_rows", return_value=set()), \
             patch.object(pool_watch, "restore_expanded_rows"):
            PoolWatchWindow.refresh(win)

        store.clear.assert_called_once()
        self.assertEqual(store.append.call_count, 2)  # pool node + dummy child
        win.summary_label.set_text.assert_called_once_with("")

    def test_start_stop_timer(self):
        parent = self._make_parent()
        with patch.object(PoolWatchWindow, "refresh"), \
             patch.object(PoolWatchWindow, "_start_timer"):
            win = PoolWatchWindow("tank", parent)

        timer_id = 42
        with patch.object(pool_watch.GLib, "timeout_add_seconds", return_value=timer_id) as mock_add:
            PoolWatchWindow._start_timer(win)
        self.assertEqual(win.timer_id, timer_id)
        mock_add.assert_called_once_with(30, win._timer_tick)

        with patch.object(pool_watch.GLib, "source_remove") as mock_remove:
            PoolWatchWindow._stop_timer(win)
        self.assertIsNone(win.timer_id)
        mock_remove.assert_called_once_with(timer_id)

    def test_timer_tick_refreshes(self):
        parent = self._make_parent()
        with patch.object(PoolWatchWindow, "refresh") as mock_refresh, \
             patch.object(PoolWatchWindow, "_start_timer"), \
             patch.object(pool_watch, "get_expanded_rows", return_value=set()), \
             patch.object(pool_watch, "restore_expanded_rows"):
            win = PoolWatchWindow("tank", parent)
            self.assertEqual(mock_refresh.call_count, 1)  # from __init__
            result = win._timer_tick()
        self.assertTrue(result)
        self.assertEqual(mock_refresh.call_count, 2)

    def test_on_destroy_stops_timer_and_untracks(self):
        parent = self._make_parent()
        with patch.object(PoolWatchWindow, "refresh"), \
             patch.object(PoolWatchWindow, "_start_timer"):
            win = PoolWatchWindow("tank", parent)
        parent._watch_windows["tank"] = win
        win.timer_id = 7

        with patch.object(PoolWatchWindow, "_stop_timer") as mock_stop:
            win._on_destroy(None)

        mock_stop.assert_called_once()
        self.assertNotIn("tank", parent._watch_windows)

    def test_expand_all_and_collapse_all(self):
        parent = self._make_parent()
        with patch.object(PoolWatchWindow, "refresh"), \
             patch.object(PoolWatchWindow, "_start_timer"):
            win = PoolWatchWindow("tank", parent)
        win.view = MagicMock()
        win._on_expand_all(None)
        win.view.expand_all.assert_called_once()
        win._on_collapse_all(None)
        win.view.collapse_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()
