"""
Dataset action handlers — snapshot, delete, hold, rollback, browse, etc.

Called exclusively through the action dispatch table in action_dispatch.py.
"""

import os
import shlex
import subprocess
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
import zfs_lock_manager as zlm
from backup_config import log_msg
from command_builders import BashStep
from datasets_page import (
    refresh_datasets_page,
    update_ds_button_sensitivity,
    update_mounted_states,
)
from gi.repository import GLib, Gtk
from gui_helpers import (
    add_scrolled_text_view,
    create_dialog,
    diagnose_dataset_busy,
    get_busy_processes,
    get_mounted_snapshots,
    get_snapshot_mountpoint,
    get_tree_selection_items,
)

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
    dialog = create_dialog(
        title,
        parent,
        [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            (Gtk.STOCK_OK, Gtk.ResponseType.OK),
        ],
        default_response=Gtk.ResponseType.OK,
    )
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
        transient_for=parent,
        modal=True,
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
        app,
        "Create Snapshot",
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
        _delete_snapshots(app, snaps, selected_holds=holds)
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
                ds_info["holds"].extend(f"{hold.tag} on {snap}" for hold in repo.list_holds(snap))
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

    dialog = create_dialog(
        "Destroy Dataset(s)",
        app,
        [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            ("Destroy", Gtk.ResponseType.OK),
        ],
    )
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

    runner = getattr(app, "dataset_runner", None)
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
        steps.append(
            BashStep(
                ["bash", "-c", bash_cmd],
                f"Destroy {ds_name}",
                is_rsync=False,
                fatal=False,
            )
        )

    def _on_delete_complete(cancelled=False):
        refresh_datasets_page(app)

    runner.set_steps(steps)
    runner.start(on_complete=_on_delete_complete)


def _delete_snapshots(app, snaps, selected_holds=None):
    """Delete selected snapshots, releasing any selected holds first.

    If *selected_holds* is provided and a selected snapshot still has holds
    that were not selected, the operation is aborted with a clear warning.
    Hold-only selections should be handled by :func:`_release_holds`.
    """
    repo = _repo(app)
    selected_holds = selected_holds or []

    selected_hold_keys = {(f"{h['dataset']}@{h['snapshot']}", h["tag"]) for h in selected_holds}

    blocked = []
    for s in snaps:
        full = f"{s['dataset']}@{s['name']}"
        try:
            existing_holds = repo.list_holds(full)
        except subprocess.CalledProcessError:
            existing_holds = []
        unselected = [h for h in existing_holds if (h.snapshot, h.tag) not in selected_hold_keys]
        if unselected:
            tags = ", ".join(h.tag for h in unselected)
            blocked.append(f"{full}: {tags}")

    if blocked:
        log_msg(
            "WARN: Cannot delete: the following snapshots have holds that were not selected:\n  "
            + "\n  ".join(blocked)
        )
        return

    snap_names = [f"{s['dataset']}@{s['name']}" for s in snaps]
    lines = ["Snapshots to delete:"]
    lines.extend(f"  {name}" for name in snap_names)
    if selected_holds:
        lines.append("")
        lines.append("Holds to release:")
        lines.extend(f"  {h['tag']} on {h['dataset']}@{h['snapshot']}" for h in selected_holds)
    display = "\n".join(lines)
    if not _confirm_yes_no(
        app,
        f"Delete {len(snap_names)} snapshot(s)"
        + (f" and release {len(selected_holds)} hold(s)?" if selected_holds else "?"),
        f"{display}\n\nThis cannot be undone.",
    ):
        return

    parents = _unique_parent_datasets(snaps + selected_holds)
    try:
        with zlm.locks("w", parents):
            for h in selected_holds:
                full = f"{h['dataset']}@{h['snapshot']}"
                if repo.release(h["tag"], full):
                    log_msg(f"INFO: Released '{h['tag']}' on {full}")
                else:
                    log_msg(f"WARN: Error releasing '{h['tag']}' on {full}")

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
    names = "\n  ".join(f"{h['tag']} on {h['dataset']}@{h['snapshot']}" for h in holds)
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
    detail = (
        f"This will revert {s['dataset']} to snapshot {s['name']}.\n\n"
        "All data written after this snapshot will be LOST.\n"
        "Newer snapshots will be destroyed."
    )
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


def on_datasets_show_big_stuff(app):
    """Run zfsshowbigstuff on the selected pool and log the output."""
    items = get_tree_selection_items(app.datasets_view)
    pool_items = [i for i in items if i["type"] == "pool"]
    if len(pool_items) != 1:
        log_msg("WARN: Select exactly one pool to show big stuff")
        return

    pool = pool_items[0]["name"]

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    parent_dir = app.parent_dir
    pool_quoted = shlex.quote(pool)
    bash_cmd = (
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; "$mydir/zfsshowbigstuff" {pool_quoted}'
    )
    step = BashStep(
        ["bash", "-c", bash_cmd],
        f"Show big stuff for {pool}",
        is_rsync=False,
        fatal=False,
    )
    runner.set_steps([step])
    runner.start()


