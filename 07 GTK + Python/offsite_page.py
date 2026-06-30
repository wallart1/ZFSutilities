"""
Offsite Backup tab UI — builds the Offsite page widget and handles interaction.

Mirrors the pattern of backup_page.py but tailored for the zfssendoffsite workflow:
no rsync pull steps, per-step includes/excludes, offsite pool discovery, and
optional ZFS hold application.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from logging_config import log_msg
from feature_config import (
    get_offsite_config, generate_offsite_snapshot_name,
    save_offsite_config, get_offsite_candidate_names,
    _read_snapfile, OFFSITE_SNAPFILE,
)
from offsite_runner import detect_offsite_pool, build_offsite_step_command
from scrub_manager import attach_step_scrub_callbacks
from gui_helpers import (
    setup_row_scroll,
    set_button_markup_red, DirtyTracker, add_var_row,
    handle_editing_key_press, on_toggle, on_cell_edited,
    on_row_activated,
    configure_treeview_column, ACTIVE_COLUMN_WIDTH,
    bold_label,
)

OFFSITE_DATASET_VARIABLES = ["includes", "excludes", "startwith", "endwith"]
OFFSITE_VARIABLES = ["applyholds", "doincrementals", "dointermediates",
                     "allow_destructive", "receive_F_option",
                     "verify_after_transfer", "pv_rate_limit"]
OFFSITE_YN_VARIABLES = {"applyholds", "doincrementals", "dointermediates",
                        "allow_destructive",
                        "verify_after_transfer"}
_OFFSITE_TOPIC_MAP = {
    "includes": "offsite_includes",
    "excludes": "offsite_excludes",
    "startwith": "offsite_startwith",
    "endwith": "offsite_endwith",
    "applyholds": "offsite_applyholds",
    "doincrementals": "backup_doincrementals",
    "dointermediates": "backup_dointermediates",
    "allow_destructive": "backup_allow_destructive",
    "receive_F_option": "backup_receive_F_option",
    "verify_after_transfer": "offsite_verify_after_transfer",
    "pv_rate_limit": "backup_pv_rate_limit",
}
_EDITABLE_COLS = [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def create_offsite_page(app, ctx):
    """Build and return the full Offsite Backup tab widget."""
    offsite_cfg = get_offsite_config(ctx.config)
    variables = offsite_cfg["variables"]

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(10)
    box.set_margin_end(10)
    box.set_margin_top(10)
    box.set_margin_bottom(10)
    scrolled.add(box)

    # Title
    title = Gtk.Label()
    title.set_markup("<big><b>Offsite Backup</b></big>")
    title.set_halign(Gtk.Align.START)
    box.pack_start(title, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 0)

    app.offsite_var_widgets = {}

    # --- Offsite Pool frame ---
    pool_frame = Gtk.Frame()
    pool_frame.set_label_widget(bold_label("Offsite Pool"))
    pool_grid = Gtk.Grid()
    pool_grid.set_row_spacing(5)
    pool_grid.set_column_spacing(10)
    pool_grid.set_margin_start(10)
    pool_grid.set_margin_end(10)
    pool_grid.set_margin_top(5)
    pool_grid.set_margin_bottom(5)
    pool_frame.add(pool_grid)
    box.pack_start(pool_frame, False, False, 0)

    lbl_det = Gtk.Label(label="Detected pool")
    lbl_det.set_halign(Gtk.Align.END)
    pool_grid.attach(lbl_det, 0, 0, 1, 1)

    app.offsite_detected_label = Gtk.Label(label="(not checked)")
    app.offsite_detected_label.set_halign(Gtk.Align.START)
    app.offsite_detected_label.set_selectable(True)
    pool_grid.attach(app.offsite_detected_label, 1, 0, 1, 1)

    # Auto-detect offsite pool from candidates defined in the Pools tab.
    do_detect_offsite_pool(app)

    # --- Advanced expander ---
    adv_exp = Gtk.Expander()
    adv_exp.set_label_widget(bold_label("Advanced"))
    adv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    adv_box.set_margin_start(10)
    adv_box.set_margin_end(10)
    adv_box.set_margin_top(5)
    adv_box.set_margin_bottom(5)
    adv_exp.add(adv_box)
    box.pack_start(adv_exp, False, False, 0)

    # Dataset Selection subsection
    ds_frame = Gtk.Frame()
    ds_frame.set_label_widget(bold_label("Dataset Selection"))
    ds_grid = Gtk.Grid()
    ds_grid.set_row_spacing(5)
    ds_grid.set_column_spacing(10)
    ds_grid.set_margin_start(10)
    ds_grid.set_margin_end(10)
    ds_grid.set_margin_top(5)
    ds_grid.set_margin_bottom(5)
    ds_frame.add(ds_grid)
    adv_box.pack_start(ds_frame, False, False, 0)

    for i, key in enumerate(OFFSITE_DATASET_VARIABLES):
        add_var_row(ds_grid, i, key, variables, app.offsite_var_widgets,
                    yn_vars=OFFSITE_YN_VARIABLES, topic_map=_OFFSITE_TOPIC_MAP)

    adv_grid = Gtk.Grid()
    adv_grid.set_row_spacing(5)
    adv_grid.set_column_spacing(10)
    adv_box.pack_start(adv_grid, False, False, 0)

    for i, key in enumerate(OFFSITE_VARIABLES):
        add_var_row(adv_grid, i, key, variables, app.offsite_var_widgets,
                    yn_vars=OFFSITE_YN_VARIABLES, topic_map=_OFFSITE_TOPIC_MAP)

    app.offsite_pause_scrubs = Gtk.CheckButton(
        label="Pause scrubs on source/destination pools during each step"
    )
    app.offsite_pause_scrubs.set_active(
        offsite_cfg.get("pause_scrubs", False)
    )
    app.offsite_pause_scrubs.set_tooltip_text(
        "Pause ZFS scrubs on the pools used by each offsite step "
        "while that step is running."
    )
    adv_box.pack_start(app.offsite_pause_scrubs, False, False, 0)

    # --- Snapshot frame ---
    snap_frame = Gtk.Frame()
    snap_frame.set_label_widget(bold_label("Snapshot"))
    snap_grid = Gtk.Grid()
    snap_grid.set_row_spacing(5)
    snap_grid.set_column_spacing(10)
    snap_grid.set_margin_start(10)
    snap_grid.set_margin_end(10)
    snap_grid.set_margin_top(5)
    snap_grid.set_margin_bottom(5)
    snap_frame.add(snap_grid)
    box.pack_start(snap_frame, False, False, 0)

    app.offsite_nextsnap_label = Gtk.Label(label="nextsnap")
    app.offsite_nextsnap_label.set_halign(Gtk.Align.END)
    snap_grid.attach(app.offsite_nextsnap_label, 0, 0, 1, 1)

    snap_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    app.offsite_nextsnap_entry = Gtk.Entry()
    app.offsite_nextsnap_entry.set_hexpand(True)
    app.offsite_nextsnap_entry.set_width_chars(1)
    snap_box.pack_start(app.offsite_nextsnap_entry, True, True, 0)

    gen_btn = Gtk.Button(label="Generate")
    gen_btn.connect("clicked", lambda _b, a=app: _do_generate_snap(a))
    snap_box.pack_start(gen_btn, False, False, 0)
    snap_grid.attach(snap_box, 1, 0, 1, 1)

    # Inline: read previously saved offsite snapshot name from disk
    saved = _read_snapfile(OFFSITE_SNAPFILE)
    if saved:
        app.offsite_nextsnap_entry.set_text(saved)
        app.offsite_nextsnap_label.set_text("nextsnap (previous)")
        log_msg(f"INFO: Offsite: previous snapshot name found: {saved}")
    else:
        _do_generate_snap(app)

    # --- Send/Receive Steps ---
    sr_frame = Gtk.Frame()
    sr_frame.set_label_widget(bold_label("Send/Receive Steps"))
    sr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    sr_box.set_margin_start(10)
    sr_box.set_margin_end(10)
    sr_box.set_margin_top(5)
    sr_box.set_margin_bottom(5)
    sr_frame.add(sr_box)
    box.pack_start(sr_frame, False, False, 0)

    # ListStore: active(bool), source, dest, includes, excludes
    app.offsite_step_store = Gtk.ListStore(bool, str, str, str, str)
    step_view = Gtk.TreeView(model=app.offsite_step_store)
    step_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

    toggle_r = Gtk.CellRendererToggle()
    toggle_r.connect("toggled", on_toggle, app.offsite_step_store)
    col_active = Gtk.TreeViewColumn("Active", toggle_r, active=0)
    configure_treeview_column(col_active, width=ACTIVE_COLUMN_WIDTH,
                              min_width=ACTIVE_COLUMN_WIDTH)
    step_view.append_column(col_active)

    col_defs = [
        (1, "Source", 110),
        (2, "Destination", 110),
        (3, "Includes", 140),
        (4, "Excludes", 110),
    ]
    for col_idx, col_title, width in col_defs:
        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", True)
        renderer.connect("edited", on_cell_edited, app.offsite_step_store, col_idx)
        renderer.connect("editing-started", _on_editing_started, step_view, col_idx)
        col = Gtk.TreeViewColumn(col_title, renderer, text=col_idx)
        configure_treeview_column(col, width=width)
        step_view.append_column(col)

    step_view.connect("row-activated", on_row_activated, 1)
    step_view.set_reorderable(True)
    app.offsite_step_view = step_view
    app._ui_state.bind_treeview(app.offsite_step_view, "offsite_steps_view")

    step_scroll = Gtk.ScrolledWindow()
    step_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    step_scroll.set_min_content_height(140)
    step_scroll.add(step_view)
    setup_row_scroll(step_scroll, step_view)
    sr_box.pack_start(step_scroll, True, True, 0)

    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    for label, cb in [("Add", _on_step_add), ("Remove", _on_step_remove)]:
        btn = Gtk.Button(label=label)
        btn.connect("clicked", cb, app)
        btn_box.pack_start(btn, False, False, 0)
    sr_box.pack_start(btn_box, False, False, 0)

    for step in offsite_cfg["steps"]:
        app.offsite_step_store.append([
            step["active"], step["source"], step["dest"],
            step.get("includes", ""), step.get("excludes", ""),
        ])

    tracker = DirtyTracker(app, lambda: collect_offsite_config(app),
                           "_offsite_save_button")
    app._offsite_tracker = tracker
    for widget in app.offsite_var_widgets.values():
        widget.connect("changed", lambda _w, t=tracker: t.check())
    app.offsite_step_store.connect(
        "row-changed", lambda _m, _p, _i, t=tracker: t.check())
    app.offsite_step_store.connect(
        "row-inserted", lambda _m, _p, _i, t=tracker: t.check())
    app.offsite_step_store.connect(
        "row-deleted", lambda _m, _p, t=tracker: t.check())
    app.offsite_pause_scrubs.connect(
        "toggled", lambda _w, t=tracker: t.check())

    return scrolled


# ---------------------------------------------------------------------------
# Config snapshot helpers
# ---------------------------------------------------------------------------

def collect_offsite_config(app):
    """Collect current offsite UI state into a config dict."""
    variables = {}
    for key, widget in app.offsite_var_widgets.items():
        if isinstance(widget, Gtk.ComboBoxText):
            variables[key] = widget.get_active_text() or "Y"
        else:
            variables[key] = widget.get_text()

    # Candidate pools are now maintained in the Pools tab registry.
    offsite_pools = get_offsite_candidate_names(app.ctx.config)

    steps = []
    for row in app.offsite_step_store:
        steps.append({
            "active": row[0],
            "source": row[1],
            "dest": row[2],
            "includes": row[3],
            "excludes": row[4],
        })

    return {
        "variables": variables,
        "offsite_pools": offsite_pools,
        "steps": steps,
        "pause_scrubs": app.offsite_pause_scrubs.get_active(),
    }


def check_offsite_dirty(app):
    """Compare current UI state to last-saved state; style Save button."""
    if hasattr(app, '_offsite_tracker'):
        app._offsite_tracker.check()


def mark_offsite_clean(app):
    """Call after saving to update saved state and reset the button."""
    if hasattr(app, '_offsite_tracker'):
        app._offsite_tracker.mark_clean()


def load_offsite_config(app, config):
    """Load an offsite config dict into the UI widgets."""
    for key, widget in app.offsite_var_widgets.items():
        val = config.get("variables", {}).get(key, "")
        if isinstance(widget, Gtk.ComboBoxText):
            widget.set_active(0 if val == "Y" else 1)
        else:
            widget.set_text(val)

    # Candidate pools are maintained in the Pools tab; refresh detection.
    do_detect_offsite_pool(app)

    app.offsite_step_store.clear()
    for step in config.get("steps", []):
        app.offsite_step_store.append([
            step["active"], step["source"], step["dest"],
            step.get("includes", ""), step.get("excludes", ""),
        ])
    app.offsite_pause_scrubs.set_active(config.get("pause_scrubs", False))


def revert_offsite_config(app):
    """Restore all offsite UI widgets to the last-saved state."""
    if hasattr(app, '_offsite_tracker'):
        app._offsite_tracker.revert(lambda cfg: load_offsite_config(app, cfg))


def _do_generate_snap(app):
    """Generate a new offsite snapshot name, update entry and label."""
    snap = generate_offsite_snapshot_name()
    app.offsite_nextsnap_entry.set_text(snap)
    app.offsite_nextsnap_label.set_text("nextsnap (new)")
    log_msg(f"INFO: Offsite: new snapshot name: {snap}")


def do_detect_offsite_pool(app):
    """Detect online offsite pool and update the UI label.

    Candidates are read from the pool registry (Pools tab).

    Returns the detected pool name or None.
    """
    candidates = get_offsite_candidate_names(app.ctx.config)
    if not candidates:
        app.offsite_detected_label.set_text("(no candidates configured)")
        return None
    pool = detect_offsite_pool(candidates)
    if pool:
        app.offsite_detected_label.set_markup(f"<b>{pool}</b>")
    else:
        app.offsite_detected_label.set_text(
            f"(none online; looked for: {', '.join(candidates)})"
        )
    return pool


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------

def _on_editing_started(renderer, editable, path, treeview, col_idx):
    """Connect key-press on the editable to handle Tab/Shift+Tab."""
    editable.connect("key-press-event", handle_editing_key_press,
                     treeview, path, col_idx, _EDITABLE_COLS)


def _on_step_add(button, app):
    tree_iter = app.offsite_step_store.append([True, "", "", "", ""])
    # Inline: place cursor into the new row's cell for editing after a short delay
    model = app.offsite_step_view.get_model()
    path = model.get_path(tree_iter)
    col = app.offsite_step_view.get_column(1)
    GLib.idle_add(app.offsite_step_view.set_cursor, path, col, True)


def _on_step_remove(button, app):
    sel = app.offsite_step_view.get_selection()
    model, tree_iter = sel.get_selected()
    if tree_iter:
        model.remove(tree_iter)


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def on_offsite_run(app, ctx):
    """Build step list and start offsite backup execution."""
    app.clear_log_status()
    if app.backup_runner and app.backup_runner.running:
        log_msg("WARN: Cannot start offsite backup while daily backup is running")
        return
    if app.restore_runner and app.restore_runner.running:
        log_msg("WARN: Cannot start offsite backup while restore is running")
        return

    nextsnap = app.offsite_nextsnap_entry.get_text().strip()
    if not nextsnap:
        log_msg("WARN: Generate or enter a snapshot name first")
        return

    if nextsnap[0] != '@':
        nextsnap = '@' + nextsnap
        app.offsite_nextsnap_entry.set_text(nextsnap)

    offsite_pool = do_detect_offsite_pool(app)
    if offsite_pool is None:
        log_msg("FATAL: No offsite pool online. Cannot proceed.")
        return

    while True:
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            text=f"New snapshot: {nextsnap}",
        )
        dialog.format_secondary_text(
            f"Offsite pool: {offsite_pool}\nProceed with offsite backup?"
        )
        dialog.add_button("Generate", Gtk.ResponseType.APPLY)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            break
        if response == Gtk.ResponseType.APPLY:
            _do_generate_snap(app)
            nextsnap = app.offsite_nextsnap_entry.get_text().strip()
            continue
        log_msg("INFO: Offsite backup cancelled")
        return

    app.offsite_runner.prepare_session_log()

    offsite_cfg = collect_offsite_config(app)
    variables = offsite_cfg["variables"]
    dryrun = getattr(app, '_dry_run_active', False)

    if dryrun:
        log_msg("INFO: Dry run mode enabled — no changes will be made")

    steps = []
    pause_scrubs = offsite_cfg.get("pause_scrubs", False)
    for step in offsite_cfg["steps"]:
        if not step["active"]:
            continue
        source = step["source"]
        dest = step["dest"].replace("<offsite>", offsite_pool)
        includes = step.get("includes", "")
        excludes = step.get("excludes", "")

        offsite_step = build_offsite_step_command(
            source, dest, variables, ctx.parent_dir, nextsnap,
            includes, excludes,
            dryrun=dryrun,
        )
        attach_step_scrub_callbacks(
            offsite_step, source, dest,
            enabled=pause_scrubs, dry_run=dryrun,
        )
        steps.append(offsite_step)

    if not steps:
        log_msg("WARN: No active steps to run")
        return

    log_msg(f"INFO: Snapshot: {nextsnap}")
    app.offsite_runner.set_steps(steps)
    app.offsite_runner.start(on_complete=lambda cancelled=False: _on_offsite_complete(app, cancelled))
    app.update_action_buttons("offsite")


def _on_offsite_complete(app, cancelled=False):
    """Called when offsite backup finishes or is cancelled."""
    app.update_action_buttons("offsite")


def on_offsite_cancel(app, ctx):
    """Cancel the running offsite backup."""
    if app.offsite_runner:
        app.offsite_runner.cancel()
    app.update_action_buttons("offsite")


def on_offsite_save(app, ctx):
    """Save current offsite config to JSON."""
    offsite_data = collect_offsite_config(app)
    try:
        save_offsite_config(ctx.config, offsite_data)
        mark_offsite_clean(app)
        log_msg("INFO: Offsite config saved to /root/.config/zfsutilities.json")
    except OSError as e:
        log_msg(f"WARN: Error saving config: {e}")


def on_offsite_revert(app, ctx):
    """Revert offsite UI to last-saved state."""
    if not hasattr(app, '_offsite_saved_state'):
        log_msg("INFO: Nothing to revert")
        return
    revert_offsite_config(app)
    log_msg("INFO: Offsite config reverted to last saved state")


def offsite_set_all_active(app, ctx, active):
    """Set all Active checkboxes in the offsite step list."""
    tree_iter = app.offsite_step_store.get_iter_first()
    while tree_iter:
        app.offsite_step_store.set_value(tree_iter, 0, active)
        tree_iter = app.offsite_step_store.iter_next(tree_iter)
    state = "selected" if active else "deselected"
    log_msg(f"INFO: All offsite steps {state}")
