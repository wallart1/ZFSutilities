# GUI Charting

Decision record for chart rendering inside the GTK3 GUI — what the
Performance page charts are drawn with, how the library is embedded, what
it costs, and what has to happen on production hosts. Written after the
Task 2.3 spike; the pages that build charts on top of this are
[GTK GUI Reference](../user-guide/gtk-gui.md) (Performance tab).

## Decision

The Performance page uses **matplotlib embedded in GTK3** via
`FigureCanvasGTK3Agg` for its high-quality charts — both the live-charts
refresh and the blocksize-alignment visuals. The existing Cairo-drawn
`RollingChart` (`python/memory_page.py`) stays in the tree as the
**fallback renderer when matplotlib is not installed**, so the GUI keeps
working on hosts without the optional package.

## Proof (spike)

`spikes/charting_spike_gtk3_matplotlib.py` embeds a matplotlib canvas and
the unmodified Cairo `RollingChart` side by side in one `Gtk.Window` and
exercises the live-refresh path. Run headless:

```bash
NO_AT_BRIDGE=1 xvfb-run -a python3 spikes/charting_spike_gtk3_matplotlib.py
```

All checks passed on the test VM (Python 3.12.3, GTK 3.24.41,
matplotlib 3.11.2): import alongside the GUI's `gi` usage, canvas is a
real `Gtk.Widget`, live refresh via `GLib` timeout + `draw_idle`,
mid-run window resize re-render, non-blank pixel buffer, and a window
screenshot written next to the spike.

## The proven embed pattern

```python
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")  # see gotcha below
from gi.repository import Gtk

import matplotlib

matplotlib.use("gtk3agg")
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.figure import Figure

fig = Figure(figsize=(5.6, 4.0), dpi=100)
ax = fig.add_subplot(1, 1, 1)
(line,) = ax.plot([], [], lw=1.6)
canvas = FigureCanvasGTK3Agg(fig)  # a Gtk.Widget — pack it directly
canvas.set_size_request(560, 220)

# per refresh tick (main thread):
line.set_data(xs, ys)
ax.relim()
ax.autoscale_view()
canvas.draw_idle()
```

### Gotchas found by the spike

- **Pin `Gdk` to 3.0.** Hosts that also have GTK4 installed (like the
  test VM) resolve an unpinned `Gdk` import to 4.0, after which
  `Gtk` 3.0 cannot load at all. The existing GUI modules only import
  `GLib`/`Gtk` at module level, which is why they never hit this; any
  new module-level `Gdk` import must pin the version.
- **Do not use `constrained_layout`** on live-refreshed figures. It
  re-solves the layout on every draw and tripled the steady-state redraw
  cost in the spike (~150 ms vs ~50 ms at 560×420). Call
  `fig.tight_layout()` once at build time instead.
- **Import matplotlib lazily**, never at module level in a GUI module.
  The test suites import every `gi`-importing module under the
  `mock_gtk()` fake (see [Testing](testing.md)), where real GTK — and
  therefore matplotlib's GTK backend — does not exist. The import belongs
  behind a try/except at chart-construction time, falling back to the
  Cairo renderer.

## Measured cost

Warm full `canvas.draw()` ≈ 50 ms at 560×420 px and ≈ 90–112 ms at
925×540 px on the test VM (cost scales with canvas pixels); blitted
artist update (`copy_from_bbox`/`restore_region`/`blit`)
≈ 0.4–2 ms. The Performance page refreshes at a user-configurable
1–300 s (default 5 s), so a full redraw per tick is well within budget —
blitting is only needed if sub-second chart updates are ever introduced.

## Rollout: the live charts

`python/charting.py` owns this decision for the GUI. The Performance
page's four live charts (ARC size, ARC hit rate, L2ARC traffic, SLOG
writes) are built through `charting.create_rolling_chart()`, which
returns a `MatplotlibRollingChart` when the probe succeeds and the Cairo
`RollingChart` (still in `memory_page.py`) otherwise. Both renderers
take the same constructor arguments and expose the same interface —
`widget` (the packed `Gtk.Widget`), `append(monotonic, values)`,
`set_reference(value, label)`, and `points` — and share one vocabulary
(sample window, series colours, nice-ceiling ladder, age labels), so
series semantics, the 300-sample window, Y scaling, legend text, and the
fixed-height/pack-without-expand sizing behaviour are identical either
way.

The matplotlib renderer updates the line/fill/legend artists in place on
every append and schedules `draw_idle()` on the canvas; tick positions
are fixed fractions of the window so only the label text slides as the
window advances. Verified end-to-end under real GTK with
`spikes/live_charts_smoke_matplotlib.py` (run like the first spike,
headless under `NO_AT_BRIDGE=1 xvfb-run -a`): the factory selects
matplotlib, all four canvases render non-blank content, a mid-run window
resize re-renders, warm full redraws cost ≤ ~40 ms per chart at the
page's chart sizes (455–1220 px wide × 110 px tall) with ≤ ~16 ms of
artist updates per refresh tick, and a screenshot is written next to the
spike for visual review.

Probe-cost notes measured on the test VM: the first successful probe
costs a one-time ~0.7 s matplotlib import at page build (GUI pages are
built at window construction); a *failed* probe costs ~1 ms per retry
once matplotlib itself is cached, and the outcome is cached per module
binding. Hosts without matplotlib fail the import instantly and keep the
Cairo renderer.

