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

Needs a display, and it must be one this script made itself: it starts a
private Xvfb and never opens the ambient display — a realized window
flashing on the operator's desktop mid-suite is exactly the leak this
guards against.  When no private display can be produced the check
skips rather than fall back.  Exit codes: 0 pass, 3 skip (no private
display available), anything else failure with a traceback on stderr.
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
    """Start the private Xvfb, bind GTK to it, and return it for exit.

    This script realizes real windows, so the ambient display is never
    an option: opening it would flash a GTK window on the operator's
    desktop during a full-suite run.  DISPLAY is only ever pointed at an
    Xvfb this script started; when that is impossible (Xvfb missing, no
    free display number, or GTK refusing to bind) the check skips.  The
    rebind dance matters for the bind-failure path: a failed
    ``Gtk.init_check`` leaves PyGObject's initialized flag stale, and a
    plain retry would raise from every widget constructor even after the
    environment is healthy again.
    """
    xvfb = _start_xvfb()
    if xvfb is None:
        _skip("no private Xvfb available (the ambient display is never used)")
    if not _rebind_gtk():
        xvfb.terminate()
        _skip("Gtk could not open the private Xvfb")
    print(f"REALIZED-DISPLAY: {os.environ.get('DISPLAY', '')} (private Xvfb)")
    return xvfb


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
        _run_geometry_checks()
    finally:
        if xvfb is not None:
            xvfb.terminate()
    print("ALIGNMENT-REALIZED-OK")
    return 0


def _run_checks():
    from test_support import import_gui_fresh

    mp = import_gui_fresh("memory_page")
    ap = sys.modules["alignment_page"]  # real-bound by the fresh import above
    ch = sys.modules["charting"]  # real-bound alongside
    Gtk = mp.Gtk

    # REALIZED_CHART_RENDERER=cairo forces the Cairo fallbacks (rolling
    # charts and ladder) so the scroll/geometry checks run under both
    # renderers; the module cache must be flipped before any page builds.
    if os.environ.get("REALIZED_CHART_RENDERER") == "cairo":
        ch._backend = None

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
    print(f"REALIZED-RENDERER: {type(app._alignment_ladder).__name__}")
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


