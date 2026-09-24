"""Disks tab UI — disk inventory and pool topology.

The page content sits behind a view switcher (radio row) with Inventory and
Topology and Performance views. Slow block-device and ZFS calls run in a
background thread so the GTK main thread stays responsive.
"""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

import gi
import node_config

gi.require_version("Gtk", "3.0")

from disk_repository import DiskInfo, DiskRepository
from gi.repository import GLib, Gtk
from gui_helpers import (
    bold_label,
    configure_treeview_column,
    setup_row_scroll,
)
from logging_config import log_msg
from zfs_repository import TopologyNode, ZfsRepository

# Foreground color used to tint the rows in one pane that correlate with the
# current selection in the other: disks of the selected pool (or of the
# selected topology node) in the Disk Inventory, and the devices of the
# selected inventory disk in the Pool Topology.
POOL_MEMBER_HIGHLIGHT_FG = "#00797A"

# Minimum height of the Inventory and Topology view. Keeps the panes usable
# on short windows and drives the page-level vertical scrollbar instead of
# letting the view be squashed by its neighbors.
DISKS_TOPOLOGY_MIN_HEIGHT = 260

# Disk pane ListStore columns:
#   0 name, 1 by-id, 2 model, 3 serial, 4 size, 5 type,
#   6 logical_sector, 7 physical_sector, 8 transport, 9 pools, 10 smart_health,
#   11 health (SSD/NVMe wear %, HDD surface-test status), 12 highlight
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
    COL_D_HEALTH,
    COL_D_HIGHLIGHT,
) = range(13)

# Topology pane TreeStore columns:
#   0 name, 1 type, 2 state, 3 read, 4 write, 5 cksum, 6 ashift,
#   7 highlight
(
    COL_T_NAME,
    COL_T_TYPE,
    COL_T_STATE,
    COL_T_READ,
    COL_T_WRITE,
    COL_T_CKSUM,
    COL_T_ASHIFT,
    COL_T_HIGHLIGHT,
) = range(8)


