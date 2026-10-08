"""Alignment view — blocksize alignment chain and tuning advice.

The second view of the Performance page (behind the Live Charts /
Alignment radio switcher built in memory_page).  Everything here is
advisory only: the chain table shows the device → pool → dataset → VM
blocksize stack, the findings table renders alignment_analysis Finding
rows, and the workload table summarises each pool's observed request-size
histogram and classifier verdict.  The memory-tier observations grid
carries the kstat-analyzer-inspired ARC/prefetcher readouts.

Data-source availability follows the memory_stats/alignment_stats model:
each source degrades on its own and the availability note names what is
missing; absent values render as "—".
"""

import threading

import gi

gi.require_version("Gtk", "3.0")
from alignment_analysis import (
    SYNC_COLUMNS,
    TRAFFIC_COLUMNS,
    analyse,
    arc_readouts,
    classify_workload,
)
from alignment_stats import collect_alignment_sample
from disk_repository import format_bytes
from feature_config import get_alignment_survey, get_workload_profiles
from gi.repository import GLib, Gtk
from gui_helpers import (
    configure_treeview_column,
    note_label,
    reconcile_rows,
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
    if not sample.pve_available:
        missing.append("PVE VM configs (two-node installs keep them on the compute node)")
    if not missing:
        return None
    return "Unavailable on this host: " + ", ".join(missing) + "."


def _table(app, store_attr, columns, state_key):
    """Build a bound TreeView; return the view and store (memory_page pattern)."""
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

    # --- Alignment chain ---
    box.pack_start(section_header("Alignment Chain"), False, False, 0)
    chain_view, _chain_store = _table(
        app,
        "_alignment_chain_store",
        ["Layer", "Object", "Block size", "Detail"],
        "alignment_chain_view",
    )
    box.pack_start(chain_view, False, False, 0)

    # --- Findings ---
    box.pack_start(section_header("Findings & Recommendations"), False, False, 0)
    findings_view, _findings_store = _table(
        app,
        "_alignment_findings_store",
        ["Severity", "Layer", "Subject", "Finding", "Recommendation"],
        "alignment_findings_view",
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


def _apply_alignment_sample(app, sample):
    """Synchronously apply one sample to the view widgets."""
    app._alignment_sample = sample

    note = _availability_note(sample)
    if note is None:
        app._alignment_note.hide()
    else:
        show_note(app._alignment_note, note)

    _apply_memory_readouts(app, sample)
    _apply_chain_rows(app, sample)
    _apply_findings_rows(app, sample)
    _apply_workload_rows(app, sample)


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
    rows = {}
    for pool in sample.pools:
        block = None if pool.ashift_effective is None else 1 << pool.ashift_effective
        configured = pool.ashift_configured or "—"
        auto = configured in ("0", "-", "default", "—")
        rows[("Pool", pool.name)] = [
            "Pool",
            pool.name,
            f"ashift {pool.ashift_effective} ({format_bytes(block)})" if block else "—",
            f"configured {configured}" + (" (auto)" if auto else ""),
        ]
        for member in pool.members:
            rows[("Device", member.path)] = [
                "Device",
                member.path.rsplit("/", 1)[-1],
                _fmt_sectors(member),
                _device_status(member),
            ]
        for ds in sample.datasets:
            if ds.name.split("/", 1)[0] != pool.name:
                continue
            if ds.kind == "filesystem":
                rows[("Dataset", ds.name)] = [
                    "Dataset",
                    ds.name,
                    f"recordsize {ds.recordsize or '—'}",
                    ds.recordsize_source or "—",
                ]
            else:
                rows[("VM", ds.name)] = [
                    "VM",
                    ds.name.rsplit("/", 1)[-1],
                    f"volblocksize {ds.volblocksize or '—'}",
                    _vm_detail(sample, ds),
                ]
    reconcile_rows(app._alignment_chain_store, rows)


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


def _apply_findings_rows(app, sample):
    survey = get_alignment_survey(app.config)
    profiles = get_workload_profiles(app.config)
    findings = analyse(sample, survey=survey, profiles=profiles)
    store = app._alignment_findings_store
    store.clear()
    for finding in findings:
        store.append(
            [
                _SEVERITY_MARKERS.get(finding.severity, finding.severity),
                finding.layer,
                finding.subject,
                finding.message,
                finding.recommendation,
            ]
        )


def _apply_workload_rows(app, sample):
    store = app._alignment_workload_store
    store.clear()
    for pool in sample.pools:
        hist = sample.histograms.get(pool.name)
        verdict = classify_workload(hist, sample.prefetch if sample.prefetch_available else None)
        label = verdict.label
        if verdict.confidence == "low" and label in ("sequential", "random-sync", "mixed"):
            label += " (low confidence)"
        total = hist.ops(TRAFFIC_COLUMNS) if hist is not None else None
        store.append(
            [
                pool.name,
                label,
                _fmt_dominant(hist.dominant_bucket(SYNC_COLUMNS)) if hist else "—",
                _fmt_dominant(hist.dominant_bucket(TRAFFIC_COLUMNS)) if hist else "—",
                _fmt_ops(total),
                _fmt_pct(verdict.prefetch_rate),
            ]
        )
