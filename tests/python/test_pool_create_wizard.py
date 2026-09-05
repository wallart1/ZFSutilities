"""Tests for pool_create_wizard — create-pool wizard UI and handler."""

import contextlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from disk_repository import DiskInfo
from pool_create import disk_eligibility, pool_filesystem_options
from test_support import capture_logs, mock_gtk, temp_lock_dir
from zfs_repository import TopologyNode

TB = 10**12


def _import_disks_page():
    """Import disks_page under a fresh mocked GTK context."""
    sys.modules.pop("disks_page", None)
    with mock_gtk():
        import disks_page

        return disks_page


def _import_wizard():
    """Import pool_create_wizard under a fresh mocked GTK context."""
    sys.modules.pop("pool_create_wizard", None)
    with mock_gtk():
        import pool_create_wizard

        return pool_create_wizard


def _disk(path, **kwargs):
    defaults = {
        "name": os.path.basename(path),
        "path": path,
        "by_id": "ata-TEST" + os.path.basename(path),
        "size_bytes": TB,
        "size_human": "10T",
        "disk_type": "HDD",
        "physical_sector": 4096,
        "transport": "sata",
    }
    defaults.update(kwargs)
    return DiskInfo(**defaults)


def _eligible(disks, imported=None, importable=None):
    return disk_eligibility(disks, imported or {}, importable or {})


GENERAL_PROFILE = {
    "description": "General-purpose mixed files.",
    "applies_to": ["filesystem"],
    "properties": {
        "recordsize": "128K",
        "compression": "lz4",
        "atime": "off",
        "logbias": "latency",
        "sync": "standard",
        "primarycache": "all",
        "special_small_blocks": "0",
    },
    "notes": "",
}


