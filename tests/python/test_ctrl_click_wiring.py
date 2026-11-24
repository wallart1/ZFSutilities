"""Sweep: every GUI TreeView carries the ctrl-click-deselect wiring.

GTK3 skips the ctrl-click selection toggle on a view that lacks keyboard
focus, so every selectable TreeView must be wired through
``gui_helpers.enable_ctrl_click_deselect`` (see the unit tests in
test_gui_infrastructure.py and the realized check in
test_ctrl_click_realized.py for the behavior itself).

Each test builds a page or dialog under its own fresh ``mock_gtk``
context whose ``Gtk.TreeView`` hands out DISTINCT mock instances, then
asserts every created view got a ``button-press-event`` connect — a new
table added without the wiring fails here. Views with selection mode NONE
(pool-create wizard's disk list, the growth-dialog read-only disk list)
are exempt by design and are not created by these builders. Pages whose
full create path trips pre-existing mock-fitness walls (pools, retention,
offsite, logs, checkagainst — ``set_button_markup`` runs isinstance()
against the mock Gtk.Label class) are covered by the static AST audit
below instead, which checks every TreeView site in python/.
"""

import ast
import atexit
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from typing import ClassVar
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

# Real page and dialog builds reach the persistent state dir: the schedule
# page refreshes its profile list at build time and the profile dialogs
# list existing profiles, both landing in paths.get_profiles_dir()'s
# makedirs. On a host without the root-owned /var/lib/zfsutilities — the
# CI runner — that makedirs fails with EACCES. Redirect the state dir to a
# private temp dir so every build sees an empty profiles list anywhere the
# suite runs; an explicitly exported value is respected, matching the
# conftest lock-dir fence.
if "ZFSUTILITIES_STATE_DIR" not in os.environ:
    _isolated_state_dir = tempfile.mkdtemp(prefix="zfsutilities-ctrlclick-state-")
    os.environ["ZFSUTILITIES_STATE_DIR"] = _isolated_state_dir
    atexit.register(shutil.rmtree, _isolated_state_dir, ignore_errors=True)

from test_support import mock_gtk


@contextmanager
def _mock_gtk_distinct_treeviews():
    """Fresh mock_gtk with per-instance TreeView/TreeStore/ListStore mocks.

    The stock mock shares one return_value across every TreeView call,
    which would merge all connect histories; distinct instances let each
    view's wiring be asserted on its own mock. Stores terminate the
    recursive tree walks (empty iter chain), and selections return real
    (model, rows) shapes so dialog callbacks can unpack them.
    """
    with mock_gtk(fresh=True) as gtk_mock:
        views = []

        def _new_treeview(*_args, **_kwargs):
            view = MagicMock()
            selection = view.get_selection.return_value
            selection.get_selected_rows.return_value = (MagicMock(), [])
            selection.get_selected.return_value = (MagicMock(), MagicMock())
            views.append(view)
            return view

        def _new_store(*_args, **_kwargs):
            store = MagicMock()
            store.get_iter_first.return_value = None
            store.iter_children.return_value = None
            store.get_value.return_value = ""
            return store

        gtk_mock.TreeView = MagicMock(side_effect=_new_treeview)
        gtk_mock.TreeStore = MagicMock(side_effect=_new_store)
        gtk_mock.ListStore = MagicMock(side_effect=_new_store)
        yield views


def _wired_signals(view):
    return [c.args[0] for c in view.connect.call_args_list if c.args]


def _assert_wired(testcase, views, label):
    testcase.assertTrue(views, f"{label}: no TreeView was created")
    unwired = [i for i, v in enumerate(views) if "button-press-event" not in _wired_signals(v)]
    testcase.assertEqual(
        unwired,
        [],
        f"{label}: TreeView instances {unwired} lack ctrl-click wiring",
    )


def _fake_app():
    app = MagicMock()
    repo = app.ctx.zfs_repository
    repo.list_pools.return_value = []
    repo.list_datasets.return_value = []
    return app


class TestMainPages(unittest.TestCase):
    def test_datasets_page(self):
        with _mock_gtk_distinct_treeviews() as views:
            import datasets_page

            datasets_page.create_datasets_page(_fake_app())
            _assert_wired(self, views, "datasets page")

    def test_dashboard_page(self):
        with _mock_gtk_distinct_treeviews() as views:
            import dashboard_page

            dashboard_page.create_dashboard_page(_fake_app())
            _assert_wired(self, views, "dashboard page")

    def test_schedule_page(self):
        with _mock_gtk_distinct_treeviews() as views:
            import schedule_page

            schedule_page.create_schedule_page(_fake_app())
            _assert_wired(self, views, "schedule page")

    def test_disks_page(self):
        with _mock_gtk_distinct_treeviews() as views:
            import disks_page

            disks_page.create_disks_page(_fake_app())
            _assert_wired(self, views, "disks page")

    def test_memory_page(self):
        with _mock_gtk_distinct_treeviews() as views:
            import memory_page

            memory_page.create_memory_page(_fake_app())
            _assert_wired(self, views, "memory page")

    def test_alignment_page(self):
        with _mock_gtk_distinct_treeviews() as views:
            import alignment_page

            alignment_page.create_alignment_view(_fake_app())
            _assert_wired(self, views, "alignment page")


class TestSharedBuilders(unittest.TestCase):
    def test_editable_list_view(self):
        with _mock_gtk_distinct_treeviews() as views:
            import gui_helpers

            gui_helpers.EditableListView()
            _assert_wired(self, views, "EditableListView")

    def test_checkagainst_readonly_treeview(self):
        with _mock_gtk_distinct_treeviews() as views:
            import checkagainst_page

            checkagainst_page._build_readonly_treeview(MagicMock(), "state_key")
            _assert_wired(self, views, "checkagainst readonly view")


