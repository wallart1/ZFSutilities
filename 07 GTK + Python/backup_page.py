"""
Backup tab UI — builds the full Backup page widget and handles interaction.
"""

import os
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from logging_config import log_msg
from feature_config import (
    get_backup_config, generate_snapshot_name,
    save_backup_config, remove_snapfile,
    get_pool_names,
    _read_snapfile, SNAPFILE,
)
from command_builders import (
    BashStep,
    parse_rsync_endpoint,
    build_rsync_command,
    build_send_receive_command,
    build_pre_backup_command,
    build_post_backup_command,
    build_retention_command,
)
from scrub_manager import attach_step_scrub_callbacks
from gui_helpers import (
    DirtyTracker, add_var_row, EditableListView, bold_label,
)
from profile_dialogs import show_add_profile_dialog, show_recall_profile_dialog


# --- Layout constants ---

DATASET_VARIABLES = ["includes", "excludes", "startwith", "endwith"]

ADVANCED_VARIABLES = [
    "label", "autoresume", "receive_F_option", "releaseholds",
    "doincrementals", "dointermediates", "allow_destructive",
    "verify_after_transfer", "pv_rate_limit",
]

YN_VARIABLES = {"autoresume", "releaseholds", "doincrementals",
                "dointermediates", "allow_destructive",
                "verify_after_transfer"}

_BACKUP_TOPIC_MAP = {
    "includes": "backup_includes",
    "excludes": "backup_excludes",
    "startwith": "backup_startwith",
    "endwith": "backup_endwith",
    "label": "backup_label",
    "autoresume": "backup_autoresume",
    "receive_F_option": "backup_receive_F_option",
    "releaseholds": "backup_releaseholds",
    "doincrementals": "backup_doincrementals",
    "dointermediates": "backup_dointermediates",
    "allow_destructive": "backup_allow_destructive",
    "verify_after_transfer": "backup_verify_after_transfer",
    "pv_rate_limit": "backup_pv_rate_limit",
}


def _frame_grid(parent, label):
    """Create a Frame containing a Grid with standard margins."""
    frame = Gtk.Frame()
    frame.set_label_widget(bold_label(label))
    grid = Gtk.Grid()
    grid.set_row_spacing(5)
    grid.set_column_spacing(10)
    grid.set_margin_start(10)
    grid.set_margin_end(10)
    grid.set_margin_top(5)
    grid.set_margin_bottom(5)
    frame.add(grid)
    parent.pack_start(frame, False, False, 0)
    return grid


def _frame_box(parent, label, header_widget=None):
    """Create a Frame containing a Box with standard margins.

    If *header_widget* is supplied, it is packed into the frame's label
    area to the right of the label text.
    """
    frame = Gtk.Frame()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    box.set_margin_start(10)
    box.set_margin_end(10)
    box.set_margin_top(5)
    box.set_margin_bottom(5)
    frame.add(box)

    if header_widget is not None:
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_box.pack_start(bold_label(label), False, False, 0)
        header_box.pack_end(header_widget, False, False, 0)
        frame.set_label_widget(header_box)
    else:
        frame.set_label_widget(bold_label(label))

    parent.pack_start(frame, False, False, 0)
    return box


