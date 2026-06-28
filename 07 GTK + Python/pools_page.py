"""
Pools tab UI — the pool registry and live status are edited in a single table.

The pool list is stored in the JSON config (see backup_config.get_pools).
Rows represent either a registered pool (from app.known_pools) or an
unregistered pool (online but not in the registry). Only registered rows are
editable and removable.
"""

import re
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango, GLib

from logging_config import log_msg
from feature_config import (
    get_pools, get_pool_names, get_offsite_candidate_names,
    get_scrub_manager_config, save_scrub_manager_config,
)
from gui_helpers import (
    setup_row_scroll, set_button_markup_red, set_monospace_font,
    configure_treeview_column,
)
from scrub_manager import (
    ScrubQueue, get_all_pool_scrub_states, ScrubState,
    sync_system_scrub_for_pools,
)


# ListStore columns:
#   0 name, 1 health, 2 size, 3 alloc, 4 free, 5 freeing,
#   6 ckpoint, 7 frag, 8 cap, 9 status_flag ("registered" / "unregistered"),
#  10 offsite_candidate (bool)
COL_NAME, COL_HEALTH, COL_SIZE, COL_ALLOC, COL_FREE, \
    COL_FREEING, COL_CKPOINT, COL_FRAG, COL_CAP, COL_FLAG, \
    COL_OFFSITE = range(11)

FLAG_REGISTERED   = "registered"
FLAG_UNREGISTERED = "unregistered"


# ---------------------------------------------------------------------------
# Sort helpers
# ---------------------------------------------------------------------------

# Regex: ^([\d.]+)\s*([TGMKB]?)
# Purpose: Parse zpool size strings (e.g. "1.5T", "500G", "-") into numeric + unit parts.
# Group 1: numeric value   e.g. "1.5", "500"
# Group 2: unit suffix     e.g. "T", "G", "M", "K", "B", or "" (bytes)
# Examples:
#   "1.5T"  -> match (1.5, T)
#   "500G"  -> match (500, G)
#   "-"     -> no match (handled separately)
_SIZE_RE = re.compile(r'^([\d.]+)\s*([TGMKB]?)', re.IGNORECASE)


def _parse_size(val):
    """Convert zpool list size strings to a comparable integer."""
    if val == "-":
        return -1
    m = _SIZE_RE.match(str(val).strip())
    if not m:
        return 0
    num = float(m.group(1))
    suffix = m.group(2).upper()
    multipliers = {
        'T': 1024 ** 4, 'G': 1024 ** 3, 'M': 1024 ** 2,
        'K': 1024, 'B': 1, '': 1,
    }
    return int(num * multipliers.get(suffix, 1))


def _parse_percent(val):
    """Convert percentage strings like '15%' to a comparable float."""
    if val == "-" or val == "":
        return -1
    try:
        return float(str(val).rstrip('%'))
    except ValueError:
        return -1


def _numeric_sort_func(model, iter1, iter2, col_idx):
    """GtkTreeIterCompareFunc for size columns."""
    a = _parse_size(model.get_value(iter1, col_idx))
    b = _parse_size(model.get_value(iter2, col_idx))
    return (a > b) - (a < b)


