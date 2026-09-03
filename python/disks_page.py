"""Disks tab UI — disk inventory and pool topology.

Slow block-device and ZFS calls run in a background thread so the GTK main
thread stays responsive.
"""

import contextlib
import os
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import gi
import zfs_lock_manager as zlm

gi.require_version("Gtk", "3.0")

from command_builders import BashStep
from disk_repository import DiskInfo, DiskRepository
from feature_config import (
    delete_workload_profile,
    get_workload_profiles,
    reset_workload_profiles,
    save_workload_profiles,
)
from gi.repository import GLib, Gtk
from gui_helpers import (
    bold_label,
    configure_treeview_column,
    create_dialog,
    setup_row_scroll,
)
from logging_config import log_msg
from workload_profiles import (
    LIVE_PROPERTIES,
    ZFS_GET_PROPERTIES,
    build_apply_plan,
    build_zfs_set_commands,
    match_profile,
    profile_has_warning,
    warning_text,
)
from zfs_repository import TopologyNode, ZfsRepository

# Foreground color used to highlight every disk that belongs to the pool
# currently selected in the Pool Topology section.
POOL_MEMBER_HIGHLIGHT_FG = "#00797A"

# Disk pane ListStore columns:
#   0 name, 1 by-id, 2 model, 3 serial, 4 size, 5 type,
#   6 logical_sector, 7 physical_sector, 8 transport, 9 pools, 10 smart_health,
#   11 highlight
(
    COL_D_NAME,
    COL_D_BYID,
    COL_D_MODEL,
    COL_D_SERIAL,
    COL_D_SIZE,
    COL_D_TYPE,
    COL_D_LSEC,
    COL_D_PSEC,
    COL_D_TRANSPORT,
    COL_D_POOLS,
    COL_D_SMART,
    COL_D_HIGHLIGHT,
) = range(12)

# Topology pane TreeStore columns:
#   0 name, 1 type, 2 state, 3 read, 4 write, 5 cksum, 6 ashift
(
    COL_T_NAME,
    COL_T_TYPE,
    COL_T_STATE,
    COL_T_READ,
    COL_T_WRITE,
    COL_T_CKSUM,
    COL_T_ASHIFT,
) = range(7)

# Dataset tuning pane ListStore columns:
#   0 name, 1 type, 2 recordsize, 3 compression, 4 atime, 5 logbias,
#   6 sync, 7 primarycache, 8 special_small_blocks, 9 volblocksize,
#   10 profile_match
(
    COL_DS_NAME,
    COL_DS_TYPE,
    COL_DS_RECORDSIZE,
    COL_DS_COMPRESSION,
    COL_DS_ATIME,
    COL_DS_LOGBIAS,
    COL_DS_SYNC,
    COL_DS_PRIMARYCACHE,
    COL_DS_SPECIAL_SMALL_BLOCKS,
    COL_DS_VOLBLOCKSIZE,
    COL_DS_PROFILE_MATCH,
) = range(11)


@dataclass
class DiskInventoryData:
    """Snapshot returned by DiskInventoryCache."""

    disks: list[DiskInfo]
    topologies: dict[str, TopologyNode]


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


def _set_combo_active_text(combo: Gtk.ComboBoxText, text: str) -> bool:
    """Select the item whose text matches *text*.

    Returns True if the text was found and selected, False otherwise.
    """
    model = combo.get_model()
    for i, row in enumerate(model):
        if row[0] == text:
            combo.set_active(i)
            return True
    return False


