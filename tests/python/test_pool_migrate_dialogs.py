"""Tests for pool_migrate_dialogs — Migrate Pool dialog and handler."""

import contextlib
import os
import shlex
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from disk_repository import DiskInfo
from pool_create import disk_eligibility
from test_support import capture_logs, mock_gtk, normalize_repo_root, requires_gi

pytestmark = requires_gi
import golden
from zfs_repository import DatasetRow, TopologyNode

TB = 10**12

SNAP = "@migrate-2026-09-10T14:30-04:00"


def _import_dialogs():
    """Import pool_migrate_dialogs under a fresh mocked GTK context."""
    sys.modules.pop("pool_migrate_dialogs", None)
    with mock_gtk(fresh=True):
        import pool_migrate_dialogs

        return pool_migrate_dialogs


def _disk(path, **kwargs):
    defaults = {
        "name": os.path.basename(path),
        "path": path,
        "by_id": "ata-TEST" + os.path.basename(path),
        "size_bytes": TB,
        "size_human": "1.0 TB",
        "disk_type": "HDD",
        "physical_sector": 4096,
        "transport": "sata",
    }
    defaults.update(kwargs)
    return DiskInfo(**defaults)


def _node(name, vdev_type, children=(), state="ONLINE"):
    return TopologyNode(name, vdev_type, state, 0, 0, 0, None, list(children))


def _topology(pool, leaf_paths):
    return _node(
        pool,
        "pool",
        [_node(path, "disk") for path in leaf_paths],
    )


def _default_topologies():
    return {
        "pool1": _topology("pool1", ["/dev/sda", "/dev/sdb"]),
        "pool2": _topology("pool2", ["/dev/sdz"]),
    }


def _default_datasets():
    return {"pool1": ["data", "vm-100-disk-0"], "pool2": ["stuff"]}


