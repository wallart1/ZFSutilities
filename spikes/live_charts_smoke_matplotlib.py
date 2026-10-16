#!/usr/bin/env python3
"""Live-charts smoke — the production renderer path under real GTK3.

Task 2.5 verification that the Performance page's live charts, as rewired
through ``charting.create_rolling_chart()``, render with matplotlib and
refresh smoothly in the real GTK stack.  Builds the four production charts
in the page's layout (ARC size + hit-rate pair, L2ARC traffic, SLOG
writes), feeds them synthetic samples on a GLib timeout exactly the way
``memory_page._apply_memory_sample`` does (``set_reference`` + ``append``
per tick), and checks:

1. the factory selected the matplotlib renderer (backend available);
2. every canvas rendered real content (non-uniform pixel buffers);
3. the live-refresh loop ran and a warm full redraw stays far below the
   page's minimum 1 s refresh interval;
4. a mid-run window resize reallocates and re-renders;
5. a window screenshot is written out for visual review.

Run headless:

    NO_AT_BRIDGE=1 xvfb-run -a python3 spikes/live_charts_smoke_matplotlib.py

Outputs ``spikes/live_charts_smoke_matplotlib.png`` and prints one
PASS/FAIL line per check; exit status 0 only if all pass.
"""

import math
import os
import random
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "python"))

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from charting import create_rolling_chart, matplotlib_backend
from disk_repository import format_bytes
from gi.repository import Gdk, GLib, Gtk

_SCREENSHOT = os.path.join(_REPO, "spikes", "live_charts_smoke_matplotlib.png")
_RESULTS = []


def check(name, ok, detail=""):
    _RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


GIB = 1024**3
MIB = 1024**2


def build_window():
    """The four live charts in the Performance page's layout."""
    win = Gtk.Window(title="Live charts smoke: matplotlib via create_rolling_chart")
    win.set_default_size(950, 560)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_margin_start(15)
    box.set_margin_end(15)
    box.set_margin_top(15)
    box.set_margin_bottom(15)
    win.add(box)

    arc_size = create_rolling_chart("ARC size", ["size"])
    arc_rate = create_rolling_chart(
        "ARC hit rate", ["hit rate"], percent=True, formatter=lambda v: f"{v:.0f}"
    )
    arc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    arc_row.pack_start(arc_size.widget, True, True, 0)
    arc_row.pack_start(arc_rate.widget, True, True, 0)
    # Packed without vertical expand, exactly like the page (task 1.2).
    box.pack_start(arc_row, False, False, 0)

    l2_chart = create_rolling_chart("L2ARC traffic", ["read", "write"])
    box.pack_start(l2_chart.widget, False, False, 0)

    slog_chart = create_rolling_chart("SLOG writes", ["write"])
    box.pack_start(slog_chart.widget, False, False, 0)

    return win, (arc_size, arc_rate, l2_chart, slog_chart)


