"""Tests for pool_actions.py — pool registry add/remove/save/revert."""

import os
import subprocess
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk


def _iscsi_blocker(dataset="tank/vm-211-disk-0", bsname="vm-211-disk-0", lun_info=""):
    """A resolvable iSCSI-holder blocker shaped like gui_helpers.BusyReason.

    Built as a local namespace (not an import) so this suite keeps no
    module-level GUI import — the gi import-guard audit requires that.
    """
    return SimpleNamespace(
        category="iscsi",
        dataset=dataset,
        detail="zvol is an active iSCSI LUN backstore",
        resolvable=True,
        action="",
        data={"bsname": bsname, "lun_info": lun_info},
    )


def _fake_reason(category, dataset, detail, resolvable=False, action="", data=None):
    """Return a SimpleNamespace that looks like a gui_helpers.BusyReason."""
    return SimpleNamespace(
        category=category,
        dataset=dataset,
        detail=detail,
        resolvable=resolvable,
        action=action,
        data=data or {},
    )


def _import_pool_actions():
    """Import pool_actions under a fresh mocked GTK context."""
    sys.modules.pop("pool_actions", None)
    with mock_gtk(fresh=True):
        import pool_actions

        return pool_actions


def _make_app(known_pools=None):
    app = MagicMock()
    app.known_pools = list(known_pools or [])
    app._pools_saved_state = list(known_pools or [])
    app.config = {"pools": list(known_pools or [])}
    app.pools_dirty = False
    app.pool_view = MagicMock()
    app.pool_view.get_selection.return_value.get_selected_rows.return_value = (None, [])
    return app


class TestCheckPoolsDirty(unittest.TestCase):
    """check_pools_dirty styles the Save button and the Pools tab together."""

    def test_dirty_styles_tab_red(self):
        pa = _import_pool_actions()
        app = _make_app()
        app.pools_dirty = True

        with patch.object(pa, "set_button_markup_red") as mock_red:
            pa.check_pools_dirty(app)

        mock_red.assert_called_once_with(app._pools_save_btn, True)
        app.set_page_attention.assert_called_once_with("pools", "dirty", True)

    def test_clean_clears_tab_attention(self):
        pa = _import_pool_actions()
        app = _make_app()

        with patch.object(pa, "set_button_markup_red"):
            pa.check_pools_dirty(app)

        app.set_page_attention.assert_called_once_with("pools", "dirty", False)


def _make_app_with_pool_selection(pa, known_pools, selected):
    """Return an app whose pool_view has selected pool rows.

    selected: list of dicts with 'name' and 'flag' keys.
    """
    app = _make_app(known_pools)
    model = MagicMock()
    paths = []
    for row in selected:
        path = MagicMock()
        paths.append(path)

    def get_iter(path):
        for row, p in zip(selected, paths):
            if p is path:
                return row
        return None

    def get_value(it, col):
        if col == pa.COL_NAME:
            return it["name"]
        if col == pa.COL_FLAG:
            return it["flag"]
        return None

    model.get_iter.side_effect = get_iter
    model.get_value.side_effect = get_value
    app.pool_view.get_selection.return_value.get_selected_rows.return_value = (model, paths)
    return app


def _make_add_dialog(pool_name):
    """Return a mock create_dialog that simulates entering pool_name."""
    dialog = MagicMock()
    dialog.return_value.run.return_value = 1  # ResponseType.OK
    entry = MagicMock()
    entry.get_text.return_value = pool_name
    content = MagicMock()
    dialog.return_value.get_content_area.return_value = content

    def fake_add(widget):
        """No-op; we rely on the patched Gtk.Entry returning our entry mock."""

    content.add.side_effect = fake_add
    return dialog


def _patch_entry(pa, pool_name):
    """Patch Gtk.Entry so the dialog returns pool_name."""
    entry_mock = MagicMock()
    entry_mock.get_text.return_value = pool_name
    pa.Gtk.Entry = MagicMock(return_value=entry_mock)


