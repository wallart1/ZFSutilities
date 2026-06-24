"""Tests for snapshot_manager.py — Snapshot Manager window."""

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
    import snapshot_manager
    from snapshot_manager import SnapshotManagerWindow


class _FakeSnapshotRow:
    """Minimal snapshot row stand-in."""
    def __init__(self, name, creation="2025-01-01", used="1G", refer="10G"):
        self.name = name
        self.creation = creation
        self.used = used
        self.refer = refer


class _FakeHoldRow:
    """Minimal hold row stand-in."""
    def __init__(self, tag, date="2025-01-01"):
        self.tag = tag
        self.date = date


class _FakeTreeStore:
    """Tiny fake TreeStore sufficient for _get_selected_items tests."""
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

    def iter_parent(self, node):
        return node["parent"]

    def get_path(self, node):
        return node["id"]

    def get_iter(self, path):
        for node in self._rows:
            if node["id"] == path:
                return node
        return None

    def iter_next(self, node):
        # Not needed for these tests
        return None


class TestSnapshotManagerInit(unittest.TestCase):
    """__init__ builds the UI and triggers snapshot loading."""

    def _make_parent(self):
        parent = MagicMock()
        parent.ctx.zfs_repository = MagicMock()
        return parent

    def test_builds_ui_and_stores_dataset(self):
        parent = self._make_parent()
        with patch.object(SnapshotManagerWindow, "refresh_snapshots") as mock_refresh:
            win = SnapshotManagerWindow("tank/data", parent)
        self.assertEqual(win.dataset, "tank/data")
        self.assertIs(win.parent_window, parent)
        self.assertTrue(hasattr(win, "snap_store"))
        self.assertTrue(hasattr(win, "snap_view"))
        mock_refresh.assert_called_once()


class TestRefreshSnapshots(unittest.TestCase):
    """refresh_snapshots loads snapshots and holds into the tree."""

    def _make_window(self, repo):
        parent = MagicMock()
        parent.ctx.zfs_repository = repo
        with patch.object(SnapshotManagerWindow, "refresh_snapshots"):
            win = SnapshotManagerWindow("tank/data", parent)
        return win

    def test_loads_snapshots_and_holds(self):
        repo = MagicMock()
        repo.list_snapshots.return_value = [
            _FakeSnapshotRow("tank/data@snap1"),
            _FakeSnapshotRow("tank/data@snap2"),
        ]
        repo.list_holds.side_effect = [
            [_FakeHoldRow("keep", "2025-01-01")],
            [],
        ]

        win = self._make_window(repo)
        win.refresh_snapshots()

        repo.list_snapshots.assert_called_once_with("tank/data", depth=1, sort_creation=True)
        self.assertEqual(win.snap_summary.set_text.call_args[0][0], "2 snapshots")

    def test_handles_list_snapshots_error(self):
        repo = MagicMock()
        repo.list_snapshots.side_effect = FileNotFoundError("zfs not found")

        win = self._make_window(repo)
        with patch.object(win, "set_status") as mock_status:
            win.refresh_snapshots()

        mock_status.assert_called_once()
        self.assertIn("zfs not found", mock_status.call_args[0][0])


class TestGetSelectedItems(unittest.TestCase):
    """_get_selected_items parses snapshot vs hold selections."""

    def _make_window(self):
        parent = MagicMock()
        parent.ctx.zfs_repository = MagicMock()
        with patch.object(SnapshotManagerWindow, "refresh_snapshots"):
            win = SnapshotManagerWindow("tank/data", parent)
        return win

    def test_distinguishes_snapshots_and_holds(self):
        win = self._make_window()
        store = _FakeTreeStore()
        win.snap_store = store

        # Build tree: snap1 with hold, snap2 without
        snap1 = store.append(None, ["snap1", "2025-01-01", "1G", "10G", "1"])
        hold1 = store.append(snap1, ["keep", "2025-01-01", "", "", ""])
        snap2 = store.append(None, ["snap2", "2025-01-02", "2G", "10G", "0"])

        selection = MagicMock()
        selection.get_selected_rows.return_value = (
            store, [store.get_path(snap1), store.get_path(hold1), store.get_path(snap2)]
        )
        win.snap_view.get_selection.return_value = selection

        items = win._get_selected_items()

        self.assertEqual(len(items), 3)
        self.assertEqual(items[0], {"type": "snapshot", "name": "snap1"})
        self.assertEqual(items[1], {"type": "hold", "tag": "keep", "snapshot": "snap1"})
        self.assertEqual(items[2], {"type": "snapshot", "name": "snap2"})


