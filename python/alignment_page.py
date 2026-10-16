"""Alignment view — blocksize alignment chain and tuning advice.

The second view of the Performance page (behind the Live Charts /
Alignment radio switcher built in memory_page).  Everything here is
advisory only: the blocksize-scan table shows the device → pool →
dataset → VM blocksize stack, the blocksize ladder draws that same
stack visually (a log2-scale ladder per pool, renderer chosen by the
charting module), the topology table lays out each pool's
vdev classes and their members with the pool's ashift, the findings
table renders alignment_analysis Finding rows, and the workload table
summarises each pool's observed request-size histogram and classifier
verdict.  The memory-tier observations grid carries the
kstat-analyzer-inspired ARC/prefetcher readouts.

Data-source availability follows the memory_stats/alignment_stats model:
each source degrades on its own and the availability note names what is
missing; absent values render as "—".

Refreshes are scroll-stable: the page's vertical offset is saved and
restored around every apply (the datasets-page idiom), and every table
reconciles in place on stable keys — the chain, topology, and findings
tables key on hidden identity columns, so legitimately changed rows
shift only the rows below them instead of collapsing and rebuilding
the page.
"""

import math
import threading

import cairo
import gi

gi.require_version("Gtk", "3.0")
from alignment_analysis import (
    SYNC_COLUMNS,
    TRAFFIC_COLUMNS,
    analyse,
    arc_readouts,
    blocksize_ladder,
    classify_workload,
    vdev_groups,
)
from alignment_stats import collect_alignment_sample
from charting import (
    LADDER_EMPTY_HEIGHT,
    LADDER_LEGEND,
    LADDER_ROW_HEIGHT,
    LADDER_STATE_COLORS,
    REFERENCE_COLOR,
    create_blocksize_ladder,
    format_blocksize,
    ladder_axis_range,
    ladder_pixel_height,
)
from disk_repository import format_bytes
from feature_config import get_alignment_survey, get_workload_profiles
from gi.repository import GLib, Gtk
from gui_helpers import (
    configure_treeview_column,
    note_label,
    section_header,
    set_text_if_changed,
    show_note,
)
from memory_stats import format_percent

# Memory-tier observation rows (arc_readouts keys plus the prefetcher
# vote, which comes from zfetchstats rather than arcstats).
_MEMORY_ROWS = (
    "Demand data hit rate",
    "Demand metadata hit rate",
    "Prefetch data hit rate",
    "Prefetcher hit rate",
    "Ghost hits (share of real)",
    "Evictions eligible for L2ARC",
    "Average L2 hit size",
)

_SEVERITY_MARKERS = {"OK": "✓ OK", "info": "• info", "WARN": "⚠ WARN"}


def _fmt_pct(fraction):
    """Render a 0-1 fraction as a percentage; '—' when unknown."""
    return format_percent(fraction * 100) if fraction is not None else "—"


