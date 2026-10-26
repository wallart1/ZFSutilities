"""Tests for alignment_page.py — the Alignment view of the Performance page.

Covers the Live Charts / Blocksize Alignment view switcher built into memory_page,
the sample-application helpers (chain, findings, workload, memory-tier
readouts), per-source degrade notes, the survey dialog from
alignment_dialogs, the in-place row reconciliation that keeps the page
scroll-stable, and the save/restore of the page's vertical offset around
every apply.
"""

import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import alignment_stats as astats
import config_core
from alignment_guestfs import GuestFsEntry
from disk_repository import format_bytes
from memory_stats import format_percent
from test_support import mock_gtk, temp_config_dir
from zfs_repository import TopologyNode

# Pool-member paths shared by _topology() and _pool(): the sample model
# flattens the same tree into PoolAlignment.members, so the fixture keeps
# them in sync the way collect_alignment_sample produces them.
_MIRROR_A = "/dev/disk/by-id/ata-WDC_WD80EDAZ-11"
_MIRROR_B = "/dev/disk/by-id/ata-WDC_WD80EDAZ-12"
_SLOG_DISK = "/dev/disk/by-id/ata-SLOG-1"
_L2_DISK = "/dev/disk/by-id/ata-L2-1"


def _member(path="/dev/disk/by-id/ata-WDC_WD80EDAZ-11"):
    return astats.MemberDisk(path=path, logical_sector=512, physical_sector=4096)


def _topo_node(name, vdev_type, children=None):
    return TopologyNode(
        name=name,
        vdev_type=vdev_type,
        state="ONLINE" if vdev_type == "disk" else "-",
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=children or [],
    )


def _topology():
    """NVME1's vdev tree: a data mirror plus log and cache classes."""
    return _topo_node(
        "NVME1",
        "pool",
        [
            _topo_node(
                "mirror-0", "mirror", [_topo_node(_MIRROR_A, "disk"), _topo_node(_MIRROR_B, "disk")]
            ),
            _topo_node("logs", "log", [_topo_node(_SLOG_DISK, "disk")]),
            _topo_node("cache", "cache", [_topo_node(_L2_DISK, "disk")]),
        ],
    )


def _pool():
    return astats.PoolAlignment(
        name="NVME1",
        ashift_configured="12",
        ashift_effective=12,
        topology=_topology(),
        members=[_member(path) for path in (_MIRROR_A, _MIRROR_B, _SLOG_DISK, _L2_DISK)],
        has_cache=True,
    )


def _hist():
    hist = astats.ReqHistogram(pool="NVME1")
    hist.add(4096, "ind", "sync_write", 2000)
    hist.add(1024**2, "agg", "async_read", 8000)
    return hist


def _datasets():
    return [
        astats.DatasetBlocks(
            name="NVME1/backups",
            kind="filesystem",
            recordsize="128K",
            recordsize_source="local",
        ),
        astats.DatasetBlocks(
            name="NVME1/vm-201-disk-0",
            kind="volume",
            volblocksize="16K",
            volblocksize_source="-",
        ),
    ]


def _arc():
    return {
        "demand_data_hits": 900,
        "demand_data_misses": 100,
        "demand_metadata_hits": 950,
        "demand_metadata_misses": 50,
        "prefetch_data_hits": 600,
        "prefetch_data_misses": 400,
        "mru_hits": 300,
        "mfu_hits": 700,
        "mru_ghost_hits": 10,
        "mfu_ghost_hits": 20,
        "evict_l2_cached": 100,
        "evict_l2_ineligible": 300,
        "evict_l2_eligible": 600,
        "l2_hits": 1000,
        "l2_read_bytes": 4 * 1024**2,
    }


def _sample(**overrides):
    values = {
        "monotonic": 100.0,
        "pools": [_pool()],
        "datasets": _datasets(),
        "histograms": {"NVME1": _hist()},
        "vm_disks": {
            "vm-201-disk-0": astats.VMOption(
                vmid="201",
                disknum="0",
                bus="scsi0",
                options={"discard": "1", "iothread": "1"},
            )
        },
        "arc": _arc(),
        "prefetch": {"hits": 900, "misses": 100},
        # Per-dataset objset counters: 4K average writes on both datasets
        # (128K recordsize / 16K volblocksize), above the per-dataset op
        # floor — the observed-size findings' fixture.
        "objset": {
            "NVME1/backups": {
                "reads": 4000,
                "nread": 4000 * 4096,
                "writes": 4000,
                "nwritten": 4000 * 4096,
            },
            "NVME1/vm-201-disk-0": {
                "reads": 4000,
                "nread": 4000 * 4096,
                "writes": 4000,
                "nwritten": 4000 * 4096,
            },
        },
        "objset_available": True,
        "pools_available": True,
        "datasets_available": True,
        "iostat_r_available": True,
        "arcstats_available": True,
        "prefetch_available": True,
        "pve_available": True,
    }
    values.update(overrides)
    return astats.AlignmentSample(**values)


def _make_app():
    """Return a mock app with a real config dict, ready for the page build."""
    app = MagicMock()
    app.config = {}
    app.ctx = MagicMock()
    app.ctx.zfs_caps = None
    return app


class _FakeRow:
    """One store row; the row object doubles as its GTK iter (node-stable)."""

    def __init__(self, values):
        self.values = list(values)


class _FakeStore:
    """Gtk.ListStore stand-in with node-stable iters and change journaling.

    Iters are the row objects themselves, so removing one row leaves every
    other iter pointing at its own row — the ListStore guarantee the
    reconcile algorithm relies on. ``inserted``/``removed`` journal the
    structural changes so tests can prove rows were updated in place
    rather than rebuilt.
    """

    def __init__(self, rows=None):
        self.rows = [_FakeRow(row) for row in (rows or [])]
        self.inserted = []
        self.appended = []
        self.removed = []

    def get_iter_first(self):
        return self.rows[0] if self.rows else None

    def iter_next(self, it):
        index = self.rows.index(it)
        return self.rows[index + 1] if index + 1 < len(self.rows) else None

    def get_value(self, it, col):
        return it.values[col]

    def set_value(self, it, col, val):
        it.values[col] = val

    def insert(self, position, row):
        new = _FakeRow(row)
        self.rows.insert(position, new)
        self.inserted.append(new)

    def append(self, row):
        new = _FakeRow(row)
        self.rows.append(new)
        self.appended.append(new)

    def remove(self, it):
        self.rows.remove(it)
        self.removed.append(it)

    def keys(self):
        return [row.values[0] for row in self.rows]

    def layer_object_keys(self):
        """(Layer, Object) pairs — the visible identity of chain-table rows."""
        return [(row.values[1], row.values[2]) for row in self.rows]

    def set_sorted(self, column=1):
        """Pretend the user clicked a column sort (PyGObject answers a
        (column, order) tuple; see _reconcile_rows)."""
        self._sort_state = (column, 0)

    def get_sort_column_id(self):
        return getattr(self, "_sort_state", None)


class _PageTestCase(unittest.TestCase):
    """Shared page-build fixture with distinct widget mocks.

    Gtk.Label, Gtk.ListStore, Gtk.Box, and Gtk.RadioButton get side
    effects so every widget instance is its own mock (the shared defaults
    would merge the two view radios, the chain/findings/workload stores,
    and every value label into single objects).
    """

    def _prepared(self, config=None):
        app = _make_app()
        if config is not None:
            app.config = config
        with mock_gtk(fresh=True) as gtk:
            gtk.Label = MagicMock(side_effect=lambda *a, **k: MagicMock())
            gtk.ListStore = MagicMock(side_effect=lambda *a, **k: MagicMock())
            gtk.Box = MagicMock(side_effect=lambda *a, **k: MagicMock())
            gtk.RadioButton = MagicMock()
            gtk.RadioButton.new_with_label_from_widget = MagicMock(
                side_effect=lambda *a, **k: MagicMock()
            )
            import memory_page as mp

            mp.create_memory_page(app)
            import alignment_page as ap

            self.ap = ap
        self.mp = mp
        for attr in (
            "_alignment_chain_store",
            "_alignment_topology_store",
            "_alignment_findings_store",
            "_alignment_workload_store",
        ):
            getattr(app, attr).get_iter_first.return_value = None
        return mp, ap, app


