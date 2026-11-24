"""Sweep: every dialog display goes through gui_helpers.run_dialog.

While a modal dialog is open the GUI dims its other toplevel windows (the
behavior lives in gui_helpers.run_dialog/dimmed_modal; the state machine is
unit-tested in test_modal_dim.py). A dialog displayed by calling .run()
directly would skip that dimming, so this audit holds every Python source
file to the contract:

* ``subprocess.run(...)`` calls are unrelated and always allowed;
* ``app.run(None)`` in main.py is the Gtk.Application main loop;
* ``dialog.run()`` appears exactly once, inside gui_helpers.run_dialog;
* every other ``.run(...)`` on any receiver is a violation;
* a module that calls ``run_dialog`` must import it from gui_helpers.
"""

import ast
import os
import re
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)


def _python_sources():
    for fname in sorted(os.listdir(PYTHON_SRC)):
        if fname.endswith(".py"):
            yield fname, os.path.join(PYTHON_SRC, fname)


def _run_dialog_function(tree):
    """Return the run_dialog FunctionDef from a gui_helpers parse tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_dialog":
            return node
    return None


def _inside(node, func):
    return func.lineno <= node.lineno <= func.end_lineno


class RunDialogWiring(unittest.TestCase):
    def test_every_run_call_is_sanctioned(self):
        violations = []
        passthrough_seen = 0
        for fname, path in _python_sources():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=fname)
            passthrough = None
            if fname == "gui_helpers.py":
                passthrough = _run_dialog_function(tree)
                self.assertIsNotNone(passthrough, "gui_helpers.run_dialog is gone")
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == "run"):
                    continue
                if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                    continue
                if (
                    fname == "main.py"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "app"
                ):
                    continue  # Gtk.Application.run(None)
                if passthrough is not None and _inside(node, passthrough):
                    passthrough_seen += 1
                    continue
                violations.append(f"{fname}:{node.lineno}")
        self.assertEqual(
            violations,
            [],
            "dialog .run() outside run_dialog (dimming bypassed): " + ", ".join(violations),
        )
        self.assertEqual(passthrough_seen, 1, "run_dialog must keep exactly one .run() passthrough")

    def test_run_dialog_callers_import_it(self):
        offenders = []
        for fname, path in _python_sources():
            if fname == "gui_helpers.py":
                continue
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if re.search(r"\brun_dialog\(", text) and not re.search(
                r"^from gui_helpers import .*\brun_dialog\b", text, re.MULTILINE | re.DOTALL
            ):
                offenders.append(fname)
        self.assertEqual(
            offenders, [], "run_dialog used without importing it: " + ", ".join(offenders)
        )


if __name__ == "__main__":
    unittest.main()
