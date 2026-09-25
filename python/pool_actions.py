"""
Pool tab action handlers — extracted from pools_page.py.
"""

import os
import re
import subprocess
import time

import gi

gi.require_version("Gtk", "3.0")
from backup_config import log_msg, save_pools
from gi.repository import Gtk
from gui_helpers import (
    add_scrolled_text_view,
    collect_dataset_busy_reasons,
    configure_treeview_column,
    create_dialog,
    diagnose_dataset_busy,
    set_button_markup_red,
)
from pool_watch import PoolWatchWindow
from pools_page import (
    COL_FLAG,
    COL_HEALTH,
    COL_NAME,
    FLAG_UNREGISTERED,
    _update_pools_dirty_indicator,
    get_selected_pool_names,
    refresh_pools_page,
    refresh_scrub_table,
    schedule_scrub_refresh_burst,
)
from scrub_manager import (
    pause_scrub,
    stop_scrub,
)


def on_pools_watch(app):
    """Open independent watch windows for all selected online pools."""
    rows = _get_selected_rows(app)
    known_names = {p["name"] for p in app.known_pools}
    selected = [(n, h) for n, h in rows if n in known_names]
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
    """Write zpool status and zpool get all output for the selected pool to the GUI log."""
    selection = app.pool_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if not pathlist:
        log_msg("WARN: Select a pool to view details")
        return

    tree_iter = model.get_iter(pathlist[0])
    pool_name = model.get_value(tree_iter, COL_NAME)

    status_text = app.ctx.zfs_repository.pool_status(pool_name)
    if not status_text:
        log_msg(f"WARN: Error getting status for '{pool_name}'")
        return

    log_msg(f"INFO: Pool details for {pool_name}:")
    for line in status_text.splitlines():
        if line.strip():
            log_msg(f"INFO: {line}")

    props_text = app.ctx.zfs_repository.pool_get_all(pool_name)
    if not props_text:
        log_msg(f"WARN: Error reading properties for '{pool_name}'")
        return

    log_msg(f"INFO: zpool get all output for {pool_name}:")
    for line in props_text.splitlines():
        if line.strip():
            log_msg(f"INFO: {line}")


def on_pools_add(app):
    """Add a pool to the registry."""
    prefill = ""
    selection = app.pool_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if pathlist:
        tree_iter = model.get_iter(pathlist[0])
        flag = model.get_value(tree_iter, COL_FLAG)
        if flag == FLAG_UNREGISTERED:
            prefill = model.get_value(tree_iter, COL_NAME)

    dialog = create_dialog(
        "Add Pool",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL), (Gtk.STOCK_OK, Gtk.ResponseType.OK)],
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

    app.known_pools.append({"name": pool_name, "offsite_candidate": False})
    refresh_pools_page(app)
    log_msg(f"INFO: Added '{pool_name}' to pool registry (unsaved)")