def _state(pcw, disks=None, **overrides):
    """Build a wizard state with all eligible disks selected."""
    disks = disks if disks is not None else [_disk("/dev/sda"), _disk("/dev/sdb")]
    results = _eligible(disks)
    state = pcw._WizardState(
        eligibility=results,
        selected=[r.disk for r in results if r.eligible],
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


class _Iter:
    """Truth-y iterator stand-in for FakeListStoreIterable."""

    def __init__(self, index):
        self.index = index


class FakeListStoreIterable:
    """Minimal ListStore stand-in supporting get_iter_first/iter_next."""

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


def _make_app(disks=None, topologies=None):
    """Return a mocked app object ready for create-pool handler tests."""
    app = MagicMock()
    app.config = {"pools": []}
    app.parent_dir = "/tmp/bin"
    app.stack.get_visible_child_name.return_value = "disks"
    app.enable_treeview_copy = MagicMock()

    data = MagicMock()
    data.disks = (
        disks if disks is not None else [_disk("/dev/sda"), _disk("/dev/sdb")]
    )
    data.topologies = topologies or {}
    app._disks_inventory_cache = MagicMock()
    app._disks_inventory_cache.get.return_value = data
    app._disks_syncing_selection = False

    app._disks_pool_selector = MagicMock()
    app._disks_pool_selector.get_active_text.return_value = None
    app.disks_store = FakeListStoreIterable()
    app.disks_view = FakeTreeView(app.disks_store, [])
    app.disks_topology_store = MagicMock()
    app.disks_topology_view = MagicMock()
    app.disks_dataset_store = FakeListStoreIterable()
    app.disks_dataset_view = FakeTreeView(app.disks_dataset_store, [])
    app.dataset_runner = FakeDatasetRunner()

    app.known_pools = []
    app._pools_saved_state = []
    app._pools_save_btn = None  # avoid MagicMock in set_button_markup_red
    app.pool_store = FakeListStoreIterable()
    app.pool_view = FakeTreeView(app.pool_store, [])
    app._importable_pool_cache = MagicMock()
    app._importable_pool_cache.get.return_value = set()

    repo = MagicMock()
    repo.list_importable_pool_devices.return_value = {}
    repo.list_importable_pool_names.return_value = set()
    repo.list_pools_full.return_value = []
    repo.create_pool_dry_run.return_value = (0, "would create 'newpool'")

    app.ctx = MagicMock()
    app.ctx.zfs_repository = repo
    app.ctx.zfs_caps = MagicMock()
    return app


def _expected_general_command():
    """The exact argv the happy path should produce (general profile)."""
    from feature_config import DEFAULT_WORKLOAD_PROFILES

    expected = ["zpool", "create"]
    for prop, value in pool_filesystem_options(DEFAULT_WORKLOAD_PROFILES["general"]):
        expected += ["-O", f"{prop}={value}"]
    expected += [
        "newpool",
        "mirror",
        "/dev/disk/by-id/ata-TESTsda",
        "/dev/disk/by-id/ata-TESTsdb",
    ]
    return expected


def _make_spy_state(pcw):
    """Return a (spy class, states list) pair capturing wizard states."""
    states = []

    class _SpyState(pcw._WizardState):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            states.append(self)

    return _SpyState, states


NEXT = "next"
CREATE = "create"
BACK = "back"
CANCEL = "cancel"


def _select_all(state):
    state.selected = [r.disk for r in state.eligibility if r.eligible]


def _name_pool(state):
    state.pool_name = "newpool"


def _confirm(state):
    state.typed = "newpool"


class _WizardDriver:
    """Drives the wizard through a scripted response sequence.

    Each script step is a token (NEXT/CREATE/BACK/CANCEL) or a callable that
    receives the live wizard state, may mutate it (simulating the user's
    widget interactions), and returns a token. The token is resolved to a
    dialog response id inside the dialog.run() side effect.
    """

    def __init__(self, pcw, script):
        self.pcw = pcw
        self.script = list(script)
        self.pages_seen = []
        self.states = []
        self.fake_dlg = MagicMock()
        self.fake_dlg.run.side_effect = self._respond

    def _respond(self):
        state = self.states[0]
        self.pages_seen.append(state.page)
        step = self.script.pop(0)
        token = step(state) if callable(step) else step
        responses = {
            NEXT: self.pcw._RESPONSE_NEXT,
            CREATE: self.pcw._RESPONSE_CREATE,
            BACK: self.pcw._RESPONSE_BACK,
            CANCEL: self.pcw.Gtk.ResponseType.CANCEL,
        }
        return responses[token]


def _drive_wizard(pcw, app, driver, patch_zlm=True):
    """Run on_disks_create_pool with a scripted wizard dialog."""
    spy_state, driver.states = _make_spy_state(pcw)
    mock_zlm = MagicMock()
    mock_zlm.acquire.return_value = "/lock/newpool"
    nc = MagicMock()
    nc.is_two_node.return_value = False
    patches = [
        patch.object(pcw, "create_dialog", return_value=driver.fake_dlg),
        patch.object(pcw, "_WizardState", spy_state),
        patch.object(pcw, "node_config", nc),
        patch.object(pcw.Gtk, "MessageDialog"),
    ]
    if patch_zlm:
        patches.append(patch.object(pcw, "zlm", mock_zlm))
    stack = contextlib.ExitStack()
    for p in patches:
        stack.enter_context(p)
    with capture_logs():
        pcw.on_disks_create_pool(app)
    # The runner completes asynchronously (FakeDatasetRunner.finish), so the
    # caller must keep the patch stack alive until completion; the context
    # manager closes it on exit. Returns the zlm mock (or None).
    return mock_zlm, stack


@contextlib.contextmanager
def _wizard_session(pcw, app, driver, patch_zlm=True):
    """Drive the wizard and keep its patches active for runner completion."""
    mock_zlm, stack = _drive_wizard(pcw, app, driver, patch_zlm)
    try:
        yield mock_zlm
    finally:
        stack.close()


class TestPureHelpers(unittest.TestCase):
    """Wizard decision helpers, no dialogs required."""

    def test_leaf_paths_by_pool_collects_disk_nodes(self):
        pcw = _import_wizard()
        root = TopologyNode(
            "pool1",
            "pool",
            "ONLINE",
            0,
            0,
            0,
            None,
            [
                TopologyNode(
                    "mirror-0",
                    "mirror",
                    "ONLINE",
                    0,
                    0,
                    0,
                    None,
                    [
                        TopologyNode("/dev/sda", "disk", "ONLINE", 0, 0, 0, None, []),
                        TopologyNode("/dev/sdb", "disk", "ONLINE", 0, 0, 0, None, []),
                    ],
                )
            ],
        )
        paths = pcw._leaf_paths_by_pool({"pool1": root})
        self.assertEqual(paths, {"pool1": ["/dev/sda", "/dev/sdb"]})

    def test_leaf_paths_by_pool_ignores_missing_topologies(self):
        pcw = _import_wizard()
        self.assertEqual(pcw._leaf_paths_by_pool({}), {})
        self.assertEqual(pcw._leaf_paths_by_pool(None), {})

    def test_recordsize_bytes(self):
        pcw = _import_wizard()
        self.assertEqual(pcw._recordsize_bytes({"properties": {"recordsize": "8K"}}), 8192)
        self.assertEqual(pcw._recordsize_bytes({"properties": {"recordsize": "1M"}}), 1048576)
        self.assertEqual(pcw._recordsize_bytes({"properties": {"recordsize": "16K"}}), 16384)
        self.assertEqual(pcw._recordsize_bytes({"properties": {}}), 128 * 1024)
        self.assertEqual(pcw._recordsize_bytes({"properties": {"recordsize": "junk"}}), 128 * 1024)

    def test_format_bytes(self):
        pcw = _import_wizard()
        self.assertEqual(pcw._format_bytes(0), "0 B")
        self.assertEqual(pcw._format_bytes(512), "512 B")
        self.assertEqual(pcw._format_bytes(1024), "1.0 KiB")
        self.assertEqual(pcw._format_bytes(1536), "1.5 KiB")
        self.assertEqual(pcw._format_bytes(10**12), "931.3 GiB")

    def test_disks_problems(self):
        pcw = _import_wizard()
        empty = pcw._WizardState(eligibility=[])
        self.assertEqual(pcw._disks_problems(empty), ["Select at least one eligible disk"])
        state = _state(pcw)
        self.assertEqual(pcw._disks_problems(state), [])

    def test_topology_problems_enforce_minimums(self):
        pcw = _import_wizard()
        two = [_disk("/dev/sda"), _disk("/dev/sdb")]
        state = _state(pcw, disks=two, topology="raidz2")
        problems = pcw._topology_problems(state)
        self.assertEqual(len(problems), 1)
        self.assertIn("at least 4 disks", problems[0])

        state = _state(pcw, disks=two, topology="mirror")
        self.assertEqual(pcw._topology_problems(state), [])

    def test_topology_problems_reject_same_parent_partitions(self):
        pcw = _import_wizard()
        part1 = _disk("/dev/sda1", disk_type="part", parent_path="/dev/sda")
        part2 = _disk("/dev/sda2", disk_type="part", parent_path="/dev/sda")
        state = pcw._WizardState(eligibility=[], selected=[part1, part2], topology="mirror")
        problems = pcw._topology_problems(state)
        self.assertEqual(len(problems), 1)
        self.assertIn("same physical device", problems[0])

    def test_settings_problems(self):
        pcw = _import_wizard()
        state = _state(pcw, pool_name="newpool")
        self.assertEqual(pcw._settings_problems(state, set()), [])
        self.assertEqual(
            pcw._settings_problems(state, {"newpool"}),
            ["pool 'newpool' already exists (or is importable)"],
        )
        state.pool_name = "mirror"
        self.assertTrue(pcw._settings_problems(state, set()))

    def test_review_problems_matrix(self):
        pcw = _import_wizard()
        state = _state(pcw, pool_name="newpool")
        state.command = ["zpool", "create", "newpool", "mirror"]
        self.assertEqual(pcw._review_problems(state), ["Dry run has not completed"])
        state.dry_run_rc = 1
        self.assertEqual(
            pcw._review_problems(state),
            ["Dry run failed — resolve the problem before creating"],
        )
        state.dry_run_rc = 0
        self.assertEqual(
            pcw._review_problems(state),
            ["Type the pool name 'newpool' to confirm"],
        )
        state.typed = "newpool"
        self.assertEqual(pcw._review_problems(state), [])

    def test_review_problems_without_command(self):
        pcw = _import_wizard()
        state = _state(pcw, pool_name="newpool", typed="newpool", dry_run_rc=0)
        self.assertEqual(pcw._review_problems(state), ["Command is not ready"])

    def test_build_wizard_command_exact_argv(self):
        pcw = _import_wizard()
        state = _state(
            pcw,
            pool_name="newpool",
            topology="mirror",
            ashift=12,
            profile_name="general",
        )
        cmd = pcw.build_wizard_command(state, {"general": GENERAL_PROFILE})
        self.assertEqual(
            cmd,
            [
                "zpool",
                "create",
                "-o",
                "ashift=12",
                "-O",
                "recordsize=128K",
                "-O",
                "compression=lz4",
                "-O",
                "atime=off",
                "-O",
                "logbias=latency",
                "-O",
                "sync=standard",
                "-O",
                "primarycache=all",
                "-O",
                "special_small_blocks=0",
                "newpool",
                "mirror",
                "/dev/disk/by-id/ata-TESTsda",
                "/dev/disk/by-id/ata-TESTsdb",
            ],
        )

    def test_build_wizard_command_propagates_value_error(self):
        pcw = _import_wizard()
        state = _state(
            pcw,
            disks=[_disk("/dev/sda")],
            pool_name="newpool",
            topology="mirror",
        )
        with self.assertRaises(ValueError):
            pcw.build_wizard_command(state, {"general": GENERAL_PROFILE})

    def test_estimate_text(self):
        pcw = _import_wizard()
        state = _state(pcw, topology="mirror")
        text = pcw._estimate_text(state, GENERAL_PROFILE)
        self.assertIn("100% of raw usable", text)

        mixed = [
            _disk("/dev/sda", size_bytes=TB, size_human="10T"),
            _disk("/dev/sdb", size_bytes=TB // 2, size_human="5T"),
        ]
        state = _state(pcw, disks=mixed, topology="mirror")
        text = pcw._estimate_text(state, GENERAL_PROFILE)
        self.assertIn("smallest member", text)

        empty = pcw._WizardState(eligibility=[])
        self.assertIn("Select disks", pcw._estimate_text(empty, GENERAL_PROFILE))

    def test_review_warnings_for_selected_usb_disk(self):
        pcw = _import_wizard()
        usb = _disk("/dev/sdc", transport="usb")
        results = _eligible([usb])
        state = pcw._WizardState(
            eligibility=results,
            selected=[results[0].disk],
        )
        warnings = pcw._review_warnings(state)
        self.assertEqual(len(warnings), 1)
        self.assertIn("USB", warnings[0])

    def test_signal_handlers_update_state(self):
        pcw = _import_wizard()
        state = _state(pcw)
        calls = []

        def on_change():
            calls.append(1)

        entry = MagicMock()
        entry.get_text.return_value = "newpool"
        pcw._on_name_changed(entry, state, on_change)
        self.assertEqual(state.pool_name, "newpool")

        typed = MagicMock()
        typed.get_text.return_value = "newpool"
        pcw._on_typed_changed(typed, state, on_change)
        self.assertEqual(state.typed, "newpool")

        ashift = MagicMock()
        ashift.get_active_text.return_value = "12"
        pcw._on_ashift_changed(ashift, state, on_change)
        self.assertEqual(state.ashift, 12)
        ashift.get_active_text.return_value = "auto (recommended)"
        pcw._on_ashift_changed(ashift, state, on_change)
        self.assertIsNone(state.ashift)

        profile = MagicMock()
        profile.get_active_text.return_value = "media"
        pcw._on_profile_changed(profile, state, on_change)
        self.assertEqual(state.profile_name, "media")

        radio = MagicMock()
        radio.get_active.return_value = True
        pcw._on_topology_toggled(radio, "raidz2", state, on_change)
        self.assertEqual(state.topology, "raidz2")

        radio.get_active.return_value = False
        pcw._on_topology_toggled(radio, "stripe", state, on_change)
        self.assertEqual(state.topology, "raidz2")

        self.assertEqual(len(calls), 6)

    def test_disk_toggle_updates_selection(self):
        pcw = _import_wizard()
        disks = [_disk("/dev/sda"), _disk("/dev/sdb")]
        results = _eligible(disks)
        state = pcw._WizardState(eligibility=results)
        store = FakeListStoreIterable(
            [
                [False, "ata-TESTsda", "10T", "", "sata", "eligible", True, None],
                [False, "ata-TESTsdb", "10T", "", "sata", "eligible", True, None],
            ]
        )
        calls = []
        pcw._on_disk_toggled(None, 1, store, state, lambda: calls.append(1))
        self.assertEqual(state.selected, [disks[1]])
        self.assertTrue(calls)

        # Toggling an ineligible row is refused.
        store.set_value(_Iter(0), pcw._COL_ELIGIBLE, False)
        pcw._on_disk_toggled(None, 0, store, state, lambda: None)
        self.assertEqual(state.selected, [disks[1]])


class TestHandlerGuards(unittest.TestCase):
    """Early-return guards in on_disks_create_pool."""

    def test_two_node_compute_host_bails(self):
        pcw = _import_wizard()
        app = _make_app()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with (
            patch.object(pcw, "node_config", nc),
            patch.object(pcw, "show_create_pool_wizard") as wiz,
            capture_logs() as logs,
        ):
            pcw.on_disks_create_pool(app)
        wiz.assert_not_called()
        self.assertEqual(app.dataset_runner.steps, [])
        self.assertFalse(app.ctx.zfs_repository.list_importable_pool_devices.called)
        self.assertTrue(
            any("storage host" in line for line in logs),
            logs,
        )

    def test_runner_busy_bails(self):
        pcw = _import_wizard()
        app = _make_app()
        app.dataset_runner.running = True
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pcw, "node_config", nc),
            patch.object(pcw, "show_create_pool_wizard") as wiz,
            capture_logs() as logs,
        ):
            pcw.on_disks_create_pool(app)
        wiz.assert_not_called()
        self.assertTrue(any("already running" in line for line in logs), logs)

    def test_no_eligible_disks_shows_info_dialog(self):
        pcw = _import_wizard()
        disk = _disk("/dev/sda")
        topo = TopologyNode(
            "pool1",
            "pool",
            "ONLINE",
            0,
            0,
            0,
            None,
            [TopologyNode("/dev/sda", "disk", "ONLINE", 0, 0, 0, None, [])],
        )
        app = _make_app(disks=[disk], topologies={"pool1": topo})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pcw, "node_config", nc),
            patch.object(pcw, "show_create_pool_wizard") as wiz,
            patch.object(pcw.Gtk, "MessageDialog") as msg_dialog,
            capture_logs(),
        ):
            pcw.on_disks_create_pool(app)
        wiz.assert_not_called()
        msg_dialog.assert_called_once()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_wizard_cancel_runs_nothing(self):
        pcw = _import_wizard()
        app = _make_app()
        driver = _WizardDriver(pcw, [CANCEL])
        with _wizard_session(pcw, app, driver):
            pass
        self.assertEqual(app.dataset_runner.steps, [])

    def test_no_filesystem_profiles_bails(self):
        pcw = _import_wizard()
        app = _make_app()
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pcw, "node_config", nc),
            patch.object(pcw, "get_workload_profiles", return_value={}),
            patch.object(pcw, "show_create_pool_wizard") as wiz,
            capture_logs() as logs,
        ):
            pcw.on_disks_create_pool(app)
        wiz.assert_not_called()
        self.assertTrue(
            any("No filesystem workload profiles" in line for line in logs),
            logs,
        )

    def test_wizard_requires_profiles(self):
        pcw = _import_wizard()
        with capture_logs() as logs:
            result = pcw.show_create_pool_wizard(
                MagicMock(), eligibility=[], profiles={}, existing_names=set()
            )
        self.assertIsNone(result)
        self.assertTrue(any("WARN" in line for line in logs), logs)


