"""Tests for pools_page.py — pool registry UI."""

import os
import sys
import unittest
from unittest.mock import ANY, MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk, temp_config_dir


def _import_pools_page():
    """Import pools_page under a fresh mocked GTK context.

    Other test suites may have imported pools_page under a different GTK mock,
    so we force a re-import here to guarantee the module's Gtk reference is
    the current mock.
    """
    sys.modules.pop("pools_page", None)
    with mock_gtk():
        import pools_page

        return pools_page


class TestRefreshPoolsPage(unittest.TestCase):
    """refresh_pools_page() populates the pool store including offsite flags."""

    def _make_app(self, known_pools, online_pools=None, errors_by_pool=None,
                  importable_names=None):
        app = MagicMock()
        app.config = {"pools": known_pools}
        app.known_pools = list(known_pools)
        app._pools_saved_state = list(known_pools)
        app.pool_store = MagicMock()
        app.pool_store.__iter__ = lambda _s: iter([])
        app.pool_view = MagicMock()
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (None, [])
        app.pool_summary_label = MagicMock()
        app.pools_dirty_label = MagicMock()
        app._ui_state = MagicMock()
        app.ctx = MagicMock()
        app.ctx.zfs_repository.list_pools_full.return_value = online_pools or []
        errors_by_pool = errors_by_pool or {}

        def _pool_status_errors(pool_name):
            return errors_by_pool.get(
                pool_name,
                {"has_errors": False, "errors_summary": "No known data errors"},
            )

        app.ctx.zfs_repository.pool_status_errors.side_effect = _pool_status_errors
        app._offsite_candidates = set()
        cache = MagicMock()
        cache.get.return_value = set(importable_names or [])
        app._importable_pool_cache = cache
        return app

    def test_registered_pool_shows_offsite_candidate_true(self):
        pp = _import_pools_page()
        app = self._make_app(
            [{"name": "z40tb", "offsite_candidate": True}],
            [
                {
                    "name": "z40tb",
                    "health": "ONLINE",
                    "size": "1T",
                    "alloc": "100G",
                    "free": "900G",
                    "freeing": "0",
                    "ckpoint": "-",
                    "frag": "5%",
                    "cap": "10%",
                }
            ],
        )
        captured = []
        app.pool_store.append = captured.append

        with patch.object(pp, "_update_pools_dirty_indicator"):
            pp.refresh_pools_page(app)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][pp.COL_NAME], "z40tb")
        self.assertTrue(captured[0][pp.COL_OFFSITE])

    def test_unregistered_pool_has_offsite_false(self):
        pp = _import_pools_page()
        app = self._make_app(
            [],
            [
                {
                    "name": "tank",
                    "health": "ONLINE",
                    "size": "1T",
                    "alloc": "100G",
                    "free": "900G",
                    "freeing": "0",
                    "ckpoint": "-",
                    "frag": "5%",
                    "cap": "10%",
                }
            ],
        )
        captured = []
        app.pool_store.append = captured.append

        with patch.object(pp, "_update_pools_dirty_indicator"):
            pp.refresh_pools_page(app)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][pp.COL_FLAG], "unregistered")
        self.assertFalse(captured[0][pp.COL_OFFSITE])

    def test_registered_pool_with_errors(self):
        pp = _import_pools_page()
        app = self._make_app(
            [{"name": "tank", "offsite_candidate": False}],
            [
                {
                    "name": "tank",
                    "health": "ONLINE",
                    "size": "1T",
                    "alloc": "100G",
                    "free": "900G",
                    "freeing": "0",
                    "ckpoint": "-",
                    "frag": "5%",
                    "cap": "10%",
                }
            ],
            errors_by_pool={
                "tank": {
                    "has_errors": True,
                    "errors_summary": "vdev errors: sda (cksum=5)",
                },
            },
        )
        captured = []
        app.pool_store.append = captured.append

        with patch.object(pp, "_update_pools_dirty_indicator"):
            pp.refresh_pools_page(app)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][pp.COL_ERRORS], "vdev errors: sda (cksum=5)")

    def test_offline_pool_shows_no_errors_dash(self):
        pp = _import_pools_page()
        app = self._make_app(
            [{"name": "tank", "offsite_candidate": False}],
            [],
        )
        captured = []
        app.pool_store.append = captured.append

        with patch.object(pp, "_update_pools_dirty_indicator"):
            pp.refresh_pools_page(app)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][pp.COL_HEALTH], "OFFLINE")
        self.assertEqual(captured[0][pp.COL_ERRORS], "—")

    def test_importable_registered_pool_shows_importable_health(self):
        pp = _import_pools_page()
        app = self._make_app(
            [{"name": "tank", "offsite_candidate": False}],
            [],
            importable_names=["tank"],
        )
        captured = []
        app.pool_store.append = captured.append

        with patch.object(pp, "_update_pools_dirty_indicator"):
            pp.refresh_pools_page(app)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][pp.COL_HEALTH], "IMPORTABLE")
        self.assertEqual(captured[0][pp.COL_FLAG], pp.FLAG_REGISTERED)

    def test_unregistered_importable_pool_appears_in_store(self):
        pp = _import_pools_page()
        app = self._make_app(
            [],
            [],
            importable_names=["foreign"],
        )
        captured = []
        app.pool_store.append = captured.append

        with patch.object(pp, "_update_pools_dirty_indicator"):
            pp.refresh_pools_page(app)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][pp.COL_NAME], "foreign")
        self.assertEqual(captured[0][pp.COL_HEALTH], "IMPORTABLE")
        self.assertEqual(captured[0][pp.COL_FLAG], pp.FLAG_UNREGISTERED)

    def test_summary_counts_importable_pools(self):
        pp = _import_pools_page()
        app = self._make_app(
            [
                {"name": "online", "offsite_candidate": False},
                {"name": "offline", "offsite_candidate": False},
                {"name": "importable", "offsite_candidate": False},
            ],
            [
                {
                    "name": "online",
                    "health": "ONLINE",
                    "size": "1T",
                    "alloc": "100G",
                    "free": "900G",
                    "freeing": "0",
                    "ckpoint": "-",
                    "frag": "5%",
                    "cap": "10%",
                }
            ],
            importable_names=["importable", "foreign"],
        )
        with patch.object(pp, "_update_pools_dirty_indicator"):
            pp.refresh_pools_page(app)

        text = app.pool_summary_label.set_text.call_args[0][0]
        self.assertIn("3 registered pools: 1 online, 1 offline, 1 importable", text)
        self.assertIn("1 unregistered importable", text)


