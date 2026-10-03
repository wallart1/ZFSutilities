"""Tests for pool_profile_dialogs.py — pool profile manager and editor."""

import os
import sys
import unittest
from typing import ClassVar
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk, requires_gi

pytestmark = requires_gi

from pool_profiles import POOL_PROPERTIES
from workload_profiles import LIVE_PROPERTIES


def _import_pool_profile_dialogs():
    """Import pool_profile_dialogs under a fresh mocked GTK context."""
    sys.modules.pop("pool_profile_dialogs", None)
    with mock_gtk(fresh=True):
        import pool_profile_dialogs

        return pool_profile_dialogs


def _import_action_dispatch():
    """Import action_dispatch under a fresh mocked GTK context."""
    sys.modules.pop("action_dispatch", None)
    sys.modules.pop("pool_profile_dialogs", None)
    with mock_gtk(fresh=True):
        import action_dispatch

        return action_dispatch


def _make_app():
    """Return a mocked app object ready for pool-profile dialog tests."""
    app = MagicMock()
    app.config = {}
    return app


def _make_tree_view(store, paths):
    """Return a TreeView mock whose selection reports *paths* against *store*."""
    view = MagicMock()
    selection = MagicMock()
    selection.get_selected_rows.return_value = (store, paths)
    view.get_selection.return_value = selection
    return view


class GtkListStoreAdapter:
    """ListStore stand-in that records rows and supports view selection."""

    def __init__(self, rows=None):
        self.rows = rows or []

    def clear(self):
        self.rows = []

    def append(self, row):
        self.rows.append(list(row))

    def get_iter(self, path):
        return path if isinstance(path, int) else 0

    def get_value(self, it, col):
        return self.rows[it][col]


class _FakeEntry:
    """Entry stand-in that returns a value fixed at creation time."""

    def __init__(self, values, keys, idx):
        self._values = values
        self._keys = keys
        self._idx = idx
        self.sensitive = None

    def get_text(self):
        return str(self._values.get(self._keys[self._idx], ""))

    def set_text(self, text):
        pass

    def set_sensitive(self, value):
        self.sensitive = value

    def set_placeholder_text(self, text):
        pass


class _FakeComboBoxText:
    """ComboBoxText stand-in that returns a value fixed at creation time."""

    def __init__(self, values, keys, idx):
        self._values = values
        self._keys = keys
        self._idx = idx

    def append_text(self, text):
        pass

    def set_active(self, index):
        pass

    def get_active_text(self):
        return str(self._values.get(self._keys[self._idx], ""))


class _FakePoolProfileEditor:
    """Controlled stand-in for the Add/Edit Pool Profile dialog widgets.

    Widget creation order mirrors the editor: name and description entries,
    the blocksize combo, one combo per curated pool property, then one entry
    per root filesystem property, then the notes buffer.
    """

    ENTRY_KEYS: ClassVar[list[str]] = ["name", "description", *LIVE_PROPERTIES]
    COMBO_KEYS: ClassVar[list[str]] = ["blocksize", *POOL_PROPERTIES]

    def __init__(self, ppd, values, dialog_responses):
        self.ppd = ppd
        self.values = values
        self.dialog_responses = list(dialog_responses)
        self._entry_counter = [0]
        self._combo_counter = [0]
        self.entries = []
        self._patches = []

    def _make_entry(self, *_args, **_kwargs):
        idx = self._entry_counter[0]
        self._entry_counter[0] += 1
        entry = _FakeEntry(self.values, self.ENTRY_KEYS, idx)
        self.entries.append(entry)
        return entry

    def _make_combo(self, *_args, **_kwargs):
        idx = self._combo_counter[0]
        self._combo_counter[0] += 1
        return _FakeComboBoxText(self.values, self.COMBO_KEYS, idx)

    def _make_text_buffer(self, *_args, **_kwargs):
        values = self.values

        class _Buf:
            def get_text(self, _start, _end, _hidden):
                return str(values.get("notes", ""))

            def set_text(self, text):
                pass

            def get_start_iter(self):
                return None

            def get_end_iter(self):
                return None

        return _Buf()

    def _make_dialog(self, *_args, **_kwargs):
        responses = self.dialog_responses
        idx = [0]

        def _run():
            resp = responses[idx[0]]
            idx[0] += 1
            return resp

        dialog = MagicMock()
        dialog.run.side_effect = _run
        return dialog

    def __enter__(self):
        self._patches = [
            patch.object(self.ppd.Gtk, "Entry", side_effect=self._make_entry),
            patch.object(self.ppd.Gtk, "ComboBoxText", side_effect=self._make_combo),
            patch.object(self.ppd.Gtk, "TextBuffer", side_effect=self._make_text_buffer),
            patch.object(self.ppd, "create_dialog", side_effect=self._make_dialog),
            patch.object(
                self.ppd.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=self.ppd.Gtk.ResponseType.OK)),
            ),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in reversed(self._patches):
            p.stop()
        return False


