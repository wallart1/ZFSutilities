"""Tests for retention_actions.py — retention tab action handlers."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk


def _import_retention_actions():
    """Import retention_actions under a fresh mocked GTK context."""
    sys.modules.pop("retention_actions", None)
    with mock_gtk():
        import retention_actions
        return retention_actions


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

        with patch.object(ra, "get_all_retention", return_value={"default": []}), \
             patch.object(ra, "_get_online_pool_names", return_value=[]), \
             patch.object(ra, "save_retention") as mock_save, \
             patch.object(ra, "refresh_prune_pools") as mock_refresh, \
             patch.object(ra, "log_msg"):
            ra.Gtk.ComboBoxText = combo_mock
            ra.Gtk.Dialog.return_value.run.return_value = ra.Gtk.ResponseType.OK
            ra.on_retention_add_policy(app, MagicMock())

        # Combo should be populated with known pool names (strings), not dicts.
        calls = combo_instance.append_text.call_args_list
        names = [c[0][0] for c in calls]
        self.assertEqual(names, ["tank", "archive"])
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

        with patch.object(ra, "get_all_retention",
                          return_value={"default": [], "tank": []}), \
             patch.object(ra, "_get_online_pool_names", return_value=[]), \
             patch.object(ra, "save_retention") as mock_save, \
             patch.object(ra, "refresh_prune_pools") as mock_refresh, \
             patch.object(ra, "log_msg"):
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


class TestOnRetentionPruneOrder(unittest.TestCase):
    """Prune execution follows the visual list order, not selection order."""

    def _make_app(self, model_rows, selected_paths):
        app = MagicMock()
        app._ret_prune_label_entry = MagicMock()
        app._ret_prune_label_entry.get_text.return_value = "dailybackup"
        app._dry_run_active = False
        app.retention_runner = MagicMock()
        app.retention_runner.running = False

        model = _FakePruneModel(model_rows)
        selection = MagicMock()
        selection.get_selected_rows.return_value = (model, selected_paths)
        app._ret_prune_view.get_selection.return_value = selection
        return app, model

    def test_prune_follows_visual_order(self):
        ra = _import_retention_actions()
        app, _model = self._make_app(
            [["archive", "ONLINE"], ["tank", "ONLINE"], ["backup", "ONLINE"]],
            selected_paths=[1, 2, 0],  # selected in arbitrary order
        )

        ctx = MagicMock()
        ctx.parent_dir = "/bin"
        with patch.object(ra, "_show_error") as mock_error, \
             patch.object(ra, "log_msg"):
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

        with patch.object(ra, "get_all_retention", return_value=ctx.config["retention"]), \
             patch.object(ra, "save_config") as mock_save_config, \
             patch.object(ra, "refresh_prune_pools") as mock_refresh, \
             patch.object(ra, "log_msg"):
            ra.Gtk.MessageDialog.return_value.run.return_value = ra.Gtk.ResponseType.YES
            ra.on_retention_remove_policy(app, ctx)

        self.assertNotIn("tank", ctx.config["retention"])
        mock_save_config.assert_called_once_with(ctx.config)
        mock_refresh.assert_called_once_with(app)


if __name__ == "__main__":
    unittest.main()
