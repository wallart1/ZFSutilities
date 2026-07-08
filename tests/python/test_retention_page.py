"""Tests for the Retention Policies tab UI."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from test_support import mock_gtk, temp_config_dir, capture_logs
from app_context import AppContext


def _clear_cached_modules(*names):
    """Remove named modules from sys.modules so they re-import fresh."""
    suffixes = tuple("." + n for n in names)
    for name in list(sys.modules.keys()):
        if name in names or name.endswith(suffixes):
            sys.modules.pop(name, None)


class _FakeEntry:
    """Entry stand-in that stores text and records connected callbacks."""

    def __init__(self, text=""):
        self._text = text
        self._callbacks = {}

    def set_text(self, text):
        self._text = text

    def get_text(self):
        return self._text

    def set_width_chars(self, *_args):
        pass

    def connect(self, signal, callback):
        self._callbacks[signal] = callback

    def emit(self, signal):
        cb = self._callbacks.get(signal)
        if cb:
            cb()


class _FakeLabel:
    """Label stand-in that records markup/text changes."""

    def __init__(self):
        self._text = ""
        self._markup = ""

    def set_text(self, text):
        self._text = text
        self._markup = ""

    def set_markup(self, markup):
        self._markup = markup
        self._text = ""


class _FakeStore:
    """Minimal ListStore stand-in for dirty comparisons."""

    def __init__(self, rows=None):
        self._rows = [list(r) for r in (rows or [])]

    def __iter__(self):
        return iter(self._rows)

    def clear(self):
        self._rows = []

    def append(self, row):
        self._rows.append(list(row))


class TestRetentionPagePruneLabel(unittest.TestCase):
    """Verify the prune snapshot label entry sizing."""

    def test_prune_label_entry_is_twenty_chars_wide(self):
        """The snapshot label entry should be wide enough for typical labels."""
        _clear_cached_modules(
            "retention_page",
            "retention_actions",
            "action_dispatch",
            "zfsutilities_gui",
        )
        with temp_config_dir(), mock_gtk():
            import retention_page as rp

            # Avoid filesystem / subprocess side effects during page creation
            rp._get_online_pool_names = MagicMock(return_value=[])
            rp._load_pool_into_store = MagicMock()

            app = MagicMock()
            app.ctx = AppContext(
                config={"retention": {"default": []}},
                script_dir="",
                parent_dir=os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                ),
                version="dev",
            )

            with patch.object(rp, "import_legacy_retention", return_value=False):
                rp.create_retention_page(app, app.ctx)

            app._ret_prune_label_entry.set_width_chars.assert_called_once_with(20)


class TestRetentionPagePoolLabel(unittest.TestCase):
    """Verify the current-pool label is updated when a pool is loaded."""

    def _fresh_module(self):
        _clear_cached_modules("retention_page")
        with mock_gtk():
            import retention_page as rp
            return rp

    def test_load_pool_updates_label(self):
        with temp_config_dir():
            rp = self._fresh_module()
            config = {
                "retention": {
                    "default": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                }
            }
            app = MagicMock()
            app.ctx = AppContext(
                config=config,
                script_dir="",
                parent_dir="",
                version="dev",
            )
            app._ret_prune_label_entry = _FakeEntry("dailybackup")
            app._ret_original_prune_label = "dailybackup"
            app._ret_status_label = _FakeLabel()
            app._ret_save_button = None
            app._ret_pool_list = ["default"]
            app._ret_pending = {}
            app._ret_original = {}
            app._ret_store = _FakeStore()

            rp._load_pool_into_store(app, app.ctx, "default")

            app._ret_pool_label.set_text.assert_called_once_with(
                "Editing retention policy for pool: default"
            )


class TestRetentionPageLabelDirtyState(unittest.TestCase):
    """Verify prune-label dirty detection, save, and revert."""

    def _fresh_module(self):
        _clear_cached_modules("retention_page")
        with mock_gtk():
            import retention_page as rp
            return rp

    def _make_app(self, rp, label="dailybackup", buckets=None):
        app = MagicMock()
        app._ret_prune_label_entry = _FakeEntry(label)
        app._ret_original_prune_label = label
        app._ret_store = _FakeStore(buckets or [
            ["d", "Daily", 3, 0],
            ["w", "Weekly", 2, 0],
        ])
        app._ret_original = {"default": [
            {"name": "d", "retain": 3, "minage": 0},
            {"name": "w", "retain": 2, "minage": 0},
        ]}
        app._ret_pool = "default"
        app._ret_status_label = _FakeLabel()
        app._ret_save_button = MagicMock()
        return app

    def test_label_change_marks_dirty(self):
        with temp_config_dir():
            rp = self._fresh_module()
            app = self._make_app(rp)
            self.assertFalse(rp._is_dirty(app))

            app._ret_prune_label_entry.set_text("weekly")
            self.assertTrue(rp._is_dirty(app))

    def test_bucket_change_still_marks_dirty(self):
        with temp_config_dir():
            rp = self._fresh_module()
            app = self._make_app(rp)
            self.assertFalse(rp._is_dirty(app))

            app._ret_store._rows[0][2] = 99
            self.assertTrue(rp._is_dirty(app))

    def test_update_status_styles_save_button_when_label_changes(self):
        with temp_config_dir():
            rp = self._fresh_module()
            app = self._make_app(rp)

            with patch.object(rp, "set_button_markup_red") as mock_red:
                app._ret_prune_label_entry.set_text("weekly")
                rp._update_ret_status(app)
                mock_red.assert_called_with(app._ret_save_button, True)

    def test_save_persists_label_and_clears_dirty(self):
        with temp_config_dir():
            rp = self._fresh_module()
            app = self._make_app(rp)
            app.ctx = AppContext(
                config={"retention": {"default": []}},
                script_dir="",
                parent_dir="",
                version="dev",
            )

            app._ret_prune_label_entry.set_text("weekly")
            self.assertTrue(rp._is_dirty(app))

            with patch.object(rp, "_update_ret_status"):
                rp._on_ret_save(None, app, app.ctx)

            self.assertEqual(app.ctx.config["prune_label"], "weekly")
            self.assertEqual(app._ret_original_prune_label, "weekly")
            self.assertFalse(rp._is_dirty(app))

    def test_save_normalizes_empty_label_to_default(self):
        with temp_config_dir():
            rp = self._fresh_module()
            app = self._make_app(rp)
            app.ctx = AppContext(
                config={"retention": {"default": []}},
                script_dir="",
                parent_dir="",
                version="dev",
            )

            app._ret_prune_label_entry.set_text("   ")
            with patch.object(rp, "_update_ret_status"):
                rp._on_ret_save(None, app, app.ctx)

            self.assertEqual(app.ctx.config["prune_label"], "dailybackup")
            self.assertEqual(app._ret_original_prune_label, "dailybackup")

    def test_revert_restores_label(self):
        with temp_config_dir():
            rp = self._fresh_module()
            app = self._make_app(rp)
            app.ctx = AppContext(
                config={"retention": {"default": [
                    {"name": "d", "retain": 3, "minage": 0},
                    {"name": "w", "retain": 2, "minage": 0},
                ]}},
                script_dir="",
                parent_dir="",
                version="dev",
            )

            app._ret_prune_label_entry.set_text("weekly")
            self.assertTrue(rp._is_dirty(app))

            with patch.object(rp, "_update_ret_status"):
                rp._on_ret_revert(None, app, app.ctx)

            self.assertEqual(app._ret_prune_label_entry.get_text(), "dailybackup")


class TestRetentionPageProfileConfig(unittest.TestCase):
    """Verify profile capture/recall includes the prune label."""

    def _fresh_module(self):
        _clear_cached_modules("retention_page")
        with mock_gtk():
            import retention_page as rp
            return rp

    def test_collect_profile_config_includes_label(self):
        with temp_config_dir():
            rp = self._fresh_module()
            app = MagicMock()
            app._ret_prune_label_entry = _FakeEntry("weekly")
            selection = MagicMock()
            selection.get_selected_rows.return_value = (MagicMock(), [])
            app._ret_prune_view.get_selection.return_value = selection

            cfg = rp.collect_retention_profile_config(app)

            self.assertEqual(cfg["prune_label"], "weekly")
            self.assertEqual(cfg["prune_pools"], [])

    def test_load_profile_config_sets_label(self):
        with temp_config_dir():
            rp = self._fresh_module()
            app = MagicMock()
            app._ret_prune_label_entry = _FakeEntry("dailybackup")
            app._ret_prune_store = []
            app._ret_prune_view = MagicMock()

            rp.load_retention_profile_config(
                app, {"prune_label": "monthly", "prune_pools": []}
            )

            self.assertEqual(app._ret_prune_label_entry.get_text(), "monthly")
            self.assertEqual(app._ret_original_prune_label, "monthly")


class TestRetentionPageMultiPoolSave(unittest.TestCase):
    """Verify edits to multiple pools are saved together."""

    def _fresh_module(self):
        _clear_cached_modules("retention_page")
        with mock_gtk():
            import retention_page as rp
            return rp

    def _make_app(self, rp, config, current_pool="default"):
        app = MagicMock()
        app.ctx = AppContext(
            config=config,
            script_dir="",
            parent_dir="",
            version="dev",
        )
        app._ret_prune_label_entry = _FakeEntry("dailybackup")
        app._ret_original_prune_label = "dailybackup"
        app._ret_status_label = _FakeLabel()
        app._ret_save_button = None
        app._ret_pool_list = ["default", "fivebays"]
        app._ret_pending = {}
        app._ret_original = {}
        app._ret_store = _FakeStore()
        rp._load_pool_into_store(app, app.ctx, current_pool)
        return app

    def test_switching_pools_preserves_edits(self):
        """Edits to a pool should survive switching away and back."""
        with temp_config_dir():
            rp = self._fresh_module()
            config = {
                "retention": {
                    "default": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                    "fivebays": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                }
            }
            app = self._make_app(rp, config, current_pool="default")
            app._ret_store._rows[0][2] = 99

            combo = MagicMock()
            combo.get_active_text.return_value = "fivebays"
            rp._on_pool_changed(combo, app)

            self.assertEqual(app._ret_pool, "fivebays")
            self.assertEqual(app._ret_pending["default"][0]["retain"], 99)

            app._ret_store._rows[0][2] = 77
            with patch.object(rp, "_update_ret_status"):
                rp._on_ret_save(None, app, app.ctx)

            self.assertEqual(config["retention"]["default"][0]["retain"], 99)
            self.assertEqual(config["retention"]["fivebays"][0]["retain"], 77)
            self.assertFalse(rp._is_dirty(app))

    def test_multi_pool_save_logs_all_pools(self):
        """Saving multiple changed pools should list each pool in the log."""
        with temp_config_dir():
            rp = self._fresh_module()
            config = {
                "retention": {
                    "default": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                    "fivebays": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                }
            }
            app = self._make_app(rp, config, current_pool="default")
            app._ret_store._rows[0][2] = 99

            combo = MagicMock()
            combo.get_active_text.return_value = "fivebays"
            rp._on_pool_changed(combo, app)
            app._ret_store._rows[0][2] = 77

            with capture_logs() as logs:
                with patch.object(rp, "_update_ret_status"):
                    rp._on_ret_save(None, app, app.ctx)

            self.assertTrue(any(
                "pools:" in log and "default" in log and "fivebays" in log
                for log in logs
            ))

    def test_dirty_detects_pending_pool_while_current_is_clean(self):
        """The dirty flag should reflect unsaved edits in non-current pools."""
        with temp_config_dir():
            rp = self._fresh_module()
            config = {
                "retention": {
                    "default": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                    "fivebays": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                }
            }
            app = self._make_app(rp, config, current_pool="default")
            app._ret_store._rows[0][2] = 99

            combo = MagicMock()
            combo.get_active_text.return_value = "fivebays"
            rp._on_pool_changed(combo, app)

            self.assertTrue(rp._is_dirty(app))

    def test_revert_clears_pending_for_current_pool(self):
        """Reverting a pool should drop its pending edits."""
        with temp_config_dir():
            rp = self._fresh_module()
            config = {
                "retention": {
                    "default": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                    "fivebays": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                }
            }
            app = self._make_app(rp, config, current_pool="default")
            app._ret_store._rows[0][2] = 99

            combo = MagicMock()
            combo.get_active_text.return_value = "fivebays"
            rp._on_pool_changed(combo, app)
            self.assertIn("default", app._ret_pending)

            # Switch back to default so the revert targets the edited pool.
            combo.get_active_text.return_value = "default"
            rp._on_pool_changed(combo, app)

            with patch.object(rp, "_update_ret_status"):
                rp._on_ret_revert(None, app, app.ctx)

            self.assertNotIn("default", app._ret_pending)
            self.assertEqual(app._ret_store._rows[0][2], 3)

    def test_round_trip_pool_still_saves_after_returning(self):
        """Editing a pool, switching away and back, then saving must persist it."""
        with temp_config_dir():
            rp = self._fresh_module()
            config = {
                "retention": {
                    "default": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                    "fivebays": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                }
            }
            app = self._make_app(rp, config, current_pool="fivebays")
            app._ret_store._rows[0][2] = 77

            combo = MagicMock()
            combo.get_active_text.return_value = "default"
            rp._on_pool_changed(combo, app)
            self.assertEqual(app._ret_pending["fivebays"][0]["retain"], 77)

            # Return to fivebays without further edits and save.
            combo.get_active_text.return_value = "fivebays"
            rp._on_pool_changed(combo, app)

            with capture_logs() as logs:
                with patch.object(rp, "_update_ret_status"):
                    rp._on_ret_save(None, app, app.ctx)

            self.assertEqual(config["retention"]["fivebays"][0]["retain"], 77)
            self.assertTrue(any(
                "Retention policy saved for pool: fivebays" in log
                for log in logs
            ))

    def test_revert_clears_pending_for_all_pools(self):
        """Revert should discard pending edits for every pool, matching Save."""
        with temp_config_dir():
            rp = self._fresh_module()
            config = {
                "retention": {
                    "default": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                    "fivebays": [
                        {"name": "d", "retain": 3, "minage": 0},
                    ],
                }
            }
            app = self._make_app(rp, config, current_pool="default")
            app._ret_store._rows[0][2] = 99

            combo = MagicMock()
            combo.get_active_text.return_value = "fivebays"
            rp._on_pool_changed(combo, app)
            app._ret_store._rows[0][2] = 77

            with patch.object(rp, "_update_ret_status"):
                rp._on_ret_revert(None, app, app.ctx)

            self.assertEqual(app._ret_pending, {})
            self.assertEqual(app._ret_store._rows[0][2], 3)
            self.assertFalse(rp._is_dirty(app))


class TestRetentionPageNewInstallCleanup(unittest.TestCase):
    """Verify fresh installs keep only the default retention policy."""

    def _fresh_module(self):
        _clear_cached_modules("retention_page")
        with mock_gtk():
            import retention_page as rp
            return rp

    def _make_context(self, config, is_new_install):
        return AppContext(
            config=config,
            script_dir="",
            parent_dir="",
            version="dev",
            is_new_install=is_new_install,
        )

    def test_new_install_clears_pool_specific_policies(self):
        """Legacy-imported pool policies are cleared on a fresh install."""
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=[])
            rp._load_pool_into_store = MagicMock()

            default_buckets = [
                {"name": "d", "retain": 3, "minage": 0},
            ]
            config = {"retention": {"default": default_buckets}}
            ctx = self._make_context(config, is_new_install=True)

            def _fake_import_legacy(c, _parent_dir):
                c.setdefault("retention", {})["threeamigos"] = [
                    dict(b) for b in default_buckets
                ]
                c["retention"]["fivebays"] = [dict(b) for b in default_buckets]
                return ["threeamigos", "fivebays"]

            app = MagicMock()
            app.ctx = ctx
            app._ui_state = MagicMock()

            with patch.object(rp, "import_legacy_retention", side_effect=_fake_import_legacy):
                rp.create_retention_page(app, ctx)

            self.assertIn("default", config["retention"])
            self.assertNotIn("threeamigos", config["retention"])
            self.assertNotIn("fivebays", config["retention"])
            self.assertFalse(ctx.is_new_install)

    def test_existing_install_keeps_pool_specific_policies(self):
        """Pool policies are not cleared when this is not a new install."""
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=[])
            rp._load_pool_into_store = MagicMock()

            default_buckets = [{"name": "d", "retain": 3, "minage": 0}]
            config = {
                "retention": {
                    "default": default_buckets,
                    "tank": [{"name": "d", "retain": 7, "minage": 0}],
                }
            }
            ctx = self._make_context(config, is_new_install=False)

            app = MagicMock()
            app.ctx = ctx
            app._ui_state = MagicMock()

            with patch.object(rp, "import_legacy_retention", return_value=[]):
                rp.create_retention_page(app, ctx)

            self.assertIn("tank", config["retention"])
            self.assertEqual(config["retention"]["tank"][0]["retain"], 7)


class TestRetentionPagePruneList(unittest.TestCase):
    """Verify the prune list only shows online pools with retention policies."""

    def _fresh_module(self):
        _clear_cached_modules("retention_page")
        with mock_gtk():
            import retention_page as rp
            return rp

    def test_prune_list_includes_online_pools_with_policies(self):
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=["tank", "archive"])

            app = MagicMock()
            app.ctx = AppContext(
                config={
                    "retention": {
                        "default": [{"name": "d", "retain": 3, "minage": 0}],
                        "tank": [{"name": "d", "retain": 3, "minage": 0}],
                        "archive": [{"name": "d", "retain": 3, "minage": 0}],
                    }
                },
                script_dir="",
                parent_dir="",
                version="dev",
            )
            app._ret_prune_store = _FakeStore()

            rp.refresh_prune_pools(app)

            pools = [row[0] for row in app._ret_prune_store]
            self.assertEqual(pools, ["archive", "tank"])
            self.assertTrue(all(row[1] == "ONLINE" for row in app._ret_prune_store))

    def test_prune_list_excludes_pools_without_policy(self):
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=["tank", "nopolicy"])

            app = MagicMock()
            app.ctx = AppContext(
                config={
                    "retention": {
                        "default": [{"name": "d", "retain": 3, "minage": 0}],
                        "tank": [{"name": "d", "retain": 3, "minage": 0}],
                    }
                },
                script_dir="",
                parent_dir="",
                version="dev",
            )
            app._ret_prune_store = _FakeStore()

            rp.refresh_prune_pools(app)

            pools = [row[0] for row in app._ret_prune_store]
            self.assertIn("tank", pools)
            self.assertNotIn("nopolicy", pools)

    def test_prune_list_excludes_offline_pools_with_policy(self):
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=["tank"])

            app = MagicMock()
            app.ctx = AppContext(
                config={
                    "retention": {
                        "default": [{"name": "d", "retain": 3, "minage": 0}],
                        "tank": [{"name": "d", "retain": 3, "minage": 0}],
                        "offline": [{"name": "d", "retain": 3, "minage": 0}],
                    }
                },
                script_dir="",
                parent_dir="",
                version="dev",
            )
            app._ret_prune_store = _FakeStore()

            rp.refresh_prune_pools(app)

            pools = [row[0] for row in app._ret_prune_store]
            self.assertIn("tank", pools)
            self.assertNotIn("offline", pools)

    def test_prune_list_preserves_existing_order_for_remaining_pools(self):
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=["tank", "archive"])

            app = MagicMock()
            app.ctx = AppContext(
                config={
                    "retention": {
                        "default": [{"name": "d", "retain": 3, "minage": 0}],
                        "tank": [{"name": "d", "retain": 3, "minage": 0}],
                        "archive": [{"name": "d", "retain": 3, "minage": 0}],
                    }
                },
                script_dir="",
                parent_dir="",
                version="dev",
            )
            app._ret_prune_store = _FakeStore([["tank", "ONLINE"]])

            rp.refresh_prune_pools(app)

            pools = [row[0] for row in app._ret_prune_store]
            self.assertEqual(pools, ["tank", "archive"])

    def test_prune_list_uses_saved_order_on_refresh(self):
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=["tank", "archive"])

            app = MagicMock()
            app.ctx = AppContext(
                config={
                    "retention": {
                        "default": [{"name": "d", "retain": 3, "minage": 0}],
                        "tank": [{"name": "d", "retain": 3, "minage": 0}],
                        "archive": [{"name": "d", "retain": 3, "minage": 0}],
                    },
                    "prune_pools_order": ["archive", "tank"],
                },
                script_dir="",
                parent_dir="",
                version="dev",
            )
            app._ret_prune_store = _FakeStore()

            rp.refresh_prune_pools(app)

            pools = [row[0] for row in app._ret_prune_store]
            self.assertEqual(pools, ["archive", "tank"])

    def test_drag_end_saves_store_order(self):
        with temp_config_dir():
            rp = self._fresh_module()

            app = MagicMock()
            app.ctx = AppContext(
                config={"retention": {"default": []}},
                script_dir="",
                parent_dir="",
                version="dev",
            )
            app._ret_prune_store = _FakeStore([["tank", "ONLINE"], ["archive", "ONLINE"]])

            rp._on_prune_drag_end(MagicMock(), MagicMock(), app)

            self.assertEqual(app.ctx.config["prune_pools_order"], ["tank", "archive"])


class TestTabNavigationWiring(unittest.TestCase):
    """Editable spin renderers are wired for Tab/Shift+Tab navigation."""

    def _fresh_module(self):
        _clear_cached_modules("retention_page")
        with mock_gtk():
            import retention_page as rp
            return rp

    def test_spin_renderers_connect_editing_started(self):
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=[])
            rp._load_pool_into_store = MagicMock()

            renderers = []

            def _make_spin():
                r = MagicMock()
                r._connections = []

                def _connect(signal, callback, *args):
                    r._connections.append((signal, callback, args))

                r.connect.side_effect = _connect
                renderers.append(r)
                return r

            app = MagicMock()
            app.ctx = AppContext(
                config={"retention": {"default": []}},
                script_dir="",
                parent_dir=os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                ),
                version="dev",
            )

            with patch.object(rp.Gtk, "CellRendererSpin", side_effect=_make_spin), \
                 patch.object(rp, "import_legacy_retention", return_value=False):
                rp.create_retention_page(app, app.ctx)

            self.assertEqual(len(renderers), 2)
            for idx, renderer in enumerate(renderers):
                editing_connections = [
                    c for c in renderer._connections if c[0] == "editing-started"
                ]
                self.assertEqual(len(editing_connections), 1,
                                 f"Renderer {idx} should have one editing-started connection")
                _signal, handler, args = editing_connections[0]
                self.assertIs(handler, rp._on_editing_started)
                self.assertEqual(args[1], 2 + idx)

    def test_editing_started_handler_wires_key_press(self):
        with temp_config_dir():
            rp = self._fresh_module()
            rp._get_online_pool_names = MagicMock(return_value=[])
            rp._load_pool_into_store = MagicMock()

            renderers = []

            def _make_spin():
                r = MagicMock()
                r._connections = []

                def _connect(signal, callback, *args):
                    r._connections.append((signal, callback, args))

                r.connect.side_effect = _connect
                renderers.append(r)
                return r

            app = MagicMock()
            app.ctx = AppContext(
                config={"retention": {"default": []}},
                script_dir="",
                parent_dir=os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                ),
                version="dev",
            )

            with patch.object(rp.Gtk, "CellRendererSpin", side_effect=_make_spin), \
                 patch.object(rp, "import_legacy_retention", return_value=False):
                rp.create_retention_page(app, app.ctx)

            renderer = renderers[0]
            editing_connections = [
                c for c in renderer._connections if c[0] == "editing-started"
            ]
            self.assertEqual(len(editing_connections), 1)
            _signal, handler, args = editing_connections[0]
            editable = MagicMock()
            treeview = args[0]
            col_idx = args[1]

            with patch.object(rp, "handle_editing_key_press") as mock_handler:
                handler(renderer, editable, "0", treeview, col_idx)

            editable.connect.assert_called_once()
            conn_args = editable.connect.call_args[0]
            self.assertEqual(conn_args[0], "key-press-event")
            self.assertIs(conn_args[1], mock_handler)
            self.assertEqual(conn_args[2], treeview)
            self.assertEqual(conn_args[3], "0")
            self.assertEqual(conn_args[4], col_idx)
            self.assertEqual(conn_args[5], [2, 3])


if __name__ == "__main__":
    unittest.main()
