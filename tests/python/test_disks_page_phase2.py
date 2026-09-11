"""Phase 2 tests for the Disks page dataset-tuning UI and Apply Profile action."""

import os
import subprocess
import sys
import unittest
from typing import ClassVar
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs, mock_gtk
from workload_profiles import ALL_KNOWN_PROPERTIES
from zfs_repository import DatasetRow, TopologyNode


def _import_disks_page():
    """Import disks_page under a fresh mocked GTK context."""
    sys.modules.pop("disks_page", None)
    with mock_gtk():
        import disks_page

        return disks_page


def _import_action_dispatch():
    """Import action_dispatch under a fresh mocked GTK context."""
    sys.modules.pop("action_dispatch", None)
    sys.modules.pop("disks_page", None)
    with mock_gtk():
        import action_dispatch

        return action_dispatch


class FakeListStore:
    """Minimal ListStore stand-in."""

    def __init__(self, rows=None):
        self.rows = rows or []

    def clear(self):
        self.rows = []

    def append(self, row):
        self.rows.append(list(row))

    def get_iter_first(self):
        return None

    def iter_next(self, it):
        return None

    def get_iter(self, path):
        return path

    def get_value(self, it, col):
        return self.rows[it][col]

    def get_path(self, it):
        return it

    def set_value(self, it, col, value):
        self.rows[it][col] = value


class FakeTreeSelection:
    """TreeSelection stand-in that reports a configurable path list.

    Mirrors real GTK behavior: paths that no longer resolve to a row in the
    model (e.g. after the store was cleared) are dropped.
    """

    def __init__(self, model, paths=None):
        self.model = model
        self.paths = paths or []

    def get_selected_rows(self):
        rows = getattr(self.model, "rows", None)
        if isinstance(rows, list):
            self.paths = [p for p in self.paths if isinstance(p, int) and p < len(rows)]
        return (self.model, self.paths)

    def select_path(self, path):
        pass

    def select_iter(self, it):
        index = it.index if hasattr(it, "index") else it
        if index not in self.paths:
            self.paths.append(index)

    def unselect_all(self):
        self.paths = []


class FakeAdjustment:
    """Gtk.Adjustment stand-in for scroll-position tests."""

    def __init__(self, value=0.0, upper=0.0, page_size=0.0):
        self._value = value
        self._upper = upper
        self._page_size = page_size

    def get_value(self):
        return self._value

    def set_value(self, value):
        self._value = value

    def get_upper(self):
        return self._upper

    def get_page_size(self):
        return self._page_size


class FakeTreeView:
    """TreeView stand-in with a FakeTreeSelection."""

    def __init__(self, model=None, paths=None):
        self.model = model
        self._selection = FakeTreeSelection(model, paths)
        self._vadjustment = None

    def get_selection(self):
        return self._selection

    def get_vadjustment(self):
        return self._vadjustment


class FakeComboBoxText:
    """ComboBoxText stand-in with active-text tracking."""

    def __init__(self):
        self._text = None
        self._items = []
        self._handlers = []

    def append_text(self, text):
        self._items.append(text)

    def remove_all(self):
        self._items = []

    def get_active_text(self):
        return self._text

    def set_active(self, index):
        if 0 <= index < len(self._items):
            self._text = self._items[index]
        else:
            self._text = None
        for handler in self._handlers:
            handler(self)

    def get_model(self):
        return [[item] for item in self._items]

    def connect(self, signal, handler, *args):
        self._handlers.append(lambda cb: handler(cb, *args))


class FakePickerListStore:
    """ListStore stand-in for the Apply Profile picker; keyed by row index."""

    def __init__(self, *types):
        self.types = types
        self.rows = []

    def append(self, row):
        self.rows.append(list(row))

    def get_value(self, it, col):
        return self.rows[it][col]


class FakeSingleSelection:
    """Single-selection TreeSelection stand-in driven by row index."""

    def __init__(self, model):
        self.model = model
        self.selected = None
        self.mode = None
        self._handlers = []

    def set_mode(self, mode):
        self.mode = mode

    def get_selected(self):
        if self.selected is None:
            return (self.model, None)
        return (self.model, self.selected)

    def select_path(self, path):
        self.selected = path
        for handler in self._handlers:
            handler()

    def connect(self, signal, handler):
        self._handlers.append(handler)


class FakePickerTreeView:
    """TreeView stand-in whose selection is a FakeSingleSelection."""

    def __init__(self, model=None):
        self.model = model
        self._selection = FakeSingleSelection(model)
        self.columns = []

    def set_grid_lines(self, *_args):
        pass

    def get_selection(self):
        return self._selection

    def append_column(self, col):
        self.columns.append(col)


class FakeDatasetRunner:
    """BackupRunner stand-in for dataset action tests."""

    def __init__(self):
        self.running = False
        self.steps = []
        self._on_complete = None

    def set_steps(self, steps):
        self.steps = steps

    def start(self, on_complete=None):
        self.running = True
        self._on_complete = on_complete

    def finish(self, cancelled=False, rc=0):
        self.running = False
        if self._on_complete:
            self._on_complete(cancelled=cancelled, rc=rc)


class _Iter:
    """Truth-y iterator stand-in for FakeListStore iteration."""

    def __init__(self, index):
        self.index = index


class FakeListStoreIterable:
    """FakeListStore that supports get_iter_first/iter_next."""

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


def _make_app(topologies=None, datasets=None, properties=None):
    """Return a mocked app object ready for dataset-tuning tests."""
    app = MagicMock()
    app.config = {"pools": []}
    app.parent_dir = "/tmp/bin"
    app.stack.get_visible_child_name.return_value = "disks"
    app.enable_treeview_copy = MagicMock()

    cache = MagicMock()
    cache.get.return_value = MagicMock(disks=[], topologies=topologies or {})
    app._disks_inventory_cache = cache
    app._disks_syncing_selection = False

    app._disks_pool_selector = FakeComboBoxText()
    app.disks_store = FakeListStoreIterable()
    app.disks_view = FakeTreeView(app.disks_store, [])
    app.disks_topology_store = MagicMock()
    app.disks_topology_view = MagicMock()
    app.disks_dataset_store = FakeListStoreIterable()
    app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [])
    app.dataset_runner = FakeDatasetRunner()

    zfs_caps = MagicMock()
    zfs_caps.supports.return_value = False
    zfs_caps.requires.return_value = "requires OpenZFS 2.3+"

    repo = MagicMock()
    repo.list_datasets.return_value = datasets or []
    repo.get_properties.return_value = properties or {}

    app.ctx = MagicMock()
    app.ctx.zfs_repository = repo
    app.ctx.zfs_caps = zfs_caps

    return app


def _dataset_row(name, ds_type):
    return DatasetRow(
        name=name,
        creation="Mon Jan 1 00:00 2024",
        ds_type=ds_type,
        used="10G",
        avail="100G",
        refer="5G",
        origin="-",
        clones="-",
        mounted="yes",
    )


def _topology(pool_name="pool1", children=None):
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