class TestOnPoolsRefresh(unittest.TestCase):
    """on_pools_refresh() invalidates the importable cache and redraws."""

    def test_invalidates_cache_and_refreshes(self):
        pp = _import_pools_page()
        app = MagicMock()
        cache = MagicMock()
        app._importable_pool_cache = cache

        with patch.object(pp, "refresh_pools_page") as mock_refresh:
            pp.on_pools_refresh(app)

        cache.invalidate.assert_called_once_with()
        mock_refresh.assert_called_once_with(app)

    def test_missing_cache_still_refreshes(self):
        pp = _import_pools_page()
        app = MagicMock()
        app._importable_pool_cache = None

        with patch.object(pp, "refresh_pools_page") as mock_refresh:
            pp.on_pools_refresh(app)

        mock_refresh.assert_called_once_with(app)


class TestErrorsSummaryForPool(unittest.TestCase):
    """_errors_summary_for_pool() translates repository output to labels."""

    def test_no_errors(self):
        pp = _import_pools_page()
        app = MagicMock()
        app.ctx.zfs_repository.pool_status_errors.return_value = {
            "has_errors": False,
            "errors_summary": "No known data errors",
        }
        self.assertEqual(pp._errors_summary_for_pool("tank", app), "No errors")

    def test_has_errors(self):
        pp = _import_pools_page()
        app = MagicMock()
        app.ctx.zfs_repository.pool_status_errors.return_value = {
            "has_errors": True,
            "errors_summary": "vdev errors: sda (cksum=5)",
        }
        self.assertEqual(
            pp._errors_summary_for_pool("tank", app),
            "vdev errors: sda (cksum=5)",
        )

    def test_missing_summary_falls_back(self):
        pp = _import_pools_page()
        app = MagicMock()
        app.ctx.zfs_repository.pool_status_errors.return_value = {
            "has_errors": True,
        }
        self.assertEqual(pp._errors_summary_for_pool("tank", app), "unknown error")

    def test_subprocess_error_returns_dash(self):
        pp = _import_pools_page()
        app = MagicMock()
        app.ctx.zfs_repository.pool_status_errors.side_effect = FileNotFoundError
        self.assertEqual(pp._errors_summary_for_pool("tank", app), "—")


