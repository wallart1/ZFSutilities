"""Tests for pool_growth_dialogs — Add Data Vdev, Attach, Replace, Detach,
and Add Infrastructure Vdev dialogs/handlers.
"""

import contextlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from disk_repository import DiskInfo
from pool_create import EligibilityResult, disk_eligibility
from test_support import capture_logs, mock_gtk, requires_gi

pytestmark = requires_gi
from zfs_repository import TopologyNode

TB = 10**12

POOL1_TOPOLOGY = TopologyNode(
    "pool1",
    "pool",
    "ONLINE",
    0,
    0,
    0,
    None,
    [TopologyNode("/dev/sdz", "disk", "ONLINE", 0, 0, 0, None, [])],
)


def _import_dialogs():
    """Import pool_growth_dialogs under a fresh mocked GTK context."""
    sys.modules.pop("pool_growth_dialogs", None)
    with mock_gtk(fresh=True):
        import pool_growth_dialogs

        return pool_growth_dialogs


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


def _state(pgd, pools=None, disks=None, **overrides):
    """Build an Add-Vdev dialog state with all eligible disks selected."""
    disks = disks if disks is not None else [_disk("/dev/sda"), _disk("/dev/sdb")]
    results = _eligible(disks)
    pools = pools if pools is not None else ["pool1"]
    state = pgd._AddVdevState(
        pools=pools,
        pool_name=pools[0] if pools else "",
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


class _FakeTreeStore:
    """Minimal TreeStore stand-in recording (parent, row) appends."""

    def __init__(self):
        self.rows = []

    def clear(self):
        self.rows = []

    def append(self, parent, row):
        self.rows.append((parent, list(row)))
        return len(self.rows) - 1


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

    def finish(self, cancelled=False, rc=0):
        self.running = False
        if self._on_complete:
            self._on_complete(cancelled=cancelled, rc=rc)


def _make_app(disks=None, topologies=None):
    """Return a mocked app object ready for Add-Vdev handler tests."""
    app = MagicMock()
    app.config = {"pools": []}
    app.parent_dir = "/tmp/bin"
    app.stack.get_visible_child_name.return_value = "disks"
    app.enable_treeview_copy = MagicMock()

    data = MagicMock()
    data.disks = disks if disks is not None else [_disk("/dev/sda"), _disk("/dev/sdb")]
    data.topologies = topologies if topologies is not None else {"pool1": POOL1_TOPOLOGY}
    app._disks_inventory_cache = MagicMock()
    app._disks_inventory_cache.get.return_value = data
    app._disks_syncing_selection = False

    app._disks_pool_selector = MagicMock()
    app._disks_pool_selector.get_active_text.return_value = "pool1"
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

    app.ctx = MagicMock()
    app.ctx.zfs_repository = repo
    app.ctx.zfs_caps = MagicMock()
    return app


def _expected_add_command(pool="pool1", topology="mirror", ids=("sda", "sdb")):
    return (
        ["zpool", "add", pool]
        + ([topology] if topology != "stripe" else [])
        + [f"/dev/disk/by-id/ata-TEST{name}" for name in ids]
    )


def _make_spy_state(pgd):
    """Return a (spy class, states list) pair capturing dialog states."""
    states = []

    class _SpyState(pgd._AddVdevState):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            states.append(self)

    return _SpyState, states


CONFIRM = "confirm"
CANCEL = "cancel"


def _select_all(state):
    state.selected = [r.disk for r in state.eligibility if r.eligible]


def _confirm(state):
    state.typed = state.pool_name


class _AddVdevDriver:
    """Drives the Add-Vdev dialog through a scripted response sequence.

    Each script step is a token (CONFIRM/CANCEL) or a callable that receives
    the live dialog state, may mutate it (simulating the user's widget
    interactions), and returns a token. The token is resolved to a dialog
    response id inside the dialog.run() side effect.
    """

    def __init__(self, pgd, script):
        self.pgd = pgd
        self.script = list(script)
        self.runs_seen = []
        self.states = []
        self.fake_dlg = MagicMock()
        self.fake_dlg.run.side_effect = self._respond

    def _respond(self):
        state = self.states[0]
        self.runs_seen.append(state.pool_name)
        step = self.script.pop(0)
        token = step(state) if callable(step) else step
        responses = {
            CONFIRM: self.pgd._RESPONSE_CONFIRM,
            CANCEL: self.pgd.Gtk.ResponseType.CANCEL,
        }
        return responses[token]


def _drive_handler(pgd, app, driver):
    """Run on_disks_add_vdev with a scripted dialog."""
    spy_state, driver.states = _make_spy_state(pgd)
    mock_zlm = MagicMock()
    mock_zlm.acquire.return_value = "/lock/pool1"
    nc = MagicMock()
    nc.is_two_node.return_value = False
    patches = [
        patch.object(pgd, "create_scrolled_dialog", return_value=(driver.fake_dlg, MagicMock())),
        patch.object(pgd, "_AddVdevState", spy_state),
        patch.object(pgd, "node_config", nc),
        patch.object(pgd.Gtk, "MessageDialog"),
        patch.object(pgd, "scrub_blocks_pool_op", return_value=None),
        patch.object(pgd, "zlm", mock_zlm),
    ]
    stack = contextlib.ExitStack()
    for p in patches:
        stack.enter_context(p)
    with capture_logs():
        pgd.on_disks_add_vdev(app)
    # The runner completes asynchronously (FakeDatasetRunner.finish), so the
    # caller must keep the patch stack alive until completion; the context
    # manager closes it on exit. Returns the zlm mock.
    return mock_zlm, stack


@contextlib.contextmanager
def _handler_session(pgd, app, driver):
    """Drive the handler and keep its patches active for runner completion."""
    mock_zlm, stack = _drive_handler(pgd, app, driver)
    try:
        yield mock_zlm
    finally:
        stack.close()


class TestPureHelpers(unittest.TestCase):
    """Dialog decision helpers, no dialogs required."""

    def test_problems_require_a_pool(self):
        pgd = _import_dialogs()
        state = _state(pgd, pools=[])
        self.assertEqual(pgd._add_vdev_problems(state), ["Select a pool"])

    def test_problems_require_a_selection(self):
        pgd = _import_dialogs()
        state = _state(pgd, selected=[])
        self.assertEqual(pgd._add_vdev_problems(state), ["Select at least one eligible disk"])

    def test_problems_enforce_topology_minimum(self):
        pgd = _import_dialogs()
        state = _state(pgd, disks=[_disk("/dev/sda")])
        self.assertEqual(
            pgd._add_vdev_problems(state),
            ["mirror requires at least 2 disks"],
        )

    def test_problems_enforce_device_separation(self):
        pgd = _import_dialogs()
        disks = [
            _disk("/dev/sda1", parent_path="/dev/sda"),
            _disk("/dev/sda2", parent_path="/dev/sda"),
        ]
        state = _state(pgd, disks=disks)
        problems = pgd._add_vdev_problems(state)
        self.assertTrue(any("same physical device" in p for p in problems), problems)

    def test_problems_enforce_raidz_minimum(self):
        pgd = _import_dialogs()
        state = _state(pgd, selected=[_disk("/dev/sda")], topology="raidz2")
        self.assertEqual(
            pgd._add_vdev_problems(state),
            ["raidz2 requires at least 4 disks"],
        )

    def test_problems_surface_builder_value_error(self):
        pgd = _import_dialogs()
        # A by-id containing whitespace passes the dialog-level checks but
        # the argv builder refuses it.
        bad = _disk("/dev/sda", by_id="bad disk")
        state = _state(pgd, selected=[bad, _disk("/dev/sdb")], typed="pool1")
        problems = pgd._add_vdev_problems(state)
        self.assertTrue(any("by-id" in p for p in problems), problems)
        self.assertEqual(state.command, [])

    def test_problems_require_typed_confirmation(self):
        pgd = _import_dialogs()
        state = _state(pgd, typed="")
        self.assertEqual(
            pgd._add_vdev_problems(state),
            ["Type the pool name 'pool1' to confirm"],
        )

    def test_no_problems_on_valid_selection(self):
        pgd = _import_dialogs()
        state = _state(pgd, typed="pool1")
        self.assertEqual(pgd._add_vdev_problems(state), [])
        self.assertEqual(
            state.command,
            _expected_add_command(),
        )

    def test_warnings_include_mixed_sizes(self):
        pgd = _import_dialogs()
        disks = [_disk("/dev/sda"), _disk("/dev/sdb", size_bytes=2 * TB, size_human="20T")]
        state = _state(pgd, disks=disks)
        warnings = pgd._add_vdev_warnings(state)
        self.assertTrue(any("differ in size" in w for w in warnings), warnings)

    def test_warnings_include_eligibility_warnings(self):
        pgd = _import_dialogs()
        disks = [_disk("/dev/sda"), _disk("/dev/sdb", transport="usb")]
        state = _state(pgd, disks=disks)
        warnings = pgd._add_vdev_warnings(state)
        self.assertTrue(any("USB" in w for w in warnings), warnings)

    def test_no_warnings_when_uniform_and_clean(self):
        pgd = _import_dialogs()
        state = _state(pgd)
        self.assertEqual(pgd._add_vdev_warnings(state), [])

    def test_build_argv_exact(self):
        pgd = _import_dialogs()
        state = _state(pgd, topology="raidz1", disks=[_disk(f"/dev/sd{c}") for c in "abc"])
        self.assertEqual(
            pgd.build_add_vdev_argv(state),
            _expected_add_command(topology="raidz1", ids=("sda", "sdb", "sdc")),
        )

    def test_build_argv_stripe_has_no_keyword(self):
        pgd = _import_dialogs()
        state = _state(pgd, topology="stripe", disks=[_disk("/dev/sda")])
        self.assertEqual(
            pgd.build_add_vdev_argv(state),
            _expected_add_command(topology="stripe", ids=("sda",)),
        )

    def test_signal_handlers_update_state(self):
        pgd = _import_dialogs()
        state = _state(pgd, selected=[])
        calls = []

        def on_change():
            calls.append(1)

        combo = MagicMock()
        combo.get_active_text.return_value = "pool2"
        pgd._on_pool_changed(combo, state, on_change)
        self.assertEqual(state.pool_name, "pool2")

        radio = MagicMock()
        radio.get_active.return_value = True
        pgd._on_topology_toggled(radio, "raidz2", state, on_change)
        self.assertEqual(state.topology, "raidz2")

        radio.get_active.return_value = False
        pgd._on_topology_toggled(radio, "stripe", state, on_change)
        self.assertEqual(state.topology, "raidz2")

        typed = MagicMock()
        typed.get_text.return_value = "pool2"
        pgd._on_typed_changed(typed, state, on_change)
        self.assertEqual(state.typed, "pool2")

        self.assertEqual(len(calls), 3)

    def test_disk_toggle_updates_selection(self):
        pgd = _import_dialogs()
        disks = [_disk("/dev/sda"), _disk("/dev/sdb")]
        results = _eligible(disks)
        state = pgd._AddVdevState(pools=["pool1"], pool_name="pool1", eligibility=results)
        store = FakeListStoreIterable(
            [
                [False, "ata-TESTsda", "10T", "", "sata", "eligible", True, None],
                [False, "ata-TESTsdb", "10T", "", "sata", "eligible", True, None],
            ]
        )
        calls = []
        pgd._on_disk_toggled(None, 1, store, state, lambda: calls.append(1))
        self.assertEqual(state.selected, [disks[1]])
        self.assertTrue(calls)

        # Toggling an ineligible row is refused.
        store.set_value(_Iter(0), pgd._COL_ELIGIBLE, False)
        pgd._on_disk_toggled(None, 0, store, state, lambda: None)
        self.assertEqual(state.selected, [disks[1]])


class TestHandlerGuards(unittest.TestCase):
    """Early-return guards in on_disks_add_vdev."""

    def test_two_node_compute_host_bails(self):
        pgd = _import_dialogs()
        app = _make_app()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_add_vdev_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_add_vdev(app)
        dialog.assert_not_called()
        self.assertEqual(app.dataset_runner.steps, [])
        self.assertTrue(any("storage host" in line for line in logs), logs)

    def test_runner_busy_bails(self):
        pgd = _import_dialogs()
        app = _make_app()
        app.dataset_runner.running = True
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_add_vdev_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_add_vdev(app)
        dialog.assert_not_called()
        self.assertTrue(any("already running" in line for line in logs), logs)

    def test_no_imported_pools_bails(self):
        pgd = _import_dialogs()
        app = _make_app(topologies={})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_add_vdev_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_add_vdev(app)
        dialog.assert_not_called()
        self.assertTrue(any("No imported pools" in line for line in logs), logs)

    def test_no_eligible_disks_shows_info_dialog(self):
        pgd = _import_dialogs()
        disk = _disk("/dev/sdz")
        app = _make_app(disks=[disk], topologies={"pool1": POOL1_TOPOLOGY})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_add_vdev_dialog") as dialog,
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            capture_logs(),
        ):
            pgd.on_disks_add_vdev(app)
        dialog.assert_not_called()
        msg_dialog.assert_called_once()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_dialog_cancel_runs_nothing(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _AddVdevDriver(pgd, [CANCEL])
        with _handler_session(pgd, app, driver):
            pass
        self.assertEqual(app.dataset_runner.steps, [])


class TestDialogFlow(unittest.TestCase):
    """End-to-end handler flow with a scripted Add-Vdev dialog."""

    def test_happy_path_adds_vdev(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _AddVdevDriver(
            pgd,
            [lambda state: (_select_all(state), _confirm(state), CONFIRM)[2]],
        )
        with _handler_session(pgd, app, driver) as mock_zlm:
            expected = _expected_add_command()
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, expected)
            self.assertTrue(step.fatal)
            self.assertEqual(step.description, "Add vdev to pool pool1")
            mock_zlm.acquire.assert_called_once_with("pool1", "w", "Add vdev to pool1")

            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        app._disks_inventory_cache.invalidate.assert_called_once()
        self.assertTrue(app._importable_pool_cache.invalidate.called)

    def test_happy_path_adds_stripe_vdev_single_disk(self):
        """Stripe-grow path: one disk + stripe topology adds a new top-level
        stripe vdev with no topology keyword (`zpool add pool1 <disk>`)."""
        pgd = _import_dialogs()
        app = _make_app(disks=[_disk("/dev/sdc")])
        driver = _AddVdevDriver(
            pgd,
            [
                lambda state: (
                    _select_all(state),
                    setattr(state, "topology", "stripe"),
                    _confirm(state),
                    CONFIRM,
                )[3],
            ],
        )
        with _handler_session(pgd, app, driver) as mock_zlm:
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, _expected_add_command(topology="stripe", ids=("sdc",)))
            self.assertEqual(step.description, "Add vdev to pool pool1")
            mock_zlm.acquire.assert_called_once_with("pool1", "w", "Add vdev to pool1")
            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/pool1")

    def test_happy_path_cancelled_logs_info(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _AddVdevDriver(
            pgd,
            [lambda state: (_select_all(state), _confirm(state), CONFIRM)[2]],
        )
        with _handler_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            app.dataset_runner.finish(cancelled=True)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        self.assertTrue(any("cancelled" in line for line in logs), logs)

    def test_failed_step_logs_failed_and_skips_success_note(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _AddVdevDriver(
            pgd,
            [lambda state: (_select_all(state), _confirm(state), CONFIRM)[2]],
        )
        with _handler_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            app.dataset_runner.finish(cancelled=False, rc=1)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        self.assertTrue(
            any("Add vdev failed for pool 'pool1' (rc=1)" in line for line in logs),
            logs,
        )
        self.assertFalse(any("Added vdev to pool" in line for line in logs), logs)

    def test_typed_mismatch_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _make_app()

        def _select_and_mistype(state):
            _select_all(state)
            state.typed = "wrongpool"
            return CONFIRM

        driver = _AddVdevDriver(pgd, [_select_and_mistype, CANCEL])
        with _handler_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_minimum_disk_validation_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _make_app(disks=[_disk("/dev/sda")])
        driver = _AddVdevDriver(
            pgd,
            [
                lambda state: (_select_all(state), _confirm(state), CONFIRM)[2],
                CANCEL,
            ],
        )
        with _handler_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_raidz_disabled_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _raidz_app()
        app.ctx.zfs_caps.supports.return_value = False
        app.ctx.zfs_caps.requires.return_value = "requires OpenZFS 2.3+"
        driver = _AttachDriver(pgd, [_pick_raidz_target, CANCEL])
        with _attach_handler_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        driver.msg_dialog.assert_not_called()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_scrub_block_keeps_dialog_open(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _AddVdevDriver(
            pgd,
            [
                lambda state: (_select_all(state), _confirm(state), CONFIRM)[2],
                CANCEL,
            ],
        )
        spy_state, driver.states = _make_spy_state(pgd)
        mock_zlm = MagicMock()
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(
                pgd, "create_scrolled_dialog", return_value=(driver.fake_dlg, MagicMock())
            ),
            patch.object(pgd, "_AddVdevState", spy_state),
            patch.object(pgd, "node_config", nc),
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            patch.object(
                pgd,
                "scrub_blocks_pool_op",
                return_value="pool 'pool1' has a scrub scanning",
            ),
            patch.object(pgd, "zlm", mock_zlm),
            capture_logs(),
        ):
            pgd.on_disks_add_vdev(app)
        # Confirm was refused, the info dialog was shown, then cancel ran.
        self.assertEqual(len(driver.runs_seen), 2)
        msg_dialog.assert_called_once()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_scrub_pass_returns_command(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _AddVdevDriver(
            pgd,
            [lambda state: (_select_all(state), _confirm(state), CONFIRM)[2]],
        )
        with _handler_session(pgd, app, driver) as mock_zlm:
            expected = _expected_add_command()
            self.assertEqual(app.dataset_runner.steps[0].command, expected)
            mock_zlm.acquire.assert_called_once_with("pool1", "w", "Add vdev to pool1")
            app.dataset_runner.finish()

    def test_topology_radio_emission_during_construction_is_safe(self):
        """GTK emits 'toggled' from set_active while the dialog is built.

        Regression: the radios were connected before set_active, so the
        constructor-time emission called _refresh before the review scaffold
        existed (NameError: free variable 'scaffold').
        """
        pgd = _import_dialogs()
        app = _make_app()

        class _FakeRadio:
            """RadioButton stand-in that emits 'toggled' from set_active."""

            def __init__(self, label=""):
                self._active = False
                self._handlers = []

            def connect(self, _signal, handler, *args):
                self._handlers.append((handler, args))

            def set_active(self, active):
                self._active = active
                for handler, args in list(self._handlers):
                    handler(self, *args)

            def get_active(self):
                return self._active

            def set_label(self, _label):
                pass

            def set_halign(self, _align):
                pass

            @classmethod
            def new_from_widget(cls, _widget):
                return cls()

        driver = _AddVdevDriver(pgd, [CANCEL])
        with patch.object(pgd.Gtk, "RadioButton", _FakeRadio):
            with _handler_session(pgd, app, driver):
                pass
        self.assertEqual(driver.runs_seen, ["pool1"])


# ---------------------------------------------------------------------------
# Attach dialog fixtures
# ---------------------------------------------------------------------------


def _stripe_topology():
    """pool1: single-disk stripe vdev."""
    return TopologyNode(
        "pool1",
        "pool",
        "ONLINE",
        0,
        0,
        0,
        None,
        [TopologyNode("/dev/sdz", "disk", "ONLINE", 0, 0, 0, None, [])],
    )


def _mirror_topology():
    """pool1: two-way mirror vdev."""
    return TopologyNode(
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
                    TopologyNode("/dev/sdz", "disk", "ONLINE", 0, 0, 0, None, []),
                    TopologyNode("/dev/sdy", "disk", "ONLINE", 0, 0, 0, None, []),
                ],
            )
        ],
    )


