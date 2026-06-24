"""Tests for pool_actions.py — pool registry add/remove/save/revert."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk


def _import_pool_actions():
    """Import pool_actions under a fresh mocked GTK context."""
    sys.modules.pop("pool_actions", None)
    with mock_gtk():
        import pool_actions
        return pool_actions


def _make_app(known_pools=None):
    app = MagicMock()
    app.known_pools = list(known_pools or [])
    app._pools_saved_state = list(known_pools or [])
    app.config = {"pools": list(known_pools or [])}
    app.pools_dirty = False
    app.pool_view = MagicMock()
    app.pool_view.get_selection.return_value.get_selected.return_value = (None, None)
    app.pool_view.get_selection.return_value.get_selected_rows.return_value = (None, [])
    return app


def _make_add_dialog(pool_name):
    """Return a mock create_dialog that simulates entering pool_name."""
    dialog = MagicMock()
    dialog.return_value.run.return_value = 1  # ResponseType.OK
    entry = MagicMock()
    entry.get_text.return_value = pool_name
    content = MagicMock()
    dialog.return_value.get_content_area.return_value = content

    def fake_add(widget):
        """No-op; we rely on the patched Gtk.Entry returning our entry mock."""
        pass

    content.add.side_effect = fake_add
    return dialog


def _patch_entry(pa, pool_name):
    """Patch Gtk.Entry so the dialog returns pool_name."""
    entry_mock = MagicMock()
    entry_mock.get_text.return_value = pool_name
    pa.Gtk.Entry = MagicMock(return_value=entry_mock)


class TestOnPoolsAdd(unittest.TestCase):
    """on_pools_add appends dict pools and rejects duplicate names."""

    def test_adds_dict_with_offsite_candidate_false(self):
        pa = _import_pool_actions()
        app = _make_app([{"name": "tank", "offsite_candidate": False}])
        dialog_mock = _make_add_dialog("archive")

        with patch.object(pa, "create_dialog", dialog_mock), \
             patch.object(pa, "refresh_pools_page") as mock_refresh:
            _patch_entry(pa, "archive")
            pa.on_pools_add(app)

        self.assertEqual(len(app.known_pools), 2)
        self.assertEqual(app.known_pools[-1], {"name": "archive", "offsite_candidate": False})
        mock_refresh.assert_called_once_with(app)

    def test_rejects_duplicate_name(self):
        pa = _import_pool_actions()
        app = _make_app([{"name": "tank", "offsite_candidate": False}])
        dialog_mock = _make_add_dialog("tank")

        with patch.object(pa, "create_dialog", dialog_mock), \
             patch.object(pa, "refresh_pools_page") as mock_refresh, \
             patch.object(pa, "log_msg") as mock_log:
            _patch_entry(pa, "tank")
            pa.on_pools_add(app)

        self.assertEqual(len(app.known_pools), 1)
        mock_refresh.assert_not_called()
        mock_log.assert_called_once()
        self.assertIn("already in the registry", mock_log.call_args[0][0])

    def test_cancel_does_nothing(self):
        pa = _import_pool_actions()
        app = _make_app()
        dialog_mock = MagicMock()
        dialog_mock.return_value.run.return_value = -6  # ResponseType.CANCEL

        with patch.object(pa, "create_dialog", dialog_mock), \
             patch.object(pa, "refresh_pools_page") as mock_refresh:
            _patch_entry(pa, "tank")
            pa.on_pools_add(app)

        self.assertEqual(app.known_pools, [])
        mock_refresh.assert_not_called()


class TestOnPoolsRemove(unittest.TestCase):
    """on_pools_remove filters dict pools by name."""

    def _make_app_with_selection(self, pools, selected):
        app = _make_app(pools)
        model = MagicMock()
        paths = []
        for name, health in selected:
            path = MagicMock()
            paths.append(path)

        def get_iter(path):
            for (n, h), p in zip(selected, paths):
                if p is path:
                    it = MagicMock()
                    it.__eq__ = lambda self, other: True
                    return it
            return None

        model.get_iter.side_effect = get_iter
        model.get_value.side_effect = lambda it, col: {
            pa.COL_NAME: selected[paths.index(path) if False else 0][0],
            pa.COL_HEALTH: selected[paths.index(path) if False else 0][1],
        }.get(col)

        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (
            model, paths
        )
        app.pool_view.get_selection.return_value.get_selected.return_value = (
            model, None
        )
        return app, model, paths, selected

    def test_removes_selected_registered_pool(self):
        pa = _import_pool_actions()
        app = _make_app([
            {"name": "tank", "offsite_candidate": False},
            {"name": "archive", "offsite_candidate": True},
        ])
        model = MagicMock()
        path = MagicMock()
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (
            model, [path]
        )

        def get_iter(p):
            if p is path:
                it = MagicMock()
                return it
            return None

        model.get_iter.side_effect = get_iter
        call_count = {"n": 0}

        def get_value(it, col):
            call_count["n"] += 1
            if col == pa.COL_NAME:
                return "archive"
            if col == pa.COL_HEALTH:
                return "ONLINE"
            return None

        model.get_value.side_effect = get_value

        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        with patch.object(pa, "refresh_pools_page") as mock_refresh, \
             patch.object(pa, "log_msg"):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_remove(app)

        self.assertEqual([p["name"] for p in app.known_pools], ["tank"])
        mock_refresh.assert_called_once_with(app)

    def test_unregistered_selection_warns(self):
        pa = _import_pool_actions()
        app = _make_app([{"name": "tank", "offsite_candidate": False}])
        model = MagicMock()
        path = MagicMock()
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (
            model, [path]
        )

        it = MagicMock()
        model.get_iter.return_value = it
        model.get_value.side_effect = lambda _it, col: {
            pa.COL_NAME: "unknown",
            pa.COL_HEALTH: "ONLINE",
        }.get(col)

        with patch.object(pa, "refresh_pools_page") as mock_refresh, \
             patch.object(pa, "log_msg") as mock_log:
            pa.on_pools_remove(app)

        self.assertEqual(len(app.known_pools), 1)
        mock_refresh.assert_not_called()
        mock_log.assert_called_once()
        self.assertIn("Select at least one registered pool", mock_log.call_args[0][0])


class TestOnPoolsSave(unittest.TestCase):
    """on_pools_save persists dict pools and updates saved state."""

    def test_saves_dict_pools(self):
        pa = _import_pool_actions()
        app = _make_app([
            {"name": "tank", "offsite_candidate": False},
            {"name": "z40tb", "offsite_candidate": True},
        ])
        app.pools_dirty = True

        with patch.object(pa, "save_pools") as mock_save, \
             patch.object(pa, "_update_pools_dirty_indicator") as mock_dirty:
            pa.on_pools_save(app)

        mock_save.assert_called_once_with(app.config, app.known_pools)
        self.assertEqual(app._pools_saved_state, app.known_pools)
        mock_dirty.assert_called_once_with(app)

    def test_no_op_when_clean(self):
        pa = _import_pool_actions()
        app = _make_app()
        app.pools_dirty = False

        with patch.object(pa, "save_pools") as mock_save:
            pa.on_pools_save(app)

        mock_save.assert_not_called()


class TestOnPoolsRevert(unittest.TestCase):
    """on_pools_revert restores dict pools from saved state."""

    def test_restores_dict_list(self):
        pa = _import_pool_actions()
        original = [
            {"name": "tank", "offsite_candidate": False},
            {"name": "z40tb", "offsite_candidate": True},
        ]
        app = _make_app(original)
        app.known_pools.append({"name": "extra", "offsite_candidate": False})

        with patch.object(pa, "refresh_pools_page") as mock_refresh, \
             patch.object(pa, "log_msg"):
            pa.on_pools_revert(app)

        self.assertEqual(app.known_pools, original)
        mock_refresh.assert_called_once_with(app)


if __name__ == "__main__":
    unittest.main()