class BlocksizeLadder:
    """Cairo-drawn blocksize ladder on a Gtk.DrawingArea.

    Fallback renderer (see ``charting.create_blocksize_ladder``): used on
    hosts without the optional matplotlib package. Draws the same picture
    as the matplotlib ladder from the same shared vocabulary — one row per
    rung on a log2 grid, the pool's ashift block as a dashed reference
    line spanning its rows, rung colours by state — so the visual degrades
    in quality only, never in meaning. Composition (rather than
    subclassing Gtk.DrawingArea) keeps the class usable under the test GTK
    mocks, like the Cairo ``RollingChart``.
    """

    def __init__(self, title="Blocksize ladder"):
        self.title = title
        self._pools = []
        self._unavailable = False
        self.widget = Gtk.DrawingArea()
        self.widget.set_size_request(-1, LADDER_EMPTY_HEIGHT)
        self.widget.connect("draw", self._on_draw)

    # -- data management (same contract as the matplotlib renderer) ---------

    def update(self, pools, unavailable=False):
        """Replace the ladder's pool set and redraw."""
        self._pools = list(pools)
        self._unavailable = unavailable
        height = ladder_pixel_height(self._pools) if self._pools else LADDER_EMPTY_HEIGHT
        self.widget.set_size_request(-1, height)
        self.widget.queue_draw()

    @property
    def pools(self):
        """Snapshot of the rendered pool set."""
        return list(self._pools)

    # -- drawing -----------------------------------------------------------

    def _on_draw(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9)

        if not self._pools:
            message = (
                f"{self.title} — pool and device data unavailable"
                if self._unavailable
                else f"{self.title} — no pools found"
            )
            cr.set_source_rgb(0.42, 0.42, 0.42)
            cr.move_to(16, height // 2)
            cr.show_text(message)
            return

        labels = []
        for pool in self._pools:
            labels.append(pool.pool)
            labels.extend(bar.label for bar in pool.bars)
        # Left gutter wide enough for the longest label, then the grid.
        gutter = max(cr.text_extents(label).x_advance for label in labels) + 20
        left = max(64.0, gutter)
        right = width - 14.0
        # First row starts below the legend band reserved by the top margin.
        top = 30.0
        plot_w = max(1.0, right - left)
        x_min, x_max, ticks = ladder_axis_range(self._pools)
        span = math.log2(x_max / x_min)

        def _x(size):
            return left + math.log2(size / x_min) / span * plot_w

        # Log2 grid with tick labels along the bottom.
        for tick in ticks:
            x = _x(tick)
            cr.set_source_rgb(0.87, 0.87, 0.87)
            cr.move_to(x, top)
            cr.line_to(x, height - 18)
            cr.stroke()
            label = format_blocksize(tick)
            extent = cr.text_extents(label)
            cr.set_source_rgb(0.35, 0.35, 0.35)
            cr.move_to(x - extent.x_advance / 2, height - 6)
            cr.show_text(label)

        y = top
        for pool in self._pools:
            # Header row: bold pool name with a separator under it.
            cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_source_rgb(0.20, 0.20, 0.20)
            cr.move_to(8, y + 13)
            cr.show_text(pool.pool)
            cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_source_rgb(0.86, 0.86, 0.86)
            cr.move_to(left, y + LADDER_ROW_HEIGHT - 0.5)
            cr.line_to(right, y + LADDER_ROW_HEIGHT - 0.5)
            cr.stroke()
            y += LADDER_ROW_HEIGHT
            pool_top = y - LADDER_ROW_HEIGHT
            for bar in pool.bars:
                color = LADDER_STATE_COLORS.get(bar.state, LADDER_STATE_COLORS["info"])
                cr.set_source_rgb(*color)
                cr.rectangle(left, y + 4, _x(bar.size) - left, LADDER_ROW_HEIGHT - 9)
                cr.fill()
                cr.set_source_rgb(0.25, 0.25, 0.25)
                cr.move_to(8, y + 13)
                cr.show_text(bar.label)
                y += LADDER_ROW_HEIGHT
            if pool.block is not None:
                # Dashed ashift reference spanning the header and rungs.
                cr.set_source_rgb(*REFERENCE_COLOR)
                cr.set_dash([4, 4])
                cr.move_to(_x(pool.block), pool_top)
                cr.line_to(_x(pool.block), y)
                cr.stroke()
                cr.set_dash([])

        # Legend, top-right: the shared state colour key.
        x = right
        for state, text in reversed(LADDER_LEGEND):
            extent = cr.text_extents(text)
            cr.set_source_rgb(0.30, 0.30, 0.30)
            cr.move_to(x - extent.x_advance, 12)
            cr.show_text(text)
            x -= extent.x_advance + 14
            cr.set_source_rgb(*LADDER_STATE_COLORS[state])
            cr.rectangle(x, 4, 8, 8)
            cr.fill()
            x -= 18


def _fmt_ops(count):
    return f"{count:,}" if count is not None else "—"


def _prefetch_rate(prefetch):
    """Prefetcher hit rate from zfetchstats counters; None without traffic."""
    hits, misses = prefetch.get("hits"), prefetch.get("misses")
    if hits is None or misses is None:
        return None
    total = hits + misses
    return hits / total if total > 0 else None


def _fmt_dominant(dominant):
    """Render a dominant-bucket pair as '8K (63%)'; '—' without traffic."""
    if dominant is None:
        return "—"
    bucket, share = dominant
    return f"{format_bytes(bucket)} ({share:.0%})"


def _pool_detail(pool):
    """Detail cell for a Pool chain row: configured-vs-auto ashift status.

    The zfs-get strings "0"/"-"/"default" all mean the property is unset
    and ZFS auto-detected the ashift; None means the property read failed
    (which is unknown, not auto).
    """
    configured = pool.ashift_configured
    if configured in ("0", "-", "default", ""):
        return "auto (ashift not configured)"
    if configured is None:
        return "ashift property unavailable"
    return f"configured ashift {configured}"


def _device_status(member):
    """One-line sector-geometry summary for a chain Device row."""
    logical, physical = member.logical_sector, member.physical_sector
    if logical is None or physical is None:
        return "—"
    if logical < physical:
        return "512e advanced format"
    return f"{format_bytes(physical)} native"


def _fmt_sectors(member):
    logical, physical = member.logical_sector, member.physical_sector
    if logical is None or physical is None:
        return "—"
    return f"{format_bytes(logical)} logical / {format_bytes(physical)} physical"


def _fmt_pool_block(pool):
    """Block-size cell for a pool row: bytes plus effective ashift; '—'."""
    block = None if pool.ashift_effective is None else 1 << pool.ashift_effective
    if not block:
        return "—"
    return f"{format_bytes(block)} (effective ashift {pool.ashift_effective})"


def _leaf_short_names(node):
    """Short device names of every disk leaf under *node*, in tree order."""
    if node.vdev_type == "disk":
        return [node.name.rsplit("/", 1)[-1]]
    names = []
    for child in node.children:
        names.extend(_leaf_short_names(child))
    return names


def _availability_note(sample):
    """Return the per-source availability note, or None when all present."""
    missing = []
    if not sample.pools_available:
        missing.append("zfs/zpool reads")
    if not sample.iostat_r_available:
        missing.append("request-size histograms")
    if not sample.arcstats_available:
        missing.append("ARC kstats")
    if not sample.prefetch_available:
        missing.append("prefetcher kstats")
    if not sample.objset_available:
        missing.append(
            "per-dataset I/O counters (OpenZFS 2.2+ objset kstats — observed-size "
            "advice stays per-pool)"
        )
    if not sample.pve_available:
        missing.append("PVE VM configs (two-node installs keep them on the compute node)")
    notes = []
    if missing:
        notes.append("Unavailable on this host: " + ", ".join(missing) + ".")
    if sample.dataset_read_failures:
        # Per-pool degrade: the failed pools lost only their dataset rows;
        # the rest of the chain stays live, so the note names the pools
        # instead of declaring the whole source down.
        notes.append(
            "Dataset block properties unreadable for: "
            + ", ".join(sample.dataset_read_failures)
            + "."
        )
    topology_failures = [pool.name for pool in sample.pools if pool.topology is None]
    if topology_failures:
        # Same per-pool degrade for the topology reads: the ashift is probed
        # separately from `zpool status`, so a failed pool keeps its chain
        # row and whatever ashift is known — only its topology rows are gone.
        notes.append("vdev topology unreadable for: " + ", ".join(topology_failures) + ".")
    if not notes:
        return None
    return " ".join(notes)


def _table(app, store_attr, columns, state_key, hidden_key=False):
    """Build a bound TreeView; return the view and store (memory_page pattern).

    With *hidden_key* the store carries one extra leading column holding
    each row's identity key for ``_reconcile_rows``; no TreeViewColumn is
    created for it, so it never renders. Keying on a hidden column (rather
    than on rendered text) keeps row identity stable while visible cells
    drift between refreshes.
    """
    store = Gtk.ListStore(*([str] * (len(columns) + 1 if hidden_key else len(columns))))
    view = Gtk.TreeView(model=store)
    view.set_headers_visible(True)
    offset = 1 if hidden_key else 0
    for index, title in enumerate(columns):
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title, renderer, text=index + offset)
        configure_treeview_column(col)
        view.append_column(col)
    setattr(app, store_attr, store)
    app._ui_state.bind_treeview(view, state_key)
    view.set_size_request(-1, 60)
    return view, store