class DiskInventoryCache:
    """Async TTL cache for disk inventory + pool topology.

    `lsblk`, `smartctl`, `zpool status`, and `zdb` can all be slow. This cache
    returns the last known result immediately and refreshes it in a daemon
    thread so the page never blocks on device scans.
    """

    def __init__(
        self,
        disk_repository: DiskRepository,
        zfs_repository: ZfsRepository,
        ttl_seconds: float = 30.0,
    ):
        self.disk_repository = disk_repository
        self.zfs_repository = zfs_repository
        self.ttl = ttl_seconds
        self._data = DiskInventoryData(disks=[], topologies={})
        self._last_update = 0.0
        self._lock = threading.Lock()
        self._refreshing = False

    def get(self, callback: Callable[[], None] | None = None) -> DiskInventoryData:
        """Return cached data immediately, refreshing in the background if stale."""
        with self._lock:
            now = time.monotonic()
            fresh = now - self._last_update < self.ttl
            if fresh and not self._refreshing:
                return self._data
            if not self._refreshing:
                self._refreshing = True
                thread = threading.Thread(target=self._refresh, args=(callback,), daemon=True)
                thread.start()
            return self._data

    def invalidate(self) -> None:
        """Force a fresh load on the next get() call."""
        with self._lock:
            self._last_update = 0.0

    def _refresh(self, callback: Callable[[], None] | None) -> None:
        try:
            data = self._load()
        except Exception as exc:  # pragma: no cover - defensive
            log_msg(f"WARN: Error refreshing disk inventory: {exc}")
            with self._lock:
                self._refreshing = False
            if callback is not None:
                callback()
            return

        with self._lock:
            self._data = data
            self._last_update = time.monotonic()
            self._refreshing = False
        if callback is not None:
            callback()

    def _load(self) -> DiskInventoryData:
        inventory = self.disk_repository.disk_inventory()
        disks = list(inventory.disks)

        try:
            pools = self.zfs_repository.list_pools_full()
        except Exception:
            pools = []

        topologies: dict[str, TopologyNode] = {}
        path_to_pools: dict[str, list[str]] = {}

        for pool_row in pools:
            pool_name = pool_row.get("name")
            if not pool_name:
                continue
            try:
                topology = self.zfs_repository.pool_topology(pool_name)
            except Exception:
                topology = None
            if topology is None:
                continue
            try:
                ashift_info = self.zfs_repository.get_ashift(pool_name)
            except Exception:
                ashift_info = None
            topology.ashift = ashift_info.effective if ashift_info else None
            topologies[pool_name] = topology
            self._collect_disk_paths(topology, pool_name, path_to_pools)

        for disk in disks:
            disk.pools = self._pools_for_disk(disk.path, path_to_pools)

        return DiskInventoryData(disks=disks, topologies=topologies)

    @staticmethod
    def _collect_disk_paths(
        node: TopologyNode,
        pool_name: str,
        path_to_pools: dict[str, list[str]],
    ) -> None:
        """Record leaf disk paths for pool membership lookups."""
        if node.vdev_type == "disk" and node.name:
            path_to_pools.setdefault(node.name, []).append(pool_name)
            try:
                real = os.path.realpath(node.name)
            except OSError:
                real = node.name
            if real != node.name:
                path_to_pools.setdefault(real, []).append(pool_name)
        for child in node.children:
            DiskInventoryCache._collect_disk_paths(child, pool_name, path_to_pools)

    @staticmethod
    def _pools_for_disk(
        path: str,
        path_to_pools: dict[str, list[str]],
    ) -> list[str]:
        """Return sorted pool names for *path* using realpath and basename fallback."""
        try:
            real = os.path.realpath(path)
        except OSError:
            real = path
        pools = set(path_to_pools.get(real, []))
        if not pools:
            base = os.path.basename(path)
            for disk_path, pool_names in path_to_pools.items():
                if os.path.basename(disk_path) == base:
                    pools.update(pool_names)
        return sorted(pools)