class TestDatasetTuningUI(unittest.TestCase):
    """Disks page dataset-tuning pane construction and refresh."""

    def test_dataset_tuning_store_columns_defined(self):
        dp = _import_disks_page()
        self.assertEqual(dp.COL_DS_NAME, 0)
        self.assertEqual(dp.COL_DS_USED, 2)
        self.assertEqual(dp.COL_DS_PROFILE_MATCH, 11)

    def test_refresh_loads_datasets_and_profile_match(self):
        dp = _import_disks_page()
        datasets = [
            _dataset_row("pool1/data", "filesystem"),
        ]
        props = {
            "recordsize": "128K",
            "compression": "lz4",
            "atime": "off",
            "logbias": "latency",
            "sync": "standard",
            "primarycache": "all",
            "special_small_blocks": "0",
            "volblocksize": "16K",
            "ashift": "12",
        }
        app = _make_app(
            topologies={"pool1": _topology("pool1")},
            datasets=datasets,
            properties=props,
        )
        app._disks_pool_selector._text = "pool1"
        app._disks_pool_selector._items = ["pool1"]

        dp.refresh_disks_page(app)

        self.assertEqual(len(app.disks_dataset_store.rows), 1)
        row = app.disks_dataset_store.rows[0]
        self.assertEqual(row[dp.COL_DS_NAME], "pool1/data")
        self.assertEqual(row[dp.COL_DS_TYPE], "filesystem")
        self.assertEqual(row[dp.COL_DS_USED], "10G")
        self.assertEqual(row[dp.COL_DS_COMPRESSION], "lz4")
        self.assertEqual(row[dp.COL_DS_PROFILE_MATCH], "general")

    def test_pool_selector_change_repopulates_dataset_view(self):
        dp = _import_disks_page()
        datasets = [_dataset_row("pool1/data", "filesystem")]
        app = _make_app(
            topologies={"pool1": _topology("pool1")},
            datasets=datasets,
            properties={"compression": "lz4"},
        )
        app._disks_pool_selector._text = "pool1"
        app._disks_pool_selector._items = ["pool1"]

        dp._on_pool_selector_changed(app._disks_pool_selector, app)

        self.assertEqual(len(app.disks_dataset_store.rows), 1)
        self.assertEqual(app.disks_dataset_store.rows[0][dp.COL_DS_NAME], "pool1/data")

    def test_refresh_logs_invalid_property_message(self):
        dp = _import_disks_page()
        datasets = [_dataset_row("zfstest1", "filesystem")]
        exc = subprocess.CalledProcessError(
            2,
            ["sudo", "zfs", "get", "-H", "-o", "property,value", "ashift", "zfstest1"],
            stderr="bad property list: invalid property 'ashift'\nusage:\n    get ...",
        )
        app = _make_app(
            topologies={"zfstest1": _topology("zfstest1")},
            datasets=datasets,
        )
        app.ctx.zfs_repository.get_properties.side_effect = exc
        app._disks_pool_selector._text = "zfstest1"
        app._disks_pool_selector._items = ["zfstest1"]

        with capture_logs() as logs:
            dp.refresh_disks_page(app)

        self.assertEqual(len(app.disks_dataset_store.rows), 0)
        self.assertTrue(
            any(
                "Could not read properties for zfstest1" in msg
                and "requested an unsupported property" in msg
                and "bug in the requested property list" in msg
                and "bad property list" not in msg
                and "usage:" not in msg
                for msg in logs
            ),
            f"Expected user-friendly log message, got: {logs}",
        )

    def test_refresh_logs_dataset_not_found_message(self):
        dp = _import_disks_page()
        datasets = [_dataset_row("zfstest1", "filesystem")]
        exc = subprocess.CalledProcessError(
            2,
            ["sudo", "zfs", "get", "-H", "-o", "property,value", "recordsize", "zfstest1"],
            stderr="cannot open 'zfstest1': dataset does not exist",
        )
        app = _make_app(
            topologies={"zfstest1": _topology("zfstest1")},
            datasets=datasets,
        )
        app.ctx.zfs_repository.get_properties.side_effect = exc
        app._disks_pool_selector._text = "zfstest1"
        app._disks_pool_selector._items = ["zfstest1"]

        with capture_logs() as logs:
            dp.refresh_disks_page(app)

        self.assertEqual(len(app.disks_dataset_store.rows), 0)
        self.assertTrue(
            any(
                "Could not read properties for zfstest1" in msg
                and "dataset was not found" in msg
                and "dataset does not exist" not in msg
                for msg in logs
            ),
            f"Expected user-friendly log message, got: {logs}",
        )

    def test_dataset_tuning_uses_zfs_get_properties(self):
        dp = _import_disks_page()
        datasets = [_dataset_row("pool1/data", "filesystem")]
        app = _make_app(
            topologies={"pool1": _topology("pool1")},
            datasets=datasets,
            properties={"compression": "lz4"},
        )
        app._disks_pool_selector._text = "pool1"
        app._disks_pool_selector._items = ["pool1"]

        dp.refresh_disks_page(app)

        args = app.ctx.zfs_repository.get_properties.call_args
        requested = args[0][1]
        self.assertIn("recordsize", requested)
        self.assertIn("ashift", ALL_KNOWN_PROPERTIES)
        self.assertNotIn("ashift", requested)