def _reconcile_rows(store, rows, key_column=0):
    """Update *store* in place against ordered ``{key: row-values}``.

    Unlike ``gui_helpers.reconcile_rows`` (two-column keys, appends new
    rows at the end — right for vdev tables), this reconciles on one key
    column and keeps the store ordered like *rows*: surviving rows are
    updated in place so their heights and positions persist across
    refreshes (a numeric scroll restore alone cannot hold the page steady
    when rows churn), vanished rows are removed, and new rows are inserted
    at their ordered position so a change shifts only the rows below it.
    *rows* must be in a deterministic order — a pure function of its key
    set — which the callers guarantee by construction.
    """
    existing = {}
    tree_iter = store.get_iter_first()
    while tree_iter is not None:
        existing[store.get_value(tree_iter, key_column)] = tree_iter
        tree_iter = store.iter_next(tree_iter)
    for key in [key for key in existing if key not in rows]:
        store.remove(existing.pop(key))
    tree_iter = store.get_iter_first()
    for position, (key, row) in enumerate(rows.items()):
        current = store.get_value(tree_iter, key_column) if tree_iter is not None else None
        if current == key:
            for col_idx, val in enumerate(row):
                if store.get_value(tree_iter, col_idx) != val:
                    store.set_value(tree_iter, col_idx, val)
            tree_iter = store.iter_next(tree_iter)
        else:
            if key in existing:
                # A surviving row sitting further down must move up to its
                # ordered position; re-inserting it here is cheaper and
                # steadier than shifting everything around it.
                store.remove(existing.pop(key))
            store.insert(position, list(row))