def _percent_sort_func(model, iter1, iter2, col_idx):
    """GtkTreeIterCompareFunc for percentage columns."""
    a = _parse_percent(model.get_value(iter1, col_idx))
    b = _parse_percent(model.get_value(iter2, col_idx))
    return (a > b) - (a < b)


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def create_pools_page(app):
    """Build and return the full Pools tab widget."""
    app.known_pools = list(get_pools(app.config))
    app._pools_saved_state = list(app.known_pools)
    app.pools_dirty = False

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(10)
    box.set_margin_end(10)
    box.set_margin_top(10)
    box.set_margin_bottom(10)

    # Title
    title_label = Gtk.Label()
    title_label.set_markup("<big><b>Pool Registry</b></big>")
    title_label.set_halign(Gtk.Align.START)
    # --- Top section: Pool Registry ---
    top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

    top_box.pack_start(title_label, False, False, 0)

    desc_label = Gtk.Label(
        label="Authoritative list of known pools, compared with live status. "
              "Pools in red are online but not added."
    )
    desc_label.set_halign(Gtk.Align.START)
    desc_label.set_line_wrap(True)
    desc_label.set_selectable(True)
    top_box.pack_start(desc_label, False, False, 0)

    top_box.pack_start(Gtk.Separator(), False, False, 0)

    # Pool table
    app.pool_store = Gtk.ListStore(
        str, str, str, str, str, str, str, str, str, str, bool
    )
    app.pool_view = Gtk.TreeView(model=app.pool_store)
    app.pool_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.pool_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    # Pool name — colored by registration state
    name_renderer = Gtk.CellRendererText()
    name_col = Gtk.TreeViewColumn("Pool", name_renderer, text=COL_NAME)
    name_col.set_cell_data_func(name_renderer, _pool_name_cell_func)
    configure_treeview_column(name_col, width=120)
    name_col.set_clickable(True)
    name_col.connect("clicked", _on_pool_column_clicked, app, COL_NAME)
    app.pool_view.append_column(name_col)

    # Offsite candidate checkbox (registered pools only)
    offsite_renderer = Gtk.CellRendererToggle()
    offsite_renderer.connect("toggled", _on_offsite_toggled, app)
    offsite_col = Gtk.TreeViewColumn(
        "Offsite", offsite_renderer, active=COL_OFFSITE
    )
    offsite_col.set_cell_data_func(
        offsite_renderer, _pool_offsite_cell_func
    )
    configure_treeview_column(offsite_col, width=55)
    app.pool_view.append_column(offsite_col)

    # Health — replaces the removed Status column at position 1
    health_renderer = Gtk.CellRendererText()
    health_col = Gtk.TreeViewColumn("Health", health_renderer, text=COL_HEALTH)
    health_col.set_cell_data_func(health_renderer, _pool_health_cell_func)
    configure_treeview_column(health_col, width=80)
    health_col.set_clickable(True)
    health_col.connect("clicked", _on_pool_column_clicked, app, COL_HEALTH)
    app.pool_view.append_column(health_col)

    # Numeric columns — narrower, right-aligned headings and cells
    numeric_cols = [
        ("Size",    COL_SIZE,    55),
        ("Alloc",   COL_ALLOC,   55),
        ("Free",    COL_FREE,    55),
        ("Freeing", COL_FREEING, 50),
        ("Ckpoint", COL_CKPOINT, 50),
        ("Frag",    COL_FRAG,    45),
        ("Cap",     COL_CAP,     45),
    ]
    for title, col_idx, width in numeric_cols:
        renderer = Gtk.CellRendererText()
        renderer.set_property("xalign", 1.0)
        col = Gtk.TreeViewColumn(title, renderer, text=col_idx)
        col.set_alignment(1.0)            # right-align the header
        configure_treeview_column(col, width=width)
        col.set_clickable(True)
        col.connect("clicked", _on_pool_column_clicked, app, col_idx)
        if col_idx in (COL_FRAG, COL_CAP):
            app.pool_store.set_sort_func(col_idx, _percent_sort_func, col_idx)
        else:
            app.pool_store.set_sort_func(col_idx, _numeric_sort_func, col_idx)
        app.pool_view.append_column(col)

    app.enable_treeview_copy(app.pool_view)
    app._ui_state.bind_treeview(app.pool_view, "pools_pool_view")

    # Enable drag-and-drop reordering; disable while sorted
    app.pool_view.set_reorderable(True)
    app.pool_store.connect(
        "sort-column-changed", _on_pools_sort_column_changed, app
    )
    app.pool_view.connect("drag-end", _on_pools_drag_end, app)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.add(app.pool_view)
    setup_row_scroll(scrolled, app.pool_view)
    top_box.pack_start(scrolled, True, True, 0)

    # Summary + dirty indicator
    app.pool_summary_label = Gtk.Label()
    app.pool_summary_label.set_halign(Gtk.Align.START)
    top_box.pack_start(app.pool_summary_label, False, False, 0)

    app.pools_dirty_label = Gtk.Label()
    app.pools_dirty_label.set_halign(Gtk.Align.START)
    top_box.pack_start(app.pools_dirty_label, False, False, 0)

    # Track offsite candidates for comparison during refresh
    app._offsite_candidates = set(get_offsite_candidate_names(app.config))

    # Load status data
    refresh_pools_page(app)

    # --- Bottom section: Scrub Manager ---
    bottom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

    scrub_title = Gtk.Label()
    scrub_title.set_markup("<big><b>Scrub Manager</b></big>")
    scrub_title.set_halign(Gtk.Align.START)
    bottom_box.pack_start(scrub_title, False, False, 0)

    # Controls — stacked vertically so the window can shrink narrow
    controls_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    controls_box.set_halign(Gtk.Align.START)

    scrub_cfg = get_scrub_manager_config(app.config)

    # Row 1: Simultaneous scrubs
    sim_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    sim_box.pack_start(Gtk.Label(label="Simultaneous scrubs:"), False, False, 0)
    app._scrub_sim_spin = Gtk.SpinButton()
    app._scrub_sim_spin.set_range(1, 10)
    app._scrub_sim_spin.set_increments(1, 1)
    app._scrub_sim_spin.set_value(scrub_cfg.get("simultaneous", 1))
    app._scrub_sim_spin.connect("value-changed", _on_scrub_sim_changed, app)
    sim_box.pack_start(app._scrub_sim_spin, False, False, 0)
    controls_box.pack_start(sim_box, False, False, 0)

    # Row 2: Refresh interval
    ref_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    ref_box.pack_start(Gtk.Label(label="Refresh every (s):"), False, False, 0)
    app._scrub_ref_spin = Gtk.SpinButton()
    app._scrub_ref_spin.set_range(1, 300)
    app._scrub_ref_spin.set_increments(1, 10)
    app._scrub_ref_spin.set_value(scrub_cfg.get("refresh_seconds", 10))
    app._scrub_ref_spin.connect("value-changed", _on_scrub_ref_changed, app)
    ref_box.pack_start(app._scrub_ref_spin, False, False, 0)
    controls_box.pack_start(ref_box, False, False, 0)

    # Row 3: Checkbuttons
    check_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    app._scrub_weekly_check = Gtk.CheckButton(label="System weekly scrub")
    app._scrub_weekly_check.set_active(scrub_cfg.get("system_scrub_weekly", False))
    app._scrub_weekly_check.connect("toggled", _on_scrub_weekly_toggled, app)
    check_box.pack_start(app._scrub_weekly_check, False, False, 0)

    app._scrub_monthly_check = Gtk.CheckButton(label="System monthly scrub")
    app._scrub_monthly_check.set_active(scrub_cfg.get("system_scrub_monthly", False))
    app._scrub_monthly_check.connect("toggled", _on_scrub_monthly_toggled, app)
    check_box.pack_start(app._scrub_monthly_check, False, False, 0)
    controls_box.pack_start(check_box, False, False, 0)

    bottom_box.pack_start(controls_box, False, False, 0)

    # Scrub summary label
    app.scrub_summary_label = Gtk.Label()
    app.scrub_summary_label.set_halign(Gtk.Align.START)
    bottom_box.pack_start(app.scrub_summary_label, False, False, 0)

    # Scrub table
    app.scrub_store = Gtk.ListStore(str, str, str, str, str)
    app.scrub_view = Gtk.TreeView(model=app.scrub_store)
    app.scrub_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.scrub_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    for col_idx, title_text, width in [
        (0, "Pool", 90),
        (1, "Status", 70),
        (2, "Progress", 65),
        (3, "Last Scrub", 130),
        (4, "Scan Line", 150),
    ]:
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
        if col_idx == 3:
            set_monospace_font(r)
        col = Gtk.TreeViewColumn(title_text, r, text=col_idx)
        configure_treeview_column(col, width=width)
        app.scrub_view.append_column(col)

    app.enable_treeview_copy(app.scrub_view)
    app._ui_state.bind_treeview(app.scrub_view, "pools_scrub_view")

    scrub_scrolled = Gtk.ScrolledWindow()
    scrub_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrub_scrolled.set_min_content_height(150)
    scrub_scrolled.add(app.scrub_view)
    setup_row_scroll(scrub_scrolled, app.scrub_view)
    bottom_box.pack_start(scrub_scrolled, False, False, 0)

    # Initialize scrub queue
    app.scrub_queue = ScrubQueue(target=int(scrub_cfg.get("simultaneous", 1)))

    # --- Paned divider ---
    paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
    paned.pack1(top_box, True, False)
    paned.pack2(bottom_box, False, False)
    box.pack_start(paned, True, True, 0)

    return box


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def refresh_pools_page(app):
    """Refresh the table from zpool list, preserving the known-pool order."""
    # Preserve multi-selection by pool name
    selection = app.pool_view.get_selection()
    model_sel, pathlist = selection.get_selected_rows()
    selected_names = set()
    if model_sel:
        for path in pathlist:
            tree_iter = model_sel.get_iter(path)
            selected_names.add(model_sel.get_value(tree_iter, COL_NAME))

    app.pool_store.clear()

    try:
        online_pools = {
            row["name"]: row
            for row in app.ctx.zfs_repository.list_pools_full()
        }
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error running zpool list: {e}")
        online_pools = {}

    online_count = 0
    offline_count = 0

    known_names = {p["name"] for p in app.known_pools}

    for pool in app.known_pools:
        pool_name = pool["name"]
        is_candidate = pool.get("offsite_candidate", False)
        if pool_name in online_pools:
            p = online_pools[pool_name]
            app.pool_store.append([
                pool_name, p['health'], p['size'], p['alloc'], p['free'],
                p['freeing'], p['ckpoint'], p['frag'], p['cap'],
                FLAG_REGISTERED, is_candidate,
            ])
            online_count += 1
        else:
            app.pool_store.append([
                pool_name, "OFFLINE", "-", "-", "-", "-", "-", "-", "-",
                FLAG_REGISTERED, is_candidate,
            ])
            offline_count += 1

    # Unregistered pools (online but not in the registry)
    for pool_name, p in online_pools.items():
        if pool_name not in known_names:
            app.pool_store.append([
                pool_name, p['health'], p['size'], p['alloc'], p['free'],
                p['freeing'], p['ckpoint'], p['frag'], p['cap'],
                FLAG_UNREGISTERED, False,
            ])
            log_msg(
                f"WARN: Pool '{pool_name}' is online but not in the pool registry"
            )

    total = len(app.known_pools)
    app.pool_summary_label.set_text(
        f"{total} registered pools: {online_count} online, {offline_count} offline"
    )
    _update_pools_dirty_indicator(app)

    # Restore multi-selection
    if selected_names:
        tree_iter = app.pool_store.get_iter_first()
        while tree_iter:
            name = app.pool_store.get_value(tree_iter, COL_NAME)
            if name in selected_names:
                path = app.pool_store.get_path(tree_iter)
                selection.select_path(path)
            tree_iter = app.pool_store.iter_next(tree_iter)


