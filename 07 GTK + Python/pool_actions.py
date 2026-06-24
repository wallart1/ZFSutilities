"""
Pool tab action handlers — extracted from pools_page.py.
"""

import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from backup_config import save_pools, log_msg
from gui_helpers import (
    create_dialog,
    configure_treeview_column, _ensure_treeview_scrolling,
    add_scrolled_text_view, set_button_markup_red,
)
from pools_page import (
    refresh_pools_page, _update_pools_dirty_indicator, get_selected_pool_names,
    COL_NAME, COL_HEALTH, COL_FLAG,
    FLAG_REGISTERED, FLAG_UNREGISTERED,
)
from scrub_manager import (
    start_scrub, pause_scrub, resume_scrub, stop_scrub,
)
from pool_watch import PoolWatchWindow


def on_pools_watch(app):
    """Open independent watch windows for all selected online pools."""
    selected = _get_selected_registered_rows(app)
    if not selected:
        log_msg("WARN: Select at least one pool to watch")
        return

    opened = 0
    for pool_name, health in selected:
        if health == "OFFLINE":
            log_msg(f"WARN: Pool '{pool_name}' is offline — cannot watch")
            continue
        if pool_name in app._watch_windows:
            app._watch_windows[pool_name].present()
        else:
            win = PoolWatchWindow(pool_name, app)
            app._watch_windows[pool_name] = win
            win.show_all()
        opened += 1
    if opened:
        log_msg(f"INFO: Opened watch window(s) for {opened} pool(s)")


def on_pools_details(app):
    """Show zpool status output for the selected pool."""
    selection = app.pool_view.get_selection()
    model, tree_iter = selection.get_selected()
    if tree_iter is None:
        log_msg("WARN: Select a pool to view details")
        return

    pool_name = model.get_value(tree_iter, COL_NAME)
    status_text = app.ctx.zfs_repository.pool_status(pool_name)
    if not status_text:
        log_msg(f"WARN: Error getting status for '{pool_name}'")
        return

    dialog = create_dialog(
        f"Pool Details: {pool_name}", app,
        [(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)],
        size=(650, 450),
    )
    add_scrolled_text_view(dialog.get_content_area(), status_text)
    dialog.show_all()
    dialog.run()
    dialog.destroy()


def on_pools_add(app):
    """Add a pool to the registry."""
    prefill = ""
    selection = app.pool_view.get_selection()
    model, tree_iter = selection.get_selected()
    if tree_iter is not None:
        flag = model.get_value(tree_iter, COL_FLAG)
        if flag == FLAG_UNREGISTERED:
            prefill = model.get_value(tree_iter, COL_NAME)

    dialog = create_dialog(
        "Add Pool", app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
         (Gtk.STOCK_OK, Gtk.ResponseType.OK)],
        default_response=Gtk.ResponseType.OK,
    )
    content = dialog.get_content_area()
    label = Gtk.Label(label="Pool name:")
    label.set_halign(Gtk.Align.START)
    content.add(label)

    entry = Gtk.Entry()
    entry.set_width_chars(1)
    entry.set_text(prefill)
    entry.set_activates_default(True)
    content.add(entry)

    dialog.show_all()
    response = dialog.run()
    pool_name = entry.get_text().strip()
    dialog.destroy()

    if response != Gtk.ResponseType.OK or not pool_name:
        return
    known_names = {p["name"] for p in app.known_pools}
    if pool_name in known_names:
        log_msg(f"WARN: Pool '{pool_name}' is already in the registry")
        return

    app.known_pools.append(
        {"name": pool_name, "offsite_candidate": False}
    )
    refresh_pools_page(app)
    log_msg(f"INFO: Added '{pool_name}' to pool registry (unsaved)")


def _parse_importable_pools(zpool_output):
    """Parse 'zpool import' output into (name, details) tuples.

    Filters out pools whose config contains zvol-backed devices
    (device names starting with 'zd').
    """
    blocks = []
    current = []
    for line in zpool_output.split('\n'):
        if line.strip().startswith('pool:') and current:
            blocks.append('\n'.join(current))
            current = []
        current.append(line)
    if current:
        blocks.append('\n'.join(current))

    pools = []
    filtered = []
    for block in blocks:
        lines = block.split('\n')
        name = None
        in_config = False
        is_zvol_backed = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('pool:'):
                name = stripped.split(':', 1)[1].strip()
            elif stripped == 'config:':
                in_config = True
            elif in_config and stripped:
                parts = stripped.split()
                if parts and parts[0].startswith('zd'):
                    is_zvol_backed = True
        if name:
            if is_zvol_backed:
                filtered.append(name)
            else:
                pools.append((name, block))
    return pools, filtered