class TestDatasetViewStateRestore(unittest.TestCase):
    """Selection and scroll restoration across dataset-view repopulation."""

    def _repopulate_app(self, dp, datasets, pool="pool1"):
        app = _make_app(
            topologies={pool: _topology(pool)},
            datasets=datasets,
            properties={"compression": "lz4"},
        )
        app._disks_pool_selector._text = pool
        app._disks_pool_selector._items = [pool]
        return app

    def test_repopulate_restores_selection_by_name(self):
        dp = _import_disks_page()
        app = self._repopulate_app(
            dp,
            [_dataset_row("pool1/a", "filesystem"), _dataset_row("pool1/b", "filesystem")],
        )
        dp._repopulate_dataset_tuning_for_selected_pool(app)
        # User selects "pool1/b" (row 1).
        app.disks_dataset_view._selection.paths = [1]
        # Refresh returns the same datasets in a different order.
        app.ctx.zfs_repository.list_datasets.return_value = [
            _dataset_row("pool1/b", "filesystem"),
            _dataset_row("pool1/a", "filesystem"),
        ]

        dp._repopulate_dataset_tuning_for_selected_pool(app)

        selected = app.disks_dataset_view.get_selection().get_selected_rows()[1]
        self.assertEqual(selected, [0])
        self.assertEqual(app.disks_dataset_store.rows[0][dp.COL_DS_NAME], "pool1/b")

    def test_repopulate_restores_scroll_position(self):
        dp = _import_disks_page()
        app = self._repopulate_app(dp, [_dataset_row("pool1/a", "filesystem")])
        adj = FakeAdjustment(value=120.0, upper=1000.0, page_size=100.0)
        app.disks_dataset_view._vadjustment = adj
        dp._repopulate_dataset_tuning_for_selected_pool(app)

        with patch.object(dp, "GLib") as mock_glib:
            mock_glib.idle_add = lambda fn: fn()
            dp._repopulate_dataset_tuning_for_selected_pool(app)

        self.assertEqual(adj.get_value(), 120.0)

    def test_repopulate_clamps_scroll_position(self):
        dp = _import_disks_page()
        app = self._repopulate_app(dp, [_dataset_row("pool1/a", "filesystem")])
        adj = FakeAdjustment(value=500.0, upper=200.0, page_size=100.0)
        app.disks_dataset_view._vadjustment = adj
        dp._repopulate_dataset_tuning_for_selected_pool(app)

        with patch.object(dp, "GLib") as mock_glib:
            mock_glib.idle_add = lambda fn: fn()
            dp._repopulate_dataset_tuning_for_selected_pool(app)

        self.assertEqual(adj.get_value(), 100.0)

    def test_repopulate_after_pool_switch_starts_fresh(self):
        dp = _import_disks_page()
        rows_by_pool = {
            "pool1": [_dataset_row("pool1/a", "filesystem")],
            "pool2": [_dataset_row("pool2/a", "filesystem")],
        }
        app = _make_app(
            topologies={"pool1": _topology("pool1"), "pool2": _topology("pool2")},
            properties={"compression": "lz4"},
        )
        app.ctx.zfs_repository.list_datasets.side_effect = (
            lambda pool=None: rows_by_pool.get(pool, [])
        )
        app._disks_pool_selector._text = "pool1"
        app._disks_pool_selector._items = ["pool1", "pool2"]
        adj = FakeAdjustment(value=80.0, upper=1000.0, page_size=100.0)
        app.disks_dataset_view._vadjustment = adj

        dp._repopulate_dataset_tuning_for_selected_pool(app)
        app.disks_dataset_view._selection.paths = [0]
        adj._value = 40.0

        # Switch to pool2: the previous pool's selection/scroll must not return.
        app._disks_pool_selector._text = "pool2"
        with patch.object(dp, "GLib") as mock_glib:
            mock_glib.idle_add = lambda fn: fn()
            dp._repopulate_dataset_tuning_for_selected_pool(app)

        selected_paths = app.disks_dataset_view.get_selection().get_selected_rows()[1]
        selected_names = {
            app.disks_dataset_store.rows[p][dp.COL_DS_NAME] for p in selected_paths
        }
        self.assertNotIn("pool1/a", selected_names)
        self.assertEqual(adj.get_value(), 40.0)


class TestPoolHelpers(unittest.TestCase):
    """Standalone helper functions in disks_page."""

    def test_pool_has_special_vdev_detects_special(self):
        dp = _import_disks_page()
        topology = _topology(
            "pool1",
            children=[
                TopologyNode(
                    name="special",
                    vdev_type="special",
                    state="ONLINE",
                    read=0,
                    write=0,
                    cksum=0,
                    ashift=12,
                    children=[],
                )
            ],
        )
        self.assertTrue(dp._pool_has_special_vdev(topology))

    def test_pool_has_special_vdev_false_without_special(self):
        dp = _import_disks_page()
        topology = _topology(
            "pool1",
            children=[
                TopologyNode(
                    name="mirror-0",
                    vdev_type="mirror",
                    state="ONLINE",
                    read=0,
                    write=0,
                    cksum=0,
                    ashift=12,
                    children=[],
                )
            ],
        )
        self.assertFalse(dp._pool_has_special_vdev(topology))

    def test_pool_has_special_vdev_none_is_false(self):
        dp = _import_disks_page()
        self.assertFalse(dp._pool_has_special_vdev(None))

    def test_user_friendly_property_error_permission_denied(self):
        dp = _import_disks_page()
        exc = subprocess.CalledProcessError(
            1,
            ["sudo", "zfs", "get", "recordsize", "tank/data"],
            stderr="cannot open 'tank/data': permission denied",
        )
        msg = dp._user_friendly_property_error("tank/data", exc)
        self.assertIn("permission was denied", msg)
        self.assertNotIn("permission denied", msg)

    def test_user_friendly_property_error_unexpected_exception(self):
        dp = _import_disks_page()
        msg = dp._user_friendly_property_error("tank/data", RuntimeError("boom"))
        self.assertIn("unexpected error occurred", msg)
        self.assertIn("boom", msg)


class TestActionDispatch(unittest.TestCase):
    """Action dispatch wiring for the new Disks page buttons."""

    def test_action_dispatch_has_apply_profile_button(self):
        ad = _import_action_dispatch()
        labels = [btn[0] for btn in ad.PAGE_SPECS["disks"]["buttons"]]
        self.assertIn("Apply Profile…", labels)
        self.assertIn("Rewrite Data", labels)
        self.assertIn("Advanced: Manage Profiles…", labels)

        handlers = ad.ACTION_HANDLERS["disks"]
        self.assertIn("Apply Profile…", handlers)
        self.assertIn("Rewrite Data", handlers)
        self.assertIn("Advanced: Manage Profiles…", handlers)


class TestUpdateButtonSensitivity(unittest.TestCase):
    """update_disks_button_sensitivity gates the new dataset buttons."""

    def test_update_sensitivity_apply_profile_requires_selection(self):
        dp = _import_disks_page()
        app = _make_app()
        app._disks_apply_profile_btn = MagicMock()

        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [])
        dp.update_disks_button_sensitivity(app)
        self.assertFalse(app._disks_apply_profile_btn.set_sensitive.call_args[0][0])

        app.disks_dataset_store.append(["pool1/data", "filesystem"] + [""] * 10)
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])
        dp.update_disks_button_sensitivity(app)
        self.assertTrue(app._disks_apply_profile_btn.set_sensitive.call_args[0][0])

    def test_update_sensitivity_rewrite_data_gated_by_zfs_caps(self):
        dp = _import_disks_page()
        app = _make_app()
        app._disks_rewrite_data_btn = MagicMock()
        app.disks_dataset_store.append(["pool1/data", "filesystem"] + [""] * 10)
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

        app.ctx.zfs_caps.supports.return_value = False
        dp.update_disks_button_sensitivity(app)
        self.assertFalse(app._disks_rewrite_data_btn.set_sensitive.call_args[0][0])
        app._disks_rewrite_data_btn.set_tooltip_text.assert_called_with("requires OpenZFS 2.3+")

        app._disks_rewrite_data_btn.reset_mock()
        app.ctx.zfs_caps.supports.return_value = True
        dp.update_disks_button_sensitivity(app)
        self.assertTrue(app._disks_rewrite_data_btn.set_sensitive.call_args[0][0])

    def test_update_sensitivity_rewrite_data_insensitive_for_volume(self):
        dp = _import_disks_page()
        app = _make_app()
        app._disks_rewrite_data_btn = MagicMock()
        app.ctx.zfs_caps.supports.return_value = True
        app.disks_dataset_store.append(["pool1/vol0", "volume"] + [""] * 10)
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

        dp.update_disks_button_sensitivity(app)
        self.assertFalse(app._disks_rewrite_data_btn.set_sensitive.call_args[0][0])
        app._disks_rewrite_data_btn.set_tooltip_text.assert_called_with(
            "Rewrite Data supports filesystem datasets only"
        )

    def test_update_sensitivity_rewrite_data_multiple_filesystems(self):
        dp = _import_disks_page()
        app = _make_app()
        app._disks_rewrite_data_btn = MagicMock()
        app.ctx.zfs_caps.supports.return_value = True
        app.disks_dataset_store.append(["pool1/data", "filesystem"] + [""] * 10)
        app.disks_dataset_store.append(["pool1/data2", "filesystem"] + [""] * 10)
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0, 1])

        dp.update_disks_button_sensitivity(app)
        self.assertTrue(app._disks_rewrite_data_btn.set_sensitive.call_args[0][0])
        app._disks_rewrite_data_btn.set_tooltip_text.assert_called_with("")


