"""
Logs tab UI — browse, view, and prune session log files.

Log files live in /var/log/zfsutilities/sessions/ and are named:
    YYYY-MM-DD_HH-MM-SS_<type>_<name>.log
"""

import os
import re
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk, Gio

from logging_config import (
    log_msg, MSG_LEVELS, DEFAULT_MSG_LEVEL,
    parse_msg_level, viewer_should_show,
    format_log_text_short,
)
from config_core import (
    prune_old_logs,
    get_log_retention_days, save_log_retention_days,
    get_history_retention_days, SESSION_LOG_DIR,
)
from log_index import LogIndex
from backup_history import load_history, get_success_rate, format_duration
from gui_helpers import (
    LogPopoutWindow, TextViewSearch, set_monospace_font,
    configure_treeview_column, bold_label,
)

# Column indices
COL_DATETIME = 0
COL_TYPE = 1
COL_NAME = 2
COL_STATUS = 3
COL_SIZE = 4
COL_DURATION = 5
COL_BYTES = 6
COL_PATH = 7

# Maximum log file size the viewer will load from the beginning.  Larger files
# are shown tail-only to avoid hanging the GUI on a multi-gigabyte session log.
MAX_VIEWER_FULL_READ_BYTES = 1024 * 1024  # 1 MB

# Maximum characters the live log viewer will keep in its TextBuffer while
# tailing a running log.  Older text is dropped to prevent unbounded memory
# growth when a subprocess logs continuously.
MAX_VIEWER_BUFFER_CHARS = 2 * 1024 * 1024  # 2 MB

# Regex: ^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_(\w+)_(.+)\.log$
# Purpose: Parse session log filenames into (date, time, type, name).
# Supports both new format (type first) and legacy format (gui first).
# Group 1: ISO date   e.g. "2026-05-11"
# Group 2: Time       e.g. "16-42-30"
# Group 3: Log type   e.g. "backup", "offsite", "gui"
# Group 4: Base name  e.g. "gui", "profile-Daily", "offsite_backup"
# Examples:
#   "2026-05-11_16-42-30_backup_gui.log"              -> type=backup, name=gui
#   "2026-05-11_16-42-30_offsite_profile-Weekly.log"  -> type=offsite, name=profile-Weekly
#   "2026-05-11_16-42-30_gui_offsite_backup.log"      -> type=gui, name=offsite_backup (legacy)
_LOG_FILENAME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_"
    r"(backup|offsite|restore|prune|gui)_(.+)\.log$"
)

_CHUNK_READ_BYTES = 256 * 1024  # 256 KB per "Show More" click

# Regex: # END: (?:rc=(\d+)|cancelled), duration=([\d.]+)s(?:, bytes=(\d+))?
# Purpose: Parse the structured trailer written by BackupRunner and profile_runner
#          to extract result code, duration, and optional bytes transferred.
# Group 1: Return code integer (only present for rc=N form)
# Group 2: Duration in seconds as float  e.g. "123.4"
# Group 3: Bytes transferred (optional)  e.g. "1073741824"
# Examples:
#   "# END: rc=0, duration=123.4s, bytes=1073741824" -> match
#   "# END: cancelled, duration=45.0s" -> match
#   "# END: rc=1, duration=9.0s" -> match
#   "2026-05-20 21:55:15  INFO: done" -> no match
_TRAILER_RE = re.compile(
    r"# END: (?:rc=(\d+)|cancelled), duration=([\d.]+)s(?:, bytes=(\d+))?"
)


def _filter_log_text(text, min_level):
    """Return only lines from *text* visible at *min_level*.

    Lines without a recognized level (e.g., raw subprocess output, END
    trailers) use the implied "(none)" level and are always displayed.
    """
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        level = parse_msg_level(line)
        if viewer_should_show(level, min_level):
            out.append(line)
    return "".join(out)


