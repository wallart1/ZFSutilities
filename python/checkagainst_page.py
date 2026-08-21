"""
Checkagainst configuration page — edit the fss table stored in the JSON
config (config["checkagainst"]).

The page shows four sections:

- Backup-derived entries: rows derived from active Backup send/receive steps.
- Offsite-derived entries: rows derived from active Offsite steps.
- User entries: manually maintained rows.
- Merged fss table: read-only preview of the effective runtime table after
  merging the active derived sections and user entries.

The Destination root column accepts a literal pool/path and the special
placeholder "<offsite>", which resolves at run-time to all pools marked as
offsite candidates in the Pools tab. Full documentation and examples are in
the user guide.
"""

import copy

import gi

gi.require_version("Gtk", "3.0")
from feature_config import (
    _compute_destination_root,
    _reverse_checkagainst_row,
    derive_checkagainst_entries,
    get_checkagainst,
    get_pool_names,
    merge_checkagainst_entries,
    save_checkagainst,
)
from gi.repository import Gtk
from gui_helpers import (
    configure_treeview_column,
    handle_editing_key_press,
    set_button_markup,
    show_error,
)
from logging_config import log_msg

# Column indices in the ListStore (display order):
# Snapshot label, Source root, Destination root, Comment.
COL_LABEL = 0
COL_SOURCE_ROOT = 1
COL_DEST_ROOT = 2
COL_COMMENT = 3

# Titles shown on the user-entry column headers.
_COLUMN_TITLES = {
    COL_LABEL: "Snapshot label",
    COL_SOURCE_ROOT: "Source root",
    COL_DEST_ROOT: "Destination root",
    COL_COMMENT: "Comment",
}

# Tooltips for each column header.
_COLUMN_TOOLTIPS = {
    COL_LABEL: "Snapshot label used to build snapshot names (e.g. offsite, dailybackup).",
    COL_SOURCE_ROOT: "Source root dataset tree whose snapshots are checked. <offsite> may appear anywhere.",
    COL_DEST_ROOT: (
        "Destination root dataset tree where the counterpart snapshot is expected. "
        "<offsite> expands to all offsite-candidate pools."
    ),
    COL_COMMENT: "Optional note about this row.",
}


def _entries_from_config(app):
    """Load user checkagainst entries as 4-tuples from the JSON config."""
    data = get_checkagainst(app.config)
    return [
        (e.get("label", ""), e.get("source_root", ""), e.get("dest_root", ""), e.get("comment", ""))
        for e in data.get("user_entries", [])
    ]


def _row_to_dict(row):
    """Convert a 4-tuple store row into the config row dict."""
    return {
        "label": row[COL_LABEL],
        "source_root": row[COL_SOURCE_ROOT],
        "dest_root": row[COL_DEST_ROOT],
        "comment": row[COL_COMMENT],
    }


# Page factory


