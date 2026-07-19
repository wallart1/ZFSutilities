"""Tests for checkagainst_page.py — checkagainst table editing."""

import copy
import html
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk, temp_config_dir

with mock_gtk():
    import checkagainst_page as cap


class _FakeStore:
    """Minimal ListStore stand-in."""
    def __init__(self, rows=None):
        self._rows = [list(r) for r in (rows or [])]

    def clear(self):
        self._rows = []

    def append(self, values):
        self._rows.append(list(values))

    def __iter__(self):
        return iter(self._rows)

    def __getitem__(self, idx):
        if isinstance(idx, str):
            idx = int(idx)
        return self._rows[idx]

    def __len__(self):
        return len(self._rows)


def _make_checkbox(active=True):
    chk = MagicMock()
    chk.get_active.return_value = active
    return chk


class TestEntriesFromToConfig(unittest.TestCase):
    """Config serialization round-trips."""

    def setUp(self):
        self._p = patch.object(cap, "_set_button_markup")
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_entries_from_config_defaults(self):
        app = MagicMock()
        app.config = {"checkagainst": {"user_entries": [
            {"dataset": "tank/a", "counterpart": "backup/a"},
        ]}}
        entries = cap._entries_from_config(app)
        self.assertEqual(entries, [("", "tank/a", "0", "backup/a", "")])

    def test_entries_from_config_reads_comment(self):
        app = MagicMock()
        app.config = {"checkagainst": {"user_entries": [
            {"dataset": "tank/a", "quals": "1", "counterpart": "backup/a",
             "label": "offsite", "comment": "kept for parity"},
        ]}}
        entries = cap._entries_from_config(app)
        self.assertEqual(entries, [("offsite", "tank/a", "1", "backup/a", "kept for parity")])

    def test_full_dict_from_ui(self):
        app = MagicMock()
        app.config = {}
        app._ca_backup_store = _FakeStore([("dailybackup", "src/a", "0", "dst/a", "")])
        app._ca_offsite_store = _FakeStore([("offsite", "src/b", "1", "-", "")])
        app._ca_store = _FakeStore([("offsite", "tank/a", "0", "backup/a", "note")])
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(False)

        data = cap._full_dict_from_ui(app)
        self.assertTrue(data["backup_derived_active"])
        self.assertFalse(data["offsite_derived_active"])
        self.assertEqual(data["backup_derived"], [
            {"label": "dailybackup", "dataset": "src/a", "quals": "0",
             "counterpart": "dst/a", "comment": ""},
        ])
        self.assertEqual(data["user_entries"], [
            {"label": "offsite", "dataset": "tank/a", "quals": "0",
             "counterpart": "backup/a", "comment": "note"},
        ])

    def test_save_full_checkagainst(self):
        with temp_config_dir():
            app = MagicMock()
            app.config = {}
            app._ca_backup_store = _FakeStore()
            app._ca_offsite_store = _FakeStore()
            app._ca_store = _FakeStore([("offsite", "tank/a", "0", "backup/a", "")])
            app._ca_backup_active_chk = _make_checkbox(True)
            app._ca_offsite_active_chk = _make_checkbox(True)

            cap.on_checkagainst_save(app)
            self.assertEqual(app.config["checkagainst"]["user_entries"], [
                {"label": "offsite", "dataset": "tank/a", "quals": "0",
                 "counterpart": "backup/a", "comment": ""},
            ])