class TestOnPoolsDetails(unittest.TestCase):
    """on_pools_details shows zpool status and zpool get all for the first selected pool."""

    def test_warns_when_nothing_selected(self):
        pa = _import_pool_actions()
        app = _make_app()
        with patch.object(pa, "log_msg") as mock_log:
            pa.on_pools_details(app)
        mock_log.assert_called_once()
        self.assertIn("Select a pool", mock_log.call_args[0][0])

    def test_logs_details_for_first_selected_pool(self):
        pa = _import_pool_actions()
        app = _make_app_with_pool_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            [{"name": "tank", "flag": "registered"}],
        )
        app.ctx.zfs_repository.pool_status.return_value = "mock status"
        app.ctx.zfs_repository.pool_get_all.return_value = "size\t10T\ncapacity\t50%\n"
        with patch.object(pa, "log_msg") as mock_log:
            pa.on_pools_details(app)
        mock_log.assert_called()
        messages = [call[0][0] for call in mock_log.call_args_list]
        self.assertTrue(any("Pool details for tank" in m for m in messages))
        self.assertTrue(any("mock status" in m for m in messages))
        self.assertTrue(any("zpool get all output for tank" in m for m in messages))
        self.assertTrue(any("size\t10T" in m for m in messages))
        self.assertTrue(any("capacity\t50%" in m for m in messages))

    def test_warns_when_pool_get_all_fails(self):
        pa = _import_pool_actions()
        app = _make_app_with_pool_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            [{"name": "tank", "flag": "registered"}],
        )
        app.ctx.zfs_repository.pool_status.return_value = "mock status"
        app.ctx.zfs_repository.pool_get_all.return_value = ""
        with patch.object(pa, "log_msg") as mock_log:
            pa.on_pools_details(app)
        messages = [call[0][0] for call in mock_log.call_args_list]
        self.assertTrue(any("Pool details for tank" in m for m in messages))
        self.assertTrue(any("mock status" in m for m in messages))
        self.assertTrue(any("Error reading properties for 'tank'" in m for m in messages))


class TestOnPoolsAdd(unittest.TestCase):
    """on_pools_add appends dict pools and rejects duplicate names."""

    def test_prefills_unregistered_pool_name(self):
        pa = _import_pool_actions()
        app = _make_app_with_pool_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            [{"name": "unknown", "flag": "unregistered"}],
        )
        dialog_mock = _make_add_dialog("unknown")
        with patch.object(pa, "create_dialog", dialog_mock), patch.object(pa, "refresh_pools_page"):
            _patch_entry(pa, "unknown")
            pa.on_pools_add(app)
        self.assertIn("unknown", app.known_pools[-1].values())

    def test_add_dialog_entry_carries_tooltip(self):
        pa = _import_pool_actions()
        app = _make_app([{"name": "tank", "offsite_candidate": False}])
        dialog_mock = _make_add_dialog("archive")

        with (
            patch.object(pa, "create_dialog", dialog_mock),
            patch.object(pa, "refresh_pools_page"),
        ):
            _patch_entry(pa, "archive")
            pa.on_pools_add(app)

        tip = pa.Gtk.Entry.return_value.set_tooltip_text.call_args.args[0]
        self.assertTrue(tip.strip())
        self.assertIn("registration", tip)

    def test_adds_dict_with_offsite_candidate_false(self):
        pa = _import_pool_actions()
        app = _make_app([{"name": "tank", "offsite_candidate": False}])
        dialog_mock = _make_add_dialog("archive")

        with (
            patch.object(pa, "create_dialog", dialog_mock),
            patch.object(pa, "refresh_pools_page") as mock_refresh,
        ):
            _patch_entry(pa, "archive")
            pa.on_pools_add(app)

        self.assertEqual(len(app.known_pools), 2)
        self.assertEqual(app.known_pools[-1], {"name": "archive", "offsite_candidate": False})
        mock_refresh.assert_called_once_with(app)

    def test_rejects_duplicate_name(self):
        pa = _import_pool_actions()
        app = _make_app([{"name": "tank", "offsite_candidate": False}])
        dialog_mock = _make_add_dialog("tank")

        with (
            patch.object(pa, "create_dialog", dialog_mock),
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "log_msg") as mock_log,
        ):
            _patch_entry(pa, "tank")
            pa.on_pools_add(app)

        self.assertEqual(len(app.known_pools), 1)
        mock_refresh.assert_not_called()
        mock_log.assert_called_once()
        self.assertIn("already in the registry", mock_log.call_args[0][0])

    def test_cancel_does_nothing(self):
        pa = _import_pool_actions()
        app = _make_app()
        dialog_mock = MagicMock()
        dialog_mock.return_value.run.return_value = -6  # ResponseType.CANCEL

        with (
            patch.object(pa, "create_dialog", dialog_mock),
            patch.object(pa, "refresh_pools_page") as mock_refresh,
        ):
            _patch_entry(pa, "tank")
            pa.on_pools_add(app)

        self.assertEqual(app.known_pools, [])
        mock_refresh.assert_not_called()