def create_checkagainst_page(app):
    """Build and return the Checkagainst configuration page widget."""

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    outer.set_margin_start(12)
    outer.set_margin_end(12)
    outer.set_margin_top(10)
    outer.set_margin_bottom(10)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.add(outer)

    # Header
    hdr = Gtk.Label()
    hdr.set_markup("<big><b>Checkagainst Table</b></big>")
    hdr.set_halign(Gtk.Align.START)
    outer.pack_start(hdr, False, False, 0)

    desc = Gtk.Label(
        label="Maps dataset pairs for incremental-backup safety checks. Before deleting a\n"
        "snapshot, the system verifies a counterpart snapshot exists in the paired dataset.\n"
        "Use <offsite> in the Destination root column to check against all "
        "offsite-candidate pools."
    )
    desc.set_halign(Gtk.Align.START)
    desc.set_line_wrap(True)
    outer.pack_start(desc, False, False, 0)

    # Derived sections and merged preview
    app._ca_backup_store = Gtk.ListStore(str, str, str, str)
    app._ca_offsite_store = Gtk.ListStore(str, str, str, str)
    app._ca_store = Gtk.ListStore(str, str, str, str)
    app._ca_merged_store = Gtk.ListStore(str, str, str, str)

    app._ca_backup_active_chk = Gtk.CheckButton(label="Active")
    app._ca_backup_active_chk.set_tooltip_text(
        "Include backup-derived rows when the checkagainst table is evaluated."
    )
    app._ca_backup_active_chk.connect("toggled", _on_active_toggled, app)
    backup_section, backup_tv = _build_section_box(
        "Backup-derived entries",
        app._ca_backup_store,
        app._ca_backup_active_chk,
        "checkagainst_backup_derived_view",
    )
    outer.pack_start(backup_section, True, True, 0)
    app._ui_state.bind_treeview(backup_tv, "checkagainst_backup_derived_view")

    app._ca_offsite_active_chk = Gtk.CheckButton(label="Active")
    app._ca_offsite_active_chk.set_tooltip_text(
        "Include offsite-derived rows when the checkagainst table is evaluated."
    )
    app._ca_offsite_active_chk.connect("toggled", _on_active_toggled, app)
    offsite_section, offsite_tv = _build_section_box(
        "Offsite-derived entries",
        app._ca_offsite_store,
        app._ca_offsite_active_chk,
        "checkagainst_offsite_derived_view",
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

    for col_idx in (COL_LABEL, COL_SOURCE_ROOT, COL_DEST_ROOT, COL_COMMENT):
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

    # Merged fss table preview (read-only)
    merged_section, merged_tv = _build_section_box(
        "Merged fss table",
        app._ca_merged_store,
        None,
        "checkagainst_merged_view",
    )
    outer.pack_start(merged_section, True, True, 0)
    app._ui_state.bind_treeview(merged_tv, "checkagainst_merged_view")

    merged_hint = Gtk.Label()
    merged_hint.set_markup(
        "<small>Effective runtime table after merging the active derived "
        "sections and user entries. See the user guide for details on how "
        "counterpart datasets are constructed and how the &lt;offsite&gt; "
        "placeholder is expanded.</small>"
    )
    merged_hint.set_halign(Gtk.Align.START)
    merged_hint.set_line_wrap(True)
    outer.pack_start(merged_hint, False, False, 0)

    # Load initial data
    _load_fss_into_store(app)

    return scrolled


def _column_width(col_idx):
    """Return a reasonable default width for a checkagainst column."""
    widths = {
        COL_LABEL: 100,
        COL_SOURCE_ROOT: 190,
        COL_DEST_ROOT: 190,
        COL_COMMENT: 140,
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

    for col_idx in (COL_LABEL, COL_SOURCE_ROOT, COL_DEST_ROOT, COL_COMMENT):
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
    """Assemble a labeled section with an optional Active checkbox and a TreeView."""
    frame = Gtk.Frame(label=title)
    frame.set_label_align(0.0, 0.5)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_margin_start(6)
    box.set_margin_end(6)
    box.set_margin_top(6)
    box.set_margin_bottom(6)

    if checkbox is not None:
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.pack_start(checkbox, False, False, 0)
        box.pack_start(header, False, False, 0)

    tv, sw = _build_readonly_treeview(store, state_key)
    box.pack_start(sw, True, True, 0)

    frame.add(box)
    return frame, tv


# Internal helpers


def _load_store(store, entries):
    """Populate a ListStore with a list of 4-tuples."""
    store.clear()
    for entry in entries:
        store.append(list(entry))


def _refresh_merged_table(app):
    """Update the read-only merged fss table preview from the current UI."""
    data = _full_dict_from_ui(app)
    merged = merge_checkagainst_entries({"checkagainst": data})
    rows = [
        (
            e.get("label", ""),
            e.get("source_root", ""),
            e.get("dest_root", ""),
            e.get("comment", ""),
        )
        for e in merged
        if e.get("source_root") and e.get("dest_root") and e.get("label")
    ]
    _load_store(app._ca_merged_store, rows)


def _load_fss_into_store(app):
    """Load all sections from config and snapshot the saved state."""
    data = get_checkagainst(app.config)
    app._ca_backup_active_chk.set_active(data.get("backup_derived_active", True))
    app._ca_offsite_active_chk.set_active(data.get("offsite_derived_active", True))

    # Derived sections always reflect the current Backup/Offsite configs,
    # not whatever happened to be saved in the checkagainst dict.
    refresh_checkagainst_derived(app)

    entries = _entries_from_config(app)
    _load_store(app._ca_store, entries)

    # Snapshot the loaded UI state, not the raw config, so that default
    # values applied by the UI do not create a false dirty state.
    app._ca_original_full = _full_dict_from_ui(app)
    _update_ca_status(app)


def _store_to_entries(store):
    return [(row[0], row[1], row[2], row[3]) for row in store]


def _full_dict_from_ui(app):
    """Collect the entire checkagainst dict from the current UI state."""
    return {
        "backup_derived_active": app._ca_backup_active_chk.get_active(),
        "offsite_derived_active": app._ca_offsite_active_chk.get_active(),
        "backup_derived": [_row_to_dict(row) for row in app._ca_backup_store],
        "offsite_derived": [_row_to_dict(row) for row in app._ca_offsite_store],
        "user_entries": [_row_to_dict(row) for row in app._ca_store],
    }


def _is_ca_dirty(app):
    if not hasattr(app, "_ca_original_full"):
        return False
    return _full_dict_from_ui(app) != app._ca_original_full


def refresh_checkagainst_derived(app):
    """Recompute derived rows from current Backup/Offsite configs and update stores."""
    backup_derived, offsite_derived = derive_checkagainst_entries(app.config)
    _load_store(
        app._ca_backup_store,
        [
            (
                e.get("label", ""),
                e.get("source_root", ""),
                e.get("dest_root", ""),
                e.get("comment", ""),
            )
            for e in backup_derived
        ],
    )
    _load_store(
        app._ca_offsite_store,
        [
            (
                e.get("label", ""),
                e.get("source_root", ""),
                e.get("dest_root", ""),
                e.get("comment", ""),
            )
            for e in offsite_derived
        ],
    )
    _update_ca_status(app)


def _is_derived_stale(app):
    """Return True if displayed derived rows differ from current Backup/Offsite configs."""
    backup_derived, offsite_derived = derive_checkagainst_entries(app.config)

    def _rows_match(store, entries):
        if len(store) != len(entries):
            return False
        for store_row, entry in zip(store, entries):
            if (
                store_row[COL_LABEL] != entry.get("label", "")
                or store_row[COL_SOURCE_ROOT] != entry.get("source_root", "")
                or store_row[COL_DEST_ROOT] != entry.get("dest_root", "")
                or store_row[COL_COMMENT] != entry.get("comment", "")
            ):
                return False
        return True

    return not (
        _rows_match(app._ca_backup_store, backup_derived)
        and _rows_match(app._ca_offsite_store, offsite_derived)
    )


def _style_get_entries_button(app):
    """Set the Get Entries action button red when derived rows are stale."""
    btn = getattr(app, "_ca_get_entries_button", None)
    if btn is None:
        return
    if _is_derived_stale(app):
        set_button_markup(btn, '<span foreground="red">Get Entries</span>')
    else:
        set_button_markup(btn, "Get Entries")


def check_checkagainst_stale(app):
    """Update the Get Entries button to reflect whether derived rows are stale."""
    _style_get_entries_button(app)


def _validate_rows(rows, source):
    """Validate rows and return a list of human-readable errors."""
    errors = []
    for row in rows:
        label, source_root, dest_root, _comment = row
        if not source_root or not dest_root or not label:
            errors.append(f"One or more {source} rows have empty required fields.")
            break
    return errors


def _update_ca_status(app):
    errors = []
    errors.extend(_validate_rows(_store_to_entries(app._ca_backup_store), "Backup-derived"))
    errors.extend(_validate_rows(_store_to_entries(app._ca_offsite_store), "Offsite-derived"))
    errors.extend(_validate_rows(_store_to_entries(app._ca_store), "User"))

    if errors:
        app._ca_status_label.set_markup("<span foreground='red'>" + "\n".join(errors) + "</span>")
    elif _is_ca_dirty(app):
        app._ca_status_label.set_markup("<span foreground='orange'>Unsaved changes.</span>")
    else:
        app._ca_status_label.set_text("")

    # Refresh the merged preview after every change.
    _refresh_merged_table(app)

    # Also update Save button styling
    check_checkagainst_dirty(app)

    # Update Get Entries button styling when derived rows drift from
    # the current Backup/Offsite configurations.
    _style_get_entries_button(app)


def _on_active_toggled(checkbox, app):
    _update_ca_status(app)


def _on_cell_edited(renderer, path, new_text, app, col_idx):
    app._ca_store[path][col_idx] = new_text.strip()
    _update_ca_status(app)


def _on_editing_started(renderer, editable, path, treeview, col_idx):
    """Connect key-press on the editable to handle Tab/Shift+Tab."""
    editable.connect(
        "key-press-event",
        handle_editing_key_press,
        treeview,
        path,
        col_idx,
        [COL_LABEL, COL_SOURCE_ROOT, COL_DEST_ROOT, COL_COMMENT],
    )


def _on_ca_add(btn, app):
    app._ca_store.append(["offsite", "", "", ""])
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
        show_error(app, "Cannot save:\n" + "\n".join(errors))
        return
    try:
        data = _full_dict_from_ui(app)
        save_checkagainst(app.config, data)
    except OSError as e:
        show_error(app, f"Failed to save checkagainst table:\n{e}")
        return
    app._ca_original_full = copy.deepcopy(data)
    log_msg("INFO: Checkagainst table saved to JSON config")
    _update_ca_status(app)


def _on_ca_revert(btn, app):
    if hasattr(app, "_ca_original_full"):
        app.config["checkagainst"] = copy.deepcopy(app._ca_original_full)
    _load_fss_into_store(app)


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

    refresh_checkagainst_derived(app)

    log_msg(
        f"INFO: Derived {len(backup_derived)} backup and {len(offsite_derived)} "
        "offsite checkagainst entries"
    )


def _build_pair_rows(source, dest, label, comment=""):
    """Build the forward and reverse checkagainst rows for a source/dest pair."""
    dest_root = _compute_destination_root(source, dest)
    forward = {
        "label": label,
        "source_root": source,
        "dest_root": dest_root,
        "comment": comment,
    }
    reverse = _reverse_checkagainst_row(source, dest_root, label)
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
            dest_root = _compute_destination_root(source, dest)
        except (ValueError, KeyError, TypeError):
            preview_lbl.set_text("Unable to compute destination root.")
            return
        forward = f"{source} → {dest_root}"
        try:
            reverse = _reverse_checkagainst_row(source, dest_root, label or "offsite")
            reverse_text = f"{reverse['source_root']} → {reverse['dest_root']}"
        except (ValueError, KeyError, TypeError):
            reverse_text = "(unable to compute reverse)"
        preview_lbl.set_markup(f"<b>Forward:</b> {forward}\n<b>Reverse:</b> {reverse_text}")

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
            _compute_destination_root(source, dest)
        except (ValueError, KeyError, TypeError):
            _show_validation_error(
                "Could not compute a valid destination root for the given datasets."
            )
            continue

        forward, reverse = _build_pair_rows(source, dest, label, comment)

        app._ca_store.append(
            [
                forward["label"],
                forward["source_root"],
                forward["dest_root"],
                forward["comment"],
            ]
        )
        app._ca_store.append(
            [
                reverse["label"],
                reverse["source_root"],
                reverse["dest_root"],
                reverse["comment"],
            ]
        )
        _update_ca_status(app)
        log_msg(f"INFO: Added checkagainst pair for {source} ↔ {dest} (label {label})")
        break

    dlg.destroy()


def on_checkagainst_add_pair(app):
    """Open the Add pair assistant."""
    _show_add_pair_assistant(app)


def check_checkagainst_dirty(app):
    """Compare current UI state to last-saved state; style Save button accordingly."""
    dirty = _is_ca_dirty(app)
    btn = getattr(app, "_ca_save_button", None)
    if btn is None:
        return
    if dirty:
        set_button_markup(btn, '<span foreground="red">Save</span>')
    else:
        set_button_markup(btn, "Save")