def _parse_log_filename(name):
    """Parse a log filename into (datetime_str, type, name) or None."""
    m = _LOG_FILENAME_RE.match(name)
    if not m:
        return None
    date_part, time_part, log_type, log_name = m.groups()
    dt = f"{date_part} {time_part.replace('-', ':')}"
    return dt, log_type, log_name


def _format_size(size):
    """Format byte size human-readably."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _scan_logs(app):
    """Scan SESSION_LOG_DIR and return list of row tuples for the model.

    Uses and updates the persistent log index so historical logs are not
    re-read on every refresh.
    """
    rows = []
    if not os.path.isdir(SESSION_LOG_DIR):
        return rows

    index = getattr(app, "_log_index", None)
    if index is None:
        index = LogIndex.load()
        app._log_index = index

    current_paths = set()
    index_file_name = ".log_index.json"
    for name in sorted(os.listdir(SESSION_LOG_DIR), reverse=True):
        if name.startswith(".") or name == index_file_name:
            continue
        path = os.path.join(SESSION_LOG_DIR, name)
        if not os.path.isfile(path):
            continue
        parsed = _parse_log_filename(name)
        if not parsed:
            continue

        current_paths.add(path)
        entry = index.update(path)

        dt, log_type, log_name = parsed
        size = entry.get("size", 0)
        status = entry.get("status", "Done")
        duration_str = ""
        bytes_str = ""
        if entry.get("duration") is not None:
            duration_str = format_duration(entry["duration"])
        if entry.get("bytes_transferred") is not None:
            bytes_str = _format_size(entry["bytes_transferred"])

        # Surface WARN/FATAL in the Status column for finished logs.
        if status not in ("Running", "Cancelled"):
            highest = entry.get("highest_level")
            if highest in ("WARN", "FATAL"):
                status = highest.title()

        rows.append((dt, log_type, log_name, status, _format_size(size),
                     duration_str, bytes_str, path))

    index.remove_missing(current_paths)
    index.save()

    return rows


def _on_logs_popout_toggled(button, app, viewer_box, viewer_frame):
    """Toggle the Logs tab viewer between the tab and a pop-out window."""
    if button.get_active():
        viewer_frame.remove(viewer_box)
        app.logs_popout_window.box.pack_start(viewer_box, True, True, 0)
        app.logs_popout_window.show_all()
    else:
        app.logs_popout_window.box.remove(viewer_box)
        viewer_frame.add(viewer_box)
        app.logs_popout_window.hide()


def create_logs_page(app):
    """Build and return the Logs tab widget."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.set_margin_start(10)
    outer.set_margin_end(10)
    outer.set_margin_top(10)
    outer.set_margin_bottom(10)

    # Title
    title = Gtk.Label()
    title.set_markup("<big><b>Logs</b></big>")
    title.set_halign(Gtk.Align.START)
    outer.pack_start(title, False, False, 0)
    outer.pack_start(Gtk.Separator(), False, False, 0)

    # Success-rate summary
    app.logs_success_rate_label = Gtk.Label()
    app.logs_success_rate_label.set_halign(Gtk.Align.START)
    _update_success_rate_label(app)
    outer.pack_start(app.logs_success_rate_label, False, False, 0)

    # Controls row — retention days and viewer level filter
    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    controls.set_margin_bottom(5)

    controls.pack_start(Gtk.Label(label="Retention (days):"), False, False, 0)
    app.logs_retention_spin = Gtk.SpinButton()
    app.logs_retention_spin.set_range(0, 3650)
    app.logs_retention_spin.set_increments(1, 10)
    app.logs_retention_spin.set_value(get_log_retention_days(app.config))
    app.logs_retention_spin.connect("value-changed", _on_retention_changed, app)
    controls.pack_start(app.logs_retention_spin, False, False, 0)

    outer.pack_start(controls, False, False, 0)

    # Top pane: log list
    app.logs_store = Gtk.ListStore(str, str, str, str, str, str, str, str)
    app.logs_view = Gtk.TreeView(model=app.logs_store)
    app.logs_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.logs_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    cols = [
        (COL_DATETIME, "Date/Time", 160, "Session log timestamp"),
        (COL_TYPE, "Type", 70, "Log type: backup, offsite, restore, prune, or gui"),
        (COL_NAME, "Name", 140, "Name of the operation or profile"),
        (COL_STATUS, "Status", 70, "Completion status"),
        (COL_SIZE, "Log Size", 65, "Size of the log file on disk"),
        (COL_DURATION, "Duration", 65, "Elapsed run time"),
        (COL_BYTES, "Transfer", 70, "Bytes transferred during the operation"),
    ]
    for col_idx, title_text, width, tooltip in cols:
        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", False)
        if col_idx == COL_DATETIME:
            set_monospace_font(renderer)
        column = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        configure_treeview_column(column, width=width)
        column.set_sort_column_id(col_idx)

        # TreeViewColumn is not a Gtk.Widget, so tooltips must live on the
        # header label instead of on the column itself.
        header = Gtk.Label(label=title_text)
        header.set_tooltip_text(tooltip)
        header.show_all()
        column.set_widget(header)

        app.logs_view.append_column(column)
    app._ui_state.bind_treeview(app.logs_view, "logs_view")

    list_scroll = Gtk.ScrolledWindow()
    list_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    list_scroll.set_min_content_height(200)
    list_scroll.add(app.logs_view)
    outer.pack_start(list_scroll, True, True, 0)

    # Bottom pane: log viewer
    viewer_frame = Gtk.Frame()
    viewer_frame.set_label_widget(bold_label("Log Viewer"))
    viewer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    viewer_box.set_margin_start(5)
    viewer_box.set_margin_end(5)
    viewer_box.set_margin_top(5)
    viewer_box.set_margin_bottom(5)
    viewer_frame.add(viewer_box)
    outer.pack_start(viewer_frame, True, True, 0)

    app.logs_text = Gtk.TextView()
    app.logs_text.set_editable(False)
    app.logs_text.set_cursor_visible(False)
    app.logs_text.set_wrap_mode(Gtk.WrapMode.CHAR)
    app.logs_text.set_monospace(True)
    app.logs_text.set_left_margin(5)
    app.logs_text.set_right_margin(5)
    app.logs_text_scroll = Gtk.ScrolledWindow()
    app.logs_text_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    app.logs_text_scroll.set_min_content_height(200)
    app.logs_text_scroll.add(app.logs_text)

    # Viewer toolbar: level filter + short-prefix toggle + search + pop-out
    app.logs_viewer_level = DEFAULT_MSG_LEVEL
    app.logs_level_combo = Gtk.ComboBoxText()
    for level in MSG_LEVELS:
        app.logs_level_combo.append_text(level)
    app.logs_level_combo.set_active(MSG_LEVELS.index(app.logs_viewer_level))
    app.logs_level_combo.set_tooltip_text("Filter messages shown in the log viewer")
    app.logs_level_combo.connect("changed", _on_logs_level_changed, app)

    app.logs_short_prefix = True
    app._logs_short_prefix_toggle = Gtk.ToggleButton(label="Short prefix")
    app._logs_short_prefix_toggle.set_active(True)
    app._logs_short_prefix_toggle.set_tooltip_text(
        "Show only date and time in the log viewer"
    )
    app._logs_short_prefix_toggle.connect(
        "toggled", _on_logs_short_prefix_toggled, app
    )

    viewer_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    viewer_toolbar.pack_start(Gtk.Label(label="Level:"), False, False, 0)
    viewer_toolbar.pack_start(app.logs_level_combo, False, False, 0)
    viewer_toolbar.pack_start(app._logs_short_prefix_toggle, False, False, 0)

    # Search bar inside viewer pane
    app.logs_search = TextViewSearch(app.logs_text)
    search_box = app.logs_search.widget
    viewer_toolbar.pack_start(search_box, True, True, 0)

    # Pop-out toggle button for log viewer
    app._logs_popout_toggle = Gtk.ToggleButton()
    app._logs_popout_toggle.set_image(
        Gtk.Image.new_from_icon_name("window-new", Gtk.IconSize.BUTTON)
    )
    app._logs_popout_toggle.set_tooltip_text(
        "Pop out log viewer into a separate window"
    )
    app._logs_popout_toggle.connect(
        "toggled", _on_logs_popout_toggled, app, viewer_box, viewer_frame
    )
    viewer_toolbar.pack_start(app._logs_popout_toggle, False, False, 0)

    viewer_box.pack_start(viewer_toolbar, False, False, 0)
    viewer_box.pack_start(app.logs_text_scroll, True, True, 0)

    # Create pop-out window for log viewer (hidden by default)
    app.logs_popout_window = LogPopoutWindow(
        app,
        title="ZFS Utilities — Log Viewer",
        toggle_widget=app._logs_popout_toggle,
    )

    # Show More button (hidden until needed)
    app.logs_show_more_btn = Gtk.Button(label="Show More")
    app.logs_show_more_btn.set_no_show_all(True)
    app.logs_show_more_btn.hide()
    app.logs_show_more_btn.connect("clicked", lambda _b: _load_next_chunk(app))
    viewer_box.pack_start(app.logs_show_more_btn, False, False, 0)

    # Load Full Log button for large files (hidden until needed)
    app.logs_load_full_btn = Gtk.Button(label="Load Full Log")
    app.logs_load_full_btn.set_no_show_all(True)
    app.logs_load_full_btn.hide()
    app.logs_load_full_btn.set_tooltip_text(
        "Load the entire log file (may be slow for very large files)"
    )
    app.logs_load_full_btn.connect(
        "clicked", lambda _b: _on_load_full_log_clicked(app)
    )
    viewer_box.pack_start(app.logs_load_full_btn, False, False, 0)

    # Track current file and read offset for chunked loading
    app._logs_current_path = None
    app._logs_read_offset = 0
    app._logs_file_size = 0
    app._logs_full_mode = False
    app._logs_tail_timer = None
    app._logs_sync_debounce_id = None

    # Selection change loads viewer and updates action button sensitivity
    selection = app.logs_view.get_selection()
    selection.connect("changed", _on_selection_changed, app)
    selection.connect("changed", _on_logs_selection_changed, app)

    # Right-click context menu
    app.logs_view.connect("button-press-event", _on_log_button_press, app)

    # Initial load
    _sync_log_list(app)

    # Default sort descending by Date/Time
    app.logs_store.set_sort_column_id(COL_DATETIME, Gtk.SortType.DESCENDING)

    # Watch the sessions directory for async updates
    dir_file = Gio.File.new_for_path(SESSION_LOG_DIR)
    app._logs_file_monitor = dir_file.monitor_directory(
        Gio.FileMonitorFlags.NONE, None
    )
    app._logs_file_monitor.connect("changed", _on_dir_changed, app)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.add(outer)
    return scrolled