@dataclass
class DiskInventoryData:
    """Snapshot returned by DiskInventoryCache."""

    disks: list[DiskInfo]
    topologies: dict[str, TopologyNode]


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
    page_box.set_margin_start(10)
    page_box.set_margin_end(10)
    page_box.set_margin_top(10)
    page_box.set_margin_bottom(10)

    # --- View switcher: radio row across the top of the page ---
    app._disks_view_radios = {}
    view_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    group = None
    for view_name, label_text in (
        ("inventory", "Inventory and Topology"),
        ("performance", "Performance"),
    ):
        if group is None:
            radio = Gtk.RadioButton(label=label_text)
            group = radio
        else:
            radio = Gtk.RadioButton.new_from_widget(group)
            radio.set_label(label_text)
        app._disks_view_radios[view_name] = radio
        radio.connect("toggled", _on_view_radio_toggled, view_name, app)
        view_row.pack_start(radio, False, False, 0)
    page_box.pack_start(view_row, False, False, 0)

    page_box.pack_start(Gtk.Separator(), False, False, 0)

    # --- Pool selector (drives the topology view) ---
    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    controls.set_halign(Gtk.Align.START)
    app._disks_pool_selector = Gtk.ComboBoxText()
    app._disks_pool_selector.connect("changed", _on_pool_selector_changed, app)
    controls.pack_start(app._disks_pool_selector, False, False, 0)

    hint = Gtk.Label(label="Select a pool for its vdev topology")
    hint.set_halign(Gtk.Align.START)
    controls.pack_start(hint, False, False, 0)
    page_box.pack_start(controls, False, False, 0)

    # --- View stack: one named child per view-switcher target ---
    app._disks_view_stack = Gtk.Stack()
    page_box.pack_start(app._disks_view_stack, True, True, 0)

    # --- View: Inventory and Topology ---
    inventory_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    # Minimum height keeps the panes usable on short windows and drives the
    # page-level vertical scrollbar instead of letting the view be squashed.
    inventory_box.set_size_request(-1, DISKS_TOPOLOGY_MIN_HEIGHT)
    app._disks_view_stack.add_named(inventory_box, "inventory")

    title = bold_label("Disk Inventory")
    inventory_box.pack_start(title, False, False, 0)

    desc = Gtk.Label(
        label="Physical block devices and partitions detected on this system "
        "and their pool membership."
    )
    desc.set_halign(Gtk.Align.START)
    desc.set_line_wrap(True)
    inventory_box.pack_start(desc, False, False, 0)

    inventory_box.pack_start(Gtk.Separator(), False, False, 0)

    app.disks_store = Gtk.ListStore(
        str, str, str, str, str, str, str, str, str, str, str, str, bool
    )
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
        (COL_D_HEALTH, "Wear/Test", 110),
    ]
    for col_idx, title_text, width in disk_cols:
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        col.set_cell_data_func(renderer, _disk_cell_highlight_func)
        configure_treeview_column(col, width=width)
        if col_idx == COL_D_HEALTH:
            # TreeViewColumn is not a Gtk.Widget, so the tooltip lives on
            # the header label instead of on the column itself.
            header = Gtk.Label(label=title_text)
            header.set_tooltip_text(
                "SSD/NVMe: wear percentage from SMART data. HDD: surface "
                "self-test status (percent and ETA while running, then "
                "Passed/Failed/Aborted/Canceled). Select an HDD and use "
                "Surface Test… to start one."
            )
            header.show_all()
            col.set_widget(header)
        app.disks_view.append_column(col)

    app.enable_treeview_copy(app.disks_view)

    disks_scrolled = Gtk.ScrolledWindow()
    disks_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    disks_scrolled.add(app.disks_view)
    setup_row_scroll(disks_scrolled, app.disks_view)
    inventory_box.pack_start(disks_scrolled, True, True, 0)

    inventory_box.pack_start(Gtk.Separator(), False, False, 0)

    topo_title = bold_label("Pool Topology")
    inventory_box.pack_start(topo_title, False, False, 0)

    app.disks_topology_store = Gtk.TreeStore(str, str, str, str, str, str, str, bool)
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
        (COL_T_ASHIFT, "Blocksize", 90),
    ]
    for col_idx, title_text, width in topo_cols:
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        col.set_cell_data_func(renderer, _topology_cell_highlight_func)
        configure_treeview_column(col, width=width)
        app.disks_topology_view.append_column(col)

    app.enable_treeview_copy(app.disks_topology_view)

    topo_scrolled = Gtk.ScrolledWindow()
    topo_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    topo_scrolled.add(app.disks_topology_view)
    setup_row_scroll(topo_scrolled, app.disks_topology_view)
    inventory_box.pack_start(topo_scrolled, True, True, 0)

    # --- View: Performance (placeholder for forthcoming monitoring sections) ---
    perf_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    app._disks_view_stack.add_named(perf_box, "performance")

    perf_title = bold_label("Performance")
    perf_box.pack_start(perf_title, False, False, 0)

    perf_box.pack_start(Gtk.Separator(), False, False, 0)

    perf_desc = Gtk.Label(
        label="Pool and device performance monitoring sections will appear "
        "here in a future release."
    )
    perf_desc.set_halign(Gtk.Align.START)
    perf_desc.set_line_wrap(True)
    perf_box.pack_start(perf_desc, False, False, 0)

    refresh_disks_page(app)

    # Wrap the page so the whole tab scrolls vertically on short windows
    # instead of squashing the stacked panes.
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.add(page_box)
    return scrolled


def _on_view_radio_toggled(radio, view_name, app):
    """Show the Disks page view selected in the view-switcher radio row."""
    if radio.get_active():
        app._disks_view_stack.set_visible_child_name(view_name)
        update_disks_button_sensitivity(app)


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

    from disk_surface_test import load_surface_test_state, surface_cell_text

    surface_state = load_surface_test_state()

    # Repopulate disk inventory
    app.disks_store.clear()
    for disk in data.disks:
        if disk.wear_percent is not None:
            health_text = f"{disk.wear_percent}%"
        else:
            # HDDs (and their partitions, via parent_path) show surface-test status.
            health_text = surface_cell_text(
                surface_state["tests"].get(disk.parent_path or disk.path)
            )
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
                health_text,
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

    # Repopulate topology for the selected pool
    _repopulate_topology_for_selected_pool(app)

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


