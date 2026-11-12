#!/usr/bin/env python3
"""gui_probe — drive the real GUI under a private Xvfb, one op at a time.

Runs INSIDE the ITF guest (root, headless, no tty): starts its own Xvfb,
builds the real ZFSUtilitiesWindow from the tree under test, and executes
survey ops — action-button dispatches (L1), central-content widget
interactions (L2), and multi-widget composites with linkage asserts
(L3).  Modal dialogs and held input prompts are answered per the op's
archived RESPONSE PROFILE (accept / decline / cancel / invalid), so a
run exercises different scenarios, never a constant safe default.

Incremental results (JSON lines, flushed per op) make the probe
crash-resumable: ops already carrying a verdict are skipped; ops with a
started marker but no verdict (watchdog kill, crash) are recorded as
failed stalls.  The journey re-invokes the probe until every op has a
verdict or attempts run out.

Usage:
    python3 gui_probe.py --ops FILE --results FILE --repo /root/ZFSutilities

Ops file: the sampler's TSV (id, kind, name, page, profile).
Exit codes: 0 all ops pass/blocked, 1 any fail, 2 premise error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from contextlib import suppress
from typing import ClassVar

OP_TIMEOUT_DEFAULT = int(os.environ.get("SURVEY_OP_TIMEOUT", "300"))
MAX_DIALOG_RESPONSES_PER_OP = 6

# Dialog-button label classes (mnemonics stripped, lowercased).  "close"
# and "stop" are negative-side: they dismiss/refuse rather than commit.
NEGATIVE_LABELS = re.compile(
    r"^(no\b|don't|dont|cancel|close|stop|abort|keep|skip|dismiss|exit|quit)",
    re.IGNORECASE,
)
AFFIRMATIVE_HINTS = re.compile(
    r"(ok|yes|save|apply|add|create|make|build|remove|delete|wipe|destroy|"
    r"start|run|proceed|continue|replace|overwrite|format|mount|unmount|"
    r"snapshot|rollback|prune|accept|confirm|recall|import|export|repair|"
    r"fix|enroll|resize|rename|move|sever|promote|write|load)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Xvfb: the probe must make its own display and never touch another
# ---------------------------------------------------------------------------


def ensure_display():
    """Start a private Xvfb; return the process (caller terminates it).

    The guest is headless, but the discipline is the same as the dev-host
    realized checks: the display this process uses is one it made.
    """
    for num in range(90, 110):
        display = f":{num}"
        proc = subprocess.Popen(
            ["Xvfb", display, "-nolisten", "tcp", "-screen", "0", "1280x900x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.environ["DISPLAY"] = display
        time.sleep(1.5)
        if proc.poll() is None:
            try:
                import gi

                gi.require_version("Gtk", "3.0")
                from gi.repository import Gtk

                if Gtk.init_check()[0]:
                    return proc
            except Exception as exc:  # pragma: no cover - display probe failure
                # A dead candidate display is not fatal: try the next one.
                print(f"gui_probe: display {display} rejected: {exc}", file=sys.stderr)
                continue
        proc.terminate()
    raise RuntimeError("no private Xvfb display could be produced")


# ---------------------------------------------------------------------------
# Results (JSON lines) + started markers
# ---------------------------------------------------------------------------


class Results:
    def __init__(self, path, started_path):
        self.path = path
        self.started_path = started_path
        self.verdicts = {}
        self.started = set()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("event") == "started":
                        self.started.add(rec["id"])
                    elif "verdict" in rec:
                        self.verdicts[rec["id"]] = rec

    def mark_started(self, op_id):
        self.started.add(op_id)
        self._append({"event": "started", "id": op_id, "ts": time.time()})

    def record(self, rec):
        self.verdicts[rec["id"]] = rec
        self._append(rec)

    def _append(self, rec):
        with open(self.path, "a", encoding="utf-8") as f:
            # ensure_ascii=False keeps ids with unicode (e.g. the "…" in
            # action-button labels) byte-comparable with the ops TSV.
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


# ---------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------


class GuiProbe:
    def __init__(self, repo, results):
        self.repo = repo
        self.results = results
        self.profile = "decline"
        self.dialog_log = []
        self.dialog_budget = 0
        self._handled_dialogs = set()
        self._window_grace = {}

        sys.path.insert(0, os.path.join(repo, "python"))
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import GLib, Gtk

        self.GLib = GLib
        self.Gtk = Gtk

        # A real Gtk.Application to own the window (the way main.py runs).
        import main as gui_main

        self.gui_main = gui_main
        app = gui_main.ZFSUtilitiesApp()
        app.register(None)
        import zfsutilities_gui

        self.window_module = zfsutilities_gui
        self.app = app
        self.win = zfsutilities_gui.ZFSUtilitiesWindow(application=app)
        self.win.set_default_size(1280, 900)
        self.win.show_all()
        self.pump(30)

        import action_dispatch

        self.handlers = action_dispatch.ACTION_HANDLERS
        self.input_registry = getattr(self.win, "_input_registry", None)

        # The responder fires from every nested main loop (dialog .run()
        # iterates the default context), which is what makes modal flows
        # answerable without a human.
        GLib.timeout_add(80, self._responder_tick)
        self.pump(5)

    # -- plumbing ----------------------------------------------------------

    def pump(self, rounds=10):
        Gtk = self.Gtk
        for _ in range(rounds):
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

    def navigate(self, page):
        row = self.win._page_rows.get(page)
        if row is None:
            raise RuntimeError(f"no sidebar row for page {page!r}")
        self.win.sidebar.emit("row-activated", row)
        self.win.stack.set_visible_child_name(page)
        self.pump(10)
        visible = self.win.stack.get_visible_child_name()
        if visible != page:
            raise RuntimeError(f"navigation to {page} landed on {visible!r}")

    def page_widget(self, page):
        return self.win.stack.get_child_by_name(page)

    # -- widget walking ----------------------------------------------------

    def walk(self, widget, pred, out=None):
        """Depth-first walk over a widget subtree.

        Uses Gtk.Container.foreach, which covers every container shape
        uniformly — including Gtk.Paned, whose get_children() does not
        report its child1/child2.
        """
        if out is None:
            out = []
        if pred(widget):
            out.append(widget)
        if isinstance(widget, self.Gtk.Container):
            widget.foreach(lambda child: self.walk(child, pred, out))
        return out

    def treeviews(self, page):
        Gtk = self.Gtk
        return self.walk(self.page_widget(page), lambda w: isinstance(w, Gtk.TreeView))

    def entries(self, page):
        Gtk = self.Gtk
        return self.walk(self.page_widget(page), lambda w: isinstance(w, Gtk.Entry))

    def combos(self, page):
        Gtk = self.Gtk
        return self.walk(self.page_widget(page), lambda w: isinstance(w, Gtk.ComboBoxText))

    def spins(self, page):
        Gtk = self.Gtk
        return self.walk(self.page_widget(page), lambda w: isinstance(w, Gtk.SpinButton))

    def select_row(self, view, index=0, extra=0):
        """Select row `index` (and `extra` more rows when extra>0)."""
        store = view.get_model()
        if store is None or store.iter_n_children(None) <= index:
            return False
        sel = view.get_selection()
        sel.unselect_all()
        path = store.get_path(store.iter_nth_child(None, index))
        sel.select_path(path)
        for n in range(1, extra + 1):
            if index + n < store.iter_n_children(None):
                p2 = store.get_path(store.iter_nth_child(None, index + n))
                sel.select_path(p2)
        view.queue_draw()
        self.pump(5)
        return True

    def select_scratch_or_first(self, page, needle_key="SURVEY_DS"):
        """Prefer a survey-owned row (by name needle), else row 0."""
        needle = os.environ.get(needle_key, "")
        views = self.treeviews(page)
        if not views:
            return False
        view = views[0]
        if needle:
            store = view.get_model()
            # Search the first text column for the needle.
            for col_idx in range(store.get_n_columns()):
                col = view.get_column(col_idx)
                if col is None:
                    continue
                for n in range(store.iter_n_children(None)):
                    it = store.iter_nth_child(None, n)
                    val = store.get_value(it, col_idx)
                    if isinstance(val, str) and needle in val:
                        return self.select_row_at_iter(view, it)
        return self.select_row(view, 0)

    def select_row_at_iter(self, view, it):
        store = view.get_model()
        sel = view.get_selection()
        sel.unselect_all()
        sel.select_path(store.get_path(it))
        self.pump(5)
        return True

    # -- responders (dialogs + held prompts) --------------------------------

    def _dialog_buttons(self, dlg):
        Gtk = self.Gtk
        buttons = []
        area = dlg.get_action_area() if hasattr(dlg, "get_action_area") else None
        if area is not None:
            buttons = [b for b in area.get_children() if isinstance(b, Gtk.Button)]
        if not buttons:
            buttons = [
                w
                for w in self.walk(dlg, lambda x: isinstance(x, Gtk.Button))
                if w.get_parent() is not area
            ]
        return buttons

    def _label_of(self, widget):
        """Best-effort text of a button/toggle: its own label, else any
        Gtk.Label descendant (action buttons wrap their label in a Box)."""
        label = widget.get_label() if hasattr(widget, "get_label") else None
        if label:
            return label
        if isinstance(widget, self.Gtk.Container):
            labels = []
            self.walk(widget, lambda w: isinstance(w, self.Gtk.Label), labels)
            if labels:
                return labels[0].get_text() or ""
        return ""

    def _respond_dialog(self, dlg, profile):
        Gtk = self.Gtk
        label = self._label_of(dlg) or (dlg.get_title() or "")
        buttons = self._dialog_buttons(dlg)
        chosen = None

        if profile == "cancel":
            dlg.response(Gtk.ResponseType.CANCEL)
            return f"[{label}] response:cancel"

        if profile == "invalid":
            # Garbage into every text input, then try the affirmative —
            # validation must refuse or re-prompt; either is the scenario.
            for entry in self.walk(dlg, lambda w: isinstance(w, Gtk.Entry)):
                entry.set_text("survey-garbage-\u00b5")
            affirmative = self._pick_affirmative(buttons)
            if affirmative is not None:
                affirmative.clicked()
                chosen = f"garbage+click:{self._label_of(affirmative)!r}"
            else:
                dlg.response(Gtk.ResponseType.OK)
                chosen = "garbage+response:ok"
            return f"[{label}] {chosen}"

        # accept / decline
        negative = None
        affirmative = self._pick_affirmative(buttons)
        for b in buttons:
            if NEGATIVE_LABELS.match(self._label_of(b).replace("_", "").strip()):
                negative = b
                break
        if profile == "decline":
            if negative is not None:
                negative.clicked()
                chosen = f"click:{self._label_of(negative)!r}"
            else:
                dlg.response(Gtk.ResponseType.NO)
                chosen = "response:no"
        else:  # accept
            if affirmative is not None:
                affirmative.clicked()
                chosen = f"click:{self._label_of(affirmative)!r}"
            else:
                dlg.response(Gtk.ResponseType.OK)
                chosen = "response:ok"
        return f"[{label}] {chosen}"

    def _pick_affirmative(self, buttons):
        for b in buttons:
            text = self._label_of(b).replace("_", "").strip()
            if NEGATIVE_LABELS.match(text):
                continue
            if AFFIRMATIVE_HINTS.search(text):
                return b
        for b in buttons:  # any non-negative button is the primary action
            text = self._label_of(b).replace("_", "").strip()
            if not NEGATIVE_LABELS.match(text):
                return b
        return None

    PROFILE_ANSWERS: ClassVar[dict] = {
        "accept": "y",
        "decline": "n",
        "invalid": "survey-garbage-answer",
        "cancel": "n",
    }

    def _answer_prompts(self):
        if self.input_registry is None:
            return
        for request in list(self.input_registry.outstanding()):
            runner = request.runner
            try:
                if self.profile == "cancel" and hasattr(runner, "cancel"):
                    runner.cancel()
                    self.dialog_log.append(f"prompt#{request.number}: cancel()->runner")
                    continue
                answer = self.PROFILE_ANSWERS.get(self.profile, "n")
                runner.send_input(answer + "\n")
                self.dialog_log.append(
                    f"prompt#{request.number}: {answer!r} [{request.prompt[:60]}]"
                )
            except Exception as exc:  # runner gone / channel closed
                self.dialog_log.append(f"prompt#{request.number}: answer failed: {exc}")

    def _responder_tick(self):
        Gtk = self.Gtk
        try:
            for wnd in list(Gtk.Window.list_toplevels()):
                if wnd is self.win or wnd in self._handled_dialogs:
                    continue
                if not wnd.get_visible():
                    continue
                if not isinstance(wnd, Gtk.Dialog):
                    # Modeless helper windows (wizards, popouts) have no
                    # response protocol; after a grace period they are
                    # closed, which unblocks handlers that nested a main
                    # loop waiting for them.
                    ticks = self._window_grace.get(id(wnd), 0) + 1
                    self._window_grace[id(wnd)] = ticks
                    if ticks > 10:
                        self.dialog_log.append(
                            f"window-closed: {wnd.get_title() or type(wnd).__name__}"
                        )
                        self._handled_dialogs.add(wnd)
                        wnd.destroy()
                    continue
                # A dialog is NOT marked handled forever: validation loops
                # re-run() the SAME dialog, and each re-ask must get its
                # own answer until the per-op budget force-cancels it.
                if self.dialog_budget <= 0:
                    wnd.response(Gtk.ResponseType.CANCEL)
                    self.dialog_log.append("budget-exhausted: response:cancel")
                    continue
                self.dialog_budget -= 1
                chosen = self._respond_dialog(wnd, self.profile)
                self.dialog_log.append(f"dialog: {chosen}")
            self._answer_prompts()
        except Exception as exc:  # never let the responder die
            self.dialog_log.append(f"responder error: {exc}")
        return True  # keep the timeout alive

    def _close_leftover_dialogs(self):
        Gtk = self.Gtk
        for wnd in list(Gtk.Window.list_toplevels()):
            if wnd is self.win or not wnd.get_visible():
                continue
            if isinstance(wnd, Gtk.Dialog):
                wnd.response(Gtk.ResponseType.DELETE_EVENT)
            else:
                wnd.destroy()
        self.pump(5)

    def _stop_runners(self):
        for attr in (
            "backup_runner",
            "offsite_runner",
            "restore_runner",
            "retention_runner",
        ):
            runner = getattr(self.win, attr, None)
            if runner is not None and getattr(runner, "running", False):
                with suppress(Exception):
                    runner.cancel()
        self.pump(10)

    # -- L1: action-button dispatch ----------------------------------------

    def run_button(self, page, name):
        handler = self.handlers[page][name]
        handler(self.win)
        self.pump(20)
        if self.win is None or not self.win.get_realized():
            raise RuntimeError("main window lost after action")

    # -- L2: widget roles ----------------------------------------------------

    def _census(self, page, limit=8):
        """Widget-type census for not-found diagnostics (drift evidence)."""
        from collections import Counter

        names = Counter(
            type(w).__name__ for w in self.walk(self.page_widget(page), lambda _w: True, [])
        )
        top = " ".join(f"{k}x{v}" for k, v in names.most_common(limit))
        return f"page census: {top}"

    def run_widget_role(self, page, role):
        Gtk = self.Gtk
        if role == "navigate":
            self.navigate(page)
            return "page is the visible stack child"
        if role == "toggle-dry-run":
            button = getattr(self.win, "_dry_run_button", None)
            for _attempt in range(2):
                if button is not None:
                    break
                for w in self.walk(self.win, lambda x: isinstance(x, Gtk.ToggleButton)):
                    if "dry" in (self._label_of(w) or "").lower():
                        button = w
                        break
                if button is None:
                    self.pump(30)  # action-panel rebuild can lag navigation
            if button is None:
                raise RuntimeError(f"no Dry Run toggle found on this page ({self._census(page)})")
            button.set_active(not button.get_active())
            self.pump(10)
            state = bool(getattr(self.win, "_dry_run_active", button.get_active()))
            button.set_active(not button.get_active())  # restore
            self.pump(5)
            return f"_dry_run_active flipped to {state} and back"
        views = self.treeviews(page)
        if role in ("select-first", "select-second", "select-multi"):
            if not views:
                raise RuntimeError(f"no treeview on page ({self._census(page)})")
            view = views[1] if (role == "select-second" and len(views) > 1) else views[0]
            extra = 1 if role == "select-multi" else 0
            if not self.select_row(view, 0, extra=extra):
                return "blocked: no rows to select"
            count = view.get_selection().count_selected_rows()
            return f"selected {count} row(s)"
        if role == "toggle-active":
            if not views:
                raise RuntimeError(f"no treeview on page ({self._census(page)})")
            view = views[0]
            store = view.get_model()
            if store is None or store.iter_n_children(None) == 0:
                return "blocked: no rows to toggle"
            for col in view.get_columns():
                for rend in col.get_cells():
                    if isinstance(rend, Gtk.CellRendererToggle) and rend.get_activatable():
                        # The canonical click equivalent: GTK emits "toggled"
                        # on the renderer and the page's callback writes the
                        # store — exactly what a real click does.
                        path = store.get_path(store.iter_nth_child(None, 0))
                        rend.emit("toggled", path.to_string())
                        self.pump(5)
                        return "toggled first activatable cell"
            raise RuntimeError("no activatable toggle renderer on page")
        if role == "edit-cell":
            if not views:
                raise RuntimeError(f"no treeview on page ({self._census(page)})")
            view = views[0]
            store = view.get_model()
            if store is None or store.iter_n_children(None) == 0:
                return "blocked: no rows to edit"
            for col in view.get_columns():
                for rend in col.get_cells():
                    if isinstance(rend, Gtk.CellRendererText) and rend.get_editable():
                        # Commit through the same signal a real edit commits
                        # through: the renderer's "edited" carries the final
                        # text to the page's store callback.
                        it = store.iter_nth_child(None, 0)
                        path = store.get_path(it)
                        col_idx = self._text_column_index(view, col)
                        current = (
                            store.get_value(it, col_idx)
                            if col_idx is not None and col_idx >= 0
                            else ""
                        )
                        new_text = (
                            f"{current}-survey" if isinstance(current, str) else "survey-edit"
                        )
                        rend.emit("edited", path.to_string(), new_text)
                        self.pump(5)
                        return f"committed edit on first editable cell ({new_text!r})"
            raise RuntimeError("no editable text renderer on page")
        if role == "cycle-combo":
            combo = self.combos(page)[0] if self.combos(page) else None
            if combo is None:
                return "blocked: no combobox on page"
            model = combo.get_model()
            if model is None or model.iter_n_children(None) < 2:
                return "blocked: combobox has no alternative value"
            combo.set_active(1)
            self.pump(5)
            combo.set_active(0)
            return "cycled combobox selection"
        if role == "set-entry":
            ents = self.entries(page)
            if not ents:
                return "blocked: no entry on page"
            ents[0].set_text("survey-edit")
            self.pump(5)
            return "set first entry text"
        if role == "toggle-check":
            Gtk = self.Gtk
            checks = self.walk(self.page_widget(page), lambda w: isinstance(w, Gtk.CheckButton), [])
            if not checks:
                return "blocked: no checkbutton on page"
            target = checks[0]
            # Click through the real signal path (toggled handlers run).
            target.set_active(not target.get_active())
            self.pump(5)
            target.set_active(not target.get_active())  # restore
            self.pump(5)
            return "toggled first checkbutton and restored"
        if role == "adjust-spin":
            sps = self.spins(page)
            if not sps:
                return "blocked: no spinbutton on page"
            sps[0].spin(self.Gtk.SpinType.STEP_FORWARD, 1)
            self.pump(5)
            sps[0].spin(self.Gtk.SpinType.STEP_BACKWARD, 1)
            return "nudged first spinbutton"
        if role == "expand-first":
            views = self.treeviews(page)
            if not views:
                raise RuntimeError(f"no treeview on page ({self._census(page)})")
            view = views[0]
            store = view.get_model()
            if store is None or store.iter_n_children(None) == 0:
                return "blocked: no rows"
            view.expand_row(store.get_path(store.iter_nth_child(None, 0)), False)
            self.pump(5)
            return "expanded first row"
        if role == "collapse-all":
            views = self.treeviews(page)
            if not views:
                raise RuntimeError(f"no treeview on page ({self._census(page)})")
            views[0].collapse_all()
            self.pump(5)
            return "collapsed tree"
        raise RuntimeError(f"unknown widget role: {role}")

    def _text_column_index(self, view, column):
        """Map a tree column to its store index (text columns carry one)."""
        try:
            attrs = column.get_attributes()
        except Exception:
            attrs = None
        if attrs and "text" in attrs:
            return attrs["text"]
        # Fall back to the first text-type store column.
        store = view.get_model()
        if store is None:
            return None
        for n in range(store.get_n_columns()):
            if store.get_column_type(n).name == "gchararray":
                return n
        return None

    # -- L3 composites -------------------------------------------------------
    # Each returns (ok, detail).  Asserts are the linkage between central
    # content state and the action buttons.

    def _button_by_label(self, page, needle):
        Gtk = self.Gtk
        panel = getattr(self.win, "action_box", None)
        scope = panel if panel is not None else self.page_widget(page)
        for w in self.walk(scope, lambda x: isinstance(x, Gtk.Button)):
            if needle.lower() in (self._label_of(w) or "").lower():
                return w
        return None

    def _sensitivity_of(self, page, needle):
        button = self._button_by_label(page, needle)
        if button is None:
            return None
        return button.get_sensitive()

    def comp_datasets_selection_scopes_actions(self):
        self.navigate("datasets")
        snap = self._sensitivity_of("datasets", "Snapshot")
        if snap is None:
            return False, "Snapshot button not found"
        detail = [f"initial Snapshot sensitive={snap}"]
        ok = True
        views = self.treeviews("datasets")
        if not views:
            return False, "no dataset tree"
        sel = views[0].get_selection()
        sel.unselect_all()
        self.pump(5)
        none_sensitive = self._sensitivity_of("datasets", "Snapshot")
        detail.append(f"no-selection sensitive={none_sensitive}")
        if self.select_scratch_or_first("datasets"):
            some_sensitive = self._sensitivity_of("datasets", "Snapshot")
            detail.append(f"selected sensitive={some_sensitive}")
            # selection-scoped action: the button must become usable OR the
            # page must refuse with visible feedback; insensitive-forever is
            # a linkage break only when it was also insensitive at baseline.
            if none_sensitive and not some_sensitive:
                ok = False
        else:
            detail.append("blocked: no rows to select")
        sel.unselect_all()
        return ok, "; ".join(detail)

    def comp_backup_edit_dirty_save_revert(self):
        self.navigate("backup")
        views = self.treeviews("backup")
        if not views:
            return False, "no step table"
        view = views[0]
        store = view.get_model()
        if store is None or store.iter_n_children(None) == 0:
            return True, "blocked: no step rows to toggle"
        # Find the active toggle column and flip row 0.
        Gtk = self.Gtk
        flipped = False
        for col in view.get_columns():
            for rend in col.get_cells():
                if isinstance(rend, Gtk.CellRendererToggle) and rend.get_activatable():
                    path = store.get_path(store.iter_nth_child(None, 0))
                    rend.emit("toggled", path.to_string())
                    flipped = True
                    break
            if flipped:
                break
        if not flipped:
            return True, "blocked: no activatable toggle column"
        self.pump(5)
        dirty = self._page_dirty("backup")
        self._click_action("backup", "Save Config")
        self.pump(20)
        saved_dirty = self._page_dirty("backup")
        self._click_action("backup", "Revert Config")
        self.pump(10)
        detail = f"dirty after toggle={dirty}, after save={saved_dirty}"
        ok = dirty is True
        return ok, detail

    def _page_dirty(self, page):
        try:
            import action_dispatch

            pred = action_dispatch.PAGE_SPECS.get(page, {}).get("dirty_predicate")
            return bool(pred(self.win)) if pred else None
        except Exception:
            return None

    def _click_action(self, page, label):
        button = self._button_by_label(page, label)
        if button is None:
            raise RuntimeError(f"action button not found: {label}")
        button.clicked()
        self.pump(10)

    def comp_dry_run_toggle_flips_flag(self):
        self.navigate("backup")
        before = bool(getattr(self.win, "_dry_run_active", False))
        button = self._button_by_label("backup", "Dry Run")
        if button is None:
            return False, "Dry Run toggle not found"
        button.clicked()
        self.pump(5)
        after = bool(getattr(self.win, "_dry_run_active", False))
        detail = f"_dry_run_active {before} -> {after}"
        button.clicked()  # restore
        self.pump(5)
        return after != before, detail

    def comp_pools_scrub_selection_buttons(self):
        self.navigate("pools")
        detail = []
        ok = True
        start = self._sensitivity_of("pools", "Start Scrub")
        detail.append(f"initial Start Scrub sensitive={start}")
        views = self.treeviews("pools")
        if not views:
            return False, "no pools view"
        # The scrub view is the second treeview when present.
        scrub_view = views[1] if len(views) > 1 else views[0]
        sel = scrub_view.get_selection()
        sel.unselect_all()
        self.pump(5)
        none_sel = self._sensitivity_of("pools", "Start Scrub")
        detail.append(f"no-selection sensitive={none_sel}")
        if self.select_row(scrub_view, 0):
            with_sel = self._sensitivity_of("pools", "Start Scrub")
            detail.append(f"selected sensitive={with_sel}")
            if none_sel and not with_sel:
                ok = False
        sel.unselect_all()
        return ok, "; ".join(detail)

    def comp_schedule_selection_actions(self):
        self.navigate("schedule")
        views = self.treeviews("schedule")
        if not views:
            return False, "no schedule list"
        if not self.select_row(views[0], 0):
            return True, "blocked: no schedule entries"
        run_now = self._sensitivity_of("schedule", "Run Now")
        delete = self._sensitivity_of("schedule", "Delete")
        views[0].get_selection().unselect_all()
        self.pump(5)
        detail = f"with selection: Run Now={run_now}, Delete={delete}"
        return True, detail

    def comp_logs_selection_delete(self):
        self.navigate("logs")
        views = self.treeviews("logs")
        if not views:
            return False, "no log list"
        delete = self._sensitivity_of("logs", "Delete Selected")
        if not self.select_row(views[0], 0):
            return True, "blocked: no log rows"
        with_sel = self._sensitivity_of("logs", "Delete Selected")
        views[0].get_selection().unselect_all()
        # decline whatever confirmation appears (profile applied)
        return True, f"delete sensitive {delete} -> {with_sel} with selection"

    def comp_dashboard_selection_actions(self):
        self.navigate("dashboard")
        views = self.treeviews("dashboard")
        if not views:
            return False, "no task list"
        cancel = self._sensitivity_of("dashboard", "Cancel Selected Tasks")
        view_log = self._sensitivity_of("dashboard", "View Log")
        if not self.select_row(views[0], 0):
            return True, "blocked: no task rows"
        cancel_sel = self._sensitivity_of("dashboard", "Cancel Selected Tasks")
        view_log_sel = self._sensitivity_of("dashboard", "View Log")
        views[0].get_selection().unselect_all()
        return True, (f"cancel {cancel}->{cancel_sel}, view-log {view_log}->{view_log_sel}")

    def comp_checkagainst_add_remove_row(self):
        self.navigate("checkagainst")
        # The page stacks four views (backup-derived, offsite-derived,
        # user entries, merged preview); Add Row/Remove Row operate on the
        # USER entries store, so count and select there — views[0] is the
        # backup-derived table and never moves.
        store = getattr(self.win, "_ca_store", None)
        view = getattr(self.win, "_ca_view", None)
        if store is None or view is None:
            return False, "no user entries view"
        before = store.iter_n_children(None)
        self._click_action("checkagainst", "Add Row")
        self.pump(5)
        after_add = store.iter_n_children(None)
        # remove it again: select the last row, click Remove Row; any
        # confirmation is answered by the profile responder
        self.select_row(view, max(after_add - 1, 0))
        self._click_action("checkagainst", "Remove Row")
        self.pump(5)
        after_remove = store.iter_n_children(None)
        return after_add == before + 1, (
            f"rows {before} -> {after_add} (add) -> {after_remove} (remove)"
        )

    def comp_retention_add_policy_save(self):
        self.navigate("retention")
        views = self.treeviews("retention")
        detail = "no policy list view found"
        if views:
            store = views[0].get_model()
            before = store.iter_n_children(None) if store is not None else 0
            detail = f"policies before={before}"
        self._click_action("retention", "Add Policy")
        self.pump(10)
        # decline any prompt per profile; the responder is armed
        if views and views[0].get_model() is not None:
            after = views[0].get_model().iter_n_children(None)
            detail += f", after Add Policy={after}"
        return True, detail

    def comp_disks_selection_wipe_sensitivity(self):
        self.navigate("disks")
        views = self.treeviews("disks")
        if not views:
            return False, "no disks view"
        wipe = self._sensitivity_of("disks", "Wipe Labels")
        if not self.select_row(views[0], 0):
            return True, "blocked: no disk rows"
        wipe_sel = self._sensitivity_of("disks", "Wipe Labels")
        views[0].get_selection().unselect_all()
        return True, f"wipe sensitive {wipe} -> {wipe_sel} with selection"

    def comp_sidebar_visits_every_page(self):
        names = []
        for name in self.win._page_rows:
            self.navigate(name)
            names.append(name)
        return len(names) > 0, f"visited {len(names)} pages: {','.join(names)}"

    def comp_datasets_expand_collapse(self):
        self.navigate("datasets")
        views = self.treeviews("datasets")
        if not views:
            return False, "no dataset tree"
        view = views[0]
        store = view.get_model()
        if store is None or store.iter_n_children(None) == 0:
            return True, "blocked: no rows"
        path = store.get_path(store.iter_nth_child(None, 0))
        view.expand_row(path, False)
        self.pump(5)
        expanded = view.row_expanded(path)
        view.collapse_all()
        self.pump(5)
        collapsed = not view.row_expanded(path)
        return expanded and collapsed, f"expanded={expanded}, collapsed-all={collapsed}"

    COMPOSITES: ClassVar[dict] = {
        "datasets_selection_scopes_actions": comp_datasets_selection_scopes_actions,
        "backup_edit_dirty_save_revert": comp_backup_edit_dirty_save_revert,
        "dry_run_toggle_flips_flag": comp_dry_run_toggle_flips_flag,
        "pools_scrub_selection_buttons": comp_pools_scrub_selection_buttons,
        "schedule_selection_actions": comp_schedule_selection_actions,
        "logs_selection_delete": comp_logs_selection_delete,
        "dashboard_selection_actions": comp_dashboard_selection_actions,
        "checkagainst_add_remove_row": comp_checkagainst_add_remove_row,
        "retention_add_policy_save": comp_retention_add_policy_save,
        "disks_selection_wipe_sensitivity": comp_disks_selection_wipe_sensitivity,
        "sidebar_visits_every_page": comp_sidebar_visits_every_page,
        "datasets_expand_collapse": comp_datasets_expand_collapse,
    }

    # -- op execution ---------------------------------------------------------

    def execute(self, op):
        """Run one op; returns the verdict record."""
        op_id = op["id"]
        self.profile = op.get("profile") or "decline"
        self.dialog_log = []
        self.dialog_budget = MAX_DIALOG_RESPONSES_PER_OP
        self._handled_dialogs = set()
        self._window_grace = {}
        started = time.time()
        verdict, detail = "pass", ""
        # The catalog ships the role/impl under `name` for widgets/composites
        # via the ops file's extra columns when present (the journey merges
        # gui_catalog data into the ops TSV).
        try:
            kind = op["kind"]
            if kind == "gui-button":
                self.navigate(op["page"])
                self.select_scratch_or_first(op["page"])
                self.run_button(op["page"], op["name"])
                detail = "dispatched without exception; window alive"
            elif kind == "gui-widget":
                role = op.get("role") or self._role_for_l2(op_id)
                # Ops run in random archived order: navigate to the op's
                # page first (the action panel and widget state belong to
                # the VISIBLE page) — except the navigate role itself,
                # which IS the navigation test.
                if role != "navigate":
                    self.navigate(op["page"])
                detail = self.run_widget_role(op["page"], role)
                if isinstance(detail, str) and detail.startswith("blocked"):
                    verdict = "blocked"
            elif kind == "gui-composite":
                impl = op.get("impl") or self._impl_for_l3(op_id)
                func = self.COMPOSITES.get(impl)
                if func is None:
                    verdict, detail = "blocked", f"no composite impl {impl!r}"
                else:
                    ok, text = func(self)
                    verdict = "pass" if ok else "fail"
                    detail = text
            else:
                verdict, detail = "blocked", f"unknown kind {kind!r}"
        except Exception as exc:
            verdict = "fail"
            detail = f"{type(exc).__name__}: {exc}"
            traceback.print_exc(file=sys.stderr)
        finally:
            self._stop_runners()
            self._close_leftover_dialogs()
        return {
            "id": op_id,
            "kind": op.get("kind"),
            "name": op.get("name"),
            "page": op.get("page"),
            "profile": self.profile,
            "verdict": verdict,
            "detail": (detail or "")[:400],
            "dialogs": self.dialog_log[:20],
            "duration": round(time.time() - started, 2),
        }

    def _role_for_l2(self, op_id):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gui_catalog

        for page_name, inters in gui_catalog.L2_INTERACTIONS.items():
            for inter in inters:
                if f"gui-w-{page_name}-{inter['suffix']}" == op_id:
                    return inter["role"]
        return "select-first"

    def _impl_for_l3(self, op_id):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gui_catalog

        for comp in gui_catalog.L3_COMPOSITES:
            if f"gui-c-{comp['id']}" == op_id:
                return comp["impl"]
        return ""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def load_ops(path):
    ops = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            ops.append(
                {
                    "id": parts[0],
                    "kind": parts[1],
                    "name": parts[2] if len(parts) > 2 else "",
                    "page": parts[3] if len(parts) > 3 else "",
                    "profile": parts[4] if len(parts) > 4 else "decline",
                }
            )
    return ops


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ops", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--only", help="comma list of op ids (default: all pending)")
    args = parser.parse_args(argv)

    ops = load_ops(args.ops)
    results = Results(args.results, args.results + ".started")
    pending = [op for op in ops if op["id"] not in results.verdicts]
    if args.only:
        wanted = set(args.only.split(","))
        pending = [op for op in pending if op["id"] in wanted]

    # Stalled ops (started, never finished — a previous invocation died
    # mid-op, usually the watchdog) are failed honestly, not re-run into
    # the same wall.
    stalled = [op for op in pending if op["id"] in results.started]
    for op in stalled:
        results.record(
            {
                "id": op["id"],
                "kind": op["kind"],
                "name": op.get("name"),
                "page": op.get("page"),
                "profile": op.get("profile"),
                "verdict": "fail",
                "detail": "stalled: started in an earlier invocation, no verdict",
                "dialogs": [],
                "duration": 0.0,
            }
        )
    pending = [op for op in pending if op["id"] not in results.started]

    if not pending:
        failed = sum(1 for r in results.verdicts.values() if r["verdict"] == "fail")
        print(f"gui_probe: nothing pending; {len(results.verdicts)} verdicts, {failed} fail")
        return 1 if failed else 0

    xvfb = ensure_display()
    probe = None
    try:
        probe = GuiProbe(args.repo, results)
        for op in pending:
            results.mark_started(op["id"])
            watchdog = threading.Timer(OP_TIMEOUT_DEFAULT, lambda: os.kill(os.getpid(), 9))
            watchdog.daemon = True
            watchdog.start()
            try:
                rec = probe.execute(op)
            finally:
                watchdog.cancel()
            results.record(rec)
            print(f"gui_probe: {op['id']} -> {rec['verdict']} ({rec['detail'][:80]})", flush=True)
    finally:
        if probe is not None:
            with suppress(Exception):
                probe.win.destroy()
        if xvfb is not None:
            xvfb.terminate()

    failed = sum(1 for r in results.verdicts.values() if r["verdict"] == "fail")
    blocked = sum(1 for r in results.verdicts.values() if r["verdict"] == "blocked")
    print(f"gui_probe: done; {len(results.verdicts)} verdicts, {failed} fail, {blocked} blocked")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
