"""
Retention tab action handlers — extracted from retention_page.py.
"""

import shlex
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from backup_config import (
    get_all_retention, save_retention, save_config,
    DEFAULT_RETENTION, log_msg,
)
from command_builders import _dryrun_assignments, BashStep
from gui_helpers import set_button_markup_red
import zfs_lock_manager as zlm
from retention_page import (
    _get_online_pool_names, _show_error, _update_ret_status,
    _load_pool_into_store, _on_ret_save, _on_ret_revert,
    refresh_prune_pools, BUCKET_LABELS,
)


def on_retention_add_policy(app, ctx):
    """Create a new retention policy for a pool, seeded from `default`."""
    retention = get_all_retention(ctx.config)
    known = list(getattr(app, 'known_pools', []) or [])
    known_names = [p["name"] for p in known]
    online = _get_online_pool_names()
    candidates = []
    for p in known_names + online:
        if p not in retention and p not in candidates:
            candidates.append(p)

    dlg = Gtk.Dialog(
        title="Add Retention Policy",
        transient_for=app,
        modal=True,
        destroy_with_parent=True,
    )
    dlg.add_buttons(
        "Cancel", Gtk.ResponseType.CANCEL,
        "Add", Gtk.ResponseType.OK,
    )
    dlg.set_default_response(Gtk.ResponseType.OK)

    content = dlg.get_content_area()
    content.set_spacing(8)
    content.set_margin_start(10)
    content.set_margin_end(10)
    content.set_margin_top(10)

    label = Gtk.Label(label="Pool name:")
    label.set_halign(Gtk.Align.START)
    content.add(label)

    if candidates:
        combo = Gtk.ComboBoxText.new_with_entry()
        for p in candidates:
            combo.append_text(p)
        combo.set_active(0)
        entry = combo.get_child()
        content.add(combo)
    else:
        entry = Gtk.Entry()
        entry.set_width_chars(1)
        content.add(entry)
    entry.set_activates_default(True)

    note = Gtk.Label()
    note.set_markup(
        "<small>Will be seeded from the current 'default' policy.</small>"
    )
    note.set_halign(Gtk.Align.START)
    content.add(note)

    dlg.show_all()
    response = dlg.run()
    pool = entry.get_text().strip()
    dlg.destroy()

    if response != Gtk.ResponseType.OK or not pool:
        return
    if pool in retention:
        log_msg(f"WARN: Retention policy for '{pool}' already exists")
        return

    default_buckets = retention.get('default') or DEFAULT_RETENTION
    try:
        save_retention(ctx.config, pool, [dict(b) for b in default_buckets])
    except OSError as e:
        _show_error(app, f"Failed to create policy for '{pool}':\n{e}")
        return

    if pool not in app._ret_pool_list:
        app._ret_pool_list.append(pool)
        app._ret_combo.append_text(pool)
    idx = app._ret_pool_list.index(pool)
    app._ret_combo.set_active(idx)
    log_msg(f"INFO: Created retention policy for pool: {pool}")

    refresh_prune_pools(app)


def on_retention_remove_policy(app, ctx):
    """Delete the currently-selected pool's retention policy."""
    pool = app._ret_pool
    if pool == 'default':
        _show_error(app, "The 'default' retention policy cannot be removed.")
        return

    dlg = Gtk.MessageDialog(
        transient_for=app, modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Remove retention policy for pool '{pool}'?",
    )
    dlg.format_secondary_text(
        "The pool will be removed from the Prune list and will fall back to "
        "the default retention policy."
    )
    response = dlg.run()
    dlg.destroy()
    if response != Gtk.ResponseType.YES:
        return

    retention = get_all_retention(ctx.config)
    if pool in retention:
        del retention[pool]
        try:
            save_config(ctx.config)
        except OSError as e:
            _show_error(app, f"Failed to save after removing '{pool}':\n{e}")
            return
        log_msg(f"INFO: Removed retention policy for pool: {pool}")

    if pool in app._ret_pool_list:
        idx = app._ret_pool_list.index(pool)
        app._ret_pool_list.remove(pool)
        app._ret_combo.remove(idx)
    app._ret_original.pop(pool, None)
    app._ret_combo.set_active(0)

    refresh_prune_pools(app)


