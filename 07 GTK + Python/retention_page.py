"""
Retention Policies page — read and write the shared JSON config
(/root/.config/zfsutilities.json, under the `retention` key).
"""

import copy
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from logging_config import log_msg
from config_core import save_config
from feature_config import (
    get_all_retention,
    get_retention,
    save_retention,
    get_prune_label,
    save_prune_label,
    get_prune_pools_order,
    save_prune_pools_order,
    import_legacy_retention,
    DEFAULT_RETENTION,
)
from gui_helpers import (
    set_button_markup_red,
    configure_treeview_column, ACTIVE_COLUMN_WIDTH,
    handle_editing_key_press,
)

# Human-readable bucket labels
BUCKET_LABELS = {
    'd': 'Daily',
    'w': 'Weekly',
    'm': 'Monthly',
    's': 'Offsite',
}


def collect_retention_profile_config(app):
    """Collect prune-relevant settings for a retention profile."""
    label = app._ret_prune_label_entry.get_text().strip() or "dailybackup"
    pools = []
    if hasattr(app, '_ret_prune_view'):
        selection = app._ret_prune_view.get_selection()
        model, paths = selection.get_selected_rows()
        for p in paths:
            pools.append(model[p][0])
    return {"prune_label": label, "prune_pools": pools}


def load_retention_profile_config(app, config):
    """Load a retention profile config into the prune UI."""
    label = config.get("prune_label", "dailybackup")
    app._ret_prune_label_entry.set_text(label)
    app._ret_original_prune_label = label
    if hasattr(app, '_ret_prune_view') and hasattr(app, '_ret_prune_store'):
        selection = app._ret_prune_view.get_selection()
        selection.unselect_all()
        prune_pools = config.get("prune_pools", [])
        for i, row in enumerate(app._ret_prune_store):
            if row[0] in prune_pools:
                selection.select_path(Gtk.TreePath.new_from_indices([i]))


# ── Online pool helpers ───────────────────────────────────────────────────────