def on_datasets_browse(app):
    """Open the selected filesystem or snapshot in the default file manager."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    if len(items) != 1:
        log_msg("WARN: Select exactly one item to browse")
        return

    item = items[0]
    item_type = item["type"]
    if item_type in ("pool", "dataset") and item.get("zfs_type") == "filesystem":
        dataset = item["name"]
        try:
            mountpoint = repo.get_property(dataset, "mountpoint")
            if not mountpoint.startswith("/"):
                log_msg(f"WARN: Cannot open {dataset}: mountpoint is {mountpoint}")
                return
            subprocess.Popen(["xdg-open", mountpoint])
            log_msg(f"VERB: Opened {mountpoint}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log_msg(f"WARN: Error opening file manager: {e}")
        return

    if item_type == "snapshot":
        full_snap = f"{item['dataset']}@{item['name']}"
        try:
            path = get_snapshot_mountpoint(item["dataset"], item["name"], repo=repo)
            subprocess.Popen(["xdg-open", path])
            log_msg(f"VERB: Browsing snapshot {full_snap}")
            update_ds_button_sensitivity(app)
            GLib.timeout_add_seconds(1, lambda a: update_ds_button_sensitivity(a) or False, app)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log_msg(f"WARN: Error browsing snapshot {full_snap}: {e}")
        return

    log_msg("WARN: Select a filesystem or snapshot to browse")


def _mount_one_dataset(item, repo, app):
    """Mount a single filesystem/pool dataset; return True if processed.

    Any unmounted ancestor datasets are mounted first so the target's
    mountpoint is not hidden by a later parent mount.
    """
    dataset = item["name"]

    # Build ancestor list from root to target, e.g. tank -> tank/vm-100.
    parts = dataset.split("/")
    candidates = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]

    targets_to_mount = []
    try:
        for candidate in candidates:
            if repo.get_property(candidate, "mounted") != "yes":
                targets_to_mount.append(candidate)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error checking mount state for {dataset}: {e}")
        return False

    if not targets_to_mount:
        return False

    try:
        with zlm.locks("w", targets_to_mount):
            for target in targets_to_mount:
                result = subprocess.run(
                    ["sudo", "zfs", "mount", target],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    log_msg(f"WARN: Error mounting {target}: {result.stderr.strip()}")
                    return False
                log_msg(f"INFO: Mounted {target}")
            return True
    except RuntimeError as exc:
        log_msg(f"WARN: cannot mount {dataset}: {exc}")
        return False


def _mount_one_snapshot(item, repo, app):
    """Mount a single snapshot by accessing its .zfs path; return True if processed."""
    full_snap = f"{item['dataset']}@{item['name']}"
    try:
        path = get_snapshot_mountpoint(item["dataset"], item["name"], repo=repo)
        parent_mountpoint = path.rsplit("/.zfs/snapshot/", 1)[0]
        with zlm.lock(item["dataset"], "r", f"mount snapshot {full_snap}"):
            parent_mounted = repo.get_property(item["dataset"], "mounted") == "yes"
            if not parent_mounted:
                log_msg(
                    f"WARN: Cannot mount {full_snap}: parent dataset "
                    f"{item['dataset']} is not mounted. Mount the parent first."
                )
                return False

            if not os.path.isdir(parent_mountpoint):
                log_msg(
                    f"WARN: Cannot mount {full_snap}: parent mountpoint "
                    f"{parent_mountpoint} is missing. A child dataset was "
                    "mounted before its parent; remount the parent dataset "
                    "to restore access."
                )
                return False

            # The .zfs/snapshot stub may exist even when the snapshot is not
            # mounted, so always list it to trigger automount and then verify
            # the mount actually appeared.
            try:
                os.listdir(path)
            except FileNotFoundError:
                log_msg(f"WARN: Cannot mount {full_snap}: snapshot path {path} is not accessible.")
                return False

            if full_snap in get_mounted_snapshots(repo=repo):
                log_msg(f"INFO: Mounted snapshot {full_snap}")
                return True

            log_msg(
                f"WARN: Cannot mount {full_snap}: snapshot did not automount. "
                f"Verify the parent dataset is healthy and try again."
            )
            return False
    except RuntimeError as exc:
        log_msg(f"WARN: cannot mount {full_snap}: {exc}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error mounting snapshot {full_snap}: {e}")
    return False


def on_datasets_mount(app):
    """Mount all selected filesystems and snapshots."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    if not items:
        log_msg("WARN: Select an item to mount")
        return

    targets = [i for i in items if i["type"] in ("pool", "dataset", "snapshot")]
    if not targets:
        log_msg("WARN: Select filesystems or snapshots to mount")
        return

    processed = False
    for item in targets:
        if item.get("mounted", False):
            continue
        if item["type"] in ("pool", "dataset") and item.get("zfs_type") == "filesystem":
            processed = _mount_one_dataset(item, repo, app) or processed
        elif item["type"] == "snapshot":
            processed = _mount_one_snapshot(item, repo, app) or processed

    if processed:
        update_mounted_states(app)
        GLib.timeout_add_seconds(1, lambda a: update_mounted_states(a) or False, app)