def on_retention_prune(app, ctx):
    """Run `zfscleanup <pool> '' <label>` for each selected online pool."""
    app.clear_log_status()
    if not hasattr(app, '_ret_prune_view'):
        log_msg("WARN: Retention page not initialized")
        return
    selection = app._ret_prune_view.get_selection()
    model, paths = selection.get_selected_rows()
    if not paths:
        log_msg("WARN: Select one or more pools in the Prune list")
        return

    label = app._ret_prune_label_entry.get_text().strip()
    if not label:
        _show_error(app, "Please enter a snapshot label for the prune operation.")
        return

    selected = {model[p][0] for p in paths}
    # Walk the model in visual order so execution order matches the list.
    pools = [row[0] for row in model if row[0] in selected]

    runner = getattr(app, 'retention_runner', None)
    if runner is None:
        log_msg("WARN: Retention runner not available")
        return
    if runner.running:
        log_msg("WARN: A prune operation is already running")
        return

    dryrun = getattr(app, '_dry_run_active', False)

    if dryrun:
        log_msg("INFO: Dry run mode enabled — no changes will be made")

    for pool in pools:
        if not zlm.check(pool, "w"):
            log_msg(
                f"WARN: cannot prune {pool}: pool is locked by another operation"
            )
            return

    steps = []
    for pool in pools:
        bash_cmd = (
            f'source ~/bashinit; bashinit; mydir="{ctx.parent_dir}"; '
            f'source "$mydir/zfscleanup"; '
            f'{_dryrun_assignments(dryrun)}'
            f'autoproceed="Y"; '
            f'releaseholds="Y"; '
            f'cleanup "{pool}" "" "{label}"'
        )
        steps.append(BashStep(
            ["bash", "-c", bash_cmd],
            f"Prune {pool} (label={label})",
            is_rsync=False,
            fatal=False,
        ))

    def _on_prune_complete(cancelled=False):
        if hasattr(app, 'update_action_buttons'):
            app.update_action_buttons("retention")

    runner.set_steps(steps)
    runner.start(on_complete=_on_prune_complete)
    if hasattr(app, 'update_action_buttons'):
        app.update_action_buttons("retention")


def on_retention_mass_delete(app, ctx):
    """Mass-delete snapshots across selected prune pools."""
    app.clear_log_status()
    if not hasattr(app, '_ret_prune_view'):
        log_msg("WARN: Retention page not initialized")
        return
    selection = app._ret_prune_view.get_selection()
    model, paths = selection.get_selected_rows()
    if not paths:
        log_msg("WARN: Select one or more pools in the Prune list")
        return

    label = app._ret_prune_label_entry.get_text().strip()
    if not label:
        _show_error(app, "Please enter a snapshot label for the mass delete operation.")
        return

    selected = {model[p][0] for p in paths}
    # Walk the model in visual order so execution order matches the list.
    pools = [row[0] for row in model if row[0] in selected]

    runner = getattr(app, 'retention_runner', None)
    if runner is None:
        log_msg("WARN: Retention runner not available")
        return
    if runner.running:
        log_msg("WARN: A retention operation is already running")
        return

    dryrun = getattr(app, '_dry_run_active', False)

    widgets = app._ret_mass_delete_widgets
    includes = widgets["includes"].get_text().strip()
    excludes = widgets["excludes"].get_text().strip()
    startwith = widgets["startwith"].get_text().strip()
    endwith = widgets["endwith"].get_text().strip()
    snapshot_has = widgets["snapshot_has"].get_text().strip()
    releaseholds = "Y" if widgets["releaseholds"].get_active() == 0 else "N"
    ignore = "Y" if app._ret_ignore_retention_check.get_active() else "N"

    var_assignments = f'{_dryrun_assignments(dryrun)}'
    var_assignments += f'ignore_retention_policies="{ignore}"; '
    var_assignments += f'releaseholds="{releaseholds}"; '
    var_assignments += f'snapshot_label="{label}"; '
    var_assignments += f'snapshot_has="{snapshot_has}"; '
    if includes:
        items = shlex.split(includes)
        arr = " ".join(f'"{i}"' for i in items)
        var_assignments += f'includes=({arr}); '
    else:
        var_assignments += 'includes=(); '
    if excludes:
        items = shlex.split(excludes)
        arr = " ".join(f'"{i}"' for i in items)
        var_assignments += f'excludes=({arr}); '
    else:
        var_assignments += 'excludes=(); '
    if startwith:
        var_assignments += f'startwith="{startwith}"; '
    if endwith:
        var_assignments += f'endwith="{endwith}"; '

    pool_list = " ".join(shlex.quote(p) for p in pools)
    bash_cmd = (
        f'source ~/bashinit; bashinit; mydir="{ctx.parent_dir}"; '
        f'source "$mydir/zfsmassdelsnaps"; '
        f'{var_assignments}'
        f'mass_delete_snapshots {pool_list}'
    )

    step = BashStep(
        ["bash", "-c", bash_cmd],
        f"Mass Delete ({', '.join(pools)})",
        is_rsync=False,
        fatal=False,
    )

    def _on_mass_delete_complete(cancelled=False):
        if hasattr(app, 'update_action_buttons'):
            app.update_action_buttons("retention")

    runner.set_steps([step])
    runner.start(on_complete=_on_mass_delete_complete)
    if hasattr(app, 'update_action_buttons'):
        app.update_action_buttons("retention")


