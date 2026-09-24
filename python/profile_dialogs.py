"""Profile dialogs shared by multiple tab pages.

Two families live here:

- Workload-profile dialogs and execution (Apply Profile, Rewrite Data, and
  the workload profile manager/editor), used by the Datasets page actions
  that operate on a caller-supplied dataset list. Selection collection and
  page refresh live with the calling page; pool topology facts the dialogs
  need (such as whether the pool has a special vdev) are passed in by the
  caller.
- Schedule profile dialogs (Add Profile to Schedule / Recall Profile) for
  the backup, offsite, restore, prune, and schedule tabs.
"""

import shlex
import subprocess

import gi
import node_config
import zfs_lock_manager as zlm

gi.require_version("Gtk", "3.0")

from command_builders import BashStep
from feature_config import (
    delete_workload_profile,
    get_workload_profiles,
    is_builtin_workload_profile,
    reset_workload_profiles,
    save_workload_profiles,
)
from gi.repository import Gtk, Pango
from gui_helpers import (
    _ensure_treeview_scrolling,
    configure_treeview_column,
    create_dialog,
    show_error_dialog,
    show_warning_dialog,
)
from logging_config import log_msg
from profile_manager import (
    create_profile,
    get_user,
    list_profiles,
    load_profile,
    profile_exists,
    update_profile,
)
from profile_validation import validate_profiles
from workload_profiles import (
    LIVE_PROPERTIES,
    ZFS_GET_PROPERTIES,
    build_apply_plan,
    build_zfs_set_commands,
    profile_has_warning,
    warning_text,
    zfs_set_commands_with_entries,
)
from zfs_repository import TopologyNode


def _user_friendly_property_error(dataset: str, exc: Exception) -> str:
    """Return a user-friendly explanation for a failed property read on *dataset*.

    Common ZFS failures are mapped to plain-language messages with actionable
    recommendations. Raw ZFS stderr/usage text is never returned.
    """
    if isinstance(exc, subprocess.CalledProcessError):
        stderr = (exc.stderr or "").strip()
        first_line = stderr.splitlines()[0] if stderr else ""
        lower = first_line.lower()

        if "invalid property" in lower:
            return (
                "the ZFS command requested an unsupported property. "
                "This usually indicates a bug in the requested property list; "
                "please report it if the problem persists."
            )
        if "dataset does not exist" in lower:
            return (
                "the dataset was not found. It may have been deleted or the pool "
                "may not be imported."
            )
        if "permission denied" in lower or "not authorized" in lower:
            return (
                "permission was denied. Run ZFS Utilities as root or ensure "
                "passwordless sudo is configured for zfs/zpool commands."
            )

        return (
            "the ZFS command failed. Check that the pool is imported, the "
            "dataset exists, and ZFS is healthy."
        )

    return f"an unexpected error occurred: {exc}"


def _topology_has_special_vdev(topology: TopologyNode | None) -> bool:
    """Return True if the topology tree contains a 'special' vdev node."""
    if topology is None:
        return False
    if topology.vdev_type == "special":
        return True
    return any(_topology_has_special_vdev(child) for child in topology.children)


# ---------------------------------------------------------------------------
# Rewrite Data action
# ---------------------------------------------------------------------------


def _build_rewrite_command(ds_name: str, mountpoint: str) -> str:
    """Build the bash script that rewrites *ds_name* in place via its mountpoint.

    ``zfs rewrite`` operates on file/directory paths inside a mounted
    filesystem, not on dataset names, so the script:

    1. Records whether the dataset is already mounted.
    2. Mounts it (non-recursively) only if it is not mounted; the mount must
       succeed or the script exits non-zero.
    3. Runs ``zfs rewrite -P -r -x -v <mountpoint>`` — physical rewrite (so
       rewritten blocks do not inflate later incremental send streams),
       recursive, never crossing filesystem mount points (so child datasets
       mounted beneath this one are not rewritten), verbose for log progress.
    4. Unmounts the dataset only if this script mounted it, restoring the
       prior state. An unmount failure is reported but does not mask the
       rewrite's exit code.

    The script sources bashinit and uses log_msg so its messages land in the
    same session log as every other BashStep (see command_builders.py).
    """
    q_ds = shlex.quote(ds_name)
    q_mp = shlex.quote(mountpoint)
    return (
        "source ~/bashinit; bashinit\n"
        f"mounted_before=$(zfs get -H -o value mounted {q_ds})\n"
        "mounted_by_us=0\n"
        'if [[ "$mounted_before" != "yes" ]]; then\n'
        f"    if ! zfs mount {q_ds}; then\n"
        f'        log_msg "FATAL: could not mount {ds_name} to rewrite data"\n'
        "        exit 1\n"
        "    fi\n"
        "    mounted_by_us=1\n"
        "fi\n"
        f"zfs rewrite -P -r -x -v {q_mp}\n"
        "rewrite_rc=$?\n"
        'if [[ "$mounted_by_us" == "1" ]]; then\n'
        f"    if ! zfs unmount {q_ds}; then\n"
        f'        log_msg "WARN: could not unmount {ds_name} after rewrite"\n'
        "    fi\n"
        "fi\n"
        "exit $rewrite_rc\n"
    )