def _unmount_one_dataset(item, repo, app):
    """Unmount a single filesystem/pool dataset; return True on success.

    Descendant datasets are unmounted first (deepest first), because ZFS
    refuses to unmount a parent while any of its children are still mounted.
    """
    dataset = item["name"]
    try:
        mountpoint = repo.get_property(dataset, "mountpoint")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error resolving mountpoint for {dataset}: {e}")
        return False

    procs = get_busy_processes(mountpoint)
    if procs:
        proc_list = "\n".join(f"  • {name} (PID {pid})" for pid, name in procs)
        detail = (
            f"{dataset} is currently in use by:\n\n{proc_list}\n\n"
            "Please close the listed application(s), then try unmounting again."
        )
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text="Dataset is busy",
        )
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()
        return False

    # Build the list of mounted descendants, deepest first, so children are
    # unmounted before their parents.
    unmount_targets = [dataset]
    try:
        descendants = [
            row.name
            for row in repo.list_datasets(pool=dataset)
            if row.name != dataset and row.ds_type != "snapshot" and row.mounted == "yes"
        ]
        descendants.sort(key=lambda name: name.count("/"), reverse=True)
        unmount_targets = descendants + [dataset]
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Could not list descendants of {dataset}: {e}")

    any_unmounted = False
    try:
        with zlm.locks("w", unmount_targets):
            for target in unmount_targets:
                result = subprocess.run(
                    ["sudo", "zfs", "unmount", target],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    any_unmounted = True
                    if target == dataset:
                        log_msg(f"INFO: Unmounted {dataset}")
                    else:
                        log_msg(f"INFO: Unmounted {target}")
                    continue

                stderr = result.stderr.strip()
                if "busy" in stderr.lower():
                    log_msg(
                        f"WARN: Dataset {target} is busy. "
                        "Please close any file manager windows and try again."
                    )
                else:
                    log_msg(f"WARN: Error unmounting {target}: {stderr}")
                # Stop at the first failure; trying to unmount a parent after
                # a child failed would just produce the same error again.
                break
    except RuntimeError as exc:
        log_msg(f"WARN: cannot unmount {dataset}: {exc}")
        return False

    return any_unmounted


def _unmount_one_snapshot(item, repo, app):
    """Unmount a single snapshot; return True on success."""
    full_snap = f"{item['dataset']}@{item['name']}"
    try:
        path = get_snapshot_mountpoint(item["dataset"], item["name"], repo=repo)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error resolving mountpoint for {full_snap}: {e}")
        return False

    procs = get_busy_processes(path)
    if procs:
        proc_list = "\n".join(f"  • {name} (PID {pid})" for pid, name in procs)
        detail = (
            f"{full_snap} is currently in use by:\n\n{proc_list}\n\n"
            "Please close the listed application(s), then try unmounting again."
        )
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text="Snapshot is busy",
        )
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()
        return False

    try:
        with zlm.lock(item["dataset"], "w", f"umount snapshot {full_snap}"):
            result = subprocess.run(
                ["sudo", "umount", path], capture_output=True, text=True, check=False
            )
    except RuntimeError as exc:
        log_msg(f"WARN: cannot unmount {full_snap}: {exc}")
        return False

    if result.returncode == 0:
        log_msg(f"INFO: Unmounted snapshot {full_snap}")
        return True

    stderr = result.stderr.strip()
    if "busy" in stderr.lower():
        log_msg(
            f"WARN: Snapshot {full_snap} is busy. "
            "Please close any file manager windows and try again."
        )
    else:
        log_msg(f"WARN: Error unmounting {full_snap}: {stderr}")
    return False


def on_datasets_unmount(app):
    """Unmount all selected filesystems and snapshots, warning if any are busy."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    if not items:
        log_msg("WARN: Select an item to unmount")
        return

    targets = [i for i in items if i["type"] in ("pool", "dataset", "snapshot")]
    if not targets:
        log_msg("WARN: Select filesystems or snapshots to unmount")
        return

    changed = False
    for item in targets:
        if not item.get("mounted", False):
            continue
        if item["type"] in ("pool", "dataset") and item.get("zfs_type") == "filesystem":
            changed = _unmount_one_dataset(item, repo, app) or changed
        elif item["type"] == "snapshot":
            changed = _unmount_one_snapshot(item, repo, app) or changed

    if changed:
        update_mounted_states(app)
