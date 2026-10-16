#!/usr/bin/env python3
"""Charting spike — matplotlib FigureCanvasGTK3Agg in the real GTK3 stack.

Task 2.3 proof that matplotlib embeds in the GUI on this host
(Python 3.12, GTK 3.24.41, matplotlib installed with
``pip3 install --user --break-system-packages matplotlib``).

What this proves, in one window:

1. ``matplotlib.backends.backend_gtk3agg.FigureCanvasGTK3Agg`` imports
   alongside the GUI's own ``gi`` usage (no version conflict).
2. The canvas is a real ``Gtk.Widget`` and packs into the same
   ``Gtk.Window`` as the existing Cairo ``RollingChart`` from
   ``python/memory_page.py`` (imported unmodified) — both render side by
   side, proving coexistence with the current architecture.
3. The live-refresh model works: a ``GLib.timeout`` tick appends samples
   to the Cairo chart (its ``queue_draw`` path) and updates the matplotlib
   artists via ``set_data`` + ``draw_idle`` — the same per-tick pattern
   the Performance page uses.
4. The Agg canvas actually renders: ``buffer_rgba()`` contains chart
   pixels (not a blank/uniform buffer), a window screenshot is written
   out, and a mid-run window resize forces reallocation + re-render.
5. Redraw cost is measured (``canvas.draw()`` timing) so per-refresh
   redraws are known to be cheap.

Run headless:

    NO_AT_BRIDGE=1 xvfb-run -a python3 spikes/charting_spike_gtk3_matplotlib.py

Outputs ``spikes/charting_spike_gtk3_matplotlib.png`` (window screenshot)
and prints one PASS/FAIL line per check; exit status 0 only if all pass.
"""

import os
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "python"))

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
import matplotlib
from gi.repository import Gdk, GLib, Gtk

# Real GUI code, imported exactly as the application does (module order
# matters: gi.require_version("Gtk", "3.0") must precede both this import
# and matplotlib's GTK3 backend import — both request the same version).
from memory_page import RollingChart  # existing Cairo chart, unmodified

matplotlib.use("gtk3agg")

import numpy as np
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure

_SCREENSHOT = os.path.join(_REPO, "spikes", "charting_spike_gtk3_matplotlib.png")

_RESULTS = []


def check(name, ok, detail=""):
    _RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def build_window():
    """One Gtk.Window holding the existing Cairo chart and a matplotlib canvas."""
    win = Gtk.Window(title="Charting spike: Cairo RollingChart + matplotlib")
    win.set_default_size(1120, 460)

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    box.set_margin_start(10)
    box.set_margin_end(10)
    box.set_margin_top(10)
    box.set_margin_bottom(10)
    win.add(box)

    # Left: the existing Cairo-drawn rolling chart from python/memory_page.py.
    cairo_chart = RollingChart("ARC size (Cairo, existing)", ["size"], height=200)
    box.pack_start(cairo_chart.widget, True, True, 0)

    # Right: matplotlib FigureCanvasGTK3Agg with a representative rolling
    # time-series (two series + translucent fills, like the L2ARC chart)
    # and a histogram (the blocksize-distribution shape the Alignment view
    # needs).  Plain layout, not constrained_layout: constrained layout
    # re-solves every draw and triples steady-state redraw cost (measured
    # ~150 ms vs ~50 ms at this size).
    fig = Figure(figsize=(5.6, 4.0), dpi=100)
    fig.patch.set_facecolor("white")

    ax = fig.add_subplot(2, 1, 1)
    ax.set_title("Rolling time-series (matplotlib gtk3agg)", fontsize=10)
    ax.grid(True, alpha=0.3)
    (line_a,) = ax.plot([], [], lw=1.6, color="#3366b3", label="read")
    (fill_a,) = ax.fill([], [], color="#3366b3", alpha=0.15)
    (line_b,) = ax.plot([], [], lw=1.6, color="#f57800", label="write")
    (fill_b,) = ax.fill([], [], color="#f57800", alpha=0.15)
    ax.legend(loc="upper left", fontsize=8, frameon=False)

    ax2 = fig.add_subplot(2, 1, 2)
    ax2.set_title("Blocksize histogram (matplotlib gtk3agg)", fontsize=10)
    ax2.grid(True, alpha=0.3)
    (bars,) = ax2.bar([0], [0], width=0.8, color="#3366b3", alpha=0.85)
    fig.tight_layout()

    canvas = FigureCanvasGTK3Agg(fig)
    canvas.set_size_request(560, 420)
    box.pack_start(canvas, True, True, 0)
    return win, cairo_chart, canvas, (line_a, fill_a, line_b, fill_b, ax, ax2, bars)