def on_rewrite_data(app, datasets, refresh=None):
    """Rewrite data on *datasets* (all filesystems) using ``zfs rewrite -P``.

    Requires at least one filesystem dataset, OpenZFS 2.3+, the pool's
    physical_rewrite feature, and a running dataset_runner. Unmounted
    datasets are mounted temporarily and returned to their prior state
    afterwards. Acquires one write lock per dataset, runs one BashStep per
    dataset sequentially, and invokes *refresh* on completion.
    """
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Rewrite Data is available only on the storage host")
        return
    if not datasets:
        log_msg("WARN: Select at least one dataset to rewrite data")
        return

    non_filesystems = [ds["name"] for ds in datasets if ds["type"] != "filesystem"]
    if non_filesystems:
        log_msg(
            "WARN: Rewrite Data supports filesystem datasets only; "
            "zfs rewrite cannot act on a volume's block device "
            f"({', '.join(non_filesystems)})"
        )
        return

    if not app.ctx.zfs_caps.supports("zfs_rewrite"):
        log_msg("WARN: Rewrite Data requires OpenZFS 2.3+")
        return

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    repo = app.ctx.zfs_repository
    mountpoints = {}
    for ds in datasets:
        ds_name = ds["name"]
        try:
            props = repo.get_properties(ds_name, ["mountpoint"])
        except Exception as exc:  # pragma: no cover - defensive
            log_msg(
                f"WARN: Could not read properties for {ds_name}: "
                f"{_user_friendly_property_error(ds_name, exc)}"
            )
            return
        mountpoint = props.get("mountpoint", "-")
        if mountpoint in ("none", "legacy", "-"):
            log_msg(f"WARN: Cannot rewrite data for {ds_name}: mountpoint is '{mountpoint}'")
            return
        mountpoints[ds_name] = mountpoint

    pools = []
    for ds in datasets:
        pool = ds["name"].split("/", 1)[0]
        if pool not in pools:
            pools.append(pool)
    for pool in pools:
        if not app.ctx.zfs_caps.supports_pool_feature(pool, "physical_rewrite"):
            log_msg(
                f"WARN: Rewrite Data requires the physical_rewrite pool feature on {pool} "
                f"(zpool set feature@physical_rewrite=enabled {pool})"
            )
            return

    if len(datasets) == 1:
        dialog_text = f"Rewrite data on {datasets[0]['name']}?"
    else:
        dialog_text = f"Rewrite data on {len(datasets)} datasets?"
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text=dialog_text,
    )
    secondary = (
        "zfs rewrite -P rewrites existing blocks in place (physical rewrite, "
        "preserving snapshot and incremental-send boundaries) so they match "
        "the current dataset properties. Datasets are mounted temporarily "
        "if they are not currently mounted and returned to their prior state "
        "afterwards. Requires the pool's physical_rewrite feature. This may "
        "take a long time and cannot be undone."
    )
    if len(datasets) > 1:
        secondary += "\n\n" + "\n".join(ds["name"] for ds in datasets)
    dialog.format_secondary_text(secondary)
    response = dialog.run()
    dialog.destroy()
    if response != Gtk.ResponseType.YES:
        return

    dataset_names = [ds["name"] for ds in datasets]
    lock_ids = zlm.acquire_multiple("w", dataset_names)

    steps = [
        BashStep(
            ["bash", "-c", _build_rewrite_command(ds_name, mountpoints[ds_name])],
            f"Rewrite data on {ds_name}",
            is_rsync=False,
            fatal=False,
        )
        for ds_name in dataset_names
    ]

    def _on_complete(cancelled=False, rc=None):
        for lock_id in lock_ids:
            zlm.release(lock_id)
        target = dataset_names[0] if len(dataset_names) == 1 else f"{len(dataset_names)} datasets"
        if cancelled:
            log_msg(f"INFO: Rewrite Data cancelled for {target}")
        elif rc:
            log_msg(f"WARN: Rewrite Data failed for {target} (rc={rc})")
        else:
            log_msg(f"INFO: Rewrite Data complete for {target}")
        if refresh is not None:
            refresh()

    runner.operation_detail = (
        f"Rewrite Data: {dataset_names[0]}"
        if len(dataset_names) == 1
        else f"Rewrite Data: {len(dataset_names)} datasets"
    )
    runner.set_steps(steps)
    if refresh is not None:
        refresh()
    runner.start(on_complete=_on_complete)