class TestApplyProfileDialog(unittest.TestCase):
    """Apply Profile dialog preview and warnings."""

    def _profiles(self):
        return {
            "general": {
                "description": "General-purpose mixed files.",
                "applies_to": ["filesystem", "volume"],
                "properties": {
                    "recordsize": "128K",
                    "compression": "zstd",
                    "atime": "on",
                    "logbias": "latency",
                    "sync": "standard",
                    "primarycache": "all",
                    "special_small_blocks": "0",
                    "volblocksize": "16K",
                },
                "notes": "General purpose.",
            },
            "scratch": {
                "description": "Temporary data that can be lost on power loss.",
                "applies_to": ["filesystem", "volume"],
                "properties": {
                    "compression": "lz4",
                    "sync": "disabled",
                },
                "notes": "Can lose data on power loss.",
            },
            "small-files": {
                "description": "Many small files; benefits from a special vdev.",
                "applies_to": ["filesystem"],
                "properties": {
                    "recordsize": "16K",
                    "special_small_blocks": "4K",
                },
                "notes": "special_small_blocks needs a special vdev.",
            },
        }

    def _dialog_app(self, datasets, properties, topologies=None):
        app = _make_app(
            topologies=topologies or {"pool1": _topology("pool1")},
            datasets=datasets,
            properties=properties,
        )
        app._disks_pool_selector._text = "pool1"
        app.config["workload_profiles"] = self._profiles()
        return app

    def _run_dialog(self, dp, app, datasets, responses):
        """Run the dialog with picker fakes; return (result, dialog, stores, views)."""
        stores = []
        views = []

        def _make_store(*types):
            store = FakePickerListStore(*types)
            stores.append(store)
            return store

        def _make_view(model=None):
            view = FakePickerTreeView(model)
            views.append(view)
            return view

        with (
            patch.object(dp, "create_dialog") as mock_create_dialog,
            patch.object(dp.Gtk, "ListStore", side_effect=_make_store),
            patch.object(dp.Gtk, "TreeView", side_effect=_make_view),
        ):
            mock_dialog = MagicMock()
            mock_dialog.run.side_effect = responses
            mock_create_dialog.return_value = mock_dialog
            result = dp.show_apply_profile_dialog(app, datasets)
        return result, mock_dialog, stores, views

    def test_apply_profile_dialog_builds_preview(self):
        dp = _import_disks_page()

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "custom"}]
        props = {
            "recordsize": "128K",
            "compression": "lz4",
            "atime": "on",
            "logbias": "latency",
            "sync": "standard",
            "primarycache": "all",
            "special_small_blocks": "0",
            "volblocksize": "16K",
            "ashift": "12",
        }
        app = self._dialog_app(datasets, props)

        _result, mock_dialog, _stores, views = self._run_dialog(
            dp, app, datasets, [dp.Gtk.ResponseType.CANCEL]
        )

        content = mock_dialog.get_content_area.return_value
        # The last packed widget is the preview scrolled window.
        self.assertGreaterEqual(content.pack_start.call_count, 2)
        self.assertTrue(views, "Expected the profile picker treeview to be built")

    def test_apply_profile_picker_lists_profiles_with_descriptions(self):
        dp = _import_disks_page()

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "custom"}]
        app = self._dialog_app(datasets, {})

        _result, _dialog, stores, _views = self._run_dialog(
            dp, app, datasets, [dp.Gtk.ResponseType.CANCEL]
        )

        self.assertEqual(
            stores[0].rows,
            [
                ["general", "filesystem, volume", "General-purpose mixed files."],
                ["scratch", "filesystem, volume", "Temporary data that can be lost on power loss."],
                ["small-files", "filesystem", "Many small files; benefits from a special vdev."],
            ],
        )

    def test_apply_profile_picker_preselects_first_dataset_match(self):
        dp = _import_disks_page()

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "small-files"}]
        app = self._dialog_app(datasets, {})

        _result, _dialog, _stores, views = self._run_dialog(
            dp, app, datasets, [dp.Gtk.ResponseType.CANCEL]
        )

        # "small-files" is the third profile in the picker.
        self.assertEqual(views[0].get_selection().selected, 2)

    def test_apply_profile_picker_uses_single_selection(self):
        dp = _import_disks_page()

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "custom"}]
        app = self._dialog_app(datasets, {})

        _result, _dialog, _stores, views = self._run_dialog(
            dp, app, datasets, [dp.Gtk.ResponseType.CANCEL]
        )

        self.assertEqual(views[0].get_selection().mode, dp.Gtk.SelectionMode.SINGLE)

    def test_apply_profile_picker_description_renderer_wraps(self):
        dp = _import_disks_page()
        renderers = []

        def _make_renderer(*_args, **_kwargs):
            renderer = MagicMock()
            renderers.append(renderer)
            return renderer

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "custom"}]
        app = self._dialog_app(datasets, {})

        with patch.object(dp.Gtk, "CellRendererText", side_effect=_make_renderer):
            self._run_dialog(dp, app, datasets, [dp.Gtk.ResponseType.CANCEL])

        properties = [
            call.args for renderer in renderers for call in renderer.set_property.call_args_list
        ]
        self.assertIn(("wrap-mode", dp.Gtk.WrapMode.WORD), properties)
        self.assertIn(("wrap-width", 350), properties)

    def test_apply_profile_warns_for_scratch(self):
        dp = _import_disks_page()

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "scratch"}]
        app = self._dialog_app(datasets, {})

        _result, mock_dialog, _stores, _views = self._run_dialog(
            dp, app, datasets, [dp.Gtk.ResponseType.CANCEL]
        )

        content = mock_dialog.get_content_area.return_value
        warning_label = content.pack_start.call_args_list[0][0][0]
        texts = [str(call.args[0]) for call in warning_label.set_text.call_args_list]
        self.assertTrue(any("Can lose data" in text for text in texts), texts)

    def test_apply_profile_warns_for_small_files_without_special_vdev(self):
        dp = _import_disks_page()

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "small-files"}]
        app = self._dialog_app(datasets, {})
        # Default topology has no special vdev.

        _result, mock_dialog, _stores, _views = self._run_dialog(
            dp, app, datasets, [dp.Gtk.ResponseType.CANCEL]
        )

        content = mock_dialog.get_content_area.return_value
        warning_label = content.pack_start.call_args_list[0][0][0]
        texts = [str(call.args[0]) for call in warning_label.set_text.call_args_list]
        self.assertTrue(any("special_small_blocks" in text for text in texts), texts)

    def test_apply_profile_dialog_returns_cancel_when_no_profiles(self):
        dp = _import_disks_page()
        app = self._dialog_app([{"name": "pool1/data", "type": "filesystem"}], {})
        app.config["workload_profiles"] = {}

        with capture_logs() as logs:
            response, name, profile = dp.show_apply_profile_dialog(app, [])

        self.assertEqual(response, dp.Gtk.ResponseType.CANCEL)
        self.assertIsNone(name)
        self.assertIsNone(profile)
        self.assertTrue(
            any("No workload profiles configured" in line for line in logs),
            logs,
        )

    def test_apply_profile_requires_confirm_for_warning_profile(self):
        dp = _import_disks_page()
        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "scratch"}]
        app = self._dialog_app(datasets, {})

        confirm_states = [False, True]

        def _make_check(*_args, **_kwargs):
            btn = MagicMock()
            btn.get_active.side_effect = lambda: confirm_states.pop(0)
            return btn

        with patch.object(dp.Gtk, "CheckButton", side_effect=_make_check):
            _result, mock_dialog, _stores, _views = self._run_dialog(
                dp, app, datasets, [dp.Gtk.ResponseType.OK, dp.Gtk.ResponseType.OK]
            )

        # The dialog should have been run twice: once without confirm, once with.
        self.assertEqual(mock_dialog.run.call_count, 2)


