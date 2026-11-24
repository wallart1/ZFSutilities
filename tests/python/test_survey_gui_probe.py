"""Tests for the j22 GUI probe's ensure-precondition + resource sampling.

The probe runs inside the ITF guest against a real window; these unit
tests exercise the NEW logic — role-target emptiness classification,
the Add-control click, the max_create bound, and the /proc sampler —
against hand-rolled fakes bound to a bare GuiProbe instance
(``__new__`` + instance attributes).  mock_gtk patches product modules
through sys.modules and does not fit the probe, which binds ``self.Gtk``
directly; the fakes below mirror only the pieces the ensure path walks.
"""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SURVEY_DIR = os.path.realpath(os.path.join(TESTS_DIR, "..", "integrated", "survey"))
if SURVEY_DIR not in sys.path:
    sys.path.insert(0, SURVEY_DIR)

import gui_probe

# ---------------------------------------------------------------------------
# Fakes: just enough widget surface for walk/treeviews/_button_by_label
# ---------------------------------------------------------------------------


class FakeWidget:
    """Anything walk() can descend into (the Gtk.Container stand-in)."""

    def __init__(self, *children):
        self._children = list(children)

    def foreach(self, cb):
        for child in self._children:
            cb(child)


class FakeStore:
    def __init__(self, rows=0):
        self.n = rows

    def iter_n_children(self, _parent):
        return self.n

    def iter_nth_child(self, _parent, index):
        return ("iter", index) if index < self.n else None

    def get_path(self, it):
        return SimpleNamespace(to_string=lambda: str(it[1]))

    def get_n_columns(self):
        return 1

    def get_column_type(self, _n):
        return SimpleNamespace(name="gchararray")


class FakeSelection:
    def __init__(self):
        self.count = 0

    def unselect_all(self):
        self.count = 0

    def select_path(self, _path):
        self.count += 1

    def count_selected_rows(self):
        return self.count


class FakeTreeView(FakeWidget):
    def __init__(self, store):
        super().__init__()
        self._store = store
        self._selection = FakeSelection()

    def get_model(self):
        return self._store

    def get_selection(self):
        return self._selection

    def get_columns(self):
        return []

    def queue_draw(self):
        pass


class FakeButton(FakeWidget):
    def __init__(self, label, on_click=None):
        super().__init__()
        self.label = label
        self.clicks = 0
        self._on_click = on_click

    def get_label(self):
        return self.label

    def clicked(self):
        self.clicks += 1
        if self._on_click is not None:
            self._on_click()


class FakeCellRendererToggle:
    def __init__(self, activatable=True):
        self._activatable = activatable
        self.emitted = []

    def get_activatable(self):
        return self._activatable

    def emit(self, signal, path):
        self.emitted.append((signal, path))


class FakeCellRendererText:
    pass


class FakeColumn:
    def __init__(self, *cells):
        self._cells = list(cells)

    def get_cells(self):
        return self._cells


class ToggleTreeView(FakeTreeView):
    """A view whose single column holds one toggle renderer."""

    def __init__(self, store, *renderers):
        super().__init__(store)
        self._renderers = renderers

    def get_columns(self):
        return [FakeColumn(*self._renderers)]


class FakeWindow(FakeWidget):
    @staticmethod
    def list_toplevels():
        return []


FAKE_GTK = SimpleNamespace(
    Container=FakeWidget,
    TreeView=FakeTreeView,
    Button=FakeButton,
    Window=FakeWindow,
    CellRendererToggle=FakeCellRendererToggle,
    CellRendererText=FakeCellRendererText,
)


def make_probe(page_widget, action_box=None):
    """A bare probe wired to fakes — no GTK, no display, no product import."""
    probe = gui_probe.GuiProbe.__new__(gui_probe.GuiProbe)
    probe.Gtk = FAKE_GTK
    probe.win = SimpleNamespace(
        stack=SimpleNamespace(
            get_child_by_name=lambda _name: page_widget,
            set_visible_child_name=lambda _name: None,
            get_visible_child_name=lambda: "retention",
        ),
        sidebar=SimpleNamespace(emit=lambda *_a: None),
        _page_rows={"retention": object()},
        action_box=action_box,
    )
    probe.pump = lambda rounds=10: None
    probe.dialog_log = []
    probe._ensure_created = {}
    return probe


# ---------------------------------------------------------------------------
# Role-target emptiness classification
# ---------------------------------------------------------------------------


def test_role_target_empty_first_view_and_walk_semantics():
    filled = FakeTreeView(FakeStore(rows=2))
    empty = FakeTreeView(FakeStore(rows=0))
    probe = make_probe(FakeWidget(filled, empty))
    # views[0] has rows: select-family satisfied; the second view being
    # empty blocks only select-second.
    assert probe._role_target_empty("retention", "select-first") is False
    assert probe._role_target_empty("retention", "select-second") is True
    # Walk roles look at ANY view with rows.
    assert probe._role_target_empty("retention", "edit-cell") is False
    assert probe._role_target_empty("retention", "toggle-active") is False


