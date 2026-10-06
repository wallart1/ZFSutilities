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
import paths
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
    find_tree_iter_by_full_name,
    get_busy_processes,
    get_mounted_snapshots,
    get_snapshot_mountpoint,
    get_tree_selection_items,
    reload_row_children,
)
from zfs_repository import zvol_device_path

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


def _snapshot_target_datasets(items):
    """Return the pool/dataset rows in *items* that can be snapshotted.

    Filesystems and volumes (including pool roots, which are filesystems)
    qualify; snapshots, holds, and volume partitions are skipped. This
    mirrors the Snapshot button's sensitivity predicate.
    """
    return [
        i
        for i in items
        if i["type"] in ("pool", "dataset")
        and (i.get("zfs_type") or "filesystem") in ("filesystem", "volume")
    ]


def _snapshot_one(app, dataset, snap_name):
    """Create a single snapshot under a dataset lock."""
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


def _snapshot_many(app, datasets, snap_name):
    """Create *snap_name* on every dataset in *datasets* under one lock set.

    Each dataset is snapshotted independently: a failure on one (e.g. the
    name already exists there) is logged and the remaining datasets are
    still attempted. The page refreshes once if anything was created.
    """
    log_msg(f"INFO: Creating snapshot '{snap_name}' on {len(datasets)} datasets")
    created = 0
    try:
        with zlm.locks("w", datasets):
            repo = _repo(app)
            for dataset in datasets:
                full_snap = f"{dataset}@{snap_name}"
                if repo.snapshot(full_snap):
                    created += 1
                    log_msg(f"INFO: Snapshot created: {full_snap}")
                else:
                    log_msg(f"WARN: Error creating snapshot: {full_snap}")
    except RuntimeError as exc:
        log_msg(f"WARN: cannot snapshot {', '.join(datasets)}: {exc}")
    except FileNotFoundError:
        log_msg("WARN: Error: zfs command not found")
    if created < len(datasets):
        log_msg(f"WARN: Created snapshot on {created} of {len(datasets)} datasets")
    if created:
        refresh_datasets_page(app)


def on_datasets_snapshot(app):
    """Create a snapshot on each selected filesystem/volume dataset."""
    items = get_tree_selection_items(app.datasets_view)
    ds_items = _snapshot_target_datasets(items)
    if not ds_items:
        log_msg("WARN: Select one or more datasets to snapshot")
        return
    datasets = [i["name"] for i in ds_items]

    now = datetime.now()
    suggested = now.strftime("manual-%Y-%m-%dT%H:%M")
    widgets = []
    if len(datasets) == 1:
        ds_label = Gtk.Label()
        ds_label.set_markup(f"<b>Dataset:</b> {datasets[0]}")
        ds_label.set_halign(Gtk.Align.START)
        ds_label.set_selectable(True)
        widgets.append(ds_label)
    else:
        count_label = Gtk.Label()
        count_label.set_markup(f"<b>Datasets ({len(datasets)}):</b>")
        count_label.set_halign(Gtk.Align.START)
        widgets.append(count_label)
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        add_scrolled_text_view(list_box, "\n".join(datasets), min_height=150)
        widgets.append(list_box)
    response, snap_name = _input_dialog(
        app,
        "Create Snapshots" if len(datasets) > 1 else "Create Snapshot",
        widgets + [Gtk.Label(label="Snapshot name (without @):")],
        suggested,
    )
    if response != Gtk.ResponseType.OK or not snap_name:
        return
    if " " in snap_name or "/" in snap_name:
        log_msg("WARN: Snapshot name cannot contain spaces or slashes")
        return

    if len(datasets) == 1:
        _snapshot_one(app, datasets[0], snap_name)
    else:
        _snapshot_many(app, datasets, snap_name)


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

    def _on_delete_complete(cancelled=False, rc=None):
        refresh_datasets_page(app)

    runner.operation_detail = (
        f"Destroy Dataset: {details[0]['name']}"
        if len(details) == 1
        else f"Destroy Datasets: {len(details)} selected"
    )
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
    runner.operation_detail = f"Show Big Stuff: {pool}"
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

    if item_type == "volume-partition":
        device = item["device"]
        try:
            mountpoint = repo.device_mountpoint(device)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log_msg(f"WARN: Error resolving mountpoint for {device}: {e}")
            return
        if not mountpoint:
            log_msg(f"WARN: {device} is not mounted; mount the partition first")
            return
        try:
            subprocess.Popen(["xdg-open", mountpoint])
            log_msg(f"VERB: Opened {mountpoint}")
        except FileNotFoundError as e:
            log_msg(f"WARN: Error opening file manager: {e}")
        return

    log_msg("WARN: Select a filesystem, snapshot, or mounted volume partition to browse")


