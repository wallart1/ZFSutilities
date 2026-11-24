#!/usr/bin/env python3
"""Realized-window check for the Datasets page mount-order warning banner.

Run directly (``python3 datasets_banner_realized_check.py``) or via
tests/python/test_datasets_banner_realized.py.  Builds the real Datasets
page (GTK 3) inside a realized window and drives the banner contract end
to end: the label stays hidden through ``show_all`` (no-show-all), the
clean state keeps it hidden, findings from the same unreachable-mount
detector the Dashboard uses make it visible with the count and the
Dashboard pointer, and a later clean check hides it again — the
repair-done path.

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
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
TESTS_SRC = os.path.join(REPO_ROOT, "tests", "python")
for path in (PYTHON_SRC, TESTS_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)

# Reuse the alignment check's display plumbing (private Xvfb, GTK env
# scrub, rebind dance) — importing it is side-effect free (main is guarded).
from alignment_realized_check import _ensure_display

_FINDINGS = [
    {"name": "tank/vm-100", "mountpoint": "/tank/vm-100"},
    {"name": "tank/vm-101", "mountpoint": "/tank/vm-101"},
]


def _pump(Gtk, rounds=20):
    for _ in range(rounds):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)


def _run_checks():
    from test_support import import_gui_fresh

    dsp = import_gui_fresh("datasets_page")
    Gtk = dsp.Gtk

    app = types.SimpleNamespace(
        ctx=types.SimpleNamespace(
            zfs_repository=types.SimpleNamespace(list_pools=list),
            config={},
        ),
        _ui_state=types.SimpleNamespace(bind_treeview=lambda *args, **kwargs: None),
    )
    window = Gtk.Window()
    window.set_default_size(900, 600)
    window.add(dsp.create_datasets_page(app))
    window.show_all()
    _pump(Gtk)
    banner = app._ds_mount_order_warning

    try:
        # show_all must not map the banner: no_show_all keeps it out of
        # every bulk show, so only the detector decides.
        assert not banner.get_visible(), "banner visible after show_all"

        with patch.object(dsp, "find_unreachable_mounts", return_value=[]):
            dsp._update_ds_mount_order_warning(app)
        assert not banner.get_visible(), "banner visible with no findings"

        with patch.object(dsp, "find_unreachable_mounts", return_value=_FINDINGS):
            dsp._update_ds_mount_order_warning(app)
        assert banner.get_visible(), "banner hidden with findings"
        _pump(Gtk)
        markup = banner.get_text()
        assert "2 mounted datasets" in markup, f"count missing from banner text: {markup!r}"
        assert "Dashboard" in markup, f"Dashboard pointer missing: {markup!r}"
        assert "Repair Mount Order" in markup, f"repair pointer missing: {markup!r}"
        print("PASS banner: hidden when clean, visible with findings and Dashboard pointer")

        # The repair-done path: the next refresh hides the banner again.
        with patch.object(dsp, "find_unreachable_mounts", return_value=[]):
            dsp._update_ds_mount_order_warning(app)
        assert not banner.get_visible(), "banner stayed visible after findings cleared"
        print("PASS banner: hides again once the detector is clean")
    finally:
        window.destroy()


def main():
    # The GUI layer writes session logs; keep them out of /var and out of
    # the repo before anything imports the logging module.
    scratch_root = tempfile.mkdtemp(prefix="datasets-banner-realized-logs-")
    os.environ.setdefault("ZFSUTILITIES_LOG_DIR", scratch_root)
    xvfb = _ensure_display()
    try:
        _run_checks()
    finally:
        if xvfb is not None:
            xvfb.terminate()
    print("DATASETS-BANNER-REALIZED-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