def test_role_target_empty_when_all_views_empty():
    probe = make_probe(FakeWidget(FakeTreeView(FakeStore(0))))
    for role in (
        "select-first",
        "select-second",
        "select-multi",
        "toggle-active",
        "edit-cell",
        "edit-spin-cell",
        "expand-first",
    ):
        assert probe._role_target_empty("retention", role) is True, role


def test_role_target_empty_no_treeview_is_not_ensure_target():
    # A page with no treeview is the census-dumped FAILURE condition —
    # never an ensure target (False, so ensure declines to act).
    probe = make_probe(FakeWidget())
    assert probe._role_target_empty("backup", "select-first") is False


# ---------------------------------------------------------------------------
# ensure_precondition
# ---------------------------------------------------------------------------


def test_ensure_clicks_add_and_unblocks_the_role():
    store = FakeStore(0)
    view = FakeTreeView(store)

    def add_policy():
        store.n += 1

    button = FakeButton("Add Policy", on_click=add_policy)
    probe = make_probe(FakeWidget(view), action_box=FakeWidget(button))

    ensured = probe.ensure_precondition("retention", "select-first")
    assert ensured == "Add Policy"
    assert button.clicks == 1
    assert store.n == 1
    assert probe._role_target_empty("retention", "select-first") is False
    assert any("ensure:" in entry for entry in probe.dialog_log)
    # The role now completes instead of blocking.
    detail = probe.run_widget_role("retention", "select-first")
    assert not detail.startswith("blocked")
    assert detail == "selected 1 row(s)"


def test_ensure_click_without_row_creation_keeps_blocked():
    # A decline-profile dialog answer, simulated: the click happens but
    # no row appears — the role must keep its normal blocked verdict.
    button = FakeButton("Add Policy")  # no on_click -> nothing created
    view = FakeTreeView(FakeStore(0))
    probe = make_probe(FakeWidget(view), action_box=FakeWidget(button))

    ensured = probe.ensure_precondition("retention", "select-first")
    assert ensured == "Add Policy"
    assert probe.run_widget_role("retention", "select-first") == "blocked: no rows to select"


def test_ensure_respects_max_create_bound():
    button = FakeButton("Add Policy")
    view = FakeTreeView(FakeStore(0))
    probe = make_probe(FakeWidget(view), action_box=FakeWidget(button))

    for _ in range(3):  # the catalog's retention max_create
        assert probe.ensure_precondition("retention", "select-first") == "Add Policy"
    assert button.clicks == 3
    # The fourth attempt declines with a logged reason, not a click.
    assert probe.ensure_precondition("retention", "select-first") is None
    assert button.clicks == 3
    assert any("max_create reached" in entry for entry in probe.dialog_log)


def test_ensure_no_ops_when_target_not_empty():
    store = FakeStore(1)
    button = FakeButton("Add Policy")
    probe = make_probe(FakeWidget(FakeTreeView(store)), action_box=FakeWidget(button))
    assert probe.ensure_precondition("retention", "select-first") is None
    assert button.clicks == 0


def test_ensure_skips_pages_without_a_spec():
    # An Add Row button present on a page with no ensure spec (backup):
    # the page lookup fails before any button is considered.
    button = FakeButton("Add Row")
    view = FakeTreeView(FakeStore(0))
    probe = make_probe(FakeWidget(view), action_box=FakeWidget(button))
    assert probe.ensure_precondition("backup", "select-first") is None
    assert button.clicks == 0


def test_ensure_skips_non_row_roles():
    button = FakeButton("Add Policy")
    view = FakeTreeView(FakeStore(0))
    probe = make_probe(FakeWidget(view), action_box=FakeWidget(button))
    for role in ("set-entry", "cycle-combo", "toggle-check", "navigate", "toggle-dry-run"):
        assert probe.ensure_precondition("retention", role) is None, role
    assert button.clicks == 0


def test_ensure_missing_button_stays_blocked_not_failed():
    view = FakeTreeView(FakeStore(0))
    probe = make_probe(FakeWidget(view), action_box=FakeWidget())  # no button
    assert probe.ensure_precondition("retention", "select-first") is None
    assert any("no 'Add Policy' button" in entry for entry in probe.dialog_log)
    assert probe.run_widget_role("retention", "select-first") == "blocked: no rows to select"