class TestDirtyTracking(unittest.TestCase):
    """Dirty detection compares the full checkagainst dict."""

    def setUp(self):
        self._p = patch.object(cap, "_set_button_markup")
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def _make_app(self, user_rows, original_user_rows, backup_derived=None,
                  offsite_derived=None, backup_active=True, offsite_active=True):
        app = MagicMock()
        app._ca_store = _FakeStore(user_rows)
        app._ca_backup_store = _FakeStore(backup_derived or [])
        app._ca_offsite_store = _FakeStore(offsite_derived or [])
        app._ca_backup_active_chk = _make_checkbox(backup_active)
        app._ca_offsite_active_chk = _make_checkbox(offsite_active)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        # Snapshot the original full dict from the original widgets.
        saved = {
            "backup_derived_active": backup_active,
            "offsite_derived_active": offsite_active,
            "backup_derived": [
                {"label": r[0], "dataset": r[1], "quals": r[2],
                 "counterpart": r[3], "comment": r[4]}
                for r in (backup_derived or [])
            ],
            "offsite_derived": [
                {"label": r[0], "dataset": r[1], "quals": r[2],
                 "counterpart": r[3], "comment": r[4]}
                for r in (offsite_derived or [])
            ],
            "user_entries": [
                {"label": r[0], "dataset": r[1], "quals": r[2],
                 "counterpart": r[3], "comment": r[4]}
                for r in original_user_rows
            ],
        }
        app._ca_original_full = saved
        return app

    def test_clean_when_same(self):
        app = self._make_app(
            [("offsite", "tank/a", "0", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        self.assertFalse(cap._is_ca_dirty(app))

    def test_dirty_when_user_row_changes(self):
        app = self._make_app(
            [("offsite", "tank/a", "1", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        self.assertTrue(cap._is_ca_dirty(app))

    def test_dirty_when_comment_changes(self):
        app = self._make_app(
            [("offsite", "tank/a", "0", "backup/a", "changed")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        self.assertTrue(cap._is_ca_dirty(app))

    def test_dirty_when_active_flag_changes(self):
        app = self._make_app(
            [("offsite", "tank/a", "0", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
            backup_active=True,
        )
        # Toggle the current checkbox state away from the saved original.
        app._ca_backup_active_chk.get_active.return_value = False
        self.assertTrue(cap._is_ca_dirty(app))

    def test_is_checkagainst_dirty_false_without_original(self):
        class NoOriginalApp:
            pass
        app = NoOriginalApp()
        self.assertFalse(cap.is_checkagainst_dirty(app))


class TestLoadNormalization(unittest.TestCase):
    """Loading must not mark the page dirty when defaults are applied."""

    def test_load_does_not_create_false_dirty_state(self):
        """Rows missing optional fields should not trigger dirty detection."""
        app = MagicMock()
        app.config = {"checkagainst": {
            "user_entries": [{"dataset": "tank/a", "label": "offsite"}],
        }}
        app._ca_backup_store = _FakeStore()
        app._ca_offsite_store = _FakeStore()
        app._ca_store = _FakeStore()
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(True)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()

        with patch.object(cap, "_set_button_markup"):
            cap._load_fss_into_store(app)

        self.assertFalse(cap._is_ca_dirty(app))


class TestStatusUpdate(unittest.TestCase):
    """_update_ca_status validates and shows status messages."""

    def setUp(self):
        self._p = patch.object(cap, "_set_button_markup")
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def _make_app(self, rows, original_rows):
        app = MagicMock()
        app._ca_store = _FakeStore(rows)
        app._ca_backup_store = _FakeStore()
        app._ca_offsite_store = _FakeStore()
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(True)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        app._ca_original_full = {
            "backup_derived_active": True,
            "offsite_derived_active": True,
            "backup_derived": [],
            "offsite_derived": [],
            "user_entries": [
                {"label": r[0], "dataset": r[1], "quals": r[2],
                 "counterpart": r[3], "comment": r[4]}
                for r in original_rows
            ],
        }
        return app

    def test_empty_required_field_shows_error(self):
        app = self._make_app(
            [("offsite", "tank/a", "0", "", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("empty required fields", markup)

    def test_negative_quals_shows_error(self):
        app = self._make_app(
            [("offsite", "tank/a", "-1", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("non-negative integer", markup)

    def test_non_numeric_quals_shows_error(self):
        app = self._make_app(
            [("offsite", "tank/a", "abc", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("non-negative integer", markup)

    def test_dirty_shows_unsaved(self):
        app = self._make_app(
            [("offsite", "tank/a", "0", "backup/a", "")],
            [("offsite", "tank/a", "1", "backup/a", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("Unsaved changes", markup)

    def test_clean_shows_empty(self):
        app = self._make_app(
            [("offsite", "tank/a", "0", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        cap._update_ca_status(app)
        app._ca_status_label.set_text.assert_called_once_with("")


class TestActionHandlers(unittest.TestCase):
    """Add/remove/save/revert/get-entries action handlers."""

    def _make_app(self, user_rows=None, original_user_rows=None):
        app = MagicMock()
        app._ca_store = _FakeStore(user_rows)
        app._ca_backup_store = _FakeStore()
        app._ca_offsite_store = _FakeStore()
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(True)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        app._ca_view = MagicMock()
        app.config = {}
        app._ca_original_full = {
            "backup_derived_active": True,
            "offsite_derived_active": True,
            "backup_derived": [],
            "offsite_derived": [],
            "user_entries": [
                {"label": r[0], "dataset": r[1], "quals": r[2],
                 "counterpart": r[3], "comment": r[4]}
                for r in (original_user_rows or (user_rows or []))
            ],
        }
        return app

    def setUp(self):
        self._set_button_markup_patch = patch.object(cap, "_set_button_markup")
        self._set_button_markup_patch.start()

    def tearDown(self):
        self._set_button_markup_patch.stop()

    def test_on_ca_add_appends_default_row(self):
        app = self._make_app()
        cap.on_checkagainst_add(app)
        self.assertEqual(len(app._ca_store), 1)
        self.assertEqual(app._ca_store[0], ["offsite", "", "0", "-", ""])

    def test_on_ca_add_appends_at_end(self):
        """Adding a row must append at the end, not sort into the middle."""
        app = self._make_app([
            ("daily", "alpha", "0", "backup/alpha", ""),
            ("daily", "bravo", "0", "backup/bravo", ""),
        ])
        cap.on_checkagainst_add(app)
        self.assertEqual(len(app._ca_store), 3)
        self.assertEqual(app._ca_store[2], ["offsite", "", "0", "-", ""])

    def test_on_ca_remove_deletes_selected_row(self):
        app = self._make_app([("offsite", "tank/a", "0", "backup/a", "")])
        selection = MagicMock()
        model = MagicMock()
        tree_iter = MagicMock()
        selection.get_selected.return_value = (model, tree_iter)
        app._ca_view.get_selection.return_value = selection
        model.remove.return_value = None

        cap.on_checkagainst_remove(app)
        model.remove.assert_called_once_with(tree_iter)

    def test_on_ca_save_validates_and_persists(self):
        with temp_config_dir():
            app = self._make_app([("offsite", "tank/a", "0", "backup/a", "")])
            cap.on_checkagainst_save(app)
            self.assertEqual(app.config["checkagainst"]["user_entries"], [
                {"label": "offsite", "dataset": "tank/a", "quals": "0",
                 "counterpart": "backup/a", "comment": ""},
            ])
            self.assertEqual(
                app._ca_original_full,
                app.config["checkagainst"],
            )

    def test_on_ca_save_rejects_invalid_rows(self):
        app = self._make_app([("offsite", "tank/a", "-1", "backup/a", "")])
        with patch.object(cap.Gtk, "MessageDialog", return_value=MagicMock()) as mock_msg:
            cap.on_checkagainst_save(app)
        mock_msg.assert_called_once()
        self.assertNotIn("checkagainst", app.config)

    def test_on_ca_revert_restores_original(self):
        app = self._make_app(
            [("offsite", "tank/a", "1", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        cap.on_checkagainst_revert(app)
        self.assertEqual(
            app._ca_store._rows,
            [["offsite", "tank/a", "0", "backup/a", ""]],
        )

    def test_on_ca_get_entries_derives_and_loads(self):
        app = MagicMock()
        app.config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": True, "source": "poolA/a", "dest": "poolB/a"},
                ],
            },
            "offsite": {"steps": []},
            "checkagainst": {
                "backup_derived_active": True,
                "offsite_derived_active": True,
                "backup_derived": [],
                "offsite_derived": [],
                "user_entries": [],
            },
        }
        app._ca_backup_store = _FakeStore()
        app._ca_offsite_store = _FakeStore()
        app._ca_store = _FakeStore()
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(True)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        app._ca_original_full = copy.deepcopy(app.config["checkagainst"])

        with patch.object(cap, "log_msg") as mock_log:
            cap.on_checkagainst_get_entries(app)

        self.assertEqual(len(app._ca_backup_store), 2)
        self.assertEqual(app._ca_backup_store[0],
                         ["dailybackup", "poolA/a", "0", "poolB/a", ""])
        self.assertEqual(app._ca_backup_store[1],
                         ["dailybackup", "poolB/a/poolA/a", "2", "-", ""])
        self.assertEqual(len(app._ca_offsite_store), 0)
        mock_log.assert_called_once()


class TestPageNotes(unittest.TestCase):
    """Inline help text documents the <offsite> placeholder."""

    def test_notes_mention_offsite_placeholder(self):
        """The notes label markup mentions <offsite>."""
        recording_label = MagicMock()
        recording_label._markups = []

        def _record_markup(markup):
            recording_label._markups.append(markup)

        recording_label.set_markup.side_effect = _record_markup

        app = MagicMock()
        app.config = {"checkagainst": {"user_entries": []}}
        with patch.object(cap.Gtk, "Label", return_value=recording_label), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)

        self.assertTrue(
            any("<offsite>" in html.unescape(m) for m in recording_label._markups),
            "Expected page notes to mention <offsite> placeholder",
        )

    def test_description_mentions_offsite_placeholder(self):
        """The page description mentions <offsite>."""
        recording_label = MagicMock()
        recording_label._texts = []

        def _record_text(text):
            recording_label._texts.append(text)

        recording_label.set_text.side_effect = _record_text
        recording_label.set_markup.side_effect = recording_label._texts.append

        app = MagicMock()
        app.config = {"checkagainst": {"user_entries": []}}
        with patch.object(cap.Gtk, "Label", return_value=recording_label), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)

        combined = " ".join(str(t) for t in recording_label._texts)
        self.assertIn("<offsite>", html.unescape(combined))


class TestPageConstruction(unittest.TestCase):
    """Checkagainst page builds three 5-column treeviews."""

    def _make_app(self):
        app = MagicMock()
        app.config = {"checkagainst": {"user_entries": []}}
        return app

    def test_liststore_has_five_string_columns(self):
        app = self._make_app()
        with patch.object(cap.Gtk, "ListStore") as mock_liststore, \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)
        # Three stores are created (backup, offsite, user).
        self.assertEqual(mock_liststore.call_count, 3)
        mock_liststore.assert_called_with(str, str, str, str, str)

    def test_user_treeview_is_reorderable(self):
        app = self._make_app()
        tv_mock = MagicMock()
        with patch.object(cap.Gtk, "TreeView", return_value=tv_mock), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)
        tv_mock.set_reorderable.assert_called_with(True)

    def test_columns_are_not_sortable(self):
        app = self._make_app()
        with patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)
        self.assertEqual(
            cap.Gtk.TreeViewColumn.return_value.set_sort_column_id.call_count,
            0,
        )

    def test_comment_column_appended(self):
        app = self._make_app()
        titles = []

        def _record_column(title, *args, **kwargs):
            titles.append(title)
            return MagicMock()

        with patch.object(cap.Gtk, "TreeViewColumn", side_effect=_record_column), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)
        self.assertIn("Comment", titles)
        self.assertEqual(len(titles), 15)  # 5 columns x 3 treeviews


class TestColumnTooltips(unittest.TestCase):
    """Each column header has an explanatory tooltip."""

    def test_all_columns_have_tooltips(self):
        for col_idx in (cap.COL_LABEL, cap.COL_DATASET, cap.COL_QUALS,
                        cap.COL_COUNTERPART, cap.COL_COMMENT):
            tooltip = cap._COLUMN_TOOLTIPS.get(col_idx, "")
            self.assertTrue(
                isinstance(tooltip, str) and len(tooltip) > 0,
                f"Column {col_idx} is missing a tooltip",
            )

    def test_tooltips_mention_display_names(self):
        self.assertIn("Snapshot label", cap._COLUMN_TOOLTIPS[cap.COL_LABEL])
        self.assertIn("Source dataset", cap._COLUMN_TOOLTIPS[cap.COL_DATASET])
        self.assertIn("leading path segments", cap._COLUMN_TOOLTIPS[cap.COL_QUALS])
        self.assertIn("Destination dataset", cap._COLUMN_TOOLTIPS[cap.COL_COUNTERPART])


class TestCellEdit(unittest.TestCase):
    """Editing a cell updates the store and revalidates status."""

    def test_on_cell_edited_updates_store_and_status(self):
        app = MagicMock()
        app._ca_store = _FakeStore([("offsite", "tank/a", "0", "backup/a", "")])
        app._ca_backup_store = _FakeStore()
        app._ca_offsite_store = _FakeStore()
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(True)
        app._ca_original_full = {
            "backup_derived_active": True,
            "offsite_derived_active": True,
            "backup_derived": [],
            "offsite_derived": [],
            "user_entries": [
                {"label": "offsite", "dataset": "tank/a", "quals": "0",
                 "counterpart": "backup/a", "comment": ""},
            ],
        }
        app._ca_save_button = MagicMock()
        with patch.object(cap, "_update_ca_status") as mock_update:
            cap._on_cell_edited(MagicMock(), "0", "  new-value  ", app, cap.COL_COUNTERPART)
        self.assertEqual(app._ca_store[0][cap.COL_COUNTERPART], "new-value")
        mock_update.assert_called_once_with(app)


class TestSaveButtonStyling(unittest.TestCase):
    """check_checkagainst_dirty styles the Save button."""

    def _make_app(self, current, original):
        app = MagicMock()
        app._ca_store = _FakeStore(current)
        app._ca_backup_store = _FakeStore()
        app._ca_offsite_store = _FakeStore()
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(True)
        app._ca_original_full = {
            "backup_derived_active": True,
            "offsite_derived_active": True,
            "backup_derived": [],
            "offsite_derived": [],
            "user_entries": [
                {"label": r[0], "dataset": r[1], "quals": r[2],
                 "counterpart": r[3], "comment": r[4]}
                for r in original
            ],
        }
        app._ca_save_button = MagicMock()
        return app

    def test_dirty_styles_save_button_red(self):
        app = self._make_app(
            [("offsite", "tank/a", "0", "backup/a", "")],
            [("offsite", "tank/a", "0", "other/a", "")],
        )
        with patch.object(cap, "_set_button_markup") as mock_markup:
            cap.check_checkagainst_dirty(app)
        mock_markup.assert_called_once_with(
            app._ca_save_button,
            '<span foreground="red">Save</span>',
        )

    def test_clean_styles_save_button_plain(self):
        app = self._make_app(
            [("offsite", "tank/a", "0", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        with patch.object(cap, "_set_button_markup") as mock_markup:
            cap.check_checkagainst_dirty(app)
        mock_markup.assert_called_once_with(app._ca_save_button, "Save")


class TestSetButtonMarkup(unittest.TestCase):
    """_set_button_markup recurses to find a Gtk.Label."""

    def test_finds_label_in_box(self):
        with patch.object(cap, "Gtk") as mock_gtk:
            class FakeLabel:
                def __init__(self):
                    self.markup = None
                def set_markup(self, markup):
                    self.markup = markup
            mock_gtk.Label = FakeLabel

            class FakeBox:
                def __init__(self):
                    self.label = FakeLabel()
                def get_children(self):
                    return [self.label]
            box = FakeBox()
            self.assertTrue(cap._set_button_markup(box, "<b>Save</b>"))
            self.assertEqual(box.label.markup, "<b>Save</b>")

    def test_finds_label_via_get_child(self):
        with patch.object(cap, "Gtk") as mock_gtk:
            class FakeLabel:
                def __init__(self):
                    self.markup = None
                def set_markup(self, markup):
                    self.markup = markup
            mock_gtk.Label = FakeLabel

            class FakeContainer:
                def __init__(self):
                    self.label = FakeLabel()
                def get_child(self):
                    return self.label
            container = FakeContainer()
            self.assertTrue(cap._set_button_markup(container, "Save"))
            self.assertEqual(container.label.markup, "Save")

    def test_returns_false_when_no_label_found(self):
        with patch.object(cap, "Gtk") as mock_gtk:
            class NotALabel:
                pass
            mock_gtk.Label = NotALabel
            widget = MagicMock()
            widget.get_children.return_value = []
            widget.get_child.return_value = None
            self.assertFalse(cap._set_button_markup(widget, "Save"))


class TestStatusUpdateEmptyFields(unittest.TestCase):
    """Status validation catches empty required fields."""

    def setUp(self):
        self._p = patch.object(cap, "_set_button_markup")
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def _make_app(self, rows, original_rows):
        app = MagicMock()
        app._ca_store = _FakeStore(rows)
        app._ca_backup_store = _FakeStore()
        app._ca_offsite_store = _FakeStore()
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(True)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        app._ca_original_full = {
            "backup_derived_active": True,
            "offsite_derived_active": True,
            "backup_derived": [],
            "offsite_derived": [],
            "user_entries": [
                {"label": r[0], "dataset": r[1], "quals": r[2],
                 "counterpart": r[3], "comment": r[4]}
                for r in original_rows
            ],
        }
        return app

    def test_empty_dataset_shows_error(self):
        app = self._make_app(
            [("offsite", "", "0", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("empty required fields", markup)

    def test_empty_label_shows_error(self):
        app = self._make_app(
            [("", "tank/a", "0", "backup/a", "")],
            [("offsite", "tank/a", "0", "backup/a", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("empty required fields", markup)


class TestTabNavigationWiring(unittest.TestCase):
    """Editable cell renderers are wired for Tab/Shift+Tab navigation."""

    def test_all_editable_renderers_connect_editing_started(self):
        app = MagicMock()
        app.config = {"checkagainst": {"user_entries": []}}
        renderers = []

        def _make_renderer():
            r = MagicMock()
            r._connections = []
            r._editable_calls = []

            def _connect(signal, callback, *args):
                r._connections.append((signal, callback, args))

            def _set_property(name, value):
                if name == "editable":
                    r._editable_calls.append(value)

            r.connect.side_effect = _connect
            r.set_property.side_effect = _set_property
            renderers.append(r)
            return r

        with patch.object(cap.Gtk, "CellRendererText", side_effect=_make_renderer), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)

        editable_renderers = [r for r in renderers if True in r._editable_calls]
        self.assertEqual(len(editable_renderers), 5)
        expected_cols = [cap.COL_LABEL, cap.COL_DATASET, cap.COL_QUALS,
                         cap.COL_COUNTERPART, cap.COL_COMMENT]
        for idx, renderer in enumerate(editable_renderers):
            editing_connections = [
                c for c in renderer._connections if c[0] == "editing-started"
            ]
            self.assertEqual(len(editing_connections), 1,
                             f"Renderer {idx} should have one editing-started connection")
            _signal, handler, args = editing_connections[0]
            self.assertIs(handler, cap._on_editing_started)
            self.assertEqual(args[1], expected_cols[idx])

    def test_editing_started_handler_wires_key_press(self):
        app = MagicMock()
        app.config = {"checkagainst": {"user_entries": []}}
        renderers = []

        def _make_renderer():
            r = MagicMock()
            r._connections = []
            r._editable_calls = []

            def _connect(signal, callback, *args):
                r._connections.append((signal, callback, args))

            def _set_property(name, value):
                if name == "editable":
                    r._editable_calls.append(value)

            r.connect.side_effect = _connect
            r.set_property.side_effect = _set_property
            renderers.append(r)
            return r

        with patch.object(cap.Gtk, "CellRendererText", side_effect=_make_renderer), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)

        editable_renderers = [r for r in renderers if True in r._editable_calls]
        renderer = editable_renderers[0]
        editing_connections = [
            c for c in renderer._connections if c[0] == "editing-started"
        ]
        self.assertEqual(len(editing_connections), 1)
        _signal, handler, args = editing_connections[0]
        editable = MagicMock()
        treeview = args[0]
        col_idx = args[1]

        with patch.object(cap, "handle_editing_key_press") as mock_handler:
            handler(renderer, editable, "0", treeview, col_idx)

        editable.connect.assert_called_once()
        conn_args = editable.connect.call_args[0]
        self.assertEqual(conn_args[0], "key-press-event")
        self.assertIs(conn_args[1], mock_handler)
        self.assertEqual(conn_args[2], treeview)
        self.assertEqual(conn_args[3], "0")
        self.assertEqual(conn_args[4], col_idx)
        self.assertEqual(conn_args[5], [
            cap.COL_LABEL, cap.COL_DATASET, cap.COL_QUALS,
            cap.COL_COUNTERPART, cap.COL_COMMENT,
        ])


class TestActionHandlersEmptyFields(unittest.TestCase):
    """Save rejects empty required fields."""

    def _make_app(self, rows):
        app = MagicMock()
        app._ca_store = _FakeStore(rows)
        app._ca_backup_store = _FakeStore()
        app._ca_offsite_store = _FakeStore()
        app._ca_backup_active_chk = _make_checkbox(True)
        app._ca_offsite_active_chk = _make_checkbox(True)
        app._ca_original_full = {
            "backup_derived_active": True,
            "offsite_derived_active": True,
            "backup_derived": [],
            "offsite_derived": [],
            "user_entries": [],
        }
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        app._ca_view = MagicMock()
        app.config = {}
        return app

    def setUp(self):
        self._set_button_markup_patch = patch.object(cap, "_set_button_markup")
        self._set_button_markup_patch.start()

    def tearDown(self):
        self._set_button_markup_patch.stop()

    def test_on_ca_save_rejects_empty_dataset(self):
        app = self._make_app([("offsite", "", "0", "backup/a", "")])
        with patch.object(cap.Gtk, "MessageDialog", return_value=MagicMock()) as mock_msg:
            cap.on_checkagainst_save(app)
        mock_msg.assert_called_once()
        self.assertNotIn("checkagainst", app.config)

    def test_on_ca_save_rejects_empty_label(self):
        app = self._make_app([("", "tank/a", "0", "backup/a", "")])
        with patch.object(cap.Gtk, "MessageDialog", return_value=MagicMock()) as mock_msg:
            cap.on_checkagainst_save(app)
        mock_msg.assert_called_once()
        self.assertNotIn("checkagainst", app.config)


class TestBuildPairRows(unittest.TestCase):
    """Direct tests for the row-building helper."""

    def test_build_pair_rows_nested_source(self):
        forward, reverse = cap._build_pair_rows(
            "threeamigos/proxmox",
            "fivebays/threeamigos/proxmox",
            "dailybackup",
            "manual",
        )
        self.assertEqual(forward, {
            "label": "dailybackup",
            "dataset": "threeamigos/proxmox",
            "quals": "0",
            "counterpart": "fivebays",
            "comment": "manual",
        })
        self.assertEqual(reverse, {
            "label": "dailybackup",
            "dataset": "fivebays/threeamigos/proxmox",
            "quals": "1",
            "counterpart": "-",
            "comment": "manual",
        })

    def test_build_pair_rows_common_suffix(self):
        forward, reverse = cap._build_pair_rows(
            "fivebays/threeamigos/proxmox",
            "threeamigos/proxmox",
            "offsite",
            "",
        )
        self.assertEqual(forward, {
            "label": "offsite",
            "dataset": "fivebays/threeamigos/proxmox",
            "quals": "1",
            "counterpart": "-",
            "comment": "",
        })
        self.assertEqual(reverse, {
            "label": "offsite",
            "dataset": "threeamigos/proxmox/fivebays/threeamigos/proxmox",
            "quals": "2",
            "counterpart": "-",
            "comment": "",
        })


class TestAddPairAssistant(unittest.TestCase):
    """Tests for the Add pair... assistant dialog."""

    def _make_fake_entry(self, text):
        entry = MagicMock()
        entry.get_text.return_value = text
        entry.connect.return_value = None
        entry.set_completion.return_value = None
        return entry

    def _run_assistant(self, app, responses, entries_text, pool_names=None):
        """Patch GTK widgets and run the assistant.

        entries_text is a 4-tuple: (label, source, dest, comment).
        responses is a list of values returned by dlg.run().
        """
        label_entry, source_entry, dest_entry, comment_entry = [
            self._make_fake_entry(t) for t in entries_text
        ]
        entry_iter = iter([
            label_entry, source_entry, dest_entry, comment_entry,
        ])

        fake_dlg = MagicMock()
        fake_dlg.run.side_effect = responses
        fake_content = MagicMock()
        fake_dlg.get_content_area.return_value = fake_content

        with patch.object(cap.Gtk, "Dialog", return_value=fake_dlg), \
             patch.object(cap.Gtk, "Entry", side_effect=lambda: next(entry_iter)), \
             patch.object(cap, "_update_ca_status") as mock_update, \
             patch.object(cap, "log_msg") as mock_log:
            cap.on_checkagainst_add_pair(app)

        return fake_dlg, fake_content, mock_update, mock_log

    def _make_app(self, pool_names=None):
        app = MagicMock()
        app.config = {"pools": [{"name": n} for n in (pool_names or [])]}
        app._ca_store = _FakeStore()
        return app

    def test_add_pair_appends_both_rows(self):
        app = self._make_app(pool_names=["threeamigos", "fivebays"])
        fake_dlg, _content, mock_update, mock_log = self._run_assistant(
            app,
            responses=[cap.Gtk.ResponseType.OK],
            entries_text=("dailybackup", "threeamigos/proxmox",
                          "fivebays/threeamigos/proxmox", "manual"),
        )
        fake_dlg.show_all.assert_called_once()
        self.assertEqual(len(app._ca_store), 2)
        self.assertEqual(app._ca_store[0],
                         ["dailybackup", "threeamigos/proxmox", "0",
                          "fivebays", "manual"])
        self.assertEqual(app._ca_store[1],
                         ["dailybackup", "fivebays/threeamigos/proxmox",
                          "1", "-", "manual"])
        mock_update.assert_called_once_with(app)
        mock_log.assert_called_once()
        fake_dlg.destroy.assert_called_once()

    def test_add_pair_strips_common_suffix(self):
        app = self._make_app()
        self._run_assistant(
            app,
            responses=[cap.Gtk.ResponseType.OK],
            entries_text=("offsite", "fivebays/threeamigos/proxmox",
                          "threeamigos/proxmox", ""),
        )
        self.assertEqual(len(app._ca_store), 2)
        self.assertEqual(app._ca_store[0],
                         ["offsite", "fivebays/threeamigos/proxmox", "1",
                          "-", ""])
        self.assertEqual(app._ca_store[1],
                         ["offsite",
                          "threeamigos/proxmox/fivebays/threeamigos/proxmox",
                          "2", "-", ""])

    def test_add_pair_rejects_empty_source(self):
        app = self._make_app()
        with patch.object(cap.Gtk, "MessageDialog", return_value=MagicMock()) as mock_err:
            fake_dlg, _content, mock_update, _mock_log = self._run_assistant(
                app,
                responses=[
                    cap.Gtk.ResponseType.OK,
                    cap.Gtk.ResponseType.CANCEL,
                ],
                entries_text=("offsite", "", "threeamigos/proxmox", ""),
            )
        mock_err.assert_called_once()
        self.assertEqual(len(app._ca_store), 0)
        mock_update.assert_not_called()
        fake_dlg.destroy.assert_called_once()

    def test_add_pair_cancel_does_nothing(self):
        app = self._make_app()
        fake_dlg, _content, mock_update, mock_log = self._run_assistant(
            app,
            responses=[cap.Gtk.ResponseType.CANCEL],
            entries_text=("offsite", "threeamigos/proxmox",
                          "fivebays/threeamigos/proxmox", ""),
        )
        self.assertEqual(len(app._ca_store), 0)
        mock_update.assert_not_called()
        mock_log.assert_not_called()
        fake_dlg.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