def create_backup_page(app, ctx):
    """Build and return the full Backup tab widget."""
    backup_cfg = get_backup_config(ctx.config)
    variables = backup_cfg["variables"]

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(10)
    box.set_margin_end(10)
    box.set_margin_top(10)
    box.set_margin_bottom(10)
    scrolled.add(box)

    title = Gtk.Label()
    title.set_markup("<big><b>Backup</b></big>")
    title.set_halign(Gtk.Align.START)
    box.pack_start(title, False, False, 0)
    box.pack_start(Gtk.Separator(), False, False, 0)

    app.backup_var_widgets = {}

    # --- Pre-Backup ---
    pre_grid = _frame_grid(box, "Pre-Backup")

    app.backup_pre_script_enabled = Gtk.CheckButton(label="Run pre-backup command")
    app.backup_pre_script_enabled.set_active(backup_cfg.get("pre_backup_script_enabled", False))
    app.backup_pre_script_enabled.set_tooltip_text(
        "Run a custom command before all backup steps. If it fails, the backup aborts."
    )
    pre_grid.attach(app.backup_pre_script_enabled, 0, 0, 2, 1)

    app.backup_pre_script_text = Gtk.Entry()
    app.backup_pre_script_text.set_text(backup_cfg.get("pre_backup_script", ""))
    app.backup_pre_script_text.set_hexpand(True)
    app.backup_pre_script_text.set_width_chars(1)
    app.backup_pre_script_text.set_placeholder_text("Command to run before backup...")
    pre_grid.attach(app.backup_pre_script_text, 0, 1, 2, 1)

    # --- Advanced (collapsed expander) ---
    advanced_exp = Gtk.Expander()
    advanced_exp.set_label_widget(bold_label("Advanced"))
    advanced_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    advanced_box.set_margin_start(10)
    advanced_box.set_margin_end(10)
    advanced_box.set_margin_top(5)
    advanced_box.set_margin_bottom(5)
    advanced_exp.add(advanced_box)
    box.pack_start(advanced_exp, False, False, 0)

    ds_grid = _frame_grid(advanced_box, "Dataset Selection")

    for i, key in enumerate(DATASET_VARIABLES):
        add_var_row(ds_grid, i, key, variables, app.backup_var_widgets,
                    yn_vars=YN_VARIABLES, topic_map=_BACKUP_TOPIC_MAP)

    other_grid = Gtk.Grid()
    other_grid.set_row_spacing(5)
    other_grid.set_column_spacing(10)
    other_grid.set_margin_start(0)
    other_grid.set_margin_end(0)
    other_grid.set_margin_top(5)
    other_grid.set_margin_bottom(5)
    advanced_box.pack_start(other_grid, False, False, 0)

    for i, key in enumerate(ADVANCED_VARIABLES):
        add_var_row(other_grid, i, key, variables, app.backup_var_widgets,
                    yn_vars=YN_VARIABLES, topic_map=_BACKUP_TOPIC_MAP)

    # --- ZFS Keys Backup ---
    zfs_keys_grid = Gtk.Grid()
    zfs_keys_grid.set_row_spacing(5)
    zfs_keys_grid.set_column_spacing(10)
    zfs_keys_grid.set_margin_top(5)
    zfs_keys_grid.set_margin_bottom(5)

    zfs_keys_lbl = Gtk.Label(label="ZFS keys source:")
    zfs_keys_lbl.set_halign(Gtk.Align.START)
    zfs_keys_grid.attach(zfs_keys_lbl, 0, 0, 1, 1)

    app.backup_zfs_keys_path = Gtk.Entry()
    app.backup_zfs_keys_path.set_hexpand(True)
    app.backup_zfs_keys_path.set_width_chars(1)
    app.backup_zfs_keys_path.set_placeholder_text("host:/path/to/keys/")
    zfs_keys_grid.attach(app.backup_zfs_keys_path, 1, 0, 1, 1)

    zfs_keys_dest_lbl = Gtk.Label(label="ZFS keys dest:")
    zfs_keys_dest_lbl.set_halign(Gtk.Align.START)
    zfs_keys_grid.attach(zfs_keys_dest_lbl, 0, 1, 1, 1)

    app.backup_zfs_keys_dest = Gtk.Entry()
    app.backup_zfs_keys_dest.set_hexpand(True)
    app.backup_zfs_keys_dest.set_width_chars(1)
    zfs_keys_grid.attach(app.backup_zfs_keys_dest, 1, 1, 1, 1)

    advanced_box.pack_start(zfs_keys_grid, False, False, 0)

    app.backup_var_widgets.get("allow_destructive").set_tooltip_text(
        "Permit a full copy that destroys an existing populated destination "
        "(snapshots and/or child datasets). Leave 'N' to skip such datasets "
        "with a WARN instead of silently destroying them."
    )

    app.backup_pause_scrubs = Gtk.CheckButton(
        label="Pause scrubs on source/destination pools during each step"
    )
    app.backup_pause_scrubs.set_active(
        backup_cfg.get("pause_scrubs", False)
    )
    app.backup_pause_scrubs.set_tooltip_text(
        "Pause ZFS scrubs on the pools used by each send/receive step "
        "while that step is running."
    )
    advanced_box.pack_start(app.backup_pause_scrubs, False, False, 0)

    # --- Pull Steps (rsync) ---
    app.backup_pull_steps_active = Gtk.CheckButton(label="Active")
    app.backup_pull_steps_active.set_active(
        backup_cfg.get("pull_steps_active", True)
    )
    app.backup_pull_steps_active.set_tooltip_text(
        "When unchecked, all pull steps are bypassed."
    )
    pull_box = _frame_box(
        box, "Pull Steps (rsync)", header_widget=app.backup_pull_steps_active
    )

    pull_elv = EditableListView()
    app.backup_pull_store = pull_elv.get_store()
    pull_box.pack_start(pull_elv.get_widget(), True, True, 0)
    pull_elv.set_data([
        (s["active"], s["source"], s["dest"])
        for s in backup_cfg["pull_steps"]
    ])

    # --- nextsnap (above ZFS Send/Receive Steps) ---
    snap_grid = _frame_grid(box, "Snapshot")

    app.backup_nextsnap_label = Gtk.Label(label="nextsnap")
    app.backup_nextsnap_label.set_halign(Gtk.Align.END)
    snap_grid.attach(app.backup_nextsnap_label, 0, 0, 1, 1)

    snap_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    app.backup_nextsnap_entry = Gtk.Entry()
    app.backup_nextsnap_entry.set_hexpand(True)
    app.backup_nextsnap_entry.set_width_chars(1)
    snap_box.pack_start(app.backup_nextsnap_entry, True, True, 0)

    gen_btn = Gtk.Button(label="Generate")
    gen_btn.connect("clicked", _on_generate_snap, app)
    snap_box.pack_start(gen_btn, False, False, 0)
    snap_grid.attach(snap_box, 1, 0, 1, 1)

    # Inline: read previously saved snapshot name from disk
    saved = _read_snapfile(SNAPFILE)
    if saved:
        app.backup_nextsnap_entry.set_text(saved)
        app.backup_nextsnap_label.set_text("nextsnap (previous)")
        log_msg(f"INFO: Previous snapshot name found: {saved}")
    else:
        _do_generate_snap(app)

    # --- ZFS Send/Receive Steps ---
    sr_box = _frame_box(box, "ZFS Send/Receive Steps")

    sr_elv = EditableListView(
        columns=[(1, "Source Pool/Subpool", 160), (2, "Destination Pool", 120)],
    )
    app.backup_sr_store = sr_elv.get_store()
    sr_box.pack_start(sr_elv.get_widget(), True, True, 0)
    sr_elv.set_data([
        (s["active"], s["source"], s["dest"])
        for s in backup_cfg["send_receive_steps"]
    ])

    # --- Post-Backup Steps ---
    post_grid = _frame_grid(box, "Post-Backup Steps")

    post_cfg = backup_cfg["post_steps"]
    app.backup_post_snapfile = Gtk.CheckButton(label="Clear snapshot name memory")
    app.backup_post_snapfile.set_active(post_cfg.get("remove_snapfile", True))
    post_grid.attach(app.backup_post_snapfile, 0, 0, 2, 1)

    app.backup_post_retention = Gtk.CheckButton(label="Prune snapshots")
    app.backup_post_retention.set_active(post_cfg.get("run_retention", True))
    post_grid.attach(app.backup_post_retention, 0, 1, 2, 1)

    app.backup_post_script_enabled = Gtk.CheckButton(label="Run post-backup command")
    app.backup_post_script_enabled.set_active(
        backup_cfg.get("post_backup_script_enabled", False)
    )
    app.backup_post_script_enabled.set_tooltip_text(
        "Run a custom command after all backup steps. Runs even if a backup step fails."
    )
    post_grid.attach(app.backup_post_script_enabled, 0, 2, 2, 1)

    app.backup_post_script_text = Gtk.Entry()
    app.backup_post_script_text.set_text(backup_cfg.get("post_backup_script", ""))
    app.backup_post_script_text.set_hexpand(True)
    app.backup_post_script_text.set_width_chars(1)
    app.backup_post_script_text.set_placeholder_text(
        "Command to run after backup..."
    )
    post_grid.attach(app.backup_post_script_text, 0, 3, 2, 1)

    tracker = DirtyTracker(app, lambda: collect_backup_config(app),
                           "_save_config_button")
    app._backup_tracker = tracker
    pull_elv.set_on_changed(tracker.check)
    sr_elv.set_on_changed(tracker.check)
    app._ui_state.bind_treeview(pull_elv.view, "backup_pull_steps_view")
    app._ui_state.bind_treeview(sr_elv.view, "backup_sendreceive_steps_view")

    for widget in app.backup_var_widgets.values():
        widget.connect("changed", lambda _w, t=tracker: t.check())
    app.backup_post_snapfile.connect("toggled", lambda _w, t=tracker: t.check())
    app.backup_post_retention.connect("toggled", lambda _w, t=tracker: t.check())
    app.backup_post_script_enabled.connect("toggled", lambda _w, t=tracker: t.check())
    app.backup_post_script_text.connect("changed", lambda _w, t=tracker: t.check())
    app.backup_pre_script_enabled.connect("toggled", lambda _w, t=tracker: t.check())
    app.backup_pre_script_text.connect("changed", lambda _w, t=tracker: t.check())
    app.backup_zfs_keys_path.connect("changed", lambda _w, t=tracker: t.check())
    app.backup_zfs_keys_dest.connect("changed", lambda _w, t=tracker: t.check())
    app.backup_pull_steps_active.connect(
        "toggled", lambda _w, t=tracker: t.check()
    )
    app.backup_pause_scrubs.connect(
        "toggled", lambda _w, t=tracker: t.check()
    )

    return scrolled