# ---------------------------------------------------------------------------
# Workload profile management dialog
# ---------------------------------------------------------------------------


def _profile_applies_to_text(profile: dict) -> str:
    """Return a human-readable applies-to string for a profile."""
    applies_to = profile.get("applies_to", [])
    if "filesystem" in applies_to and "volume" in applies_to:
        return "filesystem, volume"
    if "filesystem" in applies_to:
        return "filesystem"
    if "volume" in applies_to:
        return "volume"
    return ""


def show_manage_profiles_dialog(app):
    """Show the Manage Workload Profiles dialog."""
    dialog = create_dialog(
        "Manage Workload Profiles",
        app,
        [
            (Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE),
        ],
        default_response=Gtk.ResponseType.CLOSE,
        size=(700, 500),
    )
    content = dialog.get_content_area()

    store = Gtk.ListStore(str, str, str, str)
    view = Gtk.TreeView(model=store)
    view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

    cols = [
        (0, "Name", 180),
        (1, "Applies to", 120),
        (2, "Description", 350),
        (3, "Kind", 80),
    ]
    for col_idx, title_text, width in cols:
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        configure_treeview_column(col, width=width)
        view.append_column(col)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_min_content_height(250)
    scrolled.add(view)
    content.pack_start(scrolled, True, True, 0)

    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    btn_box.set_halign(Gtk.Align.START)

    add_btn = Gtk.Button(label="Add")
    edit_btn = Gtk.Button(label="Edit")
    delete_btn = Gtk.Button(label="Delete")
    reset_btn = Gtk.Button(label="Reset to Defaults")

    btn_box.pack_start(add_btn, False, False, 0)
    btn_box.pack_start(edit_btn, False, False, 0)
    btn_box.pack_start(delete_btn, False, False, 0)
    btn_box.pack_start(reset_btn, False, False, 0)
    content.pack_start(btn_box, False, False, 0)

    def _refresh_list():
        store.clear()
        profiles = get_workload_profiles(app.config)
        for name, profile in profiles.items():
            store.append(
                [
                    name,
                    _profile_applies_to_text(profile),
                    profile.get("description", ""),
                    "built-in" if is_builtin_workload_profile(name) else "custom",
                ]
            )

    def _selected_name():
        selection = view.get_selection()
        model, pathlist = selection.get_selected_rows()
        if not pathlist:
            return None
        tree_iter = model.get_iter(pathlist[0])
        return model.get_value(tree_iter, 0)

    def _selected_is_builtin() -> bool:
        name = _selected_name()
        return name is not None and is_builtin_workload_profile(name)

    def _on_selection_changed(_selection):
        # Seeded profiles are immutable: no editing or deleting them.
        builtin = _selected_is_builtin()
        edit_btn.set_sensitive(not builtin)
        delete_btn.set_sensitive(not builtin)
        tooltip = (
            "Built-in profiles cannot be modified; use Reset to Defaults to restore them"
            if builtin
            else ""
        )
        edit_btn.set_tooltip_text(tooltip)
        delete_btn.set_tooltip_text(tooltip)

    def _on_add(_btn):
        show_profile_editor_dialog(app)
        _refresh_list()

    def _on_edit(_btn):
        name = _selected_name()
        if name is None:
            log_msg("WARN: Select a profile to edit")
            return
        if is_builtin_workload_profile(name):
            log_msg(f"WARN: Workload profile {name!r} is built in and cannot be edited")
            return
        profiles = get_workload_profiles(app.config)
        if name not in profiles:
            log_msg(f"WARN: Profile {name} no longer exists")
            _refresh_list()
            return
        show_profile_editor_dialog(app, name)
        _refresh_list()

    def _on_delete(_btn):
        name = _selected_name()
        if name is None:
            log_msg("WARN: Select a profile to delete")
            return
        if is_builtin_workload_profile(name):
            log_msg(f"WARN: Workload profile {name!r} is built in and cannot be deleted")
            return
        confirm = Gtk.MessageDialog(
            transient_for=dialog,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete profile {name}?",
        )
        confirm.format_secondary_text("This cannot be undone.")
        response = confirm.run()
        confirm.destroy()
        if response == Gtk.ResponseType.YES:
            delete_workload_profile(app.config, name)
            _refresh_list()

    def _on_reset(_btn):
        confirm = Gtk.MessageDialog(
            transient_for=dialog,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Reset workload profiles to defaults?",
        )
        confirm.format_secondary_text(
            "All custom profiles will be discarded and the seeded defaults will be restored."
        )
        response = confirm.run()
        confirm.destroy()
        if response == Gtk.ResponseType.YES:
            reset_workload_profiles(app.config)
            _refresh_list()

    add_btn.connect("clicked", _on_add)
    edit_btn.connect("clicked", _on_edit)
    delete_btn.connect("clicked", _on_delete)
    reset_btn.connect("clicked", _on_reset)
    view.get_selection().connect("changed", _on_selection_changed)

    _refresh_list()
    _on_selection_changed(view.get_selection())
    dialog.show_all()
    dialog.run()
    dialog.destroy()