class TestManagePoolProfilesDialog(unittest.TestCase):
    """Manage Pool Profiles dialog tests."""

    def _profiles(self):
        return {
            "general": {
                "description": "General-purpose pool.",
                "blocksize": "recommended",
                "pool_properties": {"autotrim": "on"},
                "filesystem_properties": {"compression": "lz4"},
                "notes": "",
            },
        }

    def _dialog_app(self):
        app = _make_app()
        app.config["pool_profiles"] = self._profiles()
        return app

    def test_manage_dialog_lists_profiles(self):
        ppd = _import_pool_profile_dialogs()
        app = self._dialog_app()
        store = MagicMock()
        view = _make_tree_view(GtkListStoreAdapter(), [])

        with (
            patch.object(
                ppd,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(ppd.Gtk, "ListStore", return_value=store),
            patch.object(ppd.Gtk, "TreeView", return_value=view),
        ):
            ppd.show_manage_pool_profiles_dialog(app)

            self.assertTrue(store.append.called)
            appended = [call.args[0] for call in store.append.call_args_list]
            self.assertIn(
                ["general", "recommended", "General-purpose pool.", "built-in"],
                appended,
            )

    def test_manage_dialog_add_opens_editor(self):
        ppd = _import_pool_profile_dialogs()
        app = self._dialog_app()
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        with (
            patch.object(
                ppd,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(ppd.Gtk, "Button", side_effect=make_button),
            patch.object(
                ppd.Gtk,
                "TreeView",
                return_value=_make_tree_view(GtkListStoreAdapter(), []),
            ),
        ):
            ppd.show_manage_pool_profiles_dialog(app)

        add_btn = buttons[0]
        add_handler = add_btn.connect.call_args[0][1]

        with patch.object(ppd, "show_pool_profile_editor_dialog") as mock_editor:
            add_handler(add_btn)
            mock_editor.assert_called_once_with(app)

    def test_manage_dialog_edit_opens_editor_for_custom_profile(self):
        ppd = _import_pool_profile_dialogs()
        app = self._dialog_app()
        app.config["pool_profiles"] = {
            "custom": {
                "description": "Custom pool.",
                "blocksize": "4096 bytes",
                "pool_properties": {"autotrim": "off"},
                "filesystem_properties": {},
                "notes": "",
            }
        }
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        store = GtkListStoreAdapter([["custom", "4096 bytes", "Custom pool."]])
        view = _make_tree_view(store, [0])

        with (
            patch.object(
                ppd,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(ppd.Gtk, "Button", side_effect=make_button),
            patch.object(ppd.Gtk, "ListStore", return_value=store),
            patch.object(ppd.Gtk, "TreeView", return_value=view),
        ):
            ppd.show_manage_pool_profiles_dialog(app)

            edit_btn = buttons[1]
            edit_handler = edit_btn.connect.call_args[0][1]

            with patch.object(ppd, "show_pool_profile_editor_dialog") as mock_editor:
                edit_handler(edit_btn)
                mock_editor.assert_called_once_with(app, "custom")

    def test_manage_dialog_builtin_selection_editable_delete_disabled(self):
        ppd = _import_pool_profile_dialogs()
        app = self._dialog_app()
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        store = GtkListStoreAdapter([["general", "recommended", "General-purpose pool."]])
        view = _make_tree_view(store, [0])

        with (
            patch.object(
                ppd,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(ppd.Gtk, "Button", side_effect=make_button),
            patch.object(ppd.Gtk, "ListStore", return_value=store),
            patch.object(ppd.Gtk, "TreeView", return_value=view),
        ):
            ppd.show_manage_pool_profiles_dialog(app)

            edit_btn, delete_btn = buttons[1], buttons[2]
            selection = view.get_selection.return_value
            changed_handler = selection.connect.call_args[0][1]
            changed_handler(selection)

            edit_btn.set_sensitive.assert_called_with(True)
            delete_btn.set_sensitive.assert_called_with(False)
            delete_tooltip = delete_btn.set_tooltip_text.call_args[0][0]
            self.assertIn("cannot be deleted", delete_tooltip)

    def test_manage_dialog_delete_custom_profile(self):
        ppd = _import_pool_profile_dialogs()
        app = self._dialog_app()
        app.config["pool_profiles"] = {
            "custom": {
                "description": "Custom pool.",
                "blocksize": "recommended",
                "pool_properties": {},
                "filesystem_properties": {},
                "notes": "",
            }
        }
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        store = GtkListStoreAdapter([["custom", "recommended", "Custom pool."]])
        view = _make_tree_view(store, [0])

        with (
            patch.object(
                ppd,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(ppd.Gtk, "Button", side_effect=make_button),
            patch.object(ppd.Gtk, "ListStore", return_value=store),
            patch.object(ppd.Gtk, "TreeView", return_value=view),
            patch.object(
                ppd.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.YES)),
            ),
        ):
            ppd.show_manage_pool_profiles_dialog(app)

            delete_btn = buttons[2]
            delete_handler = delete_btn.connect.call_args[0][1]

            with patch.object(ppd, "delete_pool_profile", return_value=True) as mock_delete:
                delete_handler(delete_btn)
                mock_delete.assert_called_once_with(app.config, "custom")

    def test_manage_dialog_delete_builtin_profile_refused(self):
        ppd = _import_pool_profile_dialogs()
        app = self._dialog_app()
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        store = GtkListStoreAdapter([["general", "recommended", "General-purpose pool."]])
        view = _make_tree_view(store, [0])

        with (
            patch.object(
                ppd,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(ppd.Gtk, "Button", side_effect=make_button),
            patch.object(ppd.Gtk, "ListStore", return_value=store),
            patch.object(ppd.Gtk, "TreeView", return_value=view),
        ):
            ppd.show_manage_pool_profiles_dialog(app)

            delete_btn = buttons[2]
            delete_handler = delete_btn.connect.call_args[0][1]

            with patch.object(ppd, "delete_pool_profile") as mock_delete:
                delete_handler(delete_btn)
                mock_delete.assert_not_called()

    def test_manage_dialog_reset_defaults(self):
        ppd = _import_pool_profile_dialogs()
        app = self._dialog_app()
        buttons = []

        def make_button(*args, **kwargs):
            btn = MagicMock()
            buttons.append(btn)
            return btn

        with (
            patch.object(
                ppd,
                "create_dialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.CLOSE)),
            ),
            patch.object(ppd.Gtk, "Button", side_effect=make_button),
            patch.object(
                ppd.Gtk,
                "TreeView",
                return_value=_make_tree_view(GtkListStoreAdapter(), []),
            ),
            patch.object(
                ppd.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.YES)),
            ),
        ):
            ppd.show_manage_pool_profiles_dialog(app)

            reset_btn = buttons[3]
            reset_handler = reset_btn.connect.call_args[0][1]

            with patch.object(ppd, "reset_pool_profiles") as mock_reset:
                reset_handler(reset_btn)
                mock_reset.assert_called_once_with(app.config)


class TestPoolProfileEditorDialog(unittest.TestCase):
    """Add/Edit Pool Profile dialog tests."""

    def _app(self):
        app = _make_app()
        app.config["pool_profiles"] = {
            "general": {
                "description": "General-purpose pool.",
                "blocksize": "recommended",
                "pool_properties": {"autotrim": "on"},
                "filesystem_properties": {"compression": "lz4"},
                "notes": "",
            },
        }
        return app

    def test_add_new_profile(self):
        ppd = _import_pool_profile_dialogs()
        app = self._app()

        values = {
            "name": "fast-pool",
            "description": "Fast all-SSD pool.",
            "blocksize": "8192 bytes",
            "autotrim": "on",
            "failmode": "continue",
            "compression": "zstd",
            "recordsize": "64K",
            "notes": "SSD tuning.",
        }

        with (
            _FakePoolProfileEditor(ppd, values, [ppd.Gtk.ResponseType.OK]),
            patch("feature_config.save_config"),
        ):
            ppd.show_pool_profile_editor_dialog(app)

        profiles = app.config["pool_profiles"]
        self.assertIn("fast-pool", profiles)
        self.assertEqual(profiles["fast-pool"]["description"], "Fast all-SSD pool.")
        self.assertEqual(profiles["fast-pool"]["blocksize"], "8192 bytes")
        # Unset combos ("(not set)" / empty) must not enter the profile.
        self.assertEqual(
            profiles["fast-pool"]["pool_properties"],
            {"autotrim": "on", "failmode": "continue"},
        )
        self.assertEqual(
            profiles["fast-pool"]["filesystem_properties"],
            {"compression": "zstd", "recordsize": "64K"},
        )
        self.assertEqual(profiles["fast-pool"]["notes"], "SSD tuning.")

    def test_edit_custom_profile(self):
        ppd = _import_pool_profile_dialogs()
        app = self._app()
        app.config["pool_profiles"] = {
            "custom": {
                "description": "Custom pool.",
                "blocksize": "recommended",
                "pool_properties": {"autotrim": "off"},
                "filesystem_properties": {},
                "notes": "",
            }
        }

        values = {
            "name": "custom",
            "description": "Updated description.",
            "blocksize": "4096 bytes",
            "autotrim": "on",
            "compression": "zstd",
            "notes": "Updated notes.",
        }

        with (
            _FakePoolProfileEditor(ppd, values, [ppd.Gtk.ResponseType.OK]),
            patch("feature_config.save_config"),
        ):
            ppd.show_pool_profile_editor_dialog(app, "custom")

        profiles = app.config["pool_profiles"]
        self.assertEqual(profiles["custom"]["description"], "Updated description.")
        self.assertEqual(profiles["custom"]["blocksize"], "4096 bytes")
        self.assertEqual(profiles["custom"]["pool_properties"], {"autotrim": "on"})
        self.assertEqual(profiles["custom"]["filesystem_properties"], {"compression": "zstd"})
        self.assertEqual(profiles["custom"]["notes"], "Updated notes.")

    def test_edit_builtin_saves_as_new_custom_profile(self):
        """Editing a built-in is a template: save requires a new name."""
        ppd = _import_pool_profile_dialogs()
        app = self._app()

        values = {
            "name": "general-fast",
            "description": "Faster variant of general.",
            "blocksize": "8192 bytes",
            "autotrim": "on",
            "compression": "lz4",
            "notes": "Tuned copy of general.",
        }

        editor = _FakePoolProfileEditor(ppd, values, [ppd.Gtk.ResponseType.OK])
        with (
            editor,
            patch("feature_config.save_config"),
        ):
            ppd.show_pool_profile_editor_dialog(app, "general")

        # The name field stays editable when a built-in is opened for editing.
        self.assertTrue(editor.entries[0].sensitive)

        profiles = app.config["pool_profiles"]
        self.assertIn("general-fast", profiles)
        self.assertEqual(profiles["general-fast"]["blocksize"], "8192 bytes")
        # The built-in itself is untouched.
        self.assertEqual(profiles["general"]["description"], "General-purpose pool.")

    def test_edit_builtin_cannot_save_under_builtin_name(self):
        ppd = _import_pool_profile_dialogs()
        app = self._app()

        values = {
            "name": "archival",
            "description": "Attempt to shadow a built-in.",
            "blocksize": "recommended",
            "autotrim": "off",
            "compression": "zstd",
            "notes": "",
        }

        with (
            _FakePoolProfileEditor(
                ppd, values, [ppd.Gtk.ResponseType.OK, ppd.Gtk.ResponseType.CANCEL]
            ),
            patch("feature_config.save_config") as mock_save,
        ):
            ppd.show_pool_profile_editor_dialog(app, "general")

        mock_save.assert_not_called()
        profiles = app.config["pool_profiles"]
        self.assertNotIn("archival", profiles)
        self.assertEqual(profiles["general"]["description"], "General-purpose pool.")

    def test_edit_builtin_overwrites_custom_after_confirmation(self):
        ppd = _import_pool_profile_dialogs()
        app = self._app()
        app.config["pool_profiles"]["custom"] = {
            "description": "Old custom.",
            "blocksize": "recommended",
            "pool_properties": {},
            "filesystem_properties": {},
            "notes": "",
        }

        # Case-variant of the existing custom name: must overwrite the
        # existing entry, not create a case-duplicate.
        values = {
            "name": "Custom",
            "description": "Rebuilt from general.",
            "blocksize": "recommended",
            "autotrim": "on",
            "compression": "zstd",
            "notes": "",
        }

        with (
            _FakePoolProfileEditor(ppd, values, [ppd.Gtk.ResponseType.OK]),
            patch("feature_config.save_config"),
            patch.object(
                ppd.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.YES)),
            ) as mock_message_dialog,
        ):
            ppd.show_pool_profile_editor_dialog(app, "general")

        confirm_text = mock_message_dialog.call_args.kwargs["text"]
        self.assertIn("already exists", confirm_text)
        self.assertIn("custom", confirm_text)

        profiles = app.config["pool_profiles"]
        self.assertNotIn("Custom", profiles)
        self.assertEqual(profiles["custom"]["description"], "Rebuilt from general.")
        # The built-in itself is untouched.
        self.assertEqual(profiles["general"]["description"], "General-purpose pool.")

    def test_edit_builtin_overwrite_declined_saves_nothing(self):
        ppd = _import_pool_profile_dialogs()
        app = self._app()
        app.config["pool_profiles"]["custom"] = {
            "description": "Old custom.",
            "blocksize": "recommended",
            "pool_properties": {},
            "filesystem_properties": {},
            "notes": "",
        }

        values = {
            "name": "custom",
            "description": "Rebuilt from general.",
            "blocksize": "recommended",
            "autotrim": "on",
            "compression": "zstd",
            "notes": "",
        }

        with (
            _FakePoolProfileEditor(
                ppd, values, [ppd.Gtk.ResponseType.OK, ppd.Gtk.ResponseType.CANCEL]
            ),
            patch("feature_config.save_config") as mock_save,
            patch.object(
                ppd.Gtk,
                "MessageDialog",
                return_value=MagicMock(run=MagicMock(return_value=ppd.Gtk.ResponseType.NO)),
            ),
        ):
            ppd.show_pool_profile_editor_dialog(app, "general")

        mock_save.assert_not_called()
        profiles = app.config["pool_profiles"]
        self.assertEqual(profiles["custom"]["description"], "Old custom.")
        self.assertEqual(profiles["general"]["description"], "General-purpose pool.")

    def test_editor_validation(self):
        ppd = _import_pool_profile_dialogs()
        app = self._app()

        with patch("feature_config.save_config") as mock_save:
            # Empty name
            values = {"name": "", "autotrim": "on"}
            with _FakePoolProfileEditor(
                ppd, values, [ppd.Gtk.ResponseType.OK, ppd.Gtk.ResponseType.CANCEL]
            ):
                ppd.show_pool_profile_editor_dialog(app)
            mock_save.assert_not_called()

            # Duplicate name on add (case-insensitive against a seeded profile)
            values = {"name": "GENERAL", "autotrim": "on"}
            with _FakePoolProfileEditor(
                ppd, values, [ppd.Gtk.ResponseType.OK, ppd.Gtk.ResponseType.CANCEL]
            ):
                ppd.show_pool_profile_editor_dialog(app)
            mock_save.assert_not_called()

            # Nothing set at all (blocksize "recommended" shapes nothing)
            values = {"name": "empty-pool"}
            with _FakePoolProfileEditor(
                ppd, values, [ppd.Gtk.ResponseType.OK, ppd.Gtk.ResponseType.CANCEL]
            ):
                ppd.show_pool_profile_editor_dialog(app)
            mock_save.assert_not_called()

    def test_editor_explicit_blocksize_alone_is_enough(self):
        """A profile that only pins the blocksize is meaningful (ashift is
        creation-only and otherwise unfixable later)."""
        ppd = _import_pool_profile_dialogs()
        app = self._app()

        values = {"name": "small-block", "blocksize": "512 bytes"}

        with (
            _FakePoolProfileEditor(ppd, values, [ppd.Gtk.ResponseType.OK]),
            patch("feature_config.save_config"),
        ):
            ppd.show_pool_profile_editor_dialog(app)

        profiles = app.config["pool_profiles"]
        self.assertEqual(profiles["small-block"]["blocksize"], "512 bytes")
        self.assertEqual(profiles["small-block"]["pool_properties"], {})
        self.assertEqual(profiles["small-block"]["filesystem_properties"], {})


class TestActionDispatchWiring(unittest.TestCase):
    """Disks-page wiring for the pool profile manager."""

    def test_disks_page_wires_manage_pool_profiles(self):
        ad = _import_action_dispatch()
        labels = [btn[0] for btn in ad.PAGE_SPECS["disks"]["buttons"]]
        self.assertIn("Advanced: Manage Pool Profiles…", labels)

        handlers = ad.ACTION_HANDLERS["disks"]
        self.assertIn("Advanced: Manage Pool Profiles…", handlers)
        self.assertEqual(
            handlers["Advanced: Manage Pool Profiles…"].__name__,
            "on_disks_manage_pool_profiles",
        )


if __name__ == "__main__":
    unittest.main()