class TestPoolErrorsCellFunc(unittest.TestCase):
    """_pool_errors_cell_func() colors the Errors column correctly."""

    def _call(self, errors_summary):
        pp = _import_pools_page()
        renderer = MagicMock()
        model = MagicMock()
        model.get_value.return_value = errors_summary
        pp._pool_errors_cell_func(None, renderer, model, None)
        return pp, renderer

    def test_no_errors_is_green_and_normal(self):
        pp, renderer = self._call("No errors")
        renderer.set_property.assert_any_call("foreground", "#4CAF50")
        renderer.set_property.assert_any_call("weight", pp.Pango.Weight.NORMAL)

    def test_errors_is_red_and_bold(self):
        pp, renderer = self._call("vdev errors: sda (cksum=5)")
        renderer.set_property.assert_any_call("foreground", "#F44336")
        renderer.set_property.assert_any_call("weight", pp.Pango.Weight.BOLD)

    def test_unavailable_is_default_and_normal(self):
        for value in (None, "", "—"):
            with self.subTest(value=value):
                pp, renderer = self._call(value)
                renderer.set_property.assert_any_call("foreground", None)
                renderer.set_property.assert_any_call("weight", pp.Pango.Weight.NORMAL)


class TestPoolHealthCellFunc(unittest.TestCase):
    """_pool_health_cell_func() colors the Health column correctly."""

    def _call(self, health):
        pp = _import_pools_page()
        renderer = MagicMock()
        model = MagicMock()
        model.get_value.return_value = health
        pp._pool_health_cell_func(None, renderer, model, None)
        return pp, renderer

    def test_importable_is_blue_and_bold(self):
        _pp, renderer = self._call("IMPORTABLE")
        renderer.set_property.assert_any_call("foreground", "#2196F3")
        renderer.set_property.assert_any_call("weight", ANY)


class TestOffsiteToggle(unittest.TestCase):
    """Toggling the Offsite checkbox updates the pool registry."""

    def _make_app(self):
        app = MagicMock()
        app.known_pools = [
            {"name": "tank", "offsite_candidate": False},
            {"name": "z40tb", "offsite_candidate": False},
        ]
        app._pools_saved_state = [
            {"name": "tank", "offsite_candidate": False},
            {"name": "z40tb", "offsite_candidate": False},
        ]
        app.pools_dirty = False
        app.pools_dirty_label = MagicMock()
        return app

    def test_toggle_true_updates_known_pools(self):
        pp = _import_pools_page()
        app = self._make_app()
        app.pool_store = MagicMock()
        app.pool_store.get_iter.return_value = True
        app.pool_store.get_value.side_effect = lambda _it, col: [
            "tank",
            "ONLINE",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "registered",
            False,
        ][col]

        with patch.object(pp, "_update_pools_dirty_indicator") as mock_dirty:
            pp._on_offsite_toggled(None, "0", app)

        self.assertTrue(app.known_pools[0]["offsite_candidate"])
        self.assertFalse(app.known_pools[1]["offsite_candidate"])
        mock_dirty.assert_called_once_with(app)
        app.pool_store.set_value.assert_called_once_with(True, pp.COL_OFFSITE, True)

    def test_toggle_unregistered_row_is_ignored(self):
        pp = _import_pools_page()
        app = self._make_app()
        app.pool_store = MagicMock()
        app.pool_store.get_iter.return_value = True
        app.pool_store.get_value.side_effect = lambda _it, col: [
            "tank",
            "ONLINE",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "unregistered",
            False,
        ][col]

        with patch.object(pp, "_update_pools_dirty_indicator") as mock_dirty:
            pp._on_offsite_toggled(None, "0", app)

        self.assertFalse(app.known_pools[0]["offsite_candidate"])
        mock_dirty.assert_not_called()


