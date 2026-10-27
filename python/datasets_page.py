"""
Datasets tab UI — collapsible tree of all pool datasets, snapshots, and holds.

Snapshot management (delete, hold, rollback) is handled inline rather than
in a separate window, so holds are always visible in the tree.
"""

import re
import shlex
import subprocess

import gi
import node_config

gi.require_version("Gtk", "3.0")
from command_builders import BashStep
from feature_config import get_workload_profiles
from gi.repository import GLib, Gtk
from gui_helpers import (
    UNMOUNTED_FG,
    TreeSearch,
    _row_fg_color,
    add_scrolled_text_view,
    append_treeview_copy_items,
    build_full_dataset_name,
    configure_treeview_column,
    create_scrolled_dialog,
    dataset_name_cell_func,
    expand_tree_recursively,
    get_expanded_rows,
    get_mounted_snapshots,
    get_tree_selection_items,
    on_row_expanded,
    restore_expanded_rows,
    set_monospace_font,
    setup_row_scroll,
)
from logging_config import log_msg
from path_utils import resolve_local_bin
from profile_dialogs import (
    _topology_has_special_vdev,
    on_apply_profile,
    on_rewrite_data,
    show_apply_profile_dialog,
    show_manage_profiles_dialog,
)
from workload_profiles import ZFS_GET_PROPERTIES, match_profile
from zfs_repository import zvol_device_path

# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------