def _sync_log_list(app):
    """Rescan the sessions directory and update the list incrementally.

    Preserves the current selection and viewer state when the selected
    file still exists.  Only reloads the viewer when the selection
    actually changes.
    """
    selection = app.logs_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    selected_paths = {model.get_value(model.get_iter(p), COL_PATH) for p in pathlist}

    current_rows = _scan_logs(app)
    current_by_path = {r[COL_PATH]: r for r in current_rows}

    # Remove rows for files that no longer exist
    iters_to_remove = []
    tree_iter = app.logs_store.get_iter_first()
    while tree_iter:
        path = app.logs_store.get_value(tree_iter, COL_PATH)
        if path not in current_by_path:
            iters_to_remove.append(tree_iter)
        tree_iter = app.logs_store.iter_next(tree_iter)
    for tree_iter in iters_to_remove:
        app.logs_store.remove(tree_iter)

    # Update existing rows and add new ones
    for row_data in current_rows:
        path = row_data[COL_PATH]
        found = False
        tree_iter = app.logs_store.get_iter_first()
        while tree_iter:
            if app.logs_store.get_value(tree_iter, COL_PATH) == path:
                found = True
                for col, val in enumerate(row_data):
                    app.logs_store.set_value(tree_iter, col, val)
                break
            tree_iter = app.logs_store.iter_next(tree_iter)
        if not found:
            app.logs_store.append(row_data)

    app.logs_store.set_sort_column_id(COL_DATETIME, Gtk.SortType.DESCENDING)

    # Restore multi-selection for paths that still exist
    if selected_paths:
        tree_iter = app.logs_store.get_iter_first()
        while tree_iter:
            path = app.logs_store.get_value(tree_iter, COL_PATH)
            if path in selected_paths:
                selection.select_iter(tree_iter)
            tree_iter = app.logs_store.iter_next(tree_iter)

    _update_success_rate_label(app)


