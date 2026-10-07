"""Disk label wipe — helpers and typed-confirmation dialog for the Disks page.

Wraps the ``zfswipe`` script, which clears leftover signatures (ZFS labels,
partition tables, filesystem signatures) from an inactive disk via the
fallback ladder ``zpool labelclear`` → ``wipefs`` → ``dd`` so the disk can be
reused as a pool device. This module computes whether the selected disk is
wipe-eligible, builds the warnings shown before the typed confirmation, and
runs the dialog. Decision logic stays in pure helpers (testable without
GTK); the script itself re-verifies inactivity before touching anything.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping

import gi

gi.require_version("Gtk", "3.0")

from disk_repository import DiskInfo
from gi.repository import Gtk
from gui_helpers import create_scrolled_dialog
from path_utils import resolve_local_bin

# Custom dialog response id for the Wipe button. Distinct from
# Gtk.ResponseType values (which are negative).
_RESPONSE_WIPE = 13

_BY_ID_DIR = "/dev/disk/by-id"


def typed_target(disk: DiskInfo) -> str:
    """Return the text the user must type to confirm the wipe of *disk*."""
    return os.path.basename(disk.path)


def wipe_block_reason(disk: DiskInfo, disks: list[DiskInfo]) -> str | None:
    """Return why *disk* must not be wiped, or None when it is wipe-eligible.

    A disk is wipe-eligible only when neither it nor anything else on its
    backing disk belongs to an imported pool — the same conservative rule the
    ``zfswipe`` script enforces. Wiping labels on a disk that shares hardware
    with a live pool member would risk that pool.
    """
    if disk.pools:
        return f"member of imported pool '{disk.pools[0]}'"
    root = disk.parent_path or disk.path
    for other in disks:
        on_same_disk = other.path == root or other.parent_path == root
        if on_same_disk and other.pools:
            return (
                f"{os.path.basename(other.path)} on the same disk belongs to "
                f"imported pool '{other.pools[0]}'"
            )
    return None


def _importable_pool_for(disk: DiskInfo, importable_members: Mapping[str, list[str]]):
    """Return the importable pool name whose members live on *disk*, or None.

    Member paths may name by-id symlinks; basename and realpath matching
    mirrors the pool-membership logic in pool_create._match_pool.
    """
    disk_paths = {disk.path, os.path.realpath(disk.path)}
    if disk.by_id:
        by_id_path = os.path.join(_BY_ID_DIR, disk.by_id)
        disk_paths.update({by_id_path, os.path.realpath(by_id_path)})
    disk_bases = {os.path.basename(path) for path in disk_paths}
    for pool_name, paths in importable_members.items():
        for path in paths:
            if path in disk_paths or os.path.basename(path) in disk_bases:
                return pool_name
    return None


def wipe_warnings(
    disk: DiskInfo,
    disks: list[DiskInfo],
    importable_members: Mapping[str, list[str]],
) -> list[str]:
    """Build the warning lines shown above the typed confirmation."""
    warnings: list[str] = []
    importable = _importable_pool_for(disk, importable_members)
    if importable is not None:
        warnings.append(
            f"labels of importable pool '{importable}' live on this device; "
            "wiping destroys that pool's on-disk configuration permanently — "
            "it can never be imported"
        )
    if disk.parent_path is None:
        partitions = [
            other for other in disks if other.parent_path == disk.path and other.path != disk.path
        ]
        if partitions:
            warnings.append(
                f"{len(partitions)} partition(s) on this disk will be destroyed "
                "along with all data on them"
            )
    warnings.append(
        "the dd fallback blindly zeroes the first and last 1 MiB of the "
        "device (and of each partition): partition tables, foreign labels, "
        "and any data in those ranges are destroyed"
    )
    warnings.append("this is not a secure erase — data between the wiped ranges survives")
    return warnings


def build_wipe_command(disk: DiskInfo) -> list[str]:
    """Build the ``zfswipe`` argv for *disk* (GUI confirmed, script unprompted)."""
    script = resolve_local_bin("zfswipe") or "zfswipe"
    return [script, disk.path, "--confirmed"]


def _identity_rows(disk: DiskInfo) -> list[tuple[str, str]]:
    """Return (label, value) pairs describing the device about to be wiped."""
    return [
        ("Path", disk.path),
        ("by-id", disk.by_id or "-"),
        ("Model", disk.model or "-"),
        ("Serial", disk.serial or "-"),
        ("Size", disk.size_human),
        ("Type", disk.disk_type),
    ]


def show_wipe_dialog(app, disk: DiskInfo, warnings: list[str]) -> bool:
    """Run the Wipe Labels dialog.

    Shows the device identity, the warnings, the exact script command, and
    requires the device name (``typed_target``) to be typed exactly before
    the Wipe button becomes sensitive. Returns True when the user confirms,
    False when the dialog is cancelled.
    """
    target = typed_target(disk)
    command = build_wipe_command(disk)

    dialog, content = create_scrolled_dialog(
        "Wipe Disk Labels",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(640, 520),
    )
    wipe_btn = dialog.add_button("Wipe", _RESPONSE_WIPE)
    wipe_btn.set_sensitive(False)

    grid = Gtk.Grid(column_spacing=10, row_spacing=4)
    for row, (label, value) in enumerate(_identity_rows(disk)):
        grid.attach(Gtk.Label(label=f"{label}:"), 0, row, 1, 1)
        value_label = Gtk.Label(label=value)
        value_label.set_halign(Gtk.Align.START)
        grid.attach(value_label, 1, row, 1, 1)
    content.pack_start(grid, False, False, 0)
    content.pack_start(Gtk.Separator(), False, False, 0)

    warnings_label = Gtk.Label(
        label="Warnings:\n" + "\n".join(f"• {warning}" for warning in warnings)
    )
    warnings_label.set_halign(Gtk.Align.START)
    warnings_label.set_line_wrap(True)
    content.pack_start(warnings_label, False, False, 0)
    content.pack_start(Gtk.Separator(), False, False, 0)

    command_label = Gtk.Label(label="Exact command that will run:")
    command_label.set_halign(Gtk.Align.START)
    content.pack_start(command_label, False, False, 0)
    command_buf = Gtk.TextBuffer()
    command_buf.set_text(shlex.join(command))
    command_tv = Gtk.TextView(buffer=command_buf)
    command_tv.set_editable(False)
    command_tv.set_cursor_visible(False)
    command_tv.set_monospace(True)
    content.pack_start(command_tv, False, False, 0)

    methods_label = Gtk.Label(
        label="The script wipes in order, stopping when the device probes clean:\n"
        "1. zpool labelclear -f — ZFS labels and L2ARC headers only\n"
        "2. wipefs -a — all signatures, incl. the partition table\n"
        "3. dd — zero the first and last 1 MiB of the device (and each partition)"
    )
    methods_label.set_halign(Gtk.Align.START)
    methods_label.set_line_wrap(True)
    content.pack_start(methods_label, False, False, 0)

    typed_hint = Gtk.Label(label=f"Type the device name '{target}' exactly to enable Wipe.")
    typed_hint.set_halign(Gtk.Align.START)
    content.pack_start(typed_hint, False, False, 0)
    typed_entry = Gtk.Entry()
    typed_entry.set_hexpand(True)
    content.pack_start(typed_entry, False, False, 0)

    def _on_typed_changed(entry):
        wipe_btn.set_sensitive(entry.get_text().strip() == target)

    typed_entry.connect("changed", _on_typed_changed)

    dialog.show_all()
    try:
        response = dialog.run()
        return response == _RESPONSE_WIPE and typed_entry.get_text().strip() == target
    finally:
        dialog.destroy()