def _get_online_pool_names():
    """Return a list of currently-ONLINE pool names from `zpool list`."""
    try:
        result = subprocess.run(
            ["zpool", "list", "-H", "-o", "name,health"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    pools = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) >= 2 and parts[1] == 'ONLINE':
            pools.append(parts[0])
    return pools


def _clear_non_default_policies_on_new_install(ctx):
    """On a fresh install, keep only the default retention policy."""
    if not getattr(ctx, 'is_new_install', False):
        return
    retention = get_all_retention(ctx.config)
    cleared = []
    for pool in list(retention.keys()):
        if pool != 'default':
            del retention[pool]
            cleared.append(pool)
    if cleared:
        try:
            save_config(ctx.config)
            log_msg(
                f"INFO: New install — cleared pool-specific retention policies: "
                f"{', '.join(cleared)}"
            )
        except OSError as e:
            log_msg(f"WARN: Could not save cleared retention policies: {e}")
    ctx.is_new_install = False


# ── Page factory ───────────────────────────────────────────────────────────────

def create_retention_page(app, ctx):
    """Build and return the Retention Policies page widget."""
    imported = import_legacy_retention(ctx.config, ctx.parent_dir)
    if imported:
        try:
            save_config(ctx.config)
            log_msg(
                f"INFO: Imported legacy retention policies into JSON: {', '.join(imported)}"
            )
        except OSError as e:
            log_msg(f"WARN: Could not save imported retention policies: {e}")

    _clear_non_default_policies_on_new_install(ctx)

    retention = get_all_retention(ctx.config)
    pool_list = ['default'] + sorted(p for p in retention if p != 'default')
    app._ret_pool_list = pool_list
    app._ret_pool = pool_list[0]
    app._ret_original = {}
    app._ret_pending = {}

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    outer.set_margin_start(12)
    outer.set_margin_end(12)
    outer.set_margin_top(10)
    outer.set_margin_bottom(10)

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = Gtk.Label()
    hdr.set_markup("<big><b>Retention Policies</b></big>")
    hdr.set_halign(Gtk.Align.START)
    outer.pack_start(hdr, False, False, 0)

    desc = Gtk.Label(
        label="Configure how many snapshots to keep per bucket for the selected pool.\n"
              "Min Age prevents deletion of snapshots younger than N days (0 = no limit)."
    )
    desc.set_halign(Gtk.Align.START)
    desc.set_line_wrap(True)
    outer.pack_start(desc, False, False, 0)

    # ── Pool selector ─────────────────────────────────────────────────────────
    pool_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pool_box.pack_start(Gtk.Label(label="Pool:"), False, False, 0)

    combo = Gtk.ComboBoxText()
    for p in pool_list:
        combo.append_text(p)
    combo.set_active(0)
    pool_box.pack_start(combo, False, False, 0)

    app._ret_pool_label = Gtk.Label()
    app._ret_pool_label.set_halign(Gtk.Align.START)
    pool_box.pack_start(app._ret_pool_label, True, True, 0)

    outer.pack_start(pool_box, False, False, 0)

    # ── Table (TreeView) ──────────────────────────────────────────────────────
    app._ret_store = Gtk.ListStore(str, str, int, int)

    tv = Gtk.TreeView(model=app._ret_store)
    tv.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    tv.set_reorderable(True)
    app._ret_view = tv
    app._ui_state.bind_treeview(app._ret_view, "retention_buckets_view")

    r0 = Gtk.CellRendererText()
    c0 = Gtk.TreeViewColumn("Bucket", r0, text=0)
    configure_treeview_column(c0, width=70)
    tv.append_column(c0)

    r1 = Gtk.CellRendererText()
    r1.set_property("foreground", "gray")
    c1 = Gtk.TreeViewColumn("Type", r1, text=1)
    configure_treeview_column(c1, width=60)
    tv.append_column(c1)

    r2 = Gtk.CellRendererSpin()
    r2.set_property("editable", True)
    r2.set_property("adjustment",
                    Gtk.Adjustment(value=1, lower=0, upper=9999,
                                   step_increment=1, page_increment=10))
    r2.set_property("digits", 0)
    r2.connect("edited", _on_retain_edited, app)
    r2.connect("editing-started", _on_editing_started, tv, 2)
    c2 = Gtk.TreeViewColumn("Retain Count", r2, text=2)
    configure_treeview_column(c2, width=90)
    tv.append_column(c2)
    app._ret_retain_renderer = r2

    r3 = Gtk.CellRendererSpin()
    r3.set_property("editable", True)
    r3.set_property("adjustment",
                    Gtk.Adjustment(value=0, lower=0, upper=9999,
                                   step_increment=1, page_increment=10))
    r3.set_property("digits", 0)
    r3.connect("edited", _on_minage_edited, app)
    r3.connect("editing-started", _on_editing_started, tv, 3)
    c3 = Gtk.TreeViewColumn("Min Age (days)", r3, text=3)
    configure_treeview_column(c3, width=110)
    tv.append_column(c3)
    app._ret_minage_renderer = r3

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_size_request(-1, 160)
    sw.add(tv)
    outer.pack_start(sw, False, False, 0)

    app._ret_store.connect("row-changed", lambda *_a: _update_ret_status(app))
    app._ret_store.connect("row-inserted", lambda *_a: _update_ret_status(app))
    app._ret_store.connect("row-deleted", lambda *_a: _update_ret_status(app))

    # ── Dirty / warning label ─────────────────────────────────────────────────
    app._ret_status_label = Gtk.Label()
    app._ret_status_label.set_halign(Gtk.Align.START)
    app._ret_status_label.set_line_wrap(True)
    outer.pack_start(app._ret_status_label, False, False, 0)

    # ── Prune section ─────────────────────────────────────────────────────────
    outer.pack_start(Gtk.Separator(), False, False, 8)

    prune_hdr = Gtk.Label()
    prune_hdr.set_markup("<b>Prune Snapshots</b>")
    prune_hdr.set_halign(Gtk.Align.START)
    outer.pack_start(prune_hdr, False, False, 0)

    prune_desc = Gtk.Label(
        label="Select one or more online pools that have a retention policy and click "
              "Prune. Each row runs `zfscleanup <pool> '' <label>`."
    )
    prune_desc.set_halign(Gtk.Align.START)
    prune_desc.set_line_wrap(True)
    outer.pack_start(prune_desc, False, False, 0)

    # Online pools TreeView (multi-select)
    app._ret_prune_store = Gtk.ListStore(str, str)
    pv = Gtk.TreeView(model=app._ret_prune_store)
    pv.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
    pv.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    pv.set_reorderable(True)
    app._ret_prune_view = pv
    app._ui_state.bind_treeview(app._ret_prune_view, "retention_prune_view")
    pv.connect("drag-end", _on_prune_drag_end, app)

    rp0 = Gtk.CellRendererText()
    cp0 = Gtk.TreeViewColumn("Pool", rp0, text=0)
    configure_treeview_column(cp0, width=140)
    pv.append_column(cp0)
    rp1 = Gtk.CellRendererText()
    cp1 = Gtk.TreeViewColumn("Health", rp1, text=1)
    configure_treeview_column(cp1, width=90)
    pv.append_column(cp1)

    psw = Gtk.ScrolledWindow()
    psw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    psw.set_size_request(-1, 200)
    psw.add(pv)
    outer.pack_start(psw, False, False, 0)

    # Snapshot label entry for prune
    label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    label_box.pack_start(Gtk.Label(label="Snapshot label:"), False, False, 0)
    app._ret_prune_label_entry = Gtk.Entry()
    prune_label = get_prune_label(ctx.config)
    app._ret_prune_label_entry.set_text(prune_label)
    app._ret_prune_label_entry.set_width_chars(20)
    app._ret_prune_label_entry.connect(
        "changed", lambda *_a: _update_ret_status(app)
    )
    app._ret_original_prune_label = prune_label
    label_box.pack_start(app._ret_prune_label_entry, False, False, 0)
    outer.pack_start(label_box, False, False, 0)

    # ── Wire up pool selector ─────────────────────────────────────────────────
    combo.connect("changed", _on_pool_changed, app)
    app._ret_combo = combo

    # Populate online pools list and load initial editor pool
    refresh_prune_pools(app)
    _load_pool_into_store(app, ctx, app._ret_pool_list[0])

    return outer


def refresh_prune_pools(app):
    """Refresh the prune list with online pools that have retention policies.

    The order is driven by the persisted ``prune_pools_order`` key, then by
    any in-session reorder, and finally by sorted pool name for newcomers.
    """
    if not hasattr(app, '_ret_prune_store') or not hasattr(app, 'ctx'):
        return
    retention = get_all_retention(app.ctx.config)
    policy_pools = {p for p in retention if p != 'default'}
    online = set(_get_online_pool_names())
    candidates = policy_pools & online

    saved_order = get_prune_pools_order(app.ctx.config)
    current_order = [
        row[0] for row in app._ret_prune_store if row[0] in candidates
    ]

    new_order = []
    seen = set()

    for pool in saved_order:
        if pool in candidates and pool not in seen:
            new_order.append(pool)
            seen.add(pool)

    for pool in current_order:
        if pool not in seen:
            new_order.append(pool)
            seen.add(pool)

    for pool in sorted(candidates - seen):
        new_order.append(pool)

    app._ret_prune_store.clear()
    for pool in new_order:
        app._ret_prune_store.append([pool, "ONLINE"])


def _on_prune_drag_end(treeview, drag_context, app):
    """Persist the new pool order after a drag-and-drop reorder."""
    if not hasattr(app, 'ctx'):
        return
    order = [row[0] for row in app._ret_prune_store]
    if order == get_prune_pools_order(app.ctx.config):
        return
    try:
        save_prune_pools_order(app.ctx.config, order)
    except OSError as e:
        log_msg(f"WARN: Could not save prune pool order: {e}")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_pool_into_store(app, ctx, pool, buckets=None):
    # _ret_original must always reflect the on-disk config, not any in-memory
    # pending edits, so that dirty detection works across pool switches.
    original_buckets = get_retention(ctx.config, pool)
    if buckets is None:
        buckets = original_buckets
    app._ret_store.clear()
    for bkt in buckets:
        label = BUCKET_LABELS.get(bkt['name'], bkt['name'])
        app._ret_store.append([bkt['name'], label, bkt['retain'], bkt['minage']])
    app._ret_pool = pool
    app._ret_original[pool] = copy.deepcopy(original_buckets)
    if hasattr(app, '_ret_pool_label'):
        app._ret_pool_label.set_text(f"Editing retention policy for pool: {pool}")
    _update_ret_status(app)


def _store_to_buckets(app):
    buckets = []
    for row in app._ret_store:
        buckets.append({'name': row[0], 'retain': row[2], 'minage': row[3]})
    return buckets


def _is_dirty(app):
    if app._ret_prune_label_entry.get_text().strip() != app._ret_original_prune_label:
        return True
    current = _store_to_buckets(app)
    if current != app._ret_original.get(app._ret_pool, []):
        return True
    for pool, pending in app._ret_pending.items():
        if pending != app._ret_original.get(pool, []):
            return True
    return False


def _update_ret_status(app):
    warnings = []
    for row in app._ret_store:
        name, _, retain, minage = row[0], row[1], row[2], row[3]
        if minage > 0 and retain == 0:
            warnings.append(
                f"Bucket '{name}': Min Age {minage}d has no effect when Retain Count is 0."
            )
    if _is_dirty(app):
        dirty = "Unsaved changes."
        if warnings:
            dirty += "\n" + "\n".join(warnings)
        app._ret_status_label.set_markup(f"<span foreground='orange'>{dirty}</span>")
    elif warnings:
        app._ret_status_label.set_markup(
            "<span foreground='orange'>" + "\n".join(warnings) + "</span>"
        )
    else:
        app._ret_status_label.set_text("")

    # Also update Save button styling
    btn = getattr(app, '_ret_save_button', None)
    if btn:
        set_button_markup_red(btn, _is_dirty(app))


def _on_pool_changed(combo, app):
    pool = combo.get_active_text()
    if not pool:
        return
    ctx = app.ctx
    # Stash the current pool's in-memory bucket values so that edits survive
    # a pool switch and can be saved together later.
    if hasattr(app, '_ret_pool') and app._ret_pool:
        app._ret_pending[app._ret_pool] = _store_to_buckets(app)
    retention = get_all_retention(ctx.config)
    if pool != 'default' and pool not in retention:
        response = _ask_create_policy(app, pool)
        if response == Gtk.ResponseType.YES:
            save_retention(ctx.config, pool, DEFAULT_RETENTION)
            log_msg(f"INFO: Created new retention policy for pool: {pool}")
        else:
            idx = app._ret_pool_list.index(app._ret_pool) if app._ret_pool in app._ret_pool_list else 0
            combo.set_active(idx)
            return
    pending = app._ret_pending.get(pool)
    _load_pool_into_store(app, ctx, pool, buckets=pending)


def _ask_create_policy(app, pool):
    """Ask user whether to create a missing policy entry."""
    dlg = Gtk.MessageDialog(
        transient_for=app, modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.NONE,
        text=f"No retention policy exists for pool '{pool}'.",
    )
    dlg.format_secondary_text(
        "Would you like to create one now with default settings?"
    )
    dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dlg.add_button("Add Now", Gtk.ResponseType.YES)
    dlg.set_default_response(Gtk.ResponseType.YES)
    response = dlg.run()
    dlg.destroy()
    return response


def _on_retain_edited(renderer, path, new_text, app):
    try:
        val = int(new_text)
        if val < 0:
            return
    except ValueError:
        return
    app._ret_store[path][2] = val
    _update_ret_status(app)


def _on_minage_edited(renderer, path, new_text, app):
    try:
        val = int(new_text)
        if val < 0:
            return
    except ValueError:
        return
    app._ret_store[path][3] = val
    _update_ret_status(app)


def _on_editing_started(renderer, editable, path, treeview, col_idx):
    """Connect key-press on the editable to handle Tab/Shift+Tab."""
    editable.connect(
        "key-press-event", handle_editing_key_press,
        treeview, path, col_idx, [2, 3])


def _on_ret_save(btn, app, ctx):
    # Commit any active cell edit so the store reflects the latest value.
    for renderer in (getattr(app, '_ret_retain_renderer', None),
                     getattr(app, '_ret_minage_renderer', None)):
        if renderer is not None:
            try:
                renderer.stop_editing(False)
            except Exception:
                pass

    label = app._ret_prune_label_entry.get_text().strip() or "dailybackup"
    saved_pools = []

    current_buckets = _store_to_buckets(app)

    # Save the currently visible pool if it differs from the original.
    if current_buckets != app._ret_original.get(app._ret_pool, []):
        try:
            save_retention(ctx.config, app._ret_pool, current_buckets)
        except OSError as e:
            _show_error(app, f"Failed to save retention policy for '{app._ret_pool}':\n{e}")
            return
        app._ret_original[app._ret_pool] = copy.deepcopy(current_buckets)
        app._ret_pending.pop(app._ret_pool, None)
        saved_pools.append(app._ret_pool)

    # Save any other pools whose edits are pending in memory.
    for pool, pending in list(app._ret_pending.items()):
        if pending == app._ret_original.get(pool, []):
            app._ret_pending.pop(pool, None)
            continue
        try:
            save_retention(ctx.config, pool, pending)
        except OSError as e:
            _show_error(app, f"Failed to save retention policy for '{pool}':\n{e}")
            return
        app._ret_original[pool] = copy.deepcopy(pending)
        app._ret_pending.pop(pool, None)
        saved_pools.append(pool)

    try:
        save_prune_label(ctx.config, label)
    except OSError as e:
        _show_error(app, f"Failed to save prune label:\n{e}")
        return
    app._ret_original_prune_label = label

    if saved_pools:
        if len(saved_pools) == 1:
            log_msg(f"INFO: Retention policy saved for pool: {saved_pools[0]}")
        else:
            log_msg(
                f"INFO: Retention policies saved for pools: {', '.join(sorted(saved_pools))}"
            )
    _update_ret_status(app)


def _on_ret_revert(btn, app, ctx):
    """Revert all pending retention changes, matching Save's scope."""
    app._ret_prune_label_entry.set_text(app._ret_original_prune_label)
    # Discard pending edits for every pool so Revert undoes what Save would
    # have persisted across the whole page.
    app._ret_pending.clear()
    _load_pool_into_store(app, ctx, app._ret_pool)


def _show_error(app, msg):
    dlg = Gtk.MessageDialog(
        transient_for=app, modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=msg,
    )
    dlg.run()
    dlg.destroy()