def select_log_by_path(app, path):
    """Refresh the log list and select the row whose path matches.

    Returns True if the entry was found and selected, False otherwise.
    """
    if not path:
        return False
    _sync_log_list(app)
    tree_iter = app.logs_store.get_iter_first()
    while tree_iter:
        if app.logs_store.get_value(tree_iter, COL_PATH) == path:
            selection = app.logs_view.get_selection()
            selection.unselect_all()
            selection.select_iter(tree_iter)
            return True
        tree_iter = app.logs_store.iter_next(tree_iter)
    return False


def _on_dir_changed(_monitor, _file_obj, _other_file, event_type, app):
    """Debounced handler for directory change events."""
    if event_type not in (
        Gio.FileMonitorEvent.CHANGED,
        Gio.FileMonitorEvent.CREATED,
        Gio.FileMonitorEvent.DELETED,
        Gio.FileMonitorEvent.CHANGES_DONE_HINT,
    ):
        return
    if app._logs_sync_debounce_id is not None:
        GLib.source_remove(app._logs_sync_debounce_id)
    app._logs_sync_debounce_id = GLib.timeout_add(500, _do_sync_log_list, app)


def _do_sync_log_list(app):
    """Run the actual sync after the debounce period."""
    app._logs_sync_debounce_id = None
    _sync_log_list(app)
    return False