# --- Config helpers ---

def load_backup_config(app, config):
    """Load a backup config dict into the UI widgets."""
    for key, widget in app.backup_var_widgets.items():
        val = config.get("variables", {}).get(key, "")
        if isinstance(widget, Gtk.ComboBoxText):
            widget.set_active(0 if val == "Y" else 1)
        else:
            widget.set_text(val)

    for store, key in ((app.backup_pull_store, "pull_steps"),
                        (app.backup_sr_store, "send_receive_steps")):
        store.clear()
        for step in config.get(key, []):
            store.append([step["active"], step["source"], step["dest"]])

    app.backup_post_snapfile.set_active(config.get("post_steps", {}).get("remove_snapfile", True))
    app.backup_post_retention.set_active(config.get("post_steps", {}).get("run_retention", True))

    app.backup_pre_script_enabled.set_active(config.get("pre_backup_script_enabled", False))
    app.backup_pre_script_text.set_text(config.get("pre_backup_script", ""))
    app.backup_post_script_enabled.set_active(config.get("post_backup_script_enabled", False))
    app.backup_post_script_text.set_text(config.get("post_backup_script", ""))
    app.backup_zfs_keys_path.set_text(config.get("zfs_keys_path", ""))
    app.backup_zfs_keys_dest.set_text(config.get("zfs_keys_dest", ""))
    app.backup_pull_steps_active.set_active(config.get("pull_steps_active", True))
    app.backup_pause_scrubs.set_active(config.get("pause_scrubs", False))