class TestCreatePoolButtonSensitivity(unittest.TestCase):
    """update_disks_button_sensitivity gates the Create Pool button."""

    def _make(self):
        dp = _import_disks_page()
        app = _make_app()
        app._disks_create_pool_btn = MagicMock()
        return dp, app

    def test_enabled_on_single_host(self):
        dp, app = self._make()
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with patch.object(dp, "node_config", nc):
            dp.update_disks_button_sensitivity(app)
        app._disks_create_pool_btn.set_sensitive.assert_called_with(True)
        app._disks_create_pool_btn.set_tooltip_text.assert_called_with("")

    def test_disabled_on_two_node_compute_host(self):
        dp, app = self._make()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with patch.object(dp, "node_config", nc):
            dp.update_disks_button_sensitivity(app)
        app._disks_create_pool_btn.set_sensitive.assert_called_with(False)
        app._disks_create_pool_btn.set_tooltip_text.assert_called_with(
            "Pool creation is available only on the storage host"
        )

    def test_enabled_on_two_node_storage_host(self):
        dp, app = self._make()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = True
        with patch.object(dp, "node_config", nc):
            dp.update_disks_button_sensitivity(app)
        app._disks_create_pool_btn.set_sensitive.assert_called_with(True)
        app._disks_create_pool_btn.set_tooltip_text.assert_called_with("")

    def test_disabled_while_runner_busy(self):
        dp, app = self._make()
        app.dataset_runner.running = True
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with patch.object(dp, "node_config", nc):
            dp.update_disks_button_sensitivity(app)
        app._disks_create_pool_btn.set_sensitive.assert_called_with(False)
        app._disks_create_pool_btn.set_tooltip_text.assert_called_with(
            "A dataset action is already running"
        )

    def test_compute_host_tooltip_takes_precedence_over_runner_busy(self):
        dp, app = self._make()
        app.dataset_runner.running = True
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with patch.object(dp, "node_config", nc):
            dp.update_disks_button_sensitivity(app)
        app._disks_create_pool_btn.set_sensitive.assert_called_with(False)
        app._disks_create_pool_btn.set_tooltip_text.assert_called_with(
            "Pool creation is available only on the storage host"
        )

    def test_works_before_dataset_runner_exists(self):
        """Regression: page creation runs before the window builds dataset_runner."""
        dp = _import_disks_page()
        app = SimpleNamespace(
            disks_view=FakeTreeView(FakeListStoreIterable(), []),
            _disks_create_pool_btn=MagicMock(),
        )
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with patch.object(dp, "node_config", nc):
            dp.update_disks_button_sensitivity(app)
        app._disks_create_pool_btn.set_sensitive.assert_called_with(True)
        app._disks_create_pool_btn.set_tooltip_text.assert_called_with("")


