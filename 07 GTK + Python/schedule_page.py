"""
Schedule tab UI — lists profiles, manages cron parameters, and keeps
/etc/cron.d/zfsutilities synchronized.
"""

import os
import subprocess
import sys

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from logging_config import log_msg
from gui_helpers import (
    set_button_markup_red, set_monospace_font, enable_textview_copy,
    configure_treeview_column, ACTIVE_COLUMN_WIDTH,
    bold_label,
)
from profile_manager import (
    list_profiles, load_profile, save_profile, delete_profile,
)
from cron_manager import (
    write_cron_file, generate_cron_line, interpret_cron, format_next_runs,
    next_run_times,
)
from profile_dialogs import show_add_profile_dialog, show_recall_profile_dialog

COL_ACTIVE = 0
COL_NAME = 1
COL_TYPE = 2
COL_SCHEDULE = 3
COL_NEXT_RUN = 4
COL_NEXT_RUN_SORT = 5


def create_schedule_page(app):
    """Build and return the Schedule tab widget."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.set_margin_start(10)
    outer.set_margin_end(10)
    outer.set_margin_top(10)
    outer.set_margin_bottom(10)

    title = Gtk.Label()
    title.set_markup("<big><b>Schedule</b></big>")
    title.set_halign(Gtk.Align.START)
    outer.pack_start(title, False, False, 0)
    outer.pack_start(Gtk.Separator(), False, False, 0)

    desc = Gtk.Label(
        label="Manage scheduled profiles. Profiles are created from the Backup, "
              "Offsite, Restore, or Retention tabs. Enable a profile and set its "
              "cron schedule below."
    )
    desc.set_halign(Gtk.Align.START)
    desc.set_line_wrap(True)
    outer.pack_start(desc, False, False, 0)


    app.schedule_store = Gtk.ListStore(bool, str, str, str, str, str)
    app.schedule_view = Gtk.TreeView(model=app.schedule_store)
    app.schedule_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.schedule_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    toggle_r = Gtk.CellRendererToggle()
    toggle_r.connect("toggled", _on_active_toggled, app)
    col_active = Gtk.TreeViewColumn("Active", toggle_r, active=COL_ACTIVE)
    configure_treeview_column(col_active, width=ACTIVE_COLUMN_WIDTH,
                              min_width=ACTIVE_COLUMN_WIDTH)
    app.schedule_view.append_column(col_active)

    for col_idx, title_text, width in [
        (COL_NAME, "Profile Name", 140),
        (COL_TYPE, "Type", 70),
        (COL_SCHEDULE, "Schedule", 90),
        (COL_NEXT_RUN, "Next Run", 130),
    ]:
        r = Gtk.CellRendererText()
        r.set_property("editable", False)
        if col_idx == COL_NEXT_RUN:
            set_monospace_font(r)
        col = Gtk.TreeViewColumn(title_text, r, text=col_idx)
        configure_treeview_column(col, width=width)
        if col_idx in (COL_NAME, COL_TYPE):
            col.set_sort_column_id(col_idx)
            col.set_clickable(True)
        elif col_idx == COL_NEXT_RUN:
            col.set_sort_column_id(COL_NEXT_RUN_SORT)
            col.set_clickable(True)
        app.schedule_view.append_column(col)
    app._ui_state.bind_treeview(app.schedule_view, "schedule_view")

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_height(180)
    scroll.add(app.schedule_view)
    outer.pack_start(scroll, False, False, 0)

    app.schedule_view.get_selection().connect("changed", _on_selection_changed, app)

    app.schedule_detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    app.schedule_detail_box.set_no_show_all(True)
    outer.pack_start(app.schedule_detail_box, False, False, 0)

    app.schedule_detail_box.pack_start(Gtk.Separator(), False, False, 0)

    info_grid = Gtk.Grid()
    info_grid.set_row_spacing(4)
    info_grid.set_column_spacing(10)
    app.schedule_name_label = Gtk.Label()
    app.schedule_name_label.set_halign(Gtk.Align.START)
    app.schedule_name_label.set_selectable(True)
    info_grid.attach(Gtk.Label(label="Profile:"), 0, 0, 1, 1)
    info_grid.attach(app.schedule_name_label, 1, 0, 1, 1)

    app.schedule_type_label = Gtk.Label()
    app.schedule_type_label.set_halign(Gtk.Align.START)
    info_grid.attach(Gtk.Label(label="Type:"), 0, 1, 1, 1)
    info_grid.attach(app.schedule_type_label, 1, 1, 1, 1)
    app.schedule_detail_box.pack_start(info_grid, False, False, 0)

    cron_frame = Gtk.Frame()
    cron_frame.set_label_widget(bold_label("Cron Parameters"))
    cron_grid = Gtk.Grid()
    cron_grid.set_row_spacing(5)
    cron_grid.set_column_spacing(10)
    cron_grid.set_margin_start(10)
    cron_grid.set_margin_end(10)
    cron_grid.set_margin_top(5)
    cron_grid.set_margin_bottom(5)
    cron_frame.add(cron_grid)
    app.schedule_detail_box.pack_start(cron_frame, False, False, 0)

    cron_fields = [
        ("minute", "Minute (0-59 or *)",
         "0-59, *, lists (1,15,30), ranges (9-17), steps (*/5)", 0),
        ("hour", "Hour (0-23 or *)",
         "0-23, *, lists, ranges, steps", 1),
        ("day", "Day of Month (1-31 or *)",
         "1-31, *, lists, ranges, steps", 2),
        ("month", "Month (1-12 or *)",
         "1-12, *, lists, ranges, steps", 3),
        ("weekday", "Day of Week (0-7 or *)",
         "0=Sun, 1=Mon, ..., 7=Sun; lists, ranges, steps; "
         "ordinals 6#1 (first Sat) through 6#5, 6#L (last)", 4),
    ]
    app.schedule_cron_entries = {}
    for key, label_text, tooltip, row in cron_fields:
        lbl = Gtk.Label(label=label_text)
        lbl.set_halign(Gtk.Align.END)
        cron_grid.attach(lbl, 0, row, 1, 1)

        entry = Gtk.Entry()
        entry.set_width_chars(15)
        entry.set_tooltip_text(tooltip)
        entry.connect("changed", _on_cron_entry_changed, app)
        cron_grid.attach(entry, 1, row, 1, 1)
        app.schedule_cron_entries[key] = entry

    app._schedule_pending = {}
    app._schedule_ignore_changes = False

    app.schedule_interpret_label = Gtk.Label()
    app.schedule_interpret_label.set_halign(Gtk.Align.START)
    app.schedule_interpret_label.set_line_wrap(True)
    app.schedule_interpret_label.set_selectable(True)
    app.schedule_detail_box.pack_start(app.schedule_interpret_label, False, False, 0)

    app.schedule_examples_label = Gtk.Label()
    app.schedule_examples_label.set_halign(Gtk.Align.START)
    app.schedule_examples_label.set_line_wrap(True)
    app.schedule_examples_label.set_selectable(True)
    app.schedule_detail_box.pack_start(app.schedule_examples_label, False, False, 0)

    sum_exp = Gtk.Expander()
    sum_exp.set_label_widget(bold_label("Config Summary"))
    app.schedule_summary_textview = Gtk.TextView()
    app.schedule_summary_textview.set_editable(False)
    app.schedule_summary_textview.set_cursor_visible(False)
    app.schedule_summary_textview.set_monospace(True)
    app.schedule_summary_textview.set_left_margin(5)
    app.schedule_summary_textview.set_right_margin(5)
    app.schedule_summary_textview.set_top_margin(5)
    app.schedule_summary_textview.set_bottom_margin(5)
    enable_textview_copy(app.schedule_summary_textview)

    sum_scroll = Gtk.ScrolledWindow()
    sum_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sum_scroll.set_min_content_height(180)
    sum_scroll.add(app.schedule_summary_textview)
    sum_exp.add(sum_scroll)
    app.schedule_detail_box.pack_start(sum_exp, False, False, 0)

    _refresh_profile_list(app)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.add(outer)
    return scrolled


def _format_cron(cron):
    return "{} {} {} {} {}".format(
        cron.get("minute", "*"),
        cron.get("hour", "*"),
        cron.get("day", "*"),
        cron.get("month", "*"),
        cron.get("weekday", "*"),
    )


def collect_schedule_config(app):
    """Collect current cron entry values into a dict."""
    return {
        key: entry.get_text().strip() or "*"
        for key, entry in app.schedule_cron_entries.items()
    }


def load_schedule_config(app, cron):
    """Load a cron dict into the schedule UI widgets."""
    for key, entry in app.schedule_cron_entries.items():
        entry.set_text(cron.get(key, "*"))


def _next_run_strings(cron):
    """Return (display_string, sort_string) for the next cron execution."""
    times = next_run_times(
        cron.get("minute", "*"), cron.get("hour", "*"),
        cron.get("day", "*"), cron.get("month", "*"),
        cron.get("weekday", "*"), count=1,
    )
    if not times:
        return (
            "No upcoming runs found (schedule may be invalid or too restrictive.)",
            "",
        )
    dt = times[0]
    return dt.strftime("%a %b %d %Y %H:%M"), dt.strftime("%Y-%m-%d %H:%M")


def _refresh_profile_list(app):
    app.schedule_store.clear()
    profiles = list_profiles()
    for profile in profiles:
        cron = profile.get("cron", {})
        sched = _format_cron(cron)
        next_run, next_run_sort = _next_run_strings(cron)
        app.schedule_store.append([
            profile.get("active", False),
            profile["profile_name"],
            profile.get("tab_type", ""),
            sched,
            next_run,
            next_run_sort,
        ])
    app.schedule_detail_box.set_no_show_all(True)
    app.schedule_detail_box.hide()


def refresh_schedule_page(app):
    """Refresh the Schedule tab from disk.

    Updates Next Run values in place when the profile list is unchanged;
    rebuilds the list when profiles have been added or removed outside the
    Schedule tab. Preserves the current selection and any pending unsaved
    changes.
    """
    if not hasattr(app, "schedule_store"):
        return

    selection = app.schedule_view.get_selection()
    model, paths = selection.get_selected_rows()
    selected_names = []
    for path in paths:
        tree_iter = model.get_iter(path)
        selected_names.append(model.get_value(tree_iter, COL_NAME))

    profiles = list_profiles()
    profile_names = {p["profile_name"] for p in profiles}
    store_names = {row[COL_NAME] for row in app.schedule_store}

    if profile_names != store_names:
        _refresh_profile_list(app)
        for name in list(app._schedule_pending.keys()):
            if name not in profile_names:
                app._schedule_pending.pop(name, None)
        _update_schedule_dirty(app)
    else:
        for row in app.schedule_store:
            _update_next_run_for_iter(app, row.iter)

    if selected_names:
        selection.unselect_all()
        for name in selected_names:
            tree_iter = _find_iter_by_name(app, name)
            if tree_iter is not None:
                selection.select_iter(tree_iter)

    log_msg("VERB: Schedule page refreshed")


def _on_active_toggled(renderer, path, app):
    # Make the toggled row selected so Delete and the detail pane work even
    # when the user clicked the checkbox column rather than the row text.
    # With multi-selection enabled, select only the toggled row.
    selection = app.schedule_view.get_selection()
    selection.unselect_all()
    selection.select_path(Gtk.TreePath.new_from_string(path))

    tree_iter = app.schedule_store.get_iter_from_string(path)
    old_val = app.schedule_store.get_value(tree_iter, COL_ACTIVE)
    new_val = not old_val
    app.schedule_store.set_value(tree_iter, COL_ACTIVE, new_val)

    profile_name = app.schedule_store.get_value(tree_iter, COL_NAME)
    profile = load_profile(profile_name)
    if profile is None:
        log_msg(f"WARN: Profile not found: {profile_name}")
        return

    saved_active = profile.get("active", False)
    pending = app._schedule_pending.setdefault(profile_name, {})
    if new_val != saved_active:
        pending["active"] = new_val
    else:
        pending.pop("active", None)
    if not pending:
        app._schedule_pending.pop(profile_name, None)

    _update_schedule_dirty(app)


def _update_next_run_for_iter(app, tree_iter):
    profile_name = app.schedule_store.get_value(tree_iter, COL_NAME)
    profile = load_profile(profile_name)
    if profile is None:
        return
    cron = profile.get("cron", {})
    next_run, next_run_sort = _next_run_strings(cron)
    app.schedule_store.set_value(tree_iter, COL_NEXT_RUN, next_run)
    app.schedule_store.set_value(tree_iter, COL_NEXT_RUN_SORT, next_run_sort)


def _on_selection_changed(selection, app):
    model, paths = selection.get_selected_rows()
    if not paths:
        app.schedule_detail_box.hide()
        return

    tree_iter = model.get_iter(paths[0])
    profile_name = model.get_value(tree_iter, COL_NAME)
    profile = load_profile(profile_name)
    if profile is None:
        app.schedule_detail_box.hide()
        return

    app.schedule_name_label.set_text(profile_name)
    app.schedule_type_label.set_text(profile.get("tab_type", ""))

    pending = app._schedule_pending.get(profile_name, {})
    cron = pending.get("cron", profile.get("cron", {}))

    app._schedule_ignore_changes = True
    load_schedule_config(app, cron)
    app._schedule_ignore_changes = False

    saved_active = profile.get("active", False)
    current_active = model.get_value(tree_iter, COL_ACTIVE)
    if current_active != saved_active:
        pending["active"] = current_active
    else:
        pending.pop("active", None)

    current_cron = collect_schedule_config(app)
    saved_cron = profile.get("cron", {})
    if current_cron != saved_cron:
        pending["cron"] = current_cron
    else:
        pending.pop("cron", None)

    if pending:
        app._schedule_pending[profile_name] = pending
    else:
        app._schedule_pending.pop(profile_name, None)

    _update_schedule_dirty(app)
    _update_interpretation(app)

    import json
    cfg = profile.get("config", {})
    dry_run = profile.get("dry_run", False)
    summary = f"Dry run: {'Yes' if dry_run else 'No'}\n\n{json.dumps(cfg, indent=2)}"
    if profile.get("active", False):
        runner_path = _resolve_profile_runner_path()
        cron_line = generate_cron_line(profile, runner_path)
        if cron_line:
            summary = f"Crontab entry:\n{cron_line}\n\n{summary}"
    app.schedule_summary_textview.get_buffer().set_text(summary, -1)

    app.schedule_detail_box.set_no_show_all(False)
    app.schedule_detail_box.show_all()


def _on_cron_entry_changed(entry, app):
    if getattr(app, '_schedule_ignore_changes', False):
        return

    _update_interpretation(app)

    selection = app.schedule_view.get_selection()
    model, paths = selection.get_selected_rows()
    if not paths:
        return

    tree_iter = model.get_iter(paths[0])
    profile_name = model.get_value(tree_iter, COL_NAME)
    profile = load_profile(profile_name)
    if profile is None:
        return

    saved_cron = profile.get("cron", {})
    current_cron = collect_schedule_config(app)
    pending = app._schedule_pending.setdefault(profile_name, {})
    if current_cron != saved_cron:
        pending["cron"] = current_cron
    else:
        pending.pop("cron", None)
    if not pending:
        app._schedule_pending.pop(profile_name, None)

    _update_schedule_dirty(app)


def _update_interpretation(app):
    minute = app.schedule_cron_entries["minute"].get_text().strip() or "*"
    hour = app.schedule_cron_entries["hour"].get_text().strip() or "*"
    day = app.schedule_cron_entries["day"].get_text().strip() or "*"
    month = app.schedule_cron_entries["month"].get_text().strip() or "*"
    weekday = app.schedule_cron_entries["weekday"].get_text().strip() or "*"

    prose = interpret_cron(minute, hour, day, month, weekday)
    app.schedule_interpret_label.set_markup(f"<b>Interpretation:</b> {prose}")

    examples = format_next_runs(minute, hour, day, month, weekday, count=3)
    app.schedule_examples_label.set_markup(f"<b>Examples:</b>\n{examples}")


def _regenerate_cron(app):
    profiles = list_profiles()
    script_dir = os.path.dirname(os.path.realpath(__file__))
    if "/usr/local/lib/zfsutilities/versions/" in script_dir:
        # Running from a deployed version: use the current symlink so the
        # cron job tracks version switches automatically.
        runner_path = "/usr/local/lib/zfsutilities/current/07 GTK + Python/profile_runner.py"
    else:
        runner_path = os.path.join(script_dir, "profile_runner.py")
    try:
        write_cron_file(profiles, runner_path)
    except OSError as e:
        _show_error_dialog(app, f"Failed to update cron file:\n{e}")


def _show_error_dialog(app, message):
    dlg = Gtk.MessageDialog(
        transient_for=app, modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    dlg.run()
    dlg.destroy()


def _resolve_profile_runner_path():
    """Return the profile_runner.py path to use for ad-hoc runs.

    Mirrors the logic in _regenerate_cron so Run Now uses the same runner
    that cron uses.
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))
    if "/usr/local/lib/zfsutilities/versions/" in script_dir:
        return "/usr/local/lib/zfsutilities/current/07 GTK + Python/profile_runner.py"
    return os.path.join(script_dir, "profile_runner.py")