def mark_backup_clean(app):
    """Call after saving to update the saved state and reset the button."""
    if hasattr(app, '_backup_tracker'):
        app._backup_tracker.mark_clean()


def revert_backup_config(app):
    """Restore all backup UI widgets to the last-saved state."""
    if hasattr(app, '_backup_tracker'):
        app._backup_tracker.revert(lambda cfg: load_backup_config(app, cfg))


def check_backup_dirty(app):
    """Compare current UI state to last-saved state; style Save button."""
    if hasattr(app, '_backup_tracker'):
        app._backup_tracker.check()


def collect_backup_config(app):
    """Collect current UI state into a backup config dict."""
    variables = {}
    for key, widget in app.backup_var_widgets.items():
        if isinstance(widget, Gtk.ComboBoxText):
            variables[key] = widget.get_active_text() or "Y"
        else:
            variables[key] = widget.get_text()

    pull_steps = [{"active": r[0], "source": r[1], "dest": r[2]}
                  for r in app.backup_pull_store]
    sr_steps = [{"active": r[0], "source": r[1], "dest": r[2]}
                for r in app.backup_sr_store]

    post_steps = {
        "remove_snapfile": app.backup_post_snapfile.get_active(),
        "run_retention": app.backup_post_retention.get_active(),
    }

    return {
        "variables": variables,
        "pull_steps": pull_steps,
        "send_receive_steps": sr_steps,
        "post_steps": post_steps,
        "pre_backup_script_enabled": app.backup_pre_script_enabled.get_active(),
        "pre_backup_script": app.backup_pre_script_text.get_text(),
        "post_backup_script_enabled": app.backup_post_script_enabled.get_active(),
        "post_backup_script": app.backup_post_script_text.get_text(),
        "zfs_keys_path": app.backup_zfs_keys_path.get_text(),
        "zfs_keys_dest": app.backup_zfs_keys_dest.get_text(),
        "pull_steps_active": app.backup_pull_steps_active.get_active(),
        "pause_scrubs": app.backup_pause_scrubs.get_active(),
    }


# --- Snapshot helpers ---

