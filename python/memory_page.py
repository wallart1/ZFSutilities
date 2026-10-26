"""Performance tab — live memory-tier charts and the Alignment view.

Two views share this page behind a radio switcher. "Live Charts" is the
original monitor: sizes, rates, and hit ratios from
/proc/spl/kstat/zfs counters plus per-device data from interval-mode
``zpool iostat -v`` (rates over a 1-second window measured at each
refresh), refreshed on a user-configurable interval while the tab is
visible.  Rolling time-series charts render through the shared charting
module: matplotlib (``FigureCanvasGTK3Agg``) when the optional package is
installed, with the Cairo ``RollingChart`` below as the fallback renderer
so the page also works without it (see python/Prerequisites.md and the
GUI-charting developer note).  "Alignment" (built
in alignment_page) shows blocksize alignment across device, pool,
dataset, and VM layers with tuning advice from observed workloads and
the user survey.  The shared refresh timer refreshes whichever view is
visible.

Data-source availability follows the model in memory_stats and
alignment_stats: each source degrades on its own with an explanatory
note, and absent kstat fields render as "—".  The charts view also shows
live per-enclosure read/write rates against the configured caps (the
Enclosures section), fed by the iostat data-section leaf rows and the
same enclosure discovery the Disks tab uses.
"""

import threading
from collections import deque

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from alignment_page import create_alignment_view, refresh_alignment_view
from charting import (  # chart vocabulary shared with the matplotlib renderer
    CHART_MAX_SAMPLES,
    chart_font_scale,
    chart_palette,
    create_rolling_chart,
    format_age,
    nice_ceiling,
    renderer_label,
)
from config_core import (
    get_memory_config,
    get_ui_state,
    save_memory_config,
    save_ui_state,
)
from disk_repository import format_bytes
from disks_page import enclosure_display_name
from feature_config import get_enclosures_config
from gi.repository import GLib, Gtk, Pango
from gui_helpers import (
    capped_treeview_scroll,
    configure_treeview_column,
    note_label,
    reconcile_rows,
    section_header,
    set_text_if_changed,
    show_note,
)
from memory_stats import (
    collect_memory_sample,
    compute_rates,
    cumulative_hit_rate,
    format_count,
    format_per_second,
    format_percent,
    format_rate,
    rollup_enclosure_rates,
)
from zfs_repository import parse_rate_limit


