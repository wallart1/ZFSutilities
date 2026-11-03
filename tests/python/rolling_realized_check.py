#!/usr/bin/env python3
"""Realized-window check for the Performance page's rolling charts.

Run directly (``python3 rolling_realized_check.py``) or via
tests/python/test_rolling_realized.py.  Builds the real Performance page
(GTK 3) inside a realized Gtk.Window and drives the rolling charts with
synthetic samples across a wide window, locking the surfaces the user
judges: the shared doubled chart height realized in the page, the shared
X-tick grammar drawn against the real font (interior ticks on a wide
window, collision thinning on a narrow one), and the post-stall
re-baseline (a sampling stall far beyond the configured interval drops
the rate point instead of averaging across the gap or drawing an
unmeasured zero).

It runs as a child process on purpose: binding the GUI layer to real GTK
(and warming matplotlib's GTK backend) inside the pytest process would
poison the mock-bound module caches the other suites rely on.

Needs a display, and it must be one this script made itself: it starts a
private Xvfb and never opens the ambient display — a realized window
flashing on the operator's desktop mid-suite is exactly the leak this
guards against.  When no private display can be produced the check
skips rather than fall back.  Exit codes: 0 pass, 3 skip (no private
display available), anything else failure with a traceback on stderr.
"""

import os
import sys
import types

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
TESTS_SRC = os.path.join(REPO_ROOT, "tests", "python")
for path in (PYTHON_SRC, TESTS_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)

# Reuse the alignment check's display plumbing (private Xvfb, GTK env
# scrub, rebind dance) — importing it is side-effect free (main is guarded).
from alignment_realized_check import _ensure_display

# A refresh interval whose 3x stall threshold (900 s) sits between the
# per-sample spacing (300 s) and the simulated stall (1200 s).
REFRESH_SECONDS = 300
SAMPLE_STEP = 300.0
STALL_EXTRA = 1200.0
SCREENSHOT_PATH = "/tmp/zfsutilities-rolling-realized.png"


