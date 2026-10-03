"""Tests for memory_page.py — Memory tab widgets, notes, and charts."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import memory_stats as ms
from test_support import mock_gtk


def _arc_sample(mono, hits=1000, misses=100, size=32648235840, c_max=48318382080):
    return ms.MemorySample(
        monotonic=mono,
        arc={
            "hits": hits,
            "misses": misses,
            "size": size,
            "c": 32818317552,
            "c_max": c_max,
            "data_size": 15163942400,
            "metadata_size": 6813288960,
            "hdr_size": 453382368,
            "l2_hits": 46921727,
            "l2_misses": 83160143,
            "l2_size": 1810888740352,
            "l2_asize": 1643495105536,
            "l2_read_bytes": 1_000_000,
            "l2_write_bytes": 2_000_000,
            "l2_feeds": 368802,
            "memory_throttle_count": 0,
        },
        zil={
            "zil_commit_count": 4304721,
            "zil_itx_metaslab_slog_count": 9557603,
            "zil_itx_metaslab_slog_write": 1010176118784,
        },
        vdevs=[],
        arcstats_available=True,
        zil_available=True,
        iostat_available=True,
    )


def _cache_vdev(pool="fivebays", vdev="CACHE1", read_bytes=1024, write_bytes=2048):
    return ms.VdevSample(
        pool=pool,
        vdev=vdev,
        section="cache",
        alloc=822486237184,
        free=169651208192,
        reads=10,
        writes=20,
        read_bytes=read_bytes,
        write_bytes=write_bytes,
    )


def _log_vdev(pool="fivebays", vdev="mirror-2", write_bytes=5138022):
    return ms.VdevSample(
        pool=pool,
        vdev=vdev,
        section="logs",
        alloc=16252928,
        free=8031588843,
        reads=0,
        writes=48,
        read_bytes=14,
        write_bytes=write_bytes,
    )


def _make_app():
    """Return a mock app with a real config dict, ready for the Memory page."""
    app = MagicMock()
    app.config = {}
    app.ctx = MagicMock()
    app.ctx.zfs_caps = None
    return app


class TestCreateMemoryPage(unittest.TestCase):
    def test_page_construction(self):
        with mock_gtk(fresh=True):
            import memory_page as mp

            app = _make_app()
            page = mp.create_memory_page(app)
            self.assertIsNotNone(page)
            self.assertIsNotNone(app._memory_ref_spin)
            self.assertIsNotNone(app._memory_arc_labels)
            self.assertIsNotNone(app._memory_l2_labels)
            self.assertIsNotNone(app._memory_slog_labels)
            self.assertIsNotNone(app._memory_l2_store)
            self.assertIsNotNone(app._memory_slog_store)
            # Stores must not walk mock iters (reconcile would loop forever).
            self.assertIsNone(app._memory_sample)

    def test_device_tables_bound_for_width_persistence(self):
        """Both device tables register with the UI-state persistence layer."""
        with mock_gtk(fresh=True) as gtk:
            views = []

            def _make_view(*args, **kwargs):
                view = MagicMock()
                views.append(view)
                return view

            gtk.ListStore = MagicMock(side_effect=lambda *a, **k: MagicMock())
            gtk.TreeView = MagicMock(side_effect=_make_view)
            import memory_page as mp

            app = _make_app()
            mp.create_memory_page(app)
            calls = app._ui_state.bind_treeview.call_args_list
            self.assertEqual(
                [(c.args[0], c.args[1]) for c in calls],
                [(views[0], "memory_l2_view"), (views[1], "memory_slog_view")],
            )

    def test_spin_defaults_from_config(self):
        with mock_gtk(fresh=True):
            import memory_page as mp

            app = _make_app()
            app.config = {"memory": {"refresh_seconds": 17}}
            mp.create_memory_page(app)
            app._memory_ref_spin.set_value.assert_called_once_with(17)

    def test_spin_change_persists_and_restarts_timer(self):
        with mock_gtk(fresh=True):
            import memory_page as mp

            app = _make_app()
            mp.create_memory_page(app)
            app._memory_ref_spin.get_value.return_value = 7
            with patch.object(mp, "save_memory_config") as save:
                mp._on_memory_refresh_changed(app._memory_ref_spin, app)
            save.assert_called_once()
            saved = save.call_args[0][1]
            self.assertEqual(saved["refresh_seconds"], 7)
            app._start_stop_memory_timer.assert_called_once_with("memory")


class TestApplyMemorySample(unittest.TestCase):
    def _prepared(self):
        """Return (module, app) with the page built and stores made iterable.

        Gtk.Label and Gtk.ListStore are given side_effects so every widget
        is a distinct mock (the shared defaults would merge all set_text
        histories and both device tables into one object).
        """
        app = _make_app()
        with mock_gtk(fresh=True) as gtk:
            gtk.Label = MagicMock(side_effect=lambda *a, **k: MagicMock())
            gtk.ListStore = MagicMock(side_effect=lambda *a, **k: MagicMock())
            import memory_page as mp

            mp.create_memory_page(app)
        app._memory_l2_store.get_iter_first.return_value = None
        app._memory_slog_store.get_iter_first.return_value = None
        return mp, app

    def test_arc_labels_update_with_rates(self):
        mp, app = self._prepared()
        mp._apply_memory_sample(app, _arc_sample(100.0))
        mp._apply_memory_sample(app, _arc_sample(105.0, hits=1500, misses=150))

        labels = app._memory_arc_labels
        labels["Size"].set_text.assert_called_with("30.41 GiB (67.6% of max 45.00 GiB)")
        labels["Hits/s"].set_text.assert_called_with("100")
        labels["Misses/s"].set_text.assert_called_with("10")
        labels["Hit rate (interval)"].set_text.assert_called_with("90.9%")
        app._memory_arc_note.hide.assert_called()

    def test_first_sample_shows_dashes_for_rates(self):
        mp, app = self._prepared()
        mp._apply_memory_sample(app, _arc_sample(100.0))
        app._memory_arc_labels["Hits/s"].set_text.assert_called_with("—")
        app._memory_arc_labels["Hit rate (interval)"].set_text.assert_called_with("—")

    def test_arc_unavailable_shows_note(self):
        mp, app = self._prepared()
        sample = _arc_sample(100.0)
        sample.arcstats_available = False
        mp._apply_memory_sample(app, sample)
        markup = app._memory_arc_note.set_markup.call_args[0][0]
        self.assertIn("not readable", markup)
        app._memory_arc_note.show.assert_called_once_with()

    def test_no_vdevs_notes(self):
        mp, app = self._prepared()
        mp._apply_memory_sample(app, _arc_sample(100.0))
        self.assertIn("No cache vdevs", app._memory_l2_note.set_markup.call_args[0][0])
        self.assertIn("No log vdevs", app._memory_slog_note.set_markup.call_args[0][0])

    def test_zil_missing_note_when_log_vdevs_present(self):
        mp, app = self._prepared()
        sample = _arc_sample(100.0)
        sample.vdevs = [_log_vdev()]
        sample.zil_available = False
        mp._apply_memory_sample(app, sample)
        markup = app._memory_slog_note.set_markup.call_args[0][0]
        self.assertIn("ZIL kstats are not exposed", markup)
        # The SLOG counters stay untouched (dashes from construction).

    def test_iostat_unavailable_notes(self):
        mp, app = self._prepared()
        sample = _arc_sample(100.0)
        sample.iostat_available = False
        mp._apply_memory_sample(app, sample)
        self.assertIn("zpool iostat", app._memory_l2_note.set_markup.call_args[0][0])
        self.assertIn("zpool iostat", app._memory_slog_note.set_markup.call_args[0][0])
        # L2ARC kstat values are still applied.
        size_calls = [c.args[0] for c in app._memory_l2_labels["Size"].set_text.call_args_list]
        self.assertIn("1.65 TiB", size_calls)

    def test_vdev_rows_appended_and_removed(self):
        mp, app = self._prepared()
        sample = _arc_sample(100.0)
        sample.vdevs = [_cache_vdev(), _log_vdev()]
        mp._apply_memory_sample(app, sample)
        appended = [c.args[0] for c in app._memory_l2_store.append.call_args_list]
        self.assertEqual(len(appended), 1)
        self.assertEqual(appended[0][0:2], ["fivebays", "CACHE1"])
        slog_appended = [c.args[0] for c in app._memory_slog_store.append.call_args_list]
        self.assertEqual(slog_appended[0][0:2], ["fivebays", "mirror-2"])

        # Devices disappear -> reconcile removes the row.
        tree_iter = MagicMock()
        store = app._memory_l2_store
        store.get_iter_first.return_value = tree_iter
        store.iter_next.return_value = None
        store.get_value.side_effect = lambda _it, col: ["fivebays", "CACHE1", "cap", "—", "—"][col]
        mp._apply_memory_sample(app, _arc_sample(105.0))
        store.remove.assert_called_once_with(tree_iter)

    def test_charts_append_per_sample(self):
        mp, app = self._prepared()
        mp._apply_memory_sample(app, _arc_sample(100.0))
        mp._apply_memory_sample(app, _arc_sample(105.0, hits=1500, misses=150))
        self.assertEqual(len(app._memory_arc_size_chart.points), 2)
        # The hit-rate chart only records intervals with traffic.
        self.assertEqual(len(app._memory_arc_rate_chart.points), 1)
        self.assertEqual(len(app._memory_l2_chart.points), 2)
        self.assertEqual(len(app._memory_slog_chart.points), 2)
        # Reference line tracks c_max.
        self.assertEqual(app._memory_arc_size_chart._reference, 48318382080)

    def test_refresh_pending_guard(self):
        mp, app = self._prepared()
        app._memory_refresh_pending = True
        with patch.object(mp.threading, "Thread") as thread:
            mp.refresh_memory_page(app)
        thread.assert_not_called()


class TestRollingChart(unittest.TestCase):
    def test_nice_ceiling_ladder(self):
        with mock_gtk():
            import memory_page as mp

            self.assertEqual(mp._nice_ceiling(0), 1.0)
            self.assertEqual(mp._nice_ceiling(1), 1.0)
            self.assertEqual(mp._nice_ceiling(3), 5.0)
            self.assertEqual(mp._nice_ceiling(7), 10.0)
            self.assertEqual(mp._nice_ceiling(80), 100.0)
            self.assertEqual(mp._nice_ceiling(900), 1000.0)

    def test_format_age(self):
        with mock_gtk():
            import memory_page as mp

            self.assertEqual(mp._format_age(45), "45s")
            self.assertEqual(mp._format_age(299), "4m 59s")
            self.assertEqual(mp._format_age(3661), "1h 01m")

    def test_window_trims_to_max_samples(self):
        with mock_gtk():
            import memory_page as mp

            chart = mp.RollingChart("t", ["a"], max_samples=3)
            for i in range(5):
                chart.append(float(i), [i])
            self.assertEqual(len(chart.points), 3)
            self.assertEqual(chart.points[0][0], 2.0)

    def test_draw_smoke(self):
        """A full draw pass must not raise with two series and a reference."""
        with mock_gtk():
            import memory_page as mp

            chart = mp.RollingChart("traffic", ["read", "write"])
            chart.set_reference(1000.0, "c_max")
            for i in range(4):
                chart.append(float(i), [i * 100, i * 50])
            widget = chart.widget
            widget.get_allocated_width.return_value = 400
            widget.get_allocated_height.return_value = 110
            chart._on_draw(widget, MagicMock())
            self.assertTrue(widget.queue_draw.called)


if __name__ == "__main__":
    unittest.main()
