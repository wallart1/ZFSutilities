"""
Checkagainst configuration page — edit the fss table stored in the JSON
config (config["checkagainst"]).

The page now shows three sections:

- Backup-derived entries: rows derived from active Backup send/receive steps.
- Offsite-derived entries: rows derived from active Offsite steps.
- User entries: manually maintained rows.

The Counterpart column accepts a literal pool/path (or "-" for no prefix)
and the special placeholder "<offsite>", which resolves at run-time to all
pools marked as offsite candidates in the Pools tab.
"""

import copy

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from logging_config import log_msg
from feature_config import (
    get_checkagainst, save_checkagainst, derive_checkagainst_entries,
    _compute_strip_segments, _reverse_checkagainst_row, get_pool_names,
)
from gui_helpers import configure_treeview_column, handle_editing_key_press

# Column indices in the ListStore (display order):
# Snapshot label, Source dataset, Strip leading segments,
# Destination dataset, Comment.
COL_LABEL       = 0
COL_DATASET     = 1
COL_QUALS       = 2
COL_COUNTERPART = 3
COL_COMMENT     = 4

# Titles shown on the user-entry column headers.
_COLUMN_TITLES = {
    COL_LABEL:       "Snapshot label",
    COL_DATASET:     "Source dataset",
    COL_QUALS:       "Strip leading segments",
    COL_COUNTERPART: "Destination dataset",
    COL_COMMENT:     "Comment",
}

# Tooltips for each column header.
_COLUMN_TOOLTIPS = {
    COL_LABEL:       "Snapshot label used to build snapshot names (e.g. offsite, dailybackup).",
    COL_DATASET:     "Source dataset whose snapshots are checked.",
    COL_QUALS:       "Number of leading path segments to remove from the source dataset.",
    COL_COUNTERPART: (
        "Destination dataset where the counterpart snapshot is expected "
        "(use - for none, <offsite> for all candidates)."
    ),
    COL_COMMENT:     "Optional note about this row.",
}


def _entries_from_config(app):
    """Load user checkagainst entries as 5-tuples from the JSON config."""
    data = get_checkagainst(app.config)
    return [
        (e.get("label", ""), e.get("dataset", ""), e.get("quals", "0"),
         e.get("counterpart", "-"), e.get("comment", ""))
        for e in data.get("user_entries", [])
    ]


def _derived_from_config(app, section):
    """Load backup_derived or offsite_derived rows as 5-tuples."""
    data = get_checkagainst(app.config)
    return [
        (e.get("label", ""), e.get("dataset", ""), e.get("quals", "0"),
         e.get("counterpart", "-"), e.get("comment", ""))
        for e in data.get(section, [])
    ]


def _row_to_dict(row):
    """Convert a 5-tuple store row into the config row dict."""
    return {
        "label":       row[COL_LABEL],
        "dataset":     row[COL_DATASET],
        "quals":       row[COL_QUALS],
        "counterpart": row[COL_COUNTERPART],
        "comment":     row[COL_COMMENT],
    }


# Page factory