def _tail_log_file(app):
    """Periodic callback to append new lines from a running log file."""
    path = app._logs_current_path
    if not path or not os.path.isfile(path):
        app._logs_tail_timer = None
        return False

    try:
        size = os.path.getsize(path)
    except OSError:
        app._logs_tail_timer = None
        return False

    if size < app._logs_file_size:
        # File shrank — stop tailing
        app._logs_tail_timer = None
        return False

    if size > app._logs_file_size:
        try:
            with open(path, "rb") as fh:
                fh.seek(app._logs_read_offset)
                data = fh.read()
                app._logs_read_offset = fh.tell()
        except OSError as e:
            log_msg(f"WARN: Could not tail log file: {e}")
            return True

        if data:
            text = data.decode("utf-8", errors="replace")
            app._logs_file_size = size

            # Update the persistent index for the current file.
            index = getattr(app, "_log_index", None)
            if index is not None:
                entry = index.get(path)
                if entry is None:
                    entry = index.update(path)
                else:
                    from log_index import update_entry_incrementally
                    update_entry_incrementally(entry, path)
                    index._set(path, entry)
                index.save()

            filtered = _filter_log_text(text, app.logs_viewer_level)
            if filtered:
                if getattr(app, "logs_short_prefix", True):
                    filtered = format_log_text_short(filtered)
                buf = app.logs_text.get_buffer()

                # Prevent the live tail buffer from growing without bound.
                current_chars = buf.get_char_count()
                new_chars = len(filtered)
                if current_chars + new_chars > MAX_VIEWER_BUFFER_CHARS:
                    drop_target = (current_chars + new_chars) // 2
                    drop_end = buf.get_iter_at_offset(drop_target)
                    buf.delete(buf.get_start_iter(), drop_end)
                    log_msg(
                        "WARN: Log viewer buffer truncated to prevent "
                        "excessive memory use"
                    )

                # Only auto-scroll if the user is already near the bottom
                vadj = app.logs_text_scroll.get_vadjustment()
                at_bottom = (
                    vadj.get_value()
                    >= vadj.get_upper() - vadj.get_page_size() - 5
                )

                end_iter = buf.get_end_iter()
                buf.insert(end_iter, filtered)

                if at_bottom:
                    scroll_mark = buf.create_mark(None, buf.get_end_iter(), False)
                    app.logs_text.scroll_to_mark(scroll_mark, 0.0, False, 0.0, 0.0)
                    buf.delete_mark(scroll_mark)

            if "# END:" in text:
                app._logs_tail_timer = None
                _sync_log_list(app)
                return False

    return True


