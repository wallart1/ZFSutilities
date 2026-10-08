"""Performance tab — live memory-tier charts and the Alignment view.

Two views share this page behind a radio switcher. "Live Charts" is the
original monitor: sizes, rates, and hit ratios from
/proc/spl/kstat/zfs counters plus per-device data from interval-mode
``zpool iostat -v`` (rates over a 1-second window measured at each
refresh), refreshed on a user-configurable interval while the tab is
visible.  Rolling time-series charts are Cairo-drawn on a
Gtk.DrawingArea that redraws every refresh tick, so the display updates
dynamically without any extra charting dependency.  "Alignment" (built
in alignment_page) shows blocksize alignment across device, pool,
dataset, and VM layers with tuning advice from observed workloads and
the user survey.  The shared refresh timer refreshes whichever view is
visible.

Data-source availability follows the model in memory_stats and
alignment_stats: each source degrades on its own with an explanatory
note, and absent kstat fields render as "—".
"""

import threading
from collections import deque

import cairo
import gi

gi.require_version("Gtk", "3.0")
from alignment_page import create_alignment_view, refresh_alignment_view
from config_core import (
    get_memory_config,
    get_ui_state,
    save_memory_config,
    save_ui_state,
)
from disk_repository import format_bytes
from gi.repository import GLib, Gtk
from gui_helpers import (
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
)

# Number of samples kept per chart.  At the 5 s default interval this is
# about 25 minutes of history; the window slides as samples age out.
CHART_MAX_SAMPLES = 300

# Chart series colours (RGB 0.0-1.0).
_SERIES_COLORS = [
    (0.20, 0.40, 0.70),  # blue
    (0.96, 0.47, 0.00),  # orange
]
_REFERENCE_COLOR = (0.60, 0.60, 0.60)

# Nice-round-ceiling ladder used for chart Y-axis scaling.
_NICE_LADDER = (1, 2, 5)


def _nice_ceiling(value):
    """Return the smallest ladder value (1/2/5 x 10^k) >= *value*."""
    if value <= 0:
        return 1.0
    exponent = 0
    scaled = float(value)
    while scaled > 5:
        scaled /= 10.0
        exponent += 1
    for step in _NICE_LADDER:
        if scaled <= step:
            return step * 10**exponent
    return 10 ** (exponent + 1)


def _format_age(seconds):
    """Format a duration for chart X-axis labels (e.g. '4m 59s')."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


class RollingChart:
    """Rolling time-series chart drawn with Cairo on a Gtk.DrawingArea.

    Holds up to *max_samples* points of one or two series and redraws via
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
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        cr.set_source_rgb(1, 1, 1)
        cr.paint()

        cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9)

        left, right, top, bottom = 58, 8, 18, 16
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)

        if len(self._points) < 2:
            cr.set_source_rgb(0.4, 0.4, 0.4)
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
            y_max = _nice_ceiling(peak * 1.05) if peak > 0 else 1.0
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
        cr.set_source_rgb(0.85, 0.85, 0.85)
        for i in range(5):
            value = y_max * i / 4
            y = _y(value)
            cr.move_to(left, y)
            cr.line_to(left + plot_w, y)
            cr.stroke()
            label = f"{value:.0f}%" if self.percent else self.formatter(value)
            cr.set_source_rgb(0.35, 0.35, 0.35)
            cr.move_to(2, y + 3)
            cr.show_text(label)
            cr.set_source_rgb(0.85, 0.85, 0.85)

        # X-axis age labels at both ends (draws happen right after appends,
        # so the newest point is effectively "now").
        cr.set_source_rgb(0.35, 0.35, 0.35)
        cr.move_to(left, height - 4)
        cr.show_text(f"-{_format_age(t_span)}")
        cr.move_to(left + plot_w - 24, height - 4)
        cr.show_text("now")

        # Reference line (dashed).
        if self._reference is not None:
            y = _y(self._reference)
            cr.set_source_rgb(*_REFERENCE_COLOR)
            cr.set_dash([4, 4])
            cr.move_to(left, y)
            cr.line_to(left + plot_w, y)
            cr.stroke()
            cr.set_dash([])
            if self._reference_label:
                cr.move_to(left + 4, y - 3)
                cr.show_text(self._reference_label)
                cr.set_source_rgb(0.35, 0.35, 0.35)

        # Series polylines with translucent fills.
        for index in range(len(self.series_names)):
            color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
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
            color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
            latest = self._points[-1][1][index]
            if self.percent:
                text = f"{name} {format_percent(latest)}"
            else:
                text = f"{name} {self.formatter(latest) if latest is not None else '—'}"
            cr.set_source_rgb(*color)
            cr.rectangle(x, 4, 8, 8)
            cr.fill()
            cr.set_source_rgb(0.2, 0.2, 0.2)
            cr.move_to(x + 11, 12)
            cr.show_text(text)
            x += 22 + 7 * len(text)