class TestDragEndPreservesFlags(unittest.TestCase):
    """DND reorder preserves offsite_candidate flags and selection."""

    def _make_drag_app(self, pp, known_pools, reversed_order):
        app = MagicMock()
        app.known_pools = list(known_pools)
        app.pool_view = MagicMock()
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (
            app.pool_view.get_model.return_value,
            [],
        )

        row_iter = iter(reversed_order)
        model = app.pool_view.get_model.return_value

        def get_iter_first():
            try:
                return next(row_iter)
            except StopIteration:
                return None

        def iter_next(_it):
            try:
                return next(row_iter)
            except StopIteration:
                return None

        def get_value(it, col):
            if col == pp.COL_NAME:
                return it["name"]
            if col == pp.COL_FLAG:
                return it["flag"]
            return None

        model.get_iter_first.side_effect = get_iter_first
        model.iter_next.side_effect = iter_next
        model.get_value.side_effect = get_value
        model.get_iter.return_value = None
        return app

    def test_reorder_keeps_flags(self):
        pp = _import_pools_page()
        app = self._make_drag_app(
            pp,
            [
                {"name": "tank", "offsite_candidate": True},
                {"name": "z40tb", "offsite_candidate": False},
            ],
            [
                {"name": "z40tb", "flag": "registered"},
                {"name": "tank", "flag": "registered"},
            ],
        )

        with patch.object(pp, "refresh_pools_page"):
            pp._on_pools_drag_end(app.pool_view, None, app)

        self.assertEqual([p["name"] for p in app.known_pools], ["z40tb", "tank"])
        self.assertEqual(app.known_pools[0]["offsite_candidate"], False)
        self.assertEqual(app.known_pools[1]["offsite_candidate"], True)

    def test_reorder_preserves_multiple_selections(self):
        pp = _import_pools_page()
        app = self._make_drag_app(
            pp,
            [
                {"name": "tank", "offsite_candidate": True},
                {"name": "z40tb", "offsite_candidate": False},
            ],
            [
                {"name": "z40tb", "flag": "registered"},
                {"name": "tank", "flag": "registered"},
            ],
        )
        model = app.pool_view.get_model.return_value
        path_a = MagicMock()
        path_b = MagicMock()
        iter_a = {"name": "tank", "flag": "registered"}
        iter_b = {"name": "z40tb", "flag": "registered"}

        def get_iter(path):
            if path is path_a:
                return iter_a
            if path is path_b:
                return iter_b
            return None

        model.get_iter.side_effect = get_iter
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (
            model,
            [path_a, path_b],
        )

        with (
            patch.object(pp, "refresh_pools_page"),
            patch.object(pp, "_select_pool_by_name") as mock_select,
        ):
            pp._on_pools_drag_end(app.pool_view, None, app)

        mock_select.assert_any_call(app.pool_view, "tank")
        mock_select.assert_any_call(app.pool_view, "z40tb")
        self.assertEqual(mock_select.call_count, 2)


