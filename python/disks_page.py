"""Disks tab UI — disk inventory and pool topology.

Slow block-device and ZFS calls run in a background thread so the GTK
main thread stays responsive.
"""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace

import gi
import node_config

gi.require_version("Gtk", "3.0")

from disk_repository import DiskInfo, DiskRepository
from enclosure_inventory import EnclosureInfo, EnclosureInventory
from feature_config import get_enclosures_config, save_enclosures_config
from gi.repository import GLib, Gtk
from gui_helpers import (
    bold_label,
    configure_treeview_column,
    create_dialog,
    setup_row_scroll,
)
from logging_config import log_msg
from zfs_repository import TopologyNode, ZfsRepository, valid_rate_limit

# Foreground color used to tint the rows in one pane that correlate with the
# current selection in the other: disks of the selected pool (or of the
# selected topology node) in the Disk Inventory, and the devices of the
# selected inventory disk in the Pool Topology.
POOL_MEMBER_HIGHLIGHT_FG = "#00797A"

# Minimum height of the page content. Keeps the panes usable
# on short windows and drives the page-level vertical scrollbar instead of
# letting the view be squashed by its neighbors.
DISKS_TOPOLOGY_MIN_HEIGHT = 260

# Minimum height of the Enclosures pane. The section holds a handful of rows
# (one per multi-bay enclosure); taller lists scroll inside the pane rather
# than stretching the page.
ENCLOSURES_MIN_HEIGHT = 90

# Disk pane ListStore columns:
#   0 name, 1 by-id, 2 model, 3 serial, 4 size, 5 type,
#   6 logical_sector, 7 physical_sector, 8 transport, 9 enclosure,
#   10 pools, 11 smart_health, 12 health (SSD/NVMe wear %, HDD surface-test
#   status), 13 highlight
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
    COL_D_ENCLOSURE,
    COL_D_POOLS,
    COL_D_SMART,
    COL_D_HEALTH,
    COL_D_HIGHLIGHT,
) = range(14)

# Enclosure pane ListStore columns:
#   0 id (not rendered — identifies the config entry), 1 name,
#   2 kind/location, 3 disk count, 4 pools, 5 max rate
(
    COL_E_ID,
    COL_E_NAME,
    COL_E_KIND,
    COL_E_DISKS,
    COL_E_POOLS,
    COL_E_RATE,
) = range(6)

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
    enclosures: list[EnclosureInfo] = field(default_factory=list)