def create_checkagainst_page(app):
    """Build and return the Checkagainst configuration page widget."""

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    outer.set_margin_start(12)
    outer.set_margin_end(12)
    outer.set_margin_top(10)
    outer.set_margin_bottom(10)

    # Header
    hdr = Gtk.Label()
    hdr.set_markup("<big><b>Checkagainst Table</b></big>")
    hdr.set_halign(Gtk.Align.START)
    outer.pack_start(hdr, False, False, 0)

    desc = Gtk.Label(
        label="Maps dataset pairs for incremental-backup safety checks. Before deleting a\n"
              "snapshot, the system verifies a counterpart snapshot exists in the paired dataset.\n"
              "Use <offsite> in the Destination dataset column to check against all "
              "offsite-candidate pools."
    )
    desc.set_halign(Gtk.Align.START)
    desc.set_line_wrap(True)
    outer.pack_start(desc, False, False, 0)

    # Derived sections
    app._ca_backup_store = Gtk.ListStore(str, str, str, str, str)
    app._ca_offsite_store = Gtk.ListStore(str, str, str, str, str)
    app._ca_store = Gtk.ListStore(str, str, str, str, str)

    app._ca_backup_active_chk = Gtk.CheckButton(label="Active")
    app._ca_backup_active_chk.set_tooltip_text(
        "Include backup-derived rows when the checkagainst table is evaluated."
    )
    app._ca_backup_active_chk.connect("toggled", _on_active_toggled, app)
    backup_section, backup_tv = _build_section_box(
        "Backup-derived entries", app._ca_backup_store,
        app._ca_backup_active_chk, "checkagainst_backup_derived_view",
    )
    outer.pack_start(backup_section, True, True, 0)
    app._ui_state.bind_treeview(backup_tv, "checkagainst_backup_derived_view")

    app._ca_offsite_active_chk = Gtk.CheckButton(label="Active")
    app._ca_offsite_active_chk.set_tooltip_text(
        "Include offsite-derived rows when the checkagainst table is evaluated."
    )
    app._ca_offsite_active_chk.connect("toggled", _on_active_toggled, app)
    offsite_section, offsite_tv = _build_section_box(
        "Offsite-derived entries", app._ca_offsite_store,
        app._ca_offsite_active_chk, "checkagainst_offsite_derived_view",
    )
    outer.pack_start(offsite_section, True, True, 0)
    app._ui_state.bind_treeview(offsite_tv, "checkagainst_offsite_derived_view")

    # User entries section
    user_frame = Gtk.Frame(label="User entries")
    user_frame.set_label_align(0.0, 0.5)
    user_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    user_box.set_margin_start(6)
    user_box.set_margin_end(6)
    user_box.set_margin_top(6)
    user_box.set_margin_bottom(6)
    user_frame.add(user_box)

    tv = Gtk.TreeView(model=app._ca_store)
    tv.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    tv.set_reorderable(True)
    app._ca_view = tv

    for col_idx in (COL_LABEL, COL_DATASET, COL_QUALS,
                     COL_COUNTERPART, COL_COMMENT):
        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", True)
        renderer.connect("edited", _on_cell_edited, app, col_idx)
        renderer.connect("editing-started", _on_editing_started, tv, col_idx)
        col = Gtk.TreeViewColumn(_COLUMN_TITLES[col_idx], renderer, text=col_idx)
        configure_treeview_column(col, width=_column_width(col_idx))
        col.set_widget(_build_header(_COLUMN_TITLES[col_idx]))
        col.get_widget().set_tooltip_text(_COLUMN_TOOLTIPS[col_idx])
        tv.append_column(col)
    app._ui_state.bind_treeview(app._ca_view, "checkagainst_view")

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.set_size_request(-1, 150)
    sw.add(tv)
    user_box.pack_start(sw, True, True, 0)

    outer.pack_start(user_frame, True, True, 0)

    # Status label
    app._ca_status_label = Gtk.Label()
    app._ca_status_label.set_halign(Gtk.Align.START)
    outer.pack_start(app._ca_status_label, False, False, 0)

    # Notes
    notes = Gtk.Label()
    notes.set_markup(
        "<small><b>How the destination dataset is constructed:</b>\n"
        "  1. <b>Remove</b> the first N path segments from the snapshot's dataset "
        "(N = Strip leading segments)\n"
        "  2. <b>Prepend</b> the Destination dataset prefix to the result\n\n"
        "<b>Special value:</b>\n"
        "  <b>&lt;offsite&gt;</b> may be used anywhere in the Source dataset or "
        "Destination dataset "
        "column. Every occurrence is replaced with every pool marked as an offsite "
        "candidate in the Pools tab.\n\n"
        "<b>Examples:</b>\n"
        "  Strip=0: poolA/data → remove nothing → prepend poolB → "
        "<b>poolB/poolA/data</b>\n"
        "  Strip=2: poolB/poolA/data → remove 'poolB/poolA' → "
        "prepend poolA → <b>poolA/data</b>\n"
        "  Strip=0, Destination=&lt;offsite&gt;: poolA/data → "
        "<b>z22tb/poolA/data</b>, <b>z40tb/poolA/data</b>, …\n"
        "  Source=&lt;offsite&gt;/temp, Strip=1, Destination=-: "
        "z22tb/temp → remove 'z22tb' → <b>temp</b>\n"
        "  Destination=poolA/&lt;offsite&gt;/backup: poolA/data → "
        "<b>poolA/z22tb/backup/poolA/data</b>, …</small>"
    )
    notes.set_halign(Gtk.Align.START)
    notes.set_line_wrap(True)
    outer.pack_start(notes, False, False, 6)

    # Load initial data
    _load_fss_into_store(app)

    return outer


