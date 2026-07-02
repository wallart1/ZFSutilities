"""
Restore tab UI — builds the Restore page widget and handles interaction.

Implements the zfsrestore workflow: a two-step process (full copy from oldest
snapshot, then incremental copy of remaining snapshots) driven from the GUI.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from logging_config import log_msg
from feature_config import (
    get_pool_names,
    get_restore_config,
    save_restore_config,
)
from restore_runner import (
    compute_auto_destination,
    compute_restore_params,
    build_restore_command,
)
from scrub_manager import attach_step_scrub_callbacks
from command_builders import BashStep
from gui_helpers import bold_label


# Advanced variables (all plain text entries)
RESTORE_ADVANCED_VARIABLES = [
    "depth", "label", "includes", "excludes", "startwith", "endwith",
]


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def create_restore_page(app, ctx):
    """Build and return the full Restore tab widget."""
    restore_cfg = get_restore_config(ctx.config)
    variables = restore_cfg["variables"]

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
    title.set_markup("<big><b>Restore</b></big>")
    title.set_halign(Gtk.Align.START)
    box.pack_start(title, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 0)

    # Store widget references on app
    app.restore_var_widgets = {}

    # --- Source and Destination ---
    sd_frame = Gtk.Frame()
    sd_frame.set_label_widget(bold_label("Source and Destination"))
    sd_grid = Gtk.Grid()
    sd_grid.set_row_spacing(5)
    sd_grid.set_column_spacing(10)
    sd_grid.set_margin_start(10)
    sd_grid.set_margin_end(10)
    sd_grid.set_margin_top(5)
    sd_grid.set_margin_bottom(5)

    src_label = Gtk.Label(label="Source Dataset")
    src_label.set_halign(Gtk.Align.END)
    sd_grid.attach(src_label, 0, 0, 1, 1)

    app.restore_source_entry = Gtk.Entry()
    app.restore_source_entry.set_text(restore_cfg.get("source", ""))
    app.restore_source_entry.set_hexpand(True)
    app.restore_source_entry.set_width_chars(1)
    app.restore_source_entry.set_tooltip_text(
        "Fully qualified source dataset, e.g. backuppool/sourcepool/data"
    )
    sd_grid.attach(app.restore_source_entry, 1, 0, 1, 1)

    dst_label = Gtk.Label(label="Dest Dataset")
    dst_label.set_halign(Gtk.Align.END)
    sd_grid.attach(dst_label, 0, 1, 1, 1)

    app.restore_dest_entry = Gtk.Entry()
    app.restore_dest_entry.set_text(restore_cfg.get("dest", ""))
    app.restore_dest_entry.set_hexpand(True)
    app.restore_dest_entry.set_width_chars(1)
    app.restore_dest_entry.set_tooltip_text(
        "Fully qualified destination dataset, e.g. sourcepool/data"
    )
    sd_grid.attach(app.restore_dest_entry, 1, 1, 1, 1)

    app.restore_auto_dest_check = Gtk.CheckButton(
        label="Auto-determine destination"
    )
    app.restore_auto_dest_check.set_active(restore_cfg.get("auto_dest", False))
    app.restore_auto_dest_check.set_tooltip_text(
        "Leave Destination blank and derive it from the source by stripping "
        "leading qualifiers until the first remaining qualifier is a known pool"
    )
    sd_grid.attach(app.restore_auto_dest_check, 1, 2, 1, 1)

    sd_frame.add(sd_grid)
    box.pack_start(sd_frame, False, False, 0)

    # --- Advanced (collapsed) ---
    adv_expander = Gtk.Expander()
    adv_expander.set_label_widget(bold_label("Advanced"))
    adv_expander.set_expanded(False)

    adv_grid = Gtk.Grid()
    adv_grid.set_row_spacing(5)
    adv_grid.set_column_spacing(10)
    adv_grid.set_margin_start(10)
    adv_grid.set_margin_end(10)
    adv_grid.set_margin_top(5)
    adv_grid.set_margin_bottom(5)

    topic_map = {
        "depth": "restore_depth",
        "label": "restore_label",
        "includes": "restore_includes",
        "excludes": "restore_excludes",
        "startwith": "restore_startwith",
        "endwith": "restore_endwith",
    }
    for row, key in enumerate(RESTORE_ADVANCED_VARIABLES):
        lbl = Gtk.Label(label=key)
        lbl.set_halign(Gtk.Align.END)
        adv_grid.attach(lbl, 0, row, 1, 1)

        entry = Gtk.Entry()
        entry.set_text(variables.get(key, ""))
        entry.set_hexpand(True)
        entry.set_width_chars(1)
        if key in ("includes", "excludes"):
            entry.set_tooltip_text("Space-separated list of substrings; prefix with = for exact match")
        adv_grid.attach(entry, 1, row, 1, 1)
        app.restore_var_widgets[key] = entry

    adv_expander.add(adv_grid)
    box.pack_start(adv_expander, False, False, 0)

    # --- Restore Steps ---
    steps_frame = Gtk.Frame()
    steps_frame.set_label_widget(bold_label("Restore Steps"))
    steps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    steps_box.set_margin_start(10)
    steps_box.set_margin_end(10)
    steps_box.set_margin_top(5)
    steps_box.set_margin_bottom(5)

    app.restore_part1_check = Gtk.CheckButton(
        label="Part 1: Full copy from oldest snapshot"
    )
    app.restore_part1_check.set_active(restore_cfg.get("do_part1", True))
    steps_box.pack_start(app.restore_part1_check, False, False, 0)

    app.restore_part2_check = Gtk.CheckButton(
        label="Part 2: Incremental copy of remaining snapshots"
    )
    app.restore_part2_check.set_active(restore_cfg.get("do_part2", True))
    steps_box.pack_start(app.restore_part2_check, False, False, 0)

    app.restore_pause_scrubs = Gtk.CheckButton(
        label="Pause scrubs on source/destination pools during each step"
    )
    app.restore_pause_scrubs.set_active(
        restore_cfg.get("pause_scrubs", False)
    )
    app.restore_pause_scrubs.set_tooltip_text(
        "Pause ZFS scrubs on the source and destination pools while the "
        "restore step is running."
    )
    steps_box.pack_start(app.restore_pause_scrubs, False, False, 0)

    steps_frame.add(steps_box)
    box.pack_start(steps_frame, False, False, 0)

    # --- Notes ---
    notes_frame = Gtk.Frame()
    notes_frame.set_label_widget(bold_label("Notes"))
    notes_label = Gtk.Label()
    notes_label.set_markup(
        "Part 1 is destructive \u2014 it will destroy existing destination "
        "datasets before restoring from the oldest snapshot. You will be "
        "prompted once to confirm the dataset list; after that, Part 1 "
        "proceeds automatically.\n\n"
        "Part 2 copies the remaining snapshots incrementally and proceeds "
        "automatically without prompting."
    )
    notes_label.set_line_wrap(True)
    notes_label.set_halign(Gtk.Align.START)
    notes_label.set_margin_start(10)
    notes_label.set_margin_end(10)
    notes_label.set_margin_top(5)
    notes_label.set_margin_bottom(5)
    notes_label.set_selectable(True)
    notes_frame.add(notes_label)
    box.pack_start(notes_frame, False, False, 0)

    # Connect signals for dirty tracking
    app.restore_source_entry.connect(
        "changed", lambda w, a=app: _on_restore_source_changed(a)
    )
    app.restore_dest_entry.connect(
        "changed", lambda w, a=app: check_restore_dirty(a)
    )
    app.restore_auto_dest_check.connect(
        "toggled", lambda w, a=app: _on_auto_dest_toggled(a)
    )
    for widget in app.restore_var_widgets.values():
        widget.connect("changed", lambda w, a=app: check_restore_dirty(a))
    app.restore_part1_check.connect(
        "toggled", lambda w, a=app: check_restore_dirty(a)
    )
    app.restore_part2_check.connect(
        "toggled", lambda w, a=app: check_restore_dirty(a)
    )
    app.restore_pause_scrubs.connect(
        "toggled", lambda w, a=app: check_restore_dirty(a)
    )

    # Apply initial sensitivity state and auto-computed destination.
    _on_auto_dest_toggled(app)

    # --- Dirty tracking ---
    app._restore_saved_state = collect_restore_config(app)

    return scrolled


# ---------------------------------------------------------------------------
# Config snapshot helpers
# ---------------------------------------------------------------------------

def collect_restore_config(app):
    """Collect current restore UI state into a config dict."""
    variables = {}
    for key, widget in app.restore_var_widgets.items():
        variables[key] = widget.get_text()

    return {
        "source": app.restore_source_entry.get_text().strip(),
        "dest": app.restore_dest_entry.get_text().strip(),
        "auto_dest": app.restore_auto_dest_check.get_active(),
        "variables": variables,
        "do_part1": app.restore_part1_check.get_active(),
        "do_part2": app.restore_part2_check.get_active(),
        "pause_scrubs": app.restore_pause_scrubs.get_active(),
    }


def check_restore_dirty(app):
    """Compare current UI state to last-saved state; style Save button."""
    current = collect_restore_config(app)
    saved = getattr(app, "_restore_saved_state", None)
    if saved is None:
        return
    dirty = current != saved
    _style_restore_save_button(app, dirty)


def mark_restore_clean(app):
    """Call after saving to update saved state and reset the button."""
    app._restore_saved_state = collect_restore_config(app)
    _style_restore_save_button(app, dirty=False)


def load_restore_config(app, config):
    """Load a restore config dict into the UI widgets."""
    app.restore_source_entry.set_text(config.get("source", ""))
    app.restore_dest_entry.set_text(config.get("dest", ""))
    app.restore_auto_dest_check.set_active(config.get("auto_dest", False))

    for key, widget in app.restore_var_widgets.items():
        widget.set_text(config.get("variables", {}).get(key, ""))

    app.restore_part1_check.set_active(config.get("do_part1", True))
    app.restore_part2_check.set_active(config.get("do_part2", True))
    app.restore_pause_scrubs.set_active(config.get("pause_scrubs", False))

    # Ensure destination entry sensitivity matches the checkbox state.
    _on_auto_dest_toggled(app)


def revert_restore_config(app):
    """Restore all restore UI widgets to the last-saved state."""
    load_restore_config(app, app._restore_saved_state)
    _style_restore_save_button(app, dirty=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _style_restore_save_button(app, dirty):
    btn = getattr(app, '_restore_save_button', None)
    if btn is None:
        return
    if dirty:
        _set_button_markup(btn, '<span foreground="red">Save Config</span>')
    else:
        _set_button_markup(btn, 'Save Config')


def refresh_restore_destination(app):
    """Recompute and install the default destination when auto is active.

    The computed destination is written into the Dest Dataset entry.  This
    is called when the page is displayed, when auto-destination is enabled,
    and when the source dataset changes while auto-destination is active.

    Returns the computed destination string, or None when auto-destination
    is disabled or the destination cannot be computed.
    """
    if not app.restore_auto_dest_check.get_active():
        return None

    source = app.restore_source_entry.get_text().strip()
    if not source:
        app.restore_dest_entry.set_text("")
        return None

    known_pools = get_pool_names(app.ctx.config)
    try:
        dest = compute_auto_destination(source, known_pools)
    except ValueError as exc:
        log_msg(f"WARN: {exc}")
        app.restore_dest_entry.set_text("")
        return None

    app.restore_dest_entry.set_text(dest)
    return dest


def _on_restore_source_changed(app):
    """Recompute the destination whenever the source changes."""
    refresh_restore_destination(app)


def _on_auto_dest_toggled(app):
    """Handle auto-destination toggle.

    When auto-determination is enabled the destination entry is grayed out
    and populated with the computed default destination.  When disabled, the
    previously entered manual destination is restored and the entry becomes
    editable again.
    """
    auto = app.restore_auto_dest_check.get_active()
    if auto:
        app._restore_manual_dest = app.restore_dest_entry.get_text()
        refresh_restore_destination(app)
    else:
        manual = getattr(app, '_restore_manual_dest', None)
        if manual is not None:
            app.restore_dest_entry.set_text(manual)
    app.restore_dest_entry.set_sensitive(not auto)
    check_restore_dirty(app)


def _set_button_markup(widget, markup):
    """Recursively find a Gtk.Label inside a widget and set its markup."""
    if isinstance(widget, Gtk.Label):
        widget.set_markup(markup)
        return True
    if hasattr(widget, 'get_children'):
        for child in widget.get_children():
            if _set_button_markup(child, markup):
                return True
    if hasattr(widget, 'get_child'):
        child = widget.get_child()
        if child and _set_button_markup(child, markup):
            return True
    return False


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def on_restore_run(app, ctx):
    """Build restore command and start execution."""
    app.clear_log_status()

    restore_cfg = collect_restore_config(app)
    source = restore_cfg["source"]
    dest = restore_cfg["dest"]
    do_part1 = restore_cfg["do_part1"]
    do_part2 = restore_cfg["do_part2"]

    if not source:
        log_msg("WARN: Source dataset must be specified")
        return
    if '@' in source:
        log_msg("WARN: Specify datasets, not snapshots (no '@' allowed)")
        return

    auto_dest = restore_cfg.get("auto_dest", False)
    if auto_dest:
        known_pools = get_pool_names(ctx.config)
        try:
            dest = compute_auto_destination(source, known_pools)
        except ValueError as e:
            log_msg(f"WARN: Error: {e}")
            return
    elif not dest:
        log_msg("WARN: Destination dataset must be specified, or enable auto-determine destination")
        return
    elif '@' in dest:
        log_msg("WARN: Specify datasets, not snapshots (no '@' allowed)")
        return

    if not do_part1 and not do_part2:
        log_msg("WARN: At least one restore part must be selected")
        return

    try:
        removequalifiers, destfs = compute_restore_params(source, dest)
    except ValueError as e:
        log_msg(f"WARN: Error: {e}")
        return

    parts_desc = []
    if do_part1:
        parts_desc.append("Part 1 (full copy from oldest snapshot)")
    if do_part2:
        parts_desc.append("Part 2 (incremental copy of remaining)")

    secondary = "\n".join(parts_desc)
    secondary += f"\n\nsourcefsremovequalifiers={removequalifiers}, destfs={destfs}"
    if auto_dest:
        secondary += "\n\nDestination was auto-determined from the source."
    if do_part1:
        secondary += (
            "\n\nPart 1 is DESTRUCTIVE -- it will destroy existing "
            "destination datasets before restoring."
        )

    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.WARNING if do_part1 else Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.OK_CANCEL,
        text=f"Restore: {source} -> {dest}",
    )
    dialog.format_secondary_text(secondary)
    response = dialog.run()
    dialog.destroy()
    if response != Gtk.ResponseType.OK:
        log_msg("INFO: Restore cancelled")
        return

    app.restore_runner.prepare_session_log()

    advanced_vars = restore_cfg["variables"]
    dryrun = getattr(app, '_dry_run_active', False)

    if dryrun:
        log_msg("INFO: Dry run mode enabled — no changes will be made")

    step = build_restore_command(
        source, removequalifiers, destfs, ctx.parent_dir,
        advanced_vars, do_part1, do_part2,
        dryrun=dryrun,
    )
    attach_step_scrub_callbacks(
        step, source, dest,
        enabled=restore_cfg.get("pause_scrubs", False), dry_run=dryrun,
        log_func=app.restore_runner._runner_log,
    )
    log_msg(f"INFO: Starting restore: {source} -> {dest}")
    app.restore_runner.set_steps([step])
    app.restore_runner.start(on_complete=lambda cancelled=False: _on_restore_complete(app, cancelled))
    app.update_action_buttons("restore")


def _on_restore_complete(app, cancelled=False):
    """Called when restore finishes or is cancelled."""
    app.update_action_buttons("restore")


def on_restore_cancel(app, ctx):
    """Cancel the running restore."""
    if app.restore_runner:
        app.restore_runner.cancel()
    app.update_action_buttons("restore")


def on_restore_save(app, ctx):
    """Save current restore config to JSON."""
    restore_data = collect_restore_config(app)
    try:
        save_restore_config(ctx.config, restore_data)
        mark_restore_clean(app)
        log_msg("INFO: Restore config saved")
    except OSError as e:
        log_msg(f"WARN: Error saving config: {e}")


def on_restore_revert(app, ctx):
    """Revert restore UI to last-saved state."""
    if not hasattr(app, '_restore_saved_state'):
        log_msg("INFO: Nothing to revert")
        return
    revert_restore_config(app)
    log_msg("INFO: Restore config reverted")