def enclosure_display_name(enclosure: EnclosureInfo, name: str) -> str:
    """Return the user-assigned enclosure name or a self-describing fallback.

    Unnamed enclosures show their kind and location (e.g. ``usb usb2/2-2``)
    so every surface that names an enclosure stays identifiable without a
    configured name.
    """
    return name.strip() or f"{enclosure.kind} {enclosure.location}"


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
        enclosure_inventory: EnclosureInventory | None = None,
        ttl_seconds: float = 30.0,
    ):
        self.disk_repository = disk_repository
        self.zfs_repository = zfs_repository
        # None means enclosure wiring is absent (tests embed the cache without
        # the Phase 1 module): no discovery, no enclosure fields, empty list.
        self.enclosure_inventory = enclosure_inventory
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

        enclosures = self._discover_enclosures()
        if enclosures:
            enclosure_by_member = {
                member: enclosure.id for enclosure in enclosures for member in enclosure.members
            }
            for disk in disks:
                # Partitions follow their parent disk's enclosure; whole disks
                # carry their own membership directly.
                base = (
                    os.path.basename(disk.parent_path)
                    if disk.parent_path is not None
                    else disk.name
                )
                disk.enclosure_id = enclosure_by_member.get(base, "")

        return DiskInventoryData(disks=disks, topologies=topologies, enclosures=enclosures)

    def _discover_enclosures(self) -> list[EnclosureInfo]:
        """Return discovered enclosures, failing open to an empty list.

        A scan hiccup must never blank the disk list: the enclosure section
        empties and the disks lose their enclosure tags until the next
        refresh, matching the fail-open policy of the transfer-time resolver.
        """
        if self.enclosure_inventory is None:
            return []
        try:
            return self.enclosure_inventory.discover()
        except Exception as exc:  # pragma: no cover - defensive
            log_msg(f"WARN: enclosure discovery failed: {exc}")
            return []

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
    app._disks_inventory_cache = DiskInventoryCache(
        app.ctx.disk_repository,
        app.ctx.zfs_repository,
        enclosure_inventory=EnclosureInventory(
            disk_repository=app.ctx.disk_repository,
            zfs_repository=app.ctx.zfs_repository,
        ),
    )
    app._disks_syncing_selection = False

    page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    page_box.set_margin_start(10)
    page_box.set_margin_end(10)
    page_box.set_margin_top(10)
    page_box.set_margin_bottom(10)

    # --- Disk Inventory and Pool Topology sections ---
    inventory_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    # Minimum height keeps the panes usable on short windows and drives the
    # page-level vertical scrollbar instead of letting the content be squashed.
    inventory_box.set_size_request(-1, DISKS_TOPOLOGY_MIN_HEIGHT)
    page_box.pack_start(inventory_box, True, True, 0)

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
        str, str, str, str, str, str, str, str, str, str, str, str, str, bool
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
        (COL_D_ENCLOSURE, "Enclosure", 130),
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

    # --- Enclosures section: USB/eSATA enclosures and their rate caps ---
    enclosures_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    enclosures_box.set_size_request(-1, ENCLOSURES_MIN_HEIGHT)
    inventory_box.pack_start(enclosures_box, False, False, 0)

    enc_title = bold_label("Enclosures")
    enclosures_box.pack_start(enc_title, False, False, 0)

    enc_desc = Gtk.Label(
        label="Multi-bay USB and eSATA enclosures discovered on this system. "
        "A max I/O rate caps every paced transfer that touches the "
        "enclosure's disks (backups, archives, clones, restores); when an "
        "activity limit also applies, the lower one wins. Blank means "
        "unlimited."
    )
    enc_desc.set_halign(Gtk.Align.START)
    enc_desc.set_line_wrap(True)
    enclosures_box.pack_start(enc_desc, False, False, 0)

    app.enclosures_store = Gtk.ListStore(str, str, str, str, str, str)
    app.enclosures_view = Gtk.TreeView(model=app.enclosures_store)
    app.enclosures_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.enclosures_view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
    app.enclosures_view.get_selection().connect("changed", _on_enclosure_selection_changed, app)

    enclosure_cols = [
        (COL_E_NAME, "Name", 190),
        (COL_E_KIND, "Kind/Location", 150),
        (COL_E_DISKS, "Disks", 60),
        (COL_E_POOLS, "Pools", 170),
        (COL_E_RATE, "Max I/O Rate", 110),
    ]
    for col_idx, title_text, width in enclosure_cols:
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        configure_treeview_column(col, width=width)
        app.enclosures_view.append_column(col)

    app.enable_treeview_copy(app.enclosures_view)

    enclosures_scrolled = Gtk.ScrolledWindow()
    enclosures_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    enclosures_scrolled.add(app.enclosures_view)
    setup_row_scroll(enclosures_scrolled, app.enclosures_view)
    enclosures_box.pack_start(enclosures_scrolled, True, True, 0)

    inventory_box.pack_start(Gtk.Separator(), False, False, 0)

    topo_title = bold_label("Pool Topology")
    inventory_box.pack_start(topo_title, False, False, 0)

    # --- Pool selector: marks the selected pool inside the topology section ---
    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    controls.set_halign(Gtk.Align.START)
    app._disks_pool_selector = Gtk.ComboBoxText()
    app._disks_pool_selector.connect("changed", _on_pool_selector_changed, app)
    controls.pack_start(app._disks_pool_selector, False, False, 0)

    hint = Gtk.Label(label="Selected pool — pool actions and disk highlights follow it")
    hint.set_halign(Gtk.Align.START)
    controls.pack_start(hint, False, False, 0)
    inventory_box.pack_start(controls, False, False, 0)

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

    refresh_disks_page(app)

    # Wrap the page so the whole tab scrolls vertically on short windows
    # instead of squashing the stacked panes.
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.add(page_box)
    return scrolled


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
    had_choices = len(selector.get_model()) > 0

    data = app._disks_inventory_cache.get(callback=_make_disks_refresh_callback(app))

    from disk_surface_test import load_surface_test_state, surface_cell_text

    surface_state = load_surface_test_state()

    # Enclosure column: the display name (config name or kind/location
    # fallback); internal disks show a blank cell.
    enclosure_entries = get_enclosures_config(app.config)
    enclosure_names = {
        enclosure.id: enclosure_display_name(
            enclosure, enclosure_entries.get(enclosure.id, {}).get("name", "")
        )
        for enclosure in data.enclosures
    }

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
                enclosure_names.get(disk.enclosure_id, ""),
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
    elif selected_pool is None and had_choices:
        # The selector was deliberately cleared (a disk outside every pool is
        # selected); keep it cleared instead of snapping back to the first
        # pool on every background refresh.
        pass
    elif pool_names:
        selector.set_active(0)

    # Repopulate the all-pools topology view
    _repopulate_topology(app)

    # Restore disk selection
    if selected_path:
        it = app.disks_store.get_iter_first()
        while it:
            if app.disks_store.get_value(it, COL_D_NAME) == selected_path:
                path = app.disks_store.get_path(it)
                disks_view.get_selection().select_path(path)
                break
            it = app.disks_store.iter_next(it)

    # Repopulate the enclosures section
    _repopulate_enclosures(app)

    update_disks_button_sensitivity(app)