def _log_profile_line(fd, condition, app, profile_name, prefix):
    """GLib io_add_watch callback: stream one line to the GUI log panel."""
    if condition & GLib.IOCondition.IN:
        try:
            data = os.read(fd, 8192)
            if data:
                for line in data.decode("utf-8", errors="replace").splitlines():
                    log_msg(f"{prefix}{line}")
                return True
        except OSError:
            pass
    return False


def _on_profile_finished(pid, status, user_data):
    """GLib child_watch_add callback: reap finished profile run."""
    app, profile_name, process = user_data
    try:
        process.wait()
    except Exception:
        pass
    running = getattr(app, "_running_profiles", None)
    if running is not None:
        running.discard(profile_name)
    log_msg(f"INFO: Profile finished: {profile_name}")
    app.update_action_buttons("schedule")


def _run_profile_now(app, profile_name):
    """Launch profile_runner.py for *profile_name* and stream its output."""
    runner_path = _resolve_profile_runner_path()
    log_msg(f"INFO: Running profile now: {profile_name}")
    try:
        process = subprocess.Popen(
            [sys.executable, runner_path, "run", profile_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        log_msg(f"WARN: Could not start profile {profile_name}: {exc}")
        return

    if not hasattr(app, "_running_profiles"):
        app._running_profiles = set()
    app._running_profiles.add(profile_name)
    app.update_action_buttons("schedule")

    prefix = f"[{profile_name}] "
    try:
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stderr.fileno(), False)
        GLib.io_add_watch(
            process.stdout.fileno(), GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN | GLib.IOCondition.HUP,
            _log_profile_line, app, profile_name, prefix,
        )
        GLib.io_add_watch(
            process.stderr.fileno(), GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN | GLib.IOCondition.HUP,
            _log_profile_line, app, profile_name, prefix,
        )
        GLib.child_watch_add(
            GLib.PRIORITY_DEFAULT, process.pid, _on_profile_finished,
            (app, profile_name, process),
        )
    except Exception as exc:
        log_msg(f"FATAL: Could not watch profile {profile_name} output: {exc}")
        try:
            process.terminate()
        except Exception:
            pass
        app._running_profiles.discard(profile_name)
        app.update_action_buttons("schedule")


def on_schedule_run_now(app):
    """Run all selected profiles immediately, ignoring their Active status."""
    selection = app.schedule_view.get_selection()
    model, paths = selection.get_selected_rows()
    if not paths:
        log_msg("WARN: No profile selected")
        return

    for path in paths:
        tree_iter = model.get_iter(path)
        profile_name = model.get_value(tree_iter, COL_NAME)
        _run_profile_now(app, profile_name)


def on_schedule_save(app):
    if not app._schedule_pending:
        return

    for profile_name, changes in list(app._schedule_pending.items()):
        profile = load_profile(profile_name)
        if profile is None:
            log_msg(f"WARN: Profile not found: {profile_name}")
            continue

        if "active" in changes:
            profile["active"] = changes["active"]
        if "cron" in changes:
            profile["cron"] = changes["cron"]
        save_profile(profile)

        tree_iter = _find_iter_by_name(app, profile_name)
        if tree_iter is not None:
            app.schedule_store.set_value(
                tree_iter, COL_ACTIVE, profile.get("active", False)
            )
            app.schedule_store.set_value(
                tree_iter, COL_SCHEDULE, _format_cron(profile.get("cron", {}))
            )
            _update_next_run_for_iter(app, tree_iter)

    _regenerate_cron(app)
    app._schedule_pending.clear()
    _update_schedule_dirty(app)
    log_msg("INFO: Updated schedule profiles")


def on_schedule_revert(app):
    """Revert pending schedule changes to last-saved state."""
    if app._schedule_pending:
        for profile_name in list(app._schedule_pending.keys()):
            profile = load_profile(profile_name)
            if profile is None:
                continue
            tree_iter = _find_iter_by_name(app, profile_name)
            if tree_iter is not None:
                app.schedule_store.set_value(
                    tree_iter, COL_ACTIVE, profile.get("active", False)
                )
                app.schedule_store.set_value(
                    tree_iter, COL_SCHEDULE, _format_cron(profile.get("cron", {}))
                )
                _update_next_run_for_iter(app, tree_iter)
        app._schedule_pending.clear()

    selection = app.schedule_view.get_selection()
    model, paths = selection.get_selected_rows()
    if paths:
        tree_iter = model.get_iter(paths[0])
        profile_name = model.get_value(tree_iter, COL_NAME)
        profile = load_profile(profile_name)
        if profile is not None:
            app._schedule_ignore_changes = True
            load_schedule_config(app, profile.get("cron", {}))
            app._schedule_ignore_changes = False
            _update_interpretation(app)

    _update_schedule_dirty(app)
    log_msg("INFO: Reverted schedule changes")


def _update_schedule_dirty(app):
    """Style the Save button red whenever pending schedule changes exist."""
    dirty = bool(app._schedule_pending)
    btn = getattr(app, "_schedule_save_button", None)
    if btn:
        set_button_markup_red(btn, dirty)


def check_schedule_dirty(app):
    """Style the Save button based on pending schedule changes."""
    _update_schedule_dirty(app)


def mark_schedule_clean(app):
    """Clear pending state and reset the Save button."""
    app._schedule_pending.clear()
    _update_schedule_dirty(app)


def _find_iter_by_name(app, profile_name):
    """Return the TreeIter for the given profile name, or None."""
    for row in app.schedule_store:
        if row[COL_NAME] == profile_name:
            return row.iter
    return None


def on_schedule_delete(app):
    selection = app.schedule_view.get_selection()
    model, paths = selection.get_selected_rows()
    if not paths:
        log_msg("WARN: No profile selected")
        return

    tree_iter = model.get_iter(paths[0])
    profile_name = model.get_value(tree_iter, COL_NAME)

    dlg = Gtk.MessageDialog(
        transient_for=app, modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Delete profile '{profile_name}'?",
    )
    dlg.format_secondary_text(
        "This will remove the profile and its cron entry. This cannot be undone."
    )
    response = dlg.run()
    dlg.destroy()
    if response != Gtk.ResponseType.YES:
        return

    delete_profile(profile_name)
    _regenerate_cron(app)
    _refresh_profile_list(app)
    log_msg(f"INFO: Deleted profile: {profile_name}")