class TestSnapshotManagerActions(unittest.TestCase):
    """Action handlers delegate to the repository and refresh the view."""

    def _make_window(self, repo=None):
        parent = MagicMock()
        parent.ctx.zfs_repository = repo or MagicMock()
        with patch.object(SnapshotManagerWindow, "refresh_snapshots"):
            win = SnapshotManagerWindow("tank/data", parent)
        return win

    def _select_rows(self, win, *nodes):
        selection = MagicMock()
        selection.get_selected_rows.return_value = (win.snap_store, [n["id"] for n in nodes])
        win.snap_view.get_selection.return_value = selection

    def test_on_refresh(self):
        win = self._make_window()
        with patch.object(win, "refresh_snapshots") as mock_refresh:
            win.on_refresh(None)
        mock_refresh.assert_called_once()

    def test_on_delete_releases_holds(self):
        repo = MagicMock()
        repo.list_holds.return_value = []
        repo.release.return_value = True

        win = self._make_window(repo)
        store = _FakeTreeStore()
        win.snap_store = store
        snap = store.append(None, ["snap1", "2025-01-01", "1G", "10G", "1"])
        hold = store.append(snap, ["keep", "2025-01-01", "", "", ""])
        self._select_rows(win, hold)

        dialog = MagicMock()
        dialog.run.return_value = snapshot_manager.Gtk.ResponseType.YES

        with patch.object(snapshot_manager.Gtk, "MessageDialog", return_value=dialog), \
             patch.object(win, "refresh_snapshots") as mock_refresh:
            win.on_delete(None)

        repo.release.assert_called_once_with("keep", "tank/data@snap1")
        mock_refresh.assert_called_once()

    def test_on_delete_skips_held_snapshots(self):
        repo = MagicMock()
        repo.list_holds.return_value = [_FakeHoldRow("keep")]

        win = self._make_window(repo)
        store = _FakeTreeStore()
        win.snap_store = store
        snap = store.append(None, ["snap1", "2025-01-01", "1G", "10G", "1"])
        self._select_rows(win, snap)

        with patch.object(win, "set_status") as mock_status, \
             patch.object(win, "refresh_snapshots") as mock_refresh:
            win.on_delete(None)

        repo.destroy.assert_not_called()
        mock_status.assert_called_once()
        self.assertIn("still have holds", mock_status.call_args[0][0])

    def test_on_delete_deletes_snapshots(self):
        repo = MagicMock()
        repo.list_holds.return_value = []
        repo.destroy.return_value = True

        win = self._make_window(repo)
        store = _FakeTreeStore()
        win.snap_store = store
        snap = store.append(None, ["snap1", "2025-01-01", "1G", "10G", "0"])
        self._select_rows(win, snap)

        dialog = MagicMock()
        dialog.run.return_value = snapshot_manager.Gtk.ResponseType.YES

        with patch.object(snapshot_manager.Gtk, "MessageDialog", return_value=dialog), \
             patch.object(win, "refresh_snapshots") as mock_refresh:
            win.on_delete(None)

        repo.destroy.assert_called_once_with("tank/data@snap1")
        mock_refresh.assert_called_once()

    def test_on_hold_adds_hold(self):
        repo = MagicMock()
        repo.hold.return_value = True

        win = self._make_window(repo)
        store = _FakeTreeStore()
        win.snap_store = store
        snap = store.append(None, ["snap1", "2025-01-01", "1G", "10G", "0"])
        self._select_rows(win, snap)

        dialog = MagicMock()
        dialog.run.return_value = snapshot_manager.Gtk.ResponseType.OK
        entry = MagicMock()
        entry.get_text.return_value = "keep"

        with patch.object(snapshot_manager, "create_dialog", return_value=dialog), \
             patch.object(snapshot_manager.Gtk, "Entry", return_value=entry), \
             patch.object(win, "refresh_snapshots") as mock_refresh:
            win.on_hold(None)

        repo.hold.assert_called_once_with("keep", "tank/data@snap1")
        mock_refresh.assert_called_once()

    def test_on_rollback(self):
        repo = MagicMock()
        repo.rollback.return_value = True

        win = self._make_window(repo)
        store = _FakeTreeStore()
        win.snap_store = store
        snap = store.append(None, ["snap1", "2025-01-01", "1G", "10G", "0"])
        self._select_rows(win, snap)

        dialog = MagicMock()
        dialog.run.return_value = snapshot_manager.Gtk.ResponseType.YES

        with patch.object(snapshot_manager.Gtk, "MessageDialog", return_value=dialog), \
             patch.object(win, "refresh_snapshots") as mock_refresh:
            win.on_rollback(None)

        repo.rollback.assert_called_once_with("tank/data@snap1")
        mock_refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