def create_disks_page(app):
    """Build and return the full Disks tab widget."""
    app._disks_inventory_cache = DiskInventoryCache(app.ctx.disk_repository, app.ctx.zfs_repository)
    app._disks_syncing_selection = False

    page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

    # --- Pane 1: disk inventory ---
    top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    top_box.set_margin_start(10)
    top_box.set_margin_end(10)
    top_box.set_margin_top(10)
    top_box.set_margin_bottom(10)

    title = bold_label("Disk Inventory")
    top_box.pack_start(title, False, False, 0)

    desc = Gtk.Label(
        label="Physical block devices and partitions detected on this system and their pool membership."
    )
    desc.set_halign(Gtk.Align.START)
    desc.set_line_wrap(True)
    top_box.pack_start(desc, False, False, 0)

    top_box.pack_start(Gtk.Separator(), False, False, 0)

    app.disks_store = Gtk.ListStore(str, str, str, str, str, str, str, str, str, str, str, bool)
    app.disks_view = Gtk.TreeView(model=app.disks_store)
    app.disks_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.disks_view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
    app.disks_view.get_selection().connect("changed", _on_disk_selection_changed, app)

    disk_cols = [
        (COL_D_NAME, "Name", 160),
        (COL_D_BYID, "by-id", 160),
        (COL_D_MODEL, "Model", 130),
        (COL_D_SERIAL, "Serial", 130),
        (COL_D_SIZE, "Size", 70),
        (COL_D_TYPE, "Type", 60),
        (COL_D_LSEC, "Log-sec", 60),
        (COL_D_PSEC, "Phy-sec", 60),
        (COL_D_TRANSPORT, "Transport", 80),
        (COL_D_POOLS, "Pools", 100),
        (COL_D_SMART, "SMART", 60),
    ]
    for col_idx, title_text, width in disk_cols:
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        col.set_cell_data_func(renderer, _disk_cell_highlight_func)
        configure_treeview_column(col, width=width)
        app.disks_view.append_column(col)

    app.enable_treeview_copy(app.disks_view)

    disks_scrolled = Gtk.ScrolledWindow()
    disks_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    disks_scrolled.add(app.disks_view)
    setup_row_scroll(disks_scrolled, app.disks_view)
    top_box.pack_start(disks_scrolled, True, True, 0)

    page_box.pack_start(top_box, True, True, 0)

    # --- Pane 2: pool topology ---
    mid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    mid_box.set_margin_start(10)
    mid_box.set_margin_end(10)
    mid_box.set_margin_top(10)
    mid_box.set_margin_bottom(10)

    topo_title = bold_label("Pool Topology")
    mid_box.pack_start(topo_title, False, False, 0)

    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    controls.set_halign(Gtk.Align.START)
    app._disks_pool_selector = Gtk.ComboBoxText()
    app._disks_pool_selector.connect("changed", _on_pool_selector_changed, app)
    controls.pack_start(app._disks_pool_selector, False, False, 0)

    hint = Gtk.Label(label="Select a pool to view its vdev topology and dataset tuning")
    hint.set_halign(Gtk.Align.START)
    controls.pack_start(hint, False, False, 0)
    mid_box.pack_start(controls, False, False, 0)

    app.disks_topology_store = Gtk.TreeStore(str, str, str, str, str, str, str)
    app.disks_topology_view = Gtk.TreeView(model=app.disks_topology_store)
    app.disks_topology_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.disks_topology_view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
    app.disks_topology_view.get_selection().connect("changed", _on_topology_selection_changed, app)

    topo_cols = [
        (COL_T_NAME, "Name", 250),
        (COL_T_TYPE, "Type", 80),
        (COL_T_STATE, "State", 80),
        (COL_T_READ, "Read", 60),
        (COL_T_WRITE, "Write", 60),
        (COL_T_CKSUM, "Cksum", 60),
        (COL_T_ASHIFT, "Ashift", 60),
    ]
    for col_idx, title_text, width in topo_cols:
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        configure_treeview_column(col, width=width)
        app.disks_topology_view.append_column(col)

    app.enable_treeview_copy(app.disks_topology_view)

    topo_scrolled = Gtk.ScrolledWindow()
    topo_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    topo_scrolled.add(app.disks_topology_view)
    setup_row_scroll(topo_scrolled, app.disks_topology_view)
    mid_box.pack_start(topo_scrolled, True, True, 0)

    page_box.pack_start(mid_box, True, True, 0)

    # --- Pane 3: dataset tuning ---
    bottom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    bottom_box.set_margin_start(10)
    bottom_box.set_margin_end(10)
    bottom_box.set_margin_top(10)
    bottom_box.set_margin_bottom(10)

    ds_title = bold_label("Dataset Tuning")
    bottom_box.pack_start(ds_title, False, False, 0)

    ds_desc = Gtk.Label(
        label="Read-only view of dataset properties. Select one or more datasets and use Apply Profile to tune live properties."
    )
    ds_desc.set_halign(Gtk.Align.START)
    ds_desc.set_line_wrap(True)
    bottom_box.pack_start(ds_desc, False, False, 0)

    bottom_box.pack_start(Gtk.Separator(), False, False, 0)

    app.disks_dataset_store = Gtk.ListStore(str, str, str, str, str, str, str, str, str, str, str)
    app.disks_dataset_view = Gtk.TreeView(model=app.disks_dataset_store)
    app.disks_dataset_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.disks_dataset_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
    app.disks_dataset_view.get_selection().connect("changed", _on_dataset_selection_changed, app)

    ds_cols = [
        (COL_DS_NAME, "Name", 250),
        (COL_DS_TYPE, "Type", 80),
        (COL_DS_RECORDSIZE, "Recordsize", 90),
        (COL_DS_COMPRESSION, "Compression", 100),
        (COL_DS_ATIME, "Atime", 60),
        (COL_DS_LOGBIAS, "Logbias", 80),
        (COL_DS_SYNC, "Sync", 80),
        (COL_DS_PRIMARYCACHE, "Primarycache", 100),
        (COL_DS_SPECIAL_SMALL_BLOCKS, "Special small blocks", 130),
        (COL_DS_VOLBLOCKSIZE, "Volblocksize", 100),
        (COL_DS_PROFILE_MATCH, "Profile match", 130),
    ]
    for col_idx, title_text, width in ds_cols:
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        configure_treeview_column(col, width=width)
        app.disks_dataset_view.append_column(col)

    app.enable_treeview_copy(app.disks_dataset_view)

    ds_scrolled = Gtk.ScrolledWindow()
    ds_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    ds_scrolled.add(app.disks_dataset_view)
    setup_row_scroll(ds_scrolled, app.disks_dataset_view)
    bottom_box.pack_start(ds_scrolled, True, True, 0)

    app._disks_rewrite_guidance_label = Gtk.Label(
        label=(
            "Rewrite Data requires OpenZFS 2.3+. On older versions, rewrite existing data "
            "by creating a new dataset with the desired profile and using send/receive."
        )
    )
    app._disks_rewrite_guidance_label.set_halign(Gtk.Align.START)
    app._disks_rewrite_guidance_label.set_line_wrap(True)
    app._disks_rewrite_guidance_label.set_no_show_all(True)
    if not app.ctx.zfs_caps.supports("zfs_rewrite"):
        app._disks_rewrite_guidance_label.show()
    bottom_box.pack_start(app._disks_rewrite_guidance_label, False, False, 0)

    page_box.pack_start(bottom_box, True, True, 0)

    refresh_disks_page(app)

    return page_box