class TestApplyProfileHandler(unittest.TestCase):
    """Apply Profile handler execution."""

    def _profiles(self):
        return {
            "general": {
                "applies_to": ["filesystem", "volume"],
                "properties": {
                    "compression": "zstd",
                },
                "notes": "General purpose.",
            },
        }

    def test_apply_profile_handler_no_selection_warns(self):
        dp = _import_disks_page()
        app = _make_app()
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [])

        with (
            patch.object(dp, "show_apply_profile_dialog") as mock_dialog,
            capture_logs() as logs,
        ):
            dp.on_disks_apply_profile(app)

        mock_dialog.assert_not_called()
        self.assertTrue(
            any("Select at least one dataset" in line for line in logs),
            logs,
        )

    def test_apply_profile_handler_runs_runner_with_steps(self):
        dp = _import_disks_page()

        props = {
            "recordsize": "128K",
            "compression": "lz4",
            "atime": "on",
            "logbias": "latency",
            "sync": "standard",
            "primarycache": "all",
            "special_small_blocks": "0",
            "volblocksize": "16K",
            "ashift": "12",
        }
        app = _make_app(datasets=[_dataset_row("pool1/data", "filesystem")], properties=props)
        app.config["workload_profiles"] = self._profiles()
        app.disks_dataset_store = FakeListStoreIterable(
            [
                ["pool1/data", "filesystem", "", "", "lz4", "", "", "standard", "", "", "", "custom"],
            ]
        )
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

        profile = self._profiles()["general"]
        with (
            patch.object(
                dp,
                "show_apply_profile_dialog",
                return_value=(dp.Gtk.ResponseType.OK, "general", profile),
            ),
            patch.object(dp, "zlm") as mock_zlm,
        ):
            mock_zlm.acquire_multiple.return_value = ["lock1"]

            with capture_logs():
                dp.on_disks_apply_profile(app)

            mock_zlm.acquire_multiple.assert_called_once_with("w", ["pool1/data"])
            self.assertEqual(len(app.dataset_runner.steps), 1)
            self.assertEqual(
                app.dataset_runner.steps[0].command,
                ["bash", "-c", "zfs set compression=zstd pool1/data"],
            )
            # The step description comes from the plan entry, not from
            # re-parsing the command string.
            self.assertEqual(
                app.dataset_runner.steps[0].description,
                "Set compression=zstd on pool1/data",
            )

            app.dataset_runner.finish(cancelled=False)
            mock_zlm.release.assert_called_once_with("lock1")

    def test_apply_profile_handler_skips_when_nothing_to_apply(self):
        dp = _import_disks_page()
        # All applicable "general" properties already match.
        props = {
            "recordsize": "128K",
            "compression": "zstd",
            "atime": "off",
            "logbias": "latency",
            "sync": "standard",
            "primarycache": "all",
            "special_small_blocks": "0",
        }
        app = _make_app(datasets=[_dataset_row("pool1/data", "filesystem")], properties=props)
        app.config["workload_profiles"] = self._profiles()
        app.disks_dataset_store = FakeListStoreIterable(
            [
                ["pool1/data", "filesystem", "", "", "zstd", "", "", "standard", "", "", "", "general"],
            ]
        )
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

        with (
            patch.object(
                dp,
                "show_apply_profile_dialog",
                return_value=(dp.Gtk.ResponseType.OK, "general", self._profiles()["general"]),
            ),
            patch.object(dp.Gtk, "MessageDialog") as mock_message_dialog,
            capture_logs(),
        ):
            dp.on_disks_apply_profile(app)

        self.assertFalse(app.dataset_runner.running)
        mock_message_dialog.assert_called_once()

    def test_apply_profile_handler_warns_when_runner_busy(self):
        dp = _import_disks_page()
        app = _make_app(datasets=[_dataset_row("pool1/data", "filesystem")])
        app.config["workload_profiles"] = self._profiles()
        app.disks_dataset_store = FakeListStoreIterable(
            [
                ["pool1/data", "filesystem", "", "", "lz4", "", "", "standard", "", "", "", "custom"],
            ]
        )
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])
        app.dataset_runner.running = True

        with (
            patch.object(
                dp,
                "show_apply_profile_dialog",
                return_value=(dp.Gtk.ResponseType.OK, "general", self._profiles()["general"]),
            ),
            capture_logs() as logs,
        ):
            dp.on_disks_apply_profile(app)

        self.assertFalse(app.dataset_runner.steps)
        self.assertTrue(
            any("dataset action is already running" in line for line in logs),
            logs,
        )


class _FakeEntry:
    """Entry stand-in that returns a value fixed at creation time."""

    def __init__(self, values, keys, idx):
        self._values = values
        self._keys = keys
        self._idx = idx

    def get_text(self):
        return str(self._values.get(self._keys[self._idx], ""))

    def set_text(self, text):
        pass

    def set_sensitive(self, value):
        pass

    def set_editable(self, value):
        pass

    def set_can_focus(self, value):
        pass

    def set_placeholder_text(self, text):
        pass


class _FakeCheckButton:
    """CheckButton stand-in that returns a state fixed at creation time."""

    def __init__(self, values, keys, idx):
        self._values = values
        self._keys = keys
        self._idx = idx

    def get_active(self):
        return bool(self._values.get(self._keys[self._idx], False))

    def set_active(self, value):
        pass