## Rollout: the blocksize ladder

The Alignment view's blocksize-relationship visual (the log₂ ladder
relating device physical sector, pool ashift block, dataset
recordsize/volblocksize, and VM guest sector) uses the same decision:
`charting.create_blocksize_ladder()` returns a
`MatplotlibBlocksizeLadder` on the GTK3-Agg canvas, or the Cairo
`BlocksizeLadder` (`python/alignment_page.py`) when matplotlib is not
installed. Both render from one shared vocabulary — row geometry
(`ladder_pixel_height`), the horizontal-scrollbar floor
(`ladder_minimum_width`), the log2 axis bounds and power-of-two ticks
(`ladder_axis_range`, axis floor one power of two below the smallest
size so a floor-valued rung stays visible), state colours, and the
empty-height constant — so the fallback degrades in quality only, never
in meaning. The ladder's data comes from the pure layer
(`alignment_analysis.blocksize_ladder`), so per-source degrade matches
the tables beside it.

The matplotlib ladder rebuilds its axes on every Alignment-view refresh
(a warm full redraw, within the budget above at the page's 1–300 s
cadence) and re-requests the widget height from the shared row geometry
only when the row set changes — a refresh with the same pools and rungs
re-draws at the same height, preserving the page's scroll stability.
The embed, refresh path, and both renderers' output were verified in
one realized window by `spikes/blocksize_ladder_spike.py` (run like the
first spike, headless under `NO_AT_BRIDGE=1 xvfb-run -a`): factory
selection, non-blank renders from identical data, and a screenshot
written next to the spike for visual review; the realized-window check
(`test_alignment_realized`) additionally drives the ladder through the
real page on both display paths.

## Theme palette and the ladder viewport

Both renderers take their colours from a shared palette resolved out of
`charting.py` rather than hardcoded values:

- `chart_palette(widget)` reads `theme_bg_color` / `theme_fg_color`
  through the widget's style context, so charts sit on the page's own
  background (dark-grey themes included) instead of white. Below a
  luminance of 0.5 the palette switches to its dark variant: brighter
  series colours, structural colours blended between foreground and
  background, and the ladder states re-mapped onto the bright series
  pair. Anything unresolvable (no theme colours, mocked GTK) degrades
  to `LIGHT_PALETTE` — the classic white-background vocabulary.
- The matplotlib renderers resolve once at build (canvas before
  artists, so artists are coloured correctly the first time), re-apply
  on `style-updated`, and repaint via `draw_idle`; the rolling chart
  rebuilds its legend on that path too, so the legend text's colour
  follows the new theme immediately rather than at the next data
  append. The Cairo renderers resolve per draw — a theme change simply
  repaints on the next tick.

The blocksize ladder instead has a **content-minimum width contract**:
the canvas requests exactly its content-derived minimum
(`ladder_minimum_width` — the longest row label's gutter plus a plot
floor plus the legend) and nothing wider; whenever the page is wider,
the viewport stretches the canvas to the full page width, so the
request is a floor, not a target. The scrolled window keeps a small
`min_content_width` (the canvas's width request must not pin the page
wide) and its `max_content_width` is floored — by
`alignment_page._floor_ladder_scroll_width`, from both the view box's
`size-allocate` handler and the refresh apply path — at the wider of
the granted page width and that same content minimum. The floor is the
load-bearing half: a `max_content_width` below the child's requested
minimum makes GTK clamp the canvas to the window and silently drop the
horizontal scrollbar (reproduced under Xvfb at mid window widths with
an earlier half-page cap), so the ladder renders cut off with no way to
scroll. The ladder's text also sits one notch above the rolling charts'
sizes (title 11.5, row labels 11, ticks and legend 10.5 in matplotlib;
13 px in the Cairo fallback), and the width estimate's per-character
constant follows that scale (`LADDER_CHAR_WIDTH_PX`). Every chart's text
— both renderers, rolling charts and ladder alike — scales with the GUI
base font size (`chart_font_scale`: the widget's style-context font over
a 10 pt reference, re-resolved on `style-updated` like the palette,
degrading to the tuned sizes when nothing resolves), so a theme with a
larger or smaller base font rescales the charts with the page around
them, and the ladder's width floor widens with its labels.

## Dependencies and deployment

| Host | Package | How |
|------|---------|-----|
| Test VM (development) | matplotlib 3.11.2 (+ numpy) | `pip3 install --user --break-system-packages matplotlib` |
| Production (Debian 13 trixie) | `python3-matplotlib` 3.10.1 | `sudo apt install python3-matplotlib` |

Production feasibility was checked read-only on the storage node
(Debian 13.6, Python 3.13.5): `python3-matplotlib` is not installed but
is an available candidate in `trixie/main`, so the user installs one apt
package; `python3-gi` is already a runtime prerequisite. Code must stick
to APIs stable across matplotlib 3.10/3.11 (`Figure`,
`FigureCanvasGTK3Agg`, artist `set_data`/`draw_artist`, `blit`).

The dependency is **optional at runtime**: if the import fails the page
must show its note and render with the Cairo fallback rather than break.
See also `python/Prerequisites.md` (Optional Components).