# ---------------------------------------------------------------------------
# Cell data functions
# ---------------------------------------------------------------------------

def _pool_offsite_cell_func(column, renderer, model, tree_iter, data=None):
    """Enable the Offsite checkbox only for registered pools."""
    flag = model.get_value(tree_iter, COL_FLAG)
    renderer.set_property("activatable", flag == FLAG_REGISTERED)


def _pool_name_cell_func(column, renderer, model, tree_iter, data=None):
    """Color the Pool column by registration state."""
    flag = model.get_value(tree_iter, COL_FLAG)
    health = model.get_value(tree_iter, COL_HEALTH)
    if flag == FLAG_UNREGISTERED:
        renderer.set_property("foreground", "#F44336")   # red
        renderer.set_property("weight", Pango.Weight.BOLD)
    elif health == "OFFLINE":
        renderer.set_property("foreground", "#FF9800")   # orange
        renderer.set_property("weight", Pango.Weight.NORMAL)
    else:
        renderer.set_property("foreground", None)
        renderer.set_property("weight", Pango.Weight.NORMAL)


def _pool_health_cell_func(column, renderer, model, tree_iter, data=None):
    """Color the Health column based on value."""
    health = model.get_value(tree_iter, COL_HEALTH)
    if health == "ONLINE":
        renderer.set_property("foreground", "#4CAF50")
        renderer.set_property("weight", Pango.Weight.BOLD)
    elif health == "DEGRADED":
        renderer.set_property("foreground", "#FF9800")
        renderer.set_property("weight", Pango.Weight.BOLD)
    elif health == "OFFLINE":
        renderer.set_property("foreground", "#FF9800")
        renderer.set_property("weight", Pango.Weight.NORMAL)
    elif health != "-":
        renderer.set_property("foreground", "#F44336")
        renderer.set_property("weight", Pango.Weight.BOLD)
    else:
        renderer.set_property("foreground", None)
        renderer.set_property("weight", Pango.Weight.NORMAL)