def refresh_surface_test_status(app):
    """Poll running surface tests and update the inventory cells in place.

    Runs on a timer while the Disks tab is visible (and once on tab switch).
    Tests live in the drive firmware, so this also picks up tests started
    before a GUI restart and finalizes those that finished while it was down.
    """
    from datetime import datetime

    from disk_surface_test import (
        load_surface_test_state,
        save_surface_test_state,
        surface_cell_text,
        update_entries_from_polls,
    )

    store = getattr(app, "disks_store", None)
    if store is None:
        return
    state = load_surface_test_state()
    repo = app.ctx.disk_repository
    changed = update_entries_from_polls(state, repo.poll_self_test, datetime.now().astimezone())
    if changed:
        save_surface_test_state(state)
    it = store.get_iter_first()
    while it:
        path = store.get_value(it, COL_D_NAME)
        if path in state["tests"]:
            store.set_value(it, COL_D_HEALTH, surface_cell_text(state["tests"].get(path)))
        it = store.iter_next(it)


def on_disks_surface_test(app):
    """Surface Test action: start (fast/slow) or cancel a test on the selected HDD."""
    from disk_surface_test import (
        cancel_surface_test,
        load_surface_test_state,
        show_surface_test_dialog,
        start_surface_test,
    )

    selection = app.disks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if len(pathlist) != 1:
        return
    tree_iter = model.get_iter(pathlist[0])
    if model.get_value(tree_iter, COL_D_TYPE) != "HDD":
        return
    disk_path = model.get_value(tree_iter, COL_D_NAME)
    disk = SimpleNamespace(
        path=disk_path,
        model=model.get_value(tree_iter, COL_D_MODEL),
    )
    entry = load_surface_test_state()["tests"].get(disk_path)
    action = show_surface_test_dialog(app, disk, entry, app.ctx.disk_repository)
    if action in ("short", "long"):
        start_surface_test(app, disk, action)
    elif action == "abort":
        cancel_surface_test(app, disk_path)
    refresh_surface_test_status(app)


def _on_disk_selection_changed(selection, app):
    """When a disk/partition is selected, tint its devices in the topology.

    The pool selector still switches to the disk's pool, but the topology
    pane never selects a node: the devices residing on the selected disk are
    tinted teal instead (see _sync_topology_highlight_from_inventory).
    """
    if getattr(app, "_disks_syncing_selection", False):
        return
    model, pathlist = selection.get_selected_rows()
    if pathlist:
        tree_iter = model.get_iter(pathlist[0])
        pools_str = model.get_value(tree_iter, COL_D_POOLS)
        if pools_str:
            first_pool = pools_str.split(", ")[0]
            selector = app._disks_pool_selector
            if selector.get_active_text() != first_pool:
                _set_combo_active_text(selector, first_pool)
            _repopulate_topology_for_selected_pool(app)
    else:
        _clear_topology_highlights(app)
    update_disks_button_sensitivity(app)


def _on_topology_selection_changed(selection, app):
    """When a topology node is selected, highlight its devices in the inventory.

    A device node highlights that device, a vdev node highlights every device
    in the vdev, and the pool node highlights every device in the pool. An
    empty selection (or a node with no devices) restores the pool-wide
    highlight. The inventory selection is never modified; the correlation is
    teal foreground text only.
    """
    if getattr(app, "_disks_syncing_selection", False):
        return
    model, pathlist = selection.get_selected_rows()
    if pathlist:
        tree_iter = model.get_iter(pathlist[0])
        device_paths = _topology_subtree_device_paths(model, tree_iter)
        if device_paths:
            _highlight_topology_devices(app, device_paths)
        else:
            _highlight_pool_disks(app, app._disks_pool_selector.get_active_text())
    else:
        _highlight_pool_disks(app, app._disks_pool_selector.get_active_text())
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
        app.disks_topology_view.expand_all()
    _highlight_pool_disks(app, pool_name)
    _sync_topology_highlight_from_inventory(app)


_DISKS_VIEWS = ("inventory", "performance")


def _current_disks_view(app) -> str:
    """Return the visible Disks-page view ("inventory" when unknown/unset).

    Test fakes use a mocked stack whose get_visible_child_name() is not a
    real view name; those fall back to the default view so the sensitivity
    rules behave as they did before the view switcher existed.
    """
    stack = getattr(app, "_disks_view_stack", None)
    view = stack.get_visible_child_name() if stack is not None else None
    return view if view in _DISKS_VIEWS else "inventory"