def _on_log_button_press(treeview, event, app):
    """Handle right-click on the log list to show a context menu."""
    if event.button != 3:  # Right-click only
        return False

    # Get the row under the cursor
    path_info = treeview.get_path_at_pos(int(event.x), int(event.y))
    if path_info is None:
        return False
    tree_path, column, cell_x, cell_y = path_info

    # Select the row that was right-clicked if it is not already selected
    selection = treeview.get_selection()
    if not selection.path_is_selected(tree_path):
        selection.unselect_all()
        selection.select_path(tree_path)

    model = treeview.get_model()
    tree_iter = model.get_iter(tree_path)
    log_path = model.get_value(tree_iter, COL_PATH)

    menu = Gtk.Menu()
    copy_item = Gtk.MenuItem(label="Copy path to clipboard")
    copy_item.connect(
        "activate",
        lambda _i: _copy_log_path_to_clipboard(log_path),
    )
    menu.append(copy_item)

    delete_item = Gtk.MenuItem(label="Delete selected log(s)")
    delete_item.connect("activate", lambda _i: _on_delete_selected(app))
    menu.append(delete_item)

    menu.show_all()
    menu.popup_at_pointer(event)
    return True


def _copy_log_path_to_clipboard(log_path):
    """Copy the given log file path to the desktop clipboard."""
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(log_path, -1)
    clipboard.store()
    log_msg(f"INFO: Copied log path to clipboard: {log_path}")


def _setup_logs_actions(app):
    """Initialise Logs tab action button states after the buttons exist."""
    _on_logs_selection_changed(app.logs_view.get_selection(), app)


def _on_logs_selection_changed(selection, app):
    """Enable or disable the Delete Selected action button."""
    button = getattr(app, "_logs_delete_button", None)
    if button is None:
        return
    _model, pathlist = selection.get_selected_rows()
    button.set_sensitive(bool(pathlist))


def _load_log_into_viewer(app):
    """Load the current log file into the viewer, tail-first if it is huge."""
    path = app._logs_current_path
    if not path or not os.path.isfile(path):
        return

    size = app._logs_file_size
    buf = app.logs_text.get_buffer()
    app.logs_show_more_btn.hide()
    app.logs_load_full_btn.hide()

    if not getattr(app, "_logs_full_mode", False) and size > MAX_VIEWER_FULL_READ_BYTES:
        # Tail-only mode: show the last MAX_VIEWER_FULL_READ_BYTES plus a header.
        try:
            with open(path, "rb") as fh:
                fh.seek(max(0, size - MAX_VIEWER_FULL_READ_BYTES))
                fh.readline()  # discard the likely-partial first line
                app._logs_read_offset = fh.tell()
        except OSError as e:
            log_msg(f"WARN: Could not seek log file: {e}")
            return

        header = (
            f"[Log file is {_format_size(size)}; showing last "
            f"{_format_size(MAX_VIEWER_FULL_READ_BYTES)}. "
            f"Use 'Load Full Log' to read from the beginning.]\n"
        )
        buf.set_text(header)
        _load_next_chunk(app)
        while app.logs_show_more_btn.get_visible():
            _load_next_chunk(app)
        app.logs_load_full_btn.show()
    else:
        # Full-file mode (default for files under the threshold).
        app._logs_read_offset = 0
        _load_next_chunk(app)
        while app.logs_show_more_btn.get_visible():
            _load_next_chunk(app)