def show_profile_editor_dialog(app, name=None):
    """Show the Add/Edit Workload Profile dialog and persist on OK.

    When *name* is None a new profile is created. When *name* is provided the
    existing profile is edited (the name field is read-only). Built-in
    (seeded) profiles are immutable and cannot be opened for editing.
    """
    if name is not None and is_builtin_workload_profile(name):
        log_msg(f"WARN: Workload profile {name!r} is built in and cannot be edited")
        return
    profiles = get_workload_profiles(app.config)
    existing = profiles.get(name, {}) if name else {}
    is_edit = name is not None

    dialog = create_dialog(
        "Edit Profile" if is_edit else "Add Profile",
        app,
        [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            (Gtk.STOCK_OK, Gtk.ResponseType.OK),
        ],
        default_response=Gtk.ResponseType.OK,
        size=(500, 600),
    )
    content = dialog.get_content_area()

    grid = Gtk.Grid()
    grid.set_column_spacing(10)
    grid.set_row_spacing(10)
    grid.set_margin_top(10)
    grid.set_margin_bottom(10)
    grid.set_margin_start(10)
    grid.set_margin_end(10)
    content.pack_start(grid, False, False, 0)

    def _add_row(row, label_text, widget):
        label = Gtk.Label(label=label_text)
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)
        return widget

    row = 0
    name_entry = Gtk.Entry()
    name_entry.set_text(name or "")
    name_entry.set_sensitive(not is_edit)
    _add_row(row, "Name:", name_entry)
    row += 1

    desc_entry = Gtk.Entry()
    desc_entry.set_text(existing.get("description", ""))
    _add_row(row, "Description:", desc_entry)
    row += 1

    fs_check = Gtk.CheckButton(label="filesystem")
    fs_check.set_active("filesystem" in existing.get("applies_to", []))
    vol_check = Gtk.CheckButton(label="volume")
    vol_check.set_active("volume" in existing.get("applies_to", []))
    applies_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    applies_box.pack_start(fs_check, False, False, 0)
    applies_box.pack_start(vol_check, False, False, 0)
    _add_row(row, "Applies to:", applies_box)
    row += 1

    prop_entries: dict[str, Gtk.Entry] = {}
    live_props = existing.get("properties", {})
    for prop in LIVE_PROPERTIES:
        entry = Gtk.Entry()
        entry.set_text(live_props.get(prop, ""))
        entry.set_placeholder_text("e.g. zstd")
        _add_row(row, f"{prop}:", entry)
        prop_entries[prop] = entry
        row += 1

    volblock_entry = Gtk.Entry()
    volblock_entry.set_text(live_props.get("volblocksize", ""))
    volblock_entry.set_placeholder_text("creation-only, e.g. 16K")
    _add_row(row, "volblocksize (creation-only):", volblock_entry)
    prop_entries["volblocksize"] = volblock_entry
    row += 1

    ashift_entry = Gtk.Entry()
    ashift_entry.set_text(live_props.get("ashift", ""))
    ashift_entry.set_placeholder_text("informational only, auto-detected")
    ashift_entry.set_editable(False)
    ashift_entry.set_can_focus(False)
    _add_row(row, "pool blocksize (informational):", ashift_entry)
    row += 1

    notes_buf = Gtk.TextBuffer()
    notes_buf.set_text(existing.get("notes", ""))
    notes_tv = Gtk.TextView(buffer=notes_buf)
    notes_tv.set_editable(True)
    notes_tv.set_wrap_mode(Gtk.WrapMode.WORD)
    notes_sw = Gtk.ScrolledWindow()
    notes_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    notes_sw.set_min_content_height(80)
    notes_sw.add(notes_tv)
    _add_row(row, "Notes:", notes_sw)
    row += 1

    dialog.show_all()
    while True:
        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return

        new_name = name_entry.get_text().strip()
        if not new_name:
            _show_validation_error(dialog, "Profile name is required.")
            continue

        if not is_edit and any(p.lower() == new_name.lower() for p in profiles):
            _show_validation_error(dialog, f"A profile named {new_name} already exists.")
            continue

        applies_to = []
        if fs_check.get_active():
            applies_to.append("filesystem")
        if vol_check.get_active():
            applies_to.append("volume")
        if not applies_to:
            _show_validation_error(dialog, "Select at least one of filesystem or volume.")
            continue

        properties: dict[str, str] = {}
        for prop, entry in prop_entries.items():
            value = entry.get_text().strip()
            if value:
                properties[prop] = value
        if not properties:
            _show_validation_error(dialog, "At least one property value is required.")
            continue

        notes = notes_buf.get_text(
            notes_buf.get_start_iter(),
            notes_buf.get_end_iter(),
            True,
        )

        description = desc_entry.get_text().strip()
        new_profile = {
            "description": description,
            "applies_to": applies_to,
            "properties": properties,
            "notes": notes,
        }

        if is_edit:
            profiles[name] = new_profile
        else:
            profiles[new_name] = new_profile
        save_workload_profiles(app.config, profiles)
        dialog.destroy()
        return