def test_execute_prepends_ensure_marker_to_detail():
    store = FakeStore(0)
    view = FakeTreeView(store)
    button = FakeButton("Add Policy", on_click=lambda: setattr(store, "n", store.n + 1))
    probe = make_probe(FakeWidget(view), action_box=FakeWidget(button))
    rec = probe.execute(
        {
            "id": "gui-w-retention-select-policy",
            "kind": "gui-widget",
            "name": "select a retention policy row",
            "page": "retention",
            "profile": "accept",
        }
    )
    assert rec["verdict"] == "pass"
    assert rec["detail"] == "[ensure:Add Policy] selected 1 row(s)"
    assert any("ensure:" in entry for entry in rec["dialogs"])


# ---------------------------------------------------------------------------
# Resource sampling (report-only leak tracking)
# ---------------------------------------------------------------------------


def test_sample_resources_reads_a_fabricated_proc(tmp_path):
    (tmp_path / "status").write_text("Name:\tpython3\nVmSize:\t   99999 kB\nVmRSS:\t   12345 kB\n")
    fd_dir = tmp_path / "fd"
    fd_dir.mkdir()
    for n in range(3):
        (fd_dir / str(n)).touch()
    sample = gui_probe.sample_resources(str(tmp_path))
    assert sample == {"vmrss_kb": 12345, "fds": 3}


def test_sample_resources_unreadable_proc_yields_nones(tmp_path):
    assert gui_probe.sample_resources(str(tmp_path / "nope")) == {
        "vmrss_kb": None,
        "fds": None,
    }


def test_results_log_leaves_crash_resume_neutral(tmp_path):
    path = str(tmp_path / "results.jsonl")
    results = gui_probe.Results(path, path + ".started")
    results.log({"event": "resources", "phase": "start", "vmrss_kb": 1, "fds": 2})
    results.mark_started("op-1")
    results.record({"id": "op-1", "verdict": "pass", "detail": ""})
    # A fresh reader (the crash-resume path) sees only the verdict.
    reloaded = gui_probe.Results(path, path + ".started")
    assert set(reloaded.verdicts) == {"op-1"}
    assert reloaded.started == {"op-1"}
    with open(path, encoding="utf-8") as f:
        assert json.loads(f.readline())["event"] == "resources"


# ---------------------------------------------------------------------------
# comp_backup_edit_dirty_save_revert (the double-flip order-safety fix)
# ---------------------------------------------------------------------------


def _dirty_composite_probe(toggle, dirty_states):
    view = ToggleTreeView(FakeStore(1), toggle)
    save = FakeButton("Save Config")
    revert = FakeButton("Revert Config")
    probe = make_probe(FakeWidget(view), action_box=FakeWidget(save, revert))
    probe.win._page_rows["backup"] = object()  # navigate() needs the row
    shown = ["backup"]
    probe.win.stack.set_visible_child_name = lambda n: shown.__setitem__(0, n)
    probe.win.stack.get_visible_child_name = lambda: shown[0]
    it = iter(dirty_states)
    probe._page_dirty = lambda _page: next(it)
    return probe, save, revert


def test_backup_dirty_composite_single_flip_when_entry_clean():
    toggle = FakeCellRendererToggle()
    probe, save, revert = _dirty_composite_probe(toggle, [True, False])
    ok, detail = probe.comp_backup_edit_dirty_save_revert()
    assert ok is True, detail
    assert "dirty after toggle=True" in detail
    assert len(toggle.emitted) == 1  # one flip was enough
    assert save.clicks == 1 and revert.clicks == 1


def test_backup_dirty_composite_flips_again_when_prior_item_left_clean():
    # Order-safety regression (live run-20261124-121057): a prior item
    # toggled row 0's active cell and left it unsaved, so this
    # composite's own flip RESTORED the saved state — legitimately
    # clean.  The composite must flip once more before judging.
    toggle = FakeCellRendererToggle()
    probe, _save, _revert = _dirty_composite_probe(toggle, [False, True, False])
    ok, detail = probe.comp_backup_edit_dirty_save_revert()
    assert ok is True, detail
    assert len(toggle.emitted) == 2  # the double flip
    assert "dirty after toggle=True" in detail


def test_backup_dirty_composite_fails_when_never_dirty():
    # Two flips and still clean: the dirty predicate genuinely never
    # moved — an honest failure, not a blocked.
    toggle = FakeCellRendererToggle()
    probe, _save, _revert = _dirty_composite_probe(toggle, [False, False, False])
    ok, detail = probe.comp_backup_edit_dirty_save_revert()
    assert ok is False
    assert "dirty after toggle=False" in detail


def test_backup_dirty_composite_blocked_without_toggles():
    view = ToggleTreeView(FakeStore(1), FakeCellRendererToggle(activatable=False))
    probe, _save, _revert = _dirty_composite_probe(FakeCellRendererToggle(), [True, False])
    # Rebuild the probe's page with the non-activatable view.
    probe.win.stack.get_child_by_name = lambda _name: FakeWidget(view)
    ok, detail = probe.comp_backup_edit_dirty_save_revert()
    assert ok is True and detail.startswith("blocked: no activatable toggle")
