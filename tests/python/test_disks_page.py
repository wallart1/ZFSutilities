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
    with mock_gtk(fresh=True):
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
    row = [""] * 13
    row[0] = path
    row[9] = pools
    row[12] = highlight
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

    def set_value(self, it, col, value):
        self._row_node(it.path)["row"][col] = value


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
        self.expand_all_calls = 0

    def get_selection(self):
        return self._selection

    def expand_all(self):
        self.expand_all_calls += 1

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

    def test_create_disks_page_is_vertically_scrollable(self):
        """The tab is wrapped in a vertical-only ScrolledWindow like other tabs."""
        dp = _import_disks_page()
        app = MagicMock()
        app.config = {"pools": []}
        app.enable_treeview_copy = MagicMock()
        app.ctx = MagicMock()

        with patch.object(dp, "refresh_disks_page"):
            page = dp.create_disks_page(app)

        page.set_policy.assert_any_call(
            dp.Gtk.PolicyType.NEVER,
            dp.Gtk.PolicyType.AUTOMATIC,
        )
        page.add.assert_called()
        # The center Pool Topology pane enforces a minimum height so the
        # page-level scrollbar engages instead of squashing it.
        dp.Gtk.Box.return_value.set_size_request.assert_any_call(
            -1,
            dp.DISKS_TOPOLOGY_MIN_HEIGHT,
        )


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

    def test_load_passes_through_repository_filtering(self):
        """The cache must not re-add disks the repository filtered out.

        Boot-disk hiding lives in DiskRepository.list_disks(); the cache has
        no inventory of its own, so whatever the repository returns is what
        the Disks page shows.
        """
        dp = _import_disks_page()
        disk_repo = MagicMock()
        disk_repo.disk_inventory.return_value = MagicMock(
            disks=[_disk(path="/dev/sdb")],
            by_path={"/dev/sdb": _disk(path="/dev/sdb")},
        )
        zfs_repo = MagicMock()
        zfs_repo.list_pools_full.return_value = []

        cache = dp.DiskInventoryCache(disk_repo, zfs_repo)
        data = cache._load()

        self.assertEqual([d.path for d in data.disks], ["/dev/sdb"])