class TestOnPoolsRemove(unittest.TestCase):
    """on_pools_remove filters dict pools by name."""

    def _make_app_with_selection(self, pa, pools, selected):
        app = _make_app(pools)
        model = MagicMock()
        paths = []
        for name, health in selected:
            path = MagicMock()
            paths.append(path)

        def get_iter(path):
            for (n, h), p in zip(selected, paths):
                if p is path:
                    it = MagicMock()
                    it.__eq__ = lambda self, other: True
                    return it
            return None

        model.get_iter.side_effect = get_iter
        model.get_value.side_effect = lambda it, col: {
            pa.COL_NAME: selected[paths.index(path) if False else 0][0],
            pa.COL_HEALTH: selected[paths.index(path) if False else 0][1],
        }.get(col)

        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (model, paths)
        return app, model, paths, selected

    def test_removes_selected_registered_pool(self):
        pa = _import_pool_actions()
        app = _make_app(
            [
                {"name": "tank", "offsite_candidate": False},
                {"name": "archive", "offsite_candidate": True},
            ]
        )
        model = MagicMock()
        path = MagicMock()
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (model, [path])

        def get_iter(p):
            if p is path:
                it = MagicMock()
                return it
            return None

        model.get_iter.side_effect = get_iter
        call_count = {"n": 0}

        def get_value(it, col):
            call_count["n"] += 1
            if col == pa.COL_NAME:
                return "archive"
            if col == pa.COL_HEALTH:
                return "ONLINE"
            return None

        model.get_value.side_effect = get_value

        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        with patch.object(pa, "refresh_pools_page") as mock_refresh, patch.object(pa, "log_msg"):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_remove(app)

        self.assertEqual([p["name"] for p in app.known_pools], ["tank"])
        mock_refresh.assert_called_once_with(app)

    def test_unregistered_selection_warns(self):
        pa = _import_pool_actions()
        app = _make_app([{"name": "tank", "offsite_candidate": False}])
        model = MagicMock()
        path = MagicMock()
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (model, [path])

        it = MagicMock()
        model.get_iter.return_value = it
        model.get_value.side_effect = lambda _it, col: {
            pa.COL_NAME: "unknown",
            pa.COL_HEALTH: "ONLINE",
        }.get(col)

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "log_msg") as mock_log,
        ):
            pa.on_pools_remove(app)

        self.assertEqual(len(app.known_pools), 1)
        mock_refresh.assert_not_called()
        mock_log.assert_called_once()
        self.assertIn("Select at least one registered pool", mock_log.call_args[0][0])


class TestOnPoolsSave(unittest.TestCase):
    """on_pools_save persists dict pools and updates saved state."""

    def test_saves_dict_pools(self):
        pa = _import_pool_actions()
        app = _make_app(
            [
                {"name": "tank", "offsite_candidate": False},
                {"name": "z40tb", "offsite_candidate": True},
            ]
        )
        app.pools_dirty = True

        with (
            patch.object(pa, "save_pools") as mock_save,
            patch.object(pa, "_update_pools_dirty_indicator") as mock_dirty,
        ):
            pa.on_pools_save(app)

        mock_save.assert_called_once_with(app.config, app.known_pools)
        self.assertEqual(app._pools_saved_state, app.known_pools)
        mock_dirty.assert_called_once_with(app)

    def test_no_op_when_clean(self):
        pa = _import_pool_actions()
        app = _make_app()
        app.pools_dirty = False

        with patch.object(pa, "save_pools") as mock_save:
            pa.on_pools_save(app)

        mock_save.assert_not_called()


class TestOnPoolsRevert(unittest.TestCase):
    """on_pools_revert restores dict pools from saved state."""

    def test_restores_dict_list(self):
        pa = _import_pool_actions()
        original = [
            {"name": "tank", "offsite_candidate": False},
            {"name": "z40tb", "offsite_candidate": True},
        ]
        app = _make_app(original)
        app.known_pools.append({"name": "extra", "offsite_candidate": False})

        with patch.object(pa, "refresh_pools_page") as mock_refresh, patch.object(pa, "log_msg"):
            pa.on_pools_revert(app)

        self.assertEqual(app.known_pools, original)
        mock_refresh.assert_called_once_with(app)


