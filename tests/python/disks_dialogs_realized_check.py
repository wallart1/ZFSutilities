#!/usr/bin/env python3
"""Realized-window natural-sizing check for the Disks-page dialogs (child process).

Run directly (``python3 disks_dialogs_realized_check.py``) or via
tests/python/test_disks_dialogs_realized.py.  Builds the real disk-picker
builder shared by the Add Data Vdev, Expand Vdev, Replace, Detach, Add
Infra Vdev, and Migrate Pool dialogs (and the Create Pool wizard's disks
page) inside a realized ``create_scrolled_dialog`` window, with a short
6-disk inventory and an overflowing 30-disk one — the geometry where the
picker stretched to fill the dialog whatever its row count and a short
window crushed the tables instead of scrolling — and asserts the picker
hugs its rows below the 20-row cap, scrolls inside beyond it, and the
dialog window itself carries the overflow.  Two further cases run the
real Migrate Pool dialog resized short (the geometry where the dialog
used to squeeze the new-disks picker toward its floor instead of
scrolling) and the real Disks page's three panes (every renderer must
END-ellipsize and every view must carry the cell-tooltip window; the
sections must stack Enclosures first, above the Disk Inventory and the
Pool Topology).

It runs as a child process on purpose: binding the GUI layer to real GTK
inside the pytest process would poison the mock-bound module caches the
other suites rely on.

Needs a display, and it must be one this script made itself: it starts a
private Xvfb and never opens the ambient display — a realized window
flashing on the operator's desktop mid-suite is exactly the leak this
guards against.  When no private display can be produced the check skips
rather than fall back.  Exit codes: 0 pass, 3 skip (no private display
available), anything else failure with a traceback on stderr.
"""

import os
import sys
import tempfile
import types
from unittest.mock import MagicMock

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
TESTS_SRC = os.path.join(REPO_ROOT, "tests", "python")
for path in (PYTHON_SRC, TESTS_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)

# Reuse the alignment check's display plumbing (private Xvfb, GTK env
# scrub, rebind dance) — importing it is side-effect free (main is guarded).
from alignment_realized_check import _ensure_display

FEW_ROWS = 6
MANY_ROWS = 30
# Pixel slack over the header + rows block: viewport borders and the
# one-row hscrollbar allowance (bounds are PIXEL-domain, never row units —
# a row-unit bound drifts with the host's row height).
SLACK_PX = 60


def _walk(widget, pred):
    if pred(widget):
        return widget
    get_children = getattr(widget, "get_children", None)
    if get_children is None:
        return None
    for child in get_children():
        found = _walk(child, pred)
        if found is not None:
            return found
    return None


def _picker_state(pgd, rows):
    """Return a picker state whose eligibility list carries *rows* disks."""
    from disk_repository import DiskInfo
    from pool_create import EligibilityResult

    eligibility = [
        EligibilityResult(
            disk=DiskInfo(
                name=f"sd{chr(ord('a') + i)}",
                path=f"/dev/sd{chr(ord('a') + i)}",
                by_id=f"ata-DISK{i}-serial{i}",
                model=f"Model {i}",
                size_human="4 TB",
                transport="sata",
            ),
            eligible=True,
            reasons=[],
            warnings=[],
        )
        for i in range(rows)
    ]
    return types.SimpleNamespace(eligibility=eligibility, selected=[])


def _build_dialog(pgd, gui_helpers, rows, size):
    """Return a realized picker dialog: (dialog, picker scroll, view)."""
    Gtk = pgd.Gtk

    dialog, content = gui_helpers.create_scrolled_dialog(
        "Realized Probe", None, [(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)], size=size
    )
    content.pack_start(
        pgd._build_disk_picker(_picker_state(pgd, rows), lambda: None, "Select disks."),
        False,
        False,
        0,
    )
    dialog.show_all()
    for _ in range(20):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)

    store = pgd.Gtk.ListStore  # real class; the picker's model is a ListStore
    picker_scroll = _walk(
        dialog,
        lambda w: (
            isinstance(w, Gtk.ScrolledWindow)
            and isinstance(w.get_child(), Gtk.TreeView)
            and isinstance(w.get_child().get_model(), store)
        ),
    )
    assert picker_scroll is not None, "picker scrolled window not found"
    return dialog, picker_scroll, picker_scroll.get_child()