# ---------------------------------------------------------------------------
# Sorting / DND handlers
# ---------------------------------------------------------------------------

def _on_pool_column_clicked(col, app, col_idx):
    """Cycle sort state: ascending → descending → unsorted."""
    current_col, current_order = app.pool_store.get_sort_column_id()

    # Clear sort indicators on all columns
    for c in app.pool_view.get_columns():
        c.set_sort_indicator(False)

    if current_col == col_idx and current_order == Gtk.SortType.ASCENDING:
        # Ascending → descending
        app.pool_store.set_sort_column_id(col_idx, Gtk.SortType.DESCENDING)
        col.set_sort_indicator(True)
        col.set_sort_order(Gtk.SortType.DESCENDING)
    elif current_col == col_idx and current_order == Gtk.SortType.DESCENDING:
        # Descending → unsorted
        app.pool_store.set_sort_column_id(
            Gtk.TREE_SORTABLE_UNSORTED_SORT_COLUMN_ID, Gtk.SortType.ASCENDING
        )
        col.set_sort_indicator(False)
    else:
        # Unsorted or different column → ascending
        app.pool_store.set_sort_column_id(col_idx, Gtk.SortType.ASCENDING)
        col.set_sort_indicator(True)
        col.set_sort_order(Gtk.SortType.ASCENDING)


