"""Tests for datasets_page.py — Datasets tab UI."""

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
    import datasets_page as dp


class _FakePoolRow:
    def __init__(self, name):
        self.name = name


class _FakeStore:
    """Minimal TreeStore stand-in."""
    def __init__(self):
        self._rows = []
        self._counter = 0

    def clear(self):
        self._rows = []

    def append(self, parent, values):
        node = {"id": self._counter, "parent": parent, "values": list(values), "children": []}
        self._counter += 1
        self._rows.append(node)
        if parent is not None:
            parent["children"].append(node)
        return node

    def get_value(self, node, col):
        return node["values"][col]

    def get_iter_first(self):
        return self._rows[0] if self._rows else None

    def iter_next(self, node):
        return None

    def iter_children(self, node):
        return node["children"][0] if node["children"] else None

    def get_path(self, node):
        return node["id"]


class TestCreateDatasetsPage(unittest.TestCase):
    """create_datasets_page builds the page and stores app references."""

    def _make_app(self):
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        app.enable_treeview_copy = MagicMock()
        app._ui_state.bind_treeview = MagicMock()
        return app

    def test_creates_expected_widgets(self):
        app = self._make_app()
        with patch.object(dp, "refresh_datasets_page"):
            page = dp.create_datasets_page(app)

        self.assertIs(page, dp.Gtk.Box.return_value)
        self.assertTrue(hasattr(app, "datasets_store"))
        self.assertTrue(hasattr(app, "datasets_view"))
        self.assertTrue(hasattr(app, "datasets_search"))
        self.assertTrue(hasattr(app, "datasets_summary_label"))
        self.assertIs(app.datasets_scrolled, dp.Gtk.ScrolledWindow.return_value)
        app.enable_treeview_copy.assert_called_once_with(app.datasets_view)
        app._ui_state.bind_treeview.assert_called_once_with(app.datasets_view, "datasets_view")


class TestRefreshDatasetsPage(unittest.TestCase):
    """refresh_datasets_page loads online pools into the tree."""

    def _make_app(self):
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        app.ctx.zfs_repository.list_pools.return_value = [
            _FakePoolRow("tank"),
            _FakePoolRow("backup"),
        ]
        app.datasets_store = _FakeStore()
        app.datasets_view = MagicMock()
        app.datasets_view.get_selection.return_value.get_selected_rows.return_value = (None, [])
        app.datasets_search = MagicMock()
        app.datasets_search._text = ""
        app.datasets_summary_label = MagicMock()
        app.datasets_scrolled = MagicMock()
        app.datasets_scrolled.get_vadjustment.return_value.get_value.return_value = 0.0
        return app

    def test_loads_online_pools_and_summary(self):
        app = self._make_app()
        with patch.object(dp, "get_expanded_rows", return_value=set()), \
             patch.object(dp, "restore_expanded_rows"):
            dp.refresh_datasets_page(app)

        app.ctx.zfs_repository.list_pools.assert_called_once()
        self.assertEqual(len(app.datasets_store._rows), 4)  # 2 pools + 2 dummy children
        self.assertEqual(app.datasets_store._rows[0]["values"][0], "tank")
        self.assertEqual(app.datasets_store._rows[2]["values"][0], "backup")
        app.datasets_summary_label.set_text.assert_called_once_with("2 pools")

    def test_pool_filter_restricts_list(self):
        app = self._make_app()
        with patch.object(dp, "get_expanded_rows", return_value=set()), \
             patch.object(dp, "restore_expanded_rows"):
            dp.refresh_datasets_page(app, pool_filter="backup")

        self.assertEqual(len(app.datasets_store._rows), 2)  # backup + dummy child
        self.assertEqual(app.datasets_store._rows[0]["values"][0], "backup")
        app.datasets_summary_label.set_text.assert_called_once_with("1 pools")

    def test_handles_pool_list_error(self):
        app = self._make_app()
        app.ctx.zfs_repository.list_pools.side_effect = FileNotFoundError("zfs not found")
        with patch.object(dp, "get_expanded_rows", return_value=set()), \
             patch.object(dp, "restore_expanded_rows"):
            dp.refresh_datasets_page(app)

        self.assertEqual(len(app.datasets_store._rows), 0)
        app.datasets_summary_label.set_text.assert_not_called()

    def test_preserves_scroll_position(self):
        app = self._make_app()
        app.datasets_scrolled.get_vadjustment.return_value.get_value.return_value = 150.0
        with patch.object(dp, "get_expanded_rows", return_value=set()), \
             patch.object(dp, "restore_expanded_rows"), \
             patch.object(dp.GLib, "idle_add") as mock_idle:
            dp.refresh_datasets_page(app)

        app.datasets_scrolled.get_vadjustment.assert_called_once()
        mock_idle.assert_called_once()
        callback, scrolled, value = mock_idle.call_args[0]
        self.assertIs(scrolled, app.datasets_scrolled)
        self.assertEqual(value, 150.0)
        self.assertEqual(callback.__name__, "_restore_scroll")

    def test_no_scroll_restore_when_scrolled_missing(self):
        app = self._make_app()
        del app.datasets_scrolled
        with patch.object(dp, "get_expanded_rows", return_value=set()), \
             patch.object(dp, "restore_expanded_rows"), \
             patch.object(dp.GLib, "idle_add") as mock_idle:
            dp.refresh_datasets_page(app)

        mock_idle.assert_not_called()

    def test_restore_scroll_clamps_to_valid_range(self):
        scrolled = MagicMock()
        vadj = MagicMock()
        vadj.get_upper.return_value = 500.0
        vadj.get_page_size.return_value = 100.0
        scrolled.get_vadjustment.return_value = vadj
        dp._restore_scroll(scrolled, 450.0)
        vadj.set_value.assert_called_once_with(400.0)

    def test_restore_scroll_uses_exact_value_when_in_range(self):
        scrolled = MagicMock()
        vadj = MagicMock()
        vadj.get_upper.return_value = 500.0
        vadj.get_page_size.return_value = 100.0
        scrolled.get_vadjustment.return_value = vadj
        dp._restore_scroll(scrolled, 250.0)
        vadj.set_value.assert_called_once_with(250.0)

    def test_restore_scroll_returns_false_when_no_adjustment(self):
        scrolled = MagicMock()
        scrolled.get_vadjustment.return_value = None
        result = dp._restore_scroll(scrolled, 100.0)
        self.assertIs(result, False)
        scrolled.get_vadjustment.assert_called_once()

    def test_no_scroll_restore_when_adjustment_missing(self):
        app = self._make_app()
        app.datasets_scrolled.get_vadjustment.return_value = None
        with patch.object(dp, "get_expanded_rows", return_value=set()), \
             patch.object(dp, "restore_expanded_rows"), \
             patch.object(dp.GLib, "idle_add") as mock_idle:
            dp.refresh_datasets_page(app)
        mock_idle.assert_not_called()

    def test_restore_scroll_clamps_negative_to_zero(self):
        scrolled = MagicMock()
        vadj = MagicMock()
        vadj.get_upper.return_value = 500.0
        vadj.get_page_size.return_value = 100.0
        scrolled.get_vadjustment.return_value = vadj
        dp._restore_scroll(scrolled, -50.0)
        vadj.set_value.assert_called_once_with(0.0)

    def test_restore_scroll_zero_max_when_page_exceeds_upper(self):
        scrolled = MagicMock()
        vadj = MagicMock()
        vadj.get_upper.return_value = 50.0
        vadj.get_page_size.return_value = 100.0
        scrolled.get_vadjustment.return_value = vadj
        dp._restore_scroll(scrolled, 25.0)
        vadj.set_value.assert_called_once_with(0.0)


