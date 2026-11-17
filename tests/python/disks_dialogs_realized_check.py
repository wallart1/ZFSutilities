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
dialog window itself carries the overflow.

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
