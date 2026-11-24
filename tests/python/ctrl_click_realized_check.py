#!/usr/bin/env python3
"""Realized-window check: one Ctrl-click deselects a wired TreeView row.

Run directly (``python3 ctrl_click_realized_check.py``) or via
tests/python/test_ctrl_click_realized.py.  Builds real GTK 3 TreeViews in
a realized Gtk.Window — one wired through
``gui_helpers.enable_ctrl_click_deselect`` in MULTIPLE mode, one UNWIRED
in MULTIPLE mode, one wired in SINGLE mode — puts keyboard focus on an
unrelated button, selects a row in each view, and sends ONE synthesized
Ctrl+click (Gdk.EventButton.put on the view's bin window; the focus-gate
lives in GTK widget code, so a synthesized event exercises the exact
decision path a real X click reaches).

Expected: the wired views deselect in one click; the unwired view keeps
its selection on the first click (GTK's focus gate) and deselects on the
second — the unwired view doubles as a regression sentinel, so a GTK
behavior change (a GTK4 migration, say) fails this check instead of
silently stranding the workaround.

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
import time

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
TESTS_SRC = os.path.join(REPO_ROOT, "tests", "python")
for path in (PYTHON_SRC, TESTS_SRC):
    if path not in sys.path:
        sys.path.insert(0, path)

# Reuse the alignment check's display plumbing (private Xvfb, GTK env
# scrub, rebind dance) — importing it is side-effect free (main is
# guarded).  All gi/GTK/gui_helpers imports stay INSIDE _run_checks, after
# _ensure_display has bound GTK to the private display — a top-level GTK
# import would run before the env scrub and load the wrong Gdk version.
from alignment_realized_check import _ensure_display

ROWS = 12
TARGET = 3  # the row being deselected in every view


def _run_checks():
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk
    from gui_helpers import enable_ctrl_click_deselect

    def build_view(mode, wired):
        store = Gtk.ListStore(str)
        for i in range(ROWS):
            store.append([f"row {i}"])
        view = Gtk.TreeView(model=store)
        view.get_selection().set_mode(mode)
        view.append_column(Gtk.TreeViewColumn("Name", Gtk.CellRendererText(), text=0))
        if wired:
            enable_ctrl_click_deselect(view)
        return view

    def selected_paths(view):
        _model, paths = view.get_selection().get_selected_rows()
        return [str(path) for path in paths]

    class Probe:
        def __init__(self):
            self.win = Gtk.Window(title="ctrl-click realized check")
            self.win.set_default_size(600, 700)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.win.add(box)
            # Unrelated widget holding keyboard focus when the clicks arrive.
            self.bait = Gtk.Button(label="focus bait")
            box.pack_start(self.bait, False, False, 0)
            self.views = {
                "wired-multiple": build_view(Gtk.SelectionMode.MULTIPLE, True),
                "unwired-multiple": build_view(Gtk.SelectionMode.MULTIPLE, False),
                "wired-single": build_view(Gtk.SelectionMode.SINGLE, True),
            }
            for label, view in self.views.items():
                frame = Gtk.Frame(label=label)
                frame.add(view)
                box.pack_start(frame, True, True, 0)
            self.win.show_all()
            self.pointer = Gdk.Display.get_default().get_default_seat().get_pointer()

        def pump(self, seconds=0.5):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                while Gtk.events_pending():
                    Gtk.main_iteration()
                time.sleep(0.02)

        def select_target(self, view):
            selection = view.get_selection()
            selection.unselect_all()
            selection.select_path(Gtk.TreePath.new_from_indices([TARGET]))
            # Cursor ON the clicked row, so the focus gate is the only thing
            # that can block the toggle.
            view.set_cursor(Gtk.TreePath.new_from_indices([TARGET]))

        def ctrl_click_target(self, view):
            path = Gtk.TreePath.new_from_indices([TARGET])
            area = view.get_cell_area(path, view.get_column(0))
            bin_window = view.get_bin_window()
            _same, ox, oy = bin_window.get_origin()
            x = float(area.x + max(area.width // 2, 5))
            y = float(area.y + area.height // 2)
            for event_type in (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE):
                event = Gdk.EventButton.new(event_type)
                event.window = bin_window
                event.send_event = True
                event.time = Gdk.CURRENT_TIME
                event.x = x
                event.y = y
                event.x_root = float(ox + x)
                event.y_root = float(oy + y)
                event.state = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.BUTTON1_MASK
                event.button = 1
                event.device = self.pointer
                event.put()
            self.pump()

    probe = Probe()
    probe.win.present()
    results = []

    def check(label, condition, detail):
        results.append((label, condition, detail))
        state = "PASS" if condition else "FAIL"
        print(f"{state} {label}: {detail}")

    # Scenario 1: wired MULTIPLE view, focus on the bait button.
    probe.select_target(probe.views["wired-multiple"])
    probe.bait.grab_focus()
    probe.pump()
    before = selected_paths(probe.views["wired-multiple"])
    probe.ctrl_click_target(probe.views["wired-multiple"])
    after = selected_paths(probe.views["wired-multiple"])
    check(
        "wired multiple deselects in one click",
        after == [],
        f"selected {before} -> {after}",
    )

    # Scenario 2: unwired MULTIPLE view — the stock GTK behavior this
    # campaign fixes, and the sentinel for GTK itself changing.
    unwired = probe.views["unwired-multiple"]
    probe.select_target(unwired)
    probe.bait.grab_focus()
    probe.pump()
    probe.ctrl_click_target(unwired)
    one_click = selected_paths(unwired)
    probe.ctrl_click_target(unwired)
    two_clicks = selected_paths(unwired)
    check(
        "unwired view keeps selection on first click (GTK focus gate intact)",
        one_click != [],
        f"selected after one click: {one_click}",
    )
    check(
        "unwired view deselects on second click",
        two_clicks == [],
        f"selected after two clicks: {two_clicks}",
    )

    # Scenario 3: wired SINGLE view.
    probe.select_target(probe.views["wired-single"])
    probe.bait.grab_focus()
    probe.pump()
    probe.ctrl_click_target(probe.views["wired-single"])
    after = selected_paths(probe.views["wired-single"])
    check(
        "wired single deselects in one click",
        after == [],
        f"selected ['{TARGET}'] -> {after}",
    )

    if all(condition for _label, condition, _detail in results):
        print("CTRL-CLICK-REALIZED-OK")
        return 0
    return 1


def main():
    xvfb = _ensure_display()
    if xvfb is None:
        print("SKIP: no private display")
        return 3
    try:
        return _run_checks()
    finally:
        xvfb.terminate()


if __name__ == "__main__":
    sys.exit(main())