def _show_validation_error(parent, message):
    """Show a modal error dialog and block until dismissed."""
    error = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    error.run()
    error.destroy()


# ---------------------------------------------------------------------------
# Apply Profile dialog and execution
# ---------------------------------------------------------------------------


def show_apply_profile_dialog(app, datasets, pool_has_special=False):
    """Show the Apply Profile dialog and return (response, profile_name, profile).

    *pool_has_special* gates the small-files warning and is supplied by the
    caller (True when the dataset's pool has a special allocation vdev).
    """
    profiles = get_workload_profiles(app.config)
    profile_names = list(profiles.keys())
    if not profile_names:
        log_msg("WARN: No workload profiles configured")
        return Gtk.ResponseType.CANCEL, None, None

    first_match = datasets[0].get("profile_match", "custom") if datasets else "custom"
    default_name = None
    for name in profile_names:
        if name == first_match:
            default_name = name
            break
    if default_name is None:
        default_name = profile_names[0]

    dialog = create_dialog(
        "Apply Profile",
        app,
        [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            (Gtk.STOCK_OK, Gtk.ResponseType.OK),
        ],
        default_response=Gtk.ResponseType.OK,
        size=(700, 500),
    )
    content = dialog.get_content_area()

    warning_label = Gtk.Label()
    warning_label.set_halign(Gtk.Align.START)
    warning_label.set_line_wrap(True)
    warning_label.set_no_show_all(True)
    content.pack_start(warning_label, False, False, 0)

    confirm_check = Gtk.CheckButton(label="I understand and want to apply this profile")
    confirm_check.set_no_show_all(True)
    content.pack_start(confirm_check, False, False, 0)

    selector_label = Gtk.Label(label="Select a profile:")
    selector_label.set_halign(Gtk.Align.START)
    content.pack_start(selector_label, False, False, 0)

    picker_store = Gtk.ListStore(str, str, str)
    for name in profile_names:
        profile = profiles.get(name, {})
        picker_store.append(
            [name, _profile_applies_to_text(profile), profile.get("description", "")]
        )

    picker_view = Gtk.TreeView(model=picker_store)
    picker_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    picker_selection = picker_view.get_selection()
    picker_selection.set_mode(Gtk.SelectionMode.SINGLE)

    name_renderer = Gtk.CellRendererText()
    name_col = Gtk.TreeViewColumn("Profile", name_renderer, text=0)
    configure_treeview_column(name_col, width=150)
    picker_view.append_column(name_col)

    applies_renderer = Gtk.CellRendererText()
    applies_col = Gtk.TreeViewColumn("Applies to", applies_renderer, text=1)
    configure_treeview_column(applies_col, width=100)
    picker_view.append_column(applies_col)

    desc_renderer = Gtk.CellRendererText()
    # CellRendererText's wrap-mode property is Pango.WrapMode (Gtk.WrapMode
    # is only for Gtk.TextView); the wrong enum type draws a GLib warning.
    desc_renderer.set_property("wrap-mode", Pango.WrapMode.WORD)
    desc_renderer.set_property("wrap-width", 350)
    desc_col = Gtk.TreeViewColumn("Description", desc_renderer, text=2)
    configure_treeview_column(desc_col, width=350)
    picker_view.append_column(desc_col)

    picker_sw = Gtk.ScrolledWindow()
    picker_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    picker_sw.set_min_content_height(240)
    picker_sw.add(picker_view)
    # Expand so resizing the dialog vertically grows the profile list (and
    # the preview below it) instead of only the preview.
    content.pack_start(picker_sw, True, True, 0)

    def _select_profile_row(name):
        for i, row_name in enumerate(profile_names):
            if row_name == name:
                picker_selection.select_path(i)
                return True
        return False

    if not _select_profile_row(default_name):
        _select_profile_row(profile_names[0])

    preview_label = Gtk.Label(label="Planned commands:")
    preview_label.set_halign(Gtk.Align.START)
    content.pack_start(preview_label, False, False, 0)

    preview_sw = Gtk.ScrolledWindow()
    preview_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    preview_sw.set_min_content_height(200)
    preview_buf = Gtk.TextBuffer()
    preview_tv = Gtk.TextView(buffer=preview_buf)
    preview_tv.set_editable(False)
    preview_tv.set_cursor_visible(False)
    preview_tv.set_monospace(True)
    preview_sw.add(preview_tv)
    content.pack_start(preview_sw, True, True, 0)

    current_name = default_name

    def _read_selected_name():
        # Gtk.TreeSelection.get_selected() returns (model, iter) in real GTK.
        # Some test mocks return MagicMocks instead; callers fall back to the
        # tracked value in that case.
        model, tree_iter = picker_selection.get_selected()
        if tree_iter is not None:
            value = model.get_value(tree_iter, 0)
            if isinstance(value, str):
                return value
        return None

    def _get_active_profile_name():
        return _read_selected_name() or current_name

    def _update_preview(*_args):
        name = _get_active_profile_name()
        profile = profiles.get(name, {})
        has_warning = profile_has_warning(name, profile, pool_has_special)
        text = warning_text(name, profile, pool_has_special)
        if has_warning and text:
            warning_label.set_text(f"Warning: {text}")
            warning_label.show()
            confirm_check.show()
        else:
            warning_label.hide()
            confirm_check.hide()
            confirm_check.set_active(False)

        lines = []
        repo = app.ctx.zfs_repository
        for ds in datasets:
            ds_name = ds["name"]
            ds_type = ds["type"]
            try:
                live_props = repo.get_properties(ds_name, list(ZFS_GET_PROPERTIES))
            except Exception as exc:  # pragma: no cover - defensive
                lines.append(
                    f"# Could not read properties for {ds_name}: "
                    f"{_user_friendly_property_error(ds_name, exc)}"
                )
                continue
            plan = build_apply_plan(profile, ds_name, ds_type, live_props)
            for entry in plan:
                lines.append(f"# {entry['explanation']}")
            commands = build_zfs_set_commands(plan)
            lines.extend(commands)
            lines.append("")
        preview_buf.set_text("\n".join(lines).rstrip("\n"))

    def _on_selection_changed(*_args):
        nonlocal current_name
        raw = _read_selected_name()
        if isinstance(raw, str):
            current_name = raw
        _update_preview()

    picker_selection.connect("changed", _on_selection_changed)
    _update_preview()

    dialog.show_all()
    while True:
        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return Gtk.ResponseType.CANCEL, None, None
        name = _get_active_profile_name()
        profile = profiles.get(name, {})
        if profile_has_warning(name, profile, pool_has_special) and not confirm_check.get_active():
            continue
        dialog.destroy()
        return Gtk.ResponseType.OK, name, profile