def _make_disks_refresh_callback(app):
    """Return a cache callback that refreshes the page only when it is visible."""

    def _callback():
        GLib.idle_add(_refresh_disks_page_if_visible, app)

    return _callback


def _refresh_disks_page_if_visible(app):
    """Refresh the Disks tab if it is the currently visible stack child."""
    if getattr(app.stack, "get_visible_child_name", lambda: None)() == "disks":
        refresh_disks_page(app)
    return False


def refresh_disks_page(app):
    """Clear and repopulate the disk inventory, topology, and dataset views."""
    disks_view = app.disks_view
    selector = app._disks_pool_selector

    # Remember current selection
    selection = disks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    selected_path = None
    if pathlist:
        tree_iter = model.get_iter(pathlist[0])
        selected_path = model.get_value(tree_iter, COL_D_NAME)

    selected_pool = selector.get_active_text()

    data = app._disks_inventory_cache.get(callback=_make_disks_refresh_callback(app))

    # Repopulate disk inventory
    app.disks_store.clear()
    for disk in data.disks:
        app.disks_store.append(
            [
                disk.path,
                disk.by_id,
                disk.model,
                disk.serial,
                disk.size_human,
                disk.disk_type,
                str(disk.logical_sector) if disk.logical_sector is not None else "-",
                str(disk.physical_sector) if disk.physical_sector is not None else "-",
                disk.transport,
                ", ".join(disk.pools),
                disk.smart_health,
                False,
            ]
        )

    # Rebuild pool selector
    pool_names = sorted(data.topologies.keys())
    selector.remove_all()
    for pool_name in pool_names:
        selector.append_text(pool_name)
    if selected_pool in pool_names:
        _set_combo_active_text(selector, selected_pool)
    elif pool_names:
        selector.set_active(0)

    # Repopulate topology and dataset views for selected pool
    _repopulate_topology_for_selected_pool(app)
    _repopulate_dataset_tuning_for_selected_pool(app)

    # Highlight every disk that belongs to the selected pool
    _highlight_pool_disks(app, selector.get_active_text())

    # Restore disk selection
    if selected_path:
        it = app.disks_store.get_iter_first()
        while it:
            if app.disks_store.get_value(it, COL_D_NAME) == selected_path:
                path = app.disks_store.get_path(it)
                disks_view.get_selection().select_path(path)
                break
            it = app.disks_store.iter_next(it)

    update_disks_button_sensitivity(app)


