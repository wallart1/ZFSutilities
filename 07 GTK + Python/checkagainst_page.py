"""
Checkagainst configuration page — edit the fss table stored in the JSON
config (config["checkagainst"]).

The Counterpart column accepts a literal pool/path (or "-" for no prefix)
and the special placeholder "<offsite>", which resolves at run-time to all
pools marked as offsite candidates in the Pools tab.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from logging_config import log_msg
from feature_config import get_checkagainst, save_checkagainst
from gui_helpers import configure_treeview_column

# Column indices in the ListStore
COL_DATASET     = 0
COL_QUALS       = 1
COL_COUNTERPART = 2
COL_LABEL       = 3
COL_COMMENT     = 4


def _entries_from_config(app):
    """Load fss entries as 5-tuples from the JSON config."""
    data = get_checkagainst(app.config)
    return [
        (e.get("dataset", ""), e.get("quals", "0"),
         e.get("counterpart", "-"), e.get("label", ""),
         e.get("comment", ""))
        for e in data
    ]


def _entries_to_config(app, entries):
    """Persist a list of 5-tuples back to the JSON config."""
    save_checkagainst(app.config, [
        {"dataset": d, "quals": q, "counterpart": c, "label": l, "comment": cmt}
        for d, q, c, l, cmt in entries
    ])


# ── Page factory ───────────────────────────────────────────────────────────────

def create_checkagainst_page(app):
    """Build and return the Checkagainst configuration page widget.

    The Dataset and Counterpart columns accept literal pool/path values,
    "-" for no prefix, or "<offsite>" to resolve to all offsite-candidate
    pools at run-time.
    """

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    outer.set_margin_start(12)
    outer.set_margin_end(12)
    outer.set_margin_top(10)
    outer.set_margin_bottom(10)

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = Gtk.Label()
    hdr.set_markup("<big><b>Checkagainst Table</b></big>")
    hdr.set_halign(Gtk.Align.START)
    outer.pack_start(hdr, False, False, 0)

    desc = Gtk.Label(
        label="Maps dataset pairs for incremental-backup safety checks. Before deleting a\n"
              "snapshot, the system verifies a counterpart snapshot exists in the paired dataset.\n"
              "Use <offsite> in the Counterpart column to check against all offsite-candidate pools."
    )
    desc.set_halign(Gtk.Align.START)
    desc.set_line_wrap(True)
    outer.pack_start(desc, False, False, 0)

    def _build_header(title_text):
        """Build a TreeViewColumn header widget with title."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        lbl = Gtk.Label(label=title_text)
        box.pack_start(lbl, False, False, 0)
        box.show_all()
        return box

    # ── TreeView ──────────────────────────────────────────────────────────────
    app._ca_store = Gtk.ListStore(str, str, str, str, str)

    tv = Gtk.TreeView(model=app._ca_store)
    tv.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    tv.set_reorderable(True)
    app._ca_view = tv

    col_specs = [
        ("Dataset",     COL_DATASET,     160),
        ("Quals",       COL_QUALS,       50),
        ("Counterpart", COL_COUNTERPART, 130),
        ("Label",       COL_LABEL,       90),
        ("Comment",     COL_COMMENT,     140),
    ]
    for title, col_idx, width in col_specs:
        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", True)
        renderer.connect("edited", _on_cell_edited, app, col_idx)
        col = Gtk.TreeViewColumn(title, renderer, text=col_idx)
        configure_treeview_column(col, width=width)
        col.set_widget(_build_header(title))
        tv.append_column(col)
    app._ui_state.bind_treeview(app._ca_view, "checkagainst_view")

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.set_size_request(-1, 150)
    sw.add(tv)
    outer.pack_start(sw, True, True, 0)

    # ── Status label ──────────────────────────────────────────────────────────
    app._ca_status_label = Gtk.Label()
    app._ca_status_label.set_halign(Gtk.Align.START)
    outer.pack_start(app._ca_status_label, False, False, 0)

    # ── Notes ─────────────────────────────────────────────────────────────────
    # Buttons are in the Actions pane (right side); see on_checkagainst_* handlers
    notes = Gtk.Label()
    notes.set_markup(
        "<small><b>How the counterpart dataset is constructed:</b>\n"
        "  1. <b>Remove</b> the first N path segments from the snapshot's dataset "
        "(N = Quals column)\n"
        "  2. <b>Prepend</b> the Counterpart prefix to the result\n\n"
        "<b>Special value:</b>\n"
        "  <b>&lt;offsite&gt;</b> may be used anywhere in the Dataset or Counterpart "
        "column. Every occurrence is replaced with every pool marked as an offsite "
        "candidate in the Pools tab.\n\n"
        "<b>Examples:</b>\n"
        "  Quals=0: poolA/data → remove nothing → prepend poolB → "
        "<b>poolB/poolA/data</b>\n"
        "  Quals=2: poolB/poolA/data → remove 'poolB/poolA' → "
        "prepend poolA → <b>poolA/data</b>\n"
        "  Quals=0, Counterpart=&lt;offsite&gt;: poolA/data → "
        "<b>z22tb/poolA/data</b>, <b>z40tb/poolA/data</b>, …\n"
        "  Dataset=&lt;offsite&gt;/temp, Quals=1, Counterpart=-: "
        "z22tb/temp → remove 'z22tb' → <b>temp</b>\n"
        "  Counterpart=poolA/&lt;offsite&gt;/backup: poolA/data → "
        "<b>poolA/z22tb/backup/poolA/data</b>, …</small>"
    )
    notes.set_halign(Gtk.Align.START)
    notes.set_line_wrap(True)
    outer.pack_start(notes, False, False, 6)

    # Load initial data
    _load_fss_into_store(app)

    return outer


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_fss_into_store(app):
    entries = _entries_from_config(app)
    app._ca_store.clear()
    for entry in entries:
        app._ca_store.append(list(entry))
    app._ca_original = list(entries)
    _update_ca_status(app)


