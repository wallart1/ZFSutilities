"""Tests for disks_page.py and disk_actions.py — Disks tab UI and actions."""

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


def _import_disk_actions():
    """Import disk_actions under a fresh mocked GTK context."""
    sys.modules.pop("disk_actions", None)
    sys.modules.pop("disks_page", None)
    with mock_gtk():
        import disk_actions

        return disk_actions


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


def _disk_row(path, pools=""):
    """Return a disk ListStore row with *path* and *pools* filled in."""
    row = [""] * 11
    row[0] = path
    row[9] = pools
    return row


def _make_app(disks=None, topologies=None):
    """Return a mocked app object ready for disks_page tests."""
    app = MagicMock()
    app.config = {"pools": []}
    app.stack.get_visible_child_name.return_value = "disks"
    app.enable_treeview_copy = MagicMock()

    cache = MagicMock()
    cache.get.return_value = MagicMock(disks=disks or [], topologies=topologies or {})
    app._disks_inventory_cache = cache

    # Default to an empty fake store so selection-restore loops terminate.
    app.disks_store = FakeListStore()

    # Topology store helpers.
    app.disks_topology_store.append.return_value = MagicMock()

    # Selection helpers.
    app.disks_view.get_selection.return_value.get_selected_rows.return_value = (
        app.disks_store,
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

        def _set_active_text(text):
            app._disks_pool_selector.get_active_text.return_value = text

        app._disks_pool_selector.set_active_text.side_effect = _set_active_text

        selection = app.disks_view.get_selection.return_value
        selection.get_selected_rows.return_value = (
            app.disks_store,
            [0],
        )

        dp._on_disk_selection_changed(selection, app)

        app._disks_pool_selector.set_active_text.assert_called_with("pool1")
        app.disks_topology_store.append.assert_called()


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


class TestDiskActions(unittest.TestCase):
    """Disk tab action handlers."""

    def _select_first_disk(self, app, path="/dev/sda"):
        """Prime app.disks_store and selection for a single selected disk."""
        app.disks_store = FakeListStore([_disk_row(path)])
        selection = app.disks_view.get_selection.return_value
        selection.get_selected_rows.return_value = (app.disks_store, [0])

    def test_smart_details_logs_output(self):
        da = _import_disk_actions()
        app = _make_app()
        app.ctx.disk_repository.smart_details.return_value = "line one\nline two\n"
        self._select_first_disk(app)

        with capture_logs() as logs:
            da.on_disks_smart_details(app)

        _assert_log_contains(logs, "INFO: SMART details for /dev/sda:")
        _assert_log_contains(logs, "INFO: line one")
        _assert_log_contains(logs, "INFO: line two")

    def test_smart_details_warns_when_nothing_selected(self):
        da = _import_disk_actions()
        app = _make_app()
        app.disks_view.get_selection.return_value.get_selected_rows.return_value = (
            app.disks_store,
            [],
        )

        with capture_logs() as logs:
            da.on_disks_smart_details(app)

        _assert_log_contains(logs, "WARN: Select a disk to view SMART details")

    def test_smart_details_warns_when_unavailable(self):
        da = _import_disk_actions()
        app = _make_app()
        app.ctx.disk_repository.smart_details.return_value = "n/a"
        self._select_first_disk(app)

        with capture_logs() as logs:
            da.on_disks_smart_details(app)

        _assert_log_contains(logs, "WARN: SMART details unavailable for /dev/sda")


if __name__ == "__main__":
    unittest.main()