def main():
    backend = matplotlib_backend()
    check("matplotlib backend selected by the probe", backend is not None)

    win, charts = build_window()
    arc_size, arc_rate, l2_chart, slog_chart = charts
    for chart in charts:
        check(
            f"factory built a matplotlib chart ({chart.title})",
            type(chart).__name__ == "MatplotlibRollingChart",
        )

    win.show_all()
    while Gtk.events_pending():
        Gtk.main_iteration()

    c_max = 45 * GIB
    rng = random.Random(7)
    state = {
        "tick": 0,
        "t": 240,  # pre-fill 240 samples so the window is 20 min "old"
    }

    def _sample(t):
        size = 30 * GIB + 3 * GIB * math.sin(t / 40.0) + rng.uniform(-0.2, 0.2) * GIB
        hit = 78 + 14 * math.sin(t / 25.0) + rng.uniform(-2, 2)
        l2_read = (18 + 10 * abs(math.sin(t / 15.0))) * MIB + rng.uniform(0, 2) * MIB
        l2_write = (2 + 1.5 * abs(math.sin(t / 9.0))) * MIB + rng.uniform(0, 0.4) * MIB
        slog = (30 + 20 * abs(math.sin(t / 7.0))) * MIB + rng.uniform(0, 3) * MIB
        return size, hit, l2_read, l2_write, slog

    # Pre-fill the rolling windows, then measure one warm full redraw of
    # each canvas at its allocated size.
    for k in range(state["t"]):
        size, hit, l2r, l2w, slog = _sample(k)
        arc_size.set_reference(c_max, f"c_max {format_bytes(c_max)}")
        arc_size.append(float(k), [size])
        arc_rate.append(float(k), [hit])
        l2_chart.append(float(k), [l2r, l2w])
        slog_chart.append(float(k), [slog])
    while Gtk.events_pending():
        Gtk.main_iteration()

    update_ms = []
    for k in range(state["t"], state["t"] + 5):
        size, hit, l2r, l2w, slog = _sample(k)
        start = time.perf_counter()
        arc_size.set_reference(c_max, f"c_max {format_bytes(c_max)}")
        arc_size.append(float(k), [size])
        arc_rate.append(float(k), [hit])
        l2_chart.append(float(k), [l2r, l2w])
        slog_chart.append(float(k), [slog])
        update_ms.append((time.perf_counter() - start) * 1000.0)
    draw_ms = []
    for chart in charts:
        start = time.perf_counter()
        chart.widget.draw()
        draw_ms.append((time.perf_counter() - start) * 1000.0)
    check(
        "warm full redraw well under the 1 s minimum refresh",
        max(draw_ms) < 250.0,
        f"per-chart full draw max {max(draw_ms):.0f} ms, artist update per tick "
        f"max {max(update_ms):.1f} ms ({charts[0].widget.get_allocated_width()}x"
        f"{charts[0].widget.get_allocated_height()} px ARC charts)",
    )

    def on_tick():
        state["tick"] += 1
        k = state["t"] + state["tick"]
        size, hit, l2r, l2w, slog = _sample(k)
        arc_size.set_reference(c_max, f"c_max {format_bytes(c_max)}")
        arc_size.append(float(k), [size])
        arc_rate.append(float(k), [hit])
        l2_chart.append(float(k), [l2r, l2w])
        slog_chart.append(float(k), [slog])
        if state["tick"] == 12:
            win.resize(1250, 640)  # force canvas reallocation mid-run
        if state["tick"] >= 30:
            Gtk.main_quit()
            return False
        return True

    GLib.timeout_add(100, on_tick)
    GLib.timeout_add_seconds(20, Gtk.main_quit)  # safety net
    Gtk.main()
    while Gtk.events_pending():
        Gtk.main_iteration()

    check("live-refresh ticks ran", state["tick"] >= 30, f"{state['tick']} ticks")

    import numpy as np

    for chart in charts:
        buf = np.asarray(chart.widget.buffer_rgba())
        unique = len(np.unique(buf.reshape(-1, buf.shape[2]), axis=0))
        check(
            f"canvas rendered content ({chart.title})",
            unique > 200,
            f"{unique} unique RGBA colors at {buf.shape[1]}x{buf.shape[0]} px",
        )

    gdk_win = win.get_window()
    ok_shot = False
    if gdk_win is not None:
        pb = Gdk.pixbuf_get_from_window(gdk_win, 0, 0, gdk_win.get_width(), gdk_win.get_height())
        if pb is not None:
            pb.savev(_SCREENSHOT, "png", [], [])
            ok_shot = os.path.exists(_SCREENSHOT) and os.path.getsize(_SCREENSHOT) > 20000
    check(
        "window screenshot captured",
        ok_shot,
        _SCREENSHOT if ok_shot else "no/empty screenshot",
    )

    import matplotlib

    print(
        f"matplotlib {matplotlib.__version__}, GTK "
        f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}, "
        f"Python {sys.version.split()[0]}"
    )
    if all(_RESULTS):
        print("ALL CHECKS PASSED")
        return 0
    print("SOME CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