class TestRefreshDisksPage(unittest.TestCase):
    """refresh_disks_page() repopulates stores from cached inventory data."""

    def test_refresh_repopulates_disk_store(self):
        dp = _import_disks_page()
        disks = [
            _disk(path="/dev/sda", model="SSD A", smart_health="PASSED", wear_percent=85),
            _disk(path="/dev/sdb", model="SSD B", smart_health="PASSED"),
        ]
        app = _make_app(disks=disks, topologies={})

        dp.refresh_disks_page(app)

        self.assertEqual(len(app.disks_store.rows), 2)
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_NAME], "/dev/sda")
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_MODEL], "SSD A")
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_SMART], "PASSED")
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_HEALTH], "85%")
        self.assertEqual(app.disks_store.rows[1][dp.COL_D_HEALTH], "-")
        self.assertEqual(app.disks_store.rows[1][dp.COL_D_NAME], "/dev/sdb")

    def test_refresh_health_cell_shows_hdd_surface_test(self):
        """The combined Wear/Test cell shows surface-test status for HDDs."""
        dp = _import_disks_page()
        sys.modules.pop("disk_surface_test", None)
        with mock_gtk(fresh=True):
            import disk_surface_test as dst

        disks = [
            _disk(path="/dev/sdc", model="HDD C", disk_type="HDD"),
        ]
        app = _make_app(disks=disks, topologies={})
        running = {
            "status": "running",
            "mode": "long",
            "progress_percent": 60,
            "eta": None,
        }
        with patch.object(dst, "load_surface_test_state", return_value={"tests": {"/dev/sdc": running}}):
            dp.refresh_disks_page(app)
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_HEALTH], "60%")

    def test_refresh_health_cell_inherited_for_hdd_partition(self):
        """A partition row shows its parent disk's surface-test status."""
        dp = _import_disks_page()
        sys.modules.pop("disk_surface_test", None)
        with mock_gtk(fresh=True):
            import disk_surface_test as dst

        disk = _disk(path="/dev/sdc1", model="", disk_type="part", parent_path="/dev/sdc")
        app = _make_app(disks=[disk], topologies={})
        running = {
            "status": "running",
            "mode": "short",
            "progress_percent": 20,
            "eta": None,
        }
        with patch.object(dst, "load_surface_test_state", return_value={"tests": {"/dev/sdc": running}}):
            dp.refresh_disks_page(app)
        self.assertEqual(app.disks_store.rows[0][dp.COL_D_HEALTH], "20%")

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

    def test_selection_change_selects_pool_and_tints_topology_device(self):
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
        # The topology pane shows teal text only — nothing is selected.
        self.assertEqual(app.disks_topology_view.get_selection().selected_paths, [])
        disk_row = app.disks_topology_store.root[0]["children"][0]["row"]
        self.assertTrue(disk_row[dp.COL_T_HIGHLIGHT])

    def test_topology_selection_change_does_not_select_disk_row(self):
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

        # Teal highlight is applied, but no inventory row is selected.
        self.assertEqual(disk_selection.selected_paths, [])
        self.assertEqual(app.disks_view.scroll_to_cell.call_args_list, [])
        self.assertTrue(app.disks_store.rows[0][dp.COL_D_HIGHLIGHT])

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

    def test_topology_repopulate_expands_tree(self):
        dp = _import_disks_page()
        app = _make_app(
            disks=[_disk(path="/dev/sda", pools=["pool1"])],
            topologies={"pool1": _topology("pool1")},
        )
        app.disks_store = FakeListStore([_disk_row("/dev/sda", "pool1")])
        app._disks_pool_selector.get_active_text.return_value = "pool1"

        dp._repopulate_topology_for_selected_pool(app)

        self.assertEqual(app.disks_topology_view.expand_all_calls, 1)

    def test_topology_repopulate_without_topology_does_not_expand(self):
        dp = _import_disks_page()
        app = _make_app(
            disks=[_disk(path="/dev/sda", pools=["pool1"])],
            topologies={},
        )
        app.disks_store = FakeListStore([_disk_row("/dev/sda", "pool1")])
        app._disks_pool_selector.get_active_text.return_value = None

        dp._repopulate_topology_for_selected_pool(app)

        self.assertEqual(app.disks_topology_view.expand_all_calls, 0)

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


def _mirror_topology(disk_names=("/dev/sda", "/dev/sdb")):
    """Build a pool1 topology with a single mirror vdev of *disk_names*."""
    return _topology(
        "pool1",
        children=[
            TopologyNode(
                name="mirror-0",
                vdev_type="mirror",
                state="ONLINE",
                read=0,
                write=0,
                cksum=0,
                ashift=None,
                children=[
                    TopologyNode(
                        name=name,
                        vdev_type="disk",
                        state="ONLINE",
                        read=0,
                        write=0,
                        cksum=0,
                        ashift=None,
                        children=[],
                    )
                    for name in disk_names
                ],
            )
        ],
    )


class TestTopologyBlocksizeRendering(unittest.TestCase):
    """The topology pane shows pool blocksize in bytes, never raw ashift."""

    def test_populate_topology_store_renders_bytes(self):
        dp = _import_disks_page()
        store = FakeTreeStore()
        dp._populate_topology_store(
            store,
            None,
            _topology(
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
            ),
        )
        pool_row = store.root[0]["row"]
        self.assertEqual(pool_row[dp.COL_T_ASHIFT], "4096 bytes")
        disk_row = store.root[0]["children"][0]["row"]
        self.assertEqual(disk_row[dp.COL_T_ASHIFT], "-")