def on_disks_refresh(app):
    """Invalidate the disk inventory cache and refresh the page."""
    app._disks_inventory_cache.invalidate()
    refresh_disks_page(app)
    log_msg("VERB: Disks refreshed")


def _on_disk_selection_changed(selection, app):
    """When a disk/partition is selected, select its pool and node in topology."""
    if getattr(app, "_disks_syncing_selection", False):
        return
    model, pathlist = selection.get_selected_rows()
    if pathlist:
        tree_iter = model.get_iter(pathlist[0])
        pools_str = model.get_value(tree_iter, COL_D_POOLS)
        selected_path = model.get_value(tree_iter, COL_D_NAME)
        if pools_str:
            first_pool = pools_str.split(", ")[0]
            selector = app._disks_pool_selector
            if selector.get_active_text() != first_pool:
                _set_combo_active_text(selector, first_pool)
            _repopulate_topology_for_selected_pool(app)
            _select_topology_node_by_name(app, selected_path)
    update_disks_button_sensitivity(app)


@contextlib.contextmanager
def _suppress_selection_sync(app):
    """Prevent recursive selection synchronization between the two panes."""
    app._disks_syncing_selection = True
    try:
        yield
    finally:
        app._disks_syncing_selection = False


def _select_disk_row_by_path(app, path: str) -> bool:
    """Select the inventory row whose device path matches *path*."""
    store = app.disks_store
    it = store.get_iter_first()
    while it:
        if store.get_value(it, COL_D_NAME) == path:
            tree_path = store.get_path(it)
            with _suppress_selection_sync(app):
                app.disks_view.get_selection().select_path(tree_path)
                app.disks_view.scroll_to_cell(tree_path, None, False, 0, 0)
            return True
        it = store.iter_next(it)
    return False


def _select_topology_node_by_name(app, name: str) -> bool:
    """Select the topology node whose COL_T_NAME matches *name*."""
    store = app.disks_topology_store

    def _find(parent_iter):
        it = store.iter_children(parent_iter)
        while it:
            if store.get_value(it, COL_T_NAME) == name:
                return it
            found = _find(it)
            if found is not None:
                return found
            it = store.iter_next(it)
        return None

    it = _find(None)
    if it is None:
        return False
    tree_path = store.get_path(it)
    with _suppress_selection_sync(app):
        app.disks_topology_view.get_selection().select_path(tree_path)
        app.disks_topology_view.scroll_to_cell(tree_path, None, False, 0, 0)
    return True


def _on_topology_selection_changed(selection, app):
    """When a topology device node is selected, highlight it in the inventory."""
    if getattr(app, "_disks_syncing_selection", False):
        return
    model, pathlist = selection.get_selected_rows()
    if pathlist:
        tree_iter = model.get_iter(pathlist[0])
        node_name = model.get_value(tree_iter, COL_T_NAME)
        if node_name and node_name.startswith("/dev/"):
            _select_disk_row_by_path(app, node_name)
    update_disks_button_sensitivity(app)


def _on_pool_selector_changed(selector, app):
    """Refresh the topology and dataset views when the pool selector changes."""
    _repopulate_topology_for_selected_pool(app)
    _repopulate_dataset_tuning_for_selected_pool(app)