def _show_pool_import_details(app, pool_name, details):
    """Show a dialog with the full zpool import details for a pool."""
    dialog = create_dialog(
        f"Import Details: {pool_name}", app,
        [(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)],
        size=(550, 400),
    )
    add_scrolled_text_view(dialog.get_content_area(), details)
    dialog.show_all()
    dialog.run()
    dialog.destroy()


def _import_single_pool(app, pool_name):
    """Import one pool by name. Returns True on success."""
    if app.ctx.zfs_repository.import_pool(pool_name):
        log_msg(f"INFO: Pool '{pool_name}' imported successfully")
        return True
    log_msg(f"WARN: Error importing pool '{pool_name}'")
    return False


def on_pools_import(app):
    """Import selected offline pools, or show importable pools dialog if none selected."""
    selected = _get_selected_rows(app)
    offline_selected = [n for n, h in selected if h == "OFFLINE"]

    if offline_selected:
        dlg = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Import {len(offline_selected)} selected pool(s)?",
        )
        response = dlg.run()
        dlg.destroy()
        if response == Gtk.ResponseType.YES:
            for pool_name in offline_selected:
                _import_single_pool(app, pool_name)
            refresh_pools_page(app)
        return

    # Fallback: show dialog of importable pools
    raw_output = app.ctx.zfs_repository.importable_pools_raw()

    importable, filtered = _parse_importable_pools(raw_output)

    if not importable:
        msg = "No pools available for import."
        if filtered:
            msg += (
                f"\n\n({len(filtered)} pool(s) hidden because they are "
                f"backed by zvol partitions.)"
            )
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        dialog.run()
        dialog.destroy()
        return

    dialog = create_dialog(
        "Import Pool", app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
         ("Details", Gtk.ResponseType.APPLY),
         ("Import", Gtk.ResponseType.OK)],
        default_response=Gtk.ResponseType.OK,
    )
    content = dialog.get_content_area()
    label = Gtk.Label(label="Select a pool to import:")
    label.set_halign(Gtk.Align.START)
    content.add(label)

    list_store = Gtk.ListStore(str)
    details_map = {}
    for name, details in importable:
        list_store.append([name])
        details_map[name] = details

    tree_view = Gtk.TreeView(model=list_store)
    tree_view.set_headers_visible(False)
    renderer = Gtk.CellRendererText()
    col = Gtk.TreeViewColumn("Pool", renderer, text=0)
    configure_treeview_column(col, width=150)
    tree_view.append_column(col)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_min_content_height(150)
    scrolled.add(tree_view)
    content.add(scrolled)

    if filtered:
        info = Gtk.Label()
        info.set_markup(
            f"<small><i>{len(filtered)} zvol-backed pool(s) hidden</i></small>"
        )
        info.set_halign(Gtk.Align.START)
        content.add(info)

    dialog.show_all()

    selected_pool = None
    while True:
        response = dialog.run()
        selection = tree_view.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            selected_pool = model.get_value(tree_iter, 0)

        if response == Gtk.ResponseType.APPLY:
            if selected_pool:
                _show_pool_import_details(app, selected_pool, details_map[selected_pool])
            continue
        break

    dialog.destroy()

    if response != Gtk.ResponseType.OK or not selected_pool:
        return

    _import_single_pool(app, selected_pool)
    refresh_pools_page(app)


def on_pools_export(app):
    """Export all selected pools."""
    selected = [n for n, h in _get_selected_rows(app)]
    if not selected:
        log_msg("WARN: Select at least one pool to export")
        return

    names_str = ", ".join(selected)
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Export {len(selected)} pool(s): {names_str}?",
    )
    dialog.format_secondary_text(
        "This will unload the pool(s). Any datasets or VMs using them will lose access. "
        "The pool(s) can be re-imported later."
    )
    response = dialog.run()
    dialog.destroy()

    if response != Gtk.ResponseType.YES:
        return

    for pool_name in selected:
        if app.ctx.zfs_repository.export_pool(pool_name):
            log_msg(f"INFO: Pool '{pool_name}' exported successfully")
        else:
            log_msg(f"WARN: Error exporting pool '{pool_name}'")
    refresh_pools_page(app)