def _state(pmd, pools=None, datasets=None, disks=None, **overrides):
    """Build a Migrate-Pool dialog state with sane defaults."""
    disks = (
        disks
        if disks is not None
        else [_disk("/dev/sda"), _disk("/dev/sdb"), _disk("/dev/sdz")]
    )
    results = disk_eligibility(disks, {}, {})
    pools = pools if pools is not None else ["pool1", "pool2"]
    alloc = {pool: 10**9 for pool in pools}
    free = {pool: 40 * TB for pool in pools}
    state = pmd._MigrateState(
        pools=pools,
        pool_name=pools[0] if pools else "",
        mode=pmd.MIGRATE_NEW_DISKS,
        datasets_by_pool=datasets if datasets is not None else _default_datasets(),
        pool_alloc=alloc,
        pool_free=free,
        eligibility=results,
        disks=disks,
        topologies=_default_topologies(),
        existing_names=set(pools),
        snap_name=SNAP,
        selected=[r.disk for r in results if r.eligible and r.disk.path != "/dev/sdz"],
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def _request(pmd, mode=None, **overrides):
    request = pmd.MigrationRequest(
        source_pool="pool1",
        mode=mode or pmd.MIGRATE_NEW_DISKS,
        datasets=("data", "vm-100-disk-0"),
        snap_bare="migrate-2026-09-10T14:30-04:00",
        temp_pool="pool1_mig",
        **overrides,
    )
    return request


def _norm_command(cmd):
    # Send-step scripts resolve the zfs-migrate-send wrapper from this
    # checkout's absolute location; normalize it (and its quoting) so
    # goldens stay machine-independent.
    return [normalize_repo_root(c) for c in cmd]


def _plan_text(steps):
    # One step per line, argv shell-quoted (verify scripts contain spaces
    # and quotes), for readable per-step diffs.
    return "\n".join(shlex.join(_norm_command(s.command)) for s in steps)


class TestPureHelpers(unittest.TestCase):
    """Dialog decision helpers, no dialogs required."""

    def test_problems_require_a_pool(self):
        pmd = _import_dialogs()
        state = _state(pmd, pools=[], pool_name="")
        self.assertEqual(pmd._migrate_problems(state), ["Select a source pool"])

    def test_problems_refuse_pool_without_datasets(self):
        pmd = _import_dialogs()
        state = _state(pmd, datasets={"pool1": [], "pool2": ["stuff"]})
        self.assertEqual(
            pmd._migrate_problems(state),
            ["Pool 'pool1' has no datasets to migrate"],
        )

    def test_problems_require_disk_selection(self):
        pmd = _import_dialogs()
        state = _state(pmd, selected=[])
        self.assertEqual(pmd._migrate_problems(state), ["Select at least one eligible disk"])

    def test_problems_enforce_topology_minimum(self):
        pmd = _import_dialogs()
        state = _state(pmd, topology="raidz2")
        self.assertEqual(
            pmd._migrate_problems(state),
            ["raidz2 requires at least 4 disks"],
        )

    def test_problems_refuse_insufficient_new_pool_capacity(self):
        pmd = _import_dialogs()
        state = _state(pmd, pool_alloc={"pool1": 100 * TB, "pool2": 10**9})
        problems = pmd._migrate_problems(state)
        self.assertTrue(any("less than" in p for p in problems), problems)

    def test_problems_require_holding_pool(self):
        pmd = _import_dialogs()
        state = _state(pmd, mode=pmd.MIGRATE_HOLDING_POOL, holding_pool="")
        self.assertEqual(
            pmd._migrate_problems(state),
            ["Select a holding pool (a pool other than the source)"],
        )

    def test_problems_reject_source_as_holding_pool(self):
        pmd = _import_dialogs()
        state = _state(pmd, mode=pmd.MIGRATE_HOLDING_POOL, holding_pool="pool1")
        self.assertEqual(
            pmd._migrate_problems(state),
            ["Select a holding pool (a pool other than the source)"],
        )

    def test_problems_refuse_insufficient_holding_space(self):
        pmd = _import_dialogs()
        free = {"pool1": 40 * TB, "pool2": 10**6}
        state = _state(
            pmd, mode=pmd.MIGRATE_HOLDING_POOL, holding_pool="pool2", pool_free=free
        )
        problems = pmd._migrate_problems(state)
        self.assertTrue(any("insufficient" in p for p in problems), problems)

    def test_problems_require_typed_confirmation(self):
        pmd = _import_dialogs()
        state = _state(pmd, typed="")
        self.assertEqual(
            pmd._migrate_problems(state),
            ["Type the pool name 'pool1' to confirm"],
        )

    def test_no_problems_on_valid_new_disks_selection(self):
        pmd = _import_dialogs()
        state = _state(pmd, typed="pool1")
        self.assertEqual(pmd._migrate_problems(state), [])

    def test_no_problems_on_valid_holding_selection(self):
        pmd = _import_dialogs()
        state = _state(
            pmd,
            mode=pmd.MIGRATE_HOLDING_POOL,
            holding_pool="pool2",
            typed="pool1",
        )
        self.assertEqual(pmd._migrate_problems(state), [])

    def test_rate_limit_problem_accepts_empty_and_valid_rates(self):
        pmd = _import_dialogs()
        for text in ("", "100", "100k", "25M", "2g", "1T"):
            self.assertIsNone(pmd._rate_limit_problem(text), text)

    def test_rate_limit_problem_rejects_garbage(self):
        pmd = _import_dialogs()
        for text in ("abc", "10x", "1.5m", "-5m", "100 mb"):
            problem = pmd._rate_limit_problem(text)
            self.assertIsNotNone(problem, text)
            self.assertIn("bandwidth limit", problem)

    def test_problems_reject_invalid_rate_limit(self):
        pmd = _import_dialogs()
        state = _state(pmd, typed="pool1", rate_limit="fast")
        problems = pmd._migrate_problems(state)
        self.assertEqual(len(problems), 1)
        self.assertIn("bandwidth limit", problems[0])

    def test_valid_rate_limit_does_not_block_migration(self):
        pmd = _import_dialogs()
        state = _state(pmd, typed="pool1", rate_limit="100m")
        self.assertEqual(pmd._migrate_problems(state), [])

    def test_on_rate_limit_changed_updates_state(self):
        pmd = _import_dialogs()
        state = _state(pmd)
        calls = []
        entry = MagicMock()
        entry.get_text.return_value = "100m"
        pmd._on_rate_limit_changed(entry, state, lambda: calls.append(1))
        self.assertEqual(state.rate_limit, "100m")
        self.assertEqual(calls, [1])

    def test_warnings_mention_cutover_and_path_preservation(self):
        pmd = _import_dialogs()
        warnings = " ".join(pmd._migrate_warnings(_state(pmd)))
        self.assertIn("cutover exports", warnings)
        self.assertIn("dataset path survives", warnings)

    def test_holding_warnings_mention_holding_pool_uptime(self):
        pmd = _import_dialogs()
        state = _state(pmd, mode=pmd.MIGRATE_HOLDING_POOL, holding_pool="pool2")
        warnings = " ".join(pmd._migrate_warnings(state))
        self.assertIn("holding pool must stay online", warnings)

    def test_plan_lines_use_temp_pool_for_new_disks(self):
        pmd = _import_dialogs()
        lines = pmd._plan_lines(_state(pmd))
        self.assertTrue(any("'pool1_mig'" in line for line in lines), lines)

    def test_plan_lines_use_holding_pool_for_holding_mode(self):
        pmd = _import_dialogs()
        state = _state(pmd, mode=pmd.MIGRATE_HOLDING_POOL, holding_pool="pool2")
        lines = pmd._plan_lines(state)
        self.assertTrue(any("'pool2'" in line for line in lines), lines)

    def test_build_request_new_disks(self):
        pmd = _import_dialogs()
        request = pmd.build_request(_state(pmd, typed="pool1"))
        self.assertEqual(request.source_pool, "pool1")
        self.assertEqual(request.mode, pmd.MIGRATE_NEW_DISKS)
        self.assertEqual(request.temp_pool, "pool1_mig")
        self.assertEqual(request.datasets, ("data", "vm-100-disk-0"))
        self.assertEqual(request.snap_bare, "migrate-2026-09-10T14:30-04:00")
        self.assertEqual(request.holding_pool, "")

    def test_build_request_holding_mode(self):
        pmd = _import_dialogs()
        state = _state(
            pmd, mode=pmd.MIGRATE_HOLDING_POOL, holding_pool="pool2", typed="pool1"
        )
        request = pmd.build_request(state)
        self.assertEqual(request.holding_pool, "pool2")
        self.assertEqual(request.new_pool_topology, "mirror")
        self.assertEqual(
            request.new_pool_by_id,
            ("/dev/disk/by-id/ata-TESTsda", "/dev/disk/by-id/ata-TESTsdb"),
        )

    def test_build_request_carries_rate_limit(self):
        pmd = _import_dialogs()
        state = _state(pmd, typed="pool1", rate_limit="100m")
        self.assertEqual(pmd.build_request(state).rate_limit, "100m")
        state = _state(pmd, typed="pool1")
        self.assertEqual(pmd.build_request(state).rate_limit, "")


class TestBuildMigrationSteps(unittest.TestCase):
    """Execution plan composition for both migration modes."""

    def test_new_disks_copy_steps(self):
        pmd = _import_dialogs()
        copy, _cutover = pmd.build_migration_steps(_request(pmd))
        self.assertEqual(len(copy), 5)  # snapshot + 2 copies + 2 verifies
        golden.check(self, _plan_text(copy))

    def test_copy_steps_carry_rate_limit(self):
        pmd = _import_dialogs()
        request = _request(pmd, rate_limit="100m")
        copy, cutover = pmd.build_migration_steps(request)
        for step in copy[1:3]:
            self.assertIn("pv_rate_limit=100m", step.command[2])
        # Holding mode: copy-out and copy-back both honor the limit.
        holding = _request(
            pmd,
            mode=pmd.MIGRATE_HOLDING_POOL,
            holding_pool="pool2",
            new_pool_by_id=(
                "/dev/disk/by-id/ata-TESTsda",
                "/dev/disk/by-id/ata-TESTsdb",
            ),
            rate_limit="50m",
        )
        copy, cutover = pmd.build_migration_steps(holding)
        for step in copy[1:3]:
            self.assertIn("pv_rate_limit=50m", step.command[2])
        copyback = [
            s
            for s in cutover
            if s.command[0:2] == ["bash", "-c"] and "zfs_migrate_send" in s.command[2]
        ]
        self.assertTrue(copyback)
        for step in copyback:
            self.assertIn("pv_rate_limit=50m", step.command[2])

    def test_new_disks_cutover_steps(self):
        pmd = _import_dialogs()
        _copy, cutover = pmd.build_migration_steps(_request(pmd))
        golden.check(self, _plan_text(cutover))

    def test_holding_mode_cutover_sequence(self):
        pmd = _import_dialogs()
        request = _request(
            pmd,
            mode=pmd.MIGRATE_HOLDING_POOL,
            holding_pool="pool2",
            new_pool_topology="raidz1",
            new_pool_by_id=(
                "/dev/disk/by-id/ata-TESTsda",
                "/dev/disk/by-id/ata-TESTsdb",
                "/dev/disk/by-id/ata-TESTsdc",
            ),
        )
        _copy, cutover = pmd.build_migration_steps(request)
        # export, destroy, create, 2 copy-back, 2 verify, 2 destroy-copy,
        # export holding, import-rename
        self.assertEqual(len(cutover), 11)
        golden.check(self, _plan_text(cutover))


class TestRootPoolName(unittest.TestCase):
    def test_finds_pool_of_root_mount(self):
        pmd = _import_dialogs()
        repo = MagicMock()
        repo.list_dataset_info.return_value = [
            {"name": "rpool/ROOT/pve", "mountpoint": "/"},
            {"name": "rpool/var", "mountpoint": "/var"},
        ]
        self.assertEqual(pmd._root_pool_name(repo), "rpool")

    def test_no_root_mount_returns_none(self):
        pmd = _import_dialogs()
        repo = MagicMock()
        repo.list_dataset_info.return_value = [
            {"name": "pool1/data", "mountpoint": "/data"}
        ]
        self.assertIsNone(pmd._root_pool_name(repo))

    def test_read_failure_returns_none(self):
        pmd = _import_dialogs()
        repo = MagicMock()
        repo.list_dataset_info.side_effect = OSError("boom")
        with capture_logs():
            self.assertIsNone(pmd._root_pool_name(repo))


class TestCutoverConfirm(unittest.TestCase):
    def _run_confirm(self, pmd, typed, responses):
        fake = MagicMock()
        fake.run.side_effect = responses
        entry = MagicMock()
        entry.get_text.return_value = typed
        request = _request(pmd)
        with (
            patch.object(pmd, "create_dialog", return_value=fake),
            patch.object(pmd.Gtk, "Entry", return_value=entry),
        ):
            return pmd._show_cutover_confirm(MagicMock(), request)

    def test_confirm_with_typed_name(self):
        pmd = _import_dialogs()
        ok = self._run_confirm(pmd, "pool1", [pmd._RESPONSE_MIGRATE])
        self.assertTrue(ok)

    def test_cancel_returns_false(self):
        pmd = _import_dialogs()
        ok = self._run_confirm(
            pmd, "pool1", [pmd.Gtk.ResponseType.CANCEL]
        )
        self.assertFalse(ok)


class TestDialogFlow(unittest.TestCase):
    def _run_dialog(self, pmd, state, response):
        fake = MagicMock()

        def respond():
            return response(pmd, state) if callable(response) else response

        fake.run.side_effect = respond
        app = MagicMock()
        with (
            patch.object(pmd, "create_dialog", return_value=fake),
            patch.object(pmd, "scrub_blocks_pool_op", return_value=None),
        ):
            return pmd.show_migrate_pool_dialog(app, state)

    def test_confirm_returns_request(self):
        pmd = _import_dialogs()
        state = _state(pmd)

        def fill(_pmd, st):
            st.typed = st.pool_name
            return _pmd._RESPONSE_MIGRATE

        request = self._run_dialog(pmd, state, fill)
        self.assertIsNotNone(request)
        self.assertEqual(request.source_pool, "pool1")
        self.assertEqual(request.temp_pool, "pool1_mig")

    def test_request_carries_dialog_rate_limit(self):
        pmd = _import_dialogs()
        state = _state(pmd, rate_limit="100m")

        def fill(_pmd, st):
            st.typed = st.pool_name
            return _pmd._RESPONSE_MIGRATE

        request = self._run_dialog(pmd, state, fill)
        self.assertIsNotNone(request)
        self.assertEqual(request.rate_limit, "100m")

    def test_cancel_returns_none(self):
        pmd = _import_dialogs()
        request = self._run_dialog(
            pmd, _state(pmd), lambda pmd_, _st: pmd_.Gtk.ResponseType.CANCEL
        )
        self.assertIsNone(request)

    def test_scrub_blocked_shows_info_and_does_not_migrate(self):
        """A scrub blocker on the source/destination pool blocks Migrate.

        The dialog must show the blocker message and loop back without
        building a request; the follow-up CANCEL then cancels cleanly.
        """
        pmd = _import_dialogs()
        state = _state(pmd)
        state.typed = state.pool_name

        fake = MagicMock()
        fake.run.side_effect = [
            pmd._RESPONSE_MIGRATE,
            pmd.Gtk.ResponseType.CANCEL,
        ]
        app = MagicMock()
        with (
            patch.object(pmd, "create_dialog", return_value=fake),
            patch.object(
                pmd, "scrub_blocks_pool_op", return_value="scrub is running on pool1"
            ),
            patch.object(pmd, "_show_info_dialog") as mock_info,
        ):
            request = pmd.show_migrate_pool_dialog(app, state)

        self.assertIsNone(request)
        mock_info.assert_called_once_with(fake, "scrub is running on pool1")
        fake.run.assert_called_with()  # second run() consumed the CANCEL


class FakeDatasetRunner:
    """BackupRunner stand-in for dataset action tests."""

    def __init__(self):
        self.running = False
        self.steps = []
        self.operation_detail = None
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
    def __init__(self, model, paths=None):
        self.model = model
        self.paths = paths or []

    def get_selected_rows(self):
        return (self.model, self.paths)


class FakeTreeView:
    def __init__(self, model=None, paths=None):
        self.model = model
        self._selection = FakeTreeSelection(model, paths)

    def get_selection(self):
        return self._selection


def _dataset_row(name):
    return DatasetRow(name, "-", "filesystem", "1G", "1G", "1G", "-", "-", "yes")


def _make_app(pools=("pool1", "pool2"), root_pool=None):
    """Return a mocked app object ready for Migrate-Pool handler tests."""
    app = MagicMock()
    app.config = {"pools": []}
    app.stack.get_visible_child_name.return_value = "disks"

    data = MagicMock()
    data.disks = [_disk("/dev/sda"), _disk("/dev/sdb"), _disk("/dev/sdz")]
    leaf_map = {"pool1": ["/dev/sda", "/dev/sdb"], "pool2": ["/dev/sdz"]}
    data.topologies = {
        pool: _topology(pool, leaf_map.get(pool, ["/dev/sdz"])) for pool in pools
    }
    app._disks_inventory_cache = MagicMock()
    app._disks_inventory_cache.get.return_value = data
    app._disks_syncing_selection = False

    app._disks_pool_selector = MagicMock()
    app._disks_pool_selector.get_active_text.return_value = pools[0]
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
    repo.list_pools_full.return_value = [
        {
            "name": pool,
            "size": str(40 * TB),
            "alloc": str(10**9),
            "free": str(40 * TB),
            "freeing": "0",
            "ckpoint": "-",
            "frag": "0%",
            "cap": "3%",
            "health": "ONLINE",
        }
        for pool in pools
    ]
    repo.list_datasets.side_effect = lambda pool, depth=None: [
        _dataset_row(pool),
        _dataset_row(f"{pool}/data"),
    ]
    mount_info = []
    if root_pool:
        mount_info.append({"name": f"{root_pool}/ROOT/pve", "mountpoint": "/"})
    repo.list_dataset_info.return_value = mount_info

    app.ctx = MagicMock()
    app.ctx.zfs_repository = repo
    app.ctx.zfs_caps = MagicMock()
    return app


def _drive_handler(pmd, app, request, confirm_cutover=True):
    """Run on_disks_migrate_pool with the dialog and cutover confirm scripted."""
    mock_zlm = MagicMock()
    mock_zlm.acquire.return_value = "/lock/pool1"
    nc = MagicMock()
    nc.is_two_node.return_value = False
    patches = [
        patch.object(pmd, "show_migrate_pool_dialog", return_value=request),
        patch.object(pmd, "_show_cutover_confirm", return_value=confirm_cutover),
        patch.object(pmd, "node_config", nc),
        patch.object(pmd, "zlm", mock_zlm),
    ]
    stack = contextlib.ExitStack()
    for p in patches:
        stack.enter_context(p)
    with capture_logs():
        pmd.on_disks_migrate_pool(app)
    # The runner completes asynchronously (FakeDatasetRunner.finish), so the
    # caller must keep the patch stack alive until completion.
    return mock_zlm, stack


class TestHandlerGuards(unittest.TestCase):
    def test_compute_host_warns(self):
        pmd = _import_dialogs()
        app = _make_app()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with (
            patch.object(pmd, "node_config", nc),
            patch.object(pmd, "show_migrate_pool_dialog") as dialog,
            capture_logs() as logs,
        ):
            pmd.on_disks_migrate_pool(app)
        dialog.assert_not_called()
        self.assertTrue(any("storage host" in m for m in logs))

    def test_runner_busy_warns(self):
        pmd = _import_dialogs()
        app = _make_app()
        app.dataset_runner.running = True
        with (
            patch.object(pmd, "show_migrate_pool_dialog") as dialog,
            capture_logs() as logs,
        ):
            pmd.on_disks_migrate_pool(app)
        dialog.assert_not_called()
        self.assertTrue(any("already running" in m for m in logs))

    def test_no_pools_warns(self):
        pmd = _import_dialogs()
        app = _make_app(pools=("pool1",))
        app._disks_inventory_cache.get.return_value.topologies = {}
        with (
            patch.object(pmd, "show_migrate_pool_dialog") as dialog,
            capture_logs() as logs,
        ):
            pmd.on_disks_migrate_pool(app)
        dialog.assert_not_called()
        self.assertTrue(any("No imported pools" in m for m in logs))

    def test_root_pool_only_shows_info_dialog(self):
        pmd = _import_dialogs()
        app = _make_app(pools=("pool1",), root_pool="pool1")
        with (
            patch.object(pmd, "show_migrate_pool_dialog") as dialog,
            patch.object(pmd, "_show_info_dialog") as info,
            capture_logs(),
        ):
            pmd.on_disks_migrate_pool(app)
        dialog.assert_not_called()
        info.assert_called_once()

    def test_dialog_cancel_starts_nothing(self):
        pmd = _import_dialogs()
        app = _make_app()
        mock_zlm, stack = _drive_handler(pmd, app, None)
        with stack:
            self.assertEqual(app.dataset_runner.steps, [])
            self.assertFalse(app.dataset_runner.running)
            mock_zlm.acquire.assert_not_called()


class TestHandlerExecution(unittest.TestCase):
    def test_full_migration_runs_copy_then_cutover(self):
        pmd = _import_dialogs()
        app = _make_app()
        request = _request(pmd)
        mock_zlm, stack = _drive_handler(pmd, app, request)
        with stack:
            # Copy phase started.
            self.assertEqual(len(app.dataset_runner.steps), 5)
            self.assertTrue(app.dataset_runner.running)
            self.assertEqual(app.dataset_runner.operation_detail, "Migrate Pool: pool1")
            app.dataset_runner.finish(rc=0)
            # Cutover phase started after confirmation; the detail persists
            # across the runner restart.
            self.assertEqual(len(app.dataset_runner.steps), 2)
            self.assertEqual(app.dataset_runner.operation_detail, "Migrate Pool: pool1")
            app.dataset_runner.finish(rc=0)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
            app._disks_inventory_cache.invalidate.assert_called_once()

    def test_copy_failure_skips_cutover(self):
        pmd = _import_dialogs()
        app = _make_app()
        request = _request(pmd)
        mock_zlm, stack = _drive_handler(pmd, app, request)
        with stack:
            app.dataset_runner.finish(rc=1)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
            app._disks_inventory_cache.invalidate.assert_called_once()

    def test_deferred_cutover_releases_lock_without_cutover(self):
        pmd = _import_dialogs()
        app = _make_app()
        request = _request(pmd)
        mock_zlm, stack = _drive_handler(pmd, app, request, confirm_cutover=False)
        with stack:
            app.dataset_runner.finish(rc=0)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
            # The runner was not started a second time.
            self.assertFalse(app.dataset_runner.running)

    def test_holding_mode_uses_holding_request(self):
        pmd = _import_dialogs()
        app = _make_app()
        request = _request(
            pmd,
            mode=pmd.MIGRATE_HOLDING_POOL,
            holding_pool="pool2",
            new_pool_topology="mirror",
            new_pool_by_id=("/dev/disk/by-id/ata-TESTsda", "/dev/disk/by-id/ata-TESTsdb"),
        )
        mock_zlm, stack = _drive_handler(pmd, app, request)
        with stack:
            self.assertEqual(len(app.dataset_runner.steps), 5)
            app.dataset_runner.finish(rc=0)
            self.assertEqual(len(app.dataset_runner.steps), 11)
            app.dataset_runner.finish(rc=0)
            mock_zlm.release.assert_called_once_with("/lock/pool1")


class TestCutoverIscsiRepair(unittest.TestCase):
    """repair-iscsi-luns chaining after a successful cutover."""

    REPAIR_BIN = "/usr/local/lib/zfsutilities/current/bin/repair-iscsi-luns"

    def _run_cutover(self, managed, final_rc=0, two_node_hint=True):
        """Drive a migration through cutover completion; return (pmd, app, logs)."""
        pmd = _import_dialogs()
        app = _make_app()
        request = _request(pmd)
        _mock_zlm, stack = _drive_handler(pmd, app, request)
        with stack:
            # The cutover-completion hint is only logged in two-node configs.
            pmd.node_config.is_two_node.return_value = two_node_hint
            app.dataset_runner.finish(rc=0)  # copy phase
            with (
                patch.object(pmd, "is_iscsi_managed_pool", return_value=managed),
                patch.object(pmd, "resolve_local_bin", return_value=self.REPAIR_BIN),
                capture_logs() as logs,
            ):
                app.dataset_runner.finish(rc=0)  # cutover phase → chaining decision
                if managed:
                    app.dataset_runner.finish(rc=final_rc)  # chained repair phase
        return pmd, app, logs

    def test_managed_pool_chains_repair_step(self):
        _pmd, app, _logs = self._run_cutover(managed=True)
        self.assertEqual(len(app.dataset_runner.steps), 1)
        self.assertEqual(app.dataset_runner.operation_detail, "Migrate Pool: pool1")
        step = app.dataset_runner.steps[0]
        golden.check(self, step.command)
        self.assertEqual(step.description, "Re-register migrated pool iSCSI LUNs")
        self.assertFalse(step.is_rsync)
        self.assertFalse(step.fatal)

    def test_unmanaged_pool_skips_repair_and_logs_hint(self):
        _pmd, app, logs = self._run_cutover(managed=False)
        # The cutover step list (2 steps) was not replaced by a repair step.
        self.assertEqual(len(app.dataset_runner.steps), 2)
        self.assertTrue(
            any("not enrolled in two-node iSCSI" in line for line in logs), logs
        )
        self.assertTrue(any("setup-iscsi-targets" in line for line in logs), logs)

    def test_unmanaged_pool_single_node_finishes_silently(self):
        _pmd, app, logs = self._run_cutover(managed=False, two_node_hint=False)
        self.assertEqual(len(app.dataset_runner.steps), 2)
        self.assertFalse(
            any("not enrolled in two-node iSCSI" in line for line in logs), logs
        )
        self.assertFalse(any("setup-iscsi-targets" in line for line in logs), logs)

    def test_repair_failure_logs_warn(self):
        _pmd, _app, logs = self._run_cutover(managed=True, final_rc=4)
        self.assertTrue(
            any("WARN" in line and "failed (rc=4)" in line for line in logs), logs
        )


if __name__ == "__main__":
    unittest.main()