def main():
    win, cairo_chart, canvas, artists = build_window()
    line_a, fill_a, line_b, fill_b, ax, ax2, bars = artists

    check(
        "FigureCanvasGTK3Agg is a Gtk.Widget",
        isinstance(canvas, Gtk.Widget),
        type(canvas).__mro__[1].__name__,
    )

    win.show_all()
    while Gtk.events_pending():
        Gtk.main_iteration()

    rng = np.random.default_rng(42)
    n = 240
    t = np.arange(n, dtype=float)
    series_a = 300e6 + 40e6 * np.sin(t / 18.0) + rng.normal(0, 8e6, n)
    series_b = 60e6 + 25e6 * np.abs(np.sin(t / 30.0)) + rng.normal(0, 4e6, n)

    # Emulate one matplotlib redraw cost (fresh full-figure render).
    line_a.set_data(t, series_a)
    line_b.set_data(t, series_b)
    fill_a.xy = np.column_stack(
        [np.concatenate([t, t[::-1]]), np.concatenate([series_a, np.zeros(n)])]
    )
    fill_b.xy = np.column_stack(
        [np.concatenate([t, t[::-1]]), np.concatenate([series_b, np.zeros(n)])]
    )
    ax.relim()
    ax.autoscale_view()
    start = time.perf_counter()
    canvas.draw()
    draw_ms = (time.perf_counter() - start) * 1000.0
    check("canvas.draw() full render", draw_ms < 250.0, f"{draw_ms:.1f} ms")

    buf = np.asarray(canvas.buffer_rgba())
    unique_colors = len(np.unique(buf.reshape(-1, buf.shape[2]), axis=0))
    check(
        "Agg buffer has rendered content (non-uniform pixels)",
        unique_colors > 500,
        f"{unique_colors} unique RGBA colors, shape {buf.shape}",
    )

    # Live-refresh model: per-tick appends to the Cairo chart and artist
    # updates + draw_idle on the matplotlib canvas, from a GLib timeout —
    # the same wiring the Performance page's refresh timer uses.
    state = {"tick": 0, "bars": [bars]}

    def _swap_histogram(values):
        for patch in state["bars"]:
            patch.remove()
        counts, edges = np.histogram(values, bins=24)
        state["bars"] = list(
            ax2.bar(
                edges[:-1],
                counts,
                width=np.diff(edges),
                align="edge",
                color="#3366b3",
                alpha=0.85,
            )
        )

    def on_tick():
        state["tick"] += 1
        k = state["tick"]
        cairo_chart.append(float(k), [float(series_a[k % n])])
        slide = slice(max(0, k - 120), k + 1)
        x = t[slide] - t[slide][0]
        ya, yb = series_a[slide], series_b[slide]
        line_a.set_data(x, ya)
        line_b.set_data(x, yb)
        fill_a.xy = np.column_stack(
            [np.concatenate([x, x[::-1]]), np.concatenate([ya, np.zeros(len(ya))])]
        )
        fill_b.xy = np.column_stack(
            [np.concatenate([x, x[::-1]]), np.concatenate([yb, np.zeros(len(yb))])]
        )
        ax.relim()
        ax.autoscale_view()
        # Histogram update (bar artists) as the Alignment view would do.
        _swap_histogram(series_a[slide])
        canvas.draw_idle()
        if state["tick"] == 12:
            # Force a reallocation + re-render mid-run, as a window/paned
            # resize would, then let pending draws land before capture.
            win.resize(1320, 560)
        if state["tick"] >= 24:
            Gtk.main_quit()
            return False
        return True

    GLib.timeout_add(30, on_tick)
    GLib.timeout_add_seconds(20, Gtk.main_quit)  # safety net
    Gtk.main()
    while Gtk.events_pending():
        Gtk.main_iteration()

    check("live-refresh ticks ran", state["tick"] >= 24, f"{state['tick']} ticks")

    # Warm redraw cost (fonts cached, same artists) — the per-refresh
    # cost the Performance page would actually pay each tick.  Budget
    # check, not a micro-benchmark: the page's refresh interval is
    # user-configurable 1–300 s (default 5 s), so a full redraw stays
    # acceptable while it is comfortably under the 1 s minimum (the
    # blit path below covers any future sub-second need).
    alloc_w = canvas.get_allocated_width()
    alloc_h = canvas.get_allocated_height()
    warm = []
    for _ in range(5):
        start = time.perf_counter()
        canvas.draw()
        warm.append((time.perf_counter() - start) * 1000.0)
    check(
        "warm canvas.draw() steady-state cost",
        max(warm) < 250.0,
        f"max {max(warm):.1f} ms over 5 draws (median {sorted(warm)[2]:.1f} ms) "
        f"at {alloc_w}x{alloc_h} px",
    )

    # Blitted-update path: restore a cached background and redraw only the
    # changed artists — the fast per-tick route if a live chart ever needs
    # sub-full-redraw updates.
    canvas.draw()
    background = canvas.copy_from_bbox(ax.bbox)
    blit_ms = []
    for k in range(5):
        line_a.set_data(t, series_a + 5e6 * k)
        start = time.perf_counter()
        canvas.restore_region(background)
        ax.draw_artist(line_a)
        canvas.blit(ax.bbox)
        blit_ms.append((time.perf_counter() - start) * 1000.0)
    check(
        "blitted artist update cost",
        max(blit_ms) < 20.0,
        f"max {max(blit_ms):.1f} ms over 5 updates (median {sorted(blit_ms)[2]:.1f} ms)",
    )

    gdk_win = win.get_window()
    ok_shot = False
    if gdk_win is not None:
        pb = Gdk.pixbuf_get_from_window(gdk_win, 0, 0, gdk_win.get_width(), gdk_win.get_height())
        if pb is not None:
            pb.savev(_SCREENSHOT, "png", [], [])
            ok_shot = os.path.exists(_SCREENSHOT) and os.path.getsize(_SCREENSHOT) > 20000
    check(
        "window screenshot captured (both charts on-screen)",
        ok_shot,
        _SCREENSHOT if ok_shot else "no/empty screenshot",
    )

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