def _repopulate_enclosures(app):
    """Refill the Enclosures section from cached discovery plus config.

    Discovery data comes from the inventory cache (same TTL refresh as the
    disk list); names and current max rates come from the enclosures config
    section, so a rate saved through the dialog shows up on the next
    repopulation without waiting for a device rescan.
    """
    store = app.enclosures_store

    # Selection capture mirrors _sync_topology_highlight_from_inventory: a
    # view that answers anything other than a (model, paths) tuple simply
    # has no selection to preserve.
    selected_id = None
    view = getattr(app, "enclosures_view", None)
    if view is not None:
        selection = view.get_selection()
        rows = selection.get_selected_rows()
        if isinstance(rows, tuple) and len(rows) == 2 and rows[1]:
            model, pathlist = rows
            try:
                tree_iter = model.get_iter(pathlist[0])
                selected_id = model.get_value(tree_iter, COL_E_ID)
            except (IndexError, TypeError, ValueError):
                selected_id = None

    store.clear()
    data = app._disks_inventory_cache.get()
    entries = get_enclosures_config(app.config)
    for enclosure in data.enclosures:
        entry = entries.get(enclosure.id) or {}
        store.append(
            [
                enclosure.id,
                enclosure_display_name(enclosure, entry.get("name", "")),
                f"{enclosure.kind} {enclosure.location}",
                str(len(enclosure.members)),
                ", ".join(enclosure.pools),
                entry.get("max_rate", "") or "unlimited",
            ]
        )

    # Restore the enclosure selection so a background refresh does not
    # desensitize the Set Max I/O Rate… button mid-choice.
    if selected_id and view is not None:
        selection = view.get_selection()
        it = store.get_iter_first()
        while it:
            if store.get_value(it, COL_E_ID) == selected_id:
                path = store.get_path(it)
                selection.select_path(path)
                break
            it = store.iter_next(it)


def on_disks_refresh(app):
    """Invalidate the disk inventory cache and refresh the page."""
    app._disks_inventory_cache.invalidate()
    refresh_disks_page(app)
    log_msg("VERB: Disks refreshed")


def on_disks_manage_pool_profiles(app):
    """Open the pool profile manager."""
    from pool_profile_dialogs import show_manage_pool_profiles_dialog

    show_manage_pool_profiles_dialog(app)


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


def _on_enclosure_selection_changed(selection, app):
    """An Enclosures selection only drives the Set Max I/O Rate… button."""
    update_disks_button_sensitivity(app)


def _selected_enclosure_id(app) -> str:
    """Return the id of the single selected Enclosures row, or an empty string."""
    view = getattr(app, "enclosures_view", None)
    if view is None:
        return ""
    selection = view.get_selection()
    rows = selection.get_selected_rows()
    if not isinstance(rows, tuple) or len(rows) != 2 or not rows[1]:
        return ""
    model, pathlist = rows
    try:
        tree_iter = model.get_iter(pathlist[0])
        enclosure_id = model.get_value(tree_iter, COL_E_ID)
    except (IndexError, TypeError, ValueError):
        return ""
    return enclosure_id if isinstance(enclosure_id, str) else ""


def _enclosure_rate_problem(text: str) -> str | None:
    """Refusal line when *text* is not a valid pacer rate; None when valid.

    Accepts exactly the grammar lib/pace_stream.py enforces (digits plus an
    optional k/m/g/t/p/e multiplier with optional i and b, case-insensitive,
    1024-based) so the dialog never refuses a value the transfer-side
    resolver would happily pace. An empty string is valid (unlimited).
    """
    if not text:
        return None
    if not valid_rate_limit(text):
        return (
            f"invalid max I/O rate '{text}' — use digits with an optional "
            "k/m/g/t/p/e suffix (i and b also accepted, for example 100m "
            "or 64KiB), or leave it blank for unlimited"
        )
    return None