def update_disks_button_sensitivity(app):
    """Enable action buttons based on the current view and selection."""
    selection = app.disks_view.get_selection()
    _model, pathlist = selection.get_selected_rows()
    single_selection = len(pathlist) == 1
    btn = getattr(app, "_disks_smart_details_btn", None)
    if btn:
        btn.set_sensitive(single_selection and _current_disks_view(app) == "inventory")

    runner_busy = bool(
        getattr(app, "dataset_runner", None) and getattr(app.dataset_runner, "running", False)
    )
    compute_host = node_config.is_two_node() and not node_config.is_storage_host()
    inventory_active = _current_disks_view(app) == "inventory"

    create_btn = getattr(app, "_disks_create_pool_btn", None)
    if create_btn:
        if not inventory_active:
            create_btn.set_sensitive(False)
            create_btn.set_tooltip_text(
                "Switch to the Inventory and Topology view to use this action"
            )
        elif compute_host:
            create_btn.set_sensitive(False)
            create_btn.set_tooltip_text("Pool creation is available only on the storage host")
        elif runner_busy:
            create_btn.set_sensitive(False)
            create_btn.set_tooltip_text("A dataset action is already running")
        else:
            create_btn.set_sensitive(True)
            create_btn.set_tooltip_text("")

    # Phase 4 pool-growth/maintenance buttons share the Create Pool gating:
    # view disable (taking precedence), then compute-host, then runner-busy.
    growth_attrs = (
        ("_disks_add_vdev_btn", "Pool growth is available only on the storage host"),
        ("_disks_attach_btn", "Pool growth is available only on the storage host"),
        ("_disks_add_infra_vdev_btn", "Pool growth is available only on the storage host"),
        ("_disks_migrate_pool_btn", "Pool migration is available only on the storage host"),
        ("_disks_replace_btn", "Pool maintenance is available only on the storage host"),
        ("_disks_detach_btn", "Pool maintenance is available only on the storage host"),
    )
    for attr, host_tooltip in growth_attrs:
        btn = getattr(app, attr, None)
        if btn is None:
            continue
        if not inventory_active:
            btn.set_sensitive(False)
            btn.set_tooltip_text("Switch to the Inventory and Topology view to use this action")
        elif compute_host:
            btn.set_sensitive(False)
            btn.set_tooltip_text(host_tooltip)
        elif runner_busy:
            btn.set_sensitive(False)
            btn.set_tooltip_text("A dataset action is already running")
        else:
            btn.set_sensitive(True)
            btn.set_tooltip_text("")

    surf_btn = getattr(app, "_disks_surface_test_btn", None)
    if surf_btn:
        selected_hdd = single_selection and _selected_disk_is_hdd(app)
        if not inventory_active:
            surf_btn.set_sensitive(False)
            surf_btn.set_tooltip_text(
                "Switch to the Inventory and Topology view to use this action"
            )
        elif compute_host:
            surf_btn.set_sensitive(False)
            surf_btn.set_tooltip_text("Surface tests run on the storage host")
        elif runner_busy:
            surf_btn.set_sensitive(False)
            surf_btn.set_tooltip_text("A dataset action is already running")
        else:
            surf_btn.set_sensitive(bool(selected_hdd))
            surf_btn.set_tooltip_text(
                "" if selected_hdd else "Select a single HDD to run a surface test"
            )


def _selected_disk_is_hdd(app) -> bool:
    """Return True when the Disk Inventory selection is exactly one HDD row."""
    selection = app.disks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if len(pathlist) != 1:
        return False
    try:
        tree_iter = model.get_iter(pathlist[0])
        return model.get_value(tree_iter, COL_D_TYPE) == "HDD"
    except (IndexError, ValueError):
        return False


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


def _topology_cell_highlight_func(column, renderer, model, tree_iter, data=None):
    """Tint the foreground text of topology devices residing on the selected disk."""
    highlighted = model.get_value(tree_iter, COL_T_HIGHLIGHT)
    if highlighted:
        renderer.set_property("foreground", POOL_MEMBER_HIGHLIGHT_FG)
    else:
        renderer.set_property("foreground", None)


def _topology_node_matches_disk(node_name: str, disk_path: str) -> bool:
    """Return True if topology node *node_name* is *disk_path* or resides on it.

    Mirrors _path_matches_any_device in the opposite direction: a whole-disk
    inventory row matches its own leaf and any partition leaf (``/dev/sda``
    matches ``/dev/sda1``; ``/dev/nvme0n1`` matches ``/dev/nvme0n1p1``), plus
    basename and realpath equality for by-id leaf names. Non-device node
    names (pool, vdev) never match.
    """
    if not isinstance(node_name, str) or not node_name.startswith("/dev/"):
        return False
    if node_name == disk_path or os.path.basename(node_name) == os.path.basename(disk_path):
        return True
    if node_name.startswith(disk_path):
        rest = node_name[len(disk_path) :]
        if rest.isdigit() or (rest.startswith("p") and rest[1:].isdigit()):
            return True
    try:
        return os.path.realpath(node_name) == os.path.realpath(disk_path)
    except OSError:
        return False


