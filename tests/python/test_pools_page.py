"""Tests for pools_page.py — pool registry UI."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, ANY

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
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

    def _make_app(self, known_pools, online_pools=None, errors_by_pool=None):
        app = MagicMock()
        app.config = {"pools": known_pools}
        app.known_pools = list(known_pools)
        app._pools_saved_state = list(known_pools)
        app.pool_store = MagicMock()
        app.pool_store.__iter__ = lambda _s: iter([])
        app.pool_view = MagicMock()
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (
            None, []
        )
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
        return app

    def test_registered_pool_shows_offsite_candidate_true(self):
        pp = _import_pools_page()
        app = self._make_app(
            [{"name": "z40tb", "offsite_candidate": True}],
            [{"name": "z40tb", "health": "ONLINE", "size": "1T",
              "alloc": "100G", "free": "900G", "freeing": "0",
              "ckpoint": "-", "frag": "5%", "cap": "10%"}],
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
            [{"name": "tank", "health": "ONLINE", "size": "1T",
              "alloc": "100G", "free": "900G", "freeing": "0",
              "ckpoint": "-", "frag": "5%", "cap": "10%"}],
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
            [{"name": "tank", "health": "ONLINE", "size": "1T",
              "alloc": "100G", "free": "900G", "freeing": "0",
              "ckpoint": "-", "frag": "5%", "cap": "10%"}],
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
            "tank", "ONLINE", "-", "-", "-", "-", "-", "-", "-",
            "registered", False,
        ][col]

        with patch.object(pp, "_update_pools_dirty_indicator") as mock_dirty:
            pp._on_offsite_toggled(None, "0", app)

        self.assertTrue(app.known_pools[0]["offsite_candidate"])
        self.assertFalse(app.known_pools[1]["offsite_candidate"])
        mock_dirty.assert_called_once_with(app)
        app.pool_store.set_value.assert_called_once_with(
            True, pp.COL_OFFSITE, True
        )

    def test_toggle_unregistered_row_is_ignored(self):
        pp = _import_pools_page()
        app = self._make_app()
        app.pool_store = MagicMock()
        app.pool_store.get_iter.return_value = True
        app.pool_store.get_value.side_effect = lambda _it, col: [
            "tank", "ONLINE", "-", "-", "-", "-", "-", "-", "-",
            "unregistered", False,
        ][col]

        with patch.object(pp, "_update_pools_dirty_indicator") as mock_dirty:
            pp._on_offsite_toggled(None, "0", app)

        self.assertFalse(app.known_pools[0]["offsite_candidate"])
        mock_dirty.assert_not_called()


class TestDragEndPreservesFlags(unittest.TestCase):
    """DND reorder preserves offsite_candidate flags."""

    def test_reorder_keeps_flags(self):
        pp = _import_pools_page()
        app = MagicMock()
        app.known_pools = [
            {"name": "tank", "offsite_candidate": True},
            {"name": "z40tb", "offsite_candidate": False},
        ]
        app.pool_view = MagicMock()
        app.pool_view.get_selection.return_value.get_selected.return_value = (
            None, None
        )

        # Simulate rows in reversed order
        rows = [
            {"name": "z40tb", "flag": "registered"},
            {"name": "tank", "flag": "registered"},
        ]
        row_iter = iter(rows)

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

        with patch.object(pp, "refresh_pools_page"):
            pp._on_pools_drag_end(app.pool_view, None, app)

        self.assertEqual([p["name"] for p in app.known_pools], ["z40tb", "tank"])
        self.assertEqual(app.known_pools[0]["offsite_candidate"], False)
        self.assertEqual(app.known_pools[1]["offsite_candidate"], True)


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
        with mock_gtk():
            with patch.object(pp.Gtk, "Paned", return_value=paned_mock):
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
            "tank", "ONLINE", "-", "-", "-", "-", "-", "-", "-",
            "registered", False,
        ][col]

        with patch.object(pp, "_update_pools_dirty_indicator") as mock_dirty:
            pp._on_offsite_toggled(None, "0", app)

        self.assertTrue(app.known_pools[0]["offsite_candidate"])
        mock_dirty.assert_called_once_with(app)


if __name__ == "__main__":
    unittest.main()