def _raidz_topology():
    """pool1: four-disk raidz2 vdev."""
    return TopologyNode(
        "pool1",
        "pool",
        "ONLINE",
        0,
        0,
        0,
        None,
        [
            TopologyNode(
                "raidz2-0",
                "raidz2",
                "ONLINE",
                0,
                0,
                0,
                None,
                [TopologyNode(f"/dev/sd{c}", "disk", "ONLINE", 0, 0, 0, None, []) for c in "abcd"],
            )
        ],
    )


def _caps(supports=True):
    """Mocked capability layer with a fixed raidz_expansion verdict."""
    caps = MagicMock()
    caps.supports.return_value = supports
    caps.requires.return_value = "requires OpenZFS 2.3+"
    return caps


def _attach_state(
    pgd,
    topologies=None,
    target=None,
    selected=None,
    typed="",
    disks=None,
    eligibility=None,
    **overrides,
):
    """Build an Attach dialog state around a pool1 topology."""
    disks = (
        disks if disks is not None else [_disk("/dev/sdz"), _disk("/dev/sda"), _disk("/dev/sdb")]
    )
    if eligibility is None:
        eligibility = _eligible(disks)
    topologies = topologies if topologies is not None else {"pool1": _stripe_topology()}
    if selected is None:
        selected = [disks[1]]
    state = pgd._AttachState(
        pools=["pool1"],
        pool_name="pool1",
        topologies=topologies,
        eligibility=eligibility,
        disks=disks,
        target=target,
        selected=selected,
        typed=typed,
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def _stripe_app():
    """App mock: pool1 is a single-disk stripe; sda/sdb are free."""
    disks = [_disk("/dev/sdz"), _disk("/dev/sda"), _disk("/dev/sdb")]
    return _make_app(disks=disks, topologies={"pool1": _stripe_topology()})


def _raidz_app():
    """App mock: pool1 is a raidz2 vdev; sdx/sdy are free."""
    disks = [_disk(f"/dev/sd{c}") for c in "abcd"]
    disks += [_disk("/dev/sdx"), _disk("/dev/sdy")]
    return _make_app(disks=disks, topologies={"pool1": _raidz_topology()})


def _pick_stripe_target(state):
    state.target = state.topologies["pool1"].children[0]
    state.selected = [state.disks[1]]
    return CONFIRM


def _pick_raidz_target(state):
    state.target = state.topologies["pool1"].children[0]
    state.selected = [state.disks[4]]
    state.typed = "pool1"
    return CONFIRM


def _make_attach_spy_state(pgd):
    """Return a (spy class, states list) pair capturing attach dialog states."""
    states = []

    class _SpyState(pgd._AttachState):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            states.append(self)

    return _SpyState, states


class _AttachDriver:
    """Drives the Attach dialog through a scripted response sequence.

    Each script step is a token (CONFIRM/CANCEL) or a callable that receives
    the live dialog state, may mutate it (simulating the user's widget
    interactions), and returns a token. *message_response* is what the YES/NO
    warning MessageDialog (and any info dialog) returns from run().
    """

    def __init__(self, pgd, script, message_response=None):
        self.pgd = pgd
        self.script = list(script)
        self.runs_seen = []
        self.states = []
        self.fake_dlg = MagicMock()
        self.fake_dlg.run.side_effect = self._respond
        self.msg_dialog = MagicMock()
        if message_response is not None:
            self.msg_dialog.return_value.run.return_value = message_response

    def _respond(self):
        state = self.states[0]
        self.runs_seen.append(state.pool_name)
        step = self.script.pop(0)
        token = step(state) if callable(step) else step
        responses = {
            CONFIRM: self.pgd._RESPONSE_CONFIRM,
            CANCEL: self.pgd.Gtk.ResponseType.CANCEL,
        }
        return responses[token]

    def patch_stack(self):
        """Enter all handler patches; returns (ExitStack, zlm mock)."""
        spy_state, self.states = _make_attach_spy_state(self.pgd)
        mock_zlm = MagicMock()
        mock_zlm.acquire.return_value = "/lock/pool1"
        nc = MagicMock()
        nc.is_two_node.return_value = False
        patches = [
            patch.object(
                self.pgd, "create_scrolled_dialog", return_value=(self.fake_dlg, MagicMock())
            ),
            patch.object(self.pgd, "_AttachState", spy_state),
            patch.object(self.pgd, "node_config", nc),
            patch.object(self.pgd.Gtk, "MessageDialog", self.msg_dialog),
            patch.object(self.pgd, "scrub_blocks_pool_op", return_value=None),
            patch.object(self.pgd, "zlm", mock_zlm),
        ]
        stack = contextlib.ExitStack()
        for p in patches:
            stack.enter_context(p)
        return stack, mock_zlm


@contextlib.contextmanager
def _attach_handler_session(pgd, app, driver):
    """Drive the attach handler and keep its patches active for completion."""
    stack, mock_zlm = driver.patch_stack()
    try:
        with capture_logs():
            pgd.on_disks_attach_device(app)
        yield mock_zlm
    finally:
        stack.close()


class TestAttachPureHelpers(unittest.TestCase):
    """Attach decision helpers, no dialogs required."""

    def test_problems_require_a_pool(self):
        pgd = _import_dialogs()
        state = _attach_state(pgd, pool_name="")
        self.assertEqual(pgd._attach_problems(state, _caps()), ["Select a pool"])

    def test_problems_require_a_target(self):
        pgd = _import_dialogs()
        state = _attach_state(pgd, target=None)
        self.assertEqual(
            pgd._attach_problems(state, _caps()),
            ["Select a target member or raidz group in the topology tree"],
        )

    def test_problems_surface_classification_error(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        state = _attach_state(
            pgd, topologies={"pool1": raidz}, target=raidz.children[0].children[0]
        )
        problems = pgd._attach_problems(state, _caps())
        self.assertTrue(any("raidz group itself" in p for p in problems), problems)
        self.assertEqual(state.kind, "")

    def test_problems_require_exactly_one_disk(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _attach_state(
            pgd,
            topologies={"pool1": stripe},
            target=stripe.children[0],
            selected=[],
        )
        self.assertEqual(
            pgd._attach_problems(state, _caps()),
            ["Select exactly one eligible disk"],
        )

    def test_problems_refuse_ineligible_disk(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        member, bad = _disk("/dev/sdz"), _disk("/dev/sda")
        eligibility = [
            EligibilityResult(
                disk=bad, eligible=False, reasons=["already a pool member"], warnings=[]
            )
        ]
        state = _attach_state(
            pgd,
            topologies={"pool1": stripe},
            target=stripe.children[0],
            selected=[bad],
            disks=[member, bad],
            eligibility=eligibility,
        )
        self.assertEqual(pgd._attach_problems(state, _caps()), ["already a pool member"])

    def test_problems_surface_builder_value_error(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        member = _disk("/dev/sdz")
        bad = _disk("/dev/sda", by_id="bad disk")
        state = _attach_state(
            pgd,
            topologies={"pool1": stripe},
            target=stripe.children[0],
            selected=[bad],
            disks=[member, bad],
        )
        problems = pgd._attach_problems(state, _caps())
        self.assertTrue(any("/dev/disk/by-id" in p for p in problems), problems)
        self.assertEqual(state.command, [])

    def test_raidz_gating_enabled_disabled_pair(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        for supports, expected in (
            (True, []),
            (False, ["requires OpenZFS 2.3+"]),
        ):
            with self.subTest(supports=supports):
                state = _attach_state(
                    pgd,
                    topologies={"pool1": raidz},
                    target=raidz.children[0],
                    typed="pool1",
                )
                self.assertEqual(pgd._attach_problems(state, _caps(supports=supports)), expected)

    def test_raidz_disabled_leaves_no_command(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        state = _attach_state(
            pgd, topologies={"pool1": raidz}, target=raidz.children[0], typed="pool1"
        )
        self.assertEqual(
            pgd._attach_problems(state, _caps(supports=False)),
            ["requires OpenZFS 2.3+"],
        )
        self.assertEqual(state.command, [])

    def test_gated_raidz_group_greys_its_children(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        state = _attach_state(pgd, topologies={"pool1": raidz})
        store = _FakeTreeStore()
        pgd._populate_target_store(store, state, _caps(supports=False))
        # Rows: pool root, raidz2-0 group, four child disks.
        self.assertEqual(len(store.rows), 6)
        fg = pgd._TCOL_FG
        # The pool root row is not greyed.
        self.assertIsNone(store.rows[0][1][fg])
        # The group row carries the greyed foreground and the requires() text.
        group_row = store.rows[1][1]
        self.assertEqual(group_row[fg], pgd._INELIGIBLE_FG)
        self.assertIn("requires OpenZFS 2.3+", group_row[pgd._TCOL_STATE])
        # Child disks inherit the greyed foreground but keep their own status.
        for _parent, row in store.rows[2:]:
            self.assertEqual(row[fg], pgd._INELIGIBLE_FG)
            self.assertEqual(row[pgd._TCOL_STATE], "ONLINE")

    def test_supported_raidz_group_leaves_children_normal(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        state = _attach_state(pgd, topologies={"pool1": raidz})
        store = _FakeTreeStore()
        pgd._populate_target_store(store, state, _caps(supports=True))
        for _parent, row in store.rows:
            self.assertIsNone(row[pgd._TCOL_FG])
            self.assertEqual(row[pgd._TCOL_STATE], "ONLINE")

    def test_target_store_shows_member_sizes(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        disks = [_disk("/dev/sdz"), _disk("/dev/sdy")]
        state = _attach_state(pgd, topologies={"pool1": mirror}, disks=disks)
        store = _FakeTreeStore()
        pgd._populate_target_store(store, state, _caps())
        rows = [row for _parent, row in store.rows]
        size = pgd._TCOL_SIZE
        # Pool root and mirror group carry the summed size of both members.
        self.assertEqual(rows[0][size], "1.82 TiB")
        self.assertEqual(rows[1][size], "1.82 TiB")
        # Leaf rows show the individual member sizes.
        self.assertEqual(rows[2][size], "931.32 GiB")
        self.assertEqual(rows[3][size], "931.32 GiB")

    def test_target_store_size_dash_for_unresolved_member(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        disks = [_disk("/dev/sdz")]  # sdy missing from the inventory
        state = _attach_state(pgd, topologies={"pool1": mirror}, disks=disks, selected=disks)
        store = _FakeTreeStore()
        pgd._populate_target_store(store, state, _caps())
        rows = [row for _parent, row in store.rows]
        size = pgd._TCOL_SIZE
        self.assertEqual(rows[2][size], "931.32 GiB")
        self.assertEqual(rows[3][size], "-")
        # The group sum counts only the resolved member.
        self.assertEqual(rows[1][size], "931.32 GiB")

    def test_stripe_to_mirror_command(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _attach_state(pgd, topologies={"pool1": stripe}, target=stripe.children[0])
        self.assertEqual(pgd._attach_problems(state, _caps()), [])
        self.assertEqual(
            state.command,
            [
                "zpool",
                "attach",
                "pool1",
                "/dev/disk/by-id/ata-TESTsdz",
                "/dev/disk/by-id/ata-TESTsda",
            ],
        )
        self.assertEqual(state.kind, pgd.ATTACH_STRIPE_TO_MIRROR)

    def test_mirror_grow_command(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        disks = [_disk("/dev/sdz"), _disk("/dev/sdy"), _disk("/dev/sda")]
        state = _attach_state(
            pgd,
            topologies={"pool1": mirror},
            target=mirror.children[0].children[0],
            selected=[disks[2]],
            disks=disks,
        )
        self.assertEqual(pgd._attach_problems(state, _caps()), [])
        self.assertEqual(
            state.command,
            [
                "zpool",
                "attach",
                "pool1",
                "/dev/disk/by-id/ata-TESTsdz",
                "/dev/disk/by-id/ata-TESTsda",
            ],
        )
        self.assertEqual(state.kind, pgd.ATTACH_MIRROR_GROW)

    def test_raidz_enabled_builds_expansion_command(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        state = _attach_state(
            pgd, topologies={"pool1": raidz}, target=raidz.children[0], typed="pool1"
        )
        self.assertEqual(pgd._attach_problems(state, _caps(supports=True)), [])
        self.assertEqual(
            state.command,
            ["zpool", "attach", "pool1", "raidz2-0", "/dev/disk/by-id/ata-TESTsda"],
        )
        self.assertEqual(state.kind, pgd.ATTACH_RAIDZ_EXPANSION)

    def test_typed_confirmation_required_only_for_raidz(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _attach_state(
            pgd, topologies={"pool1": stripe}, target=stripe.children[0], typed=""
        )
        self.assertEqual(pgd._attach_problems(state, _caps()), [])
        raidz = _raidz_topology()
        state = _attach_state(pgd, topologies={"pool1": raidz}, target=raidz.children[0], typed="")
        self.assertEqual(
            pgd._attach_problems(state, _caps(supports=True)),
            ["Type the pool name 'pool1' to confirm"],
        )

    def test_typed_required_helper(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _attach_state(pgd, target=stripe.children[0])
        self.assertFalse(pgd._attach_typed_required(state))
        raidz = _raidz_topology()
        state = _attach_state(pgd, topologies={"pool1": raidz}, target=raidz.children[0])
        self.assertTrue(pgd._attach_typed_required(state))
        state = _attach_state(pgd, target=None)
        self.assertFalse(pgd._attach_typed_required(state))

    def test_warnings_stripe_converts_to_mirror(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _attach_state(pgd, topologies={"pool1": stripe}, target=stripe.children[0])
        warnings = pgd._attach_warnings(state)
        self.assertTrue(any("converts the stripe" in w for w in warnings), warnings)

    def test_warnings_stripe_hint_points_to_add_data_vdev(self):
        """Attaching to a stripe member always mirrors it; the hint names the
        capacity-growth path (a new top-level stripe vdev via Add Data Vdev)."""
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _attach_state(pgd, topologies={"pool1": stripe}, target=stripe.children[0])
        warnings = pgd._attach_warnings(state)
        self.assertTrue(
            any("Add Data Vdev with the stripe topology" in w for w in warnings), warnings
        )
        self.assertTrue(any("top-level stripe vdev" in w for w in warnings), warnings)

    def test_warnings_mirror_grow_counts_members(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        state = _attach_state(
            pgd, topologies={"pool1": mirror}, target=mirror.children[0].children[0]
        )
        warnings = pgd._attach_warnings(state)
        self.assertTrue(any("from 2 to 3" in w for w in warnings), warnings)

    def test_warnings_raidz_carry_expansion_notes(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        state = _attach_state(pgd, topologies={"pool1": raidz}, target=raidz.children[0])
        warnings = pgd._attach_warnings(state)
        self.assertTrue(any("data:parity ratio" in w for w in warnings), warnings)
        self.assertTrue(any("Rewrite Data" in w for w in warnings), warnings)

    def test_warnings_include_disk_warnings(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        disks = [
            _disk("/dev/sdz"),
            _disk("/dev/sda", transport="usb"),
            _disk("/dev/sdb"),
        ]
        state = _attach_state(
            pgd, topologies={"pool1": stripe}, target=stripe.children[0], disks=disks
        )
        warnings = pgd._attach_warnings(state)
        self.assertTrue(any("USB" in w for w in warnings), warnings)

    def test_confirm_text_per_kind(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _attach_state(pgd, topologies={"pool1": stripe}, target=stripe.children[0])
        primary, secondary = pgd._attach_confirm_text(state)
        self.assertIn("pool1", primary)
        self.assertIn("converts the stripe vdev into a mirror", secondary)
        mirror = _mirror_topology()
        state = _attach_state(
            pgd,
            topologies={"pool1": mirror},
            target=mirror.children[0].children[0],
        )
        _primary, secondary = pgd._attach_confirm_text(state)
        self.assertIn("another member of the mirror", secondary)


class TestAttachSignalHandlers(unittest.TestCase):
    """Attach target-tree and single-select disk picker handlers."""

    def test_target_selection_updates_state(self):
        pgd = _import_dialogs()
        node = _stripe_topology().children[0]
        store = FakeListStoreIterable([[node.name, "disk", "ONLINE", None, node]])
        state = _attach_state(pgd)
        calls = []
        selection = MagicMock()
        selection.get_selected.return_value = (store, _Iter(0))
        pgd._on_target_changed(selection, store, state, lambda: calls.append(1))
        self.assertIs(state.target, node)
        selection.get_selected.return_value = (store, None)
        pgd._on_target_changed(selection, store, state, lambda: calls.append(1))
        self.assertIsNone(state.target)
        self.assertEqual(len(calls), 2)

    def test_single_toggle_untoggles_other_rows(self):
        pgd = _import_dialogs()
        disks = [_disk("/dev/sda"), _disk("/dev/sdb")]
        results = _eligible(disks)
        state = pgd._AttachState(
            pools=["pool1"],
            pool_name="pool1",
            topologies={"pool1": _stripe_topology()},
            eligibility=results,
            disks=disks,
        )
        store = FakeListStoreIterable(
            [
                [True, "ata-TESTsda", "10T", "", "sata", "eligible", True, None],
                [False, "ata-TESTsdb", "10T", "", "sata", "eligible", True, None],
            ]
        )
        pgd._on_disk_toggled(None, 1, store, state, lambda: None, single=True)
        self.assertFalse(store.get_value(_Iter(0), pgd._COL_USE))
        self.assertTrue(store.get_value(_Iter(1), pgd._COL_USE))
        self.assertEqual(state.selected, [disks[1]])


class TestAttachHandlerGuards(unittest.TestCase):
    """Early-return guards in on_disks_attach_device."""

    def test_two_node_compute_host_bails(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_attach_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_attach_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("storage host" in line for line in logs), logs)

    def test_runner_busy_bails(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        app.dataset_runner.running = True
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_attach_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_attach_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("already running" in line for line in logs), logs)

    def test_no_imported_pools_bails(self):
        pgd = _import_dialogs()
        app = _make_app(topologies={})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_attach_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_attach_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("No imported pools" in line for line in logs), logs)

    def test_no_eligible_disks_shows_info_dialog(self):
        pgd = _import_dialogs()
        disk = _disk("/dev/sdz")
        app = _make_app(disks=[disk], topologies={"pool1": POOL1_TOPOLOGY})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_attach_dialog") as dialog,
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            capture_logs(),
        ):
            pgd.on_disks_attach_device(app)
        dialog.assert_not_called()
        msg_dialog.assert_called_once()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_dialog_cancel_runs_nothing(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _AttachDriver(pgd, [CANCEL])
        with _attach_handler_session(pgd, app, driver):
            pass
        self.assertEqual(app.dataset_runner.steps, [])


class TestAttachDialogFlow(unittest.TestCase):
    """End-to-end handler flow with a scripted Attach dialog."""

    def test_stripe_happy_path_attaches(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _AttachDriver(
            pgd, [_pick_stripe_target], message_response=pgd.Gtk.ResponseType.YES
        )
        with _attach_handler_session(pgd, app, driver) as mock_zlm:
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(
                step.command,
                [
                    "zpool",
                    "attach",
                    "pool1",
                    "/dev/disk/by-id/ata-TESTsdz",
                    "/dev/disk/by-id/ata-TESTsda",
                ],
            )
            self.assertTrue(step.fatal)
            self.assertEqual(step.description, "Expand vdev in pool pool1")
            mock_zlm.acquire.assert_called_once_with("pool1", "w", "Expand vdev in pool1")
            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        app._disks_inventory_cache.invalidate.assert_called_once()
        self.assertTrue(app._importable_pool_cache.invalidate.called)

    def test_no_response_cancels(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _AttachDriver(
            pgd, [_pick_stripe_target, CANCEL], message_response=pgd.Gtk.ResponseType.NO
        )
        with _attach_handler_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_raidz_typed_happy_path_expands(self):
        pgd = _import_dialogs()
        app = _raidz_app()
        app.ctx.zfs_caps.supports.return_value = True
        app.ctx.zfs_caps.requires.return_value = "requires OpenZFS 2.3+"
        driver = _AttachDriver(pgd, [_pick_raidz_target])
        with _attach_handler_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(
                step.command,
                ["zpool", "attach", "pool1", "raidz2-0", "/dev/disk/by-id/ata-TESTsdx"],
            )
            # RAIDZ expansion confirms via typed entry, not a YES/NO dialog.
            driver.msg_dialog.assert_not_called()
            mock_zlm.acquire.assert_called_once_with("pool1", "w", "Expand vdev in pool1")
            app.dataset_runner.finish()
        self.assertTrue(any("Expanded vdev in pool 'pool1'" in line for line in logs), logs)
        self.assertTrue(any("Rewrite Data" in line for line in logs), logs)

    def test_raidz_typed_mismatch_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _raidz_app()
        app.ctx.zfs_caps.supports.return_value = True
        app.ctx.zfs_caps.requires.return_value = "requires OpenZFS 2.3+"

        def _mistype(state):
            _pick_raidz_target(state)
            state.typed = "wrongpool"
            return CONFIRM

        driver = _AttachDriver(pgd, [_mistype, CANCEL])
        with _attach_handler_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_scrub_block_keeps_dialog_open(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _AttachDriver(
            pgd,
            [_pick_stripe_target, CANCEL],
            message_response=pgd.Gtk.ResponseType.YES,
        )
        spy_state, driver.states = _make_attach_spy_state(pgd)
        mock_zlm = MagicMock()
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(
                pgd, "create_scrolled_dialog", return_value=(driver.fake_dlg, MagicMock())
            ),
            patch.object(pgd, "_AttachState", spy_state),
            patch.object(pgd, "node_config", nc),
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            patch.object(
                pgd,
                "scrub_blocks_pool_op",
                return_value="pool 'pool1' has a scrub scanning",
            ) as scrub_mock,
            patch.object(pgd, "zlm", mock_zlm),
            capture_logs(),
        ):
            msg_dialog.return_value.run.return_value = pgd.Gtk.ResponseType.YES
            pgd.on_disks_attach_device(app)
        # YES/NO warning answered YES, scrub refusal shown, then cancel ran.
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(msg_dialog.call_count, 2)
        scrub_mock.assert_called_once_with("pool1", app.ctx.zfs_repository)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_happy_path_cancelled_logs_info(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _AttachDriver(
            pgd, [_pick_stripe_target], message_response=pgd.Gtk.ResponseType.YES
        )
        with _attach_handler_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            app.dataset_runner.finish(cancelled=True)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        self.assertTrue(any("cancelled" in line for line in logs), logs)


# ---------------------------------------------------------------------------
# Replace dialog fixtures
# ---------------------------------------------------------------------------


def _replace_state(
    pgd,
    topologies=None,
    target=None,
    selected=None,
    typed="",
    disks=None,
    eligibility=None,
    **overrides,
):
    """Build a Replace dialog state around a pool1 topology."""
    disks = (
        disks if disks is not None else [_disk("/dev/sdz"), _disk("/dev/sda"), _disk("/dev/sdb")]
    )
    if eligibility is None:
        eligibility = _eligible(disks)
    topologies = topologies if topologies is not None else {"pool1": _stripe_topology()}
    if selected is None:
        selected = [disks[1]]
    state = pgd._ReplaceState(
        pools=["pool1"],
        pool_name="pool1",
        topologies=topologies,
        eligibility=eligibility,
        disks=disks,
        target=target,
        selected=selected,
        typed=typed,
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def _pick_replace_target(state):
    state.target = state.topologies["pool1"].children[0]
    state.selected = [state.disks[1]]
    state.typed = "pool1"
    return CONFIRM


def _make_replace_spy_state(pgd):
    """Return a (spy class, states list) pair capturing replace dialog states."""
    states = []

    class _SpyState(pgd._ReplaceState):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            states.append(self)

    return _SpyState, states


class _ReplaceDriver:
    """Drives the Replace dialog through a scripted response sequence.

    Same contract as ``_AttachDriver``; *message_response* is what the info
    dialog (scrub refusal) returns from run().
    """

    def __init__(self, pgd, script, message_response=None):
        self.pgd = pgd
        self.script = list(script)
        self.runs_seen = []
        self.states = []
        self.fake_dlg = MagicMock()
        self.fake_dlg.run.side_effect = self._respond
        self.msg_dialog = MagicMock()
        if message_response is not None:
            self.msg_dialog.return_value.run.return_value = message_response

    def _respond(self):
        state = self.states[0]
        self.runs_seen.append(state.pool_name)
        step = self.script.pop(0)
        token = step(state) if callable(step) else step
        responses = {
            CONFIRM: self.pgd._RESPONSE_CONFIRM,
            CANCEL: self.pgd.Gtk.ResponseType.CANCEL,
        }
        return responses[token]

    def patch_stack(self):
        """Enter all handler patches; returns (ExitStack, zlm mock)."""
        spy_state, self.states = _make_replace_spy_state(self.pgd)
        mock_zlm = MagicMock()
        mock_zlm.acquire.return_value = "/lock/pool1"
        nc = MagicMock()
        nc.is_two_node.return_value = False
        patches = [
            patch.object(
                self.pgd, "create_scrolled_dialog", return_value=(self.fake_dlg, MagicMock())
            ),
            patch.object(self.pgd, "_ReplaceState", spy_state),
            patch.object(self.pgd, "node_config", nc),
            patch.object(self.pgd.Gtk, "MessageDialog", self.msg_dialog),
            patch.object(self.pgd, "scrub_blocks_pool_op", return_value=None),
            patch.object(self.pgd, "zlm", mock_zlm),
        ]
        stack = contextlib.ExitStack()
        for p in patches:
            stack.enter_context(p)
        return stack, mock_zlm


@contextlib.contextmanager
def _replace_handler_session(pgd, app, driver):
    """Drive the replace handler and keep its patches active for completion."""
    stack, mock_zlm = driver.patch_stack()
    try:
        with capture_logs():
            pgd.on_disks_replace_device(app)
        yield mock_zlm
    finally:
        stack.close()


class TestReplacePureHelpers(unittest.TestCase):
    """Replace decision helpers, no dialogs required."""

    def test_problems_require_a_pool(self):
        pgd = _import_dialogs()
        state = _replace_state(pgd, pool_name="")
        self.assertEqual(pgd._replace_problems(state), ["Select a pool"])

    def test_problems_require_a_target(self):
        pgd = _import_dialogs()
        state = _replace_state(pgd, target=None)
        self.assertEqual(
            pgd._replace_problems(state),
            ["Select the pool member to replace in the topology tree"],
        )

    def test_problems_surface_classification_error(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        state = _replace_state(
            pgd, topologies={"pool1": raidz}, target=raidz.children[0], typed="pool1"
        )
        problems = pgd._replace_problems(state)
        self.assertTrue(any("vdev group" in p for p in problems), problems)

    def test_problems_require_exactly_one_disk(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _replace_state(
            pgd,
            topologies={"pool1": stripe},
            target=stripe.children[0],
            selected=[],
            typed="pool1",
        )
        self.assertEqual(pgd._replace_problems(state), ["Select exactly one eligible disk"])

    def test_problems_refuse_same_device(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        source = _disk("/dev/sdz")
        state = _replace_state(
            pgd,
            topologies={"pool1": stripe},
            target=stripe.children[0],
            selected=[source],  # the source member itself
            disks=[source, _disk("/dev/sda")],
            typed="pool1",
        )
        problems = pgd._replace_problems(state)
        self.assertTrue(any("same device" in p for p in problems), problems)

    def test_problems_refuse_ineligible_disk(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        member, bad = _disk("/dev/sdz"), _disk("/dev/sda")
        eligibility = [
            EligibilityResult(
                disk=bad, eligible=False, reasons=["already a pool member"], warnings=[]
            )
        ]
        state = _replace_state(
            pgd,
            topologies={"pool1": stripe},
            target=stripe.children[0],
            selected=[bad],
            disks=[member, bad],
            eligibility=eligibility,
            typed="pool1",
        )
        self.assertEqual(pgd._replace_problems(state), ["already a pool member"])

    def test_typed_confirmation_always_required(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _replace_state(
            pgd, topologies={"pool1": stripe}, target=stripe.children[0], typed=""
        )
        self.assertEqual(
            pgd._replace_problems(state),
            ["Type the pool name 'pool1' to confirm"],
        )

    def test_stripe_replace_command(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _replace_state(
            pgd, topologies={"pool1": stripe}, target=stripe.children[0], typed="pool1"
        )
        self.assertEqual(pgd._replace_problems(state), [])
        self.assertEqual(
            state.command,
            [
                "zpool",
                "replace",
                "pool1",
                "/dev/disk/by-id/ata-TESTsdz",
                "/dev/disk/by-id/ata-TESTsda",
            ],
        )

    def test_raidz_member_replace_command(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        disks = [_disk(f"/dev/sd{c}") for c in "abcd"] + [_disk("/dev/sdx")]
        state = _replace_state(
            pgd,
            topologies={"pool1": raidz},
            target=raidz.children[0].children[1],
            selected=[disks[4]],
            disks=disks,
            typed="pool1",
        )
        self.assertEqual(pgd._replace_problems(state), [])
        self.assertEqual(
            state.command,
            [
                "zpool",
                "replace",
                "pool1",
                "/dev/disk/by-id/ata-TESTsdb",
                "/dev/disk/by-id/ata-TESTsdx",
            ],
        )

    def test_warnings_smaller_replacement_present_but_not_problem(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        disks = [
            _disk("/dev/sdz", size_bytes=10 * TB, size_human="10T"),
            _disk("/dev/sda", size_bytes=5 * TB, size_human="5T"),
        ]
        state = _replace_state(
            pgd,
            topologies={"pool1": stripe},
            target=stripe.children[0],
            disks=disks,
            typed="pool1",
        )
        self.assertEqual(pgd._replace_problems(state), [])
        warnings = pgd._replace_warnings(state)
        self.assertTrue(any("smaller" in w for w in warnings), warnings)

    def test_warnings_carry_resilver_note(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _replace_state(
            pgd, topologies={"pool1": stripe}, target=stripe.children[0], typed="pool1"
        )
        warnings = pgd._replace_warnings(state)
        self.assertTrue(any("resilvering" in w for w in warnings), warnings)
        self.assertTrue(any("Watch window" in w for w in warnings), warnings)

    def test_warnings_empty_without_selection(self):
        pgd = _import_dialogs()
        state = _replace_state(pgd, target=None)
        self.assertEqual(pgd._replace_warnings(state), [])


class TestReplaceHandlerGuards(unittest.TestCase):
    """Early-return guards in on_disks_replace_device."""

    def test_two_node_compute_host_bails(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_replace_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_replace_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("storage host" in line for line in logs), logs)

    def test_runner_busy_bails(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        app.dataset_runner.running = True
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_replace_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_replace_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("already running" in line for line in logs), logs)

    def test_no_imported_pools_bails(self):
        pgd = _import_dialogs()
        app = _make_app(topologies={})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_replace_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_replace_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("No imported pools" in line for line in logs), logs)

    def test_no_eligible_disks_shows_info_dialog(self):
        pgd = _import_dialogs()
        disk = _disk("/dev/sdz")
        app = _make_app(disks=[disk], topologies={"pool1": POOL1_TOPOLOGY})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_replace_dialog") as dialog,
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            capture_logs(),
        ):
            pgd.on_disks_replace_device(app)
        dialog.assert_not_called()
        msg_dialog.assert_called_once()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_dialog_cancel_runs_nothing(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _ReplaceDriver(pgd, [CANCEL])
        with _replace_handler_session(pgd, app, driver):
            pass
        self.assertEqual(app.dataset_runner.steps, [])


class TestReplaceDialogFlow(unittest.TestCase):
    """End-to-end handler flow with a scripted Replace dialog."""

    def test_happy_path_replaces(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _ReplaceDriver(pgd, [_pick_replace_target])
        with _replace_handler_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(
                step.command,
                [
                    "zpool",
                    "replace",
                    "pool1",
                    "/dev/disk/by-id/ata-TESTsdz",
                    "/dev/disk/by-id/ata-TESTsda",
                ],
            )
            self.assertTrue(step.fatal)
            self.assertEqual(step.description, "Replace device in pool pool1")
            # Replace confirms via typed entry, not a YES/NO dialog.
            driver.msg_dialog.assert_not_called()
            mock_zlm.acquire.assert_called_once_with("pool1", "w", "Replace device in pool1")
            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        app._disks_inventory_cache.invalidate.assert_called_once()
        self.assertTrue(app._importable_pool_cache.invalidate.called)
        self.assertTrue(any("Replaced device in pool 'pool1'" in line for line in logs), logs)
        self.assertTrue(any("Watch window" in line for line in logs), logs)

    def test_typed_mismatch_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _stripe_app()

        def _mistype(state):
            _pick_replace_target(state)
            state.typed = "wrongpool"
            return CONFIRM

        driver = _ReplaceDriver(pgd, [_mistype, CANCEL])
        with _replace_handler_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_scrub_block_keeps_dialog_open(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _ReplaceDriver(pgd, [_pick_replace_target, CANCEL])
        spy_state, driver.states = _make_replace_spy_state(pgd)
        mock_zlm = MagicMock()
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(
                pgd, "create_scrolled_dialog", return_value=(driver.fake_dlg, MagicMock())
            ),
            patch.object(pgd, "_ReplaceState", spy_state),
            patch.object(pgd, "node_config", nc),
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            patch.object(
                pgd,
                "scrub_blocks_pool_op",
                return_value="pool 'pool1' has a scrub scanning",
            ) as scrub_mock,
            patch.object(pgd, "zlm", mock_zlm),
            capture_logs(),
        ):
            msg_dialog.return_value.run.return_value = pgd.Gtk.ResponseType.OK
            pgd.on_disks_replace_device(app)
        self.assertEqual(len(driver.runs_seen), 2)
        msg_dialog.assert_called_once()
        scrub_mock.assert_called_once_with("pool1", app.ctx.zfs_repository)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_happy_path_cancelled_logs_info(self):
        pgd = _import_dialogs()
        app = _stripe_app()
        driver = _ReplaceDriver(pgd, [_pick_replace_target])
        with _replace_handler_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            app.dataset_runner.finish(cancelled=True)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        self.assertTrue(any("cancelled" in line for line in logs), logs)


# ---------------------------------------------------------------------------
# Detach dialog fixtures
# ---------------------------------------------------------------------------


def _detach_state(pgd, topologies=None, target=None, typed="", disks=None, **overrides):
    """Build a Detach dialog state around a pool1 topology."""
    disks = (
        disks if disks is not None else [_disk("/dev/sdz"), _disk("/dev/sdy"), _disk("/dev/sda")]
    )
    topologies = topologies if topologies is not None else {"pool1": _mirror_topology()}
    state = pgd._DetachState(
        pools=["pool1"],
        pool_name="pool1",
        topologies=topologies,
        disks=disks,
        target=target,
        typed=typed,
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def _pick_detach_target(state):
    mirror = state.topologies["pool1"].children[0]
    state.target = mirror.children[0]
    state.typed = "pool1"
    return CONFIRM


def _make_detach_spy_state(pgd):
    """Return a (spy class, states list) pair capturing detach dialog states."""
    states = []

    class _SpyState(pgd._DetachState):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            states.append(self)

    return _SpyState, states


class _DetachDriver:
    """Drives the Detach dialog through a scripted response sequence.

    Same contract as ``_ReplaceDriver``; *message_response* is what the info
    dialog (scrub refusal) returns from run().
    """

    def __init__(self, pgd, script, message_response=None):
        self.pgd = pgd
        self.script = list(script)
        self.runs_seen = []
        self.states = []
        self.fake_dlg = MagicMock()
        self.fake_dlg.run.side_effect = self._respond
        self.msg_dialog = MagicMock()
        if message_response is not None:
            self.msg_dialog.return_value.run.return_value = message_response

    def _respond(self):
        state = self.states[0]
        self.runs_seen.append(state.pool_name)
        step = self.script.pop(0)
        token = step(state) if callable(step) else step
        responses = {
            CONFIRM: self.pgd._RESPONSE_CONFIRM,
            CANCEL: self.pgd.Gtk.ResponseType.CANCEL,
        }
        return responses[token]

    def patch_stack(self):
        """Enter all handler patches; returns (ExitStack, zlm mock)."""
        spy_state, self.states = _make_detach_spy_state(self.pgd)
        mock_zlm = MagicMock()
        mock_zlm.acquire.return_value = "/lock/pool1"
        nc = MagicMock()
        nc.is_two_node.return_value = False
        patches = [
            patch.object(
                self.pgd, "create_scrolled_dialog", return_value=(self.fake_dlg, MagicMock())
            ),
            patch.object(self.pgd, "_DetachState", spy_state),
            patch.object(self.pgd, "node_config", nc),
            patch.object(self.pgd.Gtk, "MessageDialog", self.msg_dialog),
            patch.object(self.pgd, "scrub_blocks_pool_op", return_value=None),
            patch.object(self.pgd, "zlm", mock_zlm),
        ]
        stack = contextlib.ExitStack()
        for p in patches:
            stack.enter_context(p)
        return stack, mock_zlm


@contextlib.contextmanager
def _detach_handler_session(pgd, app, driver):
    """Drive the detach handler and keep its patches active for completion."""
    stack, mock_zlm = driver.patch_stack()
    try:
        with capture_logs():
            pgd.on_disks_detach_device(app)
        yield mock_zlm
    finally:
        stack.close()


def _mirror_app():
    """App mock: pool1 is a two-way mirror of sdz/sdy; sda is free."""
    disks = [_disk("/dev/sdz"), _disk("/dev/sdy"), _disk("/dev/sda")]
    return _make_app(disks=disks, topologies={"pool1": _mirror_topology()})


class TestDetachPureHelpers(unittest.TestCase):
    """Detach decision helpers, no dialogs required."""

    def test_problems_require_a_pool(self):
        pgd = _import_dialogs()
        state = _detach_state(pgd, pool_name="")
        self.assertEqual(pgd._detach_problems(state), ["Select a pool"])

    def test_problems_require_a_target(self):
        pgd = _import_dialogs()
        state = _detach_state(pgd, target=None)
        self.assertEqual(
            pgd._detach_problems(state),
            ["Select the mirror member to detach in the topology tree"],
        )

    def test_problems_no_target_mirrorless_pool(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _detach_state(pgd, topologies={"pool1": stripe}, target=None)
        self.assertEqual(
            pgd._detach_problems(state),
            ["Pool 'pool1' has no mirror members to detach"],
        )

    def test_detach_targets_grey_everything_but_mirror_members(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        disks = [_disk("/dev/sdz"), _disk("/dev/sdy")]
        state = _detach_state(pgd, topologies={"pool1": mirror}, disks=disks)
        store = _FakeTreeStore()
        pgd._populate_target_store(store, state, _caps(), gate_raidz=False, detach_targets=True)
        rows = [row for _parent, row in store.rows]
        fg = pgd._TCOL_FG
        # Pool root and the mirror group row are not detachable targets.
        self.assertEqual(rows[0][fg], pgd._INELIGIBLE_FG)
        self.assertEqual(rows[1][fg], pgd._INELIGIBLE_FG)
        # Only the mirror member disks stay selectable.
        self.assertIsNone(rows[2][fg])
        self.assertIsNone(rows[3][fg])

    def test_problems_refuse_raidz_member(self):
        pgd = _import_dialogs()
        raidz = _raidz_topology()
        disks = [_disk(f"/dev/sd{c}") for c in "abcd"]
        state = _detach_state(
            pgd,
            topologies={"pool1": raidz},
            target=raidz.children[0].children[0],
            disks=disks,
            typed="pool1",
        )
        problems = pgd._detach_problems(state)
        self.assertTrue(any("raidz" in p for p in problems), problems)

    def test_problems_refuse_stripe_member(self):
        pgd = _import_dialogs()
        stripe = _stripe_topology()
        state = _detach_state(
            pgd, topologies={"pool1": stripe}, target=stripe.children[0], typed="pool1"
        )
        problems = pgd._detach_problems(state)
        self.assertTrue(any("non-redundant stripe" in p for p in problems), problems)

    def test_problems_refuse_pool_root(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        state = _detach_state(pgd, topologies={"pool1": mirror}, target=mirror, typed="pool1")
        problems = pgd._detach_problems(state)
        self.assertTrue(any("not the pool itself" in p for p in problems), problems)

    def test_problems_refuse_vdev_group(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        state = _detach_state(
            pgd, topologies={"pool1": mirror}, target=mirror.children[0], typed="pool1"
        )
        problems = pgd._detach_problems(state)
        self.assertTrue(any("disk member" in p for p in problems), problems)

    def test_problems_refuse_unresolvable_member(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        # Inventory has no row matching the member path.
        state = _detach_state(
            pgd,
            topologies={"pool1": mirror},
            target=mirror.children[0].children[0],
            disks=[],
            typed="pool1",
        )
        problems = pgd._detach_problems(state)
        self.assertTrue(any("by-id" in p for p in problems), problems)

    def test_typed_confirmation_always_required(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        state = _detach_state(
            pgd, topologies={"pool1": mirror}, target=mirror.children[0].children[0], typed=""
        )
        self.assertEqual(
            pgd._detach_problems(state),
            ["Type the pool name 'pool1' to confirm"],
        )

    def test_mirror_detach_command(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        state = _detach_state(
            pgd, topologies={"pool1": mirror}, target=mirror.children[0].children[0], typed="pool1"
        )
        self.assertEqual(pgd._detach_problems(state), [])
        self.assertEqual(
            state.command,
            ["zpool", "detach", "pool1", "/dev/disk/by-id/ata-TESTsdz"],
        )

    def test_warnings_carry_redundancy_notes(self):
        pgd = _import_dialogs()
        mirror = _mirror_topology()
        state = _detach_state(
            pgd, topologies={"pool1": mirror}, target=mirror.children[0].children[0], typed="pool1"
        )
        warnings = pgd._detach_warnings(state)
        self.assertTrue(any("reduces redundancy" in w for w in warnings), warnings)
        self.assertTrue(any("non-redundant disk" in w for w in warnings), warnings)

    def test_warnings_empty_without_selection(self):
        pgd = _import_dialogs()
        state = _detach_state(pgd, target=None)
        self.assertEqual(pgd._detach_warnings(state), [])


class TestDetachHandlerGuards(unittest.TestCase):
    """Early-return guards in on_disks_detach_device."""

    def test_two_node_compute_host_bails(self):
        pgd = _import_dialogs()
        app = _mirror_app()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_detach_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_detach_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("storage host" in line for line in logs), logs)

    def test_no_mirror_members_bails(self):
        pgd = _import_dialogs()
        app = _make_app(disks=[_disk("/dev/sdz")], topologies={"pool1": _stripe_topology()})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_detach_dialog") as dialog,
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            capture_logs(),
        ):
            pgd.on_disks_detach_device(app)
        dialog.assert_not_called()
        msg_dialog.assert_called_once()

    def test_runner_busy_bails(self):
        pgd = _import_dialogs()
        app = _mirror_app()
        app.dataset_runner.running = True
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_detach_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_detach_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("already running" in line for line in logs), logs)

    def test_no_imported_pools_bails(self):
        pgd = _import_dialogs()
        app = _make_app(topologies={})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_detach_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_detach_device(app)
        dialog.assert_not_called()
        self.assertTrue(any("No imported pools" in line for line in logs), logs)

    def test_proceeds_when_every_disk_is_a_pool_member(self):
        """Detach frees a disk; the handler must not require eligible disks."""
        pgd = _import_dialogs()
        member = _disk("/dev/sdz")
        app = _make_app(disks=[member], topologies={"pool1": _mirror_topology()})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_detach_dialog", return_value=None) as dialog,
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            capture_logs(),
        ):
            pgd.on_disks_detach_device(app)
        dialog.assert_called_once()
        msg_dialog.assert_not_called()


class TestDetachDialogFlow(unittest.TestCase):
    """End-to-end handler flow with a scripted Detach dialog."""

    def test_happy_path_detaches(self):
        pgd = _import_dialogs()
        app = _mirror_app()
        driver = _DetachDriver(pgd, [_pick_detach_target])
        with _detach_handler_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(
                step.command,
                ["zpool", "detach", "pool1", "/dev/disk/by-id/ata-TESTsdz"],
            )
            self.assertTrue(step.fatal)
            self.assertEqual(step.description, "Detach device from pool pool1")
            # Detach confirms via typed entry, not a YES/NO dialog.
            driver.msg_dialog.assert_not_called()
            mock_zlm.acquire.assert_called_once_with("pool1", "w", "Detach device from pool1")
            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        app._disks_inventory_cache.invalidate.assert_called_once()
        self.assertTrue(app._importable_pool_cache.invalidate.called)
        self.assertTrue(any("Detached device from pool 'pool1'" in line for line in logs), logs)

    def test_typed_mismatch_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _mirror_app()

        def _mistype(state):
            _pick_detach_target(state)
            state.typed = "wrongpool"
            return CONFIRM

        driver = _DetachDriver(pgd, [_mistype, CANCEL])
        with _detach_handler_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_scrub_block_keeps_dialog_open(self):
        pgd = _import_dialogs()
        app = _mirror_app()
        driver = _DetachDriver(pgd, [_pick_detach_target, CANCEL])
        spy_state, driver.states = _make_detach_spy_state(pgd)
        mock_zlm = MagicMock()
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(
                pgd, "create_scrolled_dialog", return_value=(driver.fake_dlg, MagicMock())
            ),
            patch.object(pgd, "_DetachState", spy_state),
            patch.object(pgd, "node_config", nc),
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            patch.object(
                pgd,
                "scrub_blocks_pool_op",
                return_value="pool 'pool1' has a scrub scanning",
            ) as scrub_mock,
            patch.object(pgd, "zlm", mock_zlm),
            capture_logs(),
        ):
            msg_dialog.return_value.run.return_value = pgd.Gtk.ResponseType.OK
            pgd.on_disks_detach_device(app)
        self.assertEqual(len(driver.runs_seen), 2)
        msg_dialog.assert_called_once()
        scrub_mock.assert_called_once_with("pool1", app.ctx.zfs_repository)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_dialog_cancel_runs_nothing(self):
        pgd = _import_dialogs()
        app = _mirror_app()
        driver = _DetachDriver(pgd, [CANCEL])
        with _detach_handler_session(pgd, app, driver):
            pass
        self.assertEqual(app.dataset_runner.steps, [])

    def test_happy_path_cancelled_logs_info(self):
        pgd = _import_dialogs()
        app = _mirror_app()
        driver = _DetachDriver(pgd, [_pick_detach_target])
        with _detach_handler_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            app.dataset_runner.finish(cancelled=True)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        self.assertTrue(any("cancelled" in line for line in logs), logs)


# ---------------------------------------------------------------------------
# Add Infrastructure Vdev fixtures
# ---------------------------------------------------------------------------


def _infra_state(pgd, pools=None, disks=None, kind="special", **overrides):
    """Build an Infra-Vdev dialog state with all eligible disks selected."""
    disks = disks if disks is not None else [_disk("/dev/sda"), _disk("/dev/sdb")]
    results = _eligible(disks)
    pools = pools if pools is not None else ["pool1"]
    state = pgd._InfraVdevState(
        pools=pools,
        pool_name=pools[0] if pools else "",
        eligibility=results,
        kind=kind,
        selected=[r.disk for r in results if r.eligible],
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def _make_infra_spy_state(pgd):
    """Return a (spy class, states list) pair capturing infra dialog states."""
    states = []

    class _SpyState(pgd._InfraVdevState):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            states.append(self)

    return _SpyState, states


class _InfraDriver:
    """Drives the Infra-Vdev dialog through a scripted response sequence."""

    def __init__(self, pgd, script):
        self.pgd = pgd
        self.script = list(script)
        self.runs_seen = []
        self.states = []
        self.yes_no_dialog = None
        self.fake_dlg = MagicMock()
        self.fake_dlg.run.side_effect = self._respond

    def _respond(self):
        state = self.states[0]
        self.runs_seen.append(state.pool_name)
        step = self.script.pop(0)
        token = step(state) if callable(step) else step
        responses = {
            CONFIRM: self.pgd._RESPONSE_CONFIRM,
            CANCEL: self.pgd.Gtk.ResponseType.CANCEL,
        }
        return responses[token]


def _infra_handler(pgd, app, driver, yes_no=True, scrub_blocker=None):
    """Run on_disks_add_infra_vdev with a scripted dialog.

    Returns (zlm mock, patch ExitStack, yes/no dialog mock); the caller must
    keep the stack alive until runner completion.
    """
    spy_state, driver.states = _make_infra_spy_state(pgd)
    mock_zlm = MagicMock()
    mock_zlm.acquire.return_value = "/lock/pool1"
    nc = MagicMock()
    nc.is_two_node.return_value = False
    yes_no_dialog = MagicMock(return_value=yes_no)
    patches = [
        patch.object(pgd, "create_scrolled_dialog", return_value=(driver.fake_dlg, MagicMock())),
        patch.object(pgd, "_InfraVdevState", spy_state),
        patch.object(pgd, "node_config", nc),
        patch.object(pgd.Gtk, "MessageDialog"),
        patch.object(pgd, "scrub_blocks_pool_op", return_value=scrub_blocker),
        patch.object(pgd, "zlm", mock_zlm),
        patch.object(pgd, "_show_yes_no_dialog", yes_no_dialog),
    ]
    stack = contextlib.ExitStack()
    for p in patches:
        stack.enter_context(p)
    with capture_logs():
        pgd.on_disks_add_infra_vdev(app)
    driver.yes_no_dialog = yes_no_dialog
    return mock_zlm, stack, yes_no_dialog


@contextlib.contextmanager
def _infra_session(pgd, app, driver, yes_no=True):
    """Drive the handler and keep its patches active for runner completion."""
    mock_zlm, stack, _yes_no = _infra_handler(pgd, app, driver, yes_no=yes_no)
    try:
        yield mock_zlm
    finally:
        stack.close()


class TestInfraPureHelpers(unittest.TestCase):
    """Infra-vdev decision helpers, no dialogs required."""

    def test_problems_require_a_pool(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, pools=[])
        self.assertEqual(pgd._infra_problems(state), ["Select a pool"])

    def test_problems_require_a_selection(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, selected=[])
        self.assertEqual(pgd._infra_problems(state), ["Select at least one eligible disk"])

    def test_problems_refuse_ineligible_disk(self):
        pgd = _import_dialogs()
        disk = _disk("/dev/sdz")
        results = _eligible([disk], imported={"pool9": ["/dev/sdz"]})
        state = _infra_state(pgd, disks=[disk], eligibility=results)
        problems = pgd._infra_problems(state)
        self.assertTrue(any("member of imported pool 'pool9'" in p for p in problems), problems)

    def test_special_requires_a_mirror(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, disks=[_disk("/dev/sda")], kind="special")
        problems = pgd._infra_problems(state)
        self.assertTrue(any("special vdev must be a mirror" in p for p in problems), problems)

    def test_cache_cannot_be_a_mirror(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, kind="cache")  # two disks -> mirror
        problems = pgd._infra_problems(state)
        self.assertTrue(any("cache vdevs cannot be mirrored" in p for p in problems))

    def test_unknown_kind_refused(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, kind="dedup")
        problems = pgd._infra_problems(state)
        self.assertTrue(any("unknown infrastructure vdev kind" in p for p in problems))

    def test_typed_confirmation_required_for_special_only(self):
        pgd = _import_dialogs()
        special = _infra_state(pgd, kind="special")
        self.assertIn("Type the pool name 'pool1' to confirm", pgd._infra_problems(special))
        special.typed = "pool1"
        self.assertEqual(pgd._infra_problems(special), [])

    def test_checkbox_required_for_log_only(self):
        pgd = _import_dialogs()
        log = _infra_state(pgd, kind="log")
        self.assertIn("Check the acknowledgment box to confirm", pgd._infra_problems(log))
        log.checked = True
        self.assertEqual(pgd._infra_problems(log), [])

    def test_cache_needs_no_extra_confirmation(self):
        pgd = _import_dialogs()
        cache = _infra_state(pgd, disks=[_disk("/dev/sda")], kind="cache")
        self.assertEqual(pgd._infra_problems(cache), [])

    def test_topology_auto_derived_from_selection(self):
        pgd = _import_dialogs()
        self.assertEqual(pgd._infra_topology([]), "stripe")
        self.assertEqual(pgd._infra_topology([_disk("/dev/sda")]), "stripe")
        self.assertEqual(pgd._infra_topology([_disk("/dev/sda"), _disk("/dev/sdb")]), "mirror")

    def test_special_mirror_command(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, kind="special", typed="pool1")
        self.assertEqual(
            pgd.build_infra_argv(state),
            [
                "zpool",
                "add",
                "pool1",
                "special",
                "mirror",
                "/dev/disk/by-id/ata-TESTsda",
                "/dev/disk/by-id/ata-TESTsdb",
            ],
        )

    def test_log_stripe_command_has_no_mirror_keyword(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, disks=[_disk("/dev/sda")], kind="log", checked=True)
        self.assertEqual(
            pgd.build_infra_argv(state),
            ["zpool", "add", "pool1", "log", "/dev/disk/by-id/ata-TESTsda"],
        )

    def test_log_mirror_command(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, kind="log", checked=True)
        self.assertEqual(
            pgd.build_infra_argv(state),
            [
                "zpool",
                "add",
                "pool1",
                "log",
                "mirror",
                "/dev/disk/by-id/ata-TESTsda",
                "/dev/disk/by-id/ata-TESTsdb",
            ],
        )

    def test_cache_command(self):
        pgd = _import_dialogs()
        state = _infra_state(pgd, disks=[_disk("/dev/sda")], kind="cache")
        self.assertEqual(
            pgd.build_infra_argv(state),
            ["zpool", "add", "pool1", "cache", "/dev/disk/by-id/ata-TESTsda"],
        )

    def test_warnings_carry_kind_notes(self):
        pgd = _import_dialogs()
        special = pgd._infra_warnings(_infra_state(pgd, kind="special"))
        self.assertTrue(any("loses the entire pool" in w for w in special), special)
        cache = pgd._infra_warnings(_infra_state(pgd, disks=[_disk("/dev/sda")], kind="cache"))
        self.assertTrue(any("read cache" in w for w in cache), cache)

    def test_warnings_single_log_mentions_failure(self):
        pgd = _import_dialogs()
        warnings = pgd._infra_warnings(_infra_state(pgd, disks=[_disk("/dev/sda")], kind="log"))
        self.assertTrue(any("if it fails" in w or "failure" in w for w in warnings))

    def test_warnings_include_mixed_sizes(self):
        pgd = _import_dialogs()
        disks = [_disk("/dev/sda"), _disk("/dev/sdb", size_bytes=2 * TB)]
        state = _infra_state(pgd, disks=disks, kind="special", typed="pool1")
        self.assertTrue(any("differ in size" in w for w in pgd._infra_warnings(state)))

    def test_checkbox_label_adapts_to_topology(self):
        pgd = _import_dialogs()
        single = _infra_state(pgd, disks=[_disk("/dev/sda")], kind="log", checked=True)
        self.assertIn("single log device", pgd._infra_checkbox_label(single))
        mirrored = _infra_state(pgd, kind="log", checked=True)
        self.assertIn("holds no pool data", pgd._infra_checkbox_label(mirrored))


class TestInfraHandlerGuards(unittest.TestCase):
    """Early-return guards in on_disks_add_infra_vdev."""

    def test_two_node_compute_host_bails(self):
        pgd = _import_dialogs()
        app = _make_app()
        nc = MagicMock()
        nc.is_two_node.return_value = True
        nc.is_storage_host.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_add_infra_vdev_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_add_infra_vdev(app)
        dialog.assert_not_called()
        self.assertEqual(app.dataset_runner.steps, [])
        self.assertTrue(any("storage host" in line for line in logs), logs)

    def test_runner_busy_bails(self):
        pgd = _import_dialogs()
        app = _make_app()
        app.dataset_runner.running = True
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_add_infra_vdev_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_add_infra_vdev(app)
        dialog.assert_not_called()
        self.assertTrue(any("already running" in line for line in logs), logs)

    def test_no_imported_pools_bails(self):
        pgd = _import_dialogs()
        app = _make_app(topologies={})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_add_infra_vdev_dialog") as dialog,
            capture_logs() as logs,
        ):
            pgd.on_disks_add_infra_vdev(app)
        dialog.assert_not_called()
        self.assertTrue(any("No imported pools" in line for line in logs), logs)

    def test_no_eligible_disks_shows_info_dialog(self):
        pgd = _import_dialogs()
        disk = _disk("/dev/sdz")
        app = _make_app(disks=[disk], topologies={"pool1": POOL1_TOPOLOGY})
        nc = MagicMock()
        nc.is_two_node.return_value = False
        with (
            patch.object(pgd, "node_config", nc),
            patch.object(pgd, "show_add_infra_vdev_dialog") as dialog,
            patch.object(pgd.Gtk, "MessageDialog") as msg_dialog,
            capture_logs(),
        ):
            pgd.on_disks_add_infra_vdev(app)
        dialog.assert_not_called()
        msg_dialog.assert_called_once()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_dialog_cancel_runs_nothing(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _InfraDriver(pgd, [CANCEL])
        with _infra_session(pgd, app, driver):
            pass
        self.assertEqual(app.dataset_runner.steps, [])


class TestInfraDialogFlow(unittest.TestCase):
    """End-to-end handler flow with a scripted Infra-Vdev dialog."""

    def test_special_happy_path_adds_vdev(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _InfraDriver(
            pgd,
            [lambda state: (_select_all(state), _confirm(state), CONFIRM)[2]],
        )
        with _infra_session(pgd, app, driver) as mock_zlm:
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(
                step.command,
                [
                    "zpool",
                    "add",
                    "pool1",
                    "special",
                    "mirror",
                    "/dev/disk/by-id/ata-TESTsda",
                    "/dev/disk/by-id/ata-TESTsdb",
                ],
            )
            self.assertTrue(step.fatal)
            self.assertEqual(step.description, "Add special vdev to pool pool1")
            mock_zlm.acquire.assert_called_once_with("pool1", "w", "Add special vdev to pool1")
            driver.yes_no_dialog.assert_not_called()
            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        app._disks_inventory_cache.invalidate.assert_called_once()
        self.assertTrue(app._importable_pool_cache.invalidate.called)

    def test_log_happy_path_requires_checkbox(self):
        pgd = _import_dialogs()
        app = _make_app()

        def _ack(state):
            state.kind = "log"
            state.checked = True
            _select_all(state)
            return CONFIRM

        driver = _InfraDriver(pgd, [_ack])
        with _infra_session(pgd, app, driver) as mock_zlm:
            step = app.dataset_runner.steps[0]
            self.assertEqual(
                step.command,
                [
                    "zpool",
                    "add",
                    "pool1",
                    "log",
                    "mirror",
                    "/dev/disk/by-id/ata-TESTsda",
                    "/dev/disk/by-id/ata-TESTsdb",
                ],
            )
            self.assertEqual(step.description, "Add log vdev to pool pool1")
            driver.yes_no_dialog.assert_not_called()
            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/pool1")

    def test_log_without_checkbox_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _InfraDriver(
            pgd,
            [
                lambda state: (
                    setattr(state, "kind", "log"),
                    _select_all(state),
                    CONFIRM,
                )[2],
                CANCEL,
            ],
        )
        with _infra_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_cache_happy_path_asks_yes_no(self):
        pgd = _import_dialogs()
        app = _make_app(disks=[_disk("/dev/sda")])
        driver = _InfraDriver(
            pgd,
            [
                lambda state: (
                    setattr(state, "kind", "cache"),
                    _select_all(state),
                    CONFIRM,
                )[2]
            ],
        )
        with _infra_session(pgd, app, driver, yes_no=True) as mock_zlm:
            step = app.dataset_runner.steps[0]
            self.assertEqual(
                step.command,
                ["zpool", "add", "pool1", "cache", "/dev/disk/by-id/ata-TESTsda"],
            )
            self.assertEqual(step.description, "Add cache vdev to pool pool1")
            driver.yes_no_dialog.assert_called_once()
            app.dataset_runner.finish()
            mock_zlm.release.assert_called_once_with("/lock/pool1")

    def test_cache_no_answer_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _make_app(disks=[_disk("/dev/sda")])
        driver = _InfraDriver(
            pgd,
            [
                lambda state: (
                    setattr(state, "kind", "cache"),
                    _select_all(state),
                    CONFIRM,
                )[2],
                CANCEL,
            ],
        )
        with _infra_session(pgd, app, driver, yes_no=False):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        driver.yes_no_dialog.assert_called_once()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_special_typed_mismatch_blocks_confirm(self):
        pgd = _import_dialogs()
        app = _make_app()

        def _mistype(state):
            _select_all(state)
            state.typed = "wrongpool"
            return CONFIRM

        driver = _InfraDriver(pgd, [_mistype, CANCEL])
        with _infra_session(pgd, app, driver):
            pass
        self.assertEqual(len(driver.runs_seen), 2)
        self.assertEqual(app.dataset_runner.steps, [])

    def test_scrub_block_keeps_dialog_open(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _InfraDriver(
            pgd,
            [
                lambda state: (_select_all(state), _confirm(state), CONFIRM)[2],
                CANCEL,
            ],
        )
        mock_zlm, stack, _yes_no = _infra_handler(
            pgd,
            app,
            driver,
            scrub_blocker="pool 'pool1' has a scrub scanning",
        )
        with stack:
            pass
        # Confirm was refused, the info dialog was shown, then cancel ran.
        self.assertEqual(len(driver.runs_seen), 2)
        mock_zlm.acquire.assert_not_called()
        self.assertEqual(app.dataset_runner.steps, [])

    def test_happy_path_cancelled_logs_info(self):
        pgd = _import_dialogs()
        app = _make_app()
        driver = _InfraDriver(
            pgd,
            [lambda state: (_select_all(state), _confirm(state), CONFIRM)[2]],
        )
        with _infra_session(pgd, app, driver) as mock_zlm, capture_logs() as logs:
            app.dataset_runner.finish(cancelled=True)
            mock_zlm.release.assert_called_once_with("/lock/pool1")
        self.assertTrue(any("cancelled" in line for line in logs), logs)