def _store_to_entries(app):
    return [(row[0], row[1], row[2], row[3], row[4]) for row in app._ca_store]


def _is_ca_dirty(app):
    return _store_to_entries(app) != app._ca_original


def _update_ca_status(app):
    errors = []
    for row in app._ca_store:
        dataset, quals, counterpart, label, comment = \
            row[0], row[1], row[2], row[3], row[4]
        # Dataset and label must be present; counterpart may be "-" (null prepend).
        if not dataset or not counterpart or not label:
            errors.append("One or more rows have empty required fields.")
            break
        try:
            q = int(quals)
            if q < 0:
                raise ValueError
        except ValueError:
            errors.append(f"Row '{dataset}': Quals must be a non-negative integer.")

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


def _on_cell_edited(renderer, path, new_text, app, col_idx):
    app._ca_store[path][col_idx] = new_text.strip()
    _update_ca_status(app)


def _on_ca_add(btn, app):
    app._ca_store.append(["", "0", "-", "offsite", ""])
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
    entries = _store_to_entries(app)
    # Validate before saving
    for dataset, quals, counterpart, label, comment in entries:
        if not dataset or not counterpart or not label:
            _show_error(app, "Cannot save: one or more rows have empty required fields.")
            return
        try:
            if int(quals) < 0:
                raise ValueError
        except ValueError:
            _show_error(app, f"Cannot save: Quals for '{dataset}' must be a non-negative integer.")
            return
    try:
        _entries_to_config(app, entries)
    except OSError as e:
        _show_error(app, f"Failed to save checkagainst table:\n{e}")
        return
    app._ca_original = list(entries)
    log_msg("INFO: Checkagainst table saved to JSON config")
    _update_ca_status(app)


def _on_ca_revert(btn, app):
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


# ── Action handlers (called from Actions pane) ─────────────────────────────────

def on_checkagainst_add(app):
    """Add a new row to the fss table.

    The default row uses "offsite" for the label and "-" for the
    counterpart; users may enter "<offsite>" to check all offsite
    candidate pools.
    """
    _on_ca_add(None, app)


def on_checkagainst_remove(app):
    """Remove the selected row from the fss table."""
    _on_ca_remove(None, app)


def on_checkagainst_save(app):
    """Save the fss table to the JSON config.

    Counterpart values may be literal pool/paths, "-", or "<offsite>"
    (with an optional suffix).
    """
    _on_ca_save(None, app)


def on_checkagainst_revert(app):
    """Revert to the last saved state."""
    _on_ca_revert(None, app)


def is_checkagainst_dirty(app):
    """Return True if there are unsaved changes."""
    if not hasattr(app, '_ca_original'):
        return False
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