class TestScrubTogglesUsePoolNames(unittest.TestCase):
    """Scrub toggles pass plain names to sync_system_scrub_for_pools."""

    def _make_app(self):
        app = MagicMock()
        app.config = {
            "pools": [
                {"name": "tank", "offsite_candidate": False},
                {"name": "archive", "offsite_candidate": True},
            ],
            "scrub_manager": {
                "system_scrub_weekly": False,
                "system_scrub_monthly": False,
            },
        }
        return app

    def test_weekly_toggle_uses_names(self):
        with temp_config_dir():
            pp = _import_pools_page()
            app = self._make_app()
            check = MagicMock()
            check.get_active.return_value = True

            with patch.object(pp, "sync_system_scrub_for_pools") as mock_sync:
                pp._on_scrub_weekly_toggled(check, app)

            mock_sync.assert_called_once()
            args = mock_sync.call_args[0]
            self.assertEqual(args[0], ["tank", "archive"])
            self.assertTrue(args[1])  # weekly
            self.assertFalse(args[2])  # monthly

    def test_monthly_toggle_uses_names(self):
        with temp_config_dir():
            pp = _import_pools_page()
            app = self._make_app()
            check = MagicMock()
            check.get_active.return_value = True

            with patch.object(pp, "sync_system_scrub_for_pools") as mock_sync:
                pp._on_scrub_monthly_toggled(check, app)

            mock_sync.assert_called_once()
            args = mock_sync.call_args[0]
            self.assertEqual(args[0], ["tank", "archive"])
            self.assertFalse(args[1])  # weekly
            self.assertTrue(args[2])  # monthly


class TestPoolsPageLayout(unittest.TestCase):
    """create_pools_page() wires widgets and UI state correctly."""

    def _make_app(self):
        app = MagicMock()
        app.config = {}
        app._ui_state = MagicMock()
        app.ctx.zfs_repository.list_pools_full.return_value = []
        return app

    def test_paned_is_bound_to_ui_state(self):
        pp = _import_pools_page()
        with patch.object(pp, "refresh_pools_page", MagicMock()):
            with patch.object(pp, "ScrubQueue", MagicMock()):
                app = self._make_app()
                pp.create_pools_page(app)

        app._ui_state.bind_paned.assert_called_once()
        args = app._ui_state.bind_paned.call_args[0]
        self.assertEqual(args[1], "pools_paned")

    def test_paned_bottom_pane_is_resizable(self):
        pp = _import_pools_page()
        paned_mock = MagicMock()
        with mock_gtk(), patch.object(pp.Gtk, "Paned", return_value=paned_mock):
            with patch.object(pp, "refresh_pools_page", MagicMock()):
                with patch.object(pp, "ScrubQueue", MagicMock()):
                    app = self._make_app()
                    pp.create_pools_page(app)

        paned_mock.pack2.assert_called_with(ANY, True, False)


class TestPoolsDirtyState(unittest.TestCase):
    """Dirty state reflects dict-pool inequality including offsite_candidate."""

    def test_toggle_offsite_marks_dirty(self):
        pp = _import_pools_page()
        app = MagicMock()
        app.known_pools = [
            {"name": "tank", "offsite_candidate": False},
        ]
        app._pools_saved_state = [
            {"name": "tank", "offsite_candidate": False},
        ]
        app.pool_store = MagicMock()
        app.pool_store.get_iter.return_value = True
        app.pool_store.get_value.side_effect = lambda _it, col: [
            "tank",
            "ONLINE",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "registered",
            False,
        ][col]

        with patch.object(pp, "_update_pools_dirty_indicator") as mock_dirty:
            pp._on_offsite_toggled(None, "0", app)

        self.assertTrue(app.known_pools[0]["offsite_candidate"])
        mock_dirty.assert_called_once_with(app)