def on_pools_remove(app):
    """Remove all selected registered pools from the registry."""
    selected = _get_selected_rows(app)
    known_names = {p["name"] for p in app.known_pools}
    registered = [n for n, h in selected if n in known_names]
    if not registered:
        log_msg("WARN: Select at least one registered pool to remove")
        return

    names_str = ", ".join(registered)
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Remove {len(registered)} pool(s) from the registry?",
    )
    dialog.format_secondary_text(
        f"Pools: {names_str}\n"
        "This only removes them from the known pools list. It does not destroy the pools."
    )
    response = dialog.run()
    dialog.destroy()

    if response != Gtk.ResponseType.YES:
        return

    for pool_name in registered:
        app.known_pools = [
            p for p in app.known_pools if p["name"] != pool_name
        ]
        log_msg(f"INFO: Removed '{pool_name}' from pool registry (unsaved)")
    refresh_pools_page(app)


def on_pools_save(app):
    """Save the pool registry to the JSON config."""
    if not app.pools_dirty:
        log_msg("INFO: No changes to save")
        return
    try:
        save_pools(app.config, app.known_pools)
    except OSError as e:
        log_msg(f"WARN: Error saving pool registry: {e}")
        return
    app._pools_saved_state = list(app.known_pools)
    _update_pools_dirty_indicator(app)
    log_msg("INFO: Pool registry saved to JSON config")


def on_pools_revert(app):
    """Revert to the last-saved registry."""
    app.known_pools = list(app._pools_saved_state)
    refresh_pools_page(app)
    log_msg("INFO: Pool registry reverted")


def check_pools_dirty(app):
    """Style the Save button to match the Backup tab pattern."""
    btn = getattr(app, '_pools_save_button', None)
    if btn:
        set_button_markup_red(btn, app.pools_dirty)


# ---------------------------------------------------------------------------
# Scrub action handlers
# ---------------------------------------------------------------------------

def on_scrub_start(app):
    """Add selected pools to the scrub queue."""
    pools = get_selected_pool_names(app.scrub_view)
    if not pools:
        log_msg("WARN: Select at least one pool to scrub")
        return
    app.scrub_queue.add_pending(pools)
    from pools_page import refresh_scrub_table
    refresh_scrub_table(app)


def on_scrub_pause(app):
    """Pause selected pools in the scrub queue."""
    pools = get_selected_pool_names(app.scrub_view)
    if not pools:
        log_msg("WARN: Select at least one pool to pause")
        return
    app.scrub_queue.pause_pools(pools)
    for name in pools:
        pause_scrub(name)
    from pools_page import refresh_scrub_table
    refresh_scrub_table(app)


def on_scrub_resume(app):
    """Resume selected paused pools."""
    pools = get_selected_pool_names(app.scrub_view)
    if not pools:
        log_msg("WARN: Select at least one pool to resume")
        return
    app.scrub_queue.resume_pools(pools)
    from pools_page import refresh_scrub_table
    refresh_scrub_table(app)


def on_scrub_stop(app):
    """Stop selected scrubs and remove from queue."""
    pools = get_selected_pool_names(app.scrub_view)
    if not pools:
        log_msg("WARN: Select at least one pool to stop")
        return
    for name in pools:
        stop_scrub(name)
    app.scrub_queue.remove_pools(pools)
    from pools_page import refresh_scrub_table
    refresh_scrub_table(app)


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------

def _get_selected_rows(app):
    """Return list of (pool_name, health) for all selected rows in pool_view."""
    selection = app.pool_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    rows = []
    for path in pathlist:
        tree_iter = model.get_iter(path)
        rows.append((model.get_value(tree_iter, COL_NAME),
                     model.get_value(tree_iter, COL_HEALTH)))
    return rows


def _get_selected_registered_rows(app):
    """Return list of (pool_name, health) for selected registered rows."""
    rows = _get_selected_rows(app)
    known_names = {p["name"] for p in app.known_pools}
    return [(n, h) for n, h in rows if n in known_names]


# Legacy: no-op kept for any lingering callers.
def set_pools_dirty(app, dirty):
    _update_pools_dirty_indicator(app)