def _show_enclosure_rate_dialog(app, enclosure: EnclosureInfo, entry: dict):
    """Run the Set Max I/O Rate dialog for *enclosure*.

    *entry* is the enclosure's current config entry ({name, max_rate}).
    Returns (name, max_rate) when saved, None when canceled. An invalid
    rate keeps the dialog open with the refusal line shown.
    """
    parent = getattr(app, "window", None)
    dialog = create_dialog(
        f"Enclosure {enclosure_display_name(enclosure, entry.get('name', ''))}",
        parent,
        [("Cancel", Gtk.ResponseType.CANCEL), ("Save", Gtk.ResponseType.OK)],
        default_response=Gtk.ResponseType.OK,
    )
    content = dialog.get_content_area()

    pools_text = ", ".join(enclosure.pools) if enclosure.pools else "no pools"
    caption = Gtk.Label(
        label=(
            f"{enclosure.kind} at {enclosure.location} — "
            f"{len(enclosure.members)} disks, pools: {pools_text}"
        )
    )
    caption.set_halign(Gtk.Align.START)
    caption.set_line_wrap(True)
    content.pack_start(caption, False, False, 0)

    name_label = Gtk.Label(label="Enclosure name (shown in the disk list)")
    name_label.set_halign(Gtk.Align.START)
    content.pack_start(name_label, False, False, 0)
    name_entry = Gtk.Entry()
    name_entry.set_text(entry.get("name", ""))
    name_entry.set_placeholder_text(f"e.g. {enclosure.kind}-enclosure")
    content.pack_start(name_entry, False, False, 0)

    rate_label = Gtk.Label(label="Max I/O rate (blank = unlimited)")
    rate_label.set_halign(Gtk.Align.START)
    content.pack_start(rate_label, False, False, 0)
    rate_entry = Gtk.Entry()
    rate_entry.set_text(entry.get("max_rate", ""))
    rate_entry.set_placeholder_text("e.g. 100m")
    content.pack_start(rate_entry, False, False, 0)

    problem_label = Gtk.Label(label="")
    problem_label.set_halign(Gtk.Align.START)
    problem_label.set_line_wrap(True)
    content.pack_start(problem_label, False, False, 0)

    while True:
        dialog.show_all()
        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return None
        name = name_entry.get_text().strip()
        rate = rate_entry.get_text().strip()
        problem = _enclosure_rate_problem(rate)
        if problem is None:
            dialog.destroy()
            return name, rate
        problem_label.set_text(problem)


def on_disks_set_enclosure_rate(app):
    """Set Max I/O Rate… action: name and rate cap for the selected enclosure."""
    enclosure_id = _selected_enclosure_id(app)
    if not enclosure_id:
        return
    enclosure = next(
        (e for e in app._disks_inventory_cache.get().enclosures if e.id == enclosure_id),
        None,
    )
    if enclosure is None:
        return

    entries = get_enclosures_config(app.config)
    entry = entries.setdefault(enclosure_id, {})
    result = _show_enclosure_rate_dialog(app, enclosure, entry)
    if result is None:
        return
    name, rate = result
    entry["name"] = name
    entry["max_rate"] = rate
    save_enclosures_config(app.config, entries)
    log_msg(
        f"VERB: enclosure {enclosure_display_name(enclosure, name)} "
        f"max I/O rate set to {rate or 'unlimited'}"
    )
    refresh_disks_page(app)


def _on_disk_selection_changed(selection, app):
    """When a disk/partition is selected, tint its devices across all pools.

    The pool selector follows the disk's pool, but the topology pane never
    selects a node: the devices residing on the selected disk are tinted
    teal instead (see _sync_topology_highlight_from_inventory). A disk or
    partition that belongs to no pool clears the topology pane instead —
    tints, pool selector, and expansion all reset so nothing stale from the
    previously shown state stays on screen.
    """
    if getattr(app, "_disks_syncing_selection", False):
        return
    model, pathlist = selection.get_selected_rows()
    selector = app._disks_pool_selector
    if pathlist:
        tree_iter = model.get_iter(pathlist[0])
        pools_str = model.get_value(tree_iter, COL_D_POOLS)
        if pools_str:
            first_pool = pools_str.split(", ")[0]
            if selector.get_active_text() != first_pool:
                _set_combo_active_text(selector, first_pool)
            _sync_topology_highlight_from_inventory(app)
        else:
            _clear_topology_highlights(app)
            if selector.get_active() != -1:
                selector.set_active(-1)
    else:
        _clear_topology_highlights(app)
    _apply_topology_expansion(app)
    update_disks_button_sensitivity(app)