class _FakeProfileEditor:
    """Controlled stand-in for the Add/Edit Profile dialog widgets."""

    ENTRY_KEYS: ClassVar[list[str]] = [
        "name",
        "description",
        "recordsize",
        "compression",
        "atime",
        "logbias",
        "sync",
        "primarycache",
        "special_small_blocks",
        "volblocksize",
        "ashift",
    ]

    CHECK_KEYS: ClassVar[list[str]] = ["filesystem", "volume"]

    def __init__(self, dp, values, dialog_responses):
        self.dp = dp
        self.values = values
        self.dialog_responses = list(dialog_responses)
        self._entry_counter = [0]
        self._check_counter = [0]
        self._dialog_run_idx = 0
        self._patches = []

    def _make_entry(self, *args, **kwargs):
        idx = self._entry_counter[0]
        self._entry_counter[0] += 1
        return _FakeEntry(self.values, self.ENTRY_KEYS, idx)

    def _make_check(self, *args, **kwargs):
        idx = self._check_counter[0]
        self._check_counter[0] += 1
        return _FakeCheckButton(self.values, self.CHECK_KEYS, idx)

    def _make_text_buffer(self, *args, **kwargs):
        values = self.values

        class _Buf:
            def get_text(self, _start, _end, _hidden):
                return str(values.get("notes", ""))

            def set_text(self, text):
                pass

            def get_start_iter(self):
                return None

            def get_end_iter(self):
                return None

        return _Buf()

    def _make_dialog(self, *args, **kwargs):
        responses = self.dialog_responses
        idx = [0]

        def _run():
            resp = responses[idx[0]]
            idx[0] += 1
            return resp

        dialog = MagicMock()
        dialog.run.side_effect = _run
        return dialog

    def __enter__(self):
        self._patches = [
            patch.object(self.dp.Gtk, "Entry", side_effect=self._make_entry),
            patch.object(self.dp.Gtk, "CheckButton", side_effect=self._make_check),
            patch.object(self.dp.Gtk, "TextBuffer", side_effect=self._make_text_buffer),
            patch.object(self.dp, "create_dialog", side_effect=self._make_dialog),
            patch.object(
                self.dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=self.dp.Gtk.ResponseType.OK)),
            ),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in reversed(self._patches):
            p.stop()
        return False


def _make_tree_view(store, paths):
    """Return a TreeView mock whose selection reports *paths* against *store*."""
    view = MagicMock()
    selection = MagicMock()
    selection.get_selected_rows.return_value = (store, paths)
    view.get_selection.return_value = selection
    return view


class TestBuildRewriteCommand(unittest.TestCase):
    """_build_rewrite_command pins the zfs rewrite flags and mount handling."""

    def test_rewrite_flags_and_mountpoint(self):
        dp = _import_disks_page()
        script = dp._build_rewrite_command("pool1/data", "/pool1/data")
        self.assertIn("zfs rewrite -P -r -x -v /pool1/data", script)

    def test_rewrite_flags_adjacent_and_mount_quoted(self):
        # -P -r -x -v stay adjacent so the cross-mount guard (-x) cannot be
        # dropped accidentally; paths with spaces must be quoted.
        dp = _import_disks_page()
        script = dp._build_rewrite_command("tank/a b", "/mnt/a b")
        self.assertIn("zfs rewrite -P -r -x -v '/mnt/a b'", script)
        self.assertIn("zfs get -H -o value mounted 'tank/a b'", script)

    def test_mounts_only_when_not_already_mounted(self):
        dp = _import_disks_page()
        script = dp._build_rewrite_command("pool1/data", "/pool1/data")
        self.assertIn('if [[ "$mounted_before" != "yes" ]]', script)
        self.assertIn("zfs mount pool1/data", script)

    def test_unmounts_only_when_it_mounted_and_returns_rewrite_rc(self):
        dp = _import_disks_page()
        script = dp._build_rewrite_command("pool1/data", "/pool1/data")
        self.assertIn('if [[ "$mounted_by_us" == "1" ]]', script)
        self.assertIn("zfs unmount pool1/data", script)
        self.assertIn("exit $rewrite_rc", script)


