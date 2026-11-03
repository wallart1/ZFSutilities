#!/usr/bin/env python3
"""Realized-window natural-sizing check for the Backup page (child process).

Run directly (``python3 backup_realized_check.py``) or via
tests/python/test_backup_realized.py.  Builds the real Backup page (GTK 3)
inside a realized Gtk.Window with eleven pull steps and a window shorter
than the page's natural height — the reported defect geometry, where the
Pull Steps table was crushed to six visible rows behind its own scrollbar
— and asserts the table keeps every row visible while the page-level
scrollbar carries the overflow.

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

PULL_ROWS = 11
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


def _run_checks():
    from test_support import import_gui_fresh

    bp = import_gui_fresh("backup_page")
    import gui_helpers

    Gtk = bp.Gtk

    # The page reads two root-owned artifacts at build time: the
    # remembered-snapshot file and the snapshot-name lock.  Both move to
    # this check's scratch directory so the check runs as any user.
    scratch = tempfile.mkdtemp(prefix="backup-realized-")
    import feature_config

    feature_config.SNAPNAME_LOCK = os.path.join(scratch, "snapname.lock")
    feature_config.SNAPFILE = os.path.join(scratch, "snapname")
    bp.SNAPFILE = feature_config.SNAPFILE

    config = {
        "backup": {
            "pull_steps": [
                {
                    "active": True,
                    "source": f"host{i}:/etc",
                    "dest": f"/srv/pull{i}",
                    "excludes": [],
                }
                for i in range(PULL_ROWS)
            ],
            "send_receive_steps": [{"active": True, "source": "poolA/ds", "dest": "poolB"}],
        }
    }

    class _UIStateStub:
        """bind_treeview stand-in: the realized check does not persist widths."""

        def bind_treeview(self, view, state_key):
            pass

    class _App:
        pass

    app = _App()
    app.config = config
    app.ctx = types.SimpleNamespace(config=config)
    app._ui_state = _UIStateStub()
    app._save_config_button = Gtk.Button()
    app._backup_add_profile_btn = Gtk.Button()
    app.log_message = lambda *args, **kwargs: None

    page = bp.create_backup_page(app, app.ctx)

    win = Gtk.Window()
    # Shorter than the page's natural height: the defect showed exactly
    # here, with the viewport crushing the expanding step table.
    win.set_default_size(700, 560)
    win.add(page)
    win.show_all()

    def pump(rounds=10):
        for _ in range(rounds):
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

    pump(20)

    pull_store = app.backup_pull_store
    pull_scroll = _walk(
        win,
        lambda w: (
            isinstance(w, Gtk.ScrolledWindow)
            and isinstance(w.get_child(), Gtk.TreeView)
            and w.get_child().get_model() is pull_store
        ),
    )
    assert pull_scroll is not None, "pull steps scrolled window not found"
    view = pull_scroll.get_child()

    row_h = gui_helpers.treeview_row_height(view)
    header = row_h + 2
    alloc = pull_scroll.get_allocation()
    need = header + PULL_ROWS * row_h
    assert alloc.height >= need, (
        f"pull table crushed: {alloc.height}px < {need}px (header + {PULL_ROWS} rows @ {row_h}px)"
    )
    assert alloc.height <= need + SLACK_PX, (
        f"pull table window oversized: {alloc.height}px > {need + SLACK_PX}px"
    )

    vadj = pull_scroll.get_vadjustment()
    assert vadj.get_upper() <= vadj.get_page_size() + 1, (
        f"pull table scrolls internally: upper={vadj.get_upper()} page={vadj.get_page_size()}"
    )

    visible = view.get_visible_range()
    assert visible is not None, "pull view reports no visible range"
    start, end = visible
    first = start.get_indices()[0]
    last = end.get_indices()[0]
    assert last - first + 1 == PULL_ROWS, (
        f"only {last - first + 1} of {PULL_ROWS} pull rows visible"
    )

    page_vadj = page.get_vadjustment()
    assert page_vadj.get_upper() > page_vadj.get_page_size(), (
        "page-level scrollbar does not carry the overflow"
    )
    print(
        f"PASS natural sizing: pull table keeps {PULL_ROWS} rows "
        f"({alloc.height}px window, row {row_h}px) at a short page; "
        "page scrollbar carries the overflow"
    )


def main():
    # The GUI layer writes session logs; keep them out of /var and out of
    # the repo before anything imports the logging module.
    scratch_root = tempfile.mkdtemp(prefix="backup-realized-logs-")
    os.environ.setdefault("ZFSUTILITIES_LOG_DIR", scratch_root)
    xvfb = _ensure_display()
    try:
        _run_checks()
    finally:
        if xvfb is not None:
            xvfb.terminate()
    print("BACKUP-REALIZED-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