class TestUpdateButtonSensitivity(unittest.TestCase):
    """update_ds_button_sensitivity enables buttons based on selection."""

    def _make_app(self, items):
        app = MagicMock()
        app.datasets_view = MagicMock()
        with patch.object(dp, "get_tree_selection_items", return_value=items):
            dp.update_ds_button_sensitivity(app)
        return app

    def test_single_dataset_enables_snapshot(self):
        app = self._make_app([{"type": "dataset", "name": "tank/a", "zfs_type": "filesystem"}])
        app._ds_snapshot_btn.set_sensitive.assert_called_once_with(True)
        app._ds_delete_btn.set_sensitive.assert_called_once_with(True)
        app._ds_hold_btn.set_sensitive.assert_called_once_with(False)
        app._ds_rollback_btn.set_sensitive.assert_called_once_with(False)

    def test_single_snapshot_enables_rollback(self):
        app = self._make_app([{"type": "snapshot", "name": "snap", "dataset": "tank/a"}])
        app._ds_rollback_btn.set_sensitive.assert_called_once_with(True)

    def test_pool_disables_delete(self):
        app = self._make_app([{"type": "pool", "name": "tank"}])
        app._ds_delete_btn.set_sensitive.assert_called_once_with(False)

    def test_expand_selected_enabled_for_pool(self):
        app = self._make_app([{"type": "pool", "name": "tank"}])
        app._ds_expand_selected_btn.set_sensitive.assert_called_once_with(True)

    def test_expand_selected_enabled_for_dataset(self):
        app = self._make_app([{"type": "dataset", "name": "tank/a"}])
        app._ds_expand_selected_btn.set_sensitive.assert_called_once_with(True)

    def test_expand_selected_enabled_for_snapshot(self):
        app = self._make_app([{"type": "snapshot", "name": "snap", "dataset": "tank/a"}])
        app._ds_expand_selected_btn.set_sensitive.assert_called_once_with(True)

    def test_expand_selected_disabled_when_empty(self):
        app = self._make_app([])
        app._ds_expand_selected_btn.set_sensitive.assert_called_once_with(False)

    def test_expand_selected_disabled_for_hold_only(self):
        app = self._make_app([{"type": "hold", "tag": "x"}])
        app._ds_expand_selected_btn.set_sensitive.assert_called_once_with(False)