def _repopulate_topology_for_selected_pool(app):
    """Clear and refill the topology store for the currently selected pool."""
    app.disks_topology_store.clear()
    data = app._disks_inventory_cache.get()
    pool_name = app._disks_pool_selector.get_active_text()
    if pool_name and pool_name in data.topologies:
        _populate_topology_store(app.disks_topology_store, None, data.topologies[pool_name])
    _highlight_pool_disks(app, pool_name)


def _load_dataset_tuning(app, pool_name):
    """Populate the dataset tuning store for *pool_name*."""
    store = app.disks_dataset_store
    repo = app.ctx.zfs_repository
    profiles = get_workload_profiles(app.config)
    try:
        datasets = repo.list_datasets(pool_name)
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not list datasets for {pool_name}: {exc}")
        return

    for row in datasets:
        # Skip snapshots/bookmarks if any appear in the listing.
        if row.ds_type not in ("filesystem", "volume"):
            continue
        try:
            props = repo.get_properties(row.name, list(ZFS_GET_PROPERTIES))
        except Exception as exc:  # pragma: no cover - defensive
            log_msg(
                f"WARN: Could not read properties for {row.name}: "
                f"{_user_friendly_property_error(row.name, exc)}"
            )
            continue

        profile_match = match_profile(profiles, row.ds_type, props)
        store.append(
            [
                row.name,
                row.ds_type,
                props.get("recordsize", "-"),
                props.get("compression", "-"),
                props.get("atime", "-"),
                props.get("logbias", "-"),
                props.get("sync", "-"),
                props.get("primarycache", "-"),
                props.get("special_small_blocks", "-"),
                props.get("volblocksize", "-"),
                profile_match,
            ]
        )


def _repopulate_dataset_tuning_for_selected_pool(app):
    """Clear and refill the dataset tuning store for the currently selected pool."""
    app.disks_dataset_store.clear()
    pool_name = app._disks_pool_selector.get_active_text()
    if pool_name:
        _load_dataset_tuning(app, pool_name)


def _on_dataset_selection_changed(selection, app):
    """Update action button sensitivity when dataset selection changes."""
    update_disks_button_sensitivity(app)


def _pool_has_special_vdev(topology: TopologyNode | None) -> bool:
    """Return True if the topology tree contains a 'special' vdev node."""
    if topology is None:
        return False
    if topology.vdev_type == "special":
        return True
    return any(_pool_has_special_vdev(child) for child in topology.children)


def _selected_dataset_rows(app):
    """Return a list of dataset store rows for the current dataset selection."""
    selection = app.disks_dataset_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    rows = []
    for path in pathlist:
        tree_iter = model.get_iter(path)
        rows.append(
            {
                "name": model.get_value(tree_iter, COL_DS_NAME),
                "type": model.get_value(tree_iter, COL_DS_TYPE),
            }
        )
    return rows


def update_disks_button_sensitivity(app):
    """Enable action buttons based on the current disk/dataset selection."""
    selection = app.disks_view.get_selection()
    _model, pathlist = selection.get_selected_rows()
    single_selection = len(pathlist) == 1
    btn = getattr(app, "_disks_smart_details_btn", None)
    if btn:
        btn.set_sensitive(single_selection)

    dataset_view = getattr(app, "disks_dataset_view", None)
    if dataset_view is not None:
        ds_selection = dataset_view.get_selection()
        _model, ds_pathlist = ds_selection.get_selected_rows()
        ds_count = len(ds_pathlist)
    else:
        ds_count = 0

    apply_btn = getattr(app, "_disks_apply_profile_btn", None)
    if apply_btn:
        runner_busy = bool(app.dataset_runner and getattr(app.dataset_runner, "running", False))
        apply_btn.set_sensitive(ds_count > 0 and not runner_busy)

    rewrite_btn = getattr(app, "_disks_rewrite_data_btn", None)
    if rewrite_btn:
        caps = app.ctx.zfs_caps
        can_rewrite = ds_count == 1 and caps.supports("zfs_rewrite")
        rewrite_btn.set_sensitive(can_rewrite)
        if not can_rewrite:
            rewrite_btn.set_tooltip_text(caps.requires("zfs_rewrite"))
        else:
            rewrite_btn.set_tooltip_text("")

    manage_btn = getattr(app, "_disks_manage_profiles_btn", None)
    if manage_btn:
        manage_btn.set_sensitive(True)