def _on_pools_sort_column_changed(model, app):
    """Disable DND while the model is sorted; re-enable when unsorted."""
    sort_col_id, _order = model.get_sort_column_id()
    app.pool_view.set_reorderable(sort_col_id is None)


def _select_pool_by_name(treeview, pool_name):
    """Select the row matching *pool_name* and scroll it into view."""
    model = treeview.get_model()
    tree_iter = model.get_iter_first()
    while tree_iter:
        if model.get_value(tree_iter, COL_NAME) == pool_name:
            path = model.get_path(tree_iter)
            treeview.get_selection().select_path(path)
            treeview.scroll_to_cell(path, None, False, 0.0, 0.0)
            break
        tree_iter = model.iter_next(tree_iter)


def _on_pools_drag_end(treeview, drag_context, app):
    """After a DND reorder, rebuild known_pools from the store order."""
    model = treeview.get_model()
    new_order = []
    name_to_pool = {p["name"]: p for p in app.known_pools}
    tree_iter = model.get_iter_first()
    while tree_iter:
        flag = model.get_value(tree_iter, COL_FLAG)
        if flag == FLAG_REGISTERED:
            name = model.get_value(tree_iter, COL_NAME)
            new_order.append(name_to_pool.get(name, {"name": name}))
        tree_iter = model.iter_next(tree_iter)

    if new_order == app.known_pools:
        return

    # Preserve selection
    selection = treeview.get_selection()
    selected_pool = None
    model_sel, sel_iter = selection.get_selected()
    if sel_iter:
        selected_pool = model_sel.get_value(sel_iter, COL_NAME)

    app.known_pools = new_order
    refresh_pools_page(app)

    if selected_pool:
        _select_pool_by_name(treeview, selected_pool)


def _on_offsite_toggled(renderer, path, app):
    """Toggle the offsite_candidate flag for a registered pool."""
    tree_iter = app.pool_store.get_iter(path)
    if not tree_iter:
        return
    flag = app.pool_store.get_value(tree_iter, COL_FLAG)
    if flag != FLAG_REGISTERED:
        return
    name = app.pool_store.get_value(tree_iter, COL_NAME)
    old_value = app.pool_store.get_value(tree_iter, COL_OFFSITE)
    new_value = not old_value
    app.pool_store.set_value(tree_iter, COL_OFFSITE, new_value)

    for pool in app.known_pools:
        if pool["name"] == name:
            pool["offsite_candidate"] = new_value
            break

    _update_pools_dirty_indicator(app)


# ---------------------------------------------------------------------------
# Edit + dirty state
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Scrub Manager refresh + controls
# ---------------------------------------------------------------------------