def on_retention_add_bucket(app, ctx):
    """Add a new retention bucket to the current pool's policy."""
    dlg = Gtk.Dialog(
        title="Add Retention Bucket",
        transient_for=app,
        modal=True,
        destroy_with_parent=True,
    )
    dlg.add_buttons(
        Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
        Gtk.STOCK_OK, Gtk.ResponseType.OK,
    )
    dlg.set_default_response(Gtk.ResponseType.OK)

    content = dlg.get_content_area()
    content.set_spacing(10)
    content.set_margin_start(10)
    content.set_margin_end(10)
    content.set_margin_top(10)

    label = Gtk.Label(label="Bucket name (single letter, e.g. 'x'):")
    label.set_halign(Gtk.Align.START)
    content.add(label)

    entry = Gtk.Entry()
    entry.set_width_chars(1)
    entry.set_max_length(1)
    entry.set_activates_default(True)
    content.add(entry)

    dlg.show_all()
    response = dlg.run()
    bucket_name = entry.get_text().strip().lower()
    dlg.destroy()

    if response != Gtk.ResponseType.OK or not bucket_name:
        return

    for row in app._ret_store:
        if row[0] == bucket_name:
            log_msg(f"WARN: Bucket '{bucket_name}' already exists")
            return

    label = BUCKET_LABELS.get(bucket_name, bucket_name.upper())
    app._ret_store.append([bucket_name, label, 0, 0])
    _update_ret_status(app)
    log_msg(f"INFO: Added bucket '{bucket_name}' (unsaved)")


def on_retention_remove_bucket(app, ctx):
    """Remove the selected retention bucket from the current pool's policy."""
    if not hasattr(app, '_ret_view'):
        log_msg("WARN: Select a bucket to remove")
        return
    selection = app._ret_view.get_selection()
    model, tree_iter = selection.get_selected()
    if tree_iter is None:
        log_msg("WARN: Select a bucket to remove")
        return

    bucket_name = model.get_value(tree_iter, 0)
    model.remove(tree_iter)
    _update_ret_status(app)
    log_msg(f"INFO: Removed bucket '{bucket_name}' (unsaved)")


def on_retention_save(app, ctx):
    """Save the current pool's retention policy."""
    _on_ret_save(None, app, ctx)


def on_retention_revert(app, ctx):
    """Revert the current pool's retention policy to last saved state."""
    _on_ret_revert(None, app, ctx)


def is_retention_dirty(app):
    """Return True if there are unsaved changes."""
    if not hasattr(app, '_ret_original'):
        return False
    from retention_page import _is_dirty
    return _is_dirty(app)


def check_retention_dirty(app):
    """Compare current UI state to last-saved state; style Save button accordingly."""
    btn = getattr(app, '_ret_save_button', None)
    if btn:
        set_button_markup_red(btn, is_retention_dirty(app))
