"""
Dataset action handlers — snapshot, delete, hold, rollback, browse, etc.

Called exclusively through the action dispatch table in action_dispatch.py.
"""

import subprocess
from datetime import datetime

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from backup_config import log_msg
from gui_helpers import (
    create_dialog, add_scrolled_text_view, get_tree_selection_items,
    get_snapshot_mountpoint, get_busy_processes, diagnose_dataset_busy,
)
from datasets_page import refresh_datasets_page, update_ds_button_sensitivity
from command_builders import BashStep
import zfs_lock_manager as zlm


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _repo(app):
    """Return the ZFS repository from the application context."""
    return app.ctx.zfs_repository


def _unique_parent_datasets(snapshot_items: list) -> list:
    """Return the unique parent datasets for a list of snapshot items."""
    seen = set()
    parents = []
    for s in snapshot_items:
        parent = s["dataset"]
        if parent not in seen:
            seen.add(parent)
            parents.append(parent)
    return parents


def _input_dialog(parent, title, widgets, default=""):
    """Show a dialog with extra *widgets* and a single text entry."""
    dialog = create_dialog(title, parent, [
        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
        (Gtk.STOCK_OK, Gtk.ResponseType.OK),
    ], default_response=Gtk.ResponseType.OK)
    content = dialog.get_content_area()
    for w in widgets:
        content.add(w)
    entry = Gtk.Entry()
    entry.set_width_chars(1)
    entry.set_text(default)
    entry.set_activates_default(True)
    content.add(entry)
    dialog.show_all()
    response = dialog.run()
    text = entry.get_text().strip()
    dialog.destroy()
    return response, text


def _confirm_yes_no(parent, primary, secondary):
    """Show a YES/NO warning dialog; return True if YES was clicked."""
    dialog = Gtk.MessageDialog(
        transient_for=parent, modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text=primary,
    )
    dialog.format_secondary_text(secondary)
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.YES


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def on_datasets_snapshot(app):
    """Create a snapshot on the selected dataset."""
    items = get_tree_selection_items(app.datasets_view)
    ds_items = [i for i in items if i["type"] in ("pool", "dataset")]
    if len(ds_items) != 1:
        log_msg("WARN: Select exactly one dataset to snapshot")
        return
    dataset = ds_items[0]["name"]

    now = datetime.now()
    suggested = now.strftime("manual-%Y-%m-%dT%H:%M")
    ds_label = Gtk.Label()
    ds_label.set_markup(f"<b>Dataset:</b> {dataset}")
    ds_label.set_halign(Gtk.Align.START)
    ds_label.set_selectable(True)
    response, snap_name = _input_dialog(
        app, "Create Snapshot",
        [ds_label, Gtk.Label(label="Snapshot name (without @):")],
        suggested,
    )
    if response != Gtk.ResponseType.OK or not snap_name:
        return
    if " " in snap_name or "/" in snap_name:
        log_msg("WARN: Snapshot name cannot contain spaces or slashes")
        return

    full_snap = f"{dataset}@{snap_name}"
    log_msg(f"INFO: Creating snapshot: {full_snap}")
    try:
        with zlm.lock(dataset, "w", f"snapshot {full_snap}"):
            if _repo(app).snapshot(full_snap):
                log_msg(f"INFO: Snapshot created: {full_snap}")
                refresh_datasets_page(app)
            else:
                log_msg("WARN: Error creating snapshot")
    except RuntimeError as exc:
        log_msg(f"WARN: cannot snapshot {dataset}: {exc}")
    except FileNotFoundError:
        log_msg("WARN: Error: zfs command not found")


def on_datasets_delete(app):
    """Delete selected datasets, snapshots, or release holds."""
    items = get_tree_selection_items(app.datasets_view)
    if not items:
        log_msg("WARN: Select something to delete")
        return

    datasets = [i for i in items if i["type"] == "dataset"]
    snaps = [i for i in items if i["type"] == "snapshot"]
    holds = [i for i in items if i["type"] == "hold"]

    if datasets:
        _delete_datasets(app, datasets)
    elif snaps:
        _delete_snapshots(app, snaps)
    elif holds:
        _release_holds(app, holds)