def _value_row(grid, row, caption):
    """Add a caption/value row to a Gtk.Grid; return the value label."""
    caption_label = Gtk.Label(label=caption)
    caption_label.set_halign(Gtk.Align.START)
    grid.attach(caption_label, 0, row, 1, 1)
    value = Gtk.Label(label="—")
    value.set_halign(Gtk.Align.START)
    grid.attach(value, 1, row, 1, 1)
    return value


def create_alignment_view(app):
    """Build and return the Alignment view box for the Performance page."""
    app._alignment_refresh_pending = getattr(app, "_alignment_refresh_pending", False)
    app._alignment_sample = None

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

    box.pack_start(
        section_header(
            "Alignment — Block Size Chain",
            "device → pool → dataset → VM · advisory only",
        ),
        False,
        False,
        0,
    )

    app._alignment_note = note_label()
    box.pack_start(app._alignment_note, False, False, 0)

    # --- Memory-tier observations ---
    box.pack_start(section_header("Memory-tier Observations (since boot)"), False, False, 0)
    memory_grid = Gtk.Grid()
    memory_grid.set_column_spacing(24)
    memory_grid.set_row_spacing(4)
    memory_labels = {}
    for row, caption in enumerate(_MEMORY_ROWS):
        memory_labels[caption] = _value_row(memory_grid, row, caption)
    app._alignment_memory_labels = memory_labels
    box.pack_start(memory_grid, False, False, 0)

    # --- Blocksize scan ---
    # section_header() takes no margins, so the section break is sized here:
    # the box spacing (12) plus this top margin puts a clearly larger gap
    # above the heading than the spacing below it, whatever the theme.
    chain_header = section_header("Blocksize scan")
    chain_header.set_margin_top(12)
    box.pack_start(chain_header, False, False, 0)
    chain_view, _chain_store = _table(
        app,
        "_alignment_chain_store",
        ["Layer", "Object", "Block size", "Detail"],
        "alignment_chain_view",
        hidden_key=True,
    )
    box.pack_start(chain_view, False, False, 0)

    # --- Blocksize ladder ---
    # The visual companion of the scan table above: the same device → pool
    # → dataset → VM chain drawn as a log2-scale ladder per pool, with the
    # pool's ashift block as a dashed reference line (renderer and shared
    # vocabulary from the charting module — matplotlib when installed, the
    # Cairo BlocksizeLadder below otherwise).
    box.pack_start(
        section_header("Blocksize Ladder", "log₂ scale · dashed line = the pool's ashift block"),
        False,
        False,
        0,
    )
    app._alignment_ladder = create_blocksize_ladder()
    box.pack_start(app._alignment_ladder.widget, False, False, 0)

    # --- Pool topology ---
    box.pack_start(section_header("Pool Topology"), False, False, 0)
    topology_view, _topology_store = _table(
        app,
        "_alignment_topology_store",
        ["Pool", "Class", "Vdev", "Type", "Members", "Block size"],
        "alignment_topology_view",
        hidden_key=True,
    )
    box.pack_start(topology_view, False, False, 0)

    # --- Findings ---
    box.pack_start(section_header("Findings & Recommendations"), False, False, 0)
    findings_view, _findings_store = _table(
        app,
        "_alignment_findings_store",
        ["Severity", "Layer", "Subject", "Finding", "Recommendation"],
        "alignment_findings_view",
        hidden_key=True,
    )
    box.pack_start(findings_view, False, False, 0)

    # --- Workload ---
    box.pack_start(section_header("Workload (since boot)"), False, False, 0)
    workload_view, _workload_store = _table(
        app,
        "_alignment_workload_store",
        [
            "Pool",
            "Verdict",
            "Dominant sync",
            "Dominant (all)",
            "Ops since boot",
            "Prefetch hit rate",
        ],
        "alignment_workload_view",
    )
    box.pack_start(workload_view, False, False, 0)

    return box


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def refresh_alignment_view(app):
    """Collect an alignment sample off-thread and update the view on idle."""
    if getattr(app, "_alignment_refresh_pending", False):
        return
    app._alignment_refresh_pending = True

    ctx = getattr(app, "ctx", None)
    zfs_repo = getattr(ctx, "zfs_repository", None)
    disk_repo = getattr(ctx, "disk_repository", None)
    survey = get_alignment_survey(app.config)
    profiles = get_workload_profiles(app.config)

    def _collect():
        sample = collect_alignment_sample(zfs_repo=zfs_repo, disk_repo=disk_repo)
        GLib.idle_add(_finish_refresh, app, sample, survey, profiles)

    def _finish_refresh(_app, sample, _survey, _profiles):
        _app._alignment_refresh_pending = False
        _apply_alignment_sample(_app, sample)
        return False

    threading.Thread(target=_collect, daemon=True).start()


