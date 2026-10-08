"""Tests for alignment_page.py — the Alignment view of the Performance page.

Covers the Live Charts / Alignment view switcher built into memory_page,
the sample-application helpers (chain, findings, workload, memory-tier
readouts), per-source degrade notes, and the survey dialog from
alignment_dialogs.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import alignment_stats as astats
from disk_repository import format_bytes
from memory_stats import format_percent
from test_support import mock_gtk


def _member(path="/dev/disk/by-id/ata-WDC_WD80EDAZ-11"):
    return astats.MemberDisk(path=path, logical_sector=512, physical_sector=4096)


def _pool():
    return astats.PoolAlignment(
        name="NVME1",
        ashift_configured="12",
        ashift_effective=12,
        members=[_member()],
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
            "_alignment_findings_store",
            "_alignment_workload_store",
        ):
            getattr(app, attr).get_iter_first.return_value = None
        return mp, ap, app


class TestPerformanceViewSwitcher(_PageTestCase):
    """The Live Charts / Alignment radio switcher on the Performance page."""

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
        with patch("config_core.save_config"):
            mp._on_memory_view_radio_toggled(radios["alignment"], app)
        app._memory_view_stack.set_visible_child_name.assert_called_once_with("alignment")
        self.assertEqual(
            app.config.get("ui_state", {}).get("performance_view", {}).get("view"),
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
        with patch("config_core.save_config") as save:
            mp._on_memory_view_radio_toggled(radios["charts"], app)
        save.assert_not_called()
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


class TestApplyAlignmentSample(_PageTestCase):
    """_apply_alignment_sample against the built view widgets."""

    def test_chain_rows(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        rows = [c.args[0] for c in app._alignment_chain_store.append.call_args_list]
        by_key = {(row[0], row[1]): row for row in rows}
        self.assertEqual(
            by_key[("Pool", "NVME1")][:3],
            ["Pool", "NVME1", f"ashift 12 ({format_bytes(4096)})"],
        )
        self.assertEqual(by_key[("Pool", "NVME1")][3], "configured 12")
        self.assertEqual(
            by_key[("Device", "ata-WDC_WD80EDAZ-11")][2:],
            [
                f"{format_bytes(512)} logical / {format_bytes(4096)} physical",
                "512e advanced format",
            ],
        )
        self.assertEqual(
            by_key[("Dataset", "NVME1/backups")][2:],
            ["recordsize 128K", "local"],
        )
        self.assertEqual(
            by_key[("VM", "vm-201-disk-0")][2:],
            ["volblocksize 16K", "scsi0 discard iothread"],
        )

    def test_chain_row_without_pve_options(self):
        _mp, ap, app = self._prepared()
        sample = _sample(vm_disks={})
        ap._apply_alignment_sample(app, sample)
        rows = [c.args[0] for c in app._alignment_chain_store.append.call_args_list]
        vm_rows = [row for row in rows if row[0] == "VM"]
        self.assertEqual(vm_rows[0][3], "not referenced in local PVE configs")

        sample = _sample(vm_disks={}, pve_available=False)
        ap._apply_alignment_sample(app, sample)
        vm_rows = [
            row.args[0]
            for row in app._alignment_chain_store.append.call_args_list
            if row.args[0][0] == "VM"
        ]
        self.assertEqual(vm_rows[-1][3], "PVE configs unreadable on this host")

    def test_chain_reconcile_removes_vanished_rows(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        store = app._alignment_chain_store
        tree_iter = MagicMock()
        store.get_iter_first.return_value = tree_iter
        store.iter_next.return_value = None
        store.get_value.side_effect = lambda _it, col: [
            "Device",
            "ata-WDC_WD80EDAZ-11",
            "cap",
            "—",
        ][col]
        ap._apply_alignment_sample(app, _sample(pools=[], datasets=[]))
        store.remove.assert_called_once_with(tree_iter)

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
        app._alignment_findings_store.clear.assert_called()
        rows = [c.args[0] for c in app._alignment_findings_store.append.call_args_list]
        severities = [row[0] for row in rows]
        self.assertIn("⚠ WARN", severities)
        self.assertIn("✓ OK", severities)
        warn = next(row for row in rows if row[0] == "⚠ WARN")
        self.assertEqual(warn[1], "Pool")
        self.assertEqual(warn[2], "odd")
        self.assertIn("read-modify-write", warn[4])

    def test_workload_rows(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample())
        rows = [c.args[0] for c in app._alignment_workload_store.append.call_args_list]
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
        rows = [c.args[0] for c in app._alignment_workload_store.append.call_args_list]
        self.assertTrue(rows[0][1].endswith("(low confidence)"))

    def test_workload_no_histogram_row(self):
        _mp, ap, app = self._prepared()
        ap._apply_alignment_sample(app, _sample(histograms={}))
        rows = [c.args[0] for c in app._alignment_workload_store.append.call_args_list]
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


if __name__ == "__main__":
    unittest.main()