class TestTopologySelectionHighlight(unittest.TestCase):
    """Topology selection highlights the matching inventory rows."""

    def _highlight_app(self, disk_names=("/dev/sda", "/dev/sdb"), extra_rows=("/dev/sdc",)):
        disks = [_disk(path=name, pools=["pool1"]) for name in disk_names]
        disks.extend(_disk(path=name, pools=[]) for name in extra_rows)
        app = _make_app(
            disks=disks,
            topologies={"pool1": _mirror_topology(disk_names)},
        )
        rows = [_disk_row(name, "pool1") for name in disk_names]
        rows.extend(_disk_row(name) for name in extra_rows)
        app.disks_store = FakeListStore(rows)
        app._disks_pool_selector.get_active_text.return_value = "pool1"
        return app

    def _select(self, dp, app, path):
        dp._repopulate_topology_for_selected_pool(app)
        selection = app.disks_topology_view.get_selection()
        selection.paths = [path]
        dp._on_topology_selection_changed(selection, app)
        return app.disks_store.rows

    def test_pool_node_selection_highlights_all_pool_disks(self):
        dp = _import_disks_page()
        app = self._highlight_app()
        rows = self._select(dp, app, (0,))
        self.assertTrue(rows[0][dp.COL_D_HIGHLIGHT])
        self.assertTrue(rows[1][dp.COL_D_HIGHLIGHT])
        self.assertFalse(rows[2][dp.COL_D_HIGHLIGHT])

    def test_vdev_node_selection_highlights_vdev_members(self):
        dp = _import_disks_page()
        app = self._highlight_app()
        rows = self._select(dp, app, (0, 0))
        self.assertTrue(rows[0][dp.COL_D_HIGHLIGHT])
        self.assertTrue(rows[1][dp.COL_D_HIGHLIGHT])
        self.assertFalse(rows[2][dp.COL_D_HIGHLIGHT])

    def test_disk_node_selection_highlights_single_disk(self):
        dp = _import_disks_page()
        app = self._highlight_app()
        rows = self._select(dp, app, (0, 0, 0))
        self.assertTrue(rows[0][dp.COL_D_HIGHLIGHT])
        self.assertFalse(rows[1][dp.COL_D_HIGHLIGHT])
        self.assertFalse(rows[2][dp.COL_D_HIGHLIGHT])

    def test_empty_topology_selection_restores_pool_highlight(self):
        dp = _import_disks_page()
        app = self._highlight_app()
        rows = self._select(dp, app, (0, 0))
        self.assertFalse(rows[2][dp.COL_D_HIGHLIGHT])

        selection = app.disks_topology_view.get_selection()
        selection.paths = []
        dp._on_topology_selection_changed(selection, app)

        self.assertTrue(rows[0][dp.COL_D_HIGHLIGHT])
        self.assertTrue(rows[1][dp.COL_D_HIGHLIGHT])
        self.assertFalse(rows[2][dp.COL_D_HIGHLIGHT])

    def test_partition_leaf_highlights_partition_and_whole_disk_rows(self):
        dp = _import_disks_page()
        app = self._highlight_app(disk_names=("/dev/sda1",), extra_rows=("/dev/sda", "/dev/sdb"))
        rows = self._select(dp, app, (0, 0, 0))
        # /dev/sda1 leaf highlights its own row and the /dev/sda whole-disk row.
        self.assertTrue(rows[0][dp.COL_D_HIGHLIGHT])
        self.assertTrue(rows[1][dp.COL_D_HIGHLIGHT])
        self.assertFalse(rows[2][dp.COL_D_HIGHLIGHT])