def _on_load_full_log_clicked(app):
    """Prompt and switch the viewer from tail mode to full-file mode."""
    path = app._logs_current_path
    if not path:
        return
    try:
        size = os.path.getsize(path)
    except OSError:
        return

    if size > MAX_VIEWER_FULL_READ_BYTES:
        dialog = Gtk.MessageDialog(
            transient_for=app.get_active_window(),
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=(
                f"The log file is {_format_size(size)}. Loading it fully "
                f"may be slow or use a lot of memory. Continue?"
            ),
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return

    app._logs_full_mode = True
    app.logs_text.get_buffer().set_text("")
    _load_log_into_viewer(app)


def _on_selection_changed(selection, app):
    """Load the selected log file into the viewer."""
    # Stop any existing tail timer
    if app._logs_tail_timer is not None:
        GLib.source_remove(app._logs_tail_timer)
        app._logs_tail_timer = None

    model, pathlist = selection.get_selected_rows()
    if not pathlist:
        app.logs_text.get_buffer().set_text("")
        app._logs_current_path = None
        app.logs_show_more_btn.hide()
        app.logs_load_full_btn.hide()
        app.logs_search.clear()
        return

    tree_iter = model.get_iter(pathlist[0])
    path = model.get_value(tree_iter, COL_PATH)
    status = model.get_value(tree_iter, COL_STATUS)

    # If the same file is already loaded, just restart tailing when running
    if path == app._logs_current_path:
        if status == "Running":
            app._logs_tail_timer = GLib.timeout_add_seconds(
                1, _tail_log_file, app
            )
        return

    app._logs_current_path = path
    app._logs_read_offset = 0
    app._logs_full_mode = False
    try:
        app._logs_file_size = os.path.getsize(path)
    except OSError:
        app._logs_file_size = 0

    query = app.logs_search.entry.get_text()
    app.logs_search.clear(keep_query=True)
    buf = app.logs_text.get_buffer()
    buf.set_text("")

    # Load all existing chunks so the viewer is at the current end
    _load_log_into_viewer(app)

    if query:
        app.logs_search.search()

    # Start tailing if the log is still running
    if status == "Running":
        app._logs_tail_timer = GLib.timeout_add_seconds(1, _tail_log_file, app)


def _on_logs_short_prefix_toggled(button, app):
    """Re-load the current log with the short- or full-prefix display."""
    app.logs_short_prefix = button.get_active()
    if not app._logs_current_path:
        return

    vadj = app.logs_text_scroll.get_vadjustment()
    old_value = vadj.get_value()
    old_upper = vadj.get_upper()

    app.logs_text.get_buffer().set_text("")
    _load_log_into_viewer(app)

    query = app.logs_search.entry.get_text()
    if query:
        app.logs_search.search()

    def _restore_scroll():
        new_upper = vadj.get_upper()
        new_page = vadj.get_page_size()
        if old_upper > new_page:
            ratio = old_value / (old_upper - new_page)
        else:
            ratio = 0.0
        target = ratio * max(0, new_upper - new_page)
        vadj.set_value(min(target, new_upper - new_page))
        return False

    GLib.idle_add(_restore_scroll)


def _on_logs_level_changed(combo, app):
    """Apply the selected level filter to the current log viewer contents."""
    active = combo.get_active_text()
    if active is None or active == app.logs_viewer_level:
        return
    app.logs_viewer_level = active

    vadj = app.logs_text_scroll.get_vadjustment()
    old_value = vadj.get_value()
    old_upper = vadj.get_upper()

    # Re-read the file with the new filter (respecting tail/full mode).
    app.logs_text.get_buffer().set_text("")
    _load_log_into_viewer(app)

    query = app.logs_search.entry.get_text()
    if query:
        app.logs_search.search()

    def _restore_scroll():
        new_upper = vadj.get_upper()
        new_page = vadj.get_page_size()
        if old_upper > new_page:
            ratio = old_value / (old_upper - new_page)
        else:
            ratio = 0.0
        target = ratio * max(0, new_upper - new_page)
        vadj.set_value(min(target, new_upper - new_page))
        return False

    GLib.idle_add(_restore_scroll)


def _load_next_chunk(app):
    """Read the next chunk of the current log file into the viewer."""
    path = app._logs_current_path
    if not path or not os.path.isfile(path):
        return

    try:
        with open(path, "rb") as fh:
            fh.seek(app._logs_read_offset)
            data = fh.read(_CHUNK_READ_BYTES)
            app._logs_read_offset = fh.tell()
    except OSError as e:
        log_msg(f"WARN: Could not read log file: {e}")
        return

    if not data:
        app.logs_show_more_btn.hide()
        return

    text = data.decode("utf-8", errors="replace")
    filtered = _filter_log_text(text, app.logs_viewer_level)
    if filtered:
        if getattr(app, "logs_short_prefix", True):
            filtered = format_log_text_short(filtered)
        buf = app.logs_text.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, filtered)

    # Show/hide Show More button
    if app._logs_read_offset < app._logs_file_size:
        app.logs_show_more_btn.show()
    else:
        app.logs_show_more_btn.hide()