def _column_width(col_idx):
    """Return a reasonable default width for a checkagainst column."""
    widths = {
        COL_LABEL:       100,
        COL_DATASET:     160,
        COL_QUALS:       130,
        COL_COUNTERPART: 160,
        COL_COMMENT:     140,
    }
    return widths.get(col_idx, 100)


def _build_header(title_text):
    """Build a TreeViewColumn header widget with title."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    lbl = Gtk.Label(label=title_text)
    box.pack_start(lbl, False, False, 0)
    box.show_all()
    return box


def _build_readonly_treeview(store, state_key):
    """Build a non-reorderable, non-editable TreeView for derived rows."""
    tv = Gtk.TreeView(model=store)
    tv.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    tv.set_reorderable(False)

    for col_idx in (COL_LABEL, COL_DATASET, COL_QUALS, COL_COUNTERPART, COL_COMMENT):
        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", False)
        col = Gtk.TreeViewColumn(_COLUMN_TITLES[col_idx], renderer, text=col_idx)
        configure_treeview_column(col, width=_column_width(col_idx))
        col.set_widget(_build_header(_COLUMN_TITLES[col_idx]))
        col.get_widget().set_tooltip_text(_COLUMN_TOOLTIPS[col_idx])
        tv.append_column(col)

    # Width persistence is useful even for read-only views.
    # The caller binds the view after it is attached to a toplevel.
    tv._ca_state_key = state_key

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.set_size_request(-1, 100)
    sw.add(tv)
    return tv, sw


def _build_section_box(title, store, checkbox, state_key):
    """Assemble a labeled section with an Active checkbox and a TreeView."""
    frame = Gtk.Frame(label=title)
    frame.set_label_align(0.0, 0.5)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_margin_start(6)
    box.set_margin_end(6)
    box.set_margin_top(6)
    box.set_margin_bottom(6)

    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    header.pack_start(checkbox, False, False, 0)
    box.pack_start(header, False, False, 0)

    tv, sw = _build_readonly_treeview(store, state_key)
    box.pack_start(sw, True, True, 0)

    frame.add(box)
    return frame, tv


# Internal helpers

def _load_store(store, entries):
    """Populate a ListStore with a list of 5-tuples."""
    store.clear()
    for entry in entries:
        store.append(list(entry))


def _load_fss_into_store(app):
    """Load all three sections from config and snapshot the saved state."""
    data = get_checkagainst(app.config)
    app._ca_backup_active_chk.set_active(
        data.get("backup_derived_active", True))
    app._ca_offsite_active_chk.set_active(
        data.get("offsite_derived_active", True))

    _load_store(app._ca_backup_store, _derived_from_config(app, "backup_derived"))
    _load_store(app._ca_offsite_store, _derived_from_config(app, "offsite_derived"))

    entries = _entries_from_config(app)
    _load_store(app._ca_store, entries)

    # Snapshot the loaded UI state, not the raw config, so that default
    # values applied by the UI do not create a false dirty state.
    app._ca_original_full = _full_dict_from_ui(app)
    _update_ca_status(app)


def _store_to_entries(store):
    return [(row[0], row[1], row[2], row[3], row[4]) for row in store]


def _full_dict_from_ui(app):
    """Collect the entire checkagainst dict from the current UI state."""
    return {
        "backup_derived_active": app._ca_backup_active_chk.get_active(),
        "offsite_derived_active": app._ca_offsite_active_chk.get_active(),
        "backup_derived": [
            _row_to_dict(row) for row in app._ca_backup_store
        ],
        "offsite_derived": [
            _row_to_dict(row) for row in app._ca_offsite_store
        ],
        "user_entries": [
            _row_to_dict(row) for row in app._ca_store
        ],
    }


def _is_ca_dirty(app):
    if not hasattr(app, '_ca_original_full'):
        return False
    return _full_dict_from_ui(app) != app._ca_original_full


def _validate_rows(rows, source):
    """Validate rows and return a list of human-readable errors."""
    errors = []
    for row in rows:
        label, dataset, quals, counterpart, _comment = row
        if not dataset or not counterpart or not label:
            errors.append(f"One or more {source} rows have empty required fields.")
            break
        try:
            q = int(quals)
            if q < 0:
                raise ValueError
        except ValueError:
            errors.append(
                f"{source} row '{dataset}': Strip leading segments must be a non-negative integer."
            )
    return errors


def _update_ca_status(app):
    errors = []
    errors.extend(_validate_rows(_store_to_entries(app._ca_backup_store), "Backup-derived"))
    errors.extend(_validate_rows(_store_to_entries(app._ca_offsite_store), "Offsite-derived"))
    errors.extend(_validate_rows(_store_to_entries(app._ca_store), "User"))

    if errors:
        app._ca_status_label.set_markup(
            "<span foreground='red'>" + "\n".join(errors) + "</span>"
        )
    elif _is_ca_dirty(app):
        app._ca_status_label.set_markup("<span foreground='orange'>Unsaved changes.</span>")
    else:
        app._ca_status_label.set_text("")

    # Also update Save button styling
    check_checkagainst_dirty(app)


def _on_active_toggled(checkbox, app):
    _update_ca_status(app)


def _on_cell_edited(renderer, path, new_text, app, col_idx):
    app._ca_store[path][col_idx] = new_text.strip()
    _update_ca_status(app)


def _on_editing_started(renderer, editable, path, treeview, col_idx):
    """Connect key-press on the editable to handle Tab/Shift+Tab."""
    editable.connect(
        "key-press-event", handle_editing_key_press,
        treeview, path, col_idx,
        [COL_LABEL, COL_DATASET, COL_QUALS, COL_COUNTERPART, COL_COMMENT])


def _on_ca_add(btn, app):
    app._ca_store.append(["offsite", "", "0", "-", ""])
    # Select and scroll to the new row
    path = Gtk.TreePath(len(app._ca_store) - 1)
    app._ca_view.scroll_to_cell(path, None, False, 0, 0)
    app._ca_view.set_cursor(path, app._ca_view.get_columns()[0], True)
    _update_ca_status(app)


def _on_ca_remove(btn, app):
    sel = app._ca_view.get_selection()
    model, tree_iter = sel.get_selected()
    if tree_iter:
        model.remove(tree_iter)
        _update_ca_status(app)


def _on_ca_save(btn, app):
    # Validate before saving
    errors = []
    errors.extend(_validate_rows(_store_to_entries(app._ca_backup_store), "Backup-derived"))
    errors.extend(_validate_rows(_store_to_entries(app._ca_offsite_store), "Offsite-derived"))
    errors.extend(_validate_rows(_store_to_entries(app._ca_store), "User"))
    if errors:
        _show_error(app, "Cannot save:\n" + "\n".join(errors))
        return
    try:
        data = _full_dict_from_ui(app)
        save_checkagainst(app.config, data)
    except OSError as e:
        _show_error(app, f"Failed to save checkagainst table:\n{e}")
        return
    app._ca_original_full = copy.deepcopy(data)
    log_msg("INFO: Checkagainst table saved to JSON config")
    _update_ca_status(app)


def _on_ca_revert(btn, app):
    if hasattr(app, '_ca_original_full'):
        app.config["checkagainst"] = copy.deepcopy(app._ca_original_full)
    _load_fss_into_store(app)


def _show_error(app, msg):
    dlg = Gtk.MessageDialog(
        transient_for=app, modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=msg,
    )
    dlg.run()
    dlg.destroy()


# Action handlers

def on_checkagainst_add(app):
    """Add a new row to the user entries table."""
    _on_ca_add(None, app)


def on_checkagainst_remove(app):
    """Remove the selected row from the user entries table."""
    _on_ca_remove(None, app)


def on_checkagainst_save(app):
    """Save the full checkagainst dict to the JSON config."""
    _on_ca_save(None, app)


def on_checkagainst_revert(app):
    """Revert to the last saved state."""
    _on_ca_revert(None, app)


def on_checkagainst_get_entries(app):
    """Refresh derived rows from the current Backup and Offsite configs."""
    backup_derived, offsite_derived = derive_checkagainst_entries(app.config)
    data = get_checkagainst(app.config)
    data["backup_derived"] = backup_derived
    data["offsite_derived"] = offsite_derived
    app.config["checkagainst"] = data

    _load_store(app._ca_backup_store, [
        (e.get("label", ""), e.get("dataset", ""), e.get("quals", "0"),
         e.get("counterpart", "-"), e.get("comment", ""))
        for e in backup_derived
    ])
    _load_store(app._ca_offsite_store, [
        (e.get("label", ""), e.get("dataset", ""), e.get("quals", "0"),
         e.get("counterpart", "-"), e.get("comment", ""))
        for e in offsite_derived
    ])

    log_msg(
        f"INFO: Derived {len(backup_derived)} backup and {len(offsite_derived)} "
        "offsite checkagainst entries"
    )
    _update_ca_status(app)


def _build_pair_rows(source, dest, label, comment=""):
    """Build the forward and reverse checkagainst rows for a source/dest pair."""
    strip_count, prefix = _compute_strip_segments(source, dest)
    forward = {
        "label": label,
        "dataset": source,
        "quals": str(strip_count),
        "counterpart": prefix,
        "comment": comment,
    }
    reverse = _reverse_checkagainst_row(source, dest, label)
    reverse["comment"] = comment
    return forward, reverse


def _show_add_pair_assistant(app):
    """Open a dialog that builds a forward and reverse Checkagainst row."""
    dlg = Gtk.Dialog(
        title="Add Checkagainst Pair",
        transient_for=app,
        modal=True,
        destroy_with_parent=True,
    )
    dlg.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    dlg.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dlg.set_default_response(Gtk.ResponseType.OK)

    content = dlg.get_content_area()
    content.set_spacing(10)
    content.set_margin_start(10)
    content.set_margin_end(10)
    content.set_margin_top(10)
    content.set_margin_bottom(10)

    grid = Gtk.Grid()
    grid.set_column_spacing(10)
    grid.set_row_spacing(8)
    grid.set_hexpand(True)
    content.pack_start(grid, True, True, 0)

    # Snapshot label
    label_lbl = Gtk.Label(label="Snapshot label:")
    label_lbl.set_halign(Gtk.Align.END)
    grid.attach(label_lbl, 0, 0, 1, 1)
    label_entry = Gtk.Entry()
    label_entry.set_text("offsite")
    label_entry.set_hexpand(True)
    label_entry.set_activates_default(True)
    grid.attach(label_entry, 1, 0, 1, 1)

    # Source dataset
    source_lbl = Gtk.Label(label="Source dataset:")
    source_lbl.set_halign(Gtk.Align.END)
    grid.attach(source_lbl, 0, 1, 1, 1)
    source_entry = Gtk.Entry()
    source_entry.set_hexpand(True)
    source_entry.set_activates_default(True)
    grid.attach(source_entry, 1, 1, 1, 1)

    # Destination dataset
    dest_lbl = Gtk.Label(label="Destination dataset:")
    dest_lbl.set_halign(Gtk.Align.END)
    grid.attach(dest_lbl, 0, 2, 1, 1)
    dest_entry = Gtk.Entry()
    dest_entry.set_hexpand(True)
    dest_entry.set_activates_default(True)
    grid.attach(dest_entry, 1, 2, 1, 1)

    # Comment
    comment_lbl = Gtk.Label(label="Comment:")
    comment_lbl.set_halign(Gtk.Align.END)
    grid.attach(comment_lbl, 0, 3, 1, 1)
    comment_entry = Gtk.Entry()
    comment_entry.set_hexpand(True)
    comment_entry.set_activates_default(True)
    grid.attach(comment_entry, 1, 3, 1, 1)

    # Completion using known pool names plus the <offsite> placeholder.
    completion_store = Gtk.ListStore(str)
    for name in get_pool_names(app.config):
        completion_store.append([name])
    completion_store.append(["<offsite>"])

    def _attach_completion(entry):
        comp = Gtk.EntryCompletion()
        comp.set_model(completion_store)
        comp.set_text_column(0)
        comp.set_inline_completion(False)
        comp.set_popup_completion(True)
        comp.set_minimum_key_length(0)
        entry.set_completion(comp)

    _attach_completion(source_entry)
    _attach_completion(dest_entry)

    # Live preview
    preview_lbl = Gtk.Label()
    preview_lbl.set_halign(Gtk.Align.START)
    preview_lbl.set_line_wrap(True)
    preview_lbl.set_selectable(True)
    content.pack_start(preview_lbl, False, False, 0)

    def _update_preview(*_args):
        source = source_entry.get_text().strip()
        dest = dest_entry.get_text().strip()
        label = label_entry.get_text().strip()
        if not source or not dest:
            preview_lbl.set_text("Enter source and destination datasets to see preview.")
            return
        try:
            strip_count, prefix = _compute_strip_segments(source, dest)
        except Exception:
            preview_lbl.set_text("Unable to compute strip segments.")
            return
        forward = f"{source} → strip {strip_count} → prepend {prefix}"
        try:
            reverse = _reverse_checkagainst_row(source, dest, label or "offsite")
            reverse_text = (
                f"{reverse['dataset']} → strip {reverse['quals']} → "
                f"prepend {reverse['counterpart']}"
            )
        except Exception:
            reverse_text = "(unable to compute reverse)"
        preview_lbl.set_markup(
            f"<b>Forward:</b> {forward}\n<b>Reverse:</b> {reverse_text}"
        )

    label_entry.connect("changed", _update_preview)
    source_entry.connect("changed", _update_preview)
    dest_entry.connect("changed", _update_preview)
    _update_preview()

    def _show_validation_error(msg):
        err_dlg = Gtk.MessageDialog(
            transient_for=dlg,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        err_dlg.run()
        err_dlg.destroy()

    dlg.show_all()

    while True:
        response = dlg.run()
        if response != Gtk.ResponseType.OK:
            break

        label = label_entry.get_text().strip()
        source = source_entry.get_text().strip()
        dest = dest_entry.get_text().strip()
        comment = comment_entry.get_text().strip()

        if not label:
            _show_validation_error("Snapshot label is required.")
            continue
        if not source:
            _show_validation_error("Source dataset is required.")
            continue
        if not dest:
            _show_validation_error("Destination dataset is required.")
            continue

        try:
            strip_count, prefix = _compute_strip_segments(source, dest)
            if int(strip_count) < 0:
                raise ValueError
        except Exception:
            _show_validation_error(
                "Could not compute a valid strip count for the given datasets."
            )
            continue

        forward, reverse = _build_pair_rows(source, dest, label, comment)

        app._ca_store.append([
            forward["label"],
            forward["dataset"],
            forward["quals"],
            forward["counterpart"],
            forward["comment"],
        ])
        app._ca_store.append([
            reverse["label"],
            reverse["dataset"],
            reverse["quals"],
            reverse["counterpart"],
            reverse["comment"],
        ])
        _update_ca_status(app)
        log_msg(
            f"INFO: Added checkagainst pair for {source} ↔ {dest} "
            f"(label {label})"
        )
        break

    dlg.destroy()


def on_checkagainst_add_pair(app):
    """Open the Add pair assistant."""
    _show_add_pair_assistant(app)


def is_checkagainst_dirty(app):
    """Return True if there are unsaved changes."""
    return _is_ca_dirty(app)


def check_checkagainst_dirty(app):
    """Compare current UI state to last-saved state; style Save button accordingly."""
    dirty = is_checkagainst_dirty(app)
    btn = getattr(app, '_ca_save_button', None)
    if btn is None:
        return
    if dirty:
        _set_button_markup(btn, '<span foreground="red">Save</span>')
    else:
        _set_button_markup(btn, 'Save')


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
