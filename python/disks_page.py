"""Disks tab UI — disk inventory and pool topology.

Slow block-device and ZFS calls run in a background thread so the GTK main
thread stays responsive.
"""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "3.0")
from disk_repository import DiskInfo, DiskRepository
from gi.repository import GLib, Gtk
from gui_helpers import bold_label, configure_treeview_column, setup_row_scroll
from logging_config import log_msg
from zfs_repository import TopologyNode, ZfsRepository

# Disk pane ListStore columns:
#   0 name, 1 by-id, 2 model, 3 serial, 4 size, 5 type,
#   6 logical_sector, 7 physical_sector, 8 transport, 9 pools, 10 smart_health
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
) = range(11)

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


@dataclass
class DiskInventoryData:
    """Snapshot returned by DiskInventoryCache."""

    disks: list[DiskInfo]
    topologies: dict[str, TopologyNode]


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

    paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)

    # --- Upper pane: disk inventory ---
    top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    top_box.set_margin_start(10)
    top_box.set_margin_end(10)
    top_box.set_margin_top(10)
    top_box.set_margin_bottom(10)

    title = bold_label("Disk Inventory")
    top_box.pack_start(title, False, False, 0)

    desc = Gtk.Label(
        label="Physical block devices detected on this system and their pool membership."
    )
    desc.set_halign(Gtk.Align.START)
    desc.set_line_wrap(True)
    top_box.pack_start(desc, False, False, 0)

    top_box.pack_start(Gtk.Separator(), False, False, 0)

    app.disks_store = Gtk.ListStore(str, str, str, str, str, str, str, str, str, str, str)
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
        configure_treeview_column(col, width=width)
        app.disks_view.append_column(col)

    app.enable_treeview_copy(app.disks_view)

    disks_scrolled = Gtk.ScrolledWindow()
    disks_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    disks_scrolled.add(app.disks_view)
    setup_row_scroll(disks_scrolled, app.disks_view)
    top_box.pack_start(disks_scrolled, True, True, 0)

    paned.pack1(top_box, True, False)

    # --- Lower pane: pool topology ---
    bottom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    bottom_box.set_margin_start(10)
    bottom_box.set_margin_end(10)
    bottom_box.set_margin_top(10)
    bottom_box.set_margin_bottom(10)

    topo_title = bold_label("Pool Topology")
    bottom_box.pack_start(topo_title, False, False, 0)

    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    controls.set_halign(Gtk.Align.START)
    app._disks_pool_selector = Gtk.ComboBoxText()
    app._disks_pool_selector.connect("changed", _on_pool_selector_changed, app)
    controls.pack_start(app._disks_pool_selector, False, False, 0)

    hint = Gtk.Label(label="Select a pool to view its vdev topology")
    hint.set_halign(Gtk.Align.START)
    controls.pack_start(hint, False, False, 0)
    bottom_box.pack_start(controls, False, False, 0)

    app.disks_topology_store = Gtk.TreeStore(str, str, str, str, str, str, str)
    app.disks_topology_view = Gtk.TreeView(model=app.disks_topology_store)
    app.disks_topology_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

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
    bottom_box.pack_start(topo_scrolled, True, True, 0)

    paned.pack2(bottom_box, True, False)

    refresh_disks_page(app)

    return paned


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
    """Clear and repopulate the disk inventory and topology views."""
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
            ]
        )

    # Rebuild pool selector
    pool_names = sorted(data.topologies.keys())
    selector.remove_all()
    for pool_name in pool_names:
        selector.append_text(pool_name)
    if selected_pool in pool_names:
        selector.set_active_text(selected_pool)
    elif pool_names:
        selector.set_active(0)

    # Repopulate topology for selected pool
    app.disks_topology_store.clear()
    active_pool = selector.get_active_text()
    if active_pool and active_pool in data.topologies:
        _populate_topology_store(app.disks_topology_store, None, data.topologies[active_pool])

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
    """When a disk is selected, jump to its first pool in the topology view."""
    model, pathlist = selection.get_selected_rows()
    if pathlist:
        tree_iter = model.get_iter(pathlist[0])
        pools_str = model.get_value(tree_iter, COL_D_POOLS)
        if pools_str:
            first_pool = pools_str.split(", ")[0]
            selector = app._disks_pool_selector
            if selector.get_active_text() != first_pool:
                selector.set_active_text(first_pool)
            _repopulate_topology_for_selected_pool(app)
    update_disks_button_sensitivity(app)


def _on_pool_selector_changed(selector, app):
    """Refresh the topology view when the pool selector changes."""
    _repopulate_topology_for_selected_pool(app)


def _repopulate_topology_for_selected_pool(app):
    """Clear and refill the topology store for the currently selected pool."""
    app.disks_topology_store.clear()
    data = app._disks_inventory_cache.get()
    pool_name = app._disks_pool_selector.get_active_text()
    if pool_name and pool_name in data.topologies:
        _populate_topology_store(app.disks_topology_store, None, data.topologies[pool_name])


def update_disks_button_sensitivity(app):
    """Enable action buttons based on the current disk selection."""
    selection = app.disks_view.get_selection()
    _model, pathlist = selection.get_selected_rows()
    single_selection = len(pathlist) == 1
    btn = getattr(app, "_disks_smart_details_btn", None)
    if btn:
        btn.set_sensitive(single_selection)


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