def _check_real_migrate_dialog():
    """The real Migrate Pool dialog keeps its picker at natural size.

    The dialog is resized short (700x480) — well under its content's
    natural height — which is the geometry where a dialog viewport on the
    default MINIMUM vscroll policy squeezes its children toward their
    minimums instead of scrolling: the new-disks picker collapsed to a
    couple of rows. With the NATURAL policy the picker keeps its natural
    height (up to the 20-row cap), scrolls inside beyond the cap, and the
    dialog window carries the overflow.
    """
    from test_support import import_gui_fresh

    pmd = import_gui_fresh("pool_migrate_dialogs")
    import gui_helpers
    from zfs_repository import TopologyNode

    Gtk = pmd.Gtk
    from gi.repository import GLib

    def _node(name, vdev_type, children=()):
        return TopologyNode(name, vdev_type, "ONLINE", 0, 0, 0, None, list(children))

    eligibility = _picker_state(None, MANY_ROWS).eligibility
    disks = [result.disk for result in eligibility]
    state = pmd._MigrateState(
        pools=["pool1"],
        holding_pools=["pool1"],
        pool_name="pool1",
        mode=pmd.MIGRATE_NEW_DISKS,
        datasets_by_pool={"pool1": ["data"]},
        pool_alloc={"pool1": 10**9},
        pool_free={"pool1": 40 * 10**12},
        eligibility=eligibility,
        disks=disks,
        topologies={"pool1": _node("pool1", "pool", [_node("/dev/sda", "disk")])},
        existing_names={"pool1"},
        snap_name="@migrate-realized-probe",
        selected=disks[:2],
    )

    app = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)  # real transient parent
    app.ctx = MagicMock()
    app.config = {}

    captured = {}
    orig_create = pmd.create_scrolled_dialog

    def _capturing_create(title, parent, buttons, default_response=None, size=None):
        dialog, content = orig_create(title, parent, buttons, default_response, size)
        dialog.resize(700, 480)  # short window: overflow must scroll, not squeeze
        captured["dialog"] = dialog
        return dialog, content

    outcome = {}

    def _measure():
        dialog = captured.get("dialog")
        if dialog is None:
            return False
        try:
            for _ in range(40):
                while Gtk.events_pending():
                    Gtk.main_iteration_do(False)
            view = _walk(
                dialog,
                lambda w: (
                    isinstance(w, Gtk.TreeView)
                    and isinstance(w.get_model(), Gtk.ListStore)
                    and w.get_n_columns() == 6
                ),
            )
            assert view is not None, "new-disks picker treeview not found"
            scroll = view.get_parent()
            while scroll is not None and not isinstance(scroll, Gtk.ScrolledWindow):
                scroll = scroll.get_parent()
            outer = _walk(
                dialog,
                lambda w: (
                    isinstance(w, Gtk.ScrolledWindow) and isinstance(w.get_child(), Gtk.Viewport)
                ),
            )
            row_h = gui_helpers.treeview_row_height(view)
            header = row_h + 2
            cap = header + (gui_helpers.TABLE_ROW_TARGET + 1) * row_h
            n_rows = view.get_model().iter_n_children(None)
            need = header + min(n_rows, gui_helpers.TABLE_ROW_TARGET) * row_h
            alloc = scroll.get_allocation()
            assert alloc.height >= need - 2, (
                f"migrate picker squeezed: {alloc.height}px < {need}px "
                f"(header + {min(n_rows, gui_helpers.TABLE_ROW_TARGET)} rows @ {row_h}px)"
            )
            assert alloc.height <= cap + SLACK_PX, (
                f"migrate picker ignored the 20-row cap: {alloc.height}px > {cap + SLACK_PX}px"
            )
            picker_vadj = scroll.get_vadjustment()
            assert picker_vadj.get_upper() > picker_vadj.get_page_size(), (
                "migrate picker does not scroll inside beyond the cap"
            )
            outer_vadj = outer.get_vadjustment()
            assert outer_vadj.get_upper() > outer_vadj.get_page_size(), (
                "short migrate dialog window does not carry the overflow "
                f"(upper={outer_vadj.get_upper()} page={outer_vadj.get_page_size()})"
            )
            outcome["picker_px"] = alloc.height
        finally:
            dialog.response(Gtk.ResponseType.CANCEL)
        return False

    pmd.create_scrolled_dialog = _capturing_create
    try:
        GLib.timeout_add(600, _measure)
        pmd.show_migrate_pool_dialog(app, state)
    finally:
        pmd.create_scrolled_dialog = orig_create
    print(
        f"PASS real Migrate dialog: resized-short window scrolls; picker keeps "
        f"its natural height ({outcome['picker_px']}px)"
    )