def _restore_scroll(scrolled, saved_value):
    """Clamp and restore a saved vertical scroll offset."""
    vadj = scrolled.get_vadjustment()
    if vadj is None:
        return False
    upper = vadj.get_upper()
    page = vadj.get_page_size()
    max_value = max(0.0, upper - page)
    vadj.set_value(max(0.0, min(saved_value, max_value)))
    return False


def _apply_alignment_sample(app, sample):
    """Synchronously apply one sample to the view widgets."""
    # The previous sample is the delta baseline for the per-dataset
    # observed request sizes (alignment_analysis prefers the interval
    # between the last two samples over the since-boot averages).
    prev_sample = getattr(app, "_alignment_sample", None)
    app._alignment_sample = sample

    # Datasets-page idiom: remember the vertical scroll offset so the
    # refresh does not jump the view, and restore it (clamped) once GTK
    # has allocated the updated rows.  The tables below reconcile in
    # place, so the offset refers to the same content on both sides of
    # the refresh.
    scrolled = getattr(app, "performance_scrolled", None)
    saved_scroll = None
    if scrolled is not None:
        vadj = scrolled.get_vadjustment()
        if vadj is not None:
            saved_scroll = vadj.get_value()

    note = _availability_note(sample)
    if note is None:
        app._alignment_note.hide()
    else:
        show_note(app._alignment_note, note)

    _apply_memory_readouts(app, sample)
    _apply_chain_rows(app, sample)
    _apply_ladder(app, sample)
    _apply_topology_rows(app, sample)
    _apply_findings_rows(app, sample, prev_sample)
    _apply_workload_rows(app, sample)

    if saved_scroll is not None:
        GLib.idle_add(_restore_scroll, scrolled, saved_scroll)