def on_apply_profile(app, datasets, profile, refresh=None):
    """Apply the chosen workload *profile* to *datasets*.

    Builds a per-dataset plan from live properties, acquires one ``zlm``
    write lock per dataset, runs one ``zfs set`` BashStep per planned
    property under the dataset runner, and invokes *refresh* on completion.
    """
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Applying profiles is available only on the storage host")
        return

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    repo = app.ctx.zfs_repository
    all_commands = []
    ds_commands: list[tuple[str, str, list[tuple[str, dict]]]] = []
    for ds in datasets:
        ds_name = ds["name"]
        ds_type = ds["type"]
        try:
            live_props = repo.get_properties(ds_name, list(ZFS_GET_PROPERTIES))
        except Exception as exc:  # pragma: no cover - defensive
            log_msg(
                f"WARN: Could not read properties for {ds_name}: "
                f"{_user_friendly_property_error(ds_name, exc)}"
            )
            continue
        plan = build_apply_plan(profile, ds_name, ds_type, live_props)
        cmd_pairs = zfs_set_commands_with_entries(plan)
        if cmd_pairs:
            all_commands.extend(cmd for cmd, _entry in cmd_pairs)
            ds_commands.append((ds_name, ds_type, cmd_pairs))

    if not all_commands:
        dialog = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="No changes to apply",
        )
        dialog.format_secondary_text("All selected datasets already match the chosen profile.")
        dialog.run()
        dialog.destroy()
        return

    dataset_names = [ds["name"] for ds in datasets]
    lock_ids = zlm.acquire_multiple("w", dataset_names)

    steps = []
    for ds_name, _ds_type, cmd_pairs in ds_commands:
        for cmd, entry in cmd_pairs:
            desc = f"Set {entry['property']}={entry['value']} on {ds_name}"
            steps.append(
                BashStep(
                    ["bash", "-c", cmd],
                    desc,
                    is_rsync=False,
                    fatal=False,
                )
            )

    def _on_complete(cancelled=False, rc=None):
        for lock_id in lock_ids:
            zlm.release(lock_id)
        if cancelled:
            log_msg("INFO: Apply Profile cancelled")
        elif rc:
            log_msg(f"WARN: Apply Profile failed (rc={rc})")
        elif all_commands:
            log_msg(f"INFO: Apply Profile complete: {len(all_commands)} command(s)")
        if refresh is not None:
            refresh()

    runner.operation_detail = (
        f"Apply Profile: {dataset_names[0]}"
        if len(dataset_names) == 1
        else f"Apply Profile: {len(dataset_names)} datasets"
    )
    runner.set_steps(steps)
    if refresh is not None:
        refresh()
    runner.start(on_complete=_on_complete)