class TestOnPoolsImport(unittest.TestCase):
    """on_pools_import refreshes both pool and scrub tables."""

    def _make_app_with_offline_selection(self, pa, pools, selected, health="OFFLINE"):
        app = _make_app(pools)
        model = MagicMock()
        paths = []
        for name in selected:
            path = MagicMock()
            paths.append(path)

        it = MagicMock()
        model.get_iter.return_value = it
        call_count = {"n": 0}

        def get_value(_it, col):
            name = selected[call_count["n"] // 2]
            call_count["n"] += 1
            if col == pa.COL_NAME:
                return name
            if col == pa.COL_HEALTH:
                return health
            return None

        model.get_value.side_effect = get_value
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (model, paths)
        return app

    def test_import_offline_selected_opens_fallback_dialog(self):
        """OFFLINE selections no longer import directly; fallback dialog is shown."""
        pa = _import_pool_actions()
        app = self._make_app_with_offline_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.OK

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table") as mock_scrub_refresh,
            patch.object(pa, "schedule_scrub_refresh_burst") as mock_burst,
            patch.object(app.ctx.zfs_repository, "import_pool") as mock_import,
            patch.object(app.ctx.zfs_repository, "importable_pools_raw", return_value=""),
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_import(app)

        msg_dialog.assert_called_once()
        mock_import.assert_not_called()
        mock_refresh.assert_not_called()
        mock_scrub_refresh.assert_not_called()
        mock_burst.assert_not_called()

    def test_import_importable_selected_refreshes_scrub_table(self):
        pa = _import_pool_actions()
        app = self._make_app_with_offline_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
            health="IMPORTABLE",
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table") as mock_scrub_refresh,
            patch.object(pa, "schedule_scrub_refresh_burst") as mock_burst,
            patch.object(app.ctx.zfs_repository, "import_pool", return_value=True) as mock_import,
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_import(app)

            mock_import.assert_called_once_with("tank")
            mock_refresh.assert_called_once_with(app)
            mock_scrub_refresh.assert_called_once_with(app)
            mock_burst.assert_called_once_with(app)

    def test_import_importable_selected_invalidates_importable_cache(self):
        """Import invalidates the importable cache so the registry reflects it immediately."""
        pa = _import_pool_actions()
        app = self._make_app_with_offline_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
            health="IMPORTABLE",
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        with (
            patch.object(pa, "refresh_pools_page"),
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(app.ctx.zfs_repository, "import_pool", return_value=True),
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_import(app)

        app._importable_pool_cache.invalidate.assert_called_once_with()


class TestOnPoolsExport(unittest.TestCase):
    """on_pools_export refreshes both pool and scrub tables."""

    def _make_app_with_selection(self, pa, pools, selected):
        app = _make_app(pools)
        model = MagicMock()
        paths = []
        for name in selected:
            path = MagicMock()
            paths.append(path)

        it = MagicMock()
        model.get_iter.return_value = it
        call_count = {"n": 0}

        def get_value(_it, col):
            name = selected[call_count["n"] // 2]
            call_count["n"] += 1
            if col == pa.COL_NAME:
                return name
            if col == pa.COL_HEALTH:
                return "ONLINE"
            return None

        model.get_value.side_effect = get_value
        app.pool_view.get_selection.return_value.get_selected_rows.return_value = (model, paths)
        return app

    def test_export_selected_refreshes_scrub_table(self):
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table") as mock_scrub_refresh,
            patch.object(pa, "schedule_scrub_refresh_burst") as mock_burst,
            patch.object(app.ctx.zfs_repository, "export_pool_detailed", return_value=(True, "")),
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_export(app)

        mock_refresh.assert_called_once_with(app)
        mock_scrub_refresh.assert_called_once_with(app)
        mock_burst.assert_called_once_with(app)

    def test_export_selected_invalidates_importable_cache(self):
        """Export invalidates the importable cache so the registry reflects it immediately."""
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        with (
            patch.object(pa, "refresh_pools_page"),
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(app.ctx.zfs_repository, "export_pool_detailed", return_value=(True, "")),
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_export(app)

        app._importable_pool_cache.invalidate.assert_called_once_with()

    def test_export_stall_warns_and_returns(self):
        """A never-returning export must not freeze the handler (F-051).

        A zvol held by an active iSCSI LUN session blocks `zpool export`
        uninterruptibly in the kernel; the UI-side deadline reports the
        stall, the stall recovery finds nothing removable, and the
        handler finishes — window alive, refreshes run.
        """
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        app.ctx.zfs_repository.list_datasets.return_value = []
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        release = threading.Event()

        def blocked_export(_pool):
            release.wait(timeout=10)  # simulate the D-state ioctl
            return (False, "")

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(pa, "EXPORT_STALL_WARN_S", 0.05),
            patch.object(
                app.ctx.zfs_repository,
                "export_pool_detailed",
                side_effect=blocked_export,
            ),
            patch.object(pa, "log_msg") as mock_log,
        ):
            try:
                pa.Gtk.MessageDialog = msg_dialog
                pa.on_pools_export(app)  # must return, not hang
            finally:
                release.set()

        mock_refresh.assert_called_once_with(app)
        warnings = [c.args[0] for c in mock_log.call_args_list if "stalled" in c.args[0]]
        self.assertTrue(warnings, "no stall warning logged")
        gave_up = [
            c.args[0]
            for c in mock_log.call_args_list
            if "no removable holders" in c.args[0]
        ]
        self.assertTrue(gave_up, "no honest give-up warning logged")

    def test_export_stall_recovers_after_iscsi_holder_removal(self):
        """The stall path resolves holders with approval instead of WARN-only.

        A stalled export (zvol held by a live iSCSI LUN session) goes
        through the same blocker diagnosis and approval dialogs as the
        fast-fail path; removing the LUN releases the kernel hold, the
        lingering worker completes, and the pool exports.
        """
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        repo = app.ctx.zfs_repository
        repo.list_datasets.return_value = [
            SimpleNamespace(name="tank/vm-211-disk-0", ds_type="volume", mounted="no")
        ]
        blocker = _iscsi_blocker(lun_info="iqn.2023-01.com.example:t1 (LUN 3)")

        release = threading.Event()

        def blocked_export(_pool):
            release.wait(timeout=10)  # the D-state ioctl
            return (True, "")  # completes once the holder is gone

        confirm_calls = {"n": 0}

        def approve_and_release():
            confirm_calls["n"] += 1
            if confirm_calls["n"] == 1:
                return pa.Gtk.ResponseType.YES  # the export confirm dialog
            release.set()  # the LUN removal releases the kernel hold
            return pa.Gtk.ResponseType.YES  # the LUN-removal approval

        msg_dialog = MagicMock()
        msg_dialog.return_value.run.side_effect = approve_and_release

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(pa, "EXPORT_STALL_WARN_S", 0.05),
            patch.object(repo, "export_pool_detailed", side_effect=blocked_export),
            patch.object(pa, "collect_dataset_busy_reasons", return_value=[blocker]),
            patch.object(pa, "subprocess") as mock_subprocess,
            patch.object(pa, "log_msg") as mock_log,
        ):
            mock_subprocess.run.side_effect = lambda *a, **k: SimpleNamespace(
                returncode=0, stderr=""
            )
            try:
                pa.Gtk.MessageDialog = msg_dialog
                pa.on_pools_export(app)
            finally:
                release.set()

        msgs = [c.args[0] for c in mock_log.call_args_list]
        self.assertIn(
            "INFO: Pool 'tank' exported successfully after resolving blockers", msgs
        )
        self.assertTrue(any("Removed iSCSI backstore" in m for m in msgs))
        manual = [m for m in msgs if "Release holders" in m]
        self.assertFalse(manual, "stall must not instruct manual holder release")
        mock_refresh.assert_called_once_with(app)

    def test_export_stall_cancelled_by_user(self):
        """Declining the holder-removal approval cancels the stalled export."""
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        repo = app.ctx.zfs_repository
        repo.list_datasets.return_value = [
            SimpleNamespace(name="tank/vm-211-disk-0", ds_type="volume", mounted="no")
        ]
        blocker = _iscsi_blocker()
        release = threading.Event()

        def blocked_export(_pool):
            release.wait(timeout=10)
            return (False, "")

        msg_dialog = MagicMock()
        confirm_calls = {"n": 0}

        def confirm_then_decline():
            confirm_calls["n"] += 1
            if confirm_calls["n"] == 1:
                return pa.Gtk.ResponseType.YES  # the export confirm dialog
            return pa.Gtk.ResponseType.NO  # decline the LUN-removal approval

        msg_dialog.return_value.run.side_effect = confirm_then_decline

        with (
            patch.object(pa, "refresh_pools_page"),
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(pa, "EXPORT_STALL_WARN_S", 0.05),
            patch.object(repo, "export_pool_detailed", side_effect=blocked_export),
            patch.object(pa, "collect_dataset_busy_reasons", return_value=[blocker]),
            patch.object(pa, "log_msg") as mock_log,
        ):
            try:
                pa.Gtk.MessageDialog = msg_dialog
                pa.on_pools_export(app)
            finally:
                release.set()

        msgs = [c.args[0] for c in mock_log.call_args_list]
        self.assertIn("INFO: Export of 'tank' cancelled by user", msgs)
        self.assertNotIn("INFO: Pool 'tank' exported successfully after resolving blockers", msgs)

    def test_recovery_retry_stall_routes_through_stall_recovery(self):
        """A stalled retry inside fast-fail recovery gets the same treatment.

        The fast-fail path resolved blockers and retried; the retry itself
        stalls (kernel hold) — the stall recovery must run, clear the
        holder with approval, and let the lingering retry finish.
        """
        pa = _import_pool_actions()
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        repo = app.ctx.zfs_repository
        repo.list_datasets.return_value = [
            SimpleNamespace(name="tank/vm-211-disk-0", ds_type="volume", mounted="no")
        ]
        blocker = _iscsi_blocker(lun_info="iqn.2023-01.com.example:t1 (LUN 3)")

        release = threading.Event()

        def blocked_retry(_pool):
            release.wait(timeout=10)
            return (True, "")  # completes once the holder is gone

        msg_dialog = MagicMock()
        calls = {"n": 0}

        def approve_and_release():
            calls["n"] += 1
            if calls["n"] == 2:
                # Only the stall recovery's LUN removal releases the hold:
                # the first approval (fast-fail recovery) must leave the
                # retry stalled so the stall branch is what runs.
                release.set()
            return pa.Gtk.ResponseType.YES

        msg_dialog.return_value.run.side_effect = approve_and_release

        with (
            patch.object(pa, "EXPORT_STALL_WARN_S", 0.05),
            patch.object(repo, "export_pool_detailed", side_effect=blocked_retry),
            patch.object(pa, "collect_dataset_busy_reasons", return_value=[blocker]),
            patch.object(pa, "subprocess"),
            patch.object(pa, "log_msg") as mock_log,
        ):
            mock_subprocess_run = pa.subprocess.run
            mock_subprocess_run.return_value = SimpleNamespace(returncode=0, stderr="")
            try:
                pa.Gtk.MessageDialog = msg_dialog
                recovered = pa._try_export_with_recovery(app, "tank", "")
            finally:
                release.set()

        self.assertTrue(recovered)
        msgs = [c.args[0] for c in mock_log.call_args_list]
        self.assertTrue(any("stalled" in m for m in msgs), "no stall warning logged")

    def test_stall_recovery_retries_fresh_when_linger_returns_failure(self):
        """A lingering export that returns failure gets one fresh attempt."""
        pa = _import_pool_actions()
        app = MagicMock()
        app.ctx.zfs_repository = MagicMock()
        repo = app.ctx.zfs_repository
        repo.list_datasets.return_value = [
            SimpleNamespace(name="tank/vm-211-disk-0", ds_type="volume", mounted="no")
        ]
        blocker = _iscsi_blocker(lun_info="iqn.2023-01.com.example:t1 (LUN 3)")

        release = threading.Event()
        # Attempt 1 (the stalled one) fails after the holder is removed;
        # attempt 2 (the fresh retry) succeeds.
        outcomes = [
            lambda _pool: (release.wait(timeout=10), (False, "pool busy"))[1],
            lambda _pool: (True, ""),
        ]
        state = {"i": 0}

        def export_call(pool):
            outcome = outcomes[min(state["i"], len(outcomes) - 1)]
            state["i"] += 1
            return outcome(pool)

        msg_dialog = MagicMock()
        calls = {"n": 0}

        def approve_and_release():
            calls["n"] += 1
            if calls["n"] == 1:
                release.set()
            return pa.Gtk.ResponseType.YES

        msg_dialog.return_value.run.side_effect = approve_and_release

        with (
            patch.object(pa, "EXPORT_STALL_WARN_S", 0.05),
            patch.object(repo, "export_pool_detailed", side_effect=export_call),
            patch.object(pa, "collect_dataset_busy_reasons", return_value=[blocker]),
            patch.object(pa, "subprocess"),
        ):
            pa.subprocess.run.return_value = SimpleNamespace(returncode=0, stderr="")
            export = pa._BoundedExport(repo, "tank")
            finished, _ok, _err = export.wait(0.05)
            self.assertFalse(finished)  # the stall that triggers recovery
            try:
                pa.Gtk.MessageDialog = msg_dialog
                recovered = pa._recover_stalled_export(app, "tank", export)
            finally:
                release.set()

        self.assertTrue(recovered)

    def test_bounded_export_deadline(self):
        """The bounded export reports finished and deadline shapes."""
        pa = _import_pool_actions()
        repo = MagicMock()
        repo.export_pool_detailed.return_value = (True, "")
        finished, ok, err = pa._BoundedExport(repo, "tank").wait(5)
        self.assertTrue(finished)
        self.assertTrue(ok)
        self.assertEqual(err, "")

        never = threading.Event()
        repo.export_pool_detailed.side_effect = lambda _pool: (
            never.wait(timeout=10) and (False, ""),
            "",
        )
        finished, ok, _ = pa._BoundedExport(repo, "tank").wait(0.05)
        never.set()
        self.assertFalse(finished)
        self.assertFalse(ok)

    def test_export_auto_unmounts_and_retries_on_unmount_failure(self):
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        row = MagicMock()
        row.name = "tank/data"
        row.ds_type = "filesystem"
        row.mounted = "yes"

        export_results = [
            (False, "cannot unmount '/mnt/tank/data': unmount failed"),
            (True, ""),
        ]

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table") as mock_scrub_refresh,
            patch.object(pa, "schedule_scrub_refresh_burst") as mock_burst,
            patch.object(pa, "log_msg"),
            patch.object(
                app.ctx.zfs_repository,
                "export_pool_detailed",
                side_effect=export_results,
            ) as mock_export,
            patch.object(
                app.ctx.zfs_repository,
                "dataset_for_mountpoint",
                return_value="tank/data",
            ),
            patch.object(
                app.ctx.zfs_repository,
                "list_datasets",
                return_value=[row],
            ),
            patch.object(
                app.ctx.zfs_repository,
                "unmount_filesystem",
                return_value=(True, ""),
            ),
            patch.object(pa, "diagnose_dataset_busy") as mock_diagnose,
            patch.object(
                pa,
                "collect_dataset_busy_reasons",
                return_value=[
                    _fake_reason(
                        category="mounted",
                        dataset="tank/data",
                        detail="Dataset is mounted at /mnt/tank/data.",
                        resolvable=True,
                        data={"mountpoint": "/mnt/tank/data", "busy": False},
                    )
                ],
            ),
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_export(app)

            mock_diagnose.assert_called_once()
            self.assertEqual(mock_export.call_count, 2)
            mock_refresh.assert_called_once_with(app)
            mock_scrub_refresh.assert_called_once_with(app)
            mock_burst.assert_called_once_with(app)

    def test_export_approval_stop_vm_then_retry(self):
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        export_results = [
            (False, "cannot unmount '/tank': unmount failed"),
            (True, ""),
        ]

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(pa, "log_msg"),
            patch.object(
                app.ctx.zfs_repository,
                "export_pool_detailed",
                side_effect=export_results,
            ) as mock_export,
            patch.object(
                app.ctx.zfs_repository,
                "dataset_for_mountpoint",
                return_value=None,
            ),
            patch.object(
                app.ctx.zfs_repository,
                "list_datasets",
                return_value=[
                    MagicMock(name="tank/proxmox/vm-105-disk-0", ds_type="volume", mounted="no")
                ],
            ),
            patch.object(pa, "diagnose_dataset_busy"),
            patch.object(
                pa,
                "collect_dataset_busy_reasons",
                return_value=[
                    _fake_reason(
                        category="vm",
                        dataset="tank/proxmox/vm-105-disk-0",
                        detail="VM 105 is RUNNING and may be using tank/proxmox/vm-105-disk-0.",
                        resolvable=True,
                        data={"vmid": "105"},
                    )
                ],
            ),
            patch.object(
                subprocess,
                "run",
                return_value=MagicMock(returncode=0, stderr=""),
            ) as mock_run,
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_export(app)

            mock_run.assert_any_call(
                ["qm", "stop", "105"],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            self.assertEqual(mock_export.call_count, 2)
            mock_refresh.assert_called_once_with(app)

    def test_export_approval_terminate_process_then_retry(self):
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        export_results = [
            (False, "cannot unmount '/mnt/tank/data': unmount failed"),
            (True, ""),
        ]

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(pa, "log_msg"),
            patch.object(
                app.ctx.zfs_repository,
                "export_pool_detailed",
                side_effect=export_results,
            ) as mock_export,
            patch.object(
                app.ctx.zfs_repository,
                "dataset_for_mountpoint",
                return_value="tank/data",
            ),
            patch.object(
                app.ctx.zfs_repository,
                "list_datasets",
                return_value=[MagicMock(name="tank/data", ds_type="filesystem", mounted="yes")],
            ),
            patch.object(
                app.ctx.zfs_repository,
                "unmount_filesystem",
                return_value=(True, ""),
            ),
            patch.object(pa, "diagnose_dataset_busy"),
            patch.object(
                pa,
                "collect_dataset_busy_reasons",
                return_value=[
                    _fake_reason(
                        category="busy_processes",
                        dataset="tank/data",
                        detail="Open processes: bash",
                        resolvable=True,
                        data={"mountpoint": "/mnt/tank/data", "pids": [1234], "names": "bash"},
                    )
                ],
            ),
            patch.object(
                subprocess,
                "run",
                return_value=MagicMock(returncode=0, stderr=""),
            ) as mock_run,
            patch.object(pa, "time"),
            patch.object(pa, "os") as mock_pa_os,
        ):
            mock_pa_os.kill.side_effect = ProcessLookupError(1234)
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_export(app)

            mock_run.assert_any_call(
                ["kill", "-TERM", "1234"],
                check=False,
            )
            self.assertEqual(mock_export.call_count, 2)
            mock_refresh.assert_called_once_with(app)

    def test_export_approval_remove_iscsi_then_retry(self):
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        export_results = [
            (False, "cannot unmount '/tank': unmount failed"),
            (True, ""),
        ]

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(pa, "log_msg"),
            patch.object(
                app.ctx.zfs_repository,
                "export_pool_detailed",
                side_effect=export_results,
            ) as mock_export,
            patch.object(
                app.ctx.zfs_repository,
                "dataset_for_mountpoint",
                return_value=None,
            ),
            patch.object(
                app.ctx.zfs_repository,
                "list_datasets",
                return_value=[MagicMock(name="tank/proxmox/vm-105-disk-0", ds_type="volume")],
            ),
            patch.object(pa, "diagnose_dataset_busy"),
            patch.object(
                pa,
                "collect_dataset_busy_reasons",
                return_value=[
                    _fake_reason(
                        category="iscsi",
                        dataset="tank/proxmox/vm-105-disk-0",
                        detail="Zvol is exposed as an iSCSI LUN on "
                        "iqn.2026-02.local.stewie:threeamigos (LUN 3).",
                        resolvable=True,
                        data={
                            "bsname": "vm-105-disk-0",
                            "lun_info": "iqn.2026-02.local.stewie:threeamigos (LUN 3)",
                        },
                    )
                ],
            ),
            patch.object(
                subprocess,
                "run",
                return_value=MagicMock(returncode=0, stderr=""),
            ) as mock_run,
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_export(app)

            mock_run.assert_any_call(
                [
                    "targetcli",
                    "/iscsi/iqn.2026-02.local.stewie:threeamigos/tpg1/luns",
                    "delete",
                    "lun3",
                ],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            mock_run.assert_any_call(
                ["targetcli", "/backstores/block", "delete", "vm-105-disk-0"],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            self.assertEqual(mock_export.call_count, 2)
            mock_refresh.assert_called_once_with(app)

    def test_export_approval_disable_nfs_share_then_retry(self):
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        msg_dialog.return_value.run.return_value = pa.Gtk.ResponseType.YES

        export_results = [
            (False, "cannot unmount '/tank': unmount failed"),
            (True, ""),
        ]

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(pa, "log_msg"),
            patch.object(
                app.ctx.zfs_repository,
                "export_pool_detailed",
                side_effect=export_results,
            ) as mock_export,
            patch.object(
                app.ctx.zfs_repository,
                "dataset_for_mountpoint",
                return_value=None,
            ),
            patch.object(
                app.ctx.zfs_repository,
                "list_datasets",
                return_value=[MagicMock(name="tank/proxmox/vm-105-disk-0", ds_type="volume")],
            ),
            patch.object(
                app.ctx.zfs_repository,
                "set_property",
                return_value=True,
            ) as mock_set_property,
            patch.object(pa, "diagnose_dataset_busy"),
            patch.object(
                pa,
                "collect_dataset_busy_reasons",
                return_value=[
                    _fake_reason(
                        category="nfs",
                        dataset="tank/data",
                        detail="Dataset is shared via NFS (on).",
                        resolvable=True,
                        action="Unshare with 'zfs set sharenfs=off tank/data' before destroying.",
                        data={"prop": "sharenfs", "value": "on"},
                    )
                ],
            ),
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_export(app)

            mock_set_property.assert_called_once_with("tank/data", "sharenfs", "off")
            self.assertEqual(mock_export.call_count, 2)
            mock_refresh.assert_called_once_with(app)

    def test_export_declined_approval_aborts_retry(self):
        pa = _import_pool_actions()
        app = self._make_app_with_selection(
            pa,
            [{"name": "tank", "offsite_candidate": False}],
            ["tank"],
        )
        msg_dialog = MagicMock()
        # First YES confirms the export itself; the NO declines the recovery
        # approval ("Stop VM 105?"), which must abort the retry.
        msg_dialog.return_value.run.side_effect = [
            pa.Gtk.ResponseType.YES,
            pa.Gtk.ResponseType.NO,
        ]

        with (
            patch.object(pa, "refresh_pools_page") as mock_refresh,
            patch.object(pa, "refresh_scrub_table"),
            patch.object(pa, "schedule_scrub_refresh_burst"),
            patch.object(pa, "log_msg") as mock_log,
            patch.object(
                app.ctx.zfs_repository,
                "export_pool_detailed",
                return_value=(False, "cannot unmount '/tank': unmount failed"),
            ) as mock_export,
            patch.object(
                app.ctx.zfs_repository,
                "dataset_for_mountpoint",
                return_value=None,
            ),
            patch.object(
                app.ctx.zfs_repository,
                "list_datasets",
                return_value=[MagicMock(name="tank/proxmox/vm-105-disk-0", ds_type="volume")],
            ),
            patch.object(pa, "diagnose_dataset_busy"),
            patch.object(
                pa,
                "collect_dataset_busy_reasons",
                return_value=[
                    _fake_reason(
                        category="vm",
                        dataset="tank/proxmox/vm-105-disk-0",
                        detail="VM 105 is RUNNING and may be using tank/proxmox/vm-105-disk-0.",
                        resolvable=True,
                        data={"vmid": "105"},
                    )
                ],
            ),
        ):
            pa.Gtk.MessageDialog = msg_dialog
            pa.on_pools_export(app)

            self.assertEqual(mock_export.call_count, 1)
            logged = "\n".join(call.args[0] for call in mock_log.call_args_list)
            self.assertIn("cancelled by user", logged)
            mock_refresh.assert_called_once_with(app)


class TestLogPoolMountState(unittest.TestCase):
    """_log_pool_mount_state reports the post-failure mount state."""

    class _Row:
        def __init__(self, name, mounted):
            self.name = name
            self.mounted = mounted
            self.ds_type = "filesystem"

    def _repo(self, rows):
        repo = MagicMock()
        repo.list_datasets.return_value = rows
        return repo

    def test_reports_remaining_mounted_count(self):
        pa = _import_pool_actions()
        repo = self._repo(
            [
                self._Row("tank", "yes"),
                self._Row("tank/data", "no"),
                self._Row("tank/vms", "yes"),
            ]
        )
        with patch.object(pa, "log_msg") as mock_log:
            pa._log_pool_mount_state(repo, "tank")
        mock_log.assert_called_once_with("INFO: 2 of 3 datasets in 'tank' are still mounted")

    def test_all_unmounted_says_so(self):
        pa = _import_pool_actions()
        repo = self._repo([self._Row("tank", "no"), self._Row("tank/data", "no")])
        with patch.object(pa, "log_msg") as mock_log:
            pa._log_pool_mount_state(repo, "tank")
        mock_log.assert_called_once_with("INFO: All datasets in 'tank' are already unmounted")

    def test_listing_failure_stays_silent(self):
        pa = _import_pool_actions()
        repo = MagicMock()
        repo.list_datasets.side_effect = subprocess.CalledProcessError(1, "zfs")
        with patch.object(pa, "log_msg") as mock_log:
            pa._log_pool_mount_state(repo, "tank")
        mock_log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