def _highlight_pool_disks(app, pool_name):
    """Set the highlight flag on every disk row that belongs to *pool_name*.

    Passing *pool_name* as ``None`` or a pool not present in the cached data
    clears all highlights.
    """
    data = app._disks_inventory_cache.get()
    if pool_name:
        pool_member_paths = {disk.path for disk in data.disks if pool_name in disk.pools}
    else:
        pool_member_paths = set()

    it = app.disks_store.get_iter_first()
    while it:
        path = app.disks_store.get_value(it, COL_D_NAME)
        app.disks_store.set_value(it, COL_D_HIGHLIGHT, path in pool_member_paths)
        it = app.disks_store.iter_next(it)


def _disk_cell_highlight_func(column, renderer, model, tree_iter, data=None):
    """Tint the foreground text of disk rows that belong to the selected pool."""
    highlighted = model.get_value(tree_iter, COL_D_HIGHLIGHT)
    if highlighted:
        renderer.set_property("foreground", POOL_MEMBER_HIGHLIGHT_FG)
    else:
        renderer.set_property("foreground", None)


def _populate_topology_store(store, parent_iter, node: TopologyNode) -> None:
    """Recursively append *node* and its children to *store*."""
    row = [
        node.name,
        node.vdev_type,
        node.state,
        str(node.read),
        str(node.write),
        str(node.cksum),
        str(node.ashift) if node.ashift is not None else "-",
    ]
    it = store.append(parent_iter, row)
    for child in node.children:
        _populate_topology_store(store, it, child)


# ---------------------------------------------------------------------------
# Rewrite Data action
# ---------------------------------------------------------------------------


def on_disks_rewrite_data(app):
    """Rewrite data on a single dataset using ``zfs rewrite``.

    Requires exactly one selected dataset, OpenZFS 2.3+, and a running
    dataset_runner. Acquires a single write lock, runs one BashStep, and
    refreshes the page on completion.
    """
    datasets = _selected_dataset_rows(app)
    if len(datasets) != 1:
        log_msg("WARN: Select exactly one dataset to rewrite data")
        return

    ds = datasets[0]
    ds_name = ds["name"]
    ds_type = ds["type"]
    if ds_type not in ("filesystem", "volume"):
        log_msg(f"WARN: Cannot rewrite data for dataset type {ds_type}")
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

    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Rewrite data on {ds_name}?",
    )
    dialog.format_secondary_text(
        "zfs rewrite rewrites existing blocks in place so they match the current "
        "dataset properties. This may take a long time and cannot be undone."
    )
    response = dialog.run()
    dialog.destroy()
    if response != Gtk.ResponseType.YES:
        return

    lock_id = zlm.acquire(ds_name, "w", f"Rewrite data on {ds_name}")

    step = BashStep(
        ["bash", "-c", f"zfs rewrite {shlex.quote(ds_name)}"],
        f"Rewrite data on {ds_name}",
        is_rsync=False,
        fatal=False,
    )

    def _on_complete(cancelled=False):
        zlm.release(lock_id)
        if cancelled:
            log_msg(f"INFO: Rewrite Data cancelled for {ds_name}")
        else:
            log_msg(f"INFO: Rewrite Data complete for {ds_name}")
        update_disks_button_sensitivity(app)
        refresh_disks_page(app)

    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)


# ---------------------------------------------------------------------------
# Workload profile management dialog
# ---------------------------------------------------------------------------


def on_disks_manage_profiles(app):
    """Open the workload profile manager."""
    show_manage_profiles_dialog(app)


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

    store = Gtk.ListStore(str, str, str)
    view = Gtk.TreeView(model=store)
    view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

    cols = [
        (0, "Name", 180),
        (1, "Applies to", 120),
        (2, "Description", 350),
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
                ]
            )

    def _selected_name():
        selection = view.get_selection()
        model, pathlist = selection.get_selected_rows()
        if not pathlist:
            return None
        tree_iter = model.get_iter(pathlist[0])
        return model.get_value(tree_iter, 0)

    def _on_add(_btn):
        show_profile_editor_dialog(app)
        _refresh_list()

    def _on_edit(_btn):
        name = _selected_name()
        if name is None:
            log_msg("WARN: Select a profile to edit")
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

    _refresh_list()
    dialog.show_all()
    dialog.run()
    dialog.destroy()