def _on_topology_selection_changed(selection, app):
    """When a topology node is selected, highlight its devices in the inventory.

    A device node highlights that device, a vdev node highlights every device
    in the vdev, and the pool node highlights every device in the pool. The
    pool selector follows the pool containing the selection, and an empty
    selection (or a node with no devices) restores the pool-wide highlight.
    The inventory selection is never modified; the correlation is teal
    foreground text only.
    """
    if getattr(app, "_disks_syncing_selection", False):
        return
    model, pathlist = selection.get_selected_rows()
    selector = app._disks_pool_selector
    if pathlist:
        containing_pool = _topology_selection_pool(model, pathlist[0])
        if containing_pool and selector.get_active_text() != containing_pool:
            _set_combo_active_text(selector, containing_pool)
        tree_iter = model.get_iter(pathlist[0])
        device_paths = _topology_subtree_device_paths(model, tree_iter)
        if device_paths:
            _highlight_topology_devices(app, device_paths)
        else:
            _highlight_pool_disks(app, selector.get_active_text())
    else:
        _highlight_pool_disks(app, selector.get_active_text())
    _apply_topology_expansion(app)
    update_disks_button_sensitivity(app)


def _on_pool_selector_changed(selector, app):
    """Update inventory highlights and topology expansion for the selected pool."""
    _highlight_pool_disks(app, selector.get_active_text())
    _apply_topology_expansion(app)


def _repopulate_topology(app):
    """Clear and refill the topology store with every pool's vdev tree.

    All pools stay visible as top-level rows; expansion is driven by the
    selected pool, the topology selection, and teal-tinted devices (see
    _apply_topology_expansion).
    """
    app.disks_topology_store.clear()
    data = app._disks_inventory_cache.get()
    for pool_name in sorted(data.topologies.keys()):
        _populate_topology_store(app.disks_topology_store, None, data.topologies[pool_name])
    _highlight_pool_disks(app, app._disks_pool_selector.get_active_text())
    _sync_topology_highlight_from_inventory(app)
    _apply_topology_expansion(app)


