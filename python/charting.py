"""Chart renderers for the GTK3 GUI — matplotlib with a Cairo fallback.

Implements the GUI charting decision recorded in
docs/docs/developer-guide/charting.md (Task 2.3 spike): charts render at
high quality through matplotlib embedded via ``FigureCanvasGTK3Agg``, and
the Cairo-drawn ``RollingChart`` in memory_page stays in the tree as the
fallback renderer for hosts without the optional package.
``create_rolling_chart()`` picks the renderer once per process.

Rules the spike established, enforced by this module:

* matplotlib is imported lazily at chart-construction time, never at
  module level.  The test suites import this module under the
  ``mock_gtk()`` fake, where the real GTK3 backend cannot load (its
  ``Gtk.Widget`` base classes are MagicMocks), so the probe fails fast
  and the Cairo fallback is selected.
* ``Gdk`` is pinned to 3.0 before the backend import: on hosts that also
  have GTK4 installed, an unpinned ``Gdk`` resolves to 4.0 and GTK3
  cannot load afterwards.
* The probe outcome is cached for the lifetime of this module binding;
  ``mock_gtk(fresh=True)`` evicts and re-imports the module, which
  re-probes under the new binding (a repeated failed probe costs ~1 ms
  once matplotlib itself is cached).

The rolling-chart vocabulary shared by both renderers — sample window,
series colours, the nice-ceiling ladder, and age labels — lives here;
memory_page imports it for its Cairo fallback.

The same selection rule serves the Alignment view's blocksize ladder
(``create_blocksize_ladder`` / ``MatplotlibBlocksizeLadder``): the ladder's
row geometry, state colours, and log2 tick grammar are shared vocabulary
here too, so the Cairo fallback in alignment_page draws the same picture.
"""

from collections import deque
from types import SimpleNamespace

import gi

gi.require_version("Gtk", "3.0")

from disk_repository import format_blocksize, format_bytes
from memory_stats import format_percent

# Number of samples kept per rolling chart.  At the 5 s default refresh
# interval this is about 25 minutes of history; the window slides as
# samples age out.
CHART_MAX_SAMPLES = 300

# Chart series colours (RGB 0.0-1.0; matplotlib accepts the same tuples).
SERIES_COLORS = [
    (0.20, 0.40, 0.70),  # blue
    (0.96, 0.47, 0.00),  # orange
]
REFERENCE_COLOR = (0.60, 0.60, 0.60)

# Nice-round-ceiling ladder used for chart Y-axis scaling.
NICE_LADDER = (1, 2, 5)

# --- Blocksize-ladder vocabulary (shared by both ladder renderers) ---------
#
# The Alignment view's blocksize ladder draws one rung per layer size on a
# log2 axis with the pool's ashift block as a dashed reference line. Row
# geometry, the state colours, and the tick grammar are shared vocabulary so
# the matplotlib renderer and the Cairo fallback draw the same picture.

# Pixel height of one ladder row (header and rung rows share the grid; the
# header is emphasised by weight and separators, not extra height).
LADDER_ROW_HEIGHT = 19
# Margins: title + legend above the rows, X tick labels below them.
LADDER_MARGIN_TOP = 40
LADDER_MARGIN_BOTTOM = 26
# Height of the empty/unavailable placeholder (no rows to size against).
LADDER_EMPTY_HEIGHT = 70

# Rung states (alignment_analysis severity strings) to series colours: the
# blue/orange pair the rolling charts use, plus grey for advisory/unresolved.
LADDER_STATE_COLORS = {
    "OK": SERIES_COLORS[0],
    "WARN": SERIES_COLORS[1],
    "info": (0.58, 0.58, 0.58),
}
# Legend labels for the three states, in display order.
LADDER_LEGEND = (
    ("OK", "aligned"),
    ("WARN", "misaligned (padded or RMW)"),
    ("info", "advisory / unresolved"),
)


def nice_ceiling(value):
    """Return the smallest ladder value (1/2/5 x 10^k) >= *value*."""
    if value <= 0:
        return 1.0
    exponent = 0
    scaled = float(value)
    while scaled > 5:
        scaled /= 10.0
        exponent += 1
    for step in NICE_LADDER:
        if scaled <= step:
            return step * 10**exponent
    return 10 ** (exponent + 1)