# ---------------------------------------------------------------------------
# Schedule profile dialogs (backup / offsite / restore / prune profiles)
# ---------------------------------------------------------------------------


def show_add_profile_dialog(app, tab_type, config_dict, on_success=None, dry_run=False):
    """Show the Add Profile to Schedule dialog and save a profile if confirmed.

    Args:
        dry_run: capture the current Dry Run toggle state in the profile.
    """
    user = get_user()
    prefix = f"{user}-{tab_type}-"

    dlg = create_dialog(
        "Add Profile to Schedule",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL), (Gtk.STOCK_OK, Gtk.ResponseType.OK)],
        default_response=Gtk.ResponseType.OK,
    )
    content = dlg.get_content_area()

    prefix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    prefix_box.pack_start(Gtk.Label(label="Prefix:"), False, False, 0)
    prefix_lbl = Gtk.Label(label=prefix)
    prefix_lbl.set_halign(Gtk.Align.START)
    prefix_lbl.set_selectable(True)
    prefix_box.pack_start(prefix_lbl, False, False, 0)
    content.add(prefix_box)

    name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    name_box.pack_start(Gtk.Label(label="Name:"), False, False, 0)
    name_entry = Gtk.Entry()
    name_entry.set_width_chars(1)
    name_entry.set_activates_default(True)
    name_entry.set_hexpand(True)
    name_box.pack_start(name_entry, True, True, 0)
    content.add(name_box)

    note = Gtk.Label()
    note.set_markup("<small>Only letters, digits, hyphens, and underscores allowed.</small>")
    note.set_halign(Gtk.Align.START)
    content.add(note)

    dlg.show_all()
    response = dlg.run()
    custom_name = name_entry.get_text().strip()
    dlg.destroy()

    if response != Gtk.ResponseType.OK or not custom_name:
        return

    import re

    # Regex: ^[A-Za-z0-9_-]+$
    # Purpose: Validate that a custom profile name contains only safe filename characters.
    #          Only letters, digits, hyphens, and underscores are allowed.
    # Example: "my-backup_01" -> match
    #          "my backup"    -> no match (contains space)
    if not re.match(r"^[A-Za-z0-9_-]+$", custom_name):
        show_error_dialog(
            app, "Invalid profile name.\nUse only letters, digits, hyphens, and underscores."
        )
        return

    full_name = prefix + custom_name
    if profile_exists(full_name):
        dlg = Gtk.MessageDialog(
            transient_for=app,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Profile '{full_name}' already exists.",
        )
        dlg.format_secondary_text("Overwrite it with the current tab settings?")
        response = dlg.run()
        dlg.destroy()
        if response != Gtk.ResponseType.YES:
            return
        try:
            profile = update_profile(tab_type, custom_name, config_dict, dry_run=dry_run)
        except ValueError as e:
            show_error_dialog(app, str(e))
            return
    else:
        try:
            profile = create_profile(tab_type, custom_name, config_dict, dry_run=dry_run)
        except ValueError as e:
            show_error_dialog(app, str(e))
            return

    _show_profile_scope_warnings(app, profile)
    if on_success:
        on_success(profile)
    if hasattr(app, "schedule_store"):
        from schedule_page import _refresh_profile_list

        _refresh_profile_list(app)


