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
    """TreeSelection stand-in that reports a configurable path list."""

    def __init__(self, model, paths=None):
        self.model = model
        self.paths = paths or []

    def get_selected_rows(self):
        return (self.model, self.paths)

    def select_path(self, path):
        pass


class FakeTreeView:
    """TreeView stand-in with a FakeTreeSelection."""

    def __init__(self, model=None, paths=None):
        self.model = model
        self._selection = FakeTreeSelection(model, paths)

    def get_selection(self):
        return self._selection


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

    def finish(self, cancelled=False):
        self.running = False
        if self._on_complete:
            self._on_complete(cancelled=cancelled)


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
        self.assertEqual(dp.COL_DS_PROFILE_MATCH, 10)

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

        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])
        dp.update_disks_button_sensitivity(app)
        self.assertTrue(app._disks_apply_profile_btn.set_sensitive.call_args[0][0])

    def test_update_sensitivity_rewrite_data_gated_by_zfs_caps(self):
        dp = _import_disks_page()
        app = _make_app()
        app._disks_rewrite_data_btn = MagicMock()
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

        app.ctx.zfs_caps.supports.return_value = False
        dp.update_disks_button_sensitivity(app)
        self.assertFalse(app._disks_rewrite_data_btn.set_sensitive.call_args[0][0])
        app._disks_rewrite_data_btn.set_tooltip_text.assert_called_with("requires OpenZFS 2.3+")

        app._disks_rewrite_data_btn.reset_mock()
        app.ctx.zfs_caps.supports.return_value = True
        dp.update_disks_button_sensitivity(app)
        self.assertTrue(app._disks_rewrite_data_btn.set_sensitive.call_args[0][0])


class TestApplyProfileDialog(unittest.TestCase):
    """Apply Profile dialog preview and warnings."""

    def _profiles(self):
        return {
            "general": {
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
                "applies_to": ["filesystem", "volume"],
                "properties": {
                    "compression": "lz4",
                    "sync": "disabled",
                },
                "notes": "Can lose data on power loss.",
            },
            "small-files": {
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

        with patch.object(dp, "create_dialog") as mock_create_dialog:
            mock_dialog = MagicMock()
            mock_dialog.run.return_value = dp.Gtk.ResponseType.CANCEL
            mock_create_dialog.return_value = mock_dialog

            dp.show_apply_profile_dialog(app, datasets)

            content = mock_dialog.get_content_area.return_value
            # The first packed widget is the warning label; the last is the preview scrolled window.
            self.assertGreaterEqual(content.pack_start.call_count, 2)

    def test_apply_profile_warns_for_scratch(self):
        dp = _import_disks_page()

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "scratch"}]
        app = self._dialog_app(datasets, {})
        app.config["workload_profiles"] = self._profiles()

        with patch.object(dp, "create_dialog") as mock_create_dialog:
            mock_dialog = MagicMock()
            mock_dialog.run.return_value = dp.Gtk.ResponseType.CANCEL
            mock_create_dialog.return_value = mock_dialog

            dp.show_apply_profile_dialog(app, datasets)

            content = mock_dialog.get_content_area.return_value
            warning_label = content.pack_start.call_args_list[0][0][0]
            texts = [str(call.args[0]) for call in warning_label.set_text.call_args_list]
            self.assertTrue(any("Can lose data" in text for text in texts), texts)

    def test_apply_profile_warns_for_small_files_without_special_vdev(self):
        dp = _import_disks_page()

        datasets = [{"name": "pool1/data", "type": "filesystem", "profile_match": "small-files"}]
        app = self._dialog_app(datasets, {})
        app.config["workload_profiles"] = self._profiles()
        # Default topology has no special vdev.

        with patch.object(dp, "create_dialog") as mock_create_dialog:
            mock_dialog = MagicMock()
            mock_dialog.run.return_value = dp.Gtk.ResponseType.CANCEL
            mock_create_dialog.return_value = mock_dialog

            dp.show_apply_profile_dialog(app, datasets)

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
        app.config["workload_profiles"] = self._profiles()

        with (
            patch.object(dp, "create_dialog") as mock_create_dialog,
            patch.object(dp.Gtk, "CheckButton") as mock_check_button,
            patch.object(dp.Gtk, "ComboBoxText") as mock_combo,
        ):
            confirm_states = [False, True]

            def _make_check(*_args, **_kwargs):
                btn = MagicMock()
                btn.get_active.side_effect = lambda: confirm_states.pop(0)
                return btn

            def _make_combo(*_args, **_kwargs):
                combo = MagicMock()
                combo.get_active_text.return_value = "scratch"
                return combo

            mock_check_button.side_effect = _make_check
            mock_combo.side_effect = _make_combo

            mock_dialog = MagicMock()
            mock_dialog.run.return_value = dp.Gtk.ResponseType.OK
            mock_create_dialog.return_value = mock_dialog

            dp.show_apply_profile_dialog(app, datasets)

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
                ["pool1/data", "filesystem", "", "lz4", "", "", "standard", "", "", "", "custom"],
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
                ["pool1/data", "filesystem", "", "zstd", "", "", "standard", "", "", "", "general"],
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
                ["pool1/data", "filesystem", "", "lz4", "", "", "standard", "", "", "", "custom"],
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