def _on_delete_selected(app):
    """Delete all selected log files after confirmation."""
    selection = app.logs_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if not pathlist:
        log_msg("WARN: No log selected")
        return

    paths = []
    for tree_path in pathlist:
        tree_iter = model.get_iter(tree_path)
        paths.append(model.get_value(tree_iter, COL_PATH))

    count = len(paths)
    names = [os.path.basename(p) for p in paths]
    preview = ", ".join(names[:3])
    if count > 3:
        preview += f" and {count - 3} more"

    dlg = Gtk.MessageDialog(
        transient_for=app, modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Delete {count} selected log files?",
    )
    dlg.format_secondary_text(f"{preview}\nThis cannot be undone.")
    response = dlg.run()
    dlg.destroy()
    if response != Gtk.ResponseType.YES:
        return

    deleted = 0
    index = getattr(app, "_log_index", None)
    for path in paths:
        name = os.path.basename(path)
        try:
            os.remove(path)
            if index is not None:
                index.remove(path)
            log_msg(f"INFO: Deleted log: {name}")
            deleted += 1
        except OSError as e:
            log_msg(f"WARN: Could not delete log '{name}': {e}")

    if index is not None:
        index.save()

    if deleted:
        _sync_log_list(app)


def _on_prune_old(app):
    """Prune log files older than the configured retention."""
    days = int(app.logs_retention_spin.get_value())
    prune_old_logs(days)
    _sync_log_list(app)


def _update_success_rate_label(app):
    """Refresh the success-rate summary label from the history file."""
    try:
        days = get_history_retention_days(app.config)
        success, total, percent = get_success_rate(load_history(), days)
        if total == 0:
            text = "Success rate: no history yet"
        else:
            text = f"Success rate ({days} days): {percent} % ({success} / {total})"
    except Exception as e:
        log_msg(f"WARN: Could not compute success rate: {e}")
        text = "Success rate: unavailable"
    app.logs_success_rate_label.set_text(text)


def _on_retention_changed(spin, app):
    """Persist retention days when the spin button changes."""
    days = int(spin.get_value())
    try:
        save_log_retention_days(app.config, days)
    except ValueError as e:
        log_msg(f"WARN: {e}")