def _parse_importable_pools(zpool_output):
    """Parse 'zpool import' output into (name, details) tuples.

    Filters out pools whose config contains zvol-backed devices
    (device names starting with 'zd').
    """
    blocks = []
    current = []
    for line in zpool_output.split("\n"):
        if line.strip().startswith("pool:") and current:
            blocks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        blocks.append("\n".join(current))

    pools = []
    filtered = []
    for block in blocks:
        lines = block.split("\n")
        name = None
        in_config = False
        is_zvol_backed = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("pool:"):
                name = stripped.split(":", 1)[1].strip()
            elif stripped == "config:":
                in_config = True
            elif in_config and stripped:
                parts = stripped.split()
                if parts and parts[0].startswith("zd"):
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
        f"Import Details: {pool_name}",
        app,
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
    """Import selected importable pools, or show importable pools dialog if none selected."""
    selected = _get_selected_rows(app)
    importable_selected = [n for n, h in selected if h == "IMPORTABLE"]

    if importable_selected:
        dlg = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Import {len(importable_selected)} selected pool(s)?",
        )
        response = dlg.run()
        dlg.destroy()
        if response == Gtk.ResponseType.YES:
            for pool_name in importable_selected:
                _import_single_pool(app, pool_name)
            refresh_pools_page(app)
            refresh_scrub_table(app)
            schedule_scrub_refresh_burst(app)
        return

    # Fallback: show dialog of importable pools
    raw_output = app.ctx.zfs_repository.importable_pools_raw()

    importable, filtered = _parse_importable_pools(raw_output)

    if not importable:
        msg = "No pools available for import."
        if filtered:
            msg += (
                f"\n\n({len(filtered)} pool(s) hidden because they are backed by zvol partitions.)"
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
        "Import Pool",
        app,
        [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            ("Details", Gtk.ResponseType.APPLY),
            ("Import", Gtk.ResponseType.OK),
        ],
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
        info.set_markup(f"<small><i>{len(filtered)} zvol-backed pool(s) hidden</i></small>")
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
    refresh_scrub_table(app)
    schedule_scrub_refresh_burst(app)


def on_pools_export(app):
    """Export all selected pools, with diagnosis and recovery on failure."""
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
        success, stderr = app.ctx.zfs_repository.export_pool_detailed(pool_name)
        if success:
            log_msg(f"INFO: Pool '{pool_name}' exported successfully")
            continue

        log_msg(f"WARN: Error exporting pool '{pool_name}'")
        if _try_export_with_recovery(app, pool_name, stderr):
            log_msg(f"INFO: Pool '{pool_name}' exported successfully after resolving blockers")

    refresh_pools_page(app)
    refresh_scrub_table(app)
    schedule_scrub_refresh_burst(app)


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
        app.known_pools = [p for p in app.known_pools if p["name"] != pool_name]
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
    btn = getattr(app, "_pools_save_btn", None)
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
    from pools_page import refresh_scrub_table, schedule_scrub_refresh_burst

    refresh_scrub_table(app)
    schedule_scrub_refresh_burst(app)


def on_scrub_pause(app):
    """Pause selected pools in the scrub queue."""
    pools = get_selected_pool_names(app.scrub_view)
    if not pools:
        log_msg("WARN: Select at least one pool to pause")
        return
    app.scrub_queue.pause_pools(pools)
    for name in pools:
        pause_scrub(name)
    from pools_page import refresh_scrub_table, schedule_scrub_refresh_burst

    refresh_scrub_table(app)
    schedule_scrub_refresh_burst(app)


def on_scrub_resume(app):
    """Return selected paused pools to the pending queue.

    The scrub manager resumes them when a slot is available; they do not
    preempt scrubs that are already running.
    """
    pools = get_selected_pool_names(app.scrub_view)
    if not pools:
        log_msg("WARN: Select at least one pool to resume")
        return
    to_resume = [n for n in pools if n in app.scrub_queue.paused]
    if not to_resume:
        log_msg("WARN: Selected pools are not paused")
        return
    app.scrub_queue.resume_pools(to_resume)
    from pools_page import refresh_scrub_table, schedule_scrub_refresh_burst

    refresh_scrub_table(app)
    schedule_scrub_refresh_burst(app)


def on_scrub_stop(app):
    """Stop selected scrubs and remove from queue."""
    pools = get_selected_pool_names(app.scrub_view)
    if not pools:
        log_msg("WARN: Select at least one pool to stop")
        return
    for name in pools:
        stop_scrub(name)
    app.scrub_queue.remove_pools(pools)
    from pools_page import refresh_scrub_table, schedule_scrub_refresh_burst

    refresh_scrub_table(app)
    schedule_scrub_refresh_burst(app)


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
        rows.append((model.get_value(tree_iter, COL_NAME), model.get_value(tree_iter, COL_HEALTH)))
    return rows


# ---------------------------------------------------------------------------
# Pool export failure recovery
# ---------------------------------------------------------------------------


def _extract_unmount_failure(stderr):
    """Return the mountpoint from a 'cannot unmount' zpool export error, or None."""
    for line in stderr.splitlines():
        # Regex: cannot unmount '([^']+)': unmount failed
        # Anchors on zpool export's literal "cannot unmount '<mountpoint>':
        # unmount failed" diagnostic; group 1 captures the quoted mountpoint
        # (any run of non-quote characters) so the caller can resolve which
        # dataset blocked the export.
        match = re.search(r"cannot unmount '([^']+)': unmount failed", line)
        if match:
            return match.group(1)
    return None


def _collect_export_blockers(repo, pool):
    """Return BusyReason objects for every dataset in *pool* that blocks export."""
    blockers = []
    try:
        datasets = [r.name for r in repo.list_datasets(pool=pool)]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return blockers

    for dataset in datasets:
        blockers.extend(collect_dataset_busy_reasons(dataset, repo=repo))
    return blockers


def _unmount_pool_filesystems(repo, pool, blockers):
    """Unmount mounted filesystems in *pool* that have no other blocker.

    Filesystems with busy processes or active shares are skipped; those are
    handled via approval dialogs. Returns (all_succeeded, error_message).
    """
    blocked = {b.dataset for b in blockers if b.category in ("busy_processes", "nfs", "smb")}
    try:
        rows = [
            r
            for r in repo.list_datasets(pool=pool)
            if r.ds_type == "filesystem" and r.mounted == "yes"
        ]
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return False, str(exc)

    rows.sort(key=lambda r: r.name.count("/"), reverse=True)
    for row in rows:
        if row.name in blocked:
            continue
        success, stderr = repo.unmount_filesystem(row.name)
        if success:
            log_msg(f"INFO: Unmounted {row.name}")
        else:
            return False, stderr.strip()
    return True, ""


def _approve_and_stop_vms(app, blockers):
    """Ask per-VM approval and stop any approved VMs. Returns False if declined."""
    vm_blockers = [b for b in blockers if b.category == "vm"]
    if not vm_blockers:
        return True

    vmids = sorted({b.data["vmid"] for b in vm_blockers if b.data})
    for vmid in vmids:
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Stop VM {vmid}?",
        )
        dialog.format_secondary_text(
            f"VM {vmid} is running and preventing the pool export. "
            "Stopping it will shut the VM down."
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return False
        result = subprocess.run(["qm", "stop", vmid], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            log_msg(f"WARN: Failed to stop VM {vmid}: {result.stderr.strip()}")
            return False
        log_msg(f"INFO: Stopped VM {vmid}")
    return True


def _approve_and_remove_iscsi(app, blockers):
    """Ask per-LUN approval and tear down any approved iSCSI LUNs/backstores."""
    iscsi_blockers = [b for b in blockers if b.category == "iscsi"]
    if not iscsi_blockers:
        return True

    for reason in iscsi_blockers:
        bsname = reason.data.get("bsname") if reason.data else None
        lun_info = reason.data.get("lun_info", "") if reason.data else ""
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove iSCSI LUN for {bsname}?",
        )
        dialog.format_secondary_text(
            f"{reason.detail} Removing it will disconnect any initiator using this LUN."
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return False
        if not bsname:
            continue

        # Remove the LUN mapping first, then the backstore.
        removed_lun = False
        if lun_info:
            # Regex: (iqn\.\S+)\s*\(LUN\s*(\d+)\)
            # Parses the lun_info string produced by collect_dataset_busy_reasons
            # (e.g. "iqn.2023-01.com.example:t1 (LUN 3)"); group 1 captures the
            # full IQN (non-whitespace run starting with "iqn."), group 2 the
            # LUN number. \S and \s are used because targetcli output contains
            # no spaces inside IQNs but may pad around the "(LUN n)" suffix.
            m = re.search(r"(iqn\.\S+)\s*\(LUN\s*(\d+)\)", lun_info)
            if m:
                iqn, lun_num = m.groups()
                result = subprocess.run(
                    ["targetcli", f"/iscsi/{iqn}/tpg1/luns", "delete", f"lun{lun_num}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    log_msg(
                        f"WARN: Failed to remove LUN {lun_num} from {iqn}: {result.stderr.strip()}"
                    )
                    return False
                removed_lun = True
                log_msg(f"INFO: Removed LUN {lun_num} from {iqn}")

        # Some backstores have no LUN mapping; still try to remove the backstore.
        result = subprocess.run(
            ["targetcli", "/backstores/block", "delete", bsname],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 and not removed_lun:
            log_msg(f"WARN: Failed to remove iSCSI backstore {bsname}: {result.stderr.strip()}")
            return False
        if result.returncode == 0:
            log_msg(f"INFO: Removed iSCSI backstore {bsname}")
    return True


def _approve_and_unshare(app, blockers, repo):
    """Ask per-share approval and disable any approved NFS/SMB shares."""
    share_blockers = [b for b in blockers if b.category in ("nfs", "smb")]
    if not share_blockers:
        return True

    for reason in share_blockers:
        prop = reason.data.get("prop") if reason.data else None
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Disable {reason.category.upper()} share on {reason.dataset}?",
        )
        dialog.format_secondary_text(
            f"{reason.detail} Disabling the share will disconnect any client using it."
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return False
        if not prop or not repo.set_property(reason.dataset, prop, "off"):
            log_msg(f"WARN: Failed to disable {reason.category.upper()} share on {reason.dataset}")
            return False
        log_msg(f"INFO: Disabled {reason.category.upper()} share on {reason.dataset}")
    return True


def _approve_and_terminate_processes(app, blockers):
    """Ask per-mountpoint approval and terminate any approved busy processes."""
    proc_blockers = [b for b in blockers if b.category == "busy_processes"]
    if not proc_blockers:
        return True

    for reason in proc_blockers:
        pids = reason.data.get("pids", []) if reason.data else []
        names = reason.data.get("names", "") if reason.data else ""
        mountpoint = reason.data.get("mountpoint", "") if reason.data else ""
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Terminate processes using the pool?",
        )
        proc_list = "\n".join(f"  • {name}" for name in sorted(set(names.split())))
        dialog.format_secondary_text(
            f"The following processes are using {mountpoint}:\n\n{proc_list}\n\n"
            "Terminating them may lose unsaved work in those applications."
        )
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return False
        for pid in pids:
            try:
                subprocess.run(["kill", "-TERM", str(pid)], check=False)
            except OSError as exc:
                log_msg(f"WARN: Could not signal PID {pid}: {exc}")
        # Give SIGTERM a moment to take effect.
        time.sleep(1)
        survivors = [pid for pid in pids if _pid_exists(pid)]
        if survivors:
            dialog2 = Gtk.MessageDialog(
                transient_for=app,
                modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Processes did not terminate. Force kill?",
            )
            dialog2.format_secondary_text(
                f"PIDs {', '.join(str(p) for p in survivors)} did not respond to SIGTERM."
            )
            response2 = dialog2.run()
            dialog2.destroy()
            if response2 != Gtk.ResponseType.YES:
                return False
            for pid in survivors:
                try:
                    subprocess.run(["kill", "-KILL", str(pid)], check=False)
                except OSError as exc:
                    log_msg(f"WARN: Could not kill PID {pid}: {exc}")
        log_msg(f"INFO: Terminated processes using {mountpoint}")
    return True


def _pid_exists(pid):
    """Return True if *pid* is still alive."""
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def _show_export_blockers_dialog(app, pool, blockers):
    """Show a non-actionable summary of why the pool export failed."""
    lines = [f"Pool '{pool}' cannot be exported because the following blockers remain:\n"]
    for reason in blockers:
        lines.append(f"• {reason.dataset}: {reason.detail}")
        if reason.action:
            lines.append(f"  → {reason.action}")
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text="Pool export blocked",
    )
    dialog.format_secondary_text("\n".join(lines))
    dialog.run()
    dialog.destroy()


def _try_export_with_recovery(app, pool_name, stderr):
    """Diagnose and attempt to resolve blockers preventing pool export.

    Returns True if the pool was successfully exported after recovery.
    """
    repo = app.ctx.zfs_repository

    mountpoint = _extract_unmount_failure(stderr)
    dataset = None
    if mountpoint:
        dataset = repo.dataset_for_mountpoint(mountpoint, pool=pool_name)
    if dataset:
        diagnose_dataset_busy(dataset, stderr_text=stderr, repo=repo)
    else:
        log_msg(f"WARN: Could not determine which dataset blocked export of '{pool_name}'")
        if stderr.strip():
            log_msg(f"WARN: zpool export stderr: {stderr.strip()}")

    blockers = _collect_export_blockers(repo, pool_name)
    resolvable = [b for b in blockers if b.resolvable]
    unresolvable = [b for b in blockers if not b.resolvable]

    if unresolvable:
        for reason in unresolvable:
            log_msg(f"WARN: {reason.dataset}: {reason.detail}")

    if not resolvable and not unresolvable:
        log_msg(
            "WARN: No specific blockers identified. Common causes are active sends/receives, "
            "scrubs, or processes holding the pool through a different path."
        )
        return False

    if not resolvable:
        _show_export_blockers_dialog(app, pool_name, unresolvable)
        return False

    # Safe auto-unmount of filesystems that have no other blocker.
    unmount_ok, unmount_err = _unmount_pool_filesystems(repo, pool_name, blockers)
    if not unmount_ok:
        log_msg(f"WARN: Auto-unmount of filesystems failed: {unmount_err}")

    # Approval-driven resolution of side-effect blockers.
    approved = True
    approved &= _approve_and_stop_vms(app, blockers)
    approved &= _approve_and_remove_iscsi(app, blockers)
    approved &= _approve_and_unshare(app, blockers, repo)
    approved &= _approve_and_terminate_processes(app, blockers)

    if not approved:
        log_msg(f"INFO: Export of '{pool_name}' cancelled by user")
        return False

    success, stderr2 = repo.export_pool_detailed(pool_name)
    if success:
        return True

    log_msg(f"WARN: Export of '{pool_name}' still failed after recovery: {stderr2.strip()}")
    return False