class TestRewriteData(unittest.TestCase):
    """Rewrite Data handler tests."""

    def test_rewrite_data_gated_without_selection(self):
        dp = _import_disks_page()
        app = _make_app()
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [])

        with capture_logs() as logs:
            dp.on_disks_rewrite_data(app)

        self.assertFalse(app.dataset_runner.running)
        self.assertTrue(
            any("Select exactly one dataset" in line for line in logs),
            logs,
        )

    def test_rewrite_data_runs_runner_when_supported(self):
        dp = _import_disks_page()

        app = _make_app(datasets=[_dataset_row("pool1/data", "filesystem")])
        app.ctx.zfs_caps.supports.return_value = True
        app.disks_dataset_store = FakeListStoreIterable(
            [
                ["pool1/data", "filesystem", "", "", "", "", "", "", "", "", ""],
            ]
        )
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

        with (
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch.object(dp, "zlm") as mock_zlm,
            patch("feature_config.save_config"),
        ):
            mock_zlm.acquire.return_value = "/lock/rewrite"

            with capture_logs():
                dp.on_disks_rewrite_data(app)

            mock_zlm.acquire.assert_called_once_with(
                "pool1/data", "w", "Rewrite data on pool1/data"
            )
            self.assertEqual(len(app.dataset_runner.steps), 1)
            self.assertEqual(
                app.dataset_runner.steps[0].command,
                ["bash", "-c", "zfs rewrite pool1/data"],
            )

            app.dataset_runner.finish(cancelled=False)
            mock_zlm.release.assert_called_once_with("/lock/rewrite")

    def test_rewrite_data_releases_lock_on_cancel(self):
        dp = _import_disks_page()

        app = _make_app(datasets=[_dataset_row("pool1/data", "filesystem")])
        app.ctx.zfs_caps.supports.return_value = True
        app.disks_dataset_store = FakeListStoreIterable(
            [
                ["pool1/data", "filesystem", "", "", "", "", "", "", "", "", ""],
            ]
        )
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

        with (
            patch.object(
                dp.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=dp.Gtk.ResponseType.YES)),
            ),
            patch.object(dp, "zlm") as mock_zlm,
            patch("feature_config.save_config"),
        ):
            mock_zlm.acquire.return_value = "/lock/rewrite"

            with capture_logs() as logs:
                dp.on_disks_rewrite_data(app)
                app.dataset_runner.finish(cancelled=True)

            mock_zlm.release.assert_called_once_with("/lock/rewrite")
            self.assertTrue(
                any("Rewrite Data cancelled" in line for line in logs),
                logs,
            )

    def test_rewrite_data_noop_when_unsupported(self):
        dp = _import_disks_page()

        app = _make_app(datasets=[_dataset_row("pool1/data", "filesystem")])
        app.ctx.zfs_caps.supports.return_value = False
        app.disks_dataset_store = FakeListStoreIterable(
            [
                ["pool1/data", "filesystem", "", "", "", "", "", "", "", "", ""],
            ]
        )
        app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [0])

        with capture_logs() as logs:
            dp.on_disks_rewrite_data(app)

        self.assertFalse(app.dataset_runner.running)
        self.assertTrue(
            any("Rewrite Data requires OpenZFS 2.3+" in line for line in logs),
            logs,
        )


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