def _do_generate_snap(app):
    """Generate a new snapshot name, update entry and label."""
    label_widget = app.backup_var_widgets.get("label")
    if isinstance(label_widget, Gtk.Entry):
        label = label_widget.get_text().strip() or "dailybackup"
    else:
        label = "dailybackup"
    snap = generate_snapshot_name(label)
    app.backup_nextsnap_entry.set_text(snap)
    app.backup_nextsnap_label.set_text("nextsnap (new)")
    log_msg(f"INFO: New snapshot name: {snap}")


def _on_generate_snap(button, app):
    _do_generate_snap(app)


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _is_dataset_encrypted(path):
    """Return True if *path* resides on an encrypted ZFS dataset."""
    if not path:
        return False
    abs_path = os.path.abspath(path)
    try:
        result = subprocess.run(
            ["zfs", "list", "-H", "-o", "name,mountpoint"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            return False
        datasets = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                datasets.append((parts[0], parts[1]))
        candidate = None
        for ds, mp in datasets:
            if abs_path.startswith(mp.rstrip("/") + "/") or abs_path == mp.rstrip("/"):
                if candidate is None or len(mp) > len(candidate[1]):
                    candidate = (ds, mp)
        if candidate is None:
            return False
        ds_name = candidate[0]
        result = subprocess.run(
            ["zfs", "get", "-H", "-o", "value", "encryption", ds_name],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            return False
        enc = result.stdout.strip()
        return enc not in ("-", "off")
    except Exception:
        return False


def on_backup_run(app, ctx):
    """Build step list and start backup execution."""
    app.clear_log_status()

    nextsnap = app.backup_nextsnap_entry.get_text().strip()
    if not nextsnap:
        log_msg("WARN: Generate or enter a snapshot name first")
        return

    if nextsnap[0] != '@':
        nextsnap = '@' + nextsnap
        app.backup_nextsnap_entry.set_text(nextsnap)

    while True:
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            text=f"New snapshot: {nextsnap}",
        )
        dialog.format_secondary_text("Proceed with backup?")
        dialog.add_button("Generate", Gtk.ResponseType.APPLY)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            break
        if response == Gtk.ResponseType.APPLY:
            _do_generate_snap(app)
            nextsnap = app.backup_nextsnap_entry.get_text().strip()
            continue
        log_msg("INFO: Backup cancelled")
        return

    app.backup_runner.prepare_session_log()

    backup_cfg = collect_backup_config(app)
    variables = backup_cfg["variables"]
    dryrun = getattr(app, '_dry_run_active', False)

    if dryrun:
        log_msg("INFO: Dry run mode enabled — no changes will be made")

    steps = []

    # Pre-backup script
    if app.backup_pre_script_enabled.get_active():
        script = app.backup_pre_script_text.get_text().strip()
        if script:
            if dryrun:
                log_msg("INFO: Dry-run: Would run pre-backup script")
            else:
                steps.append(build_pre_backup_command(script))

    if app.backup_pull_steps_active.get_active():
        active_pulls = [(row[1], row[2]) for row in app.backup_pull_store if row[0]]
    else:
        active_pulls = []
        log_msg("INFO: Pull steps disabled by user; skipping")

    done_hosts = set()

    for source, dest in active_pulls:
        src_host, src_path = parse_rsync_endpoint(source)
        if src_host is None and src_path.startswith("/mnt/"):
            mount_path = src_path.rstrip("/")
            if not os.path.ismount(mount_path):
                log_msg(f"WARN: Skipping {source} -> {dest}: {mount_path} is not mounted")
                continue
            try:
                os.listdir(mount_path)
            except OSError:
                log_msg(f"WARN: Skipping {source} -> {dest}: {mount_path} is not accessible")
                continue
        if dryrun:
            log_msg(f"INFO: Dry-run: Would rsync {source} -> {dest}")
        else:
            steps.append(build_rsync_command(source, dest))

    # Optional ZFS keys backup
    zfs_keys_path = backup_cfg.get("zfs_keys_path", "").strip()
    zfs_keys_dest = backup_cfg.get("zfs_keys_dest", "").strip()
    if zfs_keys_path and zfs_keys_dest:
        src_host, src_path = parse_rsync_endpoint(zfs_keys_path)
        if src_host not in done_hosts:
            done_hosts.add(src_host)
        if src_host is None and src_path.startswith("/mnt/"):
            mount_path = src_path.rstrip("/")
            if not os.path.ismount(mount_path):
                log_msg(f"WARN: Skipping ZFS keys {zfs_keys_path} -> {zfs_keys_dest}: {mount_path} is not mounted")
            else:
                try:
                    os.listdir(mount_path)
                except OSError:
                    log_msg(f"WARN: Skipping ZFS keys {zfs_keys_path} -> {zfs_keys_dest}: {mount_path} is not accessible")
                else:
                    if not _is_dataset_encrypted(zfs_keys_dest):
                        log_msg(f"WARN: Skipping ZFS keys backup — destination is not encrypted. "
                                f"Set zfs_keys_dest to an encrypted dataset.")
                    elif dryrun:
                        log_msg(f"INFO: Dry-run: Would rsync {zfs_keys_path} -> {zfs_keys_dest}")
                    else:
                        steps.append(build_rsync_command(zfs_keys_path, zfs_keys_dest))
        else:
            if not _is_dataset_encrypted(zfs_keys_dest):
                log_msg(f"WARN: Skipping ZFS keys backup — destination is not encrypted. "
                                f"Set zfs_keys_dest to an encrypted dataset.")
            elif dryrun:
                log_msg(f"INFO: Dry-run: Would rsync {zfs_keys_path} -> {zfs_keys_dest}")
            else:
                steps.append(build_rsync_command(zfs_keys_path, zfs_keys_dest))

    # Send/receive steps
    pause_scrubs = backup_cfg.get("pause_scrubs", False)
    for row in app.backup_sr_store:
        if row[0]:
            sr_step = build_send_receive_command(
                row[1], row[2], variables, ctx.parent_dir, nextsnap,
                dryrun=dryrun,
            )
            attach_step_scrub_callbacks(
                sr_step, row[1], row[2],
                enabled=pause_scrubs, dry_run=dryrun,
                log_func=app.backup_runner._runner_log,
            )
            steps.append(sr_step)

    # Post steps
    post = backup_cfg["post_steps"]
    if post.get("run_retention", False):
        label = variables.get("label", "dailybackup")
        pools = get_pool_names(ctx.config) or None
        steps.append(build_retention_command(
            ctx.parent_dir, label, pools=pools, dryrun=dryrun, fatal=False,
        ))

    # Finally: post-backup script (runs even on fatal error)
    has_finally = False
    if app.backup_post_script_enabled.get_active():
        script = app.backup_post_script_text.get_text().strip()
        if script:
            if dryrun:
                log_msg("INFO: Dry-run: Would run post-backup script")
            else:
                app.backup_runner.set_finally_step(build_post_backup_command(script))
                has_finally = True

    if not steps and not has_finally:
        log_msg("WARN: No active steps to run")
        return

    log_msg(f"INFO: Snapshot: {nextsnap}")
    app.backup_runner.set_steps(steps)
    app.backup_runner.start(on_complete=lambda cancelled=False: _on_backup_complete(app, cancelled))
    app.update_action_buttons("backup")


def _on_backup_complete(app, cancelled=False):
    """Called when backup finishes or is cancelled."""
    if not cancelled and app.backup_post_snapfile.get_active():
        if getattr(app, '_dry_run_active', False):
            log_msg("INFO: Dry-run: Skipping snapfile cleanup (preserved for real run)")
        else:
            remove_snapfile()
    app.update_action_buttons("backup")


def on_backup_cancel(app, ctx):
    """Cancel the running backup."""
    if app.backup_runner:
        app.backup_runner.cancel()
    app.update_action_buttons("backup")


def on_backup_save(app, ctx):
    """Save current backup config to JSON."""
    backup_data = collect_backup_config(app)
    try:
        save_backup_config(ctx.config, backup_data)
        mark_backup_clean(app)
        log_msg("INFO: Backup config saved to /root/.config/zfsutilities.json")
    except OSError as e:
        log_msg(f"WARN: Error saving config: {e}")


def on_backup_revert(app, ctx):
    """Revert backup UI to last-saved state."""
    if not hasattr(app, '_backup_tracker'):
        log_msg("INFO: Nothing to revert")
        return
    revert_backup_config(app)
    log_msg("INFO: Backup config reverted to last saved state")


def backup_set_all_active(app, ctx, active):
    """Set all Active checkboxes in pull, send/receive, pre-backup, and post-backup."""
    for store in (app.backup_pull_store, app.backup_sr_store):
        tree_iter = store.get_iter_first()
        while tree_iter:
            store.set_value(tree_iter, 0, active)
            tree_iter = store.iter_next(tree_iter)
    app.backup_pre_script_enabled.set_active(active)
    app.backup_post_snapfile.set_active(active)
    app.backup_post_retention.set_active(active)
    app.backup_post_script_enabled.set_active(active)
    state = "selected" if active else "deselected"
    log_msg(f"INFO: All steps {state}")