class TestDiskSelectionTopologyHighlight(unittest.TestCase):
    """Selecting an inventory disk tints its devices teal in the topology pane."""

    def _app(
        self,
        leaves=("/dev/sdb1", "/dev/sdb2", "/dev/sdc1"),
        inventory_paths=("/dev/sdb", "/dev/sdb1", "/dev/sdb2", "/dev/sdc1"),
        topologies=None,
    ):
        disks = [_disk(path=p, pools=["pool1"]) for p in inventory_paths]
        if topologies is None:
            topologies = {"pool1": _leaves_topology("pool1", leaves)}
        app = _make_app(disks=disks, topologies=topologies)
        app.disks_store = FakeListStore([_disk_row(p, "pool1") for p in inventory_paths])
        app._disks_pool_selector.get_active_text.return_value = "pool1"
        dp = _import_disks_page()
        dp._repopulate_topology_for_selected_pool(app)
        return dp, app

    def _select_disk(self, dp, app, row):
        selection = app.disks_view.get_selection.return_value
        selection.get_selected_rows.return_value = (app.disks_store, [row])
        dp._on_disk_selection_changed(selection, app)

    def _leaf_rows(self, app):
        return [c["row"] for c in app.disks_topology_store.root[0]["children"][0]["children"]]

    def test_whole_disk_selection_tints_all_its_devices(self):
        dp, app = self._app()
        self._select_disk(dp, app, 0)  # /dev/sdb
        leaf_flags = [row[dp.COL_T_HIGHLIGHT] for row in self._leaf_rows(app)]
        self.assertEqual(leaf_flags, [True, True, False])
        # Pool and vdev rows are never tinted.
        self.assertFalse(app.disks_topology_store.root[0]["row"][dp.COL_T_HIGHLIGHT])
        mirror_row = app.disks_topology_store.root[0]["children"][0]["row"]
        self.assertFalse(mirror_row[dp.COL_T_HIGHLIGHT])

    def test_partition_selection_tints_only_that_device(self):
        dp, app = self._app()
        self._select_disk(dp, app, 1)  # /dev/sdb1
        leaf_flags = [row[dp.COL_T_HIGHLIGHT] for row in self._leaf_rows(app)]
        self.assertEqual(leaf_flags, [True, False, False])

    def test_topology_selection_is_never_modified_by_disk_selection(self):
        dp, app = self._app()
        self._select_disk(dp, app, 0)
        self.assertEqual(app.disks_topology_view.get_selection().selected_paths, [])

    def test_clearing_disk_selection_clears_topology_highlights(self):
        dp, app = self._app()
        self._select_disk(dp, app, 0)
        self.assertTrue(any(row[dp.COL_T_HIGHLIGHT] for row in self._leaf_rows(app)))
        selection = app.disks_view.get_selection.return_value
        selection.get_selected_rows.return_value = (app.disks_store, [])
        dp._on_disk_selection_changed(selection, app)
        self.assertFalse(any(row[dp.COL_T_HIGHLIGHT] for row in self._leaf_rows(app)))

    def test_pool_switch_reapplies_tint_for_selected_disk(self):
        topologies = {
            "pool1": _leaves_topology("pool1", ("/dev/sdb1",)),
            "pool2": _leaves_topology("pool2", ("/dev/sdb2",)),
        }
        dp, app = self._app(
            inventory_paths=("/dev/sdb",),
            topologies=topologies,
        )
        self._select_disk(dp, app, 0)  # /dev/sdb
        leaf = app.disks_topology_store.root[0]["children"][0]["children"][0]["row"]
        self.assertTrue(leaf[dp.COL_T_HIGHLIGHT])

        app._disks_pool_selector.get_active_text.return_value = "pool2"
        dp._repopulate_topology_for_selected_pool(app)

        leaf = app.disks_topology_store.root[0]["children"][0]["children"][0]["row"]
        self.assertEqual(leaf[dp.COL_T_NAME], "/dev/sdb2")
        self.assertTrue(leaf[dp.COL_T_HIGHLIGHT])

    def test_topology_cell_highlight_func_sets_foreground(self):
        dp = _import_disks_page()
        renderer = MagicMock()
        model = MagicMock()
        tree_iter = MagicMock()

        model.get_value.return_value = True
        dp._topology_cell_highlight_func(MagicMock(), renderer, model, tree_iter)
        renderer.set_property.assert_called_with("foreground", dp.POOL_MEMBER_HIGHLIGHT_FG)

        renderer.reset_mock()
        model.get_value.return_value = False
        dp._topology_cell_highlight_func(MagicMock(), renderer, model, tree_iter)
        renderer.set_property.assert_called_with("foreground", None)


