"""Disk tab action handlers — extracted from disks_page.py."""

from disks_page import COL_D_BYID, COL_D_NAME
from logging_config import log_msg


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
