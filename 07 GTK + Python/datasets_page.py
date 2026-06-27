"""
Datasets tab UI — collapsible tree of all pool datasets, snapshots, and holds.

Snapshot management (delete, hold, rollback) is handled inline rather than
in a separate window, so holds are always visible in the tree.
"""

import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from logging_config import log_msg
from gui_helpers import (
    setup_row_scroll,
    dataset_name_cell_func,
    build_full_dataset_name,
    get_expanded_rows,
    restore_expanded_rows,
    expand_tree_recursively,
    on_row_expanded,
    load_pool_children,
    load_dataset_children,
    load_snapshot_children,
    TreeSearch,
    get_tree_selection_items,
    set_monospace_font,
    configure_treeview_column,
)


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def create_datasets_page(app):
    """Build and return the full Datasets tab widget."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(10)
    box.set_margin_end(10)
    box.set_margin_top(10)
    box.set_margin_bottom(10)

    title_label = Gtk.Label()
    title_label.set_markup("<big><b>Datasets</b></big>")
    title_label.set_halign(Gtk.Align.START)
    box.pack_start(title_label, False, False, 0)

    box.pack_start(Gtk.Separator(), False, False, 0)

    # Search bar
    search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    search_icon = Gtk.Image.new_from_icon_name(
        "system-search", Gtk.IconSize.BUTTON
    )
    search_box.pack_start(search_icon, False, False, 0)

    app.datasets_search_entry = Gtk.Entry()
    app.datasets_search_entry.set_placeholder_text("Search datasets...")
    app.datasets_search_entry.set_width_chars(1)
    search_box.pack_start(app.datasets_search_entry, True, True, 0)

    app.datasets_search_clear_btn = Gtk.Button()
    app.datasets_search_clear_btn.set_image(
        Gtk.Image.new_from_icon_name("edit-clear", Gtk.IconSize.BUTTON)
    )
    app.datasets_search_clear_btn.set_tooltip_text("Clear search")
    search_box.pack_start(app.datasets_search_clear_btn, False, False, 0)

    app.datasets_search_prev_btn = Gtk.Button()
    app.datasets_search_prev_btn.set_image(
        Gtk.Image.new_from_icon_name("go-up", Gtk.IconSize.BUTTON)
    )
    app.datasets_search_prev_btn.set_tooltip_text("Previous match")
    search_box.pack_start(app.datasets_search_prev_btn, False, False, 0)

    app.datasets_search_next_btn = Gtk.Button()
    app.datasets_search_next_btn.set_image(
        Gtk.Image.new_from_icon_name("go-down", Gtk.IconSize.BUTTON)
    )
    app.datasets_search_next_btn.set_tooltip_text("Next match")
    search_box.pack_start(app.datasets_search_next_btn, False, False, 0)

    app.datasets_search_results_label = Gtk.Label()
    app.datasets_search_results_label.set_halign(Gtk.Align.START)
    app.datasets_search_results_label.set_margin_end(10)
    search_box.pack_start(app.datasets_search_results_label, False, False, 5)


    box.pack_start(search_box, False, False, 0)

    # TreeStore: pools -> datasets -> snapshots -> holds
    # Columns: name, creation, type, used, avail, refer, origin/clones, loaded
    app.datasets_store = Gtk.TreeStore(str, str, str, str, str, str, str, bool)
    app.datasets_view = Gtk.TreeView(model=app.datasets_store)
    app.datasets_view._zfs_repo = app.ctx.zfs_repository
    app.datasets_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.datasets_view.set_enable_tree_lines(True)
    app.datasets_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    app.datasets_search = TreeSearch(
        app.datasets_view,
        app.datasets_search_entry,
        app.datasets_search_results_label,
        app.datasets_search_prev_btn,
        app.datasets_search_next_btn,
        full_name_func=build_full_dataset_name,
    )
    app.datasets_search_clear_btn.connect(
        "clicked", lambda _b: app.datasets_search.clear()
    )

    ds_columns = [
        ("Name", 0, 150),
        ("Created", 1, 110),
        ("Type", 2, 70),
        ("Used", 3, 65),
        ("Avail", 4, 65),
        ("Refer", 5, 65),
        ("Origin / Clones", 6, 130),
    ]
    for title, col_idx, width in ds_columns:
        renderer = Gtk.CellRendererText()
        if title == "Created":
            set_monospace_font(renderer)
        col = Gtk.TreeViewColumn(title, renderer, text=col_idx)
        if col_idx in (3, 4, 5):
            renderer.set_property("xalign", 1.0)
            col.set_alignment(1.0)
        configure_treeview_column(col, width=width)
        if col_idx == 0:
            col.set_cell_data_func(renderer, dataset_name_cell_func)
        elif col_idx == 6:
            pass  # No special rendering needed for origin/clones column
        app.datasets_view.append_column(col)

    app.enable_treeview_copy(app.datasets_view)
    app._ui_state.bind_treeview(app.datasets_view, "datasets_view")

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.add(app.datasets_view)
    setup_row_scroll(scrolled, app.datasets_view)
    app.datasets_scrolled = scrolled
    box.pack_start(scrolled, True, True, 0)

    # Summary
    app.datasets_summary_label = Gtk.Label()
    app.datasets_summary_label.set_halign(Gtk.Align.START)
    box.pack_start(app.datasets_summary_label, False, False, 0)

    # Connect selection changed for button sensitivity
    app.datasets_view.get_selection().connect("changed", _on_ds_selection_changed, app)

    # Lazy-load children when rows are expanded
    app.datasets_view.connect("row-expanded", on_row_expanded, None)
    app.datasets_view.connect(
        "row-expanded", _on_ds_row_expanded_collapsed, app
    )
    app.datasets_view.connect(
        "row-collapsed", _on_ds_row_expanded_collapsed, app
    )

    # Initial load
    refresh_datasets_page(app)

    return box


# ---------------------------------------------------------------------------
# Data refresh
# ---------------------------------------------------------------------------

def refresh_datasets_page(app, pool_filter=None):
    """Refresh dataset tree: load only pools initially; children load on demand."""
    expanded = get_expanded_rows(app.datasets_store, app.datasets_view)

    # Remember vertical scroll offset so the view does not jump to top.
    saved_scroll = None
    scrolled = getattr(app, "datasets_scrolled", None)
    if scrolled is not None:
        vadj = scrolled.get_vadjustment()
        if vadj is not None:
            saved_scroll = vadj.get_value()

    # Remember selection so we can re-select after repopulating
    selection = app.datasets_view.get_selection()
    model, paths = selection.get_selected_rows()
    selected_names = []
    for path in paths:
        try:
            tree_iter = model.get_iter(path)
            selected_names.append(build_full_dataset_name(model, tree_iter))
        except ValueError:
            pass

    app.datasets_store.clear()

    try:
        online_pools = [row.name for row in app.ctx.zfs_repository.list_pools()]
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error listing pools: {e}")
        return

    if pool_filter:
        pools_to_show = [pool_filter] if pool_filter in online_pools else []
    else:
        pools_to_show = online_pools

    for pool in pools_to_show:
        pool_iter = app.datasets_store.append(None, [pool, "", "", "", "", "", "", False])
        # Dummy child so the expand arrow appears
        app.datasets_store.append(pool_iter, ["(loading...)", "", "", "", "", "", "", True])

    app.datasets_summary_label.set_text(f"{len(pools_to_show)} pools")

    # Restore expanded rows, loading children as we go
    restore_expanded_rows(app.datasets_store, app.datasets_view, expanded)

    # Restore vertical scroll position once GTK has allocated the new rows
    if saved_scroll is not None:
        GLib.idle_add(_restore_scroll, app.datasets_scrolled, saved_scroll)

    # Re-select previously selected items if they still exist
    if selected_names:
        _select_by_name(app.datasets_store, app.datasets_view, selected_names)
        update_ds_button_sensitivity(app)

    # Re-run active search after refresh
    if app.datasets_search._text:
        app.datasets_search._run_search()


def _restore_scroll(scrolled, saved_value):
    """Clamp and restore a saved vertical scroll offset."""
    vadj = scrolled.get_vadjustment()
    if vadj is None:
        return False
    upper = vadj.get_upper()
    page = vadj.get_page_size()
    max_value = max(0.0, upper - page)
    vadj.set_value(max(0.0, min(saved_value, max_value)))
    return False


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------

# build_full_dataset_name is imported from gui_helpers.py

def _select_by_name(store, view, names):
    """Walk the tree and select rows whose full ZFS name is in *names*."""
    selection = view.get_selection()
    selection.unselect_all()

    def _walk(tree_iter, prefix):
        while tree_iter:
            name = store.get_value(tree_iter, 0)
            full = f"{prefix}/{name}" if prefix else name
            if full in names:
                path = store.get_path(tree_iter)
                selection.select_path(path)
            child = store.iter_children(tree_iter)
            if child:
                _walk(child, full)
            tree_iter = store.iter_next(tree_iter)

    _walk(store.get_iter_first(), "")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _on_ds_row_expanded_collapsed(_view, _iter, _path, app):
    """Re-run the active search when the tree structure changes."""
    app.datasets_search.handle_expand_collapse()


# ---------------------------------------------------------------------------
# Expand selected rows
# ---------------------------------------------------------------------------

def expand_selected_datasets(app):
    """Recursively expand all rows currently selected in the Datasets tree."""
    selection = app.datasets_view.get_selection()
    model, paths = selection.get_selected_rows()
    if not paths:
        return

    placeholders = {"(loading...)", "(no datasets)", "(empty)", "(no holds)"}
    iters_to_expand = []
    for path in paths:
        try:
            tree_iter = model.get_iter(path)
        except ValueError:
            continue
        name = model.get_value(tree_iter, 0)
        ds_type = model.get_value(tree_iter, 2)
        if name in placeholders or ds_type == "hold":
            continue
        iters_to_expand.append(tree_iter)

    if not iters_to_expand:
        return

    dialog = Gtk.MessageDialog(
        transient_for=app,
        flags=Gtk.DialogFlags.MODAL,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.NONE,
        text="Expanding selected rows…",
    )
    dialog.set_deletable(False)
    dialog.show()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)

    app.datasets_search.freeze()
    try:
        for tree_iter in iters_to_expand:
            expand_tree_recursively(app.datasets_view, model, tree_iter)
    finally:
        app.datasets_search.thaw()
        dialog.destroy()
        app.datasets_search.handle_expand_collapse()


# ---------------------------------------------------------------------------
# Button sensitivity
# ---------------------------------------------------------------------------

def _on_ds_selection_changed(selection, app):
    """Update action button sensitivity when the tree selection changes."""
    update_ds_button_sensitivity(app)


def update_ds_button_sensitivity(app):
    """Enable/disable action buttons based on the current selection."""
    items = get_tree_selection_items(app.datasets_view)
    types = {i["type"] for i in items} if items else set()

    can_snapshot = len(items) == 1 and types <= {"pool", "dataset"}
    can_delete = bool(items) and "pool" not in types
    can_hold = "snapshot" in types and types <= {"snapshot", "hold"}
    can_rollback = len(items) == 1 and types == {"snapshot"}

    can_show_files = False
    if len(items) == 1 and items[0].get("zfs_type") == "filesystem":
        try:
            result = subprocess.run(
                ["zfs", "get", "-H", "-o", "value", "mounted",
                 items[0]["name"]],
                capture_output=True, text=True, check=True,
            )
            can_show_files = result.stdout.strip() == "yes"
        except subprocess.CalledProcessError:
            pass

    can_browse_snapshot = False
    can_unmount_snapshot = False
    if len(items) == 1 and items[0]["type"] == "snapshot":
        dataset = items[0]["dataset"]
        snap = items[0]["name"]
        full_snap = f"{dataset}@{snap}"
        try:
            parent_mounted = subprocess.run(
                ["zfs", "get", "-H", "-o", "value", "mounted", dataset],
                capture_output=True, text=True, check=True,
            )
            if parent_mounted.stdout.strip() == "yes":
                can_browse_snapshot = True
        except subprocess.CalledProcessError:
            pass
        try:
            mount_result = subprocess.run(
                ["mount", "-t", "zfs"],
                capture_output=True, text=True, check=True,
            )
            can_unmount_snapshot = full_snap in mount_result.stdout
        except subprocess.CalledProcessError:
            pass

    can_expand_selected = bool(items) and any(
        i["type"] in ("pool", "dataset", "snapshot") for i in items
    )

    for attr, sensitive in [
        ('_ds_snapshot_btn', can_snapshot),
        ('_ds_delete_btn', can_delete),
        ('_ds_hold_btn', can_hold),
        ('_ds_rollback_btn', can_rollback),
        ('_ds_showfiles_btn', can_show_files),
        ('_ds_browsesnap_btn', can_browse_snapshot),
        ('_ds_unmountsnap_btn', can_unmount_snapshot),
        ('_ds_expand_selected_btn', can_expand_selected),
    ]:
        btn = getattr(app, attr, None)
        if btn:
            btn.set_sensitive(sensitive)