def refresh_scrub_table(app):
    """Update the scrub table with current zpool status.

    Uses a flicker-free strategy: update existing rows in-place, and only
    add/remove rows when the pool list changes.
    """
    states = get_all_pool_scrub_states()
    queue = app.scrub_queue

    # Reconcile queue against live states
    queue.tick(states)

    # Build new data map
    new_data = {}
    for pool_name, info in states.items():
        qstate = queue.state_for_pool(pool_name)
        display_state = qstate.value if qstate != ScrubState.NONE else info.state.value
        if display_state == "scanning":
            display_state = "scrubbing"
        progress = f"{info.progress_percent:.1f}%" if info.progress_percent is not None else "—"
        last = info.last_scrub or "—"
        scan = info.scan_line or "—"
        new_data[pool_name] = [pool_name, display_state, progress, last, scan]

    # Update existing rows in place
    existing = {}
    tree_iter = app.scrub_store.get_iter_first()
    while tree_iter:
        name = app.scrub_store.get_value(tree_iter, 0)
        existing[name] = tree_iter
        tree_iter = app.scrub_store.iter_next(tree_iter)

    # Remove rows for pools that no longer exist
    for name, tree_iter in list(existing.items()):
        if name not in new_data:
            app.scrub_store.remove(tree_iter)
            del existing[name]

    # Update or add rows
    for pool_name in sorted(new_data.keys()):
        row = new_data[pool_name]
        if pool_name in existing:
            tree_iter = existing[pool_name]
            for col_idx, val in enumerate(row):
                if app.scrub_store.get_value(tree_iter, col_idx) != val:
                    app.scrub_store.set_value(tree_iter, col_idx, val)
        else:
            app.scrub_store.append(row)

    # Update summary label
    summary = queue.summary()
    parts = []
    if summary["active"]:
        parts.append(f"{summary['active']} scrubbing")
    if summary["pending"]:
        parts.append(f"{summary['pending']} pending")
    if summary["paused"]:
        parts.append(f"{summary['paused']} paused")
    if parts:
        app.scrub_summary_label.set_text(
            f"Queue: {', '.join(parts)} (target: {summary['target']})"
        )
    else:
        app.scrub_summary_label.set_text("Queue: idle")


def schedule_scrub_refresh_burst(app, count=3, interval=2):
    """Schedule *count* extra scrub refreshes every *interval* seconds.

    Gives quick visual feedback after scrub actions, even when the user has
    configured a long refresh interval.
    """
    def _burst_tick(remaining):
        if remaining <= 0:
            return False
        if app.stack.get_visible_child_name() == "pools":
            refresh_scrub_table(app)
        GLib.timeout_add_seconds(interval, _burst_tick, remaining - 1)
        return False

    GLib.timeout_add_seconds(interval, _burst_tick, count)


def _on_scrub_sim_changed(spin, app):
    val = int(spin.get_value())
    app.scrub_queue.set_target(val)
    cfg = get_scrub_manager_config(app.config)
    cfg["simultaneous"] = val
    save_scrub_manager_config(app.config, cfg)


def _on_scrub_ref_changed(spin, app):
    val = int(spin.get_value())
    cfg = get_scrub_manager_config(app.config)
    cfg["refresh_seconds"] = val
    save_scrub_manager_config(app.config, cfg)
    # Timer will pick up new interval on next restart


def _on_scrub_weekly_toggled(check, app):
    active = check.get_active()
    cfg = get_scrub_manager_config(app.config)
    cfg["system_scrub_weekly"] = active
    save_scrub_manager_config(app.config, cfg)
    # Apply to all known pools
    pools = get_pool_names(app.config)
    if pools:
        sync_system_scrub_for_pools(
            pools,
            active,
            cfg.get("system_scrub_monthly", False),
        )
    log_msg(f"INFO: System weekly scrub {'enabled' if active else 'disabled'}")


def _on_scrub_monthly_toggled(check, app):
    active = check.get_active()
    cfg = get_scrub_manager_config(app.config)
    cfg["system_scrub_monthly"] = active
    save_scrub_manager_config(app.config, cfg)
    pools = get_pool_names(app.config)
    if pools:
        sync_system_scrub_for_pools(
            pools,
            cfg.get("system_scrub_weekly", False),
            active,
        )
    log_msg(f"INFO: System monthly scrub {'enabled' if active else 'disabled'}")


def get_selected_pool_names(treeview, name_col_idx=0):
    """Return a list of pool names for all selected rows in a TreeView."""
    selection = treeview.get_selection()
    model, pathlist = selection.get_selected_rows()
    names = []
    for path in pathlist:
        tree_iter = model.get_iter(path)
        names.append(model.get_value(tree_iter, name_col_idx))
    return names


# ---------------------------------------------------------------------------
# Edit + dirty state
# ---------------------------------------------------------------------------

def _update_pools_dirty_indicator(app):
    app.pools_dirty = app.known_pools != app._pools_saved_state
    if app.pools_dirty:
        app.pools_dirty_label.set_markup(
            "<small><i>Unsaved changes</i></small>"
        )
    else:
        app.pools_dirty_label.set_text("")
    btn = getattr(app, '_pools_save_button', None)
    if btn:
        set_button_markup_red(btn, app.pools_dirty)
