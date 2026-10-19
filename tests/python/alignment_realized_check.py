#!/usr/bin/env python3
"""Realized-window scroll check for the Alignment view (child process).

Run directly (``python3 alignment_realized_check.py``) or via
tests/python/test_alignment_realized.py.  Unlike the mock_gtk suites,
this builds the real Performance page (GTK 3) inside a realized
Gtk.Window and drives GTK's main loop, so scroll preservation is
exercised against real allocations and adjustments — the level at which
the jump-on-refresh defect was measured.

It runs as a child process on purpose: binding the GUI layer to real
GTK (and warming matplotlib's GTK backend) inside the pytest process
would poison the mock-bound module caches the other suites rely on.

Needs a display: starts a private Xvfb first (so the realized window
never flashes on the operator's desktop during a full-suite run) and
falls back to the ambient display when Xvfb cannot start.  Exit codes:
0 pass, 3 skip (no display available), anything else failure with a
traceback on stderr.
"""

import os
import subprocess
import sys
import time
import types

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
TESTS_SRC = os.path.join(REPO_ROOT, "tests", "python")
for path in (PYTHON_SRC, TESTS_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)

_XVFB_READY_TIMEOUT = 5.0
_SKIP_RC = 3


def _skip(reason):
    print(f"REALIZED-SKIP: {reason}")
    raise SystemExit(_SKIP_RC)