class TestWizardFlow(unittest.TestCase):
    """End-to-end handler flow with a scripted wizard dialog."""

    def test_happy_path_creates_pool(self):
        pcw = _import_wizard()
        app = _make_app()
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                NEXT,
                lambda state: (_name_pool(state), NEXT)[1],
                lambda state: (_confirm(state), CREATE)[1],
            ],
        )
        with _wizard_session(pcw, app, driver) as mock_zlm:
            self.assertEqual(
                driver.pages_seen, ["disks", "topology", "settings", "review"]
            )
            expected = _expected_general_command()
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, expected)
            self.assertTrue(step.fatal)
            self.assertEqual(step.description, "Create pool newpool")
            mock_zlm.acquire.assert_called_once_with("newpool", "w", "Create pool newpool")
            app.ctx.zfs_repository.create_pool_dry_run.assert_called_once_with(expected)

            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/newpool")
        app._disks_inventory_cache.invalidate.assert_called_once()
        self.assertTrue(app._importable_pool_cache.invalidate.called)

    def test_registration_offer_yes_appends_to_registry(self):
        pcw = _import_wizard()
        app = _make_app()
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                NEXT,
                lambda state: (_name_pool(state), NEXT)[1],
                lambda state: (_confirm(state), CREATE)[1],
            ],
        )
        with _wizard_session(pcw, app, driver):
            yes = pcw.Gtk.ResponseType.YES
            with patch.object(
                pcw.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=yes)),
            ):
                app.dataset_runner.finish()

        self.assertEqual(
            app.known_pools, [{"name": "newpool", "offsite_candidate": False}]
        )

    def test_registration_offer_no_leaves_registry_empty(self):
        pcw = _import_wizard()
        app = _make_app()
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                NEXT,
                lambda state: (_name_pool(state), NEXT)[1],
                lambda state: (_confirm(state), CREATE)[1],
            ],
        )
        with _wizard_session(pcw, app, driver):
            no = pcw.Gtk.ResponseType.NO
            with patch.object(
                pcw.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=no)),
            ):
                app.dataset_runner.finish()

        self.assertEqual(app.known_pools, [])

    def test_minimum_disk_validation_blocks_next(self):
        pcw = _import_wizard()
        app = _make_app(disks=[_disk("/dev/sda")])
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                NEXT,  # topology page: mirror needs 2 disks -> rejected
                CANCEL,
            ],
        )
        with _wizard_session(pcw, app, driver):
            pass
        self.assertEqual(
            driver.pages_seen, ["disks", "topology", "topology"]
        )
        self.assertEqual(app.dataset_runner.steps, [])

    def test_typed_confirmation_mismatch_blocks_create(self):
        pcw = _import_wizard()
        app = _make_app()

        def _wrong_confirm(state):
            state.typed = "wrongname"
            return CREATE

        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                NEXT,
                lambda state: (_name_pool(state), NEXT)[1],
                _wrong_confirm,
                CANCEL,
            ],
        )
        with _wizard_session(pcw, app, driver):
            pass
        self.assertEqual(
            driver.pages_seen,
            ["disks", "topology", "settings", "review", "review"],
        )
        self.assertEqual(app.dataset_runner.steps, [])

    def test_dry_run_failure_blocks_create(self):
        pcw = _import_wizard()
        app = _make_app()
        app.ctx.zfs_repository.create_pool_dry_run.return_value = (1, "invalid vdev")
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                NEXT,
                lambda state: (_name_pool(state), NEXT)[1],
                lambda state: (_confirm(state), CREATE)[1],
                CANCEL,
            ],
        )
        with _wizard_session(pcw, app, driver):
            pass
        self.assertEqual(driver.pages_seen[-1], "review")
        self.assertEqual(app.dataset_runner.steps, [])

    def test_back_navigation(self):
        pcw = _import_wizard()
        app = _make_app()
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                BACK,
                BACK,
                CANCEL,
            ],
        )
        with _wizard_session(pcw, app, driver):
            pass
        self.assertEqual(driver.pages_seen, ["disks", "topology", "disks", "disks"])

    def test_cancel_mid_wizard_runs_nothing(self):
        pcw = _import_wizard()
        app = _make_app()
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                CANCEL,
            ],
        )
        with _wizard_session(pcw, app, driver):
            pass
        self.assertEqual(app.dataset_runner.steps, [])

    def test_prepare_review_command_build_failure(self):
        pcw = _import_wizard()
        state = _state(pcw, pool_name="newpool", topology="bogus")
        ctx = pcw._WizardContext(
            app=MagicMock(),
            profiles={"general": GENERAL_PROFILE},
            existing_names=set(),
            repository=MagicMock(),
        )
        pcw._prepare_review(state, ctx)
        self.assertEqual(state.dry_run_rc, 1)
        self.assertIn("could not build command", state.dry_run_output)
        ctx.repository.create_pool_dry_run.assert_not_called()

    def test_registration_skipped_when_already_registered(self):
        pcw = _import_wizard()
        app = _make_app()
        app.known_pools = [{"name": "newpool", "offsite_candidate": False}]
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                NEXT,
                lambda state: (_name_pool(state), NEXT)[1],
                lambda state: (_confirm(state), CREATE)[1],
            ],
        )
        with _wizard_session(pcw, app, driver):
            with patch.object(pcw.Gtk, "MessageDialog") as msg_dialog:
                app.dataset_runner.finish()
        msg_dialog.assert_not_called()
        self.assertEqual(
            app.known_pools, [{"name": "newpool", "offsite_candidate": False}]
        )

    def test_real_lock_acquire_and_release(self):
        pcw = _import_wizard()
        app = _make_app()
        driver = _WizardDriver(
            pcw,
            [
                lambda state: (_select_all(state), NEXT)[1],
                NEXT,
                lambda state: (_name_pool(state), NEXT)[1],
                lambda state: (_confirm(state), CREATE)[1],
            ],
        )
        import zfs_lock_manager

        with temp_lock_dir() as tmpdir:
            with patch.object(zfs_lock_manager, "node_config") as zlm_nc:
                zlm_nc.is_two_node.return_value = False
                zlm_nc.get_lock_authority_host.return_value = None
                with _wizard_session(pcw, app, driver, patch_zlm=False):
                    locks_dir = os.path.join(tmpdir, ".locks")
                    self.assertTrue(os.path.isdir(locks_dir))
                    self.assertEqual(len(app.dataset_runner.steps), 1)
                    self.assertNotEqual(os.listdir(locks_dir), [])
                    app.dataset_runner.finish()
                    self.assertEqual(os.listdir(locks_dir), [])


if __name__ == "__main__":
    unittest.main()