class TestUpdatePoolsButtonSensitivity(unittest.TestCase):
    """update_pools_button_sensitivity() enables only appropriate buttons."""

    _BUTTON_ATTRS = (
        "_pools_watch_btn",
        "_pools_details_btn",
        "_pools_add_btn",
        "_pools_remove_btn",
        "_pools_import_btn",
        "_pools_export_btn",
        "_pools_save_btn",
        "_pools_revert_btn",
        "_pools_refresh_btn",
        "_scrub_start_btn",
        "_scrub_pause_btn",
        "_scrub_resume_btn",
        "_scrub_stop_btn",
        "_pools_add_profile_btn",
    )

    def _make_app(self, pool_rows=None, scrub_states=None, dirty=False):
        """Return app with mocked buttons and selections.

        pool_rows: list of (name, flag, health)
        scrub_states: list of displayed status strings for selected scrub rows
        """
        pp = _import_pools_page()
        app = MagicMock()
        app.known_pools = [{"name": "tank", "offsite_candidate": False}]
        app.pools_dirty = dirty

        for attr in self._BUTTON_ATTRS:
            setattr(app, attr, MagicMock())

        app.pool_view = self._make_treeview(
            pool_rows or [],
            [
                pp.COL_NAME,
                pp.COL_FLAG,
                pp.COL_HEALTH,
            ],
        )
        app.scrub_view = self._make_treeview([[state] for state in (scrub_states or [])], [1])
        return app

    def _make_treeview(self, rows, col_indices):
        """Build a mock TreeView whose selection returns the given rows."""
        treeview = MagicMock()
        model = MagicMock()
        paths = []

        def get_iter(path):
            for candidate, p in zip(rows, paths):
                if p is path:
                    return candidate
            return None

        def get_value(it, col):
            idx = col_indices.index(col)
            return it[idx]

        model.get_iter.side_effect = get_iter
        model.get_value.side_effect = get_value

        for _row in rows:
            path = MagicMock()
            paths.append(path)

        treeview.get_selection.return_value.get_selected_rows.return_value = (model, paths)
        return treeview

    def _sensitivities(self, app):
        """Return dict of attr -> last set_sensitive value."""
        result = {}
        for attr in self._BUTTON_ATTRS:
            btn = getattr(app, attr)
            calls = btn.set_sensitive.call_args_list
            result[attr] = calls[-1][0][0] if calls else None
        return result

    def test_no_selection_disables_action_buttons(self):
        pp = _import_pools_page()
        app = self._make_app()
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertFalse(sens["_pools_watch_btn"])
        self.assertFalse(sens["_pools_details_btn"])
        self.assertTrue(sens["_pools_add_btn"])
        self.assertFalse(sens["_pools_remove_btn"])
        self.assertTrue(sens["_pools_import_btn"])
        self.assertFalse(sens["_pools_export_btn"])
        self.assertFalse(sens["_pools_save_btn"])
        self.assertFalse(sens["_pools_revert_btn"])
        self.assertTrue(sens["_pools_refresh_btn"])
        self.assertFalse(sens["_scrub_start_btn"])
        self.assertFalse(sens["_scrub_pause_btn"])
        self.assertFalse(sens["_scrub_resume_btn"])
        self.assertFalse(sens["_scrub_stop_btn"])
        self.assertTrue(sens["_pools_add_profile_btn"])

    def test_registered_online_pool_enables_watch_details_remove_export(self):
        pp = _import_pools_page()
        app = self._make_app(pool_rows=[("tank", pp.FLAG_REGISTERED, "ONLINE")])
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertTrue(sens["_pools_watch_btn"])
        self.assertTrue(sens["_pools_details_btn"])
        self.assertTrue(sens["_pools_remove_btn"])
        self.assertTrue(sens["_pools_export_btn"])

    def test_unregistered_pool_enables_export_but_not_watch_remove(self):
        pp = _import_pools_page()
        app = self._make_app(pool_rows=[("tank", pp.FLAG_UNREGISTERED, "ONLINE")])
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertFalse(sens["_pools_watch_btn"])
        self.assertTrue(sens["_pools_details_btn"])
        self.assertFalse(sens["_pools_remove_btn"])
        self.assertTrue(sens["_pools_export_btn"])

    def test_offline_pool_disables_watch_and_export(self):
        pp = _import_pools_page()
        app = self._make_app(pool_rows=[("tank", pp.FLAG_REGISTERED, "OFFLINE")])
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertFalse(sens["_pools_watch_btn"])
        self.assertTrue(sens["_pools_details_btn"])
        self.assertTrue(sens["_pools_remove_btn"])
        self.assertFalse(sens["_pools_export_btn"])

    def test_importable_pool_disables_watch_and_export(self):
        pp = _import_pools_page()
        app = self._make_app(pool_rows=[("tank", pp.FLAG_REGISTERED, "IMPORTABLE")])
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertFalse(sens["_pools_watch_btn"])
        self.assertTrue(sens["_pools_details_btn"])
        self.assertTrue(sens["_pools_remove_btn"])
        self.assertFalse(sens["_pools_export_btn"])

    def test_multiple_selection_disables_details(self):
        pp = _import_pools_page()
        app = self._make_app(
            pool_rows=[
                ("tank", pp.FLAG_REGISTERED, "ONLINE"),
                ("archive", pp.FLAG_REGISTERED, "ONLINE"),
            ]
        )
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertFalse(sens["_pools_details_btn"])
        self.assertTrue(sens["_pools_watch_btn"])
        self.assertTrue(sens["_pools_remove_btn"])

    def test_dirty_state_enables_save_and_revert(self):
        pp = _import_pools_page()
        app = self._make_app(dirty=True)
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertTrue(sens["_pools_save_btn"])
        self.assertTrue(sens["_pools_revert_btn"])

    def test_scrub_state_controls_scrub_buttons(self):
        pp = _import_pools_page()
        app = self._make_app(scrub_states=["scrubbing", "pending"])
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertFalse(sens["_scrub_start_btn"])
        self.assertTrue(sens["_scrub_pause_btn"])
        self.assertFalse(sens["_scrub_resume_btn"])
        self.assertTrue(sens["_scrub_stop_btn"])

    def test_single_scrubbing_selection_disables_start(self):
        pp = _import_pools_page()
        app = self._make_app(scrub_states=["scrubbing"])
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertFalse(sens["_scrub_start_btn"])
        self.assertTrue(sens["_scrub_pause_btn"])
        self.assertFalse(sens["_scrub_resume_btn"])
        self.assertTrue(sens["_scrub_stop_btn"])

    def test_paused_scrub_enables_resume(self):
        pp = _import_pools_page()
        app = self._make_app(scrub_states=["paused"])
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertTrue(sens["_scrub_start_btn"])
        self.assertFalse(sens["_scrub_pause_btn"])
        self.assertTrue(sens["_scrub_resume_btn"])
        self.assertTrue(sens["_scrub_stop_btn"])

    def test_finished_scrub_disables_pause_resume_stop(self):
        pp = _import_pools_page()
        app = self._make_app(scrub_states=["finished"])
        pp.update_pools_button_sensitivity(app)
        sens = self._sensitivities(app)

        self.assertTrue(sens["_scrub_start_btn"])
        self.assertFalse(sens["_scrub_pause_btn"])
        self.assertFalse(sens["_scrub_resume_btn"])
        self.assertFalse(sens["_scrub_stop_btn"])