def _run_geometry_checks():
    """Lock the Performance page's widget geometry in realized windows.

    These are the regression locks for the redo complaints, measured the
    way the user sees them: every table window shows its fixed 20 lines
    whatever its row count, each overflowing table carries its own live
    horizontal scrollbar while the page itself never scrolls sideways
    (so each table's vertical scrollbar sits inside the visible width),
    the far-right column keeps its configured fixed width with the
    expand column absorbing slack, and the blocksize ladder never
    renders below its content minimum — a window narrower than the chart
    gets the ladder's own horizontal scrollbar instead of a clamp.
    """
    from test_support import import_gui_fresh

    mp = import_gui_fresh("memory_page")
    ap = sys.modules["alignment_page"]
    ch = sys.modules["charting"]
    gh = sys.modules["gui_helpers"]
    Gtk = mp.Gtk
    if os.environ.get("REALIZED_CHART_RENDERER") == "cairo":
        ch._backend = None

    class _App:
        pass

    class _UIStateStub:
        def bind_treeview(self, view, state_key):
            pass

    def pump(rounds=14):
        for _ in range(rounds):
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

    def build_page():
        app = _App()
        app.config = {}
        app.ctx = types.SimpleNamespace(zfs_caps=None)
        app._ui_state = _UIStateStub()
        return app, mp.create_memory_page(app)

    def show(page, width):
        win = Gtk.Window()
        win.set_default_size(width, 900)
        win.add(page)
        win.show_all()
        pump(20)
        return win

    def walk(widget, cls):
        found = []
        if isinstance(widget, cls):
            found.append(widget)
        for child in getattr(widget, "get_children", list)():
            found.extend(walk(child, cls))
        return found

    def scrollbar_live(sw, orientation):
        bar = getattr(sw, f"get_{orientation}scrollbar")()
        return bar is not None and bar.get_visible() and bar.get_child_visible()

    def assert_twenty_rows(name, sw, view):
        row_h = gh.treeview_row_height(view)
        header = row_h + 2
        height = sw.get_allocated_height()
        visible = (height - header) / row_h
        assert 19.4 <= visible <= 21.6, (
            f"{name}: window shows {visible:.1f} rows (alloc {height}, row {row_h})"
        )

    def assert_honest_last_column(name, view, sw):
        columns = view.get_columns()
        hadj = sw.get_hadjustment()
        widths = [c.get_width() for c in columns]
        assert hadj.get_upper() + 0.5 >= sum(widths), (
            f"{name}: horizontal range {hadj.get_upper()} < column sum {sum(widths)}"
        )
        # With the columns narrower than the view, the expand column takes
        # the slack and the last column keeps its configured width; with
        # them overflowing, every column keeps its fixed width.
        assert columns[-1].get_width() == columns[-1].get_fixed_width(), (
            f"{name}: last column renders {columns[-1].get_width()}, "
            f"configured {columns[-1].get_fixed_width()}"
        )

    def assert_own_scrollbars(name, sw, page_sw):
        hadj = sw.get_hadjustment()
        if hadj.get_upper() > hadj.get_page_size() + 0.5:
            assert scrollbar_live(sw, "h"), f"{name}: columns overflow but no own h-scrollbar"
            # The table window never widens past the page: its vertical
            # scrollbar sits at the visible right edge.
            assert sw.get_allocated_width() <= page_sw.get_allocated_width(), (
                f"{name}: table window {sw.get_allocated_width()} wider than page "
                f"{page_sw.get_allocated_width()}"
            )
        page_hadj = page_sw.get_hadjustment()
        assert page_hadj.get_upper() <= page_hadj.get_page_size() + 0.5, (
            "the page itself scrolls horizontally; tables must scroll on their own"
        )

    # --- A populated Alignment view at a comfortable width ---------------
    app, page = build_page()
    win = show(page, 1000)
    app._memory_view_stack.set_visible_child_name("alignment")
    pump()
    ap._apply_alignment_sample(app, _realized_sample())
    pump(20)
    page_sw = app.performance_scrolled
    # Every table window regardless of title (two tables lead with "Pool"):
    # fixed 20 rows, honest last column, own scrollbars, page never wider.
    # Hidden stack children (GtkStack never allocates them) are skipped by
    # the allocation guard inside the loop.
    for sw in walk(win, Gtk.ScrolledWindow):
        view = sw.get_child()
        if not isinstance(view, Gtk.TreeView) or sw.get_allocated_width() < 2:
            continue
        assert_twenty_rows("alignment table", sw, view)
        assert_honest_last_column("alignment table", view, sw)
        assert_own_scrollbars("alignment table", sw, page_sw)
    # The findings table's columns overflow a 970px page: its own
    # horizontal scrollbar must be live.
    findings = [
        sw
        for sw in walk(win, Gtk.ScrolledWindow)
        if isinstance(sw.get_child(), Gtk.TreeView)
        and sw.get_child().get_columns()[0].get_title() == "Severity"
    ]
    assert findings and scrollbar_live(findings[0], "h"), "findings table: no own h-scrollbar"
    # The ladder keeps its content minimum and scrolls on its own. The
    # minimum is computed the way the renderer requests it — with the
    # GUI-base-font scale the live canvas resolved.
    ladder = app._alignment_ladder
    lsw = app._alignment_ladder_scroll
    minimum = ch.ladder_minimum_width(ladder.pools, ch.chart_font_scale(ladder.widget))
    assert minimum > lsw.get_allocated_width(), "fixture ladder minimum should exceed the window"
    assert ladder.widget.get_allocated_width() >= minimum, (
        f"ladder canvas {ladder.widget.get_allocated_width()} clamped below its {minimum} minimum"
    )
    assert scrollbar_live(lsw, "h"), "ladder: window narrower than the chart but no h-scrollbar"
    print("PASS geometry: 20-row tables, own scrollbars, honest last column, ladder floor")
    win.destroy()
    pump()

    # --- The reproduced mid-width ladder clamp ---------------------------
    app2, page2 = build_page()
    win2 = show(page2, 700)
    app2._memory_view_stack.set_visible_child_name("alignment")
    pump()
    ap._apply_alignment_sample(app2, _realized_sample())
    pump(20)
    ladder2 = app2._alignment_ladder
    lsw2 = app2._alignment_ladder_scroll
    minimum2 = ch.ladder_minimum_width(ladder2.pools, ch.chart_font_scale(ladder2.widget))
    assert ladder2.widget.get_allocated_width() >= minimum2, (
        f"700px window: ladder canvas {ladder2.widget.get_allocated_width()} clamped "
        f"below its {minimum2} minimum (the max_content_width regression)"
    )
    assert scrollbar_live(lsw2, "h"), "700px window: ladder lost its horizontal scrollbar"
    for sw in walk(win2, Gtk.ScrolledWindow):
        view = sw.get_child()
        if isinstance(view, Gtk.TreeView) and sw.get_allocated_width() >= 2:
            assert_own_scrollbars("700px table", sw, app2.performance_scrolled)
    print("PASS geometry: ladder keeps its content minimum at a 700px window")
    win2.destroy()
    pump()

    # --- Empty tables keep their 20-line windows --------------------------
    _app3, page3 = build_page()
    win3 = show(page3, 1000)
    # The charts view is the default; its L2ARC/SLOG tables are empty.
    for sw in walk(win3, Gtk.ScrolledWindow):
        view = sw.get_child()
        if isinstance(view, Gtk.TreeView) and sw.get_allocated_width() >= 2:
            assert_twenty_rows("empty charts table", sw, view)
    print("PASS geometry: empty tables keep their 20-row windows")
    win3.destroy()
    pump()


if __name__ == "__main__":
    sys.exit(main())