def _arc_sample(mono, hits, misses=100):
    import memory_stats as ms

    return ms.MemorySample(
        monotonic=mono,
        arc={
            "hits": hits,
            "misses": misses,
            "size": 32648235840,
            "c": 32818317552,
            "c_max": 48318382080,
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


def _run_checks():
    from test_support import import_gui_fresh

    mp = import_gui_fresh("memory_page")
    ch = sys.modules["charting"]  # real-bound by the fresh import above

    # REALIZED_CHART_RENDERER=cairo forces the Cairo fallback so the
    # checks run under both renderers; the module cache must be flipped
    # before any page builds.
    if os.environ.get("REALIZED_CHART_RENDERER") == "cairo":
        ch._backend = None

    class _App:
        pass

    class _UIStateStub:
        """bind_treeview stand-in: the realized check does not persist widths."""

        def bind_treeview(self, view, state_key):
            pass

    app = _App()
    # The refresh interval decides the stall threshold; SAMPLE_STEP stays
    # comfortably inside it so the wide window reads as continuous data.
    app.config = {"memory": {"refresh_seconds": REFRESH_SECONDS}}
    app.ctx = types.SimpleNamespace(zfs_caps=None)
    app._ui_state = _UIStateStub()

    page = mp.create_memory_page(app)
    charts = [
        app._memory_arc_size_chart,
        app._memory_arc_rate_chart,
        app._memory_l2_chart,
        app._memory_slog_chart,
    ]
    renderer_name = type(charts[0]).__name__
    print(f"REALIZED-RENDERER: {renderer_name}")

    Gtk = mp.Gtk
    win = Gtk.Window()
    win.set_default_size(900, 1000)
    win.add(page)
    win.show_all()

    def pump(rounds=10):
        for _ in range(rounds):
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            # queue_draw() invalidations ride the frame clock, which does
            # not necessarily produce a pending event; force the paint
            # phase so the server-side window content stays current (the
            # Cairo fallback's DrawingAreas repaint through it).
            window = win.get_window()
            if window is not None:
                window.process_updates(True)

    pump()

    # --- Geometry: every chart realizes exactly the shared doubled height.
    for chart in charts:
        allocated = chart.widget.get_allocated_height()
        assert allocated == ch.ROLLING_CHART_HEIGHT, (
            f"{type(chart).__name__} realized at {allocated} px, "
            f"expected the shared {ch.ROLLING_CHART_HEIGHT}"
        )
    print("PASS geometry: every chart realizes the shared doubled height")

    # --- Wide window: the shared tick grammar's five X ticks exist.
    for index in range(6):
        mp._apply_memory_sample(app, _arc_sample(index * SAMPLE_STEP, hits=1000 + index * 500))
    pump()
    span = 5 * SAMPLE_STEP
    if renderer_name == "MatplotlibRollingChart":
        ticks = list(charts[0]._ax.get_xticks())
        assert len(ticks) == ch.rolling_tick_count(span), ticks
        assert ticks[0] == 0.0 and abs(ticks[-1] - span) < 1e-6, ticks
    else:
        # The Cairo fallback lays its ticks out at draw time against the
        # real font: a wide plot carries all five, a narrow one thins to
        # the two edge-aligned ends.
        import cairo

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
        cr = cairo.Context(surface)
        cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9)
        wide = mp._x_tick_layout(cr, span, 58.0, 800.0)
        assert len(wide) == ch.rolling_tick_count(span), wide
        assert wide[0][1].startswith("-") and wide[-1][1] == "now", wide
        narrow = mp._x_tick_layout(cr, span, 58.0, 60.0)
        assert [label for _x, label, _lx in narrow] == [wide[0][1], "now"], narrow
    print("PASS x ticks: five on a wide window, thinned on a narrow one")

    # --- Post-stall re-baseline: rates over the stall were never measured.
    rate_points_before = len(app._memory_arc_rate_chart.points)
    size_points_before = len(app._memory_arc_size_chart.points)
    stalled_at = span + STALL_EXTRA
    mp._apply_memory_sample(app, _arc_sample(stalled_at, hits=8000))
    pump()
    assert len(app._memory_arc_rate_chart.points) == rate_points_before, (
        "the stall sample must not add a rate point"
    )
    assert len(app._memory_arc_size_chart.points) == size_points_before + 1, (
        "the size gauge keeps plotting across a stall"
    )
    interval_label = app._memory_arc_labels["Hit rate (interval)"].get_text()
    assert interval_label == "—", repr(interval_label)

    # Sampling continues normally after the re-baseline.
    mp._apply_memory_sample(app, _arc_sample(stalled_at + SAMPLE_STEP, hits=9500))
    pump()
    assert len(app._memory_arc_rate_chart.points) == rate_points_before + 1
    hits_label = app._memory_arc_labels["Hits/s"].get_text()
    assert hits_label == "5", repr(hits_label)  # (9500-8000)/300
    print("PASS stall: rate point dropped, gauge kept, baseline resumed")

    _screenshot(win)
    win.destroy()
    pump()


def _screenshot(win):
    """Best-effort PNG of the realized window, for visual review only."""
    try:
        import gi

        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk

        window = win.get_window()
        pixbuf = Gdk.pixbuf_get_from_window(window, 0, 0, window.get_width(), window.get_height())
        if pixbuf is not None:
            pixbuf.savev(SCREENSHOT_PATH, "png", [], [])
            print(f"REALIZED-SHOT: {SCREENSHOT_PATH}")
    except Exception as exc:  # the shot is informational only
        print(f"REALIZED-SHOT-SKIPPED: {exc}")


def main():
    xvfb = _ensure_display()
    try:
        _run_checks()
    finally:
        if xvfb is not None:
            xvfb.terminate()
    print("ROLLING-REALIZED-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