class TestSelectionChangedHandlers(unittest.TestCase):
    """Selection-changed callbacks trigger sensitivity updates."""

    def test_pool_selection_changed_updates_sensitivity(self):
        pp = _import_pools_page()
        app = MagicMock()
        with patch.object(pp, "update_pools_button_sensitivity") as mock_update:
            pp._on_pool_selection_changed(MagicMock(), app)
        mock_update.assert_called_once_with(app)

    def test_scrub_selection_changed_updates_sensitivity(self):
        pp = _import_pools_page()
        app = MagicMock()
        with patch.object(pp, "update_pools_button_sensitivity") as mock_update:
            pp._on_scrub_selection_changed(MagicMock(), app)
        mock_update.assert_called_once_with(app)


class TestPoolContextMenu(unittest.TestCase):
    """Right-click context menu on the Pool Registry tree."""

    def _make_event(self, button, x=10, y=20):
        event = MagicMock()
        event.button = button
        event.x = x
        event.y = y
        return event

    def _make_treeview(self, path_selected=False, path_info=None):
        treeview = MagicMock()
        selection = MagicMock()
        selection.path_is_selected.return_value = path_selected
        treeview.get_selection.return_value = selection
        treeview.get_path_at_pos.return_value = path_info
        return treeview, selection

    def test_left_click_does_not_show_menu(self):
        pp = _import_pools_page()
        treeview, _selection = self._make_treeview()
        app = MagicMock()
        result = pp._on_pool_button_press(treeview, self._make_event(1), app)
        self.assertFalse(result)
        treeview.get_path_at_pos.assert_not_called()

    def test_right_click_without_row_does_not_show_menu(self):
        pp = _import_pools_page()
        treeview, _selection = self._make_treeview(path_info=None)
        app = MagicMock()
        result = pp._on_pool_button_press(treeview, self._make_event(3), app)
        self.assertFalse(result)

    def test_right_click_shows_send_details_menu(self):
        pp = _import_pools_page()
        path_info = (MagicMock(), None, 0, 0)
        treeview, selection = self._make_treeview(path_selected=False, path_info=path_info)
        app = MagicMock()

        with patch.object(pp, "append_treeview_copy_items") as mock_append:
            result = pp._on_pool_button_press(treeview, self._make_event(3), app)

        self.assertTrue(result)
        selection.unselect_all.assert_called_once()
        selection.select_path.assert_called_once_with(path_info[0])
        treeview.set_cursor.assert_called_once_with(path_info[0], None, False)
        pp.Gtk.Menu.assert_called_once()
        mock_append.assert_called_once_with(pp.Gtk.Menu.return_value, treeview, path_info, app=app)
        menu = pp.Gtk.Menu.return_value
        menu.append.assert_any_call(pp.Gtk.SeparatorMenuItem.return_value)
        pp.Gtk.MenuItem.assert_any_call(label="Send details to log")
        menu.show_all.assert_called_once()
        menu.popup_at_pointer.assert_called_once()