def create_datasets_page(app):
    """Build and return the full Datasets tab widget."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(10)
    box.set_margin_end(10)
    box.set_margin_top(10)
    box.set_margin_bottom(10)

    title_label = Gtk.Label()
    title_label.set_markup("<big><b>Datasets</b></big>")
    title_label.set_halign(Gtk.Align.START)
    box.pack_start(title_label, False, False, 0)

    box.pack_start(Gtk.Separator(), False, False, 0)

    # Search bar
    search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    search_icon = Gtk.Image.new_from_icon_name("system-search", Gtk.IconSize.BUTTON)
    search_box.pack_start(search_icon, False, False, 0)

    app.datasets_search_entry = Gtk.Entry()
    app.datasets_search_entry.set_placeholder_text("Search datasets...")
    app.datasets_search_entry.set_width_chars(1)
    search_box.pack_start(app.datasets_search_entry, True, True, 0)

    app.datasets_search_clear_btn = Gtk.Button()
    app.datasets_search_clear_btn.set_image(
        Gtk.Image.new_from_icon_name("edit-clear", Gtk.IconSize.BUTTON)
    )
    app.datasets_search_clear_btn.set_tooltip_text("Clear search")
    search_box.pack_start(app.datasets_search_clear_btn, False, False, 0)

    app.datasets_search_prev_btn = Gtk.Button()
    app.datasets_search_prev_btn.set_image(
        Gtk.Image.new_from_icon_name("go-up", Gtk.IconSize.BUTTON)
    )
    app.datasets_search_prev_btn.set_tooltip_text("Previous match")
    search_box.pack_start(app.datasets_search_prev_btn, False, False, 0)

    app.datasets_search_next_btn = Gtk.Button()
    app.datasets_search_next_btn.set_image(
        Gtk.Image.new_from_icon_name("go-down", Gtk.IconSize.BUTTON)
    )
    app.datasets_search_next_btn.set_tooltip_text("Next match")
    search_box.pack_start(app.datasets_search_next_btn, False, False, 0)

    app.datasets_search_results_label = Gtk.Label()
    app.datasets_search_results_label.set_halign(Gtk.Align.START)
    app.datasets_search_results_label.set_margin_end(10)
    search_box.pack_start(app.datasets_search_results_label, False, False, 5)

    box.pack_start(search_box, False, False, 0)

    # TreeStore: pools -> datasets -> snapshots -> holds
    # Columns: name, creation, type, used, avail, refer, origin/clones,
    #          loaded, mounted, fg_color
    app.datasets_store = Gtk.TreeStore(str, str, str, str, str, str, str, bool, bool, str)
    app.datasets_view = Gtk.TreeView(model=app.datasets_store)
    app.datasets_view._zfs_repo = app.ctx.zfs_repository
    app.datasets_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.datasets_view.set_enable_tree_lines(True)
    app.datasets_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    app.datasets_search = TreeSearch(
        app.datasets_view,
        app.datasets_search_entry,
        app.datasets_search_results_label,
        app.datasets_search_prev_btn,
        app.datasets_search_next_btn,
        full_name_func=build_full_dataset_name,
    )
    app.datasets_search_clear_btn.connect("clicked", lambda _b: app.datasets_search.clear())

    ds_columns = [
        ("Name", 0, 150),
        ("Created", 1, 110),
        ("Type", 2, 70),
        ("Used", 3, 65),
        ("Avail", 4, 65),
        ("Refer", 5, 65),
        ("Origin / Clones", 6, 130),
    ]
    for title, col_idx, width in ds_columns:
        renderer = Gtk.CellRendererText()
        if title == "Created":
            set_monospace_font(renderer)
        col = Gtk.TreeViewColumn(title, renderer, text=col_idx, foreground=9)
        if col_idx in (3, 4, 5):
            renderer.set_property("xalign", 1.0)
            col.set_alignment(1.0)
        configure_treeview_column(col, width=width)
        if col_idx == 0:
            col.set_cell_data_func(renderer, dataset_name_cell_func)
        elif col_idx == 6:
            pass  # No special rendering needed for origin/clones column
        app.datasets_view.append_column(col)

    app._ui_state.bind_treeview(app.datasets_view, "datasets_view")

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.add(app.datasets_view)
    setup_row_scroll(scrolled, app.datasets_view)
    app.datasets_scrolled = scrolled
    box.pack_start(scrolled, True, True, 0)

    # Summary row: dataset count on the left, color legend on the right
    summary_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    app.datasets_summary_label = Gtk.Label()
    app.datasets_summary_label.set_halign(Gtk.Align.START)
    summary_row.pack_start(app.datasets_summary_label, False, False, 0)

    app.datasets_legend_label = Gtk.Label()
    app.datasets_legend_label.set_markup(
        f"<small><i><span foreground='{UNMOUNTED_FG}'>Teal text</span>"
        " — unmounted filesystem/snapshot or unattached volume</i></small>"
    )
    app.datasets_legend_label.set_halign(Gtk.Align.END)
    summary_row.pack_start(app.datasets_legend_label, True, False, 0)
    box.pack_start(summary_row, False, False, 0)

    # Connect selection changed for button sensitivity
    app.datasets_view.get_selection().connect("changed", _on_ds_selection_changed, app)

    # Lazy-load children when rows are expanded
    app.datasets_view.connect("row-expanded", on_row_expanded, None)
    app.datasets_view.connect("row-expanded", _on_ds_row_expanded_collapsed, app)
    app.datasets_view.connect("row-collapsed", _on_ds_row_expanded_collapsed, app)

    # Right-click context menu
    app.datasets_view.connect("button-press-event", _on_datasets_button_press, app)

    # Initial load
    refresh_datasets_page(app)

    return box


# ---------------------------------------------------------------------------
# Data refresh
# ---------------------------------------------------------------------------


def _append_root_dataset_row(app, pool):
    """Append a top-level row for *pool*'s root dataset.

    Uses the real root-dataset properties when available; falls back to a
    minimal filesystem row so the user can still expand it.
    """
    repo = app.ctx.zfs_repository
    try:
        root_rows = repo.list_datasets(pool=pool, depth=0)
        if root_rows:
            root = root_rows[0]
            row_data = [root.creation, root.ds_type, root.used, root.avail, root.refer]
            origin_val = root.origin if root.origin != "-" else ""
            mounted = root.mounted == "yes"
            fg_color = _row_fg_color(mounted, root.ds_type)
            return app.datasets_store.append(
                None,
                [pool] + row_data + [origin_val, False, mounted, fg_color],
            )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Could not load root dataset for pool {pool}: {e}")

    # Fallback: minimal row so the pool is still listed and expandable.
    return app.datasets_store.append(
        None, [pool, "", "filesystem", "", "", "", "", False, True, None]
    )


def refresh_datasets_page(app, pool_filter=None):
    """Refresh dataset tree: load root datasets for each pool; children load on demand."""
    expanded = get_expanded_rows(app.datasets_store, app.datasets_view)

    # Remember vertical scroll offset so the view does not jump to top.
    saved_scroll = None
    scrolled = getattr(app, "datasets_scrolled", None)
    if scrolled is not None:
        vadj = scrolled.get_vadjustment()
        if vadj is not None:
            saved_scroll = vadj.get_value()

    # Remember selection so we can re-select after repopulating
    selection = app.datasets_view.get_selection()
    model, paths = selection.get_selected_rows()
    selected_names = []
    for path in paths:
        try:
            tree_iter = model.get_iter(path)
            selected_names.append(build_full_dataset_name(model, tree_iter))
        except ValueError:
            pass

    app.datasets_store.clear()

    try:
        online_pools = [row.name for row in app.ctx.zfs_repository.list_pools()]
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error listing pools: {e}")
        return

    if pool_filter:
        pools_to_show = [pool_filter] if pool_filter in online_pools else []
    else:
        pools_to_show = online_pools

    for pool in pools_to_show:
        ds_iter = _append_root_dataset_row(app, pool)
        # Dummy child so the expand arrow appears
        app.datasets_store.append(
            ds_iter, ["(loading...)", "", "", "", "", "", "", True, False, None]
        )

    app.datasets_summary_label.set_text(f"{len(pools_to_show)} datasets")

    # Restore expanded rows, loading children as we go
    restore_expanded_rows(app.datasets_store, app.datasets_view, expanded)

    # Restore vertical scroll position once GTK has allocated the new rows
    if saved_scroll is not None:
        GLib.idle_add(_restore_scroll, app.datasets_scrolled, saved_scroll)

    # Re-select previously selected items if they still exist
    if selected_names:
        _select_by_name(app.datasets_store, app.datasets_view, selected_names)
        update_ds_button_sensitivity(app)

    # Re-run active search after refresh
    if app.datasets_search._text:
        app.datasets_search._run_search()


def _restore_scroll(scrolled, saved_value):
    """Clamp and restore a saved vertical scroll offset."""
    vadj = scrolled.get_vadjustment()
    if vadj is None:
        return False
    upper = vadj.get_upper()
    page = vadj.get_page_size()
    max_value = max(0.0, upper - page)
    vadj.set_value(max(0.0, min(saved_value, max_value)))
    return False


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------

# build_full_dataset_name is imported from gui_helpers.py


def _select_by_name(store, view, names):
    """Walk the tree and select rows whose full ZFS name is in *names*."""
    selection = view.get_selection()
    selection.unselect_all()

    def _walk(tree_iter, prefix):
        while tree_iter:
            name = store.get_value(tree_iter, 0)
            full = f"{prefix}/{name}" if prefix else name
            if full in names:
                path = store.get_path(tree_iter)
                selection.select_path(path)
            child = store.iter_children(tree_iter)
            if child:
                _walk(child, full)
            tree_iter = store.iter_next(tree_iter)

    _walk(store.get_iter_first(), "")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _on_ds_row_expanded_collapsed(_view, _iter, _path, app):
    """Re-run the active search when the tree structure changes."""
    app.datasets_search.handle_expand_collapse()


# ---------------------------------------------------------------------------
# Expand selected rows
# ---------------------------------------------------------------------------


def expand_selected_datasets(app):
    """Recursively expand all rows currently selected in the Datasets tree."""
    selection = app.datasets_view.get_selection()
    model, paths = selection.get_selected_rows()
    if not paths:
        return

    placeholders = {"(loading...)", "(no datasets)", "(empty)", "(no holds)"}
    iters_to_expand = []
    for path in paths:
        try:
            tree_iter = model.get_iter(path)
        except ValueError:
            continue
        name = model.get_value(tree_iter, 0)
        ds_type = model.get_value(tree_iter, 2)
        if name in placeholders or ds_type == "hold":
            continue
        iters_to_expand.append(tree_iter)

    if not iters_to_expand:
        return

    dialog = Gtk.MessageDialog(
        transient_for=app,
        flags=Gtk.DialogFlags.MODAL,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.NONE,
        text="Expanding selected rows…",
    )
    dialog.set_deletable(False)
    dialog.show()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)

    app.datasets_search.freeze()
    try:
        for tree_iter in iters_to_expand:
            expand_tree_recursively(app.datasets_view, model, tree_iter)
    finally:
        app.datasets_search.thaw()
        dialog.destroy()
        app.datasets_search.handle_expand_collapse()


# ---------------------------------------------------------------------------
# Button sensitivity
# ---------------------------------------------------------------------------


def _on_ds_selection_changed(selection, app):
    """Update action button sensitivity when the tree selection changes."""
    update_ds_button_sensitivity(app)


def _is_mountable(item, volume_loop_attached, canmount_off):
    """Return True if the Mount action applies to *item* right now."""
    if item["type"] == "volume-partition":
        return item.get("has_filesystem", False) and not item.get("mounted", False)
    if item["type"] in ("pool", "dataset") and item.get("zfs_type") == "volume":
        # Volumes have no zfs "mounted" property; loop-attach state decides.
        return not volume_loop_attached.get(item["name"], False)
    if item["type"] == "snapshot" and item.get("parent_type") == "volume":
        # Snapshots of volumes have no .zfs path and no block device of their
        # own; there is nothing to mount.
        return False
    if item["type"] in ("pool", "dataset") and item["name"] in canmount_off:
        # canmount=off filesystems can never be mounted by ZFS.
        return False
    return not item.get("mounted", False)


def _is_unmountable(item, volume_loop_attached):
    """Return True if the Unmount action applies to *item* right now."""
    if item["type"] in ("pool", "dataset") and item.get("zfs_type") == "volume":
        return volume_loop_attached.get(item["name"], False)
    return item.get("mounted", False)


# VM disk zvols are named vm-<vmid>-disk-<n>; sever-vm-clone derives the owning
# VM from this shape, and the Datasets page uses it to name the VM(s) a
# severance will touch.
_VM_DISK_BASENAME_RE = re.compile(r"^vm-(\d+)-disk-\d+$")


def vmid_of_dataset(dataset_name):
    """Return the VM id owning a vm-<vmid>-disk-<n> dataset name, or None."""
    match = _VM_DISK_BASENAME_RE.match(dataset_name.rsplit("/", 1)[-1])
    return match.group(1) if match else None


def is_clone_dataset(item):
    """Return True when *item* is a clone dataset Sever Clone can act on.

    A clone dataset is a pool/dataset row whose Origin column names a
    snapshot. Severance is defined for VM disk zvols, so a row that carries a
    zfs type must be a volume; rows built without one (test fixtures, older
    callers) are judged by the vm-<id>-disk-<n> basename instead.
    """
    if item.get("type") not in ("pool", "dataset"):
        return False
    if (item.get("origin") or "") in ("", "-"):
        return False
    zfs_type = item.get("zfs_type")
    if zfs_type is None:
        return vmid_of_dataset(item["name"]) is not None
    return zfs_type == "volume"


def sever_clone_datasets(items):
    """Return the unique clone dataset names in *items*, in selection order.

    Only the selected clone datasets are returned — never the other disks of
    a VM — so the action cannot reach beyond what the operator selected.
    """
    names = []
    for item in items:
        if not is_clone_dataset(item):
            continue
        if item["name"] not in names:
            names.append(item["name"])
    return names


def update_ds_button_sensitivity(app):
    """Enable/disable action buttons based on the current selection."""
    repo = app.ctx.zfs_repository
    items = get_tree_selection_items(app.datasets_view)
    types = {i["type"] for i in items} if items else set()

    # Snapshot and Apply Profile / Rewrite Data act on pool/dataset rows
    # only; a selection containing snapshots, holds, or volume partitions
    # disables them.
    def _is_tunable(i):
        if i["type"] not in ("pool", "dataset"):
            return False
        return (i.get("zfs_type") or "filesystem") in ("filesystem", "volume")

    can_snapshot = bool(items) and all(_is_tunable(i) for i in items)
    can_delete = bool(items) and types <= {"dataset", "snapshot", "hold"}
    can_hold = "snapshot" in types and types <= {"snapshot", "hold"}
    can_rollback = len(items) == 1 and types == {"snapshot"}

    browsable_types = ("pool", "dataset", "snapshot", "volume-partition")
    single = items[0] if len(items) == 1 else None
    single_browsable = single is not None and single["type"] in browsable_types
    single_mounted = single_browsable and single.get("mounted", False)

    all_browsable = bool(items) and all(i["type"] in browsable_types for i in items)

    # Volume items report mounted='-' from ZFS, so ask losetup whether a loop
    # device is attached to decide which of Mount/Unmount applies.
    volume_loop_attached = {}
    for i in items:
        if i["type"] in ("pool", "dataset") and i.get("zfs_type") == "volume":
            try:
                attached = repo.loop_find(zvol_device_path(i["name"])) is not None
            except (subprocess.CalledProcessError, FileNotFoundError):
                attached = False
            volume_loop_attached[i["name"]] = attached

    # Filesystem rows with canmount=off can never be mounted by ZFS, so they
    # never enable Mount. Only unmounted rows need the check: an off dataset
    # is never mounted, so mounted rows cannot change the verdict either way.
    canmount_off = set()
    for i in items:
        if (
            i["type"] in ("pool", "dataset")
            and (i.get("zfs_type") or "filesystem") == "filesystem"
            and not i.get("mounted", False)
        ):
            try:
                if repo.get_property(i["name"], "canmount") == "off":
                    canmount_off.add(i["name"])
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

    # A loop-attached volume row reports mounted=True, but Browse has no
    # target for the volume itself; its partition rows are the browsable
    # leaves, so the volume row keeps Browse disabled.
    can_browse = single_mounted and not (
        single is not None
        and single["type"] in ("pool", "dataset")
        and single.get("zfs_type") == "volume"
    )
    can_mount = all_browsable and any(
        _is_mountable(i, volume_loop_attached, canmount_off) for i in items
    )
    can_unmount = all_browsable and any(_is_unmountable(i, volume_loop_attached) for i in items)

    can_expand_selected = bool(items) and any(
        i["type"] in ("pool", "dataset", "snapshot") for i in items
    )

    can_show_big_stuff = len(items) == 1 and types == {"pool"}

    can_sever_clone = bool(items) and any(is_clone_dataset(i) for i in items)

    # Details needs one ZFS-named row: pools, datasets, and snapshots go
    # through `zfs get all` on the full name, and holds are answered from
    # the row itself. Volume partitions are not ZFS datasets, so the
    # button stays disabled for them.
    can_details = len(items) == 1 and types <= {"pool", "dataset", "snapshot", "hold"}

    can_apply_profile = len(items) == 1 and _is_tunable(items[0])
    can_rewrite = (
        bool(items)
        and all(
            i["type"] in ("pool", "dataset") and (i.get("zfs_type") or "filesystem") == "filesystem"
            for i in items
        )
        and app.ctx.zfs_caps.supports("zfs_rewrite")
    )

    can_repair_mount_order = (
        len(items) == 1
        and items[0]["type"] in ("pool", "dataset")
        and (items[0].get("zfs_type") or "filesystem") == "filesystem"
    )

    for attr, sensitive in [
        ("_ds_snapshot_btn", can_snapshot),
        ("_ds_delete_btn", can_delete),
        ("_ds_hold_btn", can_hold),
        ("_ds_rollback_btn", can_rollback),
        ("_ds_browse_btn", can_browse),
        ("_ds_mount_btn", can_mount),
        ("_ds_unmount_btn", can_unmount),
        ("_ds_repair_mount_order_btn", can_repair_mount_order),
        ("_ds_apply_profile_btn", can_apply_profile),
        ("_ds_rewrite_data_btn", can_rewrite),
        ("_ds_manage_profiles_btn", True),
        ("_ds_expand_selected_btn", can_expand_selected),
        ("_ds_showbigstuff_btn", can_show_big_stuff),
        ("_ds_sever_clone_btn", can_sever_clone),
        ("_ds_details_btn", can_details),
    ]:
        btn = getattr(app, attr, None)
        if btn:
            btn.set_sensitive(sensitive)

    # Explain the Mount-disabled cases that otherwise look like a bug:
    # snapshots of volumes (no .zfs path, no block device of their own), and
    # filesystems with canmount=off (ZFS refuses to mount them).
    mount_btn = getattr(app, "_ds_mount_btn", None)
    if mount_btn is not None:
        if not can_mount and any(
            i["type"] == "snapshot" and i.get("parent_type") == "volume" for i in items
        ):
            mount_btn.set_tooltip_text("Snapshots of ZFS volumes cannot be mounted")
        elif not can_mount and canmount_off:
            mount_btn.set_tooltip_text("Datasets with canmount=off cannot be mounted")
        else:
            mount_btn.set_tooltip_text("")


# ---------------------------------------------------------------------------
# Workload profile actions (Apply Profile, Rewrite Data, Manage Profiles)
# ---------------------------------------------------------------------------


def _profile_refresh(app):
    """Post-run refresh for profile actions: buttons plus a full tree reload."""
    update_ds_button_sensitivity(app)
    refresh_datasets_page(app)


def _selected_tunable_datasets(app):
    """Return tunable {name, type} dicts for the current tree selection.

    Only pool/dataset rows whose zfs_type is filesystem or volume are
    returned; snapshots, holds, and volume partitions are skipped. The
    returned dicts feed the Apply Profile and Rewrite Data dialogs.
    """
    datasets = []
    skipped = 0
    for item in get_tree_selection_items(app.datasets_view):
        if item["type"] not in ("pool", "dataset"):
            skipped += 1
            continue
        ds_type = item.get("zfs_type") or "filesystem"
        if ds_type not in ("filesystem", "volume"):
            skipped += 1
            continue
        datasets.append({"name": item["name"], "type": ds_type})
    return datasets, skipped


def on_datasets_apply_profile(app):
    """Apply a workload profile to the selected dataset.

    Enabled for a single pool/dataset row only; the profile picker lists
    just the profiles that apply to that dataset's type (the per-dataset
    plan adapts the property set to the dataset's type and live values).
    """
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Applying profiles is available only on the storage host")
        return
    datasets, _skipped = _selected_tunable_datasets(app)
    if not datasets:
        log_msg("WARN: Select at least one dataset to apply a profile")
        return
    if len(datasets) > 1:
        log_msg("WARN: Apply Profile requires a single dataset selection")
        return

    # Pick the dialog's default profile from the first dataset's live match.
    repo = app.ctx.zfs_repository
    first = datasets[0]
    try:
        live_props = repo.get_properties(first["name"], list(ZFS_GET_PROPERTIES))
        match = match_profile(get_workload_profiles(app.config), first["type"], live_props)
    except Exception:  # pragma: no cover - defensive
        match = "custom"
    for ds in datasets:
        ds["profile_match"] = match

    pool = first["name"].split("/", 1)[0]
    pool_has_special = _topology_has_special_vdev(repo.pool_topology(pool))

    response, _profile_name, profile = show_apply_profile_dialog(app, datasets, pool_has_special)
    if response != Gtk.ResponseType.OK:
        return
    on_apply_profile(app, datasets, profile, refresh=lambda: _profile_refresh(app))


def on_datasets_rewrite_data(app):
    """Rewrite data on the selected filesystem datasets using zfs rewrite."""
    datasets, _skipped = _selected_tunable_datasets(app)
    on_rewrite_data(app, datasets, refresh=lambda: _profile_refresh(app))


def on_datasets_manage_profiles(app):
    """Open the workload profile manager."""
    show_manage_profiles_dialog(app)


# ---------------------------------------------------------------------------
# Sever Clone (sever-vm-clone)
# ---------------------------------------------------------------------------
# A clone's origin snapshot pins its space for as long as any dataset
# references it; `zfs promote` inverts the clone relationship rather than
# severing it. sever-vm-clone instead copies each selected clone zvol in full
# into a fresh, origin-free zvol and swaps it in under the same name, so
# Proxmox configs and iSCSI references keep working. The GUI acts on the
# selected dataset(s) only — never on the unselected disks of a VM — and the
# script re-verifies everything (locks, stopped VMs, space) before it copies.

# Custom dialog response id for the Sever button; distinct from the negative
# Gtk.ResponseType values (same convention as disk_wipe's wipe response).
_RESPONSE_SEVER = 14
# The word that must be typed to arm the Sever button.
_SEVER_CONFIRM_WORD = "sever"


def build_sever_clone_command(datasets):
    """Build the sever-vm-clone argv for *datasets*.

    The GUI-side dialog is the typed confirmation; the script's own remaining
    questions (transfer mode, tight-space holding pool, origin-snapshot
    destruction) are asked through the numbered input-hold prompts.
    """
    script = resolve_local_bin("sever-vm-clone") or "sever-vm-clone"
    return [script, *datasets]


def _sever_dialog_rows(items):
    """Return one description line per selected clone dataset, plus the VMs."""
    lines = []
    vmids = []
    for item in items:
        if not is_clone_dataset(item):
            continue
        vmid = vmid_of_dataset(item["name"])
        if vmid is None:
            owner = "owning VM unknown (name is not vm-<id>-disk-<n>)"
        else:
            owner = f"owning VM {vmid}"
            if vmid not in vmids:
                vmids.append(vmid)
        lines.append(f"{item['name']}\n    origin: {item.get('origin') or '-'}\n    {owner}")
    return lines, vmids


def _sever_vm_phrases(vmids):
    """Return (short VM list, stopped-phrase subject) for the owning VM ids."""
    if not vmids:
        return "no recognizable VM", "the VM(s) that use these disks"
    names = [f"VM {v}" for v in vmids]
    if len(names) == 1:
        return names[0], names[0]
    return ", ".join(names), ", ".join(names[:-1]) + " and " + names[-1]


def show_sever_clone_dialog(app, items):
    """Run the typed-confirmation dialog for severing the selected clones.

    Names exactly the selected dataset(s) and their owning VM(s), states that
    severance is a full copy and that the VM(s) must be stopped for the
    cutover phase, and shows the exact command that will run. The Sever button
    stays insensitive until the word "sever" is typed. Returns True when the
    user confirms, False when the dialog is cancelled.
    """
    lines, vmids = _sever_dialog_rows(items)
    vm_list, stopped_subject = _sever_vm_phrases(vmids)
    command = build_sever_clone_command(sever_clone_datasets(items))

    dialog, content = create_scrolled_dialog(
        "Sever Clone",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(640, 520),
    )
    sever_btn = dialog.add_button("Sever", _RESPONSE_SEVER)
    sever_btn.set_sensitive(False)

    header = Gtk.Label()
    header.set_markup(
        f"<b>About to sever {len(lines)} clone dataset(s) "
        f"({vm_list}) from their origin snapshots.</b>"
    )
    header.set_halign(Gtk.Align.START)
    content.pack_start(header, False, False, 0)
    content.pack_start(Gtk.Separator(), False, False, 0)

    add_scrolled_text_view(content, "\n\n".join(lines), min_height=120)

    detail = Gtk.Label()
    detail.set_markup(
        "Severance is a <b>full copy</b>: every used byte of each selected disk is "
        "read and written again, so it needs free space for the copy (in the same "
        "pool, or in an intermediate holding pool you name when space is tight).\n\n"
        f"<b>{stopped_subject} must be stopped for the cutover phase</b>, when the "
        "original zvol is destroyed and the fresh copy is swapped in under the same "
        "name — Proxmox configs and iSCSI references keep working because the name "
        "does not change.\n\n"
        "Unlike <tt>zfs promote</tt>, severance does not invert the clone "
        "relationship: the origin snapshot is released for destruction once no "
        "clone references it, and that is where its pinned space comes back.\n\n"
        "sever-vm-clone's remaining questions (transfer mode, holding pool, "
        "origin-snapshot destruction) appear as prompts in the log panel."
    )
    detail.set_halign(Gtk.Align.START)
    detail.set_line_wrap(True)
    content.pack_start(detail, False, False, 0)
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

    typed_hint = Gtk.Label(
        label=f"Type '{_SEVER_CONFIRM_WORD}' exactly to enable Sever. "
        "This copies and swaps live VM disk zvols."
    )
    typed_hint.set_halign(Gtk.Align.START)
    content.pack_start(typed_hint, False, False, 0)
    typed_entry = Gtk.Entry()
    typed_entry.set_hexpand(True)
    content.pack_start(typed_entry, False, False, 0)

    def _on_typed_changed(entry):
        sever_btn.set_sensitive(entry.get_text().strip().lower() == _SEVER_CONFIRM_WORD)

    typed_entry.connect("changed", _on_typed_changed)

    dialog.show_all()
    try:
        response = dialog.run()
        return (
            response == _RESPONSE_SEVER
            and typed_entry.get_text().strip().lower() == _SEVER_CONFIRM_WORD
        )
    finally:
        dialog.destroy()


def on_datasets_sever_clone(app):
    """Sever the selected clone zvols from their origin snapshots.

    Acts only on the selected clone dataset(s); the other disks of a VM are
    never touched. sever-vm-clone runs as a runner step so its prompts reach
    the operator through the numbered input-hold panel and its progress lands
    in the log panel.
    """
    items = get_tree_selection_items(app.datasets_view)
    datasets = sever_clone_datasets(items)
    if not datasets:
        log_msg("WARN: Select one or more clone datasets to sever")
        return

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    if not show_sever_clone_dialog(app, items):
        log_msg("INFO: Sever clone cancelled")
        return

    step = BashStep(
        build_sever_clone_command(datasets),
        f"Sever clone {datasets[0]}" if len(datasets) == 1 else f"Sever {len(datasets)} clones",
        is_rsync=False,
        fatal=True,
    )

    def _on_sever_complete(cancelled=False, rc=None):
        update_ds_button_sensitivity(app)
        refresh_datasets_page(app)
        if cancelled:
            log_msg(f"INFO: Sever clone cancelled ({len(datasets)} dataset(s))")
            return
        if rc:
            log_msg(
                f"WARN: Sever clone failed (rc={rc}); if a cutover was interrupted, "
                "run sever-vm-clone with the state file it printed to resume or roll back"
            )
            return
        log_msg(f"INFO: Sever clone complete for {len(datasets)} dataset(s)")

    runner.operation_detail = (
        f"Sever clone: {datasets[0]}"
        if len(datasets) == 1
        else f"Sever clone: {len(datasets)} datasets"
    )
    runner.set_steps([step])
    update_ds_button_sensitivity(app)
    runner.start(on_complete=_on_sever_complete)


# ---------------------------------------------------------------------------
# In-place mount-state refresh
# ---------------------------------------------------------------------------


def update_mounted_states(app):
    """Refresh the mounted flag and foreground color of every visible tree row.

    Unlike refresh_datasets_page, this does not clear the store or change
    expansion/selection; it only updates the columns that depend on mount
    state. This avoids the stale-row and selection-restoration issues that can
    occur after a mount or unmount operation.
    """
    repo = app.ctx.zfs_repository
    store = app.datasets_store
    mounted_snaps = get_mounted_snapshots()

    # Loop-attach state for volume rows, fetched once on first need.
    loop_attached = None

    def _volume_attached(full_name):
        nonlocal loop_attached
        if loop_attached is None:
            try:
                loop_attached = repo.loop_attached_paths()
            except (subprocess.CalledProcessError, FileNotFoundError):
                loop_attached = set()
        return zvol_device_path(full_name) in loop_attached

    def _walk(tree_iter):
        while tree_iter:
            name = store.get_value(tree_iter, 0)
            ds_type = store.get_value(tree_iter, 2)
            mounted = False

            parent_iter = store.iter_parent(tree_iter)
            if ds_type == "snapshot":
                if parent_iter is not None:
                    dataset = build_full_dataset_name(store, parent_iter)
                    snap_name = name.lstrip("@")
                    mounted = f"{dataset}@{snap_name}" in mounted_snaps
            elif parent_iter is not None and store.get_value(parent_iter, 2) == "volume":
                # Loop partition row: mounted means the partition is mounted.
                try:
                    mounted = repo.device_mountpoint(f"/dev/{name}") is not None
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass
            elif ds_type == "volume":
                # Volumes have no zfs "mounted" property; loop-attach state
                # decides, matching the Mount/Unmount button logic.
                mounted = _volume_attached(build_full_dataset_name(store, tree_iter))
            elif ds_type in ("filesystem", "pool"):
                full_name = build_full_dataset_name(store, tree_iter)
                try:
                    mounted = repo.get_property(full_name, "mounted") == "yes"
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

            fg_color = _row_fg_color(mounted, ds_type)
            store.set(tree_iter, 8, mounted, 9, fg_color)

            child = store.iter_children(tree_iter)
            if child:
                _walk(child)
            tree_iter = store.iter_next(tree_iter)

    root = store.get_iter_first()
    if root is not None:
        _walk(root)
    update_ds_button_sensitivity(app)


# ---------------------------------------------------------------------------
# Context menu
# ---------------------------------------------------------------------------


def _on_datasets_button_press(treeview, event, app):
    """Show a right-click context menu for the selected dataset tree item."""
    if event.button != 3:  # Right-click only
        return False

    path_info = treeview.get_path_at_pos(int(event.x), int(event.y))
    if path_info is None:
        return False
    tree_path, column, _cell_x, _cell_y = path_info

    selection = treeview.get_selection()
    if not selection.path_is_selected(tree_path):
        selection.unselect_all()
        selection.select_path(tree_path)
    treeview.set_cursor(tree_path, column, False)

    menu = Gtk.Menu()
    append_treeview_copy_items(menu, treeview, path_info, app=app, datasets_view=treeview)
    menu.append(Gtk.SeparatorMenuItem())
    details_item = Gtk.MenuItem(label="Send details to log")
    details_item.connect("activate", lambda _i: _send_selection_details_to_log(app))
    menu.append(details_item)

    menu.show_all()
    menu.popup_at_pointer(event)
    return True


def _send_selection_details_to_log(app):
    """Gather detailed metadata for the selected tree item and log it."""
    items = get_tree_selection_items(app.datasets_view)
    if not items:
        log_msg("WARN: Select an item to send details to log")
        return
    if len(items) > 1:
        log_msg("WARN: Send details to log requires a single selection")
        return

    item = items[0]
    item_type = item["type"]
    repo = app.ctx.zfs_repository

    if item_type == "hold":
        log_msg(
            f"INFO: Details for hold '{item['tag']}' on "
            f"{item['dataset']}@{item['snapshot']} (hold)\n"
            f"  tag: {item['tag']}\n"
            f"  snapshot: {item['dataset']}@{item['snapshot']}\n"
            f"  dataset: {item['dataset']}"
        )
        return

    if item_type == "snapshot":
        full_name = f"{item['dataset']}@{item['name']}"
    else:
        full_name = item["name"]

    try:
        props = repo.get_all_properties(full_name)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Error reading details for {full_name}: {e}")
        return

    display_type = "dataset" if item_type == "pool" else item_type
    lines = [f"INFO: Details for {full_name} ({display_type})"]
    for prop in sorted(props):
        lines.append(f"  {prop}: {props[prop]}")
    log_msg("\n".join(lines))