def _show_profile_scope_warnings(app, profile):
    """Validate the saved profile against others and show warnings."""
    try:
        profiles = list_profiles()
    except Exception:
        return
    names = {p.get("profile_name") for p in profiles}
    if profile.get("profile_name") not in names:
        profiles.append(profile)
    warnings = validate_profiles(profiles)
    profile_name = profile.get("profile_name", "")
    relevant = [w for w in warnings if profile_name in w]
    if relevant:
        show_warning_dialog(app, "Profile scope mismatch detected:\n\n" + "\n\n".join(relevant))


def show_recall_profile_dialog(app, tab_type, on_select):
    """Show a dialog listing profiles of the given tab type."""
    profiles = [p for p in list_profiles() if p.get("tab_type") == tab_type]
    if not profiles:
        show_error_dialog(app, f"No {tab_type} profiles found.")
        return

    dlg = create_dialog(
        "Recall Profile",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL), ("Recall", Gtk.ResponseType.OK)],
        default_response=Gtk.ResponseType.OK,
    )
    content = dlg.get_content_area()

    label = Gtk.Label(label=f"Select a {tab_type} profile to load:")
    label.set_halign(Gtk.Align.START)
    content.add(label)

    store = Gtk.ListStore(str, str)
    for profile in profiles:
        cron = profile.get("cron", {})
        sched = "{} {} {} {} {}".format(
            cron.get("minute", "*"),
            cron.get("hour", "*"),
            cron.get("day", "*"),
            cron.get("month", "*"),
            cron.get("weekday", "*"),
        )
        store.append([profile["profile_name"], sched])

    view = Gtk.TreeView(model=store)
    view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

    r0 = Gtk.CellRendererText()
    c0 = Gtk.TreeViewColumn("Profile", r0, text=0)
    configure_treeview_column(c0, width=150)
    view.append_column(c0)

    r1 = Gtk.CellRendererText()
    c1 = Gtk.TreeViewColumn("Schedule", r1, text=1)
    configure_treeview_column(c1, width=150)
    view.append_column(c1)

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_height(150)
    scroll.add(view)
    _ensure_treeview_scrolling(view)
    content.add(scroll)

    dlg.show_all()
    response = dlg.run()

    selected = None
    if response == Gtk.ResponseType.OK:
        sel = view.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter:
            profile_name = model.get_value(tree_iter, 0)
            selected = load_profile(profile_name)

    dlg.destroy()

    if selected and on_select:
        on_select(selected)