def show_profile_editor_dialog(app, name=None):
    """Show the Add/Edit Workload Profile dialog and persist on OK.

    When *name* is None a new profile is created. When *name* is provided the
    existing profile is edited (the name field is read-only).
    """
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
    ashift_entry.set_placeholder_text("informational only, e.g. 12")
    ashift_entry.set_editable(False)
    ashift_entry.set_can_focus(False)
    _add_row(row, "ashift (informational):", ashift_entry)
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
    err = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    err.run()
    err.destroy()


# ---------------------------------------------------------------------------
# Apply Profile dialog and execution
# ---------------------------------------------------------------------------


def show_apply_profile_dialog(app, datasets):
    """Show the Apply Profile dialog and return (response, profile_name, profile)."""
    profiles = get_workload_profiles(app.config)
    profile_names = list(profiles.keys())
    if not profile_names:
        log_msg("WARN: No workload profiles configured")
        return Gtk.ResponseType.CANCEL, None, None

    pool_name = app._disks_pool_selector.get_active_text()
    topology = app._disks_inventory_cache.get().topologies.get(pool_name)
    pool_has_special = _pool_has_special_vdev(topology)

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

    selector_label = Gtk.Label(label="Profile:")
    selector_label.set_halign(Gtk.Align.START)
    content.pack_start(selector_label, False, False, 0)

    selector = Gtk.ComboBoxText()
    for name in profile_names:
        selector.append_text(name)
    _set_combo_active_text(selector, default_name)
    content.pack_start(selector, False, False, 0)

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

    def _get_active_profile_name():
        # Gtk.ComboBoxText.get_active_text() returns the active text in real GTK.
        # Some test mocks return a MagicMock instead of the string set by
        # set_active_text(); fall back to the tracked value in that case.
        raw = selector.get_active_text()
        if isinstance(raw, str):
            return raw
        return current_name

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

    selector.connect("changed", lambda *_args: _update_preview())
    _update_preview()

    dialog.show_all()
    while True:
        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return Gtk.ResponseType.CANCEL, None, None
        name = selector.get_active_text()
        profile = profiles.get(name, {})
        if profile_has_warning(name, profile, pool_has_special) and not confirm_check.get_active():
            continue
        dialog.destroy()
        return Gtk.ResponseType.OK, name, profile


def on_disks_apply_profile(app):
    """Apply the selected workload profile to the selected datasets."""
    datasets = _selected_dataset_rows(app)
    if not datasets:
        log_msg("WARN: Select at least one dataset to apply a profile")
        return

    # Attach profile-match display to each selected row.
    selection = app.disks_dataset_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    for idx, path in enumerate(pathlist):
        tree_iter = model.get_iter(path)
        datasets[idx]["profile_match"] = model.get_value(tree_iter, COL_DS_PROFILE_MATCH)

    response, _profile_name, profile = show_apply_profile_dialog(app, datasets)
    if response != Gtk.ResponseType.OK:
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
    ds_commands: list[tuple[str, str, list[str]]] = []
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
        commands = build_zfs_set_commands(plan)
        if commands:
            all_commands.extend(commands)
            ds_commands.append((ds_name, ds_type, commands))

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
    for ds_name, _ds_type, commands in ds_commands:
        for cmd in commands:
            # cmd is of the form "zfs set <prop>=<value> <dataset>"
            desc = f"Set {cmd.split(' ', 3)[2]} on {ds_name}"
            steps.append(
                BashStep(
                    ["bash", "-c", cmd],
                    desc,
                    is_rsync=False,
                    fatal=False,
                )
            )

    def _on_complete(cancelled=False):
        for lock_id in lock_ids:
            zlm.release(lock_id)
        if cancelled:
            log_msg("INFO: Apply Profile cancelled")
        elif all_commands:
            log_msg(f"INFO: Apply Profile complete: {len(all_commands)} command(s)")
        update_disks_button_sensitivity(app)
        refresh_disks_page(app)

    runner.set_steps(steps)
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)