def update_disks_button_sensitivity(app):
    """Enable action buttons based on the current selection."""
    selection = app.disks_view.get_selection()
    _model, pathlist = selection.get_selected_rows()
    single_selection = len(pathlist) == 1
    btn = getattr(app, "_disks_smart_details_btn", None)
    if btn:
        btn.set_sensitive(single_selection)

    runner_busy = bool(
        getattr(app, "dataset_runner", None) and getattr(app.dataset_runner, "running", False)
    )
    compute_host = node_config.is_two_node() and not node_config.is_storage_host()

    create_btn = getattr(app, "_disks_create_pool_btn", None)
    if create_btn:
        if compute_host:
            create_btn.set_sensitive(False)
            create_btn.set_tooltip_text("Pool creation is available only on the storage host")
        elif runner_busy:
            create_btn.set_sensitive(False)
            create_btn.set_tooltip_text("A dataset action is already running")
        else:
            create_btn.set_sensitive(True)
            create_btn.set_tooltip_text("")

    # Pool-growth/maintenance buttons share the Create Pool gating:
    # compute-host, then runner-busy.
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
        if compute_host:
            btn.set_sensitive(False)
            btn.set_tooltip_text(host_tooltip)
        elif runner_busy:
            btn.set_sensitive(False)
            btn.set_tooltip_text("A dataset action is already running")
        else:
            btn.set_sensitive(True)
            btn.set_tooltip_text("")

    # Proxmox enrollment acts on the selected pool.
    proxmox_btn = getattr(app, "_disks_proxmox_enroll_btn", None)
    if proxmox_btn:
        selector = getattr(app, "_disks_pool_selector", None)
        pool_name = selector.get_active_text() if selector is not None else ""
        if compute_host:
            proxmox_btn.set_sensitive(False)
            proxmox_btn.set_tooltip_text("Proxmox enrollment is available only on the storage host")
        elif runner_busy:
            proxmox_btn.set_sensitive(False)
            proxmox_btn.set_tooltip_text("A dataset action is already running")
        else:
            proxmox_btn.set_sensitive(bool(pool_name))
            proxmox_btn.set_tooltip_text("" if pool_name else "Select a pool to enroll in Proxmox")

    surf_btn = getattr(app, "_disks_surface_test_btn", None)
    if surf_btn:
        selected_hdd = single_selection and _selected_disk_is_hdd(app)
        if compute_host:
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

    wipe_btn = getattr(app, "_disks_wipe_btn", None)
    if wipe_btn:
        wipeable = single_selection and _selected_disk_is_wipeable(app)
        if compute_host:
            wipe_btn.set_sensitive(False)
            wipe_btn.set_tooltip_text("Disk wipe is available only on the storage host")
        elif runner_busy:
            wipe_btn.set_sensitive(False)
            wipe_btn.set_tooltip_text("A dataset action is already running")
        else:
            wipe_btn.set_sensitive(bool(wipeable))
            wipe_btn.set_tooltip_text(
                ""
                if wipeable
                else "Select a single disk that belongs to no pool to wipe its labels"
            )

    # Enclosure rate setting edits configuration only — no ZFS I/O, so it is
    # gated by storage host and selection, not by the dataset runner.
    rate_btn = getattr(app, "_disks_enclosure_rate_btn", None)
    if rate_btn:
        enclosure_id = _selected_enclosure_id(app)
        if compute_host:
            rate_btn.set_sensitive(False)
            rate_btn.set_tooltip_text("Enclosure rates are set on the storage host")
        else:
            rate_btn.set_sensitive(bool(enclosure_id))
            rate_btn.set_tooltip_text(
                "" if enclosure_id else "Select an enclosure to set its max I/O rate"
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


def _selected_disk_is_wipeable(app) -> bool:
    """Return True when the selection is one inactive disk eligible for wiping.

    Uses ``wipe_block_reason`` (same rule as the handler and the zfswipe
    script): neither the row nor anything else on its backing disk may belong
    to an imported pool.
    """
    selection = app.disks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if len(pathlist) != 1:
        return False
    try:
        tree_iter = model.get_iter(pathlist[0])
        if model.get_value(tree_iter, COL_D_POOLS):
            return False
        path = model.get_value(tree_iter, COL_D_NAME)
    except (IndexError, ValueError):
        return False

    from disk_wipe import wipe_block_reason

    data = app._disks_inventory_cache.get()
    disk = next((d for d in data.disks if d.path == path), None)
    return disk is not None and wipe_block_reason(disk, data.disks) is None


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


def _topology_selection_pool(model, path) -> str | None:
    """Return the top-level pool-row name that contains topology *path*."""
    indices = path.get_indices() if hasattr(path, "get_indices") else list(path)
    if not indices:
        return None
    try:
        top_iter = model.get_iter((indices[0],))
    except (IndexError, TypeError, ValueError):
        return None
    if top_iter is None:
        return None
    name = model.get_value(top_iter, COL_T_NAME)
    return name if isinstance(name, str) else None


def _subtree_has_highlight(store, tree_iter) -> bool:
    """Return True if any row in the subtree at *tree_iter* is teal-tinted."""
    if store.get_value(tree_iter, COL_T_HIGHLIGHT):
        return True
    child = store.iter_children(tree_iter)
    while child is not None:
        if _subtree_has_highlight(store, child):
            return True
        child = store.iter_next(child)
    return False


def _apply_topology_expansion(app) -> None:
    """Expand pool rows that are relevant; collapse the rest.

    A pool row is expanded — fully, so tinted leaves inside mirror/raidz
    groups stay visible — when it is the pool picked in the selector,
    contains the topology selection, or contains a teal-tinted device.
    Pools with no selection or highlight stay collapsed.
    """
    store = app.disks_topology_store
    view = app.disks_topology_view
    active_pool = app._disks_pool_selector.get_active_text()

    selected_pool = None
    rows = view.get_selection().get_selected_rows()
    if isinstance(rows, tuple) and len(rows) == 2 and rows[1]:
        selected_pool = _topology_selection_pool(rows[0], rows[1][0])

    it = store.get_iter_first()
    while it:
        pool_name = store.get_value(it, COL_T_NAME)
        relevant = _subtree_has_highlight(store, it) or (
            isinstance(pool_name, str) and pool_name in (active_pool, selected_pool)
        )
        path = store.get_path(it)
        if relevant:
            view.expand_row(path, True)
        else:
            view.collapse_row(path)
        it = store.iter_next(it)


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