def _unmounted_mountable_ancestors(dataset, repo):
    """Return *dataset*'s unmounted ancestors, root-first, that can be mounted.

    Ancestors with canmount=off are skipped: they can never be mounted, and
    ZFS auto-creates their mountpoint directory when a descendant mounts, so
    the target's path is not lost.
    """
    parts = dataset.split("/")
    ancestors = []
    for i in range(1, len(parts)):
        candidate = "/".join(parts[:i])
        if repo.get_property(candidate, "mounted") == "yes":
            continue
        if repo.get_property(candidate, "canmount") == "off":
            log_msg(f"INFO: Skipping {candidate} (canmount=off)")
            continue
        ancestors.append(candidate)
    return ancestors


def _mount_dataset_targets(targets, dataset=None):
    """Mount *targets* root-first under write locks; return True if all mounted.

    The write locks are held only for the duration of the mount commands and
    are released on any exit path. *dataset* only labels the lock-conflict
    warning; it defaults to the deepest target.
    """
    try:
        with zlm.locks("w", targets):
            for target in targets:
                result = subprocess.run(
                    ["sudo", "zfs", "mount", target],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    log_msg(f"WARN: Error mounting {target}: {result.stderr.strip()}")
                    return False
                log_msg(f"VERB: Mounted {target}")
            return True
    except RuntimeError as exc:
        log_msg(f"WARN: cannot mount {dataset or targets[-1]}: {exc}")
        return False


def _mount_one_dataset(item, repo, app):
    """Mount a single filesystem/pool dataset; return True if processed.

    Any unmounted ancestor datasets are mounted first so the target's
    mountpoint is not hidden by a later parent mount. Ancestors with
    canmount=off are skipped; they cannot be mounted and ZFS auto-creates
    their mountpoint directory when the target mounts.
    """
    dataset = item["name"]

    try:
        targets_to_mount = _unmounted_mountable_ancestors(dataset, repo)
        if repo.get_property(dataset, "mounted") != "yes":
            targets_to_mount.append(dataset)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error checking mount state for {dataset}: {e}")
        return False

    if not targets_to_mount:
        return False

    return _mount_dataset_targets(targets_to_mount, dataset)


def _mount_one_snapshot(item, repo, app):
    """Mount a single snapshot by accessing its .zfs path; return True if processed."""
    full_snap = f"{item['dataset']}@{item['name']}"
    if item.get("parent_type") == "volume":
        log_msg(f"WARN: Cannot mount {full_snap}: snapshots of ZFS volumes cannot be mounted")
        return False
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

            if full_snap in get_mounted_snapshots():
                log_msg(f"VERB: Mounted snapshot {full_snap}")
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


def _snapshot_parent_mount_plan(snap_items, repo):
    """Return (mount_list, offered) for snapshots whose parent is unmounted.

    mount_list is the deduplicated, root-first list of datasets to mount:
    each offered snapshot's unmounted ancestors plus its parent. Snapshots
    whose parent is already mounted, or whose parent has canmount=off and
    can therefore never be mounted, are not offered.
    """
    mount_list = []
    offered = []
    for item in snap_items:
        dataset = item["dataset"]
        try:
            if repo.get_property(dataset, "mounted") == "yes":
                continue
            if repo.get_property(dataset, "canmount") == "off":
                continue
            ancestors = _unmounted_mountable_ancestors(dataset, repo)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log_msg(f"WARN: Error checking mount state for {dataset}: {e}")
            continue
        offered.append(item)
        for candidate in ancestors + [dataset]:
            if candidate not in mount_list:
                mount_list.append(candidate)
    return mount_list, offered


def _offer_snapshot_parent_mounts(snap_items, repo, app):
    """Offer to mount the unmounted parents of selected snapshots.

    Shows a dialog listing the unmounted parent datasets and the snapshots
    they block. Confirming mounts the parents root-first; the per-snapshot
    automount then runs in the normal dispatch loop. Cancelling skips the
    parent mounts, leaving the snapshots to report the parent-not-mounted
    warning.
    """
    mount_list, offered = _snapshot_parent_mount_plan(snap_items, repo)
    if not offered:
        return

    lines = ["Parent datasets to mount:", ""]
    lines.extend(f"  {name}" for name in mount_list)
    lines.extend(["", "Snapshot(s) to mount after:", ""])
    lines.extend(f"  {item['dataset']}@{item['name']}" for item in offered)

    dialog = create_dialog(
        "Mount Snapshot(s)",
        app,
        [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            ("Mount All", Gtk.ResponseType.OK),
        ],
    )
    content = dialog.get_content_area()
    header = Gtk.Label()
    header.set_markup(
        f"<b>Mount {len(offered)} snapshot(s): {len(mount_list)} unmounted "
        "parent dataset(s) will be mounted first.</b>"
    )
    header.set_halign(Gtk.Align.START)
    content.add(header)
    add_scrolled_text_view(content, "\n".join(lines), min_height=150)

    dialog.show_all()
    response = dialog.run()
    dialog.destroy()
    if response != Gtk.ResponseType.OK:
        return

    if not _mount_dataset_targets(mount_list):
        log_msg(
            "WARN: Not all parent datasets mounted; selected snapshots "
            "that remain blocked will report warnings below."
        )


def _volume_partition_mountpoint(item):
    """Return the mountpoint path for a loop partition of a zvol."""
    parts = item["volume"].split("/") + [item["name"]]
    return os.path.join(paths.get_zvol_mount_dir(), *parts)


def _mount_one_volume(item, repo, app):
    """Attach a zvol to a read-only loop device; return True if processed.

    The volume row's children are reloaded afterwards so its partitions
    appear in the tree.
    """
    dataset = item["name"]
    try:
        with zlm.lock(dataset, "w", f"loop-mount {dataset}"):
            loop_dev = repo.loop_find(zvol_device_path(dataset))
            if not loop_dev:
                loop_dev = repo.loop_attach(zvol_device_path(dataset))
                if not loop_dev:
                    log_msg(f"WARN: Error attaching {dataset} to a loop device")
                    return False
                log_msg(f"INFO: Attached {dataset} to read-only loop device {loop_dev}")
            tree_iter = find_tree_iter_by_full_name(app.datasets_store, dataset)
            if tree_iter is not None:
                reload_row_children(app.datasets_store, tree_iter, repo=repo)
            return True
    except RuntimeError as exc:
        log_msg(f"WARN: cannot attach loop device for {dataset}: {exc}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error attaching loop device for {dataset}: {e}")
    return False


def _mount_one_volume_partition(item, repo, app):
    """Mount a loop partition at its derived mountpoint; return True if mounted.

    The loop device is read-only, so the partition mounts read-only.
    """
    device = item["device"]
    if not item.get("has_filesystem", False):
        log_msg(f"WARN: Cannot mount {device}: no filesystem detected")
        return False
    mountpoint = _volume_partition_mountpoint(item)
    try:
        os.makedirs(mountpoint, exist_ok=True)
    except OSError as e:
        log_msg(f"WARN: Error creating mountpoint {mountpoint}: {e}")
        return False
    result = subprocess.run(
        ["sudo", "mount", "-o", "ro", device, mountpoint],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        log_msg(f"WARN: Error mounting {device}: {result.stderr.strip()}")
        return False
    log_msg(f"INFO: Mounted {device} at {mountpoint} (read-only)")
    return True


def on_datasets_mount(app):
    """Mount all selected filesystems, snapshots, and volume loop devices."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    if not items:
        log_msg("WARN: Select an item to mount")
        return

    targets = [i for i in items if i["type"] in ("pool", "dataset", "snapshot", "volume-partition")]
    if not targets:
        log_msg("WARN: Select filesystems, snapshots, or volumes to mount")
        return

    pending_snaps = [
        i
        for i in targets
        if i["type"] == "snapshot"
        and not i.get("mounted", False)
        and i.get("parent_type") != "volume"
    ]
    if pending_snaps:
        _offer_snapshot_parent_mounts(pending_snaps, repo, app)

    processed = False
    for item in targets:
        if item.get("mounted", False):
            continue
        if item["type"] in ("pool", "dataset") and item.get("zfs_type") == "filesystem":
            processed = _mount_one_dataset(item, repo, app) or processed
        elif item["type"] in ("pool", "dataset") and item.get("zfs_type") == "volume":
            processed = _mount_one_volume(item, repo, app) or processed
        elif item["type"] == "volume-partition":
            processed = _mount_one_volume_partition(item, repo, app) or processed
        elif item["type"] == "snapshot":
            processed = _mount_one_snapshot(item, repo, app) or processed

    if processed:
        update_mounted_states(app)
        GLib.timeout_add_seconds(1, lambda a: update_mounted_states(a) or False, app)


def _recover_orphaned_mount(target, repo):
    """Best-effort recovery for an orphaned mount of *target*; True if unmounted.

    An orphaned mount is a dataset the kernel still lists as mounted whose
    mountpoint path is no longer reachable (its parent mount is missing), so
    umount(2) fails with ENOENT — which libzfs renders as the misleading
    "no such pool or dataset". Recovery remounts the unmounted ancestors,
    root-first, and retries the unmount. If the retry still fails, every
    ancestor mounted here is unmounted again (best effort) to restore the
    original state.
    """
    try:
        ancestors = _unmounted_mountable_ancestors(target, repo)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error checking mount state for {target}: {e}")
        return False

    if not ancestors:
        # Nothing to remount; an identical retry cannot succeed.
        return False

    try:
        with zlm.locks("w", ancestors + [target]):
            for ancestor in ancestors:
                result = subprocess.run(
                    ["sudo", "zfs", "mount", ancestor],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    log_msg(
                        f"WARN: Error remounting {ancestor} while recovering {target}: "
                        f"{result.stderr.strip()}"
                    )
                    return False
                log_msg(f"INFO: Remounted {ancestor} to recover orphaned mount")

            result = subprocess.run(
                ["sudo", "zfs", "unmount", target],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return True

            for ancestor in reversed(ancestors):
                restore = subprocess.run(
                    ["sudo", "zfs", "unmount", ancestor],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if restore.returncode != 0:
                    log_msg(
                        f"WARN: Could not restore unmounted state of {ancestor}: "
                        f"{restore.stderr.strip()}"
                    )
            log_msg(
                f"WARN: Could not unmount {target} after remounting its parents: "
                f"{result.stderr.strip()}"
            )
            return False
    except RuntimeError as exc:
        log_msg(f"WARN: cannot recover orphaned mount of {target}: {exc}")
        return False


def _unmount_one_dataset(item, repo, app):
    """Unmount a single filesystem/pool dataset; return True on success.

    Descendant datasets are unmounted first (deepest first), because ZFS
    refuses to unmount a parent while any of its children are still mounted.
    """
    dataset = item["name"]
    try:
        mountpoint = repo.get_property(dataset, "mountpoint")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"FATAL: Error resolving mountpoint for {dataset}: {e}")
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
        log_msg(f"FATAL: Dataset {dataset} is busy; unmount aborted")
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
                        log_msg(f"VERB: Unmounted {dataset}")
                    else:
                        log_msg(f"VERB: Unmounted {target}")
                    continue

                stderr = result.stderr.strip()
                if "no such pool or dataset" in stderr:
                    # Orphaned mount: the kernel still lists the dataset as
                    # mounted, but its mountpoint path is unreachable.
                    if _recover_orphaned_mount(target, repo):
                        any_unmounted = True
                        log_msg(f"VERB: Unmounted {target}")
                        continue
                    log_msg(
                        f"FATAL: {target} looks mounted but its mountpoint is "
                        "not reachable (orphaned mount) and could not be "
                        "recovered by remounting its parents. Remount the "
                        "parent dataset(s) manually and retry; if that fails "
                        "the mount is detached from the namespace and a "
                        "reboot is required."
                    )
                elif "busy" in stderr.lower():
                    log_msg(
                        f"FATAL: Dataset {target} is busy. "
                        "Please close any file manager windows and try again."
                    )
                else:
                    log_msg(f"FATAL: Error unmounting {target}: {stderr}")
                # Stop at the first failure; trying to unmount a parent after
                # a child failed would just produce the same error again.
                break
    except RuntimeError as exc:
        log_msg(f"FATAL: cannot unmount {dataset}: {exc}")
        return False

    return any_unmounted


def _unmount_one_snapshot(item, repo, app):
    """Unmount a single snapshot; return True on success."""
    full_snap = f"{item['dataset']}@{item['name']}"
    try:
        path = get_snapshot_mountpoint(item["dataset"], item["name"], repo=repo)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"FATAL: Error resolving mountpoint for {full_snap}: {e}")
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
        log_msg(f"FATAL: Snapshot {full_snap} is busy; unmount aborted")
        return False

    try:
        with zlm.lock(item["dataset"], "w", f"umount snapshot {full_snap}"):
            result = subprocess.run(
                ["sudo", "umount", path], capture_output=True, text=True, check=False
            )
    except RuntimeError as exc:
        log_msg(f"FATAL: cannot unmount {full_snap}: {exc}")
        return False

    if result.returncode == 0:
        log_msg(f"VERB: Unmounted snapshot {full_snap}")
        return True

    stderr = result.stderr.strip()
    if "busy" in stderr.lower():
        log_msg(
            f"FATAL: Snapshot {full_snap} is busy. "
            "Please close any file manager windows and try again."
        )
    else:
        log_msg(f"FATAL: Error unmounting {full_snap}: {stderr}")
    return False


def _warn_busy(app, title, detail):
    """Show a warning dialog listing busy processes blocking an unmount."""
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(detail)
    dialog.run()
    dialog.destroy()


def _unmount_one_volume_partition(item, repo, app):
    """Unmount a mounted loop partition; return True on success."""
    device = item["device"]
    try:
        mountpoint = repo.device_mountpoint(device)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"FATAL: Error resolving mountpoint for {device}: {e}")
        return False
    if not mountpoint:
        return False

    procs = get_busy_processes(mountpoint)
    if procs:
        proc_list = "\n".join(f"  • {name} (PID {pid})" for pid, name in procs)
        _warn_busy(
            app,
            "Partition is busy",
            f"{device} is currently in use by:\n\n{proc_list}\n\n"
            "Please close the listed application(s), then try unmounting again.",
        )
        log_msg(f"FATAL: Partition {device} is busy; unmount aborted")
        return False

    result = subprocess.run(
        ["sudo", "umount", mountpoint], capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        log_msg(f"INFO: Unmounted {device} from {mountpoint}")
        return True

    stderr = result.stderr.strip()
    if "busy" in stderr.lower():
        log_msg(
            f"FATAL: Partition {device} is busy. "
            "Please close any file manager windows and try again."
        )
    else:
        log_msg(f"FATAL: Error unmounting {device}: {stderr}")
    return False


def _unmount_one_volume(item, repo, app):
    """Detach a volume's loop device, unmounting its partitions first."""
    dataset = item["name"]
    try:
        loop_dev = repo.loop_find(zvol_device_path(dataset))
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"FATAL: Error finding loop device for {dataset}: {e}")
        return False
    if not loop_dev:
        return False

    try:
        parts = repo.loop_partitions(loop_dev)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"FATAL: Error listing partitions on {loop_dev}: {e}")
        return False

    mounted_parts = [p for p in parts if p.mountpoint]
    for part in mounted_parts:
        procs = get_busy_processes(part.mountpoint)
        if procs:
            proc_list = "\n".join(f"  • {name} (PID {pid})" for pid, name in procs)
            _warn_busy(
                app,
                "Partition is busy",
                f"{part.device} is currently in use by:\n\n{proc_list}\n\n"
                "Please close the listed application(s), then try unmounting again.",
            )
            log_msg(f"FATAL: Partition {part.device} is busy; unmount aborted")
            return False

    for part in mounted_parts:
        result = subprocess.run(
            ["sudo", "umount", part.mountpoint], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            log_msg(f"FATAL: Error unmounting {part.device}: {result.stderr.strip()}")
            return False
        log_msg(f"INFO: Unmounted {part.device} from {part.mountpoint}")

    if not repo.loop_detach(loop_dev):
        log_msg(f"FATAL: Error detaching {loop_dev} from {dataset}")
        return False
    log_msg(f"INFO: Detached {dataset} from loop device {loop_dev}")
    tree_iter = find_tree_iter_by_full_name(app.datasets_store, dataset)
    if tree_iter is not None:
        reload_row_children(app.datasets_store, tree_iter, repo=repo)
    return True


def on_datasets_unmount(app):
    """Unmount all selected filesystems and snapshots, warning if any are busy."""
    repo = _repo(app)
    items = get_tree_selection_items(app.datasets_view)
    if not items:
        log_msg("WARN: Select an item to unmount")
        return

    targets = [i for i in items if i["type"] in ("pool", "dataset", "snapshot", "volume-partition")]
    if not targets:
        log_msg("WARN: Select filesystems, snapshots, or volumes to unmount")
        return

    changed = False
    for item in targets:
        if item["type"] in ("pool", "dataset") and item.get("zfs_type") == "filesystem":
            if not item.get("mounted", False):
                continue
            changed = _unmount_one_dataset(item, repo, app) or changed
        elif item["type"] in ("pool", "dataset") and item.get("zfs_type") == "volume":
            changed = _unmount_one_volume(item, repo, app) or changed
        elif item["type"] == "volume-partition":
            if not item.get("mounted", False):
                continue
            changed = _unmount_one_volume_partition(item, repo, app) or changed
        elif item["type"] == "snapshot":
            if not item.get("mounted", False):
                continue
            changed = _unmount_one_snapshot(item, repo, app) or changed

    if changed:
        update_mounted_states(app)
