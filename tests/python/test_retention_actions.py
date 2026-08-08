"""Tests for retention_actions.py — retention tab action handlers."""

import os
import sys
import unittest
from unittest.mock import MagicMock, call, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import zfs_lock_manager as zlm
from test_support import mock_gtk


def _import_retention_actions():
    """Import retention_actions under a fresh mocked GTK context."""
    sys.modules.pop("retention_actions", None)
    with mock_gtk():
        import retention_actions

        return retention_actions


class TestOnRetentionPruneLocking(unittest.TestCase):
    """on_retention_prune checks for lock conflicts before launching zfscleanup."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def test_checks_lock_for_each_selected_pool(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["archive", "ONLINE"], ["tank", "ONLINE"]],
            selected_paths=[0, 1],
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"

        with (
            patch.object(ra, "show_error") as mock_error,
            patch.object(ra, "log_msg"),
            patch.object(ra, "zlm", autospec=True) as zlm_mock,
        ):
            zlm_mock.check.return_value = True
            zlm_mock.lock.return_value.__enter__ = MagicMock(return_value="lock-id")
            zlm_mock.lock.return_value.__exit__ = MagicMock(return_value=False)
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        zlm_mock.check.assert_has_calls(
            [
                call("archive", "w"),
                call("tank", "w"),
            ]
        )

    def test_aborts_when_pool_locked(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["archive", "ONLINE"], ["tank", "ONLINE"]],
            selected_paths=[0, 1],
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"

        with (
            patch.object(ra, "show_error") as mock_error,
            patch.object(ra, "log_msg") as mock_log,
            patch.object(ra, "zlm") as zlm_mock,
        ):
            zlm_mock.check.side_effect = [True, False]
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        zlm_mock.check.assert_called_with("tank", "w")
        mock_log.assert_any_call("WARN: cannot prune tank: pool is locked by another operation")
        app.retention_runner.set_steps.assert_not_called()
        app.retention_runner.start.assert_not_called()


class TestOnRetentionAddPolicy(unittest.TestCase):
    """on_retention_add_policy extracts pool names from dict known_pools."""

    def _make_app(self, known_pools, retention=None):
        app = MagicMock()
        app.known_pools = list(known_pools)
        app._ret_pool_list = list(retention.keys()) if retention else []
        app._ret_combo = MagicMock()
        app._ret_combo.append_text = MagicMock()
        app._ret_combo.set_active = MagicMock()
        return app

    def test_builds_candidates_from_dict_known_pools(self):
        ra = _import_retention_actions()
        app = self._make_app(
            [
                {"name": "tank", "offsite_candidate": False},
                {"name": "archive", "offsite_candidate": True},
            ],
            retention={"default": []},
        )

        combo_mock = MagicMock()
        combo_instance = combo_mock.new_with_entry.return_value
        combo_instance.get_child.return_value.get_text.return_value = "tank"
        combo_instance.append_text = MagicMock()
        combo_instance.set_active = MagicMock()

        with (
            patch.object(ra, "get_all_retention", return_value={"default": []}),
            patch.object(ra, "_get_online_pool_names", return_value=[]),
            patch.object(ra, "save_retention") as mock_save,
            patch.object(ra, "refresh_prune_pools") as mock_refresh,
            patch.object(ra, "log_msg"),
        ):
            ra.Gtk.ComboBoxText = combo_mock
            ra.Gtk.Dialog.return_value.run.return_value = ra.Gtk.ResponseType.OK
            ra.on_retention_add_policy(app, MagicMock())

        # Combo should be populated with known pool names (strings), not dicts,
        # plus the <offsite> placeholder.
        calls = combo_instance.append_text.call_args_list
        names = [c[0][0] for c in calls]
        self.assertEqual(names, ["tank", "archive", "<offsite>"])
        mock_save.assert_called_once()
        mock_refresh.assert_called_once_with(app)

    def test_excludes_pools_already_with_policy(self):
        ra = _import_retention_actions()
        app = self._make_app(
            [
                {"name": "tank", "offsite_candidate": False},
                {"name": "archive", "offsite_candidate": True},
            ],
            retention={"default": [], "tank": []},
        )

        combo_mock = MagicMock()
        combo_instance = combo_mock.new_with_entry.return_value
        combo_instance.get_child.return_value.get_text.return_value = "archive"
        combo_instance.append_text = MagicMock()
        combo_instance.set_active = MagicMock()

        with (
            patch.object(ra, "get_all_retention", return_value={"default": [], "tank": []}),
            patch.object(ra, "_get_online_pool_names", return_value=[]),
            patch.object(ra, "save_retention") as mock_save,
            patch.object(ra, "refresh_prune_pools") as mock_refresh,
            patch.object(ra, "log_msg"),
        ):
            ra.Gtk.ComboBoxText = combo_mock
            ra.Gtk.Dialog.return_value.run.return_value = ra.Gtk.ResponseType.OK
            ra.on_retention_add_policy(app, MagicMock())

        calls = combo_instance.append_text.call_args_list
        names = [c[0][0] for c in calls]
        self.assertNotIn("tank", names)
        self.assertIn("archive", names)
        mock_save.assert_called_once()
        mock_refresh.assert_called_once_with(app)


class _FakePruneModel:
    """List-like model for prune-order tests."""

    def __init__(self, rows):
        self._rows = [list(r) for r in rows]

    def __iter__(self):
        return iter(self._rows)

    def __getitem__(self, path):
        idx = path[0] if hasattr(path, "__getitem__") else path
        return self._rows[idx]


def _make_prune_app(
    model_rows,
    selected_paths,
    verb_active=False,
    ignore_retention=False,
    releaseholds_active=0,
    includes="",
    excludes="",
    startwith="",
    endwith="",
    snapshot_has="",
):
    """Return a minimal app mock for prune tests."""
    app = MagicMock()
    app._ret_prune_label_entry = MagicMock()
    app._ret_prune_label_entry.get_text.return_value = "dailybackup"
    app._ret_verb_check = MagicMock()
    app._ret_verb_check.get_active.return_value = verb_active
    app._dry_run_active = False
    app.retention_runner = MagicMock()
    app.retention_runner.running = False

    widgets = {
        "includes": MagicMock(get_text=MagicMock(return_value=includes)),
        "excludes": MagicMock(get_text=MagicMock(return_value=excludes)),
        "startwith": MagicMock(get_text=MagicMock(return_value=startwith)),
        "endwith": MagicMock(get_text=MagicMock(return_value=endwith)),
        "snapshot_has": MagicMock(get_text=MagicMock(return_value=snapshot_has)),
        "releaseholds": MagicMock(get_active=MagicMock(return_value=releaseholds_active)),
    }
    app._ret_mass_delete_widgets = widgets
    app._ret_ignore_retention_check = MagicMock()
    app._ret_ignore_retention_check.get_active.return_value = ignore_retention

    model = _FakePruneModel(model_rows)
    selection = MagicMock()
    selection.get_selected_rows.return_value = (model, selected_paths)
    app._ret_prune_view.get_selection.return_value = selection
    return app, model


class TestOnRetentionPruneVerb(unittest.TestCase):
    """Prune passes retain_verb to zfscleanup based on the GUI toggle."""

    def test_includes_retain_verb_when_toggle_active(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["tank", "ONLINE"]],
            selected_paths=[0],
            verb_active=True,
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        steps = app.retention_runner.set_steps.call_args[0][0]
        self.assertIn('retain_verb="Y"; ', steps[0].command[2])

    def test_omits_retain_verb_when_toggle_inactive(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["tank", "ONLINE"]],
            selected_paths=[0],
            verb_active=False,
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        steps = app.retention_runner.set_steps.call_args[0][0]
        self.assertIn('retain_verb="N"; ', steps[0].command[2])


class TestOnRetentionPruneOrder(unittest.TestCase):
    """Prune execution follows the visual list order, not selection order."""

    def test_prune_follows_visual_order(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["archive", "ONLINE"], ["tank", "ONLINE"], ["backup", "ONLINE"]],
            selected_paths=[1, 2, 0],  # selected in arbitrary order
        )

        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        steps = app.retention_runner.set_steps.call_args[0][0]
        descriptions = [step.description for step in steps]
        self.assertEqual(
            descriptions,
            [
                "Prune archive (label=dailybackup)",
                "Prune tank (label=dailybackup)",
                "Prune backup (label=dailybackup)",
            ],
        )


class TestOnRetentionPruneIgnoreMode(unittest.TestCase):
    """Prune uses zfsmassdelsnaps when 'Ignore retention policies' is checked."""

    def test_unchecked_uses_zfscleanup(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["tank", "ONLINE"]],
            selected_paths=[0],
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        steps = app.retention_runner.set_steps.call_args[0][0]
        self.assertEqual(len(steps), 1)
        self.assertIn("zfscleanup", steps[0].command[2])
        self.assertNotIn("zfsmassdelsnaps", steps[0].command[2])

    def test_checked_uses_zfsmassdelsnaps(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["archive", "ONLINE"], ["tank", "ONLINE"]],
            selected_paths=[0, 1],
            ignore_retention=True,
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        steps = app.retention_runner.set_steps.call_args[0][0]
        self.assertEqual(len(steps), 1)
        cmd = steps[0].command[2]
        self.assertIn("zfsmassdelsnaps", cmd)
        self.assertIn("mass_delete_snapshots archive tank", cmd)
        self.assertIn('ignore_retention_policies="Y"', cmd)

    def test_checked_includes_mass_delete_filters(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["archive", "ONLINE"]],
            selected_paths=[0],
            ignore_retention=True,
            includes="inc1 inc2",
            excludes="temp",
            startwith="pool/a",
            endwith="pool/z",
            snapshot_has="weekly",
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        cmd = app.retention_runner.set_steps.call_args[0][0][0].command[2]
        self.assertIn('includes=("inc1" "inc2")', cmd)
        self.assertIn('excludes=("temp")', cmd)
        self.assertIn('startwith="pool/a"', cmd)
        self.assertIn('endwith="pool/z"', cmd)
        self.assertIn('snapshot_has="weekly"', cmd)

    def test_checked_releaseholds_passed(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["archive", "ONLINE"]],
            selected_paths=[0],
            ignore_retention=True,
            releaseholds_active=0,
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        cmd = app.retention_runner.set_steps.call_args[0][0][0].command[2]
        self.assertIn('releaseholds="Y"', cmd)
        self.assertIn('releaseholds_tags=("offsite-*")', cmd)

    def test_checked_respect_releaseholds_off(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["archive", "ONLINE"]],
            selected_paths=[0],
            ignore_retention=True,
            releaseholds_active=1,
        )
        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        cmd = app.retention_runner.set_steps.call_args[0][0][0].command[2]
        self.assertIn('releaseholds="N"', cmd)

    def test_checked_dry_run_sets_dryrun_y(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["archive", "ONLINE"]],
            selected_paths=[0],
            ignore_retention=True,
        )
        app._dry_run_active = True
        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "show_error") as mock_error, patch.object(ra, "log_msg"):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        cmd = app.retention_runner.set_steps.call_args[0][0][0].command[2]
        self.assertIn("dryrun='Y'", cmd)


class TestOnRetentionAddPolicyValidation(unittest.TestCase):
    """on_retention_add_policy validates the entered pool name."""

    def _make_app(self, known_pools, retention=None):
        app = MagicMock()
        app.known_pools = list(known_pools)
        app._ret_pool_list = list(retention.keys()) if retention else []
        app._ret_combo = MagicMock()
        app._ret_combo.append_text = MagicMock()
        app._ret_combo.set_active = MagicMock()
        return app

    def _run_with_entry_text(self, app, text, retention, online=None, offsite_candidates=None):
        ra = _import_retention_actions()
        combo_mock = MagicMock()
        combo_instance = combo_mock.new_with_entry.return_value
        combo_instance.get_child.return_value.get_text.return_value = text
        combo_instance.append_text = MagicMock()
        combo_instance.set_active = MagicMock()

        ctx = MagicMock()
        ctx.config = {"pools": []}

        with (
            patch.object(ra, "get_all_retention", return_value=retention),
            patch.object(ra, "_get_online_pool_names", return_value=online or []),
            patch.object(ra, "get_offsite_candidate_names", return_value=offsite_candidates or []),
            patch.object(ra, "save_retention") as mock_save,
            patch.object(ra, "refresh_prune_pools") as mock_refresh,
            patch.object(ra, "show_error") as mock_error,
            patch.object(ra, "log_msg"),
        ):
            ra.Gtk.ComboBoxText = combo_mock
            ra.Gtk.Dialog.return_value.run.return_value = ra.Gtk.ResponseType.OK
            ra.on_retention_add_policy(app, ctx)

        return ra, mock_save, mock_error, mock_refresh

    def test_rejects_unknown_pool_name(self):
        app = self._make_app(
            [{"name": "tank", "offsite_candidate": False}],
            retention={"default": []},
        )
        _ra, mock_save, mock_error, _mock_refresh = self._run_with_entry_text(
            app, "notapool", {"default": []}
        )
        mock_save.assert_not_called()
        mock_error.assert_called_once()
        self.assertIn("notapool", mock_error.call_args[0][1])

    def test_accepts_offsite_placeholder(self):
        app = self._make_app(
            [{"name": "tank", "offsite_candidate": False}],
            retention={"default": []},
        )
        _ra, mock_save, mock_error, _mock_refresh = self._run_with_entry_text(
            app, "<offsite>", {"default": []}
        )
        mock_save.assert_called_once()
        mock_error.assert_not_called()

    def test_accepts_online_pool(self):
        app = self._make_app(
            [],
            retention={"default": []},
        )
        _ra, mock_save, mock_error, _mock_refresh = self._run_with_entry_text(
            app, "archive", {"default": []}, online=["archive"]
        )
        mock_save.assert_called_once()
        mock_error.assert_not_called()


class TestOnRetentionPruneOffsite(unittest.TestCase):
    """<offsite> in the prune list expands to all online offsite pools."""

    def test_prune_expands_offsite_to_all_online_candidates(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["<offsite>", "z22tb, z40tb"], ["tank", "ONLINE"]],
            selected_paths=[0],
        )
        ctx = MagicMock()
        ctx.config = {
            "pools": [
                {"name": "z22tb", "offsite_candidate": True},
                {"name": "z40tb", "offsite_candidate": True},
            ]
        }
        ctx.parent_dir = "/bin"

        with (
            patch.object(ra, "show_error") as mock_error,
            patch.object(ra, "log_msg"),
            patch.object(ra, "detect_offsite_pools", return_value=["z22tb", "z40tb"]),
        ):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        steps = app.retention_runner.set_steps.call_args[0][0]
        descriptions = [step.description for step in steps]
        self.assertEqual(
            descriptions,
            [
                "Prune z22tb (label=dailybackup)",
                "Prune z40tb (label=dailybackup)",
            ],
        )

    def test_prune_skips_offsite_when_none_online(self):
        ra = _import_retention_actions()
        app, _model = _make_prune_app(
            [["<offsite>", "not online"], ["tank", "ONLINE"]],
            selected_paths=[0],
        )
        ctx = MagicMock()
        ctx.config = {"pools": [{"name": "z22tb", "offsite_candidate": True}]}
        ctx.parent_dir = "/bin"

        with (
            patch.object(ra, "show_error") as mock_error,
            patch.object(ra, "log_msg") as mock_log,
            patch.object(ra, "detect_offsite_pools", return_value=[]),
        ):
            ra.on_retention_prune(app, ctx)

        mock_error.assert_not_called()
        app.retention_runner.set_steps.assert_not_called()
        mock_log.assert_any_call("WARN: No offsite pool online; skipping <offsite> prune")


class TestOnRetentionRemovePolicy(unittest.TestCase):
    """on_retention_remove_policy deletes a pool policy and refreshes the list."""

    def _make_app(self):
        app = MagicMock()
        app._ret_pool = "tank"
        app._ret_pool_list = ["default", "tank"]
        app._ret_combo = MagicMock()
        app._ret_original = {"tank": [{"name": "d", "retain": 3, "minage": 0}]}
        return app

    def test_remove_policy_refreshes_prune_list(self):
        ra = _import_retention_actions()
        app = self._make_app()
        ctx = MagicMock()
        ctx.config = {
            "retention": {
                "default": [{"name": "d", "retain": 3, "minage": 0}],
                "tank": [{"name": "d", "retain": 3, "minage": 0}],
            }
        }

        with (
            patch.object(ra, "get_all_retention", return_value=ctx.config["retention"]),
            patch.object(ra, "save_config") as mock_save_config,
            patch.object(ra, "refresh_prune_pools") as mock_refresh,
            patch.object(ra, "log_msg"),
        ):
            ra.Gtk.MessageDialog.return_value.run.return_value = ra.Gtk.ResponseType.YES
            ra.on_retention_remove_policy(app, ctx)

        self.assertNotIn("tank", ctx.config["retention"])
        mock_save_config.assert_called_once_with(ctx.config)
        mock_refresh.assert_called_once_with(app)


if __name__ == "__main__":
    unittest.main()
