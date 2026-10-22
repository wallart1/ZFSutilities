"""Tests for memory_page.py — Performance tab widgets, notes, and charts."""

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


def _cache_vdev(pool="fivebays", vdev="CACHE1", read_bps=1024, write_bps=2048):
    return ms.VdevSample(
        pool=pool,
        vdev=vdev,
        section="cache",
        alloc=822486237184,
        free=169651208192,
        reads_ps=10,
        writes_ps=20,
        read_bps=read_bps,
        write_bps=write_bps,
    )


def _log_vdev(pool="fivebays", vdev="mirror-2", write_bps=5138022):
    return ms.VdevSample(
        pool=pool,
        vdev=vdev,
        section="logs",
        alloc=16252928,
        free=8031588843,
        reads_ps=0,
        writes_ps=48,
        read_bps=14,
        write_bps=write_bps,
    )


def _make_app():
    """Return a mock app with a real config dict, ready for the Performance page."""
    app = MagicMock()
    app.config = {}
    app.ctx = MagicMock()
    app.ctx.zfs_caps = None
    return app


def _tracked_widget(seen):
    """Return a fresh MagicMock and record it in *seen* (per-call factory)."""
    widget = MagicMock()
    seen.append(widget)
    return widget


class TestCreateMemoryPage(unittest.TestCase):
    def test_arc_header_names_active_renderer(self):
        """The section header names the chart renderer, so a Cairo
        fallback is visible at a glance instead of inferred from chart
        smoothness (the classic cause: the GUI runs as root while
        matplotlib sits in a user's pip --user site)."""
        with mock_gtk(fresh=True):
            import memory_page as mp

            app = _make_app()
            with patch.object(mp, "section_header", wraps=mp.section_header) as header:
                mp.create_memory_page(app)
            arc_calls = [
                call
                for call in header.call_args_list
                if call.args[:1] == ("ARC — Adaptive Replacement Cache",)
            ]
            self.assertEqual(len(arc_calls), 1)
            subtitle = arc_calls[0].args[1]
            self.assertIn("charts: ", subtitle)
            # Under mock_gtk the matplotlib probe cannot load, so the
            # label names the Cairo fallback and its fix.
            self.assertIn("Cairo fallback", subtitle)
            self.assertIn("python3-matplotlib", subtitle)

    def test_page_construction(self):
        with mock_gtk(fresh=True) as gtk:
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
            # The page hosts both Performance views behind the switcher.
            self.assertEqual(set(app._memory_view_radios), {"charts", "alignment"})
            self.assertIsNotNone(app._memory_view_stack)
            # The page ScrolledWindow is exposed so the Alignment refresh
            # path can save/restore the vertical offset around each apply.
            self.assertIsNotNone(app.performance_scrolled)
            self.assertIs(page, app.performance_scrolled)
            # Stores must not walk mock iters (reconcile would loop forever).
            self.assertIsNone(app._memory_sample)
            # The page is titled Performance (the sidebar tab name). Label is
            # one shared mock, so assert on the recorded markup calls.
            markups = [
                call.args[0]
                for call in gtk.Label.return_value.set_markup.call_args_list
                if call.args
            ]
            self.assertIn("<big><b>Performance</b></big>", markups)

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
            # The Alignment view (second Performance view) binds its four
            # tables first, then the charts view's L2ARC and SLOG tables.
            self.assertEqual(
                [(c.args[0], c.args[1]) for c in calls],
                [
                    (views[0], "alignment_chain_view"),
                    (views[1], "alignment_topology_view"),
                    (views[2], "alignment_findings_view"),
                    (views[3], "alignment_workload_view"),
                    (views[4], "memory_l2_view"),
                    (views[5], "memory_slog_view"),
                ],
            )

    def test_page_sizes_content_by_natural_height(self):
        """The page viewport must follow the content's natural height.

        The page mixes fixed-minimum table windows with naturally sized
        content (labels, the ladder); the default MINIMUM policy clamps
        the page box to the window height and the box then crushes the
        naturally sized children toward their minimums — the historical
        two-rows-per-table defect.
        """
        with mock_gtk(fresh=True):
            import memory_page as mp

            app = _make_app()
            page = mp.create_memory_page(app)
            viewport = page.get_child()
            viewport.set_vscroll_policy.assert_called_once_with(mp.Gtk.ScrollablePolicy.NATURAL)

    def test_device_tables_scroll_in_capped_windows(self):
        """Every Performance-page table gets its own fixed 20-row scrolled
        window with an honest far-right column (expand redirected to a
        non-last column)."""
        with mock_gtk(fresh=True) as gtk:
            views = []
            scrolls = []
            columns = []

            def _make_view(*args, **kwargs):
                view = MagicMock()
                views.append(view)
                return view

            def _make_scroll(*args, **kwargs):
                scroll = MagicMock()
                scrolls.append(scroll)
                return scroll

            def _make_column(*args, **kwargs):
                col = MagicMock()
                columns.append(col)
                return col

            gtk.ListStore = MagicMock(side_effect=lambda *a, **k: MagicMock())
            gtk.TreeView = MagicMock(side_effect=_make_view)
            gtk.ScrolledWindow = MagicMock(side_effect=_make_scroll)
            gtk.TreeViewColumn = MagicMock(side_effect=_make_column)
            import gui_helpers as gh
            import memory_page as mp

            app = _make_app()
            mp.create_memory_page(app)
            # ScrolledWindow creation order: the page window, the chain
            # table, the ladder window, then topology/findings/workload,
            # then L2ARC/SLOG.
            self.assertEqual(len(scrolls), 8)
            # The fixed Performance-page window: min == max == the 20-row
            # cap, so short and empty tables keep their 20-line window
            # (the one-row allowance absorbs the horizontal scrollbar).
            row = gh.TREEVIEW_ROW_HEIGHT_FALLBACK
            cap = (row + 2) + (gh.TABLE_ROW_TARGET + 1) * row
            table_scrolls = scrolls[1:2] + scrolls[3:6] + scrolls[6:8]
            table_views = views[0:4] + views[4:6]
            for scroll, view in zip(table_scrolls, table_views):
                scroll.add.assert_called_once_with(view)
                scroll.set_propagate_natural_height.assert_called_once_with(True)
                scroll.set_min_content_height.assert_called_once_with(cap)
                scroll.set_max_content_height.assert_called_once_with(cap)
            # The ladder window is not a capped table window: it carries a
            # small minimum width so the canvas's request can never widen
            # the page (its max_content_width is floored by alignment_page).
            scrolls[2].set_min_content_width.assert_called_once_with(gh.TREEVIEW_MIN_WIDTH)
            # Columns: 21 for the Alignment tables, then 5 per device
            # table.  Each device table expands its Vdev column (second of
            # five) so the far-right column keeps its fixed width, and
            # every column starts at a sane width with a real minimum.
            self.assertEqual(len(columns), 31)
            for table in (columns[21:26], columns[26:31]):
                for col in table:
                    self.assertGreaterEqual(col.set_fixed_width.call_args.args[0], 60)
                    col.set_min_width.assert_called_once_with(60)
                table[1].set_expand.assert_called_once_with(True)
                for col in (table[0], *table[2:]):
                    col.set_expand.assert_not_called()

    def test_spin_defaults_from_config(self):
        with mock_gtk(fresh=True):
            import memory_page as mp

            app = _make_app()
            app.config = {"memory": {"refresh_seconds": 17}}
            mp.create_memory_page(app)
            app._memory_ref_spin.set_value.assert_called_once_with(17)

    def test_charts_do_not_expand_vertically_at_pack_sites(self):
        """Charts fill the page width but keep their designed height.

        Regression guard for the tall-chart defect: the three vertical pack
        sites (the ARC chart row, the L2ARC chart, the SLOG chart) must pack
        without expand so window height never stretches a chart, while the
        ARC pair still expands to share the row's width.  Box and
        DrawingArea get per-call side effects so pack calls are traced by
        widget identity instead of the shared default mocks.
        """
        with mock_gtk(fresh=True) as gtk:
            boxes = []
            gtk.Box = MagicMock(side_effect=lambda *a, **k: _tracked_widget(boxes))
            gtk.DrawingArea = MagicMock(side_effect=lambda *a, **k: MagicMock())
            import memory_page as mp

            app = _make_app()
            mp.create_memory_page(app)

            def _packs(box, child):
                return any(c.args[0] is child for c in box.pack_start.call_args_list)

            def _flags(box, child):
                matching = [c for c in box.pack_start.call_args_list if c.args[0] is child]
                self.assertEqual(len(matching), 1, "each chart is packed exactly once")
                return (matching[0].args[1], matching[0].args[2])

            l2_widget = app._memory_l2_chart.widget
            slog_widget = app._memory_slog_chart.widget
            size_widget = app._memory_arc_size_chart.widget
            rate_widget = app._memory_arc_rate_chart.widget

            # The charts-view box is the one that packs the L2ARC chart; the
            # ARC row is the horizontal box that packs the ARC chart widgets.
            charts_box = next(b for b in boxes if _packs(b, l2_widget))
            arc_row = next(b for b in boxes if _packs(b, size_widget))

            # No vertical expansion at any of the three sites.
            self.assertEqual(_flags(charts_box, l2_widget), (False, False))
            self.assertEqual(_flags(charts_box, slog_widget), (False, False))
            self.assertEqual(_flags(charts_box, arc_row), (False, False))
            # Inside the ARC row the two charts still expand to share width.
            self.assertEqual(_flags(arc_row, size_widget), (True, True))
            self.assertEqual(_flags(arc_row, rate_widget), (True, True))

            # The designed height itself stays a size request on the chart
            # widget (set by whichever renderer the factory picked),
            # independent of the pack sites and of the drawing code.
            for chart in (
                app._memory_arc_size_chart,
                app._memory_arc_rate_chart,
                app._memory_l2_chart,
                app._memory_slog_chart,
            ):
                chart.widget.set_size_request.assert_called_once_with(-1, 110)

    def test_charts_built_through_renderer_factory(self):
        """All four live charts are created via the shared renderer factory.

        The factory picks matplotlib when its GTK3 backend is available and
        the Cairo RollingChart otherwise — under mock_gtk the backend
        cannot load, so this also pins the fallback selection the suites
        rely on.
        """
        with mock_gtk(fresh=True):
            import memory_page as mp
            from memory_page import RollingChart

            app = _make_app()
            with patch.object(mp, "create_rolling_chart", wraps=mp.create_rolling_chart) as factory:
                mp.create_memory_page(app)
            self.assertEqual(
                [c.args[0] for c in factory.call_args_list],
                ["ARC size", "ARC hit rate", "L2ARC traffic", "SLOG writes"],
            )
            self.assertTrue(factory.call_args_list[1].kwargs["percent"])
            for chart in (
                app._memory_arc_size_chart,
                app._memory_arc_rate_chart,
                app._memory_l2_chart,
                app._memory_slog_chart,
            ):
                self.assertIsInstance(chart, RollingChart)

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
        # Device rates pass through on the very first sample (regression
        # guard: they must never render as constant 0/s).
        self.assertEqual(appended[0][3:], [ms.format_rate(1024), ms.format_rate(2048)])
        slog_appended = [c.args[0] for c in app._memory_slog_store.append.call_args_list]
        self.assertEqual(slog_appended[0][0:2], ["fivebays", "mirror-2"])
        self.assertEqual(slog_appended[0][3:], [ms.format_per_second(48), ms.format_rate(5138022)])

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
    """The Cairo fallback renderer (matplotlib charts are tested in
    test_charting.py; the shared vocabulary moved there with it)."""

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