def _check_disks_page_panes():
    """Every Disks-page pane ellipsizes its cells and enables cell tooltips.

    Real GTK, so the renderers are real objects: each of the three views'
    text columns must render END-ellipsized and the view must carry the
    tooltip window (``attach_cell_tooltips``), matching the universal
    table rule the user guide states. The page is also realized inside a
    shown window: every column's header button — which spans the full
    heading width, unlike the header label GTK seats inside it at natural
    text width — must carry the heading tooltip, so hovering any part of
    a heading explains the field. The realized page must also stack its
    sections in order: Enclosures is the first section of the page
    content, above the Disk Inventory and the Pool Topology.
    """
    from test_support import import_gui_fresh

    dp = import_gui_fresh("disks_page")
    from gi.repository import Pango

    dp.refresh_disks_page = lambda _app: None  # no background refresh here

    app = types.SimpleNamespace(
        ctx=MagicMock(),
        config={},
        enable_treeview_copy=MagicMock(),
    )
    # Hold the returned page widget for the assertions: once it is
    # garbage-collected the container tree is torn down and the views'
    # column lists empty (the app attributes keep only the bare views).
    page = dp.create_disks_page(app)
    assert isinstance(page, dp.Gtk.ScrolledWindow), "page wrap is not a ScrolledWindow"

    # Realize the page inside a shown window so the column header buttons
    # (and their labels) are allocated for the arming assertions below.
    window = dp.Gtk.Window()
    window.set_default_size(1280, 800)
    window.add(page)
    window.show_all()
    for _ in range(20):
        while dp.Gtk.events_pending():
            dp.Gtk.main_iteration_do(False)

    try:
        panes = [
            ("Disk Inventory", app.disks_view, 13),
            ("Enclosures", app.enclosures_view, 5),
            ("Pool Topology", app.disks_topology_view, 7),
        ]
        for name, view, expected_columns in panes:
            columns = view.get_columns()
            assert len(columns) == expected_columns, (
                f"{name}: expected {expected_columns} columns, found {len(columns)}"
            )
            for col in columns:
                renderer = col.get_cells()[0]
                ellipsize = renderer.get_property("ellipsize")
                assert ellipsize == Pango.EllipsizeMode.END, (
                    f"{name} column '{col.get_title()}' does not END-ellipsize ({ellipsize})"
                )
            assert view.get_has_tooltip(), f"{name} view carries no cell-tooltip window"

            for col in columns:
                title = col.get_title()
                label = col.get_widget()
                assert isinstance(label, dp.Gtk.Label), (
                    f"{name} column '{title}' has no header label widget"
                )
                tip = label.get_tooltip_text()
                assert tip, f"{name} column '{title}' label carries no tooltip"
                button = label.get_ancestor(dp.Gtk.Button)
                assert button is not None, (
                    f"{name} column '{title}' label has no header button ancestor"
                )
                assert button.get_tooltip_text() == tip, (
                    f"{name} column '{title}' header button is not armed with the label tooltip"
                )
                button_w = button.get_allocation().width
                column_w = col.get_width()
                assert abs(button_w - column_w) <= 2, (
                    f"{name} column '{title}' header button spans {button_w}px, "
                    f"not the column width {column_w}px"
                )

            # Dead-zone evidence on the widest heading: the label's strip is
            # far narrower than the button, so the button arming — not the
            # label — is what makes most of the heading tooltip-active.
            first = columns[0]
            first_button_w = first.get_widget().get_ancestor(dp.Gtk.Button).get_allocation().width
            first_label_w = first.get_widget().get_allocation().width
            assert first_button_w - first_label_w >= 40, (
                f"{name} first column heading: label strip ({first_label_w}px) already "
                f"covers the button ({first_button_w}px) — dead-zone law no longer holds"
            )

        # Section order: Enclosures is the first section of the page. The
        # bold section titles are Gtk.Labels carrying bold markup. The Disk
        # Inventory and Pool Topology titles sit directly in the page
        # content box; Enclosures is a box of its own inside it.
        def _section_title(text):
            label = _walk(
                window,
                lambda w: isinstance(w, dp.Gtk.Label) and w.get_label() == f"<b>{text}</b>",
            )
            assert label is not None, f"'{text}' section title not found"
            return label

        texts = ("Enclosures", "Disk Inventory", "Pool Topology")
        titles = {text: _section_title(text) for text in texts}
        enclosures_box = titles["Enclosures"].get_parent()
        content_box = titles["Disk Inventory"].get_parent()
        assert content_box is titles["Pool Topology"].get_parent(), (
            "Disk Inventory and Pool Topology titles are not packed in the same box"
        )
        assert enclosures_box.get_parent() is content_box, (
            "Enclosures section box is not packed in the page content box"
        )
        children = content_box.get_children()
        assert children and children[0] is enclosures_box, (
            "Enclosures is not the first section of the page content"
        )
        # Same parent, so the allocations compare directly.
        inventory_y = titles["Disk Inventory"].get_allocation().y
        topology_y = titles["Pool Topology"].get_allocation().y
        assert enclosures_box.get_allocation().y < inventory_y, (
            "Enclosures section does not sit above the Disk Inventory"
        )
        assert inventory_y < topology_y, "Disk Inventory does not sit above the Pool Topology"
        print(
            "PASS Disks-page panes: all three views END-ellipsize with cell "
            "tooltips; every full-width header button carries the heading tooltip; "
            "Enclosures is the first section, above Disk Inventory and Pool Topology"
        )
    finally:
        window.destroy()