class TestDialogBuilders(unittest.TestCase):
    # Both dialogs build their picker TreeView only when a profile of the
    # requested tab type exists; without a seeded list they return early
    # and no view is created (dev hosts passed by reading the real
    # profiles dir). Fixture shape mirrors test_profile_dialogs.
    _BACKUP_DAILY: ClassVar[dict] = {
        "tab_type": "backup",
        "profile_name": "tester-backup-daily",
        "cron": {"minute": "30", "hour": "4"},
    }

    def test_add_profile_dialog(self):
        with _mock_gtk_distinct_treeviews() as views:
            import profile_dialogs

            with (
                patch.object(
                    profile_dialogs,
                    "create_dialog",
                    return_value=MagicMock(
                        run=MagicMock(return_value=profile_dialogs.Gtk.ResponseType.CANCEL)
                    ),
                ),
                patch.object(
                    profile_dialogs,
                    "list_profiles",
                    return_value=[dict(self._BACKUP_DAILY)],
                ),
            ):
                profile_dialogs.show_add_profile_dialog(_fake_app(), "backup", {})
            _assert_wired(self, views, "add-profile dialog")

    def test_recall_profile_dialog(self):
        with _mock_gtk_distinct_treeviews() as views:
            import profile_dialogs

            with (
                patch.object(
                    profile_dialogs,
                    "create_dialog",
                    return_value=MagicMock(
                        run=MagicMock(return_value=profile_dialogs.Gtk.ResponseType.CANCEL)
                    ),
                ),
                patch.object(
                    profile_dialogs,
                    "list_profiles",
                    return_value=[dict(self._BACKUP_DAILY)],
                ),
            ):
                profile_dialogs.show_recall_profile_dialog(_fake_app(), "backup", lambda *_a: None)
            _assert_wired(self, views, "recall-profile dialog")

    def test_growth_dialog_target_tree(self):
        with _mock_gtk_distinct_treeviews() as views:
            import pool_growth_dialogs

            pool_growth_dialogs._build_target_tree(MagicMock(), MagicMock(), MagicMock())
            _assert_wired(self, views, "growth-dialog target tree")

    def test_pool_watch_window(self):
        with _mock_gtk_distinct_treeviews() as views:
            import pool_watch

            pool_watch.PoolWatchWindow("tank", _fake_app())
            _assert_wired(self, views, "pool watch window")


class TestStaticTreeViewWiring(unittest.TestCase):
    """AST audit: every Gtk.TreeView creation site must wire the helper.

    For each assignment of a ``Gtk.TreeView(...)`` call anywhere in
    python/, the enclosing scope must also call
    ``enable_ctrl_click_deselect`` on that same target. Scopes that set
    their view's selection mode to NONE are exempt — with no selection
    there is nothing to deselect (pool-create wizard disk list, the
    growth-dialog read-only disk list). This complements the runtime
    builds above for pages whose full create path needs fixtures beyond
    plain mocks (pools, retention, offsite, logs, checkagainst, and the
    heavier dialogs), and catches a new unwired table in any module,
    exercised or not.
    """

    _SCOPE_TYPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    _NESTED_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)

    def _direct_nodes(self, scope):
        """Yield scope nodes without descending into nested scopes."""
        todo = list(ast.iter_child_nodes(scope))
        while todo:
            node = todo.pop()
            yield node
            if not isinstance(node, self._NESTED_TYPES):
                todo.extend(ast.iter_child_nodes(node))

    def _scopes(self, root):
        """Yield every scope node (module, classes, functions) in the tree."""
        yield root
        for node in ast.walk(root):
            if isinstance(node, self._SCOPE_TYPES[1:]):
                yield node

    def _is_treeview_call(self, node):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "TreeView"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "Gtk"
        )

    def test_every_treeview_site_is_wired(self):
        failures = []
        sites = 0
        for filename in sorted(os.listdir(PYTHON_SRC)):
            if not filename.endswith(".py"):
                continue
            path = os.path.join(PYTHON_SRC, filename)
            with open(path) as handle:
                tree = ast.parse(handle.read(), filename=filename)
            for scope in self._scopes(tree):
                direct = list(self._direct_nodes(scope))
                # Exempt scopes whose view is deliberately unselectable.
                none_mode = any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "set_mode"
                    and any("SelectionMode.NONE" in ast.unparse(arg) for arg in node.args)
                    for node in direct
                )
                if none_mode:
                    continue
                for node in direct:
                    if not isinstance(node, ast.Assign):
                        continue
                    if not self._is_treeview_call(node.value):
                        continue
                    sites += 1
                    for target in node.targets:
                        target_src = ast.unparse(target)
                        wired = any(
                            isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Name)
                            and call.func.id == "enable_ctrl_click_deselect"
                            and call.args
                            and ast.unparse(call.args[0]) == target_src
                            for call in ast.walk(scope)
                        )
                        if not wired:
                            failures.append(
                                f"{filename}:{node.lineno} "
                                f"({target_src}) in "
                                f"{getattr(scope, 'name', '<module>')}"
                            )
        self.assertEqual(failures, [], f"unwired TreeView sites:\n{failures}")
        # The audit itself must stay meaningful: it must see the known
        # selectable sites, not silently match nothing.
        self.assertGreaterEqual(sites, 25)


if __name__ == "__main__":
    unittest.main()
