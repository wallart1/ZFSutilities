"""Disk tab action handlers — extracted from disks_page.py."""

import os

import node_config
import zfs_lock_manager as zlm
from command_builders import BashStep
from disk_wipe import build_wipe_command, show_wipe_dialog, wipe_block_reason, wipe_warnings
from disks_page import COL_D_BYID, COL_D_NAME, refresh_disks_page, update_disks_button_sensitivity
from logging_config import log_msg
from pools_page import on_pools_refresh


def _get_selected_disk_path(app):
    """Return the device path of the single selected disk row, or None."""
    selection = app.disks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if not pathlist:
        return None
    tree_iter = model.get_iter(pathlist[0])
    path = model.get_value(tree_iter, COL_D_NAME)
    if not path:
        path = model.get_value(tree_iter, COL_D_BYID)
    return path


def on_disks_smart_details(app):
    """Write smartctl -a output for the selected disk to the GUI log."""
    path = _get_selected_disk_path(app)
    if not path:
        log_msg("WARN: Select a disk to view SMART details")
        return

    details = app.ctx.disk_repository.smart_details(path)
    if not details or details == "n/a":
        log_msg(f"WARN: SMART details unavailable for {path}")
        return

    log_msg(f"INFO: SMART details for {path}:")
    for line in details.splitlines():
        if line.strip():
            log_msg(f"INFO: {line}")


def on_disks_wipe_labels(app):
    """Wipe labels/signatures from the selected inactive disk (Disks page action).

    Runs the ``zfswipe`` script (labelclear → wipefs → dd ladder) as a runner
    step after a typed-confirmation dialog. The script re-verifies that the
    device is inactive before touching anything.
    """
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Disk wipe is available only on the storage host")
        return

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    path = _get_selected_disk_path(app)
    if not path:
        log_msg("WARN: Select a disk to wipe")
        return

    data = app._disks_inventory_cache.get()
    disk = next((d for d in data.disks if d.path == path), None)
    if disk is None:
        log_msg(f"WARN: {path} is not in the disk inventory; refresh and retry")
        return
    reason = wipe_block_reason(disk, data.disks)
    if reason is not None:
        log_msg(f"WARN: {path} cannot be wiped: {reason}")
        return

    try:
        importable = app.ctx.zfs_repository.list_importable_pool_devices()
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not scan importable pools: {exc}")
        importable = {}
    if not show_wipe_dialog(app, disk, wipe_warnings(disk, data.disks, importable)):
        return

    cmd = build_wipe_command(disk)
    lock_id = zlm.acquire(disk.path, "w", f"Wipe labels on {disk.path}")
    step = BashStep(cmd, f"Wipe labels on {disk.path}", is_rsync=False, fatal=True)

    def _on_complete(cancelled=False, rc=None):
        zlm.release(lock_id)
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: Wipe cancelled for {disk.path}")
            return
        if rc:
            log_msg(f"WARN: Wipe failed for {disk.path} (rc={rc})")
            return
        log_msg(f"INFO: Wipe complete on {disk.path}")

    runner.operation_detail = f"Wipe labels: {os.path.basename(disk.path)}"
    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)