class TestPerformanceViewSwitcher(_PageTestCase):
    """The Live Charts / Blocksize Alignment radio switcher on the Performance page."""

    def test_switcher_radios_present(self):
        _mp, _ap, app = self._prepared()
        radios = app._memory_view_radios
        self.assertEqual(set(radios), {"charts", "alignment"})
        self.assertIsNot(radios["charts"], radios["alignment"])
        for radio in radios.values():
            toggled_handlers = [call.args[0] for call in radio.connect.call_args_list if call.args]
            self.assertIn("toggled", toggled_handlers)

    def test_stack_children_named(self):
        _mp, _ap, app = self._prepared()
        named = [call.args[1] for call in app._memory_view_stack.add_named.call_args_list]
        self.assertEqual(named, ["charts", "alignment"])

    def test_saved_view_restored(self):
        config = {"ui_state": {"performance_view": {"view": "alignment"}}}
        _mp, _ap, app = self._prepared(config)
        app._memory_view_radios["alignment"].set_active.assert_called_once_with(True)
        visible = [
            call.args[0] for call in app._memory_view_stack.set_visible_child_name.call_args_list
        ]
        self.assertIn("alignment", visible)

    def test_invalid_saved_view_falls_back_to_charts(self):
        config = {"ui_state": {"performance_view": {"view": "bogus"}}}
        _mp, _ap, app = self._prepared(config)
        app._memory_view_radios["charts"].set_active.assert_called_once_with(True)

    def test_toggle_switches_stack_and_persists(self):
        mp, _ap, app = self._prepared()
        radios = app._memory_view_radios
        radios["charts"].get_active.return_value = False
        radios["alignment"].get_active.return_value = True
        # Drop the build-phase view restoration from the call history.
        app._memory_view_stack.set_visible_child_name.reset_mock()
        with temp_config_dir():
            mp._on_memory_view_radio_toggled(radios["alignment"], app)
            with open(config_core.CONFIG_PATH) as f:
                on_disk = json.load(f)
        app._memory_view_stack.set_visible_child_name.assert_called_once_with("alignment")
        self.assertEqual(
            app.config.get("ui_state", {}).get("performance_view", {}).get("view"),
            "alignment",
        )
        # The view choice is persisted as a UI-state-only disk write.
        self.assertEqual(
            on_disk.get("ui_state", {}).get("performance_view", {}).get("view"),
            "alignment",
        )

    def test_toggle_ignored_while_deactivating(self):
        """The radio that is turning off must not re-switch the view."""
        mp, _ap, app = self._prepared()
        radios = app._memory_view_radios
        radios["charts"].get_active.return_value = False
        radios["alignment"].get_active.return_value = False
        # Drop the build-phase view restoration from the call history.
        app._memory_view_stack.set_visible_child_name.reset_mock()
        with patch("config_core.save_ui_state") as save:
            mp._on_memory_view_radio_toggled(radios["charts"], app)
        save.assert_not_called()
        app._memory_view_stack.set_visible_child_name.assert_not_called()

    def _map_handler(self, app):
        """Return the one "map" handler the view stack registered."""
        handlers = [
            call.args[1]
            for call in app._memory_view_stack.connect.call_args_list
            if call.args and call.args[0] == "map"
        ]
        self.assertEqual(len(handlers), 1)
        return handlers[0]

    def test_stack_map_reasserts_dropped_restore(self):
        """A pre-realization restore that GTK dropped is re-applied at map.

        set_visible_child_name() before the stack is shown is dropped by
        GTK and the stack falls back to its first child, so the "map"
        handler must re-point the visible child at the active radio —
        otherwise the Alignment button can be active while Live Charts is
        shown.
        """
        config = {"ui_state": {"performance_view": {"view": "alignment"}}}
        _mp, _ap, app = self._prepared(config)
        radios = app._memory_view_radios
        radios["charts"].get_active.return_value = False
        radios["alignment"].get_active.return_value = True
        # GTK dropped the build-time restore and fell back to "charts".
        app._memory_view_stack.get_visible_child_name.return_value = "charts"
        app._memory_view_stack.set_visible_child_name.reset_mock()
        self._map_handler(app)(app._memory_view_stack, app)
        app._memory_view_stack.set_visible_child_name.assert_called_once_with("alignment")

    def test_stack_map_noop_when_in_sync(self):
        """A map with matching radio and visible child re-asserts nothing."""
        config = {"ui_state": {"performance_view": {"view": "charts"}}}
        _mp, _ap, app = self._prepared(config)
        radios = app._memory_view_radios
        radios["charts"].get_active.return_value = True
        radios["alignment"].get_active.return_value = False
        app._memory_view_stack.get_visible_child_name.return_value = "charts"
        app._memory_view_stack.set_visible_child_name.reset_mock()
        self._map_handler(app)(app._memory_view_stack, app)
        app._memory_view_stack.set_visible_child_name.assert_not_called()

    def test_dispatcher_routes_to_alignment_view(self):
        mp, _ap, app = self._prepared()
        radios = app._memory_view_radios
        radios["charts"].get_active.return_value = False
        radios["alignment"].get_active.return_value = True
        with (
            patch.object(mp, "refresh_alignment_view") as refresh,
            patch.object(mp.threading, "Thread") as thread,
        ):
            mp.refresh_memory_page(app)
        refresh.assert_called_once_with(app)
        thread.assert_not_called()

    def test_dispatcher_charts_view_refreshes_charts(self):
        mp, _ap, app = self._prepared()
        radios = app._memory_view_radios
        radios["charts"].get_active.return_value = True
        radios["alignment"].get_active.return_value = False
        with patch.object(mp.threading, "Thread") as thread:
            mp.refresh_memory_page(app)
        thread.assert_called_once()

    def test_alignment_refresh_pending_guard(self):
        _mp, ap, app = self._prepared()
        app._alignment_refresh_pending = True
        with patch.object(ap.threading, "Thread") as thread:
            ap.refresh_alignment_view(app)
        thread.assert_not_called()


class TestAlignmentRefreshingIndicator(_PageTestCase):
    """The alignment refresh drives the Performance page's 'Refreshing' label.

    memory_page owns the label (it sits next to the refresh interval
    spinner on the shared controls row); the alignment path reaches it
    through the helper imported from memory_page at call time, so the
    assertions read the label mock on the shared app rather than patching
    the helper.
    """

    def test_refresh_shows_indicator(self):
        _mp, ap, app = self._prepared()
        with patch.object(ap.threading, "Thread"):
            ap.refresh_alignment_view(app)
        app.memory_refreshing_label.show.assert_called_once_with()
        self.assertTrue(app._alignment_refresh_pending)

    def test_finish_hides_indicator(self):
        _mp, ap, app = self._prepared()
        # The page build itself hides the label once; drop that history so
        # the assertions see only the refresh flow.
        app.memory_refreshing_label.reset_mock()

        class _SyncThread:
            """Thread stand-in that runs its target synchronously."""

            def __init__(self, target=None, daemon=False):
                self._target = target

            def start(self):
                self._target()

        idle_captured = []
        with (
            patch.object(ap.threading, "Thread", _SyncThread),
            patch.object(
                ap.GLib, "idle_add", side_effect=lambda fn, *a: idle_captured.append((fn, a)) or 1
            ),
            patch.object(ap, "collect_alignment_sample", return_value=object()),
        ):
            ap.refresh_alignment_view(app)
        finish_fn, finish_args = idle_captured[0]
        self.assertEqual(finish_fn.__name__, "_finish_refresh")
        with patch.object(ap, "_apply_alignment_sample"):
            self.assertFalse(finish_fn(*finish_args))
        app.memory_refreshing_label.hide.assert_called_once_with()
        self.assertFalse(app._alignment_refresh_pending)

    def test_pending_guard_leaves_indicator_untouched(self):
        _mp, ap, app = self._prepared()
        app.memory_refreshing_label.reset_mock()
        app._alignment_refresh_pending = True
        with patch.object(ap.threading, "Thread") as thread:
            ap.refresh_alignment_view(app)
        thread.assert_not_called()
        app.memory_refreshing_label.show.assert_not_called()
        app.memory_refreshing_label.hide.assert_not_called()