class TestExpandSelectedDatasets(unittest.TestCase):
    """expand_selected_datasets recursively expands selected tree rows."""

    def _make_app(self, rows):
        """Build an app mock with selected *rows* [(path, name, ds_type)]."""
        app = MagicMock()
        model = MagicMock()
        nodes = {}

        def _get_iter(path):
            return nodes.setdefault(path, MagicMock())

        model.get_iter.side_effect = _get_iter

        def _get_value(node, col):
            for path, name, ds_type in rows:
                if nodes.get(path) is node:
                    return name if col == 0 else ds_type
            return ""

        model.get_value.side_effect = _get_value
        paths = [r[0] for r in rows]
        app.datasets_view.get_selection.return_value.get_selected_rows.return_value = (
            model, paths
        )
        app.datasets_search = MagicMock()
        return app, model, nodes

    @patch.object(dp.Gtk, "events_pending", return_value=False)
    @patch.object(dp, "expand_tree_recursively")
    def test_expands_each_selected_row(self, mock_expand, _mock_events):
        app, model, nodes = self._make_app([
            ("0", "tank", ""),
            ("1", "backup", ""),
        ])
        dp.expand_selected_datasets(app)

        self.assertEqual(mock_expand.call_count, 2)
        mock_expand.assert_any_call(app.datasets_view, model, nodes["0"])
        mock_expand.assert_any_call(app.datasets_view, model, nodes["1"])
        app.datasets_search.freeze.assert_called_once()
        app.datasets_search.thaw.assert_called_once()
        app.datasets_search.handle_expand_collapse.assert_called_once()

    @patch.object(dp.Gtk, "events_pending", return_value=False)
    @patch.object(dp, "expand_tree_recursively")
    def test_skips_placeholders_and_holds(self, mock_expand, _mock_events):
        app, model, nodes = self._make_app([
            ("0", "(no holds)", ""),
            ("1", "holdtag", "hold"),
            ("2", "tank", ""),
        ])
        dp.expand_selected_datasets(app)

        mock_expand.assert_called_once_with(app.datasets_view, model, nodes["2"])

    @patch.object(dp.Gtk, "events_pending", return_value=False)
    @patch.object(dp, "expand_tree_recursively")
    def test_does_nothing_when_nothing_selected(self, mock_expand, _mock_events):
        app, _, _ = self._make_app([])
        dp.expand_selected_datasets(app)

        mock_expand.assert_not_called()
        app.datasets_search.freeze.assert_not_called()

    @patch.object(dp.Gtk, "MessageDialog")
    @patch.object(dp.Gtk, "events_pending", return_value=False)
    @patch.object(dp, "expand_tree_recursively")
    def test_no_dialog_when_all_selected_are_skipped(
        self, mock_expand, _mock_events, mock_dialog,
    ):
        app, _, _ = self._make_app([
            ("0", "(no datasets)", ""),
            ("1", "holdtag", "hold"),
        ])
        dp.expand_selected_datasets(app)

        mock_expand.assert_not_called()
        mock_dialog.assert_not_called()
        app.datasets_search.freeze.assert_not_called()

    @patch.object(dp.Gtk, "events_pending", return_value=False)
    @patch.object(dp, "expand_tree_recursively")
    def test_skips_stale_paths_that_raise_valueerror(self, mock_expand, _mock_events):
        app, model, nodes = self._make_app([
            ("0", "tank", ""),
            ("1", "backup", ""),
        ])

        def _get_iter(path):
            if path == "0":
                raise ValueError("stale path")
            return nodes.setdefault(path, MagicMock())

        model.get_iter.side_effect = _get_iter
        dp.expand_selected_datasets(app)

        mock_expand.assert_called_once_with(app.datasets_view, model, nodes["1"])


if __name__ == "__main__":
    unittest.main()


class TestRefreshDatasetsPageSearch(unittest.TestCase):
    """refresh_datasets_page re-runs an active search after repopulating."""

    def _make_app(self):
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        app.ctx.zfs_repository.list_pools.return_value = [
            _FakePoolRow("tank"),
        ]
        app.datasets_store = _FakeStore()
        app.datasets_view = MagicMock()
        app.datasets_view.get_selection.return_value.get_selected_rows.return_value = (None, [])
        app.datasets_search = MagicMock()
        app.datasets_search._text = ""
        app.datasets_summary_label = MagicMock()
        app.datasets_scrolled = MagicMock()
        app.datasets_scrolled.get_vadjustment.return_value.get_value.return_value = 0.0
        return app

    def test_refresh_reruns_active_search(self):
        app = self._make_app()
        app.datasets_search._text = "foo"
        with patch.object(dp, "get_expanded_rows", return_value=set()), \
             patch.object(dp, "restore_expanded_rows"):
            dp.refresh_datasets_page(app)
        app.datasets_search._run_search.assert_called_once()

    def test_refresh_skips_search_when_entry_empty(self):
        app = self._make_app()
        app.datasets_search._text = ""
        with patch.object(dp, "get_expanded_rows", return_value=set()), \
             patch.object(dp, "restore_expanded_rows"):
            dp.refresh_datasets_page(app)
        app.datasets_search._run_search.assert_not_called()