def _start_xvfb():
    """Start a private Xvfb and point DISPLAY at it; None when impossible."""
    if not os.path.exists("/usr/bin/Xvfb"):
        return None
    for number in range(99, 89, -1):
        socket_path = f"/tmp/.X11-unix/X{number}"
        if os.path.exists(socket_path):
            continue
        try:
            proc = subprocess.Popen(
                [
                    "/usr/bin/Xvfb",
                    f":{number}",
                    "-nolisten",
                    "tcp",
                    "-screen",
                    "0",
                    "1024x768x24",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return None
        deadline = time.monotonic() + _XVFB_READY_TIMEOUT
        while time.monotonic() < deadline:
            if os.path.exists(socket_path):
                os.environ["DISPLAY"] = f":{number}"
                return proc
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        proc.terminate()
    return None


def _rebind_gtk():
    """Re-import the Gtk overrides after a display appeared.

    PyGObject runs ``Gtk.init_check`` once, at override-import time, and
    caches the result in a module global that ``Gtk.Window()`` checks.
    When the first import happened without a display that flag stays
    False even after a later successful init, so every widget
    constructor would raise. Evicting the cached modules AND the
    attributes the gi packages carry (``from gi.repository import Gtk``
    resolves through the attribute, not just sys.modules) makes the next
    import re-run the check against the new DISPLAY.
    """
    import gi
    import gi.overrides
    import gi.repository

    for name in (
        "gi.repository.Gtk",
        "gi.repository.Gdk",
        "gi.overrides.Gtk",
        "gi.overrides.Gdk",
    ):
        sys.modules.pop(name, None)
    for package, names in ((gi.repository, ("Gtk", "Gdk")), (gi.overrides, ("Gtk", "Gdk"))):
        for name in names:
            if name in vars(package):
                delattr(package, name)
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # noqa: F401  (re-runs the init check)

    return bool(gi.overrides.Gtk.initialized)


def _ensure_display():
    """Return the Xvfb process to terminate at exit (or None)."""
    # Private Xvfb first: a realized window on the ambient display flashes
    # on the operator's desktop during full-suite runs.  The ambient display
    # is the fallback for hosts where Xvfb cannot start or GTK cannot bind.
    saved_display = os.environ.get("DISPLAY")
    xvfb = _start_xvfb()
    if xvfb is not None:
        if _rebind_gtk():
            print(f"REALIZED-DISPLAY: private Xvfb on {os.environ.get('DISPLAY')}")
            return xvfb
        xvfb.terminate()
        if saved_display is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = saved_display
    # The ambient check is a _rebind_gtk, not a bare init call: a failed
    # Xvfb bind leaves the override-import cache marked uninitialized, and
    # only a fresh import re-runs the init check against the restored
    # ambient DISPLAY.
    if _rebind_gtk():
        print(f"REALIZED-DISPLAY: ambient {os.environ.get('DISPLAY', '(default)')}")
        return None
    _skip("no display available (Xvfb could not be started and the ambient display failed)")


def _member(path):
    import alignment_stats as astats

    return astats.MemberDisk(path=path, logical_sector=512, physical_sector=4096)


def _topo_node(name, vdev_type, children=None):
    import zfs_repository

    return zfs_repository.TopologyNode(
        name=name,
        vdev_type=vdev_type,
        state="ONLINE" if vdev_type == "disk" else "-",
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=children or [],
    )


def _realized_sample():
    """A sample with enough rows to make the Alignment page scrollable."""
    import alignment_stats as astats

    pools = [
        astats.PoolAlignment(
            name="NVME1",
            ashift_configured="12",
            ashift_effective=12,
            topology=_topo_node(
                "NVME1",
                "pool",
                [
                    _topo_node(
                        "mirror-0",
                        "mirror",
                        [
                            _topo_node("/dev/disk/by-id/ata-A1", "disk"),
                            _topo_node("/dev/disk/by-id/ata-A2", "disk"),
                        ],
                    ),
                    _topo_node("cache", "cache", [_topo_node("/dev/disk/by-id/ata-C1", "disk")]),
                ],
            ),
            members=[
                _member("/dev/disk/by-id/ata-A1"),
                _member("/dev/disk/by-id/ata-A2"),
                _member("/dev/disk/by-id/ata-C1"),
            ],
            has_cache=True,
        ),
        astats.PoolAlignment(
            name="tank",
            ashift_configured="9",
            ashift_effective=9,
            topology=_topo_node(
                "tank",
                "pool",
                [_topo_node("/dev/disk/by-id/ata-B1", "disk")],
            ),
            members=[_member("/dev/disk/by-id/ata-B1")],
        ),
    ]
    datasets = [
        astats.DatasetBlocks(
            name=f"NVME1/ds{i}", kind="filesystem", recordsize="128K", recordsize_source="local"
        )
        for i in range(6)
    ]
    datasets.append(
        astats.DatasetBlocks(
            name="NVME1/vm-201-disk-0",
            kind="volume",
            volblocksize="16K",
            volblocksize_source="-",
        )
    )
    hist = astats.ReqHistogram(pool="NVME1")
    hist.add(4096, "ind", "sync_write", 2000)
    hist.add(1024**2, "agg", "async_read", 8000)
    # Per-dataset objset counters (4K average writes, above the op floor):
    # the per-dataset observed-size findings render and reconcile in the
    # realized window too. Both scenario samples reuse this fixture, and
    # equal monotonic timestamps keep them on the since-boot basis, so
    # the findings delta between the scenarios stays exactly one row.
    objset = {}
    for ds in datasets:
        objset[ds.name] = {
            "reads": 4000,
            "nread": 4000 * 4096,
            "writes": 4000,
            "nwritten": 4000 * 4096,
        }
    return astats.AlignmentSample(
        monotonic=1.0,
        pools=pools,
        datasets=datasets,
        histograms={"NVME1": hist},
        objset=objset,
        objset_available=True,
        vm_disks={
            "vm-201-disk-0": astats.VMOption(
                vmid="201", disknum="0", bus="scsi0", options={"discard": "1"}
            )
        },
        arc={
            "demand_data_hits": 900,
            "demand_data_misses": 100,
            "mru_hits": 300,
            "mfu_hits": 700,
            "mru_ghost_hits": 10,
            "mfu_ghost_hits": 20,
            "evict_l2_cached": 100,
            "evict_l2_ineligible": 300,
            "evict_l2_eligible": 600,
        },
        prefetch={"hits": 900, "misses": 100},
        pools_available=True,
        datasets_available=True,
        iostat_r_available=True,
        arcstats_available=True,
        prefetch_available=True,
        pve_available=True,
    )


def main():
    xvfb = _ensure_display()
    try:
        _run_checks()
    finally:
        if xvfb is not None:
            xvfb.terminate()
    print("ALIGNMENT-REALIZED-OK")
    return 0


def _run_checks():
    from test_support import import_gui_fresh

    mp = import_gui_fresh("memory_page")
    ap = sys.modules["alignment_page"]  # real-bound by the fresh import above
    Gtk = mp.Gtk

    class _App:
        pass

    class _UIStateStub:
        """bind_treeview stand-in: the realized check does not persist widths."""

        def bind_treeview(self, view, state_key):
            pass

    app = _App()
    app.config = {}
    app.ctx = types.SimpleNamespace(zfs_caps=None)
    app._ui_state = _UIStateStub()

    page = mp.create_memory_page(app)
    win = Gtk.Window()
    win.set_default_size(520, 320)
    win.add(page)
    win.show_all()

    def pump(rounds=10):
        for _ in range(rounds):
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

    pump()
    app._memory_view_stack.set_visible_child_name("alignment")
    pump()
    ap._apply_alignment_sample(app, _realized_sample())
    pump()
    assert app.performance_scrolled.get_vadjustment().get_upper() > (
        app.performance_scrolled.get_vadjustment().get_page_size() + 100
    ), "page is not tall enough to exercise mid-page scrolling"

    def scroll_mid_page():
        vadj = app.performance_scrolled.get_vadjustment()
        vadj.set_value(vadj.get_upper() * 0.5)
        pump()
        return vadj.get_value()

    def chain_view():
        store = app._alignment_chain_store

        def walk(widget):
            if isinstance(widget, Gtk.TreeView) and widget.get_model() is store:
                return widget
            get_children = getattr(widget, "get_children", None)
            if get_children is None:
                return None
            for child in get_children():
                found = walk(child)
                if found is not None:
                    return found
            return None

        view = walk(win)
        assert view is not None, "chain TreeView not found in the realized window"
        return view

    # --- Scenario 1: findings rows legitimately change mid-view ----------
    v_before = scroll_mid_page()
    view = chain_view()
    coords_before = view.translate_coordinates(win, 0, 0)
    chain_rows_before = len(app._alignment_chain_store)
    findings_before = len(app._alignment_findings_store)
    topo_keys_before = [row[0] for row in app._alignment_topology_store]
    assert topo_keys_before == [
        "Topology:NVME1:mirror-0",
        "Topology:NVME1:/dev/disk/by-id/ata-C1",
        "Topology:tank:/dev/disk/by-id/ata-B1",
    ], topo_keys_before

    changed = _realized_sample()
    changed.arc = dict(changed.arc, mru_ghost_hits=400, mfu_ghost_hits=500)
    ap._apply_alignment_sample(app, changed)
    pump()

    v_after = app.performance_scrolled.get_vadjustment().get_value()
    assert abs(v_after - v_before) <= 1.0, f"scroll jumped: {v_before} -> {v_after}"
    coords_after = view.translate_coordinates(win, 0, 0)
    assert coords_after == coords_before, (
        f"content above the viewport moved: {coords_before} -> {coords_after}"
    )
    assert len(app._alignment_chain_store) == chain_rows_before, "chain rows rebuilt"
    assert [row[0] for row in app._alignment_topology_store] == topo_keys_before, (
        "topology rows rebuilt"
    )
    assert len(app._alignment_findings_store) == findings_before + 1, "findings delta wrong"
    assert any("ghost hits" in row[4] for row in app._alignment_findings_store), (
        "expected the ghost-churn finding"
    )
    # The blocksize ladder keeps its per-pool rung identities too (the
    # visual renders through whichever renderer the factory selected).
    ladder = app._alignment_ladder
    assert [entry.pool for entry in ladder.pools] == ["NVME1", "tank"], ladder.pools
    assert ladder.pools[0].block == 4096
    ladder_layers = [bar.layer for entry in ladder.pools for bar in entry.bars]
    assert ladder_layers.count("Pool") == 2, ladder_layers
    assert "VM" in ladder_layers, "expected the guest-sector rung"
    print("PASS findings change: offset held, chain unmoved, findings updated in place")

    # --- Scenario 2: transient per-pool dataset failure -------------------
    v_before = scroll_mid_page()
    chain_rows_before = len(app._alignment_chain_store)

    failed = _realized_sample()
    failed.datasets = []
    failed.dataset_read_failures = ["NVME1", "tank"]
    ap._apply_alignment_sample(app, failed)
    pump()

    v_after = app.performance_scrolled.get_vadjustment().get_value()
    assert abs(v_after - v_before) <= 1.0, f"scroll jumped: {v_before} -> {v_after}"
    layers = [row[1] for row in app._alignment_chain_store]
    assert len(layers) < chain_rows_before, "dataset rows should have vanished"
    assert layers.count("Pool") == 2, f"pool rows blanked wholesale: {layers}"
    assert layers.count("Device") == 4, f"device rows blanked wholesale: {layers}"
    assert "Dataset" not in layers and "VM" not in layers
    # The availability note names the failed pools (set_markup also sets
    # the plain label text, which is what can be read back).
    assert app._alignment_note.get_visible(), "availability note not shown"
    note_text = app._alignment_note.get_text() or ""
    assert "Dataset block properties unreadable for: NVME1, tank" in note_text, note_text
    # The ladder degrades per source the same way: dataset and VM rungs
    # vanish while every pool keeps its device and reference rungs.
    ladder_layers = [bar.layer for entry in app._alignment_ladder.pools for bar in entry.bars]
    assert "Dataset" not in ladder_layers and "VM" not in ladder_layers, ladder_layers
    assert ladder_layers.count("Device") == 2 and ladder_layers.count("Pool") == 2, ladder_layers
    print("PASS per-pool failure: pool/device rows retained, note names the pools")

    win.destroy()
    pump()


if __name__ == "__main__":
    sys.exit(main())