class RollingChart:
    """Rolling time-series chart drawn with Cairo on a Gtk.DrawingArea.

    Fallback renderer (see charting.create_rolling_chart): used on hosts
    without the optional matplotlib package.  Holds up to *max_samples*
    points of one or two series and redraws via
    ``queue_draw()`` after every append.  Composition (rather than
    subclassing Gtk.DrawingArea) keeps the class usable under the test
    GTK mocks.  The Y axis auto-scales to a nice round ceiling; a static
    reference line (e.g. ARC c_max) can be overlaid.
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
        self.title = title
        self.series_names = list(series_names)
        self.percent = percent
        self.formatter = formatter
        self._points = deque(maxlen=max_samples)
        self._reference = None
        self._reference_label = ""
        self.widget = Gtk.DrawingArea()
        self.widget.set_size_request(-1, height)
        self.widget.connect("draw", self._on_draw)

    # -- data management ---------------------------------------------------

    def append(self, monotonic, values):
        """Add one sample; *values* matches the series count."""
        self._points.append((monotonic, tuple(values)))
        self.widget.queue_draw()

    def set_reference(self, value, label):
        """Overlay a horizontal reference line at *value* (None clears)."""
        self._reference = value
        self._reference_label = label
        self.widget.queue_draw()

    @property
    def points(self):
        """Snapshot of the rolling window as (monotonic, values) tuples."""
        return list(self._points)

    # -- drawing -----------------------------------------------------------

    def _on_draw(self, widget, cr):
        # Palette resolved per draw from the widget's style context: the
        # chart follows the GTK theme (dark themes get brighter series
        # colours), and a theme change repaints on the next draw.
        palette = chart_palette(widget)
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        cr.set_source_rgb(*palette.background)
        cr.paint()

        cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9 * chart_font_scale(widget))

        left, right, top, bottom = 58, 8, 18, 16
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)

        if len(self._points) < 2:
            cr.set_source_rgb(*palette.muted)
            cr.move_to(left + 8, top + plot_h // 2)
            cr.show_text(f"{self.title} — collecting data…")
            return

        # Y range: 0..ceiling over all series values and the reference line.
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

        def _x(t):
            return left + (t - t_first) / t_span * plot_w

        def _y(v):
            if v is None:
                return None
            return top + plot_h - (v / y_max) * plot_h

        # Grid lines with Y labels.
        cr.set_source_rgb(*palette.grid)
        for i in range(5):
            value = y_max * i / 4
            y = _y(value)
            cr.move_to(left, y)
            cr.line_to(left + plot_w, y)
            cr.stroke()
            label = f"{value:.0f}%" if self.percent else self.formatter(value)
            cr.set_source_rgb(*palette.muted)
            cr.move_to(2, y + 3)
            cr.show_text(label)
            cr.set_source_rgb(*palette.grid)

        # X-axis age labels at both ends (draws happen right after appends,
        # so the newest point is effectively "now").
        cr.set_source_rgb(*palette.muted)
        cr.move_to(left, height - 4)
        cr.show_text(f"-{format_age(t_span)}")
        cr.move_to(left + plot_w - 24, height - 4)
        cr.show_text("now")

        # Reference line (dashed).
        if self._reference is not None:
            y = _y(self._reference)
            cr.set_source_rgb(*palette.reference)
            cr.set_dash([4, 4])
            cr.move_to(left, y)
            cr.line_to(left + plot_w, y)
            cr.stroke()
            cr.set_dash([])
            if self._reference_label:
                cr.move_to(left + 4, y - 3)
                cr.show_text(self._reference_label)
                cr.set_source_rgb(*palette.muted)

        # Series polylines with translucent fills.
        for index in range(len(self.series_names)):
            color = palette.series[index % len(palette.series)]
            points = [(_x(t), _y(values[index])) for t, values in self._points]
            points = [(x, y) for x, y in points if y is not None]
            if len(points) < 2:
                continue
            cr.set_source_rgba(color[0], color[1], color[2], 0.15)
            cr.move_to(points[0][0], top + plot_h)
            for x, y in points:
                cr.line_to(x, y)
            cr.line_to(points[-1][0], top + plot_h)
            cr.close_path()
            cr.fill()
            cr.set_source_rgb(*color)
            cr.set_line_width(1.5)
            cr.move_to(*points[0])
            for x, y in points[1:]:
                cr.line_to(x, y)
            cr.stroke()

        # Legend with the newest value of each series.
        x = left + 4
        for index, name in enumerate(self.series_names):
            color = palette.series[index % len(palette.series)]
            latest = self._points[-1][1][index]
            if self.percent:
                text = f"{name} {format_percent(latest)}"
            else:
                text = f"{name} {self.formatter(latest) if latest is not None else '—'}"
            cr.set_source_rgb(*color)
            cr.rectangle(x, 4, 8, 8)
            cr.fill()
            cr.set_source_rgb(*palette.foreground)
            cr.move_to(x + 11, 12)
            cr.show_text(text)
            x += 22 + 7 * len(text)


# ---------------------------------------------------------------------------
# Page construction
# ---------------------------------------------------------------------------


def _value_row(grid, row, caption):
    """Add a caption/value row to a Gtk.Grid; return the value label.

    The caption ellipsizes so a long caption never pins the grid's (and
    with it the page's) minimum width in narrow windows.
    """
    caption_label = Gtk.Label(label=caption)
    caption_label.set_halign(Gtk.Align.START)
    caption_label.set_ellipsize(Pango.EllipsizeMode.END)
    grid.attach(caption_label, 0, row, 1, 1)
    value = Gtk.Label(label="—")
    value.set_halign(Gtk.Align.START)
    grid.attach(value, 1, row, 1, 1)
    return value


def _device_table(app, store_attr, columns, state_key, expand_index=None):
    """Build a vdev TreeView in its own capped scrolled window.

    *columns* are ``(title, width)`` pairs; *expand_index* names the one
    non-last column that absorbs width slack so the far-right column
    keeps an honest fixed width (GTK otherwise re-expands the last
    column, which makes shrinking it look ineffective). The window shows
    at most 20 rows and carries its own vertical and horizontal
    scrollbars (see ``gui_helpers.capped_treeview_scroll``). The view is
    bound to the UI-state persistence layer so column widths survive GUI
    restarts, like every other table.
    """
    store = Gtk.ListStore(*([str] * len(columns)))
    view = Gtk.TreeView(model=store)
    view.set_headers_visible(True)
    for index, (title, width) in enumerate(columns):
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title, renderer, text=index)
        configure_treeview_column(col, width=width, min_width=60)
        if index == expand_index:
            col.set_expand(True)
        view.append_column(col)
    setattr(app, store_attr, store)
    app._ui_state.bind_treeview(view, state_key)
    view.set_size_request(-1, 60)
    return capped_treeview_scroll(view), store


# The two named children of the Performance page's view stack.
_MEMORY_VIEWS = ("charts", "alignment")


def _current_memory_view(app):
    """Return the name of the Performance view radio that is active."""
    radios = getattr(app, "_memory_view_radios", {})
    for name in _MEMORY_VIEWS:
        radio = radios.get(name)
        if radio is not None and radio.get_active():
            return name
    return "charts"


def _on_memory_view_radio_toggled(radio, app):
    """Switch the visible Performance view and persist the selection."""
    if not radio.get_active():
        return
    view = _current_memory_view(app)
    stack = getattr(app, "_memory_view_stack", None)
    if stack is not None:
        stack.set_visible_child_name(view)
    save_ui_state(app.config, {"performance_view": {"view": view}})


def _on_memory_view_stack_mapped(stack, app):
    """Re-point the stack at the active view radio once the stack is mapped.

    ``set_visible_child_name()`` on a stack that is not shown yet is
    dropped by GTK — the stack has no visible child at that point, and its
    own show handler falls back to the first child — so the view restored
    from the saved configuration at build time never takes effect.  The
    radios sit outside the stack and keep the authoritative selection, so
    every map re-asserts the visible child from the active radio (a no-op
    when the two already agree).
    """
    view = _current_memory_view(app)
    if stack.get_visible_child_name() != view:
        stack.set_visible_child_name(view)


def create_memory_page(app):
    """Build and return the Performance tab widget."""
    app._memory_timer = None
    app._memory_sample = None
    app._memory_refresh_pending = False
    app._alignment_refresh_pending = False

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    # Exposed so the Alignment refresh path can save/restore the vertical
    # offset around each apply (datasets-page idiom; see alignment_page).
    app.performance_scrolled = scrolled

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_margin_start(15)
    box.set_margin_end(15)
    box.set_margin_top(15)
    box.set_margin_bottom(15)
    scrolled.add(box)
    # The page viewport must size its content by NATURAL height.  The
    # page's tables each sit in their own capped scrolled window, whose
    # *minimum* is tiny (their min-content height); the default MINIMUM
    # policy would clamp the page box to the window height and the box
    # would then crush every table window toward that minimum — the
    # two-rows-per-table defect.
    viewport = scrolled.get_child()
    if hasattr(viewport, "set_vscroll_policy"):
        viewport.set_vscroll_policy(Gtk.ScrollablePolicy.NATURAL)

    # Title + refresh controls
    title = Gtk.Label()
    title.set_markup("<big><b>Performance</b></big>")
    title.set_halign(Gtk.Align.START)
    box.pack_start(title, False, False, 0)

    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    controls.set_halign(Gtk.Align.START)
    controls.pack_start(Gtk.Label(label="Refresh every (s):"), False, False, 0)
    memory_cfg = get_memory_config(app.config)
    app._memory_ref_spin = Gtk.SpinButton()
    app._memory_ref_spin.set_range(1, 300)
    app._memory_ref_spin.set_increments(1, 10)
    app._memory_ref_spin.set_value(memory_cfg.get("refresh_seconds", 5))
    app._memory_ref_spin.connect("value-changed", _on_memory_refresh_changed, app)
    controls.pack_start(app._memory_ref_spin, False, False, 0)
    app.memory_refreshing_label = Gtk.Label(label="Refreshing")
    app.memory_refreshing_label.set_no_show_all(True)
    app.memory_refreshing_label.hide()
    controls.pack_start(app.memory_refreshing_label, False, False, 0)
    box.pack_start(controls, False, False, 0)

    # --- View switcher: Live Charts / Blocksize Alignment ---
    view_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    charts_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Live Charts")
    alignment_radio = Gtk.RadioButton.new_with_label_from_widget(
        charts_radio, "Blocksize Alignment"
    )
    app._memory_view_radios = {"charts": charts_radio, "alignment": alignment_radio}
    for radio in (charts_radio, alignment_radio):
        radio.connect("toggled", _on_memory_view_radio_toggled, app)
        view_row.pack_start(radio, False, False, 0)
    box.pack_start(view_row, False, False, 0)

    charts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    app._memory_view_stack = Gtk.Stack()
    app._memory_view_stack.add_named(charts_box, "charts")
    app._memory_view_stack.add_named(create_alignment_view(app), "alignment")
    box.pack_start(app._memory_view_stack, True, True, 0)

    saved_view = get_ui_state(app.config).get("performance_view", {}).get("view", "charts")
    if saved_view not in _MEMORY_VIEWS:
        saved_view = "charts"
    app._memory_view_radios[saved_view].set_active(True)
    app._memory_view_stack.set_visible_child_name(saved_view)
    # The build-time restore above is dropped by GTK while the stack is
    # not shown (see _on_memory_view_stack_mapped), and this page is built
    # at window construction but only mapped when the sidebar selects it —
    # so the view is re-asserted at map time.
    app._memory_view_stack.connect("map", _on_memory_view_stack_mapped, app)

    # --- ARC section ---
    version_note = ""
    caps = getattr(app.ctx, "zfs_caps", None)
    if caps is not None and caps.version is not None:
        kmod = caps.version.kmod
        version_note = f"OpenZFS kernel module {kmod[0]}.{kmod[1]}.{kmod[2]}"
    # The renderer note makes the matplotlib/Cairo choice visible at a
    # glance instead of guessable only from chart smoothness — the common
    # cause of "Cairo charts despite an installed matplotlib" is the GUI
    # running as root while the package sits in a user's pip --user site.
    version_note = " · ".join(
        part for part in (version_note, f"charts: {renderer_label()}") if part
    )
    charts_box.pack_start(
        section_header("ARC — Adaptive Replacement Cache", version_note), False, False, 0
    )

    app._memory_arc_note = note_label()
    charts_box.pack_start(app._memory_arc_note, False, False, 0)

    arc_grid = Gtk.Grid()
    arc_grid.set_column_spacing(24)
    arc_grid.set_row_spacing(4)
    arc_labels = {}
    for row, caption in enumerate(
        [
            "Size",
            "Target (c)",
            "Data / Metadata / Header",
            "Hits/s",
            "Misses/s",
            "Hit rate (interval)",
            "Hit rate (since boot)",
            "Memory throttles",
        ]
    ):
        arc_labels[caption] = _value_row(arc_grid, row, caption)
    app._memory_arc_labels = arc_labels
    charts_box.pack_start(arc_grid, False, False, 0)

    app._memory_arc_size_chart = create_rolling_chart("ARC size", ["size"])
    app._memory_arc_rate_chart = create_rolling_chart(
        "ARC hit rate", ["hit rate"], percent=True, formatter=lambda v: f"{v:.0f}"
    )
    # Chart sizing lives here in the pack layer, not in the drawing code:
    # every chart fills the page width but is packed without vertical
    # expand, so it keeps its designed height (the rolling-chart height
    # request, set by either renderer) no matter how tall the window is —
    # extra vertical space goes to the view stack instead of stretching
    # the charts.
    charts_arc = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    charts_arc.pack_start(app._memory_arc_size_chart.widget, True, True, 0)
    charts_arc.pack_start(app._memory_arc_rate_chart.widget, True, True, 0)
    charts_box.pack_start(charts_arc, False, False, 0)

    # --- L2ARC section ---
    charts_box.pack_start(section_header("L2ARC — Cache Devices"), False, False, 0)

    app._memory_l2_note = note_label()
    charts_box.pack_start(app._memory_l2_note, False, False, 0)

    l2_grid = Gtk.Grid()
    l2_grid.set_column_spacing(24)
    l2_grid.set_row_spacing(4)
    l2_labels = {}
    for row, caption in enumerate(
        [
            "Size",
            "Compressed size (asize)",
            "Read rate",
            "Feed (write) rate",
            "Hit rate (interval)",
            "Hit rate (since boot)",
            "Feeds",
        ]
    ):
        l2_labels[caption] = _value_row(l2_grid, row, caption)
    app._memory_l2_labels = l2_labels
    charts_box.pack_start(l2_grid, False, False, 0)

    app._memory_l2_chart = create_rolling_chart("L2ARC traffic", ["read", "write"])
    charts_box.pack_start(app._memory_l2_chart.widget, False, False, 0)

    l2_scroll, _l2_store = _device_table(
        app,
        "_memory_l2_store",
        [
            ("Pool", 100),
            ("Vdev", 200),
            ("Capacity (alloc/free)", 220),
            ("Read rate", 110),
            ("Write rate", 110),
        ],
        "memory_l2_view",
        expand_index=1,
    )
    charts_box.pack_start(l2_scroll, False, False, 0)

    # --- SLOG section ---
    charts_box.pack_start(section_header("SLOG — Log Devices (ZIL)"), False, False, 0)

    app._memory_slog_note = note_label()
    charts_box.pack_start(app._memory_slog_note, False, False, 0)

    slog_grid = Gtk.Grid()
    slog_grid.set_column_spacing(24)
    slog_grid.set_row_spacing(4)
    slog_labels = {}
    for row, caption in enumerate(
        [
            "Write rate",
            "Writes/s",
            "Commits/s",
        ]
    ):
        slog_labels[caption] = _value_row(slog_grid, row, caption)
    app._memory_slog_labels = slog_labels
    charts_box.pack_start(slog_grid, False, False, 0)

    app._memory_slog_chart = create_rolling_chart("SLOG writes", ["write"])
    charts_box.pack_start(app._memory_slog_chart.widget, False, False, 0)

    slog_scroll, _slog_store = _device_table(
        app,
        "_memory_slog_store",
        [
            ("Pool", 100),
            ("Vdev", 200),
            ("Capacity (alloc/free)", 220),
            ("Writes/s", 100),
            ("Write rate", 110),
        ],
        "memory_slog_view",
        expand_index=1,
    )
    charts_box.pack_start(slog_scroll, False, False, 0)

    # --- Enclosures section ---
    # Live per-enclosure rates against the configured caps, and the only
    # place kernel-driven enclosure I/O (scrubs, resilvers) is visible:
    # the caps govern paced transfers, not kernel I/O (see the Disks tab's
    # Enclosures pane to set them).
    charts_box.pack_start(
        section_header(
            "Enclosures — USB/eSATA Traffic",
            "read/write rates across member disks; caps govern paced transfers only",
        ),
        False,
        False,
        0,
    )

    app._memory_enclosures_note = note_label()
    charts_box.pack_start(app._memory_enclosures_note, False, False, 0)

    enclosures_scroll, _enclosures_store = _device_table(
        app,
        "_memory_enclosures_store",
        [
            ("Enclosure", 180),
            ("Pools", 130),
            ("Read", 100),
            ("Write", 100),
            ("Cap", 90),
            ("% of cap", 80),
        ],
        "memory_enclosures_view",
        expand_index=0,
    )
    charts_box.pack_start(enclosures_scroll, False, False, 0)

    # The enclosure chart's series names are fixed at construction (one
    # read/write pair per enclosure), so the chart lives in its own box and
    # is rebuilt whenever the discovered enclosure set changes.
    app._memory_enclosures_chart = None
    app._memory_enclosures_chart_key = None
    app._memory_enclosures_chart_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    charts_box.pack_start(app._memory_enclosures_chart_box, False, False, 0)

    return scrolled


def _on_memory_refresh_changed(spin, app):
    """Persist the new refresh interval and restart the timer."""
    value = int(spin.get_value())
    memory_cfg = get_memory_config(app.config)
    if memory_cfg.get("refresh_seconds") != value:
        memory_cfg["refresh_seconds"] = value
        save_memory_config(app.config, memory_cfg)
        if hasattr(app, "_start_stop_memory_timer"):
            app._start_stop_memory_timer("memory")


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def _show_memory_refreshing(app):
    """Show the 'Refreshing' indicator next to the refresh interval spinner."""
    if hasattr(app, "memory_refreshing_label"):
        app.memory_refreshing_label.show()


def _hide_memory_refreshing(app):
    """Hide the 'Refreshing' indicator after the refresh completes."""
    if hasattr(app, "memory_refreshing_label"):
        app.memory_refreshing_label.hide()


def refresh_memory_page(app):
    """Refresh whichever Performance view is visible, off-thread."""
    if _current_memory_view(app) == "alignment":
        refresh_alignment_view(app)
        return

    if getattr(app, "_memory_refresh_pending", False):
        return
    app._memory_refresh_pending = True
    _show_memory_refreshing(app)

    def _collect():
        sample = collect_memory_sample()
        GLib.idle_add(_finish_refresh, app, sample)

    def _finish_refresh(_app, sample):
        _app._memory_refresh_pending = False
        _apply_memory_sample(_app, sample)
        _hide_memory_refreshing(_app)
        return False

    threading.Thread(target=_collect, daemon=True).start()


def _apply_memory_sample(app, sample):
    """Synchronously apply one sample to the page widgets."""
    rates = compute_rates(app._memory_sample, sample)
    app._memory_sample = sample
    arc = sample.arc

    # --- ARC ---
    if sample.arcstats_available:
        app._memory_arc_note.hide()
        labels = app._memory_arc_labels
        size = arc.get("size")
        c_max = arc.get("c_max")
        if size is not None and c_max:
            pct = 100.0 * size / c_max
            set_text_if_changed(
                labels["Size"],
                f"{format_bytes(size)} ({pct:.1f}% of max {format_bytes(c_max)})",
            )
        else:
            set_text_if_changed(labels["Size"], format_bytes(size))
        set_text_if_changed(labels["Target (c)"], format_bytes(arc.get("c")))
        breakdown = " / ".join(
            format_bytes(arc.get(k)) for k in ("data_size", "metadata_size", "hdr_size")
        )
        set_text_if_changed(labels["Data / Metadata / Header"], breakdown)
        set_text_if_changed(labels["Hits/s"], format_per_second(rates.arc_hits_ps))
        set_text_if_changed(labels["Misses/s"], format_per_second(rates.arc_misses_ps))
        set_text_if_changed(labels["Hit rate (interval)"], format_percent(rates.arc_hit_rate))
        set_text_if_changed(
            labels["Hit rate (since boot)"],
            format_percent(cumulative_hit_rate(arc.get("hits"), arc.get("misses"))),
        )
        set_text_if_changed(
            labels["Memory throttles"], format_count(arc.get("memory_throttle_count"))
        )

        app._memory_arc_size_chart.set_reference(
            c_max, f"c_max {format_bytes(c_max)}" if c_max else ""
        )
        app._memory_arc_size_chart.append(sample.monotonic, [size if size is not None else 0])
        interval_rate = rates.arc_hit_rate
        if interval_rate is not None:
            app._memory_arc_rate_chart.append(sample.monotonic, [interval_rate])
    else:
        show_note(
            app._memory_arc_note,
            "ARC kstats are not available on this host "
            "(/proc/spl/kstat/zfs/arcstats is not readable).",
        )

    # --- L2ARC ---
    cache_vdevs = [v for v in sample.vdevs if v.section == "cache"]
    if not sample.iostat_available:
        show_note(
            app._memory_l2_note,
            "Cache-device data unavailable: `zpool iostat -v` failed; "
            "L2ARC counters below are still live when exposed.",
        )
    elif not cache_vdevs:
        show_note(app._memory_l2_note, "No cache vdevs (L2ARC) configured in any pool.")
    else:
        app._memory_l2_note.hide()
    if sample.arcstats_available:
        labels = app._memory_l2_labels
        set_text_if_changed(labels["Size"], format_bytes(arc.get("l2_size")))
        set_text_if_changed(labels["Compressed size (asize)"], format_bytes(arc.get("l2_asize")))
        set_text_if_changed(labels["Read rate"], format_rate(rates.l2_read_bps))
        set_text_if_changed(labels["Feed (write) rate"], format_rate(rates.l2_write_bps))
        set_text_if_changed(labels["Hit rate (interval)"], format_percent(rates.l2_hit_rate))
        set_text_if_changed(
            labels["Hit rate (since boot)"],
            format_percent(cumulative_hit_rate(arc.get("l2_hits"), arc.get("l2_misses"))),
        )
        set_text_if_changed(labels["Feeds"], format_count(arc.get("l2_feeds")))
        app._memory_l2_chart.append(
            sample.monotonic,
            [
                rates.l2_read_bps if rates.l2_read_bps is not None else 0,
                rates.l2_write_bps if rates.l2_write_bps is not None else 0,
            ],
        )

    l2_rows = {}
    for vdev in cache_vdevs:
        vr = rates.vdevs.get((vdev.pool, vdev.vdev))
        capacity = (
            f"{format_bytes(vdev.alloc)} / {format_bytes(vdev.free)}"
            if vdev.alloc is not None and vdev.free is not None
            else "—"
        )
        l2_rows[(vdev.pool, vdev.vdev)] = [
            vdev.pool,
            vdev.vdev,
            capacity,
            format_rate(vr.read_bps if vr else None),
            format_rate(vr.write_bps if vr else None),
        ]
    reconcile_rows(app._memory_l2_store, l2_rows)

    # --- SLOG ---
    log_vdevs = [v for v in sample.vdevs if v.section == "logs"]
    if not sample.iostat_available:
        show_note(
            app._memory_slog_note,
            "Log-device data unavailable: `zpool iostat -v` failed; "
            "ZIL counters below are still live when exposed.",
        )
    elif not log_vdevs:
        show_note(app._memory_slog_note, "No log vdevs (SLOG) configured in any pool.")
    elif not sample.zil_available:
        show_note(
            app._memory_slog_note,
            "ZIL kstats are not exposed by this host; the device table below is still live.",
        )
    else:
        app._memory_slog_note.hide()
    if sample.zil_available:
        labels = app._memory_slog_labels
        set_text_if_changed(labels["Write rate"], format_rate(rates.slog_write_bps))
        set_text_if_changed(labels["Writes/s"], format_per_second(rates.slog_writes_ps))
        set_text_if_changed(labels["Commits/s"], format_per_second(rates.slog_commits_ps))
        app._memory_slog_chart.append(
            sample.monotonic,
            [rates.slog_write_bps if rates.slog_write_bps is not None else 0],
        )

    slog_rows = {}
    for vdev in log_vdevs:
        vr = rates.vdevs.get((vdev.pool, vdev.vdev))
        capacity = (
            f"{format_bytes(vdev.alloc)} / {format_bytes(vdev.free)}"
            if vdev.alloc is not None and vdev.free is not None
            else "—"
        )
        slog_rows[(vdev.pool, vdev.vdev)] = [
            vdev.pool,
            vdev.vdev,
            capacity,
            format_per_second(vr.writes_ps if vr else None),
            format_rate(vr.write_bps if vr else None),
        ]
    reconcile_rows(app._memory_slog_store, slog_rows)

    # --- Enclosures ---
    _apply_enclosure_sample(app, sample)


# ---------------------------------------------------------------------------
# Enclosures: live per-enclosure rates against the configured caps
# ---------------------------------------------------------------------------


def _enclosure_membership(data):
    """Map iostat leaf vdev names to enclosure ids from inventory data.

    Discovery members are whole-disk kernel names; the inventory rows add
    partition names and by-id basenames, so every leaf spelling
    ``zpool iostat -v`` prints for an enclosure disk — kernel or by-id,
    whole disk or partition — maps to its enclosure.
    """
    membership = {}
    for enclosure in data.enclosures:
        for member in enclosure.members:
            membership[member] = enclosure.id
    for disk in data.disks:
        if disk.enclosure_id:
            membership[disk.name] = disk.enclosure_id
            if disk.by_id:
                membership[disk.by_id] = disk.enclosure_id
    return membership


def _enclosure_inventory_data(app):
    """Return the shared Disks-page inventory snapshot, or None.

    The cache never blocks: a stale hit returns immediately and refreshes
    in its own daemon thread, which then invokes the callback so the
    enclosure table reconciles as soon as the fresh inventory lands —
    without waiting for the next Performance refresh tick.
    """
    cache = getattr(app, "_disks_inventory_cache", None)
    if cache is None:
        return None

    def _loaded():
        GLib.idle_add(_reconcile_enclosures_after_inventory, app)

    data = cache.get(callback=_loaded)
    if not isinstance(getattr(data, "enclosures", None), list) or not isinstance(
        getattr(data, "disks", None), list
    ):
        # A cache that answers anything but a DiskInventoryData (tests
        # embed mock caches) simply has nothing to show yet.
        return None
    return data


def _reconcile_enclosures_after_inventory(app):
    """Reconcile the enclosure table once a background inventory load lands."""
    if _current_memory_view(app) != "charts":
        return False
    sample = getattr(app, "_memory_sample", None)
    if sample is not None:
        _apply_enclosure_sample(app, sample, charts=False)
    return False


def _ensure_enclosure_chart(app, series):
    """Return the enclosure chart, rebuilt when the enclosure set changes.

    *series* is the ordered ``(id, display name)`` list the chart should
    show; it doubles as the rebuild key, so a renamed enclosure rebuilds
    the legend too.  A rebuild discards the rolling history — the old
    chart's series no longer describe the enclosures present.
    """
    box = app._memory_enclosures_chart_box
    key = tuple(series)
    chart = app._memory_enclosures_chart
    if chart is not None and app._memory_enclosures_chart_key == key:
        return chart
    if chart is not None:
        box.remove(chart.widget)
    names = [f"{name} {way}" for _id, name in series for way in ("read", "write")]
    chart = create_rolling_chart("Enclosure traffic", names) if names else None
    if chart is not None:
        box.pack_start(chart.widget, False, False, 0)
    app._memory_enclosures_chart = chart
    app._memory_enclosures_chart_key = key
    return chart


def _apply_enclosure_sample(app, sample, charts=True):
    """Refresh the Enclosures table (and rolling chart) from one sample."""
    data = _enclosure_inventory_data(app)
    rows = {}
    series = []
    values = []
    if data is not None and data.enclosures:
        entries = get_enclosures_config(app.config)
        totals = rollup_enclosure_rates(sample.vdevs, _enclosure_membership(data))
        for enclosure in data.enclosures:
            entry = entries.get(enclosure.id) or {}
            name = enclosure_display_name(enclosure, entry.get("name", ""))
            rates = totals.get(enclosure.id)
            cap = parse_rate_limit(entry.get("max_rate", ""))
            if rates is not None and cap:
                # A paced stream loads one direction at a time, so the
                # busier direction is the one a cap can bite on.
                busy = max(rates.read_bps, rates.write_bps)
                percent = format_percent(100.0 * busy / cap)
            else:
                percent = "—"
            rows[(enclosure.id, name)] = [
                name,
                ", ".join(enclosure.pools),
                format_rate(rates.read_bps if rates is not None else None),
                format_rate(rates.write_bps if rates is not None else None),
                entry.get("max_rate", "") or "unlimited",
                percent,
            ]
            series.append((enclosure.id, name))
            values.extend(
                [
                    rates.read_bps if rates is not None else None,
                    rates.write_bps if rates is not None else None,
                ]
            )

    if not sample.iostat_available:
        show_note(
            app._memory_enclosures_note,
            "Enclosure rates unavailable: `zpool iostat -v` failed.",
        )
    elif data is None or not data.enclosures:
        show_note(
            app._memory_enclosures_note,
            "No multi-bay USB/eSATA enclosures discovered "
            "(enclosures are listed and named on the Disks tab).",
        )
    else:
        app._memory_enclosures_note.hide()

    reconcile_rows(app._memory_enclosures_store, rows)
    if charts and series:
        _ensure_enclosure_chart(app, series).append(sample.monotonic, values)
