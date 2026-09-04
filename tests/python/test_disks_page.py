"""Tests for disks_page.py — Disks tab UI."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from disk_repository import DiskInfo
from test_support import capture_logs, mock_gtk
from zfs_repository import TopologyNode


def _import_disks_page():
    """Import disks_page under a fresh mocked GTK context."""
    sys.modules.pop("disks_page", None)
    with mock_gtk():
        import disks_page

        return disks_page


def _assert_log_contains(logs, needle):
    """Assert that *needle* appears as a substring in one captured log line."""
    assert any(needle in line for line in logs), f"{needle!r} not found in {logs}"


class _Iter:
    """Truth-y iterator stand-in for FakeListStore."""

    def __init__(self, index):
        self.index = index


class FakeListStore:
    """Minimal ListStore stand-in that supports iteration and value lookups."""

    def __init__(self, rows=None):
        self.rows = rows or []

    def clear(self):
        self.rows = []

    def append(self, row):
        self.rows.append(list(row))
        return _Iter(len(self.rows) - 1)

    def get_iter_first(self):
        return _Iter(0) if self.rows else None

    def iter_next(self, it):
        nxt = it.index + 1
        return _Iter(nxt) if nxt < len(self.rows) else None

    def get_iter(self, path):
        return _Iter(path if isinstance(path, int) else 0)

    def get_value(self, it, col):
        return self.rows[it.index][col]

    def get_path(self, it):
        return it.index

    def set_value(self, it, col, value):
        self.rows[it.index][col] = value


def _disk_row(path, pools="", highlight=False):
    """Return a disk ListStore row with *path*, *pools*, and *highlight* filled in."""
    row = [""] * 12
    row[0] = path
    row[9] = pools
    row[11] = highlight
    return row


class _TreeIter:
    """Path-based iterator stand-in for FakeTreeStore."""

    def __init__(self, path):
        self.path = path


class FakeTreeStore:
    """Minimal TreeStore stand-in that supports nested iteration."""

    def __init__(self):
        self.root = []

    def clear(self):
        self.root = []

    def _node(self, parent_path):
        node = self.root
        for idx in parent_path:
            node = node[idx]["children"]
        return node

    def _row_node(self, path):
        node = self.root
        for idx in path[:-1]:
            node = node[idx]["children"]
        return node[path[-1]]

    def append(self, parent_iter, row):
        parent_path = parent_iter.path if parent_iter else ()
        children = self._node(parent_path)
        children.append({"row": list(row), "children": []})
        new_path = parent_path + (len(children) - 1,)
        return _TreeIter(new_path)

    def get_iter_first(self):
        return _TreeIter((0,)) if self.root else None

    def iter_children(self, parent_iter):
        parent_path = parent_iter.path if parent_iter else ()
        children = self._node(parent_path)
        if children:
            return _TreeIter(parent_path + (0,))
        return None

    def iter_next(self, it):
        path = it.path
        parent_path = path[:-1]
        idx = path[-1]
        children = self._node(parent_path)
        if idx + 1 < len(children):
            return _TreeIter(parent_path + (idx + 1,))
        return None

    def get_value(self, it, col):
        return self._row_node(it.path)["row"][col]

    def get_path(self, it):
        return it.path

    def get_iter(self, path):
        return _TreeIter(path)


class FakeTreeSelection:
    """TreeSelection stand-in with configurable selected paths."""

    def __init__(self, store, paths=None):
        self.store = store
        self.paths = paths or []
        self.selected_paths = []

    def get_selected_rows(self):
        return (self.store, self.paths)

    def select_path(self, path):
        self.selected_paths.append(path)


class FakeTreeView:
    """TreeView stand-in backed by a FakeTreeStore and FakeTreeSelection."""

    def __init__(self, store, paths=None):
        self.store = store
        self._selection = FakeTreeSelection(store, paths)
        self.scrolled_to = []

    def get_selection(self):
        return self._selection

    def scroll_to_cell(self, path, *args, **_kwargs):
        self.scrolled_to.append(path)


def _make_app(disks=None, topologies=None):
    """Return a mocked app object ready for disks_page tests."""
    app = MagicMock()
    app.config = {"pools": []}
    app.stack.get_visible_child_name.return_value = "disks"
    app.enable_treeview_copy = MagicMock()

    cache = MagicMock()
    cache.get.return_value = MagicMock(disks=disks or [], topologies=topologies or {})
    app._disks_inventory_cache = cache
    app._disks_syncing_selection = False

    # Default to an empty fake store so selection-restore loops terminate.
    app.disks_store = FakeListStore()

    # Topology store helpers.
    app.disks_topology_store = FakeTreeStore()
    app.disks_topology_view = FakeTreeView(app.disks_topology_store)

    # Dataset tuning store helpers.
    app.disks_dataset_store = FakeListStore()

    # Selection helpers.
    app.disks_view.get_selection.return_value.get_selected_rows.return_value = (
        app.disks_store,
        [],
    )
    app.disks_dataset_view = MagicMock()
    app.disks_dataset_view.get_selection.return_value.get_selected_rows.return_value = (
        app.disks_dataset_store,
        [],
    )

    # Pool selector helpers.
    app._disks_pool_selector.get_active_text.return_value = None
    app._disks_pool_selector.get_active.return_value = -1

    app.ctx = MagicMock()
    return app


def _disk(**kwargs):
    """Build a DiskInfo with sensible defaults."""
    defaults = {
        "name": "sda",
        "path": "/dev/sda",
        "by_id": "ata-SSD-1234",
        "model": "Test SSD",
        "serial": "ABC123",
        "size_bytes": 1000204886016,
        "size_human": "931.51 GiB",
        "disk_type": "SSD",
        "logical_sector": 512,
        "physical_sector": 512,
        "transport": "sata",
        "pools": [],
        "smart_health": "PASSED",
    }
    defaults.update(kwargs)
    return DiskInfo(**defaults)


def _topology(pool_name="pool1", children=None):
    """Build a TopologyNode for a pool."""
    return TopologyNode(
        name=pool_name,
        vdev_type="pool",
        state="ONLINE",
        read=0,
        write=0,
        cksum=0,
        ashift=12,
        children=children or [],
    )


class TestCreateDisksPage(unittest.TestCase):
    """create_disks_page() builds the tab widgets and cache."""

    def test_create_disks_page_builds_widgets_and_cache(self):
        dp = _import_disks_page()
        app = MagicMock()
        app.config = {"pools": []}
        app.enable_treeview_copy = MagicMock()
        app.ctx = MagicMock()

        with patch.object(dp, "refresh_disks_page"):
            page = dp.create_disks_page(app)

        self.assertIsNotNone(page)
        self.assertIsInstance(app._disks_inventory_cache, dp.DiskInventoryCache)
        self.assertIsNotNone(app.disks_store)
        self.assertIsNotNone(app.disks_view)
        self.assertIsNotNone(app.disks_topology_store)
        self.assertIsNotNone(app.disks_topology_view)
        self.assertIsNotNone(app._disks_pool_selector)


class TestDiskInventoryCache(unittest.TestCase):
    """DiskInventoryCache loads and maps disk inventory to pool topology."""

    def test_load_maps_disk_path_to_pool(self):
        dp = _import_disks_page()
        disk_repo = MagicMock()
        disk_repo.disk_inventory.return_value = MagicMock(
            disks=[_disk(path="/dev/sda")],
            by_path={"/dev/sda": _disk(path="/dev/sda")},
        )
        zfs_repo = MagicMock()
        zfs_repo.list_pools_full.return_value = [{"name": "pool1"}]
        zfs_repo.pool_topology.return_value = _topology(
            "pool1",
            children=[
                TopologyNode(
                    name="/dev/sda",
                    vdev_type="disk",
                    state="ONLINE",
                    read=0,
                    write=0,
                    cksum=0,
                    ashift=None,
                    children=[],
                )
            ],
        )
        zfs_repo.get_ashift.return_value = MagicMock(effective=12)

        cache = dp.DiskInventoryCache(disk_repo, zfs_repo)
        data = cache._load()

        self.assertEqual(len(data.disks), 1)
        self.assertEqual(data.disks[0].pools, ["pool1"])
        self.assertEqual(data.topologies["pool1"].ashift, 12)

    def test_load_maps_partition_path_to_pool(self):
        dp = _import_disks_page()
        partition = _disk(
            path="/dev/sda1",
            disk_type="part",
            parent_path="/dev/sda",
            pools=[],
        )
        disk_repo = MagicMock()
        disk_repo.disk_inventory.return_value = MagicMock(
            disks=[partition],
            by_path={"/dev/sda1": partition},
        )
        zfs_repo = MagicMock()
        zfs_repo.list_pools_full.return_value = [{"name": "pool1"}]
        zfs_repo.pool_topology.return_value = _topology(
            "pool1",
            children=[
                TopologyNode(
                    name="/dev/sda1",
                    vdev_type="disk",
                    state="ONLINE",
                    read=0,
                    write=0,
                    cksum=0,
                    ashift=None,
                    children=[],
                )
            ],
        )
        zfs_repo.get_ashift.return_value = MagicMock(effective=12)

        cache = dp.DiskInventoryCache(disk_repo, zfs_repo)
        data = cache._load()

        self.assertEqual(len(data.disks), 1)
        self.assertEqual(data.disks[0].pools, ["pool1"])


class TestRefreshDisksPage(unittest.TestCase):
    """refresh_disks_page() repopulates stores from cached inventory data."""

    def test_refresh_repopulates_disk_store(self):
        dp = _import_disks_page()
        disks = [
            _disk(path="/dev/sda", model="SSD A", smart_health="PASSED"),
            _disk(path="/dev/sdb", model="SSD B", smart_health="PASSED"),
        ]
        app = _make_app(disks=disks, topologies={})

        dp.refresh_disks_page(app)

        self.assertEqual(len(app.disks_store.rows), 2)
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_NAME], "/dev/sda")
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_MODEL], "SSD A")
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_SMART], "PASSED")
        self.assertEqual(app.disks_store.rows[1][dp.COL_D_NAME], "/dev/sdb")

    def test_refresh_maps_pool_membership(self):
        dp = _import_disks_page()
        disks = [_disk(path="/dev/sda", pools=["pool1"])]
        topology = _topology(
            "pool1",
            children=[
                TopologyNode(
                    name="/dev/sda",
                    vdev_type="disk",
                    state="ONLINE",
                    read=0,
                    write=0,
                    cksum=0,
                    ashift=None,
                    children=[],
                )
            ],
        )
        app = _make_app(disks=disks, topologies={"pool1": topology})

        dp.refresh_disks_page(app)

        self.assertEqual(len(app.disks_store.rows), 1)
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_POOLS], "pool1")

    def test_refresh_preserves_selection(self):
        dp = _import_disks_page()
        disks = [
            _disk(path="/dev/sda"),
            _disk(path="/dev/sdb"),
        ]
        app = _make_app(disks=disks, topologies={})
        app.disks_store = FakeListStore(
            [
                _disk_row("/dev/sda"),
                _disk_row("/dev/sdb"),
            ]
        )

        # Simulate /dev/sdb being selected before refresh.
        selection = app.disks_view.get_selection.return_value
        selection.get_selected_rows.return_value = (
            app.disks_store,
            [1],
        )
        captured_paths = []
        selection.select_path = captured_paths.append

        dp.refresh_disks_page(app)

        self.assertEqual(len(captured_paths), 1)
        self.assertEqual(captured_paths[0], 1)

    def test_on_disks_refresh_invalidates_cache_and_logs(self):
        dp = _import_disks_page()
        app = _make_app()
        with patch.object(dp, "refresh_disks_page") as mock_refresh:
            with capture_logs() as logs:
                dp.on_disks_refresh(app)

        app._disks_inventory_cache.invalidate.assert_called_once()
        mock_refresh.assert_called_once_with(app)
        _assert_log_contains(logs, "VERB: Disks refreshed")


class TestSelectionAndTopology(unittest.TestCase):
    """Selection changes drive the pool selector and topology view."""

    def test_selection_change_selects_pool_and_populates_topology(self):
        dp = _import_disks_page()
        topology = _topology(
            "pool1",
            children=[
                TopologyNode(
                    name="/dev/sda",
                    vdev_type="disk",
                    state="ONLINE",
                    read=0,
                    write=0,
                    cksum=0,
                    ashift=None,
                    children=[],
                )
            ],
        )
        app = _make_app(
            disks=[_disk(path="/dev/sda", pools=["pool1"])],
            topologies={"pool1": topology},
        )
        app.disks_store = FakeListStore([_disk_row("/dev/sda", "pool1")])
        app._disks_pool_selector.get_active_text.return_value = None
        app._disks_pool_selector.get_model.return_value = [["pool1"]]

        def _set_active(index):
            model = app._disks_pool_selector.get_model.return_value
            app._disks_pool_selector.get_active_text.return_value = (
                model[index][0] if 0 <= index < len(model) else None
            )

        app._disks_pool_selector.set_active.side_effect = _set_active

        selection = app.disks_view.get_selection.return_value
        selection.get_selected_rows.return_value = (
            app.disks_store,
            [0],
        )

        dp._on_disk_selection_changed(selection, app)

        app._disks_pool_selector.set_active.assert_called_with(0)
        self.assertTrue(len(app.disks_topology_store.root) > 0)
        self.assertEqual(app.disks_topology_view.get_selection().selected_paths, [(0, 0)])

    def test_topology_selection_change_selects_disk_row(self):
        dp = _import_disks_page()
        topology = _topology(
            "pool1",
            children=[
                TopologyNode(
                    name="/dev/sda",
                    vdev_type="disk",
                    state="ONLINE",
                    read=0,
                    write=0,
                    cksum=0,
                    ashift=None,
                    children=[],
                )
            ],
        )
        app = _make_app(
            disks=[_disk(path="/dev/sda", pools=["pool1"])],
            topologies={"pool1": topology},
        )
        app.disks_store = FakeListStore([_disk_row("/dev/sda", "pool1")])
        disk_selection = FakeTreeSelection(app.disks_store)
        app.disks_view.get_selection.return_value = disk_selection
        app._disks_pool_selector.get_active_text.return_value = "pool1"

        dp._repopulate_topology_for_selected_pool(app)

        selection = app.disks_topology_view.get_selection()
        selection.paths = [(0, 0)]
        dp._on_topology_selection_changed(selection, app)

        self.assertEqual(disk_selection.selected_paths, [0])
        self.assertEqual(app.disks_view.scroll_to_cell.call_args_list[-1][0][0], 0)

    def test_pool_selector_change_highlights_member_disks(self):
        dp = _import_disks_page()
        disks = [
            _disk(path="/dev/sda", pools=["pool1"]),
            _disk(path="/dev/sdb", pools=["pool2"]),
            _disk(path="/dev/sdc", pools=["pool1", "pool2"]),
        ]
        app = _make_app(
            disks=disks,
            topologies={
                "pool1": _topology("pool1"),
                "pool2": _topology("pool2"),
            },
        )
        app.disks_store = FakeListStore(
            [
                _disk_row("/dev/sda"),
                _disk_row("/dev/sdb"),
                _disk_row("/dev/sdc"),
            ]
        )
        app._disks_pool_selector.get_active_text.return_value = "pool1"

        dp._repopulate_topology_for_selected_pool(app)

        self.assertTrue(app.disks_store.rows[0][dp.COL_D_HIGHLIGHT])
        self.assertFalse(app.disks_store.rows[1][dp.COL_D_HIGHLIGHT])
        self.assertTrue(app.disks_store.rows[2][dp.COL_D_HIGHLIGHT])

    def test_highlight_cleared_for_missing_pool(self):
        dp = _import_disks_page()
        app = _make_app(
            disks=[_disk(path="/dev/sda", pools=["pool1"])],
            topologies={},
        )
        app.disks_store = FakeListStore([_disk_row("/dev/sda", highlight=True)])
        app._disks_pool_selector.get_active_text.return_value = None

        dp._highlight_pool_disks(app, None)

        self.assertFalse(app.disks_store.rows[0][dp.COL_D_HIGHLIGHT])

    def test_refresh_restores_highlight_for_active_pool(self):
        dp = _import_disks_page()
        disks = [
            _disk(path="/dev/sda", pools=["pool1"]),
            _disk(path="/dev/sdb", pools=["pool2"]),
        ]
        app = _make_app(
            disks=disks,
            topologies={"pool1": _topology("pool1")},
        )
        app.disks_store = FakeListStore()
        app._disks_pool_selector.get_active_text.return_value = "pool1"

        dp.refresh_disks_page(app)

        self.assertTrue(app.disks_store.rows[0][dp.COL_D_HIGHLIGHT])
        self.assertFalse(app.disks_store.rows[1][dp.COL_D_HIGHLIGHT])

    def test_disk_cell_highlight_func_sets_foreground(self):
        dp = _import_disks_page()
        renderer = MagicMock()
        model = MagicMock()
        tree_iter = MagicMock()

        model.get_value.return_value = True
        dp._disk_cell_highlight_func(MagicMock(), renderer, model, tree_iter)
        renderer.set_property.assert_called_with("foreground", dp.POOL_MEMBER_HIGHLIGHT_FG)

        renderer.reset_mock()
        model.get_value.return_value = False
        dp._disk_cell_highlight_func(MagicMock(), renderer, model, tree_iter)
        renderer.set_property.assert_called_with("foreground", None)


class TestUpdateButtonSensitivity(unittest.TestCase):
    """update_disks_button_sensitivity() respects the selection count."""

    def test_update_button_sensitivity_enables_smart_details_only_for_single_selection(self):
        dp = _import_disks_page()
        app = _make_app()
        btn = MagicMock()
        app._disks_smart_details_btn = btn
        selection = app.disks_view.get_selection.return_value

        for count, expected in [(0, False), (1, True), (2, False)]:
            paths = [MagicMock() for _ in range(count)]
            selection.get_selected_rows.return_value = (app.disks_store, paths)
            dp.update_disks_button_sensitivity(app)
            btn.set_sensitive.assert_called_with(expected)
            btn.reset_mock()


if __name__ == "__main__":
    unittest.main()