class TestTopologyNodeMatchesDisk(unittest.TestCase):
    """_topology_node_matches_disk() inventory-to-topology path matching."""

    def test_exact_match(self):
        dp = _import_disks_page()
        self.assertTrue(dp._topology_node_matches_disk("/dev/sda", "/dev/sda"))

    def test_partition_leaf_matches_whole_disk(self):
        dp = _import_disks_page()
        self.assertTrue(dp._topology_node_matches_disk("/dev/sda1", "/dev/sda"))

    def test_nvme_partition_leaf_matches_whole_disk(self):
        dp = _import_disks_page()
        self.assertTrue(dp._topology_node_matches_disk("/dev/nvme0n1p1", "/dev/nvme0n1"))

    def test_basename_match(self):
        dp = _import_disks_page()
        self.assertTrue(dp._topology_node_matches_disk("/dev/disk/by-id/sda", "/dev/sda"))

    def test_unrelated_disk_does_not_match(self):
        dp = _import_disks_page()
        self.assertFalse(dp._topology_node_matches_disk("/dev/sdc1", "/dev/sdb"))

    def test_similar_name_does_not_match(self):
        dp = _import_disks_page()
        self.assertFalse(dp._topology_node_matches_disk("/dev/sdaa", "/dev/sda"))

    def test_non_device_node_never_matches(self):
        dp = _import_disks_page()
        self.assertFalse(dp._topology_node_matches_disk("mirror-0", "/dev/sda"))
        self.assertFalse(dp._topology_node_matches_disk("pool1", "/dev/sda"))


def _leaves_topology(pool_name, leaves):
    """Build a topology with a single mirror vdev holding one disk leaf per name."""
    return _topology(
        pool_name,
        children=[
            TopologyNode(
                name="mirror-0",
                vdev_type="mirror",
                state="ONLINE",
                read=0,
                write=0,
                cksum=0,
                ashift=None,
                children=[
                    TopologyNode(
                        name=name,
                        vdev_type="disk",
                        state="ONLINE",
                        read=0,
                        write=0,
                        cksum=0,
                        ashift=None,
                        children=[],
                    )
                    for name in leaves
                ],
            )
        ],
    )


class TestPathMatchesAnyDevice(unittest.TestCase):
    """_path_matches_any_device() topology-to-inventory path matching."""

    def test_exact_match(self):
        dp = _import_disks_page()
        self.assertTrue(dp._path_matches_any_device("/dev/sda", {"/dev/sda"}))

    def test_basename_match(self):
        dp = _import_disks_page()
        self.assertTrue(dp._path_matches_any_device("/dev/sda", {"/other/dir/sda"}))

    def test_whole_disk_matches_partition_leaf(self):
        dp = _import_disks_page()
        self.assertTrue(dp._path_matches_any_device("/dev/sda", {"/dev/sda1"}))

    def test_whole_disk_matches_nvme_partition_leaf(self):
        dp = _import_disks_page()
        self.assertTrue(dp._path_matches_any_device("/dev/nvme0n1", {"/dev/nvme0n1p1"}))

    def test_unrelated_disk_does_not_match(self):
        dp = _import_disks_page()
        self.assertFalse(dp._path_matches_any_device("/dev/sdb", {"/dev/sda1"}))

    def test_similar_name_does_not_match(self):
        dp = _import_disks_page()
        self.assertFalse(dp._path_matches_any_device("/dev/sda", {"/dev/sdaa"}))

    def test_realpath_match_via_symlink(self):
        import tempfile

        dp = _import_disks_page()
        with tempfile.TemporaryDirectory() as tmp:
            link = os.path.join(tmp, "ata-TEST")
            os.symlink("/dev/null", link)
            self.assertTrue(dp._path_matches_any_device(link, {"/dev/null"}))
            self.assertTrue(dp._path_matches_any_device("/dev/null", {link}))


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