def _delete_datasets(app, datasets):
    """Run zfsdelfs on selected datasets with pre-flight checks."""
    repo = _repo(app)
    details = []
    warnings = []
    for ds in datasets:
        ds_name = ds["name"]
        ds_info = {"name": ds_name, "snapshots": [], "holds": []}

        try:
            ds_info["snapshots"] = repo.list_all_snapshot_names(pool=ds_name)
        except subprocess.CalledProcessError:
            pass

        for snap in ds_info["snapshots"]:
            try:
                ds_info["holds"].extend(
                    f"{hold.tag} on {snap}" for hold in repo.list_holds(snap)
                )
            except subprocess.CalledProcessError:
                pass

        try:
            if repo.get_recursive_snapshot_clones(ds_name):
                warnings.append(f"{ds_name} has ZFS clone dependents")
        except subprocess.CalledProcessError:
            pass

        details.append(ds_info)

    lines = []
    total_snaps = total_holds = 0
    for ds_info in details:
        lines.append(f"Dataset: {ds_info['name']}")
        snaps = ds_info["snapshots"]
        if snaps:
            lines.append(f"  Snapshots ({len(snaps)}):")
            for s in snaps[:20]:
                lines.append(f"    @{s.split('@')[1]}")
            if len(snaps) > 20:
                lines.append(f"    ... and {len(snaps) - 20} more")
            total_snaps += len(snaps)
        else:
            lines.append("  (no snapshots)")
        holds = ds_info["holds"]
        if holds:
            lines.append(f"  Holds ({len(holds)}):")
            for h in holds[:10]:
                lines.append(f"    {h}")
            if len(holds) > 10:
                lines.append(f"    ... and {len(holds) - 10} more")
            total_holds += len(holds)
        lines.append("")

    if warnings:
        lines.extend(["WARNINGS:"] + [f"  ⚠ {w}" for w in warnings] + [""])

    for ds_info in details:
        ds_name = ds_info["name"]
        if not zlm.check(ds_name, "x"):
            log_msg(f"WARN: cannot destroy {ds_name}: dataset is locked by another operation")
            return

    body = "\n".join(lines)

    dialog = create_dialog("Destroy Dataset(s)", app, [
        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
        ("Destroy", Gtk.ResponseType.OK),
    ])
    content = dialog.get_content_area()
    header = Gtk.Label()
    header.set_markup(
        f"<b>About to destroy {len(details)} dataset(s), {total_snaps} "
        f"snapshot(s), and release {total_holds} hold(s).</b>"
    )
    header.set_halign(Gtk.Align.START)
    content.add(header)
    add_scrolled_text_view(content, body, min_height=250)

    dialog.show_all()
    response = dialog.run()
    dialog.destroy()
    if response != Gtk.ResponseType.OK:
        return

    runner = getattr(app, 'dataset_runner', None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    parent_dir = app.parent_dir
    steps = []
    for ds_info in details:
        ds_name = ds_info["name"]
        bash_cmd = (
            f'autoproceed="Y"; source ~/bashinit; bashinit; '
            f'mydir="{parent_dir}"; source "$mydir/zfsdelfs"; '
            f'delfs "{ds_name}"'
        )
        steps.append(BashStep(
            ["bash", "-c", bash_cmd],
            f"Destroy {ds_name}",
            is_rsync=False,
            fatal=False,
        ))

    def _on_delete_complete(cancelled=False):
        refresh_datasets_page(app)

    runner.set_steps(steps)
    runner.start(on_complete=_on_delete_complete)


def _delete_snapshots(app, snaps):
    """Delete selected snapshots after checking for holds."""
    repo = _repo(app)
    held = []
    for s in snaps:
        full = f"{s['dataset']}@{s['name']}"
        try:
            if repo.list_holds(full):
                held.append(s["name"])
        except subprocess.CalledProcessError:
            pass

    if held:
        log_msg(
            f"WARN: Cannot delete: {', '.join(held)} still have holds. "
            "Delete the holds first."
        )
        return

    snap_names = [f"{s['dataset']}@{s['name']}" for s in snaps]
    display = "\n  ".join(snap_names)
    if not _confirm_yes_no(app, f"Delete {len(snap_names)} snapshot(s)?",
                           f"  {display}\n\nThis cannot be undone."):
        return

    parents = _unique_parent_datasets(snaps)
    try:
        with zlm.locks("w", parents):
            errors = 0
            for full in snap_names:
                if repo.destroy(full):
                    log_msg(f"INFO: Deleted: {full}")
                else:
                    log_msg(f"WARN: Error deleting {full}")
                    diagnose_dataset_busy(full, repo=repo)
                    errors += 1
            if not errors:
                log_msg(f"INFO: Deleted {len(snap_names)} snapshot(s)")
    except RuntimeError as exc:
        log_msg(f"WARN: cannot delete snapshots: {exc}")
    refresh_datasets_page(app)


def _release_holds(app, holds):
    """Release selected holds."""
    repo = _repo(app)
    names = "\n  ".join(
        f"{h['tag']} on {h['dataset']}@{h['snapshot']}" for h in holds
    )
    if not _confirm_yes_no(app, f"Release {len(holds)} hold(s)?", f"  {names}"):
        return

    parents = _unique_parent_datasets(holds)
    try:
        with zlm.locks("w", parents):
            for h in holds:
                full = f"{h['dataset']}@{h['snapshot']}"
                if repo.release(h["tag"], full):
                    log_msg(f"INFO: Released '{h['tag']}' on {full}")
                else:
                    log_msg(f"WARN: Error releasing '{h['tag']}' on {full}")
    except RuntimeError as exc:
        log_msg(f"WARN: cannot release holds: {exc}")
    refresh_datasets_page(app)


def on_datasets_hold(app):
    """Place a hold on selected snapshots."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    snaps = [i for i in items if i["type"] == "snapshot"]
    if not snaps:
        log_msg("WARN: Select one or more snapshots to hold")
        return

    response, tag = _input_dialog(app, "Add Hold", [Gtk.Label(label="Hold tag name:")], "keep")
    if response != Gtk.ResponseType.OK or not tag:
        return

    parents = _unique_parent_datasets(snaps)
    try:
        with zlm.locks("w", parents):
            for s in snaps:
                full = f"{s['dataset']}@{s['name']}"
                if repo.hold(tag, full):
                    log_msg(f"INFO: Hold '{tag}' set on {full}")
                else:
                    log_msg(f"WARN: Error setting hold '{tag}' on {full}")
    except RuntimeError as exc:
        log_msg(f"WARN: cannot set holds: {exc}")
    refresh_datasets_page(app)


def on_datasets_rollback(app):
    """Rollback a dataset to the selected snapshot."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    snaps = [i for i in items if i["type"] == "snapshot"]
    if len(snaps) != 1:
        log_msg("WARN: Select exactly one snapshot to rollback to")
        return

    s = snaps[0]
    full = f"{s['dataset']}@{s['name']}"
    detail = (f"This will revert {s['dataset']} to snapshot {s['name']}.\n\n"
              "All data written after this snapshot will be LOST.\n"
              "Newer snapshots will be destroyed.")
    if not _confirm_yes_no(app, f"Rollback to {s['name']}?", detail):
        return

    dataset = s["dataset"]
    try:
        with zlm.lock(dataset, "w", f"rollback {full}"):
            if repo.rollback(full):
                log_msg(f"INFO: Rolled back to {full}")
            else:
                log_msg(f"WARN: Error rolling back to {full}")
    except RuntimeError as exc:
        log_msg(f"WARN: cannot rollback {dataset}: {exc}")
    refresh_datasets_page(app)


def on_datasets_show_files(app):
    """Open the default file manager at the selected dataset's mountpoint."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    ds_items = [i for i in items if i.get("zfs_type") == "filesystem"]
    if len(ds_items) != 1:
        log_msg("WARN: Select exactly one dataset to open")
        return

    dataset = ds_items[0]["name"]
    try:
        mountpoint = repo.get_property(dataset, "mountpoint")
        if not mountpoint.startswith("/"):
            log_msg(f"WARN: Cannot open {dataset}: mountpoint is {mountpoint}")
            return
        subprocess.Popen(["xdg-open", mountpoint])
        log_msg(f"INFO: Opened {mountpoint}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error opening file manager: {e}")


def on_datasets_browse_snapshot(app):
    """Open a snapshot in the default file manager via .zfs/snapshot/."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    snaps = [i for i in items if i["type"] == "snapshot"]
    if len(snaps) != 1:
        log_msg("WARN: Select exactly one snapshot to browse")
        return

    s = snaps[0]
    full_snap = f"{s['dataset']}@{s['name']}"
    try:
        path = get_snapshot_mountpoint(s["dataset"], s["name"], repo=repo)
        subprocess.Popen(["xdg-open", path])
        log_msg(f"INFO: Browsing snapshot {full_snap}")
        update_ds_button_sensitivity(app)
        GLib.timeout_add_seconds(1, lambda a: update_ds_button_sensitivity(a) or False, app)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error browsing snapshot {full_snap}: {e}")


def on_datasets_unmount_snapshot(app):
    """Unmount a mounted ZFS snapshot, warning if busy."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    snaps = [i for i in items if i["type"] == "snapshot"]
    if len(snaps) != 1:
        log_msg("WARN: Select exactly one snapshot to unmount")
        return

    s = snaps[0]
    full_snap = f"{s['dataset']}@{s['name']}"
    try:
        path = get_snapshot_mountpoint(s["dataset"], s["name"], repo=repo)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error resolving mountpoint for {full_snap}: {e}")
        return

    procs = get_busy_processes(path)
    if procs:
        proc_list = "\n".join(f"  • {name} (PID {pid})" for pid, name in procs)
        detail = (
            f"{full_snap} is currently in use by:\n\n{proc_list}\n\n"
            "Please close the listed application(s), then try unmounting again."
        )
        dialog = Gtk.MessageDialog(transient_for=app, modal=True,
                                   message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.OK, text="Snapshot is busy")
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()
        return

    result = subprocess.run(["sudo", "umount", path], capture_output=True, text=True)
    if result.returncode == 0:
        log_msg(f"INFO: Unmounted snapshot {full_snap}")
        update_ds_button_sensitivity(app)
        return

    stderr = result.stderr.strip()
    if "busy" in stderr.lower():
        log_msg(
            f"WARN: Snapshot {full_snap} is busy. "
            "Please close any file manager windows and try again."
        )
        return
    log_msg(f"WARN: Error unmounting {full_snap}: {stderr}")