class TestRewriteData(unittest.TestCase):
    """Rewrite Data handler tests."""

    def _select(self, app, name, ds_type):
        app.disks_dataset_store = FakeListStoreIterable(
            [[name, ds_type] + [""] * 10]
        )
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

    def _supported_app(self, name="pool1/data", ds_type="filesystem"):
        app = _make_app(datasets=[_dataset_row(name, ds_type)])
        app.ctx.zfs_caps.supports.return_value = True
        app.ctx.zfs_caps.supports_pool_feature.return_value = True
        app.ctx.zfs_repository.get_properties.return_value = {
            "mountpoint": f"/{name}",
        }
        self._select(app, name, ds_type)
        return app

    def test_rewrite_data_gated_without_selection(self):
        dp = _import_disks_page()
        app = _make_app()
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [])

        with capture_logs() as logs:
            dp.on_disks_rewrite_data(app)

        self.assertFalse(app.dataset_runner.running)
        self.assertTrue(
            any("Select at least one dataset" in line for line in logs),
            logs,
        )

    def test_rewrite_data_runs_runner_when_supported(self):
        dp = _import_disks_page()
        app = self._supported_app()

        with (
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch.object(dp, "zlm") as mock_zlm,
            patch("feature_config.save_config"),
        ):
            mock_zlm.acquire_multiple.return_value = ["/lock/rewrite"]

            with capture_logs():
                dp.on_disks_rewrite_data(app)

            mock_zlm.acquire_multiple.assert_called_once_with("w", ["pool1/data"])
            self.assertEqual(len(app.dataset_runner.steps), 1)
            command = app.dataset_runner.steps[0].command
            self.assertEqual(command[0:2], ["bash", "-c"])
            self.assertIn("zfs rewrite -P -r -x -v /pool1/data", command[2])

            app.dataset_runner.finish(cancelled=False)
            mock_zlm.release.assert_called_once_with("/lock/rewrite")

    def test_rewrite_data_releases_lock_on_cancel(self):
        dp = _import_disks_page()
        app = self._supported_app()

        with (
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch.object(dp, "zlm") as mock_zlm,
            patch("feature_config.save_config"),
        ):
            mock_zlm.acquire_multiple.return_value = ["/lock/rewrite"]

            with capture_logs() as logs:
                dp.on_disks_rewrite_data(app)
                app.dataset_runner.finish(cancelled=True)

            mock_zlm.release.assert_called_once_with("/lock/rewrite")
            self.assertTrue(
                any("Rewrite Data cancelled" in line for line in logs),
                logs,
            )

    def test_rewrite_data_logs_failed_on_nonzero_rc(self):
        dp = _import_disks_page()
        app = self._supported_app()

        with (
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch.object(dp, "zlm") as mock_zlm,
            patch("feature_config.save_config"),
        ):
            mock_zlm.acquire_multiple.return_value = ["/lock/rewrite"]

            with capture_logs() as logs:
                dp.on_disks_rewrite_data(app)
                app.dataset_runner.finish(cancelled=False, rc=2)

            mock_zlm.release.assert_called_once_with("/lock/rewrite")
            self.assertTrue(
                any("Rewrite Data failed for pool1/data (rc=2)" in line for line in logs),
                logs,
            )
            self.assertFalse(
                any("Rewrite Data complete" in line for line in logs),
                logs,
            )

    def test_rewrite_data_logs_complete_on_rc_zero(self):
        dp = _import_disks_page()
        app = self._supported_app()

        with (
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch.object(dp, "zlm") as mock_zlm,
            patch("feature_config.save_config"),
        ):
            mock_zlm.acquire_multiple.return_value = ["/lock/rewrite"]

            with capture_logs() as logs:
                dp.on_disks_rewrite_data(app)
                app.dataset_runner.finish(cancelled=False, rc=0)

            mock_zlm.release.assert_called_once_with("/lock/rewrite")
            self.assertTrue(
                any("Rewrite Data complete for pool1/data" in line for line in logs),
                logs,
            )

    def test_rewrite_data_noop_when_unsupported(self):
        dp = _import_disks_page()
        app = self._supported_app()
        app.ctx.zfs_caps.supports.return_value = False

        with capture_logs() as logs:
            dp.on_disks_rewrite_data(app)

        self.assertFalse(app.dataset_runner.running)
        self.assertTrue(
            any("Rewrite Data requires OpenZFS 2.3+" in line for line in logs),
            logs,
        )

    def test_rewrite_data_rejects_volume(self):
        dp = _import_disks_page()
        app = self._supported_app("pool1/vol0", "volume")

        with capture_logs() as logs:
            dp.on_disks_rewrite_data(app)

        self.assertFalse(app.dataset_runner.running)
        self.assertTrue(
            any("filesystem datasets only" in line for line in logs),
            logs,
        )

    def test_rewrite_data_rejects_unmountable_mountpoint(self):
        dp = _import_disks_page()
        app = self._supported_app()
        app.ctx.zfs_repository.get_properties.return_value = {"mountpoint": "none"}

        with capture_logs() as logs:
            dp.on_disks_rewrite_data(app)

        self.assertFalse(app.dataset_runner.running)
        self.assertTrue(
            any("mountpoint is 'none'" in line for line in logs),
            logs,
        )

    def test_rewrite_data_requires_physical_rewrite_feature(self):
        dp = _import_disks_page()
        app = self._supported_app()
        app.ctx.zfs_caps.supports_pool_feature.return_value = False

        with capture_logs() as logs:
            dp.on_disks_rewrite_data(app)

        self.assertFalse(app.dataset_runner.running)
        self.assertTrue(
            any("physical_rewrite pool feature" in line for line in logs),
            logs,
        )
        app.ctx.zfs_caps.supports_pool_feature.assert_called_once_with(
            "pool1", "physical_rewrite"
        )

    def _select_rows(self, app, rows):
        app.disks_dataset_store = FakeListStoreIterable(
            [[name, ds_type] + [""] * 10 for name, ds_type in rows]
        )
        app.disks_dataset_view = FakeTreeView(
            app.disks_dataset_store, list(range(len(rows)))
        )

    def _supported_multi_app(self):
        app = _make_app(
            datasets=[
                _dataset_row("pool1/data", "filesystem"),
                _dataset_row("pool1/data2", "filesystem"),
            ]
        )
        app.ctx.zfs_caps.supports.return_value = True
        app.ctx.zfs_caps.supports_pool_feature.return_value = True
        app.ctx.zfs_repository.get_properties.return_value = {
            "mountpoint": "/pool1/data",
        }
        self._select_rows(
            app, [("pool1/data", "filesystem"), ("pool1/data2", "filesystem")]
        )
        return app

    def test_rewrite_data_multiple_datasets_runs_sequential_steps(self):
        dp = _import_disks_page()
        app = self._supported_multi_app()

        with (
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch.object(dp, "zlm") as mock_zlm,
            patch("feature_config.save_config"),
        ):
            mock_zlm.acquire_multiple.return_value = ["/lock/1", "/lock/2"]

            with capture_logs():
                dp.on_disks_rewrite_data(app)

            mock_zlm.acquire_multiple.assert_called_once_with(
                "w", ["pool1/data", "pool1/data2"]
            )
            self.assertEqual(len(app.dataset_runner.steps), 2)
            first, second = app.dataset_runner.steps
            self.assertEqual(first.description, "Rewrite data on pool1/data")
            self.assertEqual(second.description, "Rewrite data on pool1/data2")
            self.assertIn("zfs rewrite -P -r -x -v /pool1/data", first.command[2])

            app.dataset_runner.finish(cancelled=False)
            self.assertEqual(mock_zlm.release.call_count, 2)
            mock_zlm.release.assert_any_call("/lock/1")
            mock_zlm.release.assert_any_call("/lock/2")

    def test_rewrite_data_rejects_mixed_filesystem_volume_selection(self):
        dp = _import_disks_page()
        app = self._supported_multi_app()
        self._select_rows(
            app, [("pool1/data", "filesystem"), ("pool1/vol0", "volume")]
        )

        with patch.object(dp, "zlm") as mock_zlm, capture_logs() as logs:
            dp.on_disks_rewrite_data(app)

        self.assertFalse(app.dataset_runner.running)
        mock_zlm.acquire_multiple.assert_not_called()
        self.assertTrue(
            any("filesystem datasets only" in line and "pool1/vol0" in line for line in logs),
            logs,
        )

    def test_rewrite_data_multiple_datasets_confirmation_lists_names(self):
        dp = _import_disks_page()
        app = self._supported_multi_app()

        with patch.object(dp.Gtk, "MessageDialog") as mock_dialog:
            mock_dialog.return_value.run.return_value = dp.Gtk.ResponseType.NO
            dp.on_disks_rewrite_data(app)

        kwargs = mock_dialog.call_args.kwargs
        self.assertIn("2 datasets", kwargs["text"])
        secondary = mock_dialog.return_value.format_secondary_text.call_args[0][0]
        self.assertIn("pool1/data", secondary)
        self.assertIn("pool1/data2", secondary)