def format_age(seconds):
    """Format a duration for chart X-axis labels (e.g. '4m 59s')."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def ladder_pixel_height(pools):
    """Return the ladder widget's pixel height for the given pool set.

    Works on any sequence carrying ``bars`` (LadderPool from
    alignment_analysis), so both renderers size their widgets identically:
    one grid row per pool header and per rung, framed by the shared
    margins. The height therefore changes only when the row set changes —
    a refresh with the same pools and rungs re-draws at the same height,
    which is what keeps the page steady.
    """
    rows = sum(1 + len(pool.bars) for pool in pools)
    return LADDER_MARGIN_TOP + rows * LADDER_ROW_HEIGHT + LADDER_MARGIN_BOTTOM


def _pow2_at_least(value):
    """Smallest power of two >= *value* (>= 1)."""
    return 1 << (value - 1).bit_length() if value > 1 else 1


def ladder_axis_range(pools):
    """Return the ladder's ``(x_min, x_max)`` byte bounds and tick sizes.

    Ticks sit on every power of two spanning the range (the ladder's log2
    grid), thinned to every other power when the range grows too wide for
    per-tick labels. The axis floor sits one power of two below the
    smallest size — on a log axis a rung that starts at the floor would
    draw zero-wide and a reference line on the floor would hide in the
    axis spine — and one power above the largest, so no rung or line
    touches the frame. Bars always start at ``x_min``, so every rung's
    length reads against the same baseline.
    """
    sizes = [bar.size for pool in pools for bar in pool.bars]
    sizes.extend(pool.block for pool in pools if pool.block is not None)
    if not sizes:
        return 256, 8192, (256, 512, 1024, 2048, 4096, 8192)
    smallest, largest = min(sizes), max(sizes)
    x_min = max(1, _pow2_at_least(smallest) // 2)
    x_max = _pow2_at_least(largest) * 2
    lo, hi = x_min.bit_length() - 1, x_max.bit_length() - 1
    step = 1 if hi - lo <= 12 else 2
    ticks = tuple(1 << exponent for exponent in range(lo, hi + 1, step))
    return x_min, x_max, ticks


# Sentinel distinguishing "not probed yet" from "probed and unavailable".
_UNPROBED = object()
_backend = _UNPROBED


def matplotlib_backend():
    """Return the matplotlib GTK3-Agg backend namespace, or None.

    The import is lazy (never at module level — see the module docstring)
    and its outcome cached for this module binding.  Any import-time
    failure — matplotlib not installed, the GTK3 backend unable to load —
    selects the Cairo fallback instead of breaking the page.
    """
    global _backend
    if _backend is not _UNPROBED:
        return _backend
    try:
        # Pin Gdk before the backend import (GTK4 co-installed hosts resolve
        # an unpinned Gdk to 4.0 and then Gtk 3.0 cannot load).
        gi.require_version("Gdk", "3.0")
        from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
        from matplotlib.figure import Figure
        from matplotlib.patches import Patch
        from matplotlib.ticker import FuncFormatter
    except Exception:
        _backend = None
        return None
    _backend = SimpleNamespace(
        Figure=Figure,
        FigureCanvas=FigureCanvasGTK3Agg,
        FuncFormatter=FuncFormatter,
        Patch=Patch,
    )
    return _backend


class MatplotlibRollingChart:
    """Rolling time-series chart rendered by matplotlib on a GTK3 Agg canvas.

    Interface-compatible with the Cairo ``RollingChart`` fallback in
    memory_page — ``widget`` (the packed Gtk.Widget), ``append``,
    ``set_reference``, and ``points`` — so callers treat both renderers
    alike.  Data lives in a deque exactly as in the fallback; every append
    updates the line/fill/legend artists in place and schedules an idle
    redraw of the canvas, so the per-refresh cost is one warm full render
    (well within budget at the page's 1-300 s refresh interval).
    """

    def __init__(
        self,
        title,
        series_names,
        max_samples=CHART_MAX_SAMPLES,
        percent=False,
        height=110,
        formatter=format_bytes,
    ):
        backend = matplotlib_backend()
        if backend is None:
            raise RuntimeError("matplotlib GTK3 backend is not available")
        self.title = title
        self.series_names = list(series_names)
        self.percent = percent
        self.formatter = formatter
        self._points = deque(maxlen=max_samples)
        self._reference = None
        self._reference_label = ""
        self._t_last = None
        self._ref_line = None
        self._ref_text = None
        self._laid_out = False

        fig = backend.Figure(figsize=(4.5, height / 100.0), dpi=100)
        fig.patch.set_facecolor("white")
        ax = fig.add_subplot(1, 1, 1)
        self._fig = fig
        self._ax = ax

        ax.set_facecolor("white")
        ax.set_title(title, fontsize=9, loc="left", color="#333333", pad=4)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#b8b8b8")
        ax.grid(axis="y", color="#dcdcdc", linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_autoscale_on(False)
        ax.tick_params(labelsize=7.5, colors="#444444", length=3)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.yaxis.set_major_formatter(backend.FuncFormatter(self._format_y))
        ax.xaxis.set_major_formatter(backend.FuncFormatter(self._format_x))

        self._collecting = ax.text(
            0.5,
            0.5,
            f"{title} — collecting data…",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=8.5,
            color="#737373",
        )
        self._lines = []
        self._fills = []
        for index in range(len(self.series_names)):
            color = SERIES_COLORS[index % len(SERIES_COLORS)]
            (fill,) = ax.fill([], [], color=color, alpha=0.15, linewidth=0, zorder=1)
            (line,) = ax.plot([], [], linewidth=1.6, color=color, zorder=2)
            self._fills.append(fill)
            self._lines.append(line)
        self._legend = self._make_legend(list(self.series_names))
        # One static layout at build time — never constrained_layout, which
        # re-solves on every draw and tripled the redraw cost in the spike.
        fig.tight_layout(pad=0.4)

        self.widget = backend.FigureCanvas(fig)
        self.widget.set_size_request(-1, height)

    # -- data management (same contract as the Cairo fallback) -------------

    def append(self, monotonic, values):
        """Add one sample; *values* matches the series count."""
        self._points.append((monotonic, tuple(values)))
        self._render()

    def set_reference(self, value, label):
        """Overlay a horizontal reference line at *value* (None clears)."""
        self._reference = value
        self._reference_label = label
        self._render()

    @property
    def points(self):
        """Snapshot of the rolling window as (monotonic, values) tuples."""
        return list(self._points)

    # -- rendering ----------------------------------------------------------

    def _make_legend(self, labels):
        """Build the in-axes legend (rebuilt per refresh; see _render)."""
        return self._ax.legend(
            self._lines,
            labels,
            loc="upper left",
            fontsize=8,
            frameon=False,
            handlelength=1.4,
            borderaxespad=0.2,
        )

    def _format_y(self, value, _position):
        """Y-axis tick label: percent form or the chart's value formatter."""
        if self.percent:
            return f"{value:.0f}%"
        return self.formatter(value)

    def _format_x(self, value, _position):
        """X-axis tick label as the age of *value* behind the newest point."""
        if self._t_last is None:
            return ""
        age = self._t_last - value
        if age < 1.0:
            return "now"
        return f"-{format_age(age)}"

    def _render(self):
        """Sync artists with the rolling window and schedule an idle redraw."""
        if len(self._points) < 2:
            self._collecting.set_visible(True)
            self.widget.draw_idle()
            return
        self._collecting.set_visible(False)

        # Y range: 0..ceiling over all series values and the reference line
        # (identical scaling to the Cairo fallback).
        peak = 0.0
        for _t, values in self._points:
            for value in values:
                if value is not None and value > peak:
                    peak = value
        if self._reference is not None:
            peak = max(peak, self._reference)
        if self.percent:
            y_max = 100.0
        else:
            y_max = nice_ceiling(peak * 1.05) if peak > 0 else 1.0
        y_max = max(y_max, 1e-9)

        t_first = self._points[0][0]
        t_last = self._points[-1][0]
        t_span = max(1e-9, t_last - t_first)
        self._t_last = t_last

        ax = self._ax
        ax.set_xlim(t_first, t_last)
        ax.set_ylim(0.0, y_max)
        ax.set_yticks([y_max * i / 4 for i in range(5)])
        # Tick positions are fixed fractions of the window, so only the
        # label text slides as the window advances; more ticks once the
        # window is wide enough for them to stay distinct.
        ticks = 5 if t_span >= 60 else (3 if t_span >= 12 else 2)
        ax.set_xticks([t_first + t_span * i / (ticks - 1) for i in range(ticks)])

        for index, line in enumerate(self._lines):
            # None values drop out of the polyline, as in the fallback.
            pts = [(t, values[index]) for t, values in self._points if values[index] is not None]
            line.set_data([p[0] for p in pts], [p[1] for p in pts])
            fill = self._fills[index]
            if len(pts) >= 2:
                fill.xy = [(pts[0][0], 0.0), *pts, (pts[-1][0], 0.0)]
                fill.set_visible(True)
            else:
                fill.set_visible(False)

        # Legend with the newest value of each series (same text as the
        # Cairo fallback).  Legends do not track label changes, so the
        # legend is rebuilt per refresh — cheap at one or two entries.
        latest = self._points[-1][1]
        labels = []
        for index, name in enumerate(self.series_names):
            value = latest[index]
            if self.percent:
                text = f"{name} {format_percent(value)}"
            else:
                text = f"{name} {self.formatter(value) if value is not None else '—'}"
            labels.append(text)
        self._legend.remove()
        self._legend = self._make_legend(labels)

        self._draw_reference()

        if not self._laid_out:
            # Final layout pass now that real tick labels exist (the build
            # pass ran against an empty axis).
            self._fig.tight_layout(pad=0.4)
            self._laid_out = True
        self.widget.draw_idle()

    def _draw_reference(self):
        """(Re)place the dashed reference line and its label, if any."""
        if self._ref_line is not None:
            self._ref_line.remove()
            self._ref_line = None
        if self._ref_text is not None:
            self._ref_text.remove()
            self._ref_text = None
        if self._reference is None:
            return
        self._ref_line = self._ax.axhline(
            self._reference,
            color=REFERENCE_COLOR,
            linestyle=(0, (4, 4)),
            linewidth=1.0,
            zorder=1.5,
        )
        if self._reference_label:
            self._ref_text = self._ax.annotate(
                self._reference_label,
                xy=(0.0, self._reference),
                xycoords=("axes fraction", "data"),
                xytext=(4, 3),
                textcoords="offset points",
                fontsize=7.5,
                color="#595959",
            )


class MatplotlibBlocksizeLadder:
    """Blocksize ladder rendered by matplotlib on a GTK3 Agg canvas.

    The Alignment view's blocksize-relationship visual (see
    ``alignment_analysis.blocksize_ladder`` for the data). One row per
    rung — device physical sectors, the pool's ashift block, dataset
    recordsize/volblocksize groups, VM guest sectors — drawn as bars on a
    log2 X axis, with a dashed reference line per pool at its ashift
    block; a rung that ends left of its pool's line sits below the pool
    block, and rung colour carries the verdict (see
    ``LADDER_STATE_COLORS``). ``update(pools)`` rebuilds the axes — the
    Alignment view refreshes at the page's 1-300 s cadence, where a warm
    full redraw is well within the budget measured in the charting spike
    — and re-requests the widget height from the shared row geometry, so
    the ladder grows and shrinks with its row set only.
    """

    def __init__(self, title="Blocksize ladder"):
        backend = matplotlib_backend()
        if backend is None:
            raise RuntimeError("matplotlib GTK3 backend is not available")
        self.title = title
        self._pools = []
        self._rows_rendered = None

        fig = backend.Figure(figsize=(4.5, 2.0), dpi=100)
        fig.patch.set_facecolor("white")
        self._fig = fig
        self._ax = fig.add_subplot(1, 1, 1)
        self._style_axes()
        self._placeholder = self._ax.text(
            0.5,
            0.5,
            f"{self.title} — waiting for pool data…",
            transform=self._ax.transAxes,
            ha="center",
            va="center",
            fontsize=8.5,
            color="#737373",
        )
        fig.tight_layout(pad=0.4)

        self.widget = backend.FigureCanvas(fig)
        self.widget.set_size_request(-1, LADDER_EMPTY_HEIGHT)

    # -- data management -----------------------------------------------------

    def update(self, pools, unavailable=False):
        """Replace the ladder's pool set and schedule an idle redraw."""
        self._pools = list(pools)
        self._render(unavailable)

    @property
    def pools(self):
        """Snapshot of the rendered pool set."""
        return list(self._pools)

    # -- rendering -----------------------------------------------------------

    def _style_axes(self):
        """Apply the base axis styling (re-applied after every ax.clear)."""
        ax = self._ax
        ax.set_facecolor("white")
        ax.set_title(self.title, fontsize=9, loc="left", color="#333333", pad=4)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#b8b8b8")
        ax.grid(axis="x", color="#dcdcdc", linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=7.5, colors="#444444", length=3)

    def _render(self, unavailable):
        """Redraw the whole ladder; schedule an idle canvas redraw."""
        backend = matplotlib_backend()
        ax = self._ax
        ax.clear()
        self._style_axes()
        if not self._pools:
            message = (
                f"{self.title} — pool and device data unavailable"
                if unavailable
                else f"{self.title} — no pools found"
            )
            self._placeholder = ax.text(
                0.5,
                0.5,
                message,
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=8.5,
                color="#737373",
            )
            self.widget.set_size_request(-1, LADDER_EMPTY_HEIGHT)
            self.widget.draw_idle()
            return

        x_min, x_max, ticks = ladder_axis_range(self._pools)
        labels = []
        positions = []
        bar_positions = []
        bar_widths = []
        bar_colors = []
        header_labels = set()
        for pool in self._pools:
            header_labels.add(pool.pool)
            header_index = len(labels)
            labels.append(pool.pool)
            positions.append(header_index)
            first_bar = len(labels)
            for bar in pool.bars:
                labels.append(bar.label)
                positions.append(len(labels) - 1)
                bar_positions.append(len(labels) - 1)
                bar_widths.append(bar.size - x_min)
                bar_colors.append(LADDER_STATE_COLORS.get(bar.state, LADDER_STATE_COLORS["info"]))
            # Separator directly under the header row; the dashed ashift
            # reference spans the header and every rung of its pool.
            ax.axhline(
                first_bar - 0.5,
                color="#dcdcdc",
                linewidth=0.8,
                zorder=1,
            )
            if pool.block is not None:
                ax.vlines(
                    pool.block,
                    header_index - 0.5,
                    len(labels) - 0.5,
                    color=REFERENCE_COLOR,
                    linestyle=(0, (4, 4)),
                    linewidth=1.1,
                    zorder=1.5,
                )

        ax.barh(
            bar_positions,
            bar_widths,
            left=x_min,
            height=0.62,
            color=bar_colors,
            edgecolor="none",
            zorder=2,
        )
        ax.set_yticks(positions)
        ax.set_yticklabels(labels, fontsize=8)
        for tick_label, label in zip(ax.get_yticklabels(), labels):
            if label in header_labels:
                tick_label.set_fontweight("bold")
        ax.invert_yaxis()
        ax.set_xscale("log", base=2)
        ax.set_xlim(x_min, x_max)
        ax.set_xticks(list(ticks))
        ax.set_xticklabels([format_blocksize(tick) for tick in ticks])
        ax.legend(
            handles=[
                backend.Patch(facecolor=LADDER_STATE_COLORS[state], label=text)
                for state, text in LADDER_LEGEND
            ],
            loc="lower right",
            fontsize=7.5,
            frameon=True,
            facecolor="white",
            framealpha=0.85,
            edgecolor="#dcdcdc",
            handlelength=1.2,
        )

        rows = len(labels)
        if rows != self._rows_rendered:
            # Labels enter and leave with rows, so the left margin needs a
            # fresh layout exactly when the row set changes — never per
            # refresh (constrained_layout stays banned; see the spike).
            self._fig.tight_layout(pad=0.4)
            self._rows_rendered = rows
            self.widget.set_size_request(-1, ladder_pixel_height(self._pools))
        self.widget.draw_idle()


def create_rolling_chart(
    title,
    series_names,
    max_samples=CHART_MAX_SAMPLES,
    percent=False,
    height=110,
    formatter=format_bytes,
):
    """Return a rolling chart using the best renderer available.

    matplotlib (``FigureCanvasGTK3Agg``) when the optional package is
    installed; otherwise the Cairo ``RollingChart`` from memory_page, so
    the GUI keeps working on hosts without it (see python/Prerequisites.md,
    Optional Components).  Both renderers expose the same interface.
    """
    if matplotlib_backend() is not None:
        return MatplotlibRollingChart(
            title,
            series_names,
            max_samples=max_samples,
            percent=percent,
            height=height,
            formatter=formatter,
        )
    # Imported here (not at module level) to keep the dependency one-way:
    # memory_page imports this module; the fallback renderer lives there.
    from memory_page import RollingChart

    return RollingChart(
        title,
        series_names,
        max_samples=max_samples,
        percent=percent,
        height=height,
        formatter=formatter,
    )


def create_blocksize_ladder(title="Blocksize ladder"):
    """Return a blocksize ladder using the best renderer available.

    Same selection rule as :func:`create_rolling_chart`: a
    ``MatplotlibBlocksizeLadder`` on the GTK3-Agg canvas when the optional
    package is installed, otherwise the Cairo ``BlocksizeLadder`` from
    alignment_page (imported here, not at module level, so the dependency
    stays one-way — alignment_page imports this module; the fallback
    renderer lives there). Both renderers expose the same interface:
    ``widget`` (the packed Gtk.Widget), ``update(pools, unavailable=False)``,
    and ``pools``.
    """
    if matplotlib_backend() is not None:
        return MatplotlibBlocksizeLadder(title)
    from alignment_page import BlocksizeLadder

    return BlocksizeLadder(title)