def _run_checks():
    from test_support import import_gui_fresh

    pgd = import_gui_fresh("pool_growth_dialogs")
    import gui_helpers

    Gtk = pgd.Gtk
    target = gui_helpers.TABLE_ROW_TARGET

    # --- Short inventory: the picker hugs its rows, never fills the dialog.
    dialog, scroll, view = _build_dialog(pgd, gui_helpers, FEW_ROWS, (640, 520))
    try:
        row_h = gui_helpers.treeview_row_height(view)
        header = row_h + 2
        need = header + FEW_ROWS * row_h
        alloc = scroll.get_allocation()
        assert alloc.height >= need, (
            f"picker crushed: {alloc.height}px < {need}px (header + {FEW_ROWS} rows @ {row_h}px)"
        )
        assert alloc.height <= need + SLACK_PX, (
            f"picker stretched to fill the dialog: {alloc.height}px "
            f"> {need + SLACK_PX}px (header + {FEW_ROWS} rows @ {row_h}px)"
        )

        outer = _walk(
            dialog,
            lambda w: isinstance(w, Gtk.ScrolledWindow) and isinstance(w.get_child(), Gtk.Viewport),
        )
        assert outer is not None, "dialog content scrolled window not found"
        assert outer.get_child().get_vscroll_policy() == Gtk.ScrollablePolicy.NATURAL, (
            "dialog viewport is not on the NATURAL vscroll policy"
        )
        vadj = outer.get_vadjustment()
        assert vadj.get_upper() <= vadj.get_page_size() + 1, (
            "short inventory should fit without a dialog scrollbar "
            f"(upper={vadj.get_upper()} page={vadj.get_page_size()})"
        )
        print(
            f"PASS natural sizing: {FEW_ROWS}-row picker hugs its rows "
            f"({alloc.height}px window, row {row_h}px)"
        )
    finally:
        dialog.destroy()

    # --- Overflowing inventory: the picker caps near the row target and
    # scrolls inside, and the dialog window carries the overflow.
    dialog, scroll, view = _build_dialog(pgd, gui_helpers, MANY_ROWS, (640, 520))
    try:
        row_h = gui_helpers.treeview_row_height(view)
        header = row_h + 2
        cap = header + (target + 1) * row_h
        alloc = scroll.get_allocation()
        assert alloc.height <= cap + SLACK_PX, (
            f"picker ignored the {target}-row cap: {alloc.height}px > "
            f"{cap + SLACK_PX}px (header + {target + 1} rows @ {row_h}px)"
        )
        picker_vadj = scroll.get_vadjustment()
        assert picker_vadj.get_upper() > picker_vadj.get_page_size(), (
            f"picker does not scroll inside: upper={picker_vadj.get_upper()} "
            f"page={picker_vadj.get_page_size()}"
        )

        outer = _walk(
            dialog,
            lambda w: isinstance(w, Gtk.ScrolledWindow) and isinstance(w.get_child(), Gtk.Viewport),
        )
        outer_vadj = outer.get_vadjustment()
        assert outer_vadj.get_upper() > outer_vadj.get_page_size(), (
            "dialog scrollbar does not carry the overflow "
            f"(upper={outer_vadj.get_upper()} page={outer_vadj.get_page_size()})"
        )
        print(
            f"PASS natural sizing: {MANY_ROWS}-row picker scrolls inside at the "
            f"{target}-row cap ({alloc.height}px window); dialog window scrolls"
        )
    finally:
        dialog.destroy()

    # --- The real Migrate Pool dialog, resized short: the picker keeps its
    # natural height and the window scrolls instead of squeezing it.
    _check_real_migrate_dialog()

    # --- The real Disks page's three panes: END-ellipsized renderers and
    # cell tooltips on every view.
    _check_disks_page_panes()


def main():
    # The GUI layer writes session logs; keep them out of /var and out of
    # the repo before anything imports the logging module.
    scratch_root = tempfile.mkdtemp(prefix="disks-dialogs-realized-logs-")
    os.environ.setdefault("ZFSUTILITIES_LOG_DIR", scratch_root)
    xvfb = _ensure_display()
    try:
        _run_checks()
    finally:
        if xvfb is not None:
            xvfb.terminate()
    print("DISKS-DIALOGS-REALIZED-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