class TestApplyAlignmentSample(_PageTestCase):
    """_apply_alignment_sample against the built view widgets."""

    def test_chain_rows(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        rows = [c.args[1] for c in app._alignment_chain_store.insert.call_args_list]
        by_layer_object = {(row[1], row[2]): row for row in rows}
        self.assertEqual(
            by_layer_object[("Pool", "NVME1")][1:4],
            ["Pool", "NVME1", f"{format_bytes(4096)} (effective ashift 12)"],
        )
        self.assertEqual(by_layer_object[("Pool", "NVME1")][4], "configured ashift 12")
        self.assertEqual(
            by_layer_object[("Device", "ata-WDC_WD80EDAZ-11")][3:],
            [
                f"{format_bytes(512)} logical / {format_bytes(4096)} physical",
                "512e advanced format",
            ],
        )
        # Device rows display the short name but are keyed on the full path.
        device_key = by_layer_object[("Device", "ata-WDC_WD80EDAZ-11")][0]
        self.assertIn("/dev/disk/by-id/", device_key)
        self.assertEqual(
            by_layer_object[("Dataset", "NVME1/backups")][3:],
            ["recordsize 128K", "local"],
        )
        self.assertEqual(
            by_layer_object[("VM", "vm-201-disk-0")][3:],
            ["volblocksize 16K", "scsi0 discard iothread"],
        )

    def test_chain_pool_ashift_auto_and_unreadable(self):
        """Pool cells name auto-detected vs set vs unreadable ashift as data."""
        _mp, ap, app = self._prepared()
        auto_pool = astats.PoolAlignment(
            name="auto",
            ashift_configured="0",
            ashift_effective=9,
            members=[],
        )
        unreadable = astats.PoolAlignment(
            name="mute",
            ashift_configured=None,
            ashift_effective=None,
            members=[],
        )
        ap._apply_alignment_sample(
            app, _sample(pools=[auto_pool, unreadable], datasets=[], histograms={})
        )
        rows = [c.args[1] for c in app._alignment_chain_store.insert.call_args_list]
        by_object = {row[2]: row for row in rows if row[1] == "Pool"}
        self.assertEqual(by_object["auto"][3], f"{format_bytes(512)} (effective ashift 9)")
        self.assertEqual(by_object["auto"][4], "auto (ashift not configured)")
        self.assertEqual(by_object["mute"][3], "—")
        self.assertEqual(by_object["mute"][4], "ashift property unavailable")

    def test_chain_row_without_pve_options(self):
        _mp, ap, app = self._prepared()
        sample = _sample(vm_disks={})
        ap._apply_alignment_sample(app, sample)
        rows = [c.args[1] for c in app._alignment_chain_store.insert.call_args_list]
        vm_rows = [row for row in rows if row[1] == "VM"]
        # "PVE configs" without "local": on two-node installs the configs
        # arrive from the compute node, so the wording names the source set.
        self.assertEqual(vm_rows[0][4], "not referenced in PVE configs")

        sample = _sample(vm_disks={}, pve_available=False)
        ap._apply_alignment_sample(app, sample)
        vm_rows = [
            row.args[1]
            for row in app._alignment_chain_store.insert.call_args_list
            if row.args[1][1] == "VM"
        ]
        self.assertEqual(
            vm_rows[-1][4],
            "PVE configs unreadable (local directory and compute-node fetch both failed)",
        )

    def test_chain_reconcile_removes_vanished_rows(self):
        _mp, ap, app = self._prepared()
        fake = _FakeStore()
        app._alignment_chain_store = fake
        ap._apply_alignment_sample(app, _sample())
        self.assertTrue(fake.layer_object_keys())
        ap._apply_alignment_sample(app, _sample(pools=[], datasets=[]))
        self.assertEqual(fake.rows, [])
        # Pool + 4 member disks + dataset + VM rows were all live.
        self.assertEqual(len(fake.removed), 7)

    def test_findings_rows_with_severity_markers(self):
        _mp, ap, app = self._prepared()
        misaligned = astats.PoolAlignment(
            name="odd",
            ashift_configured="9",
            ashift_effective=9,
            members=[_member()],
        )
        sample = _sample(pools=[_pool(), misaligned])
        ap._apply_alignment_sample(app, sample)
        # The findings table reconciles in place: no clear-and-rebuild.
        app._alignment_findings_store.clear.assert_not_called()
        rows = [c.args[1] for c in app._alignment_findings_store.insert.call_args_list]
        self.assertTrue(rows)
        severities = [row[1] for row in rows]
        self.assertIn("⚠ WARN", severities)
        self.assertIn("✓ OK", severities)
        warn = next(row for row in rows if row[1] == "⚠ WARN")
        self.assertEqual(warn[2], "Pool")
        self.assertEqual(warn[3], "odd")
        self.assertIn("read-modify-write", warn[5])
        # Column 0 is the hidden identity key: rule key + subject.
        self.assertTrue(warn[0].endswith(":odd"))

    def test_findings_drift_updates_row_in_place(self):
        """Message drift (changing numbers) updates the same row identity."""
        _mp, ap, app = self._prepared()
        fake = _FakeStore()
        app._alignment_findings_store = fake
        ap._apply_alignment_sample(
            app, _sample(arc=dict(_arc(), mru_ghost_hits=150, mfu_ghost_hits=50))
        )
        first_keys = [row.values[0] for row in fake.rows]
        self.assertTrue(first_keys)

        # Ghost-hit share drifts: same findings, different message text.
        ap._apply_alignment_sample(
            app, _sample(arc=dict(_arc(), mru_ghost_hits=400, mfu_ghost_hits=500))
        )

        # Same rows, same order, same identities — only cells changed.
        self.assertEqual([row.values[0] for row in fake.rows], first_keys)
        self.assertEqual(len(fake.inserted), len(first_keys))  # first refresh only
        drifted = [row for row in fake.rows if "ghost hits" in row.values[4]]
        self.assertEqual(len(drifted), 1)
        self.assertIn("90%", drifted[0].values[4])

    def test_findings_include_per_dataset_observed_rows(self):
        """The objset sample yields per-dataset observed-size findings."""
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        rows = [c.args[1] for c in app._alignment_findings_store.insert.call_args_list]
        observed = [row for row in rows if row[0].startswith("obs-dataset-")]
        self.assertEqual(
            {row[0] for row in observed},
            {
                "obs-dataset-recordsize-rmw:NVME1/backups",
                "obs-dataset-volblocksize-rmw:NVME1/vm-201-disk-0",
            },
        )
        self.assertTrue(all("since boot" in row[4] for row in observed))

    def test_second_apply_switches_to_interval_basis_in_place(self):
        """The previous sample becomes the interval baseline, same rows."""
        _mp, ap, app = self._prepared()
        fake = _FakeStore()
        app._alignment_findings_store = fake
        ap._apply_alignment_sample(app, _sample())
        first_keys = [row.values[0] for row in fake.rows]
        later = _sample(
            monotonic=110.0,
            objset={
                # The interval added 800 ops of 512-byte traffic per side.
                "NVME1/backups": {
                    "reads": 4800,
                    "nread": 4000 * 4096 + 800 * 512,
                    "writes": 4800,
                    "nwritten": 4000 * 4096 + 800 * 512,
                },
                "NVME1/vm-201-disk-0": {
                    "reads": 4800,
                    "nread": 4000 * 4096 + 800 * 512,
                    "writes": 4800,
                    "nwritten": 4000 * 4096 + 800 * 512,
                },
            },
        )
        ap._apply_alignment_sample(app, later)
        # Same identities, updated in place (no inserts on the second apply).
        self.assertEqual([row.values[0] for row in fake.rows], first_keys)
        self.assertEqual(len(fake.inserted), len(first_keys))
        recordsize_row = next(
            row for row in fake.rows if row.values[0] == "obs-dataset-recordsize-rmw:NVME1/backups"
        )
        self.assertIn("over the last refresh interval", recordsize_row.values[4])
        self.assertIn("average 512", recordsize_row.values[4])

    def test_degrade_note_names_missing_objset_counters(self):
        """Missing objset kstats land in the note and a findings row."""
        _mp, ap, app = self._prepared()
        app._alignment_note.hide.reset_mock()
        ap._apply_alignment_sample(app, _sample(objset={}, objset_available=False))
        markup = app._alignment_note.set_markup.call_args[0][0]
        self.assertIn("per-dataset I/O counters", markup)
        self.assertIn("advice stays per-pool", markup)
        app._alignment_note.hide.assert_not_called()
        rows = [c.args[1] for c in app._alignment_findings_store.insert.call_args_list]
        limit_row = [row for row in rows if row[0] == "objset-unavailable:(all)"]
        self.assertEqual(len(limit_row), 1)
        self.assertIn("falls back to the per-pool histogram", limit_row[0][4])

    def test_workload_rows(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        rows = [c.args[1] for c in app._alignment_workload_store.insert.call_args_list]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row[0], "NVME1")
        self.assertEqual(row[1], "sequential")
        self.assertEqual(row[2], f"{format_bytes(4096)} (100%)")
        self.assertEqual(row[3], f"{format_bytes(1024**2)} (80%)")
        self.assertEqual(row[4], "10,000")
        self.assertEqual(row[5], format_percent(90.0))

    def test_workload_low_confidence_without_prefetch(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample(prefetch_available=False))
        rows = [c.args[1] for c in app._alignment_workload_store.insert.call_args_list]
        self.assertTrue(rows[0][1].endswith("(low confidence)"))

    def test_workload_no_histogram_row(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample(histograms={}))
        rows = [c.args[1] for c in app._alignment_workload_store.insert.call_args_list]
        self.assertEqual(rows[0][1], "unknown")
        self.assertEqual(rows[0][2], "—")
        self.assertEqual(rows[0][4], "—")

    def test_memory_readouts(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        labels = app._alignment_memory_labels
        labels["Demand data hit rate"].set_text.assert_called_with(format_percent(90.0))
        labels["Prefetch data hit rate"].set_text.assert_called_with(format_percent(60.0))
        labels["Prefetcher hit rate"].set_text.assert_called_with(format_percent(90.0))
        labels["Ghost hits (share of real)"].set_text.assert_called_with(format_percent(3.0))
        labels["Evictions eligible for L2ARC"].set_text.assert_called_with(format_percent(60.0))
        labels["Average L2 hit size"].set_text.assert_called_with(format_bytes(4 * 1024**2 / 1000))

    def test_all_sources_available_hides_note(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        app._alignment_note.hide.assert_called()
        app._alignment_note.set_markup.assert_not_called()

    def test_degrade_note_names_missing_sources(self):
        _mp, ap, app = self._prepared()
        # note_label() hides itself at construction; clear that history.
        app._alignment_note.hide.reset_mock()
        sample = _sample(
            iostat_r_available=False,
            pve_available=False,
        )
        ap._apply_alignment_sample(app, sample)
        markup = app._alignment_note.set_markup.call_args[0][0]
        self.assertIn("request-size histograms", markup)
        self.assertIn("PVE VM configs", markup)
        self.assertNotIn("ARC kstats", markup)
        app._alignment_note.hide.assert_not_called()

    def test_degrade_note_names_pools_with_dataset_read_failures(self):
        """Per-pool dataset failures are named, not treated as source-down."""
        _mp, ap, app = self._prepared()
        app._alignment_note.hide.reset_mock()
        sample = _sample(
            pools=[
                _pool(),
                astats.PoolAlignment(name="scratch", ashift_configured="12", ashift_effective=12),
            ],
            dataset_read_failures=["scratch"],
        )
        ap._apply_alignment_sample(app, sample)
        markup = app._alignment_note.set_markup.call_args[0][0]
        self.assertIn("Dataset block properties unreadable for: scratch", markup)
        self.assertNotIn("Unavailable on this host", markup)
        # The healthy pool's findings still render.
        rows = [c.args[1] for c in app._alignment_findings_store.insert.call_args_list]
        self.assertTrue(any(row[3] == "scratch" and "unreadable" in row[4] for row in rows))
        self.assertTrue(any(row[3] == "NVME1" for row in rows))


class TestTopologyRows(_PageTestCase):
    """The Pool Topology table: classes, groups, members, and degrade."""

    def test_topology_rows(self):
        """One row per vdev group, class-labelled, with the pool's ashift."""
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        rows = [c.args[1] for c in app._alignment_topology_store.insert.call_args_list]
        block = f"{format_bytes(4096)} (effective ashift 12)"
        self.assertEqual(
            rows,
            [
                [
                    "Topology:NVME1:mirror-0",
                    "NVME1",
                    "data",
                    "mirror-0",
                    "mirror",
                    "ata-WDC_WD80EDAZ-11, ata-WDC_WD80EDAZ-12",
                    block,
                ],
                [
                    f"Topology:NVME1:{_SLOG_DISK}",
                    "NVME1",
                    "log",
                    "ata-SLOG-1",
                    "disk",
                    "ata-SLOG-1",
                    block,
                ],
                [
                    f"Topology:NVME1:{_L2_DISK}",
                    "NVME1",
                    "cache",
                    "ata-L2-1",
                    "disk",
                    "ata-L2-1",
                    block,
                ],
            ],
        )

    def test_topology_class_order_and_group_names(self):
        """Data groups lead; special and spare classes follow status order."""
        _mp, ap, app = self._prepared()
        topology = _topo_node(
            "tank",
            "pool",
            [
                _topo_node(
                    "raidz2-0",
                    "raidz2",
                    [
                        _topo_node("/dev/sdb", "disk"),
                        _topo_node("/dev/sdc", "disk"),
                        _topo_node("/dev/sdd", "disk"),
                    ],
                ),
                _topo_node("special", "special", [_topo_node("/dev/sde", "disk")]),
                _topo_node("spares", "spare", [_topo_node("/dev/sdf", "disk")]),
            ],
        )
        pool = astats.PoolAlignment(
            name="tank",
            ashift_configured="12",
            ashift_effective=12,
            topology=topology,
        )
        ap._apply_alignment_sample(app, _sample(pools=[pool], datasets=[], histograms={}))
        rows = [c.args[1] for c in app._alignment_topology_store.insert.call_args_list]
        self.assertEqual(
            [(row[2], row[3], row[4], row[5]) for row in rows],
            [
                ("data", "raidz2-0", "raidz2", "sdb, sdc, sdd"),
                ("special", "sde", "disk", "sde"),
                ("spare", "sdf", "disk", "sdf"),
            ],
        )

    def test_topology_unreadable_degrades_per_pool(self):
        """A failed status read keeps the pool's row (and ashift), named in the note."""
        _mp, ap, app = self._prepared()
        app._alignment_note.hide.reset_mock()
        broken = astats.PoolAlignment(
            name="broken",
            ashift_configured="12",
            ashift_effective=12,
        )
        ap._apply_alignment_sample(app, _sample(pools=[_pool(), broken]))
        rows = [c.args[1] for c in app._alignment_topology_store.insert.call_args_list]
        broken_rows = [row for row in rows if row[1] == "broken"]
        self.assertEqual(
            broken_rows,
            [
                [
                    "Topology:broken",
                    "broken",
                    "—",
                    "—",
                    "—",
                    "topology unreadable",
                    f"{format_bytes(4096)} (effective ashift 12)",
                ]
            ],
        )
        # The healthy pool's groups still render.
        self.assertTrue(any(row[3] == "mirror-0" for row in rows))
        # The availability note names the pool, and the note is shown.
        markup = app._alignment_note.set_markup.call_args[0][0]
        self.assertIn("vdev topology unreadable for: broken", markup)
        app._alignment_note.hide.assert_not_called()

    def test_topology_all_pools_unreadable_when_ashift_unknown(self):
        """Unresolved ashift renders '—' cells instead of a bogus block size."""
        _mp, ap, app = self._prepared()
        mute = astats.PoolAlignment(name="mute", ashift_configured=None)
        ap._apply_alignment_sample(app, _sample(pools=[mute], datasets=[], histograms={}))
        rows = [c.args[1] for c in app._alignment_topology_store.insert.call_args_list]
        self.assertEqual(rows[0][6], "—")
        self.assertEqual(rows[0][5], "topology unreadable")

    def test_topology_rows_survive_ashift_drift_in_place(self):
        """Block-size drift updates rows in place on stable vdev identities."""
        _mp, ap, app = self._prepared()
        fake = _FakeStore()
        app._alignment_topology_store = fake
        ap._apply_alignment_sample(app, _sample())
        keys = fake.keys()
        self.assertEqual(
            keys,
            [
                "Topology:NVME1:mirror-0",
                f"Topology:NVME1:{_SLOG_DISK}",
                f"Topology:NVME1:{_L2_DISK}",
            ],
        )
        first = fake.rows[0]
        fake.inserted.clear()
        fake.removed.clear()

        drifted = astats.PoolAlignment(
            name="NVME1",
            ashift_configured="13",
            ashift_effective=13,
            topology=_topology(),
            members=[_member(path) for path in (_MIRROR_A, _MIRROR_B, _SLOG_DISK, _L2_DISK)],
            has_cache=True,
        )
        ap._apply_alignment_sample(app, _sample(pools=[drifted]))

        self.assertEqual(fake.keys(), keys)
        self.assertIs(fake.rows[0], first)  # updated in place, not rebuilt
        self.assertEqual(fake.inserted, [])
        self.assertEqual(fake.removed, [])
        self.assertIn("effective ashift 13", fake.rows[0].values[6])


class TestLadderSection(_PageTestCase):
    """The Blocksize ladder: section wiring, apply path, and Cairo renderer."""

    def test_ladder_built_through_factory_with_cairo_fallback(self):
        """Under mock_gtk the backend probe fails, so the page gets the
        Cairo BlocksizeLadder — the same fallback selection the live
        charts' factory tests pin."""
        _mp, ap, app = self._prepared()
        self.assertIsInstance(app._alignment_ladder, ap.BlocksizeLadder)
        draw_handlers = [
            call.args[0]
            for call in app._alignment_ladder.widget.connect.call_args_list
            if call.args
        ]
        self.assertIn("draw", draw_handlers)

    def test_apply_feeds_ladder_per_pool(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        pools = app._alignment_ladder.pools
        self.assertEqual([entry.pool for entry in pools], ["NVME1"])
        self.assertEqual(pools[0].block, 4096)
        layers = [bar.layer for bar in pools[0].bars]
        self.assertIn("Device", layers)
        self.assertIn("Pool", layers)
        self.assertIn("Dataset", layers)
        self.assertIn("VM", layers)
        # Sizing follows the shared row geometry; the width request is
        # exactly the content-derived minimum (the viewport stretches the
        # canvas to the page width whenever the page is wider).
        app._alignment_ladder.widget.set_size_request.assert_called_with(
            ap.ladder_minimum_width(pools), ap.ladder_pixel_height(pools)
        )
        app._alignment_ladder.widget.queue_draw.assert_called()
        # The retired followed-width API must stay retired on this renderer
        # too (see TestMatplotlibBlocksizeLadder for why it is gone).
        self.assertFalse(hasattr(app._alignment_ladder, "set_draw_width"))
        self.assertFalse(hasattr(app._alignment_ladder, "draw_width"))

    def test_apply_ladder_degrades_per_source(self):
        """Failed sources drop their rungs; a wholesale pool failure flips
        the chart to its unavailable placeholder height."""
        _mp, ap, app = self._prepared()
        # Per-pool dataset failure: rungs drop for that pool only.
        ap._apply_alignment_sample(app, _sample(datasets=[], dataset_read_failures=["NVME1"]))
        layers = [bar.layer for bar in app._alignment_ladder.pools[0].bars]
        self.assertNotIn("Dataset", layers)
        self.assertNotIn("VM", layers)
        self.assertIn("Device", layers)
        self.assertIn("Pool", layers)
        # Wholesale failure: empty pool set, placeholder height, and the
        # unavailable flag stored for the draw path.
        app._alignment_ladder.widget.set_size_request.reset_mock()
        ap._apply_alignment_sample(app, _sample(pools=[], pools_available=False))
        self.assertEqual(app._alignment_ladder.pools, [])
        self.assertTrue(app._alignment_ladder._unavailable)
        app._alignment_ladder.widget.set_size_request.assert_called_with(-1, ap.LADDER_EMPTY_HEIGHT)
        # zfs fine but no pools: same placeholder height, no flag.
        ap._apply_alignment_sample(app, _sample(pools=[]))
        self.assertFalse(app._alignment_ladder._unavailable)
        app._alignment_ladder.widget.set_size_request.assert_called_with(-1, ap.LADDER_EMPTY_HEIGHT)

    def test_ladder_draw_smoke(self):
        """A full Cairo draw pass must not raise with pools and reference."""
        _mp, ap, _app = self._prepared()
        ladder = ap.BlocksizeLadder("Blocksize ladder")
        ladder.update(ap.blocksize_ladder(_sample()))
        widget = ladder.widget
        widget.get_allocated_width.return_value = 520
        widget.get_allocated_height.return_value = ap.ladder_pixel_height(ladder.pools)
        cr = MagicMock()
        cr.text_extents.return_value = SimpleNamespace(x_advance=60.0)
        ladder._on_draw(widget, cr)
        self.assertTrue(widget.queue_draw.called)

    def test_ladder_font_and_width_follow_the_gui_base_font(self):
        """The Cairo ladder's 13px text and its content-minimum width
        request scale with the widget-resolved GUI base font (the tuned
        values are per a 10pt default)."""
        _mp, ap, _app = self._prepared()
        ladder = ap.BlocksizeLadder("Blocksize ladder")
        pools = ap.blocksize_ladder(_sample())
        widget = ladder.widget
        widget.get_allocated_width.return_value = 520
        widget.get_allocated_height.return_value = ap.ladder_pixel_height(pools)
        cr = MagicMock()
        cr.text_extents.return_value = SimpleNamespace(x_advance=60.0)
        with patch.object(ap, "chart_font_scale", return_value=1.25):
            ladder.update(pools)
            widget.set_size_request.assert_called_with(
                ap.ladder_minimum_width(pools, 1.25), ap.ladder_pixel_height(pools)
            )
            ladder._on_draw(widget, cr)
        cr.set_font_size.assert_called_once_with(16.25)


class TestReconcileRows(_PageTestCase):
    """_reconcile_rows: ordered, key-column reconciliation against _FakeStore."""

    def test_update_in_place_preserves_row_objects(self):
        _mp, ap, _app = self._prepared()
        store = _FakeStore([["a", "old"], ["b", "keep"]])
        first = store.rows[0]
        ap._reconcile_rows(store, {"a": ["a", "new"], "b": ["b", "keep"]})
        self.assertEqual([row.values for row in store.rows], [["a", "new"], ["b", "keep"]])
        self.assertIs(store.rows[0], first)  # same row object: no rebuild
        self.assertEqual(store.inserted, [])
        self.assertEqual(store.removed, [])

    def test_removes_vanished_keys(self):
        _mp, ap, _app = self._prepared()
        store = _FakeStore([["a", "1"], ["b", "2"]])
        ap._reconcile_rows(store, {"a": ["a", "1"]})
        self.assertEqual(store.keys(), ["a"])
        self.assertEqual([row.values[0] for row in store.removed], ["b"])

    def test_inserts_new_key_in_order(self):
        _mp, ap, _app = self._prepared()
        store = _FakeStore([["a", "1"], ["c", "3"]])
        ap._reconcile_rows(store, {"a": ["a", "1"], "b": ["b", "2"], "c": ["c", "3"]})
        self.assertEqual(store.keys(), ["a", "b", "c"])
        self.assertEqual([row.values[0] for row in store.inserted], ["b"])

    def test_moves_survivor_into_hole_left_by_removal(self):
        _mp, ap, _app = self._prepared()
        store = _FakeStore([["a", "1"], ["b", "2"], ["c", "3"]])
        ap._reconcile_rows(store, {"c": ["c", "3"], "a": ["a", "1"]})
        self.assertEqual(store.keys(), ["c", "a"])
        # b vanished; c moved up to its ordered position (a was updated
        # in place, never removed).
        self.assertEqual([row.values[0] for row in store.removed], ["b", "c"])
        self.assertEqual([row.values[0] for row in store.inserted], ["c"])

    def test_reordered_survivors_settle_without_duplicates(self):
        _mp, ap, _app = self._prepared()
        store = _FakeStore([["a", "1"], ["b", "2"]])
        ap._reconcile_rows(store, {"b": ["b", "2"], "a": ["a", "1"]})
        self.assertEqual(store.keys(), ["b", "a"])

    def test_fills_empty_store_in_order(self):
        _mp, ap, _app = self._prepared()
        store = _FakeStore()
        ap._reconcile_rows(store, {"b": ["b", "2"], "a": ["a", "1"]})
        self.assertEqual(store.keys(), ["b", "a"])

    def test_sorted_store_updates_and_appends_without_reordering(self):
        """With a column sort active the store owns the order: survivors
        update in place, new rows append, and no positional inserts run."""
        _mp, ap, _app = self._prepared()
        store = _FakeStore([["a", "1"], ["b", "2"]])
        store.set_sorted(column=1)
        ap._reconcile_rows(store, {"b": ["b", "20"], "c": ["c", "3"]})
        self.assertEqual(store.keys(), ["b", "c"])
        self.assertEqual(len(store.appended), 1)  # c
        self.assertEqual([row.values[1] for row in store.rows], ["20", "3"])
        # The vanished row was removed; nothing was positionally inserted.
        self.assertEqual([row.values[0] for row in store.removed], ["a"])
        self.assertEqual(store.inserted, [])


class TestAlignmentScrollPreservation(_PageTestCase):
    """The datasets-page save/restore idiom around every alignment apply."""

    def test_apply_schedules_clamped_restore(self):
        _mp, ap, app = self._prepared()
        app.performance_scrolled.get_vadjustment.return_value.get_value.return_value = 150.0
        with patch.object(ap.GLib, "idle_add") as idle:
            ap._apply_alignment_sample(app, _sample())
        app.performance_scrolled.get_vadjustment.assert_called_once()
        callback, scrolled, value = idle.call_args[0]
        self.assertIs(scrolled, app.performance_scrolled)
        self.assertEqual(value, 150.0)
        self.assertEqual(callback.__name__, "_restore_scroll")

    def test_no_restore_without_scrolled_window(self):
        _mp, ap, app = self._prepared()
        del app.performance_scrolled
        with patch.object(ap.GLib, "idle_add") as idle:
            ap._apply_alignment_sample(app, _sample())
        idle.assert_not_called()

    def test_no_restore_without_adjustment(self):
        _mp, ap, app = self._prepared()
        app.performance_scrolled.get_vadjustment.return_value = None
        with patch.object(ap.GLib, "idle_add") as idle:
            ap._apply_alignment_sample(app, _sample())
        idle.assert_not_called()

    def test_refresh_finish_path_preserves_offset(self):
        """The full refresh chain (collect → idle finish → apply) restores."""
        _mp, ap, app = self._prepared()
        app.performance_scrolled.get_vadjustment.return_value.get_value.return_value = 210.0

        class _SyncThread:
            """Thread stand-in that runs its target synchronously."""

            def __init__(self, target=None, daemon=False):
                self._target = target

            def start(self):
                self._target()

        idle_captured = []
        with (
            patch.object(ap.threading, "Thread", _SyncThread),
            patch.object(
                ap.GLib, "idle_add", side_effect=lambda fn, *a: idle_captured.append((fn, a)) or 1
            ),
        ):
            ap.refresh_alignment_view(app)
        # The collection thread ran and queued the idle finisher.
        finish_fn, finish_args = idle_captured[0]
        self.assertEqual(finish_fn.__name__, "_finish_refresh")
        with patch.object(ap.GLib, "idle_add") as idle:
            finish_fn(*finish_args)
        callback, _scrolled, value = idle.call_args[0]
        self.assertEqual(value, 210.0)
        self.assertEqual(callback.__name__, "_restore_scroll")
        self.assertFalse(app._alignment_refresh_pending)

    def test_refresh_survives_collection_failure(self):
        """A collect-thread exception still clears the pending flag.

        The flag only resets in the idle finisher, so an exception
        escaping the worker used to stop every future refresh until the
        GUI restarted; the failure must degrade to a skipped apply with
        the flag cleared (dashboard-worker shape).
        """
        _mp, ap, app = self._prepared()

        class _SyncThread:
            """Thread stand-in that runs its target synchronously."""

            def __init__(self, target=None, daemon=False):
                self._target = target

            def start(self):
                self._target()

        idle_captured = []
        with (
            patch.object(ap.threading, "Thread", _SyncThread),
            patch.object(
                ap.GLib, "idle_add", side_effect=lambda fn, *a: idle_captured.append((fn, a)) or 1
            ),
            patch.object(ap, "collect_alignment_sample", side_effect=RuntimeError("boom")),
        ):
            ap.refresh_alignment_view(app)
        finish_fn, finish_args = idle_captured[0]
        self.assertEqual(finish_fn.__name__, "_finish_refresh")
        self.assertIsNone(finish_args[1])
        with patch.object(ap, "_apply_alignment_sample") as apply_mock:
            finish_fn(*finish_args)
        apply_mock.assert_not_called()
        self.assertFalse(app._alignment_refresh_pending)

    def test_restore_scroll_clamps_to_valid_range(self):
        _mp, ap, _app = self._prepared()
        scrolled = MagicMock()
        vadj = MagicMock()
        vadj.get_upper.return_value = 500.0
        vadj.get_page_size.return_value = 100.0
        scrolled.get_vadjustment.return_value = vadj
        ap._restore_scroll(scrolled, 450.0)
        vadj.set_value.assert_called_once_with(400.0)

    def test_restore_scroll_uses_exact_value_when_in_range(self):
        _mp, ap, _app = self._prepared()
        scrolled = MagicMock()
        vadj = MagicMock()
        vadj.get_upper.return_value = 500.0
        vadj.get_page_size.return_value = 100.0
        scrolled.get_vadjustment.return_value = vadj
        ap._restore_scroll(scrolled, 250.0)
        vadj.set_value.assert_called_once_with(250.0)

    def test_restore_scroll_returns_false_when_no_adjustment(self):
        _mp, ap, _app = self._prepared()
        scrolled = MagicMock()
        scrolled.get_vadjustment.return_value = None
        self.assertIs(ap._restore_scroll(scrolled, 100.0), False)

    def test_chain_rows_survive_partial_dataset_failure(self):
        """One pool's failed dataset read never blanks the whole chain."""
        _mp, ap, app = self._prepared()
        fake = _FakeStore()
        app._alignment_chain_store = fake
        ap._apply_alignment_sample(app, _sample())
        keys_before = fake.layer_object_keys()
        self.assertIn(("Pool", "NVME1"), keys_before)
        self.assertIn(("Dataset", "NVME1/backups"), keys_before)
        fake.inserted.clear()
        fake.appended.clear()

        # Transient zfs failure on dataset reads: pool/device rows stay,
        # only the dataset/VM rows of the failed pool vanish.
        failed = _sample(datasets=[], dataset_read_failures=["NVME1"])
        ap._apply_alignment_sample(app, failed)
        keys_after = fake.layer_object_keys()
        self.assertIn(("Pool", "NVME1"), keys_after)
        self.assertIn(("Device", "ata-WDC_WD80EDAZ-11"), keys_after)
        self.assertNotIn(("Dataset", "NVME1/backups"), keys_after)
        # The surviving rows were updated in place, not rebuilt.
        self.assertEqual(fake.inserted, [])
        self.assertEqual(fake.appended, [])


class TestWorkloadReconcile(_PageTestCase):
    """The workload table reconciles on pool names, not rendered verdicts."""

    def test_verdict_flip_updates_row_in_place(self):
        _mp, ap, app = self._prepared()
        fake = _FakeStore()
        app._alignment_workload_store = fake
        ap._apply_alignment_sample(app, _sample())
        self.assertEqual(fake.keys(), ["NVME1"])
        first = fake.rows[0]
        fake.inserted.clear()
        fake.removed.clear()
        ap._apply_alignment_sample(app, _sample(prefetch_available=False))
        self.assertEqual(fake.keys(), ["NVME1"])
        self.assertIs(fake.rows[0], first)
        self.assertTrue(fake.rows[0].values[1].endswith("(low confidence)"))
        self.assertEqual(fake.inserted, [])
        self.assertEqual(fake.removed, [])

    def test_vanished_pool_row_removed(self):
        _mp, ap, app = self._prepared()
        fake = _FakeStore()
        app._alignment_workload_store = fake
        ap._apply_alignment_sample(app, _sample())
        ap._apply_alignment_sample(app, _sample(pools=[]))
        self.assertEqual(fake.keys(), [])
        self.assertEqual([row.values[0] for row in fake.removed], ["NVME1"])


class _FakeCombo:
    """ComboBoxText stand-in with real choice tracking for the survey dialog."""

    def __init__(self):
        self.choices = []
        self.active = 0
        self.override_text = None

    def append_text(self, text):
        self.choices.append(text)

    def set_active(self, index):
        self.active = index

    def get_active_text(self):
        if self.override_text is not None:
            return self.override_text
        return self.choices[self.active] if self.choices else None

    def get_model(self):
        return [(choice,) for choice in self.choices]

    def connect(self, *_args):
        pass


# mock_gtk's Gtk.ResponseType.OK is the plain int 1 on every context, so it
# is identity-stable across separate mock_gtk() blocks.
_RESPONSE_OK = 1

# Mirrors alignment_dialogs.NOT_SURVEYED (referenced before _open returns).
_NOT_SURVEYED = "(not surveyed)"


class TestAlignmentSurveyDialog(_PageTestCase):
    """The Survey… dialog from alignment_dialogs."""

    def _open(self, app, response, dataset_text=None, profile_text=None):
        """Run open_alignment_survey with faked combos and dialog; return them."""
        with mock_gtk(fresh=True):
            import alignment_dialogs as ad

            dataset_combo = _FakeCombo()
            profile_combo = _FakeCombo()
            dataset_combo.override_text = dataset_text
            profile_combo.override_text = profile_text
            dialog = MagicMock()
            dialog.run.return_value = response
            with (
                patch.object(ad, "create_dialog", return_value=dialog),
                patch.object(
                    ad.Gtk, "ComboBoxText", MagicMock(side_effect=[dataset_combo, profile_combo])
                ),
                patch.object(ad, "log_msg"),
                patch("feature_config.save_config"),
                patch("alignment_page.refresh_alignment_view") as refresh,
            ):
                ad.open_alignment_survey(app)
            return ad, dataset_combo, profile_combo, dialog, refresh

    def test_survey_save_writes_config(self):
        app = _make_app()
        app._alignment_sample = _sample()
        app.config["workload_profiles"] = {"vm-os": {"description": "VM disks"}}
        ad, dataset_combo, profile_combo, _dialog, refresh = self._open(
            app,
            _RESPONSE_OK,
            dataset_text="NVME1/backups",
            profile_text="vm-os",
        )
        self.assertEqual(app.config.get("alignment_survey"), {"NVME1/backups": "vm-os"})
        # Dataset choices come from the last sample's datasets.
        self.assertEqual(
            dataset_combo.choices,
            ["NVME1/backups", "NVME1/vm-201-disk-0"],
        )
        # Profile choices start with the not-surveyed placeholder.
        self.assertEqual(profile_combo.choices[0], ad.NOT_SURVEYED)
        self.assertIn("vm-os", profile_combo.choices)
        # The view refreshes so the new survey takes effect immediately.
        refresh.assert_called_once_with(app)

    def test_survey_not_surveyed_removes_entry(self):
        app = _make_app()
        app._alignment_sample = _sample()
        app.config["alignment_survey"] = {"NVME1/backups": "vm-os"}
        _ad, _dataset, _profile, _dialog, _refresh = self._open(
            app,
            _RESPONSE_OK,
            dataset_text="NVME1/backups",
            profile_text=_NOT_SURVEYED,
        )
        self.assertEqual(app.config.get("alignment_survey"), {})

    def test_survey_cancel_saves_nothing(self):
        app = _make_app()
        app._alignment_sample = _sample()
        _ad, _dataset, _profile, dialog, refresh = self._open(
            app,
            None,  # any non-OK response
            dataset_text="NVME1/backups",
            profile_text="vm-os",
        )
        self.assertNotIn("alignment_survey", app.config)
        dialog.destroy.assert_called_once()
        refresh.assert_not_called()

    def test_survey_without_sample_shows_hint(self):
        app = _make_app()
        app._alignment_sample = None
        with mock_gtk(fresh=True):
            import alignment_dialogs as ad

            dialog = MagicMock()
            dialog.run.return_value = _RESPONSE_OK
            with (
                patch.object(ad, "create_dialog", return_value=dialog),
                patch.object(
                    ad.Gtk, "ComboBoxText", MagicMock(side_effect=[_FakeCombo(), _FakeCombo()])
                ),
                patch.object(ad, "log_msg"),
                patch("feature_config.save_config") as save,
            ):
                ad.open_alignment_survey(app)
        save.assert_not_called()
        self.assertNotIn("alignment_survey", app.config)


class TestTableViewPolish(_PageTestCase):
    """Scrolled 20-row tables, sortable scan columns, and cell tooltips.

    The mock GTK classes return shared instances, so each test constructs
    its widgets under fresh-instance factories and captures them.
    """

    def _fresh_gtk(self, ap):
        """Patch fresh Gtk widget instances; return the captured lists."""
        views, scrolls, columns = [], [], []

        def _tree(*_a, **_k):
            view = MagicMock()
            views.append(view)
            return view

        def _scroll(*_a, **_k):
            scroll = MagicMock()
            scrolls.append(scroll)
            return scroll

        def _column(*_a, **_k):
            col = MagicMock()
            columns.append(col)
            return col

        patchers = [
            patch.object(ap.Gtk, "TreeView", side_effect=_tree),
            patch.object(ap.Gtk, "ScrolledWindow", side_effect=_scroll),
            patch.object(ap.Gtk, "TreeViewColumn", side_effect=_column),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        return views, scrolls, columns

    def test_chain_columns_sortable_with_offset(self):
        _mp, ap, _app2 = self._prepared()
        views, _scrolls, columns = self._fresh_gtk(ap)
        app = MagicMock()
        app._ui_state = MagicMock()
        _scroll, _store, view = ap._table(
            app,
            "_test_store",
            [("Layer", 70), ("Object", 280), ("Block size", 200), ("Detail", 380)],
            "test_view",
            hidden_key=True,
            sortable=True,
        )
        self.assertIs(view, views[0])
        self.assertEqual(len(columns), 4)
        for index, col in enumerate(columns):
            col.set_sort_column_id.assert_called_once_with(index + 1)
            col.set_clickable.assert_called_once_with(True)
        # The scrolled wrapper carries the view; identity key never sorts.
        _scroll.add.assert_called_once_with(view)

    def test_table_columns_carry_widths_and_expand(self):
        """Columns start at sane widths; one non-last column absorbs slack.

        GTK re-expands the last TreeView column to fill leftover width,
        which makes shrinking the far-right column look ineffective; the
        expand flag redirects that slack to a chosen column so the last
        column keeps its honest fixed width.
        """
        _mp, ap, _app2 = self._prepared()
        _views, _scrolls, columns = self._fresh_gtk(ap)
        app = MagicMock()
        app._ui_state = MagicMock()
        ap._table(app, "_t", [("A", 120), ("B", 200), ("C", 160)], "v", expand_index=1)
        for col, width in zip(columns, (120, 200, 160)):
            col.set_fixed_width.assert_called_once_with(width)
            col.set_min_width.assert_called_once_with(60)
        columns[1].set_expand.assert_called_once_with(True)
        columns[0].set_expand.assert_not_called()
        columns[2].set_expand.assert_not_called()

    def test_page_tables_wire_non_last_expand_columns(self):
        """Each of the four page tables expands a non-last column only."""
        _mp, ap, _app = self._prepared()
        _views, _scrolls, columns = self._fresh_gtk(ap)
        app = MagicMock()
        app._ui_state = MagicMock()
        ap.create_alignment_view(app)
        # 21 columns: chain 4, topology 6, findings 5, workload 6.  The
        # expand column sits inside each table, never on its last column.
        self.assertEqual(len(columns), 21)
        expanded = {index for index, col in enumerate(columns) if col.set_expand.called}
        self.assertEqual(expanded, {1, 8, 13, 16})
        widths = [c.set_fixed_width.call_args.args[0] for c in columns]
        self.assertEqual(
            widths,
            [
                70,
                280,
                200,
                380,
                90,
                80,
                170,
                70,
                260,
                220,
                90,
                70,
                180,
                360,
                380,
                110,
                170,
                140,
                140,
                120,
                130,
            ],
        )
        self.assertTrue(all(width >= 60 for width in widths))

    def test_other_tables_not_sortable(self):
        _mp, ap, _app2 = self._prepared()
        views, _scrolls, columns = self._fresh_gtk(ap)
        app = MagicMock()
        app._ui_state = MagicMock()
        _scroll, _store, view = ap._table(app, "_t", [("A", 80), ("B", 80)], "v")
        self.assertIs(view, views[0])
        self.assertEqual(len(columns), 2)
        for col in columns:
            col.set_sort_column_id.assert_not_called()
            col.set_clickable.assert_not_called()

    def test_query_tooltip_connected_with_store_and_offset(self):
        _mp, ap, _app2 = self._prepared()
        _views, _scrolls, _columns = self._fresh_gtk(ap)
        app = MagicMock()
        app._ui_state = MagicMock()
        _scroll, store, view = ap._table(app, "_t", [("A", 80)], "v", hidden_key=True)
        handler = [
            call
            for call in view.connect.call_args_list
            if call.args and call.args[0] == "query-tooltip"
        ]
        self.assertEqual(len(handler), 1)
        self.assertIs(handler[0].args[1], ap._on_cell_query_tooltip)
        self.assertIs(handler[0].args[2], store)
        self.assertEqual(handler[0].args[3], 1)  # hidden-key offset

    def test_cell_query_tooltip_shows_full_text(self):
        _mp, ap, _app = self._prepared()
        view = MagicMock()
        view.convert_widget_to_bin_window_coords.return_value = (11, 12)
        path = MagicMock()
        column_b = MagicMock()
        view.get_path_at_pos.return_value = (path, column_b, 1, 2)
        view.get_columns.return_value = [MagicMock(), column_b]
        store = MagicMock()
        store.__getitem__ = MagicMock(return_value=["key", "row1", "long text"])
        tooltip = MagicMock()
        self.assertTrue(ap._on_cell_query_tooltip(view, 11, 12, False, tooltip, store, 1))
        tooltip.set_text.assert_called_once_with("long text")

    @staticmethod
    def _tooltip_fakes(text, pixel_width, column_width):
        """Scriptable fakes: a view whose layout measures *pixel_width* px
        for any text, a column allocated *column_width* px, and a one-row
        store (hidden key + one visible cell)."""
        column = SimpleNamespace(get_width=lambda: column_width)
        view = SimpleNamespace(
            convert_widget_to_bin_window_coords=lambda x, y: (x, y),
            get_path_at_pos=lambda x, y: (0, column, 1, 2),
            get_columns=lambda: [column],
            create_pango_layout=lambda t: SimpleNamespace(get_pixel_size=lambda: (pixel_width, 12)),
        )
        return view, column, {0: ["key", text]}

    def test_cell_query_tooltip_silent_when_text_fits(self):
        """Only clipped cells tooltip: text measuring narrower than the
        column's width (minus the cell's own padding slack) stays silent."""
        _mp, ap, _app = self._prepared()
        view, _column, store = self._tooltip_fakes("short", 120, 300)
        tooltip = MagicMock()
        self.assertFalse(ap._on_cell_query_tooltip(view, 11, 12, False, tooltip, store, 1))
        tooltip.set_text.assert_not_called()

    def test_cell_query_tooltip_shown_when_text_truncated(self):
        _mp, ap, _app = self._prepared()
        view, _column, store = self._tooltip_fakes("a fairly long cell", 320, 300)
        tooltip = MagicMock()
        self.assertTrue(ap._on_cell_query_tooltip(view, 11, 12, False, tooltip, store, 1))
        tooltip.set_text.assert_called_once_with("a fairly long cell")

    def test_cell_query_tooltip_empty_cell_falls_through(self):
        _mp, ap, _app = self._prepared()
        view, _column, store = self._tooltip_fakes("", 0, 300)
        self.assertFalse(ap._on_cell_query_tooltip(view, 11, 12, False, MagicMock(), store, 1))

    def test_cell_query_tooltip_unmeasurable_still_shows(self):
        """Measurement impossible (no Pango context — mocked GTK, exotic
        backends): show rather than suppress, so long cells stay reachable."""
        _mp, ap, _app = self._prepared()
        column = SimpleNamespace(get_width=lambda: 300)
        view = SimpleNamespace(
            convert_widget_to_bin_window_coords=lambda x, y: (x, y),
            get_path_at_pos=lambda x, y: (0, column, 1, 2),
            get_columns=lambda: [column],
        )
        store = {0: ["key", "long text"]}
        tooltip = MagicMock()
        self.assertTrue(ap._on_cell_query_tooltip(view, 11, 12, False, tooltip, store, 1))
        tooltip.set_text.assert_called_once_with("long text")

    def test_cell_query_tooltip_empty_space_falls_through(self):
        _mp, ap, _app = self._prepared()
        view = MagicMock()
        view.convert_widget_to_bin_window_coords.return_value = (11, 12)
        view.get_path_at_pos.return_value = ()
        self.assertFalse(
            ap._on_cell_query_tooltip(view, 11, 12, False, MagicMock(), MagicMock(), 1)
        )
        view.get_path_at_pos.return_value = (MagicMock(), None, 1, 2)
        self.assertFalse(
            ap._on_cell_query_tooltip(view, 11, 12, False, MagicMock(), MagicMock(), 1)
        )

    def test_capped_scroll_shows_twenty_rows(self):
        """The shared capped scroll: a fixed 20-row window (min == max).

        ``min_content_height`` pinned at the cap keeps short and empty
        tables at their full 20-line window, and
        ``propagate_natural_height`` keeps taller tables from collapsing
        to the old couple-of-rows minimum.
        """
        with mock_gtk(fresh=True):
            import gui_helpers as gh

            scrolls = []

            def _make_scroll(*_a, **_k):
                scroll = MagicMock()
                scrolls.append(scroll)
                return scroll

            with patch.object(gh.Gtk, "ScrolledWindow", side_effect=_make_scroll):
                view = MagicMock()
                view.style_get_property.return_value = 6
                scroll = gh.capped_treeview_scroll(view)
            self.assertIs(scroll, scrolls[0])
            fallback = gh.TREEVIEW_ROW_HEIGHT_FALLBACK
            cap = fallback + 2 + 21 * fallback
            scroll.set_min_content_height.assert_called_once_with(cap)
            scroll.set_max_content_height.assert_called_once_with(cap)
            scroll.set_propagate_natural_height.assert_called_once_with(True)
            scroll.add.assert_called_once_with(view)
            # Both scroll policies automatic so either axis can scroll.
            scroll.set_policy.assert_called_once_with(
                gh.Gtk.PolicyType.AUTOMATIC, gh.Gtk.PolicyType.AUTOMATIC
            )


class TestLadderViewport(_PageTestCase):
    """The ladder scrolls its own viewport, floored at its content width."""

    def test_ladder_packed_in_horizontal_scroll(self):
        _mp, ap, app = self._prepared()
        scroll = app._alignment_ladder_scroll
        self.assertIn(
            (ap.Gtk.PolicyType.AUTOMATIC, ap.Gtk.PolicyType.NEVER),
            [c.args for c in scroll.set_policy.call_args_list],
        )
        # The canvas's width request must not pin the page wide: the scroll
        # keeps a small minimum so the viewport can be narrower than the
        # chart and the horizontal scrollbar appears.
        scroll.set_min_content_width.assert_called_once_with(ap.TREEVIEW_MIN_WIDTH)
        # The ladder widget (not a table view) is the scroll's child.
        added = [c.args[0] for c in scroll.add.call_args_list]
        self.assertIn(app._alignment_ladder.widget, added)

    def test_size_allocate_floors_viewport_at_content_minimum(self):
        """The viewport cap can never sit below the canvas's requested
        minimum: a ``max_content_width`` under the child's request makes
        GTK clamp the canvas to the window and drop the horizontal
        scrollbar (reproduced under Xvfb at mid window widths with the
        retired half-page cap). Page resizes re-floor the wider of the box
        width and the content minimum."""
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        scroll = app._alignment_ladder_scroll
        floor = max(700, ap.ladder_minimum_width(app._alignment_ladder.pools))
        scroll.set_max_content_width.reset_mock()
        scroll.get_max_content_width.return_value = -1
        ap._on_ladder_box_size_allocate(MagicMock(), SimpleNamespace(width=700), app)
        scroll.set_max_content_width.assert_called_once_with(floor)
        scroll.set_max_content_width.reset_mock()
        # Same width again: the floor already matches, nothing re-applies.
        scroll.get_max_content_width.return_value = floor
        ap._on_ladder_box_size_allocate(MagicMock(), SimpleNamespace(width=700), app)
        scroll.set_max_content_width.assert_not_called()
        # A wider page lifts the floor; a pool-set change re-floors it from
        # the refresh path (see the apply-path test below).

    def test_refresh_floors_viewport_after_pool_set_change(self):
        """Applying a sample re-floors the window's max_content_width after
        the ladder's pool set — a new pool set changes the content minimum,
        and the floor must track it between allocations."""
        _mp, ap, app = self._prepared()
        scroll = app._alignment_ladder_scroll
        scroll.get_allocated_width.return_value = 700
        scroll.get_max_content_width.return_value = -1
        ap._apply_alignment_sample(app, _sample())
        floor = max(700, ap.ladder_minimum_width(app._alignment_ladder.pools))
        scroll.set_max_content_width.assert_called_with(floor)

    def test_ladder_request_is_content_minimum_only(self):
        """update() requests exactly the content-derived minimum width with
        the new height — there is no followed page width anymore; the
        viewport stretches the canvas to the page width whenever the page
        is wider, so the request doubles as the scrollbar floor."""
        _mp, ap, _app = self._prepared()
        ladder = ap.BlocksizeLadder("Blocksize ladder")
        ladder.update(ap.blocksize_ladder(_sample()))
        ladder.widget.set_size_request.assert_called_with(
            ap.ladder_minimum_width(ladder.pools), ap.ladder_pixel_height(ladder.pools)
        )
        # No pools: the placeholder takes whatever width the page grants.
        ladder.widget.set_size_request.reset_mock()
        ladder.update([])
        ladder.widget.set_size_request.assert_called_with(-1, ap.LADDER_EMPTY_HEIGHT)


class TestGuestFsPresentation(_PageTestCase):
    """Probed guest filesystems in the chain table and the degrade note."""

    def test_vm_detail_lists_probed_filesystems(self):
        _mp, ap, app = self._prepared()
        sample = _sample(
            guest_fs={
                "vm-201-disk-0": [
                    GuestFsEntry(mount="/", fstype="ext4", blocksize=4096),
                    GuestFsEntry(mount="/var", fstype="xfs", blocksize=4096),
                ]
            }
        )
        ap._apply_alignment_sample(app, sample)
        rows = [c.args[1] for c in app._alignment_chain_store.insert.call_args_list]
        vm_row = next(row for row in rows if row[1] == "VM")
        self.assertIn("ext4 4K on /", vm_row[4])
        self.assertIn("xfs 4K on /var", vm_row[4])

    def test_vm_detail_lists_probe_failure(self):
        _mp, ap, app = self._prepared()
        sample = _sample(guest_fs_failures={"vm-201-disk-0": "VM not running"})
        ap._apply_alignment_sample(app, sample)
        rows = [c.args[1] for c in app._alignment_chain_store.insert.call_args_list]
        vm_row = next(row for row in rows if row[1] == "VM")
        self.assertIn("guest fs unprobed: VM not running", vm_row[4])

    def test_degrade_note_names_guest_probe_failures(self):
        _mp, ap, app = self._prepared()
        sample = _sample(guest_fs_failures={"vm-201-disk-0": "VM not running"})
        ap._apply_alignment_sample(app, sample)
        markup = app._alignment_note.set_markup.call_args[0][0]
        self.assertIn("Guest filesystems unprobed for: vm-201-disk-0 (VM not running)", markup)

    def test_no_guest_note_when_probed(self):
        _mp, ap, app = self._prepared()
        sample = _sample(
            guest_fs={"vm-201-disk-0": [GuestFsEntry(mount="/", fstype="ext4", blocksize=4096)]}
        )
        ap._apply_alignment_sample(app, sample)
        self.assertTrue(
            all(
                "unprobed" not in str(c.args[0])
                for c in app._alignment_note.set_markup.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