# ---------------------------------------------------------------------------
# Page construction
# ---------------------------------------------------------------------------


def _value_row(grid, row, caption):
    """Add a caption/value row to a Gtk.Grid; return the value label."""
    caption_label = Gtk.Label(label=caption)
    caption_label.set_halign(Gtk.Align.START)
    grid.attach(caption_label, 0, row, 1, 1)
    value = Gtk.Label(label="—")
    value.set_halign(Gtk.Align.START)
    grid.attach(value, 1, row, 1, 1)
    return value


def _device_table(app, store_attr, columns, state_key):
    """Build a TreeView for cache/log vdev rows; return the view and store.

    The view is bound to the UI-state persistence layer so column widths
    survive GUI restarts, like every other table.
    """
    store = Gtk.ListStore(*([str] * len(columns)))
    view = Gtk.TreeView(model=store)
    view.set_headers_visible(True)
    for index, title in enumerate(columns):
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title, renderer, text=index)
        configure_treeview_column(col)
        view.append_column(col)
    setattr(app, store_attr, store)
    app._ui_state.bind_treeview(view, state_key)
    view.set_size_request(-1, 60)
    return view, store


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


def create_memory_page(app):
    """Build and return the Performance tab widget."""
    app._memory_timer = None
    app._memory_sample = None
    app._memory_refresh_pending = False
    app._alignment_refresh_pending = False

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_margin_start(15)
    box.set_margin_end(15)
    box.set_margin_top(15)
    box.set_margin_bottom(15)
    scrolled.add(box)

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
    box.pack_start(controls, False, False, 0)

    # --- View switcher: Live Charts / Alignment ---
    view_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    charts_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Live Charts")
    alignment_radio = Gtk.RadioButton.new_with_label_from_widget(charts_radio, "Alignment")
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

    # --- ARC section ---
    version_note = ""
    caps = getattr(app.ctx, "zfs_caps", None)
    if caps is not None and caps.version is not None:
        kmod = caps.version.kmod
        version_note = f"OpenZFS kernel module {kmod[0]}.{kmod[1]}.{kmod[2]}"
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

    app._memory_arc_size_chart = RollingChart("ARC size", ["size"])
    app._memory_arc_rate_chart = RollingChart(
        "ARC hit rate", ["hit rate"], percent=True, formatter=lambda v: f"{v:.0f}"
    )
    charts_arc = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    charts_arc.pack_start(app._memory_arc_size_chart.widget, True, True, 0)
    charts_arc.pack_start(app._memory_arc_rate_chart.widget, True, True, 0)
    charts_box.pack_start(charts_arc, True, True, 0)

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

    app._memory_l2_chart = RollingChart("L2ARC traffic", ["read", "write"])
    charts_box.pack_start(app._memory_l2_chart.widget, True, True, 0)

    l2_view, _l2_store = _device_table(
        app,
        "_memory_l2_store",
        ["Pool", "Vdev", "Capacity (alloc/free)", "Read rate", "Write rate"],
        "memory_l2_view",
    )
    charts_box.pack_start(l2_view, False, False, 0)

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

    app._memory_slog_chart = RollingChart("SLOG writes", ["write"])
    charts_box.pack_start(app._memory_slog_chart.widget, True, True, 0)

    slog_view, _slog_store = _device_table(
        app,
        "_memory_slog_store",
        ["Pool", "Vdev", "Capacity (alloc/free)", "Writes/s", "Write rate"],
        "memory_slog_view",
    )
    charts_box.pack_start(slog_view, False, False, 0)

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


def refresh_memory_page(app):
    """Refresh whichever Performance view is visible, off-thread."""
    if _current_memory_view(app) == "alignment":
        refresh_alignment_view(app)
        return

    if getattr(app, "_memory_refresh_pending", False):
        return
    app._memory_refresh_pending = True

    def _collect():
        sample = collect_memory_sample()
        GLib.idle_add(_finish_refresh, app, sample)

    def _finish_refresh(_app, sample):
        _app._memory_refresh_pending = False
        _apply_memory_sample(_app, sample)
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