class TestSendPoolDetailsToLog(unittest.TestCase):
    """Pool Registry "Send details to log" handler."""

    def _make_app(self, names=None, props=None, error=None):
        app = MagicMock()
        names = names or []
        pathlist = [MagicMock() for _ in names]

        model = MagicMock()
        iters = [MagicMock() for _ in names]
        model.get_iter.side_effect = iters
        model.get_value.side_effect = lambda _it, _col: names[iters.index(_it)]

        selection = MagicMock()
        selection.get_selected_rows.return_value = (model, pathlist)
        app.pool_view.get_selection.return_value = selection

        repo = MagicMock()
        if error is not None:
            repo.get_all_pool_properties.side_effect = error
        else:
            repo.get_all_pool_properties.return_value = props or {}
        app.ctx.zfs_repository = repo
        return app

    def test_warns_when_no_selection(self):
        pp = _import_pools_page()
        app = self._make_app(names=[])
        with patch.object(pp, "log_msg") as mock_log:
            pp._send_pool_details_to_log(app)
        mock_log.assert_called_once_with("WARN: Select a pool to send details to log")

    def test_warns_on_multiple_selection(self):
        pp = _import_pools_page()
        app = self._make_app(names=["tank", "backup"])
        with patch.object(pp, "log_msg") as mock_log:
            pp._send_pool_details_to_log(app)
        mock_log.assert_called_once_with("WARN: Send details to log requires a single selection")

    def test_logs_pool_properties_line_by_line(self):
        pp = _import_pools_page()
        app = self._make_app(
            names=["tank"],
            props={"size": "10T", "capacity": "50%", "health": "ONLINE"},
        )
        with patch.object(pp, "log_msg") as mock_log:
            pp._send_pool_details_to_log(app)

        app.ctx.zfs_repository.get_all_pool_properties.assert_called_once_with("tank")
        logged = [call[0][0] for call in mock_log.call_args_list]
        self.assertIn("INFO: Details for tank (pool)", logged)
        self.assertIn("  capacity: 50%", logged)
        self.assertIn("  health: ONLINE", logged)
        self.assertIn("  size: 10T", logged)

    def test_handles_repository_error(self):
        pp = _import_pools_page()
        app = self._make_app(
            names=["tank"],
            error=FileNotFoundError("zpool not found"),
        )
        with patch.object(pp, "log_msg") as mock_log:
            pp._send_pool_details_to_log(app)

        logged = mock_log.call_args[0][0]
        self.assertIn("WARN: Error reading details for tank", logged)


if __name__ == "__main__":
    unittest.main()