def _highlight_topology_nodes_for_disk(app, disk_path: str) -> None:
    """Set the teal highlight on every topology device residing on *disk_path*."""
    store = app.disks_topology_store

    def _walk(parent_iter):
        it = store.iter_children(parent_iter)
        while it:
            name = store.get_value(it, COL_T_NAME)
            store.set_value(it, COL_T_HIGHLIGHT, _topology_node_matches_disk(name, disk_path))
            _walk(it)
            it = store.iter_next(it)

    _walk(None)


def _clear_topology_highlights(app) -> None:
    """Clear the teal highlight on every topology row."""
    store = app.disks_topology_store

    def _walk(parent_iter):
        it = store.iter_children(parent_iter)
        while it:
            store.set_value(it, COL_T_HIGHLIGHT, False)
            _walk(it)
            it = store.iter_next(it)

    _walk(None)


def _sync_topology_highlight_from_inventory(app) -> None:
    """Tint the topology devices that reside on the selected inventory disk.

    Freshly repopulated topology rows are always untinted, so with no
    inventory selection there is nothing to do; an explicit clear is only
    needed when the disk selection is removed without repopulating (see
    _on_disk_selection_changed). The topology pane only ever shows teal
    text, never a selection of its own.
    """
    selection = app.disks_view.get_selection()
    rows = selection.get_selected_rows()
    if not isinstance(rows, tuple) or len(rows) != 2 or not rows[1]:
        return
    model, pathlist = rows
    tree_iter = model.get_iter(pathlist[0])
    disk_path = model.get_value(tree_iter, COL_D_NAME)
    if not isinstance(disk_path, str):
        return
    _highlight_topology_nodes_for_disk(app, disk_path)


def _topology_subtree_device_paths(model, tree_iter) -> set[str]:
    """Collect ``/dev/`` device paths from the topology subtree at *tree_iter*."""
    paths = set()
    name = model.get_value(tree_iter, COL_T_NAME)
    if isinstance(name, str) and name.startswith("/dev/"):
        paths.add(name)
    child = model.iter_children(tree_iter)
    while child is not None:
        paths.update(_topology_subtree_device_paths(model, child))
        child = model.iter_next(child)
    return paths


def _path_matches_any_device(row_path: str, device_paths: set[str]) -> bool:
    """Return True if inventory *row_path* is one of the topology *device_paths*.

    Matches exact paths, basenames, realpath-resolved paths (so a by-id
    topology leaf matches the kernel device node), and whole-disk prefixes —
    a whole-disk inventory row matches a partition leaf (``/dev/sda`` matches
    ``/dev/sda1``; ``/dev/nvme0n1`` matches ``/dev/nvme0n1p1``). The prefix
    remainder must be digits or ``p``+digits so ``/dev/sda`` does not match
    ``/dev/sdaa``.
    """
    if row_path in device_paths:
        return True
    row_base = os.path.basename(row_path)
    row_real = os.path.realpath(row_path)
    for dev in device_paths:
        if dev == row_path or os.path.basename(dev) == row_base:
            return True
        if dev.startswith(row_path):
            rest = dev[len(row_path) :]
            if rest.isdigit() or (rest.startswith("p") and rest[1:].isdigit()):
                return True
        try:
            if os.path.realpath(dev) == row_real:
                return True
        except OSError:
            pass
    return False


def _highlight_topology_devices(app, device_paths):
    """Highlight every inventory row that matches one of *device_paths*."""
    it = app.disks_store.get_iter_first()
    while it:
        path = app.disks_store.get_value(it, COL_D_NAME)
        app.disks_store.set_value(it, COL_D_HIGHLIGHT, _path_matches_any_device(path, device_paths))
        it = app.disks_store.iter_next(it)


def _populate_topology_store(store, parent_iter, node: TopologyNode) -> None:
    """Recursively append *node* and its children to *store*."""
    row = [
        node.name,
        node.vdev_type,
        node.state,
        str(node.read),
        str(node.write),
        str(node.cksum),
        f"{1 << node.ashift} bytes" if node.ashift is not None else "-",
        False,
    ]
    it = store.append(parent_iter, row)
    for child in node.children:
        _populate_topology_store(store, it, child)