def _apply_memory_readouts(app, sample):
    labels = app._alignment_memory_labels
    readouts = arc_readouts(sample.arc, any(pool.has_cache for pool in sample.pools))
    for caption in _MEMORY_ROWS:
        if caption == "Prefetcher hit rate":
            set_text_if_changed(labels[caption], _fmt_pct(_prefetch_rate(sample.prefetch)))
            continue
        value = readouts.get(caption)
        if caption == "Average L2 hit size":
            set_text_if_changed(labels[caption], format_bytes(value) if value else "—")
        else:
            set_text_if_changed(labels[caption], _fmt_pct(value))


def _apply_chain_rows(app, sample):
    """Reconcile the chain table in place on hidden identity keys.

    Device rows display their short name but are identified by the full
    device path (two disks of one model may share a short name), so the
    identity lives in the hidden key column — keyed on rendered cells the
    device rows would churn on every refresh, dragging the page with them.
    Rows are emitted pool by pool (pool row, its devices, then its
    datasets), a deterministic order for ``_reconcile_rows``.
    """
    rows = {}
    for pool in sample.pools:
        rows[f"Pool:{pool.name}"] = [
            f"Pool:{pool.name}",
            "Pool",
            pool.name,
            _fmt_pool_block(pool),
            _pool_detail(pool),
        ]
        for member in pool.members:
            key = f"Device:{member.path}"
            rows[key] = [
                key,
                "Device",
                member.path.rsplit("/", 1)[-1],
                _fmt_sectors(member),
                _device_status(member),
            ]
        for ds in sample.datasets:
            if ds.name.split("/", 1)[0] != pool.name:
                continue
            if ds.kind == "filesystem":
                rows[f"Dataset:{ds.name}"] = [
                    f"Dataset:{ds.name}",
                    "Dataset",
                    ds.name,
                    f"recordsize {ds.recordsize or '—'}",
                    ds.recordsize_source or "—",
                ]
            else:
                rows[f"VM:{ds.name}"] = [
                    f"VM:{ds.name}",
                    "VM",
                    ds.name.rsplit("/", 1)[-1],
                    f"volblocksize {ds.volblocksize or '—'}",
                    _vm_detail(sample, ds),
                ]
    _reconcile_rows(app._alignment_chain_store, rows)


def _apply_ladder(app, sample):
    """Feed the blocksize ladder its per-pool rungs.

    The ladder's inputs degrade per source exactly like the scan table
    (blocksize_ladder drops the rungs whose source failed), so no extra
    note is needed here — only the wholesale pool failure renders the
    chart's own unavailable placeholder.
    """
    app._alignment_ladder.update(blocksize_ladder(sample), unavailable=not sample.pools_available)