class TestManageProfilesDialog(unittest.TestCase):
    """Manage Workload Profiles dialog tests."""

    def _profiles(self):
        return {
            "general": {
                "description": "Balanced settings.",
                "applies_to": ["filesystem", "volume"],
                "properties": {"compression": "zstd"},
                "notes": "",
            },
        }

    def _dialog_app(self):
        app = _make_app()
        app.config["workload_profiles"] = self._profiles()
        return app

    def test_manage_profiles_dialog_lists_profiles(self):
        dp = _import_disks_page()
        app = self._dialog_app()
        store = MagicMock()

        with (
            patch.object(
                dp,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(dp.Gtk, "ListStore", return_value=store),
        ):
            dp.show_manage_profiles_dialog(app)

            self.assertTrue(store.append.called)
            appended = [call.args[0] for call in store.append.call_args_list]
            self.assertIn(["general", "filesystem, volume", "Balanced settings."], appended)

    def test_manage_profiles_add_profile(self):
        dp = _import_disks_page()
        app = self._dialog_app()
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        with (
            patch.object(
                dp,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(dp.Gtk, "Button", side_effect=make_button),
            patch("feature_config.save_config"),
        ):
            dp.show_manage_profiles_dialog(app)

        add_btn = buttons[0]
        add_handler = add_btn.connect.call_args[0][1]

        with patch.object(dp, "show_profile_editor_dialog") as mock_editor:
            add_handler(add_btn)
            mock_editor.assert_called_once_with(app)

    def test_manage_profiles_edit_profile(self):
        dp = _import_disks_page()
        app = self._dialog_app()
        app.config["workload_profiles"]["general"]["description"] = "Updated"
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        # Capture the store so we can set the selection to "general".
        store = GtkListStoreAdapter([["general", "filesystem, volume", "Updated"]])
        view = _make_tree_view(store, [0])

        with (
            patch.object(
                dp,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(dp.Gtk, "Button", side_effect=make_button),
            patch.object(dp.Gtk, "ListStore", return_value=store),
            patch.object(dp.Gtk, "TreeView", return_value=view),
            patch("feature_config.save_config"),
        ):
            dp.show_manage_profiles_dialog(app)

            edit_btn = buttons[1]
            edit_handler = edit_btn.connect.call_args[0][1]

            with patch.object(dp, "show_profile_editor_dialog") as mock_editor:
                edit_handler(edit_btn)
                mock_editor.assert_called_once_with(app, "general")

    def test_manage_profiles_delete_profile(self):
        dp = _import_disks_page()
        app = self._dialog_app()
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        store = GtkListStoreAdapter([["general", "filesystem, volume", "Balanced settings."]])
        view = _make_tree_view(store, [0])

        with (
            patch.object(
                dp,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(dp.Gtk, "Button", side_effect=make_button),
            patch.object(dp.Gtk, "ListStore", return_value=store),
            patch.object(dp.Gtk, "TreeView", return_value=view),
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch("feature_config.save_config"),
        ):
            dp.show_manage_profiles_dialog(app)

            delete_btn = buttons[2]
            delete_handler = delete_btn.connect.call_args[0][1]

            with patch.object(dp, "delete_workload_profile", return_value=True) as mock_delete:
                delete_handler(delete_btn)
                mock_delete.assert_called_once_with(app.config, "general")

    def test_manage_profiles_reset_defaults(self):
        dp = _import_disks_page()
        app = self._dialog_app()
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        with (
            patch.object(
                dp,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(dp.Gtk, "Button", side_effect=make_button),
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch("feature_config.save_config"),
        ):
            dp.show_manage_profiles_dialog(app)

            reset_btn = buttons[3]
            reset_handler = reset_btn.connect.call_args[0][1]

            with patch.object(dp, "reset_workload_profiles") as mock_reset:
                reset_handler(reset_btn)
                mock_reset.assert_called_once_with(app.config)


class GtkListStoreAdapter:
    """ListStore stand-in that records rows and supports view selection."""

    def __init__(self, rows=None):
        self.rows = rows or []

    def clear(self):
        self.rows = []

    def append(self, row):
        self.rows.append(list(row))

    def get_iter(self, path):
        return path if isinstance(path, int) else 0

    def get_value(self, it, col):
        return self.rows[it][col]


class TestProfileEditorDialog(unittest.TestCase):
    """Add/Edit Profile dialog tests."""

    def _app(self):
        app = _make_app()
        app.config["workload_profiles"] = {
            "general": {
                "description": "Balanced.",
                "applies_to": ["filesystem", "volume"],
                "properties": {"compression": "zstd"},
                "notes": "",
            },
        }
        return app

    def test_manage_profiles_add_profile(self):
        dp = _import_disks_page()
        app = self._app()

        values = {
            "name": "media",
            "description": "Large sequential files.",
            "filesystem": True,
            "volume": False,
            "recordsize": "1M",
            "compression": "zstd-3",
            "atime": "off",
            "logbias": "throughput",
            "sync": "standard",
            "primarycache": "all",
            "special_small_blocks": "0",
            "volblocksize": "",
            "ashift": "",
            "notes": "Big files.",
        }

        with (
            _FakeProfileEditor(dp, values, [dp.Gtk.ResponseType.OK]),
            patch("feature_config.save_config"),
        ):
            dp.show_profile_editor_dialog(app)

        profiles = app.config["workload_profiles"]
        self.assertIn("media", profiles)
        self.assertEqual(profiles["media"]["description"], "Large sequential files.")
        self.assertEqual(profiles["media"]["applies_to"], ["filesystem"])
        self.assertEqual(profiles["media"]["properties"]["recordsize"], "1M")
        self.assertEqual(profiles["media"]["notes"], "Big files.")

    def test_manage_profiles_edit_profile(self):
        dp = _import_disks_page()
        app = self._app()

        values = {
            "name": "general",
            "description": "Updated description.",
            "filesystem": True,
            "volume": True,
            "recordsize": "256K",
            "compression": "lz4",
            "atime": "off",
            "logbias": "latency",
            "sync": "standard",
            "primarycache": "all",
            "special_small_blocks": "0",
            "volblocksize": "32K",
            "ashift": "",
            "notes": "Updated notes.",
        }

        with (
            _FakeProfileEditor(dp, values, [dp.Gtk.ResponseType.OK]),
            patch("feature_config.save_config"),
        ):
            dp.show_profile_editor_dialog(app, "general")

        profiles = app.config["workload_profiles"]
        self.assertEqual(profiles["general"]["description"], "Updated description.")
        self.assertEqual(profiles["general"]["properties"]["compression"], "lz4")
        self.assertEqual(profiles["general"]["properties"]["volblocksize"], "32K")
        self.assertNotIn("ashift", profiles["general"]["properties"])

    def test_manage_profiles_validation(self):
        dp = _import_disks_page()
        app = self._app()

        with patch("feature_config.save_config") as mock_save:
            # Empty name
            values = {"name": "", "filesystem": True, "recordsize": "128K"}
            with _FakeProfileEditor(
                dp, values, [dp.Gtk.ResponseType.OK, dp.Gtk.ResponseType.CANCEL]
            ):
                dp.show_profile_editor_dialog(app)
            mock_save.assert_not_called()

            # Duplicate name (case-insensitive)
            values = {"name": "GENERAL", "filesystem": True, "recordsize": "128K"}
            with _FakeProfileEditor(
                dp, values, [dp.Gtk.ResponseType.OK, dp.Gtk.ResponseType.CANCEL]
            ):
                dp.show_profile_editor_dialog(app)
            mock_save.assert_not_called()

            # Neither filesystem nor volume
            values = {"name": "orphan", "filesystem": False, "volume": False, "recordsize": "128K"}
            with _FakeProfileEditor(
                dp, values, [dp.Gtk.ResponseType.OK, dp.Gtk.ResponseType.CANCEL]
            ):
                dp.show_profile_editor_dialog(app)
            mock_save.assert_not_called()


class TestActionDispatchWiring(unittest.TestCase):
    """Action dispatch wiring completeness."""

    def test_disks_action_dispatch_wiring_complete(self):
        ad = _import_action_dispatch()
        handlers = ad.ACTION_HANDLERS["disks"]
        expected = {
            "Apply Profile…": "on_disks_apply_profile",
            "Rewrite Data": "on_disks_rewrite_data",
            "Advanced: Manage Profiles…": "on_disks_manage_profiles",
        }
        for label, expected_name in expected.items():
            self.assertIn(label, handlers)
            self.assertEqual(handlers[label].__name__, expected_name)


if __name__ == "__main__":
    unittest.main()