def _apply_topology_rows(app, sample):
    """Reconcile the topology table in place on hidden identity keys.

    One row per vdev group (a mirror/raidz group, or a bare disk),
    labelled with its class; rows are keyed on pool + vdev name, which
    `zpool status` keeps stable across refreshes, so groups reconcile in
    place like the other sections.  A pool whose status read failed keeps
    one row carrying whatever ashift is known (the ashift probe runs
    independently of the topology read) and is named in the availability
    note instead of losing its blocksize context.
    """
    rows = {}
    for pool in sample.pools:
        block_cell = _fmt_pool_block(pool)
        if pool.topology is None:
            key = f"Topology:{pool.name}"
            rows[key] = [key, pool.name, "—", "—", "—", "topology unreadable", block_cell]
            continue
        for class_label, group in vdev_groups(pool.topology):
            key = f"Topology:{pool.name}:{group.name}"
            members = _leaf_short_names(group)
            rows[key] = [
                key,
                pool.name,
                class_label,
                group.name.rsplit("/", 1)[-1] if group.vdev_type == "disk" else group.name,
                group.vdev_type,
                ", ".join(members) if members else "—",
                block_cell,
            ]
    _reconcile_rows(app._alignment_topology_store, rows)


def _vm_detail(sample, ds):
    """Detail cell for a VM chain row: the PVE disk line when known."""
    short = ds.name.rsplit("/", 1)[-1]
    option = sample.vm_disks.get(short)
    if option is None:
        if not sample.pve_available:
            return "PVE configs unreadable on this host"
        return "not referenced in local PVE configs"
    opts = " ".join(
        f"{key}={value}" for key, value in sorted(option.options.items()) if value != "1"
    )
    flags = " ".join(sorted(key for key, value in option.options.items() if value == "1"))
    detail = option.bus
    for part in (opts, flags):
        if part:
            detail += f" {part}"
    return detail


def _finding_row(finding):
    """Store row for one finding; column 0 is the hidden identity key.

    The key pairs the emitting rule's stable identity with the subject, so
    a finding whose message numbers drift between refreshes (ghost-hit
    shares, op counts) is still recognised as the same row and updated in
    place rather than removed and re-added.
    """
    key = f"{finding.key}:{finding.subject}"
    return [
        key,
        _SEVERITY_MARKERS.get(finding.severity, finding.severity),
        finding.layer,
        finding.subject,
        finding.message,
        finding.recommendation,
    ]


def _apply_findings_rows(app, sample, prev_sample=None):
    """Reconcile the findings table in place (no clear-and-rebuild).

    analyse() emits findings in a deterministic rule order, so the store
    order stays a pure function of the finding set: surviving rows keep
    their positions and heights across refreshes and a changed row shifts
    only the rows below it — which is what keeps the page steady mid-view
    when findings legitimately appear or disappear.
    """
    survey = get_alignment_survey(app.config)
    profiles = get_workload_profiles(app.config)
    findings = analyse(sample, survey=survey, profiles=profiles, prev_sample=prev_sample)
    rows = {}
    for finding in findings:
        row = _finding_row(finding)
        rows[row[0]] = row
    _reconcile_rows(app._alignment_findings_store, rows)


def _apply_workload_rows(app, sample):
    """Reconcile the workload table in place, keyed on the pool name.

    The verdict text can flip between refreshes (low-confidence suffixes,
    reclassification as traffic accumulates), so rows are keyed on the
    pool — not on any rendered cell.
    """
    rows = {}
    for pool in sample.pools:
        hist = sample.histograms.get(pool.name)
        verdict = classify_workload(hist, sample.prefetch if sample.prefetch_available else None)
        label = verdict.label
        if verdict.confidence == "low" and label in ("sequential", "random-sync", "mixed"):
            label += " (low confidence)"
        total = hist.ops(TRAFFIC_COLUMNS) if hist is not None else None
        rows[pool.name] = [
            pool.name,
            label,
            _fmt_dominant(hist.dominant_bucket(SYNC_COLUMNS)) if hist else "—",
            _fmt_dominant(hist.dominant_bucket(TRAFFIC_COLUMNS)) if hist else "—",
            _fmt_ops(total),
            _fmt_pct(verdict.prefetch_rate),
        ]
    _reconcile_rows(app._alignment_workload_store, rows)
