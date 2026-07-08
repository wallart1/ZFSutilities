"""Tests for checkagainst_page.py — checkagainst table editing."""

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


class TestEntriesFromToConfig(unittest.TestCase):
    """Config serialization round-trips."""

    def test_entries_from_config_defaults(self):
        app = MagicMock()
        app.config = {"checkagainst": [
            {"dataset": "tank/a", "counterpart": "backup/a"},
        ]}
        entries = cap._entries_from_config(app)
        self.assertEqual(entries, [("tank/a", "0", "backup/a", "", "")])

    def test_entries_from_config_reads_comment(self):
        app = MagicMock()
        app.config = {"checkagainst": [
            {"dataset": "tank/a", "quals": "1", "counterpart": "backup/a",
             "label": "offsite", "comment": "kept for parity"},
        ]}
        entries = cap._entries_from_config(app)
        self.assertEqual(entries, [("tank/a", "1", "backup/a", "offsite", "kept for parity")])

    def test_entries_to_config(self):
        with temp_config_dir():
            app = MagicMock()
            app.config = {}
            entries = [("tank/a", "1", "backup/a", "offsite", "")]
            cap._entries_to_config(app, entries)
            self.assertEqual(app.config["checkagainst"], [
                {"dataset": "tank/a", "quals": "1", "counterpart": "backup/a",
                 "label": "offsite", "comment": ""},
            ])

    def test_entries_to_config_preserves_comment(self):
        with temp_config_dir():
            app = MagicMock()
            app.config = {}
            entries = [("tank/a", "1", "backup/a", "offsite", "nightly pair")]
            cap._entries_to_config(app, entries)
            self.assertEqual(app.config["checkagainst"], [
                {"dataset": "tank/a", "quals": "1", "counterpart": "backup/a",
                 "label": "offsite", "comment": "nightly pair"},
            ])


class TestDirtyTracking(unittest.TestCase):
    """Dirty detection compares current store to original."""

    def setUp(self):
        self._p = patch.object(cap, "_set_button_markup")
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def _make_app(self, original, current):
        app = MagicMock()
        app._ca_store = _FakeStore(current)
        app._ca_original = list(original)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        return app

    def test_clean_when_same(self):
        app = self._make_app(
            [("tank/a", "0", "backup/a", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        self.assertFalse(cap._is_ca_dirty(app))

    def test_dirty_when_different(self):
        app = self._make_app(
            [("tank/a", "0", "backup/a", "offsite", "")],
            [("tank/a", "1", "backup/a", "offsite", "")],
        )
        self.assertTrue(cap._is_ca_dirty(app))

    def test_dirty_when_comment_changes(self):
        app = self._make_app(
            [("tank/a", "0", "backup/a", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "changed")],
        )
        self.assertTrue(cap._is_ca_dirty(app))

    def test_is_checkagainst_dirty_false_without_original(self):
        class NoOriginalApp:
            pass
        app = NoOriginalApp()
        self.assertFalse(cap.is_checkagainst_dirty(app))


class TestStatusUpdate(unittest.TestCase):
    """_update_ca_status validates and shows status messages."""

    def setUp(self):
        self._p = patch.object(cap, "_set_button_markup")
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def _make_app(self, rows, original):
        app = MagicMock()
        app._ca_store = _FakeStore(rows)
        app._ca_original = list(original)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        return app

    def test_empty_required_field_shows_error(self):
        app = self._make_app(
            [("tank/a", "0", "", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("empty required fields", markup)

    def test_negative_quals_shows_error(self):
        app = self._make_app(
            [("tank/a", "-1", "backup/a", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("non-negative integer", markup)

    def test_non_numeric_quals_shows_error(self):
        app = self._make_app(
            [("tank/a", "abc", "backup/a", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("non-negative integer", markup)

    def test_dirty_shows_unsaved(self):
        app = self._make_app(
            [("tank/a", "0", "backup/a", "offsite", "")],
            [("tank/a", "1", "backup/a", "offsite", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("Unsaved changes", markup)

    def test_clean_shows_empty(self):
        app = self._make_app(
            [("tank/a", "0", "backup/a", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        cap._update_ca_status(app)
        app._ca_status_label.set_text.assert_called_once_with("")


class TestActionHandlers(unittest.TestCase):
    """Add/remove/save/revert action handlers."""

    def _make_app(self, rows=None, original=None):
        app = MagicMock()
        app._ca_store = _FakeStore(rows)
        app._ca_original = list(original or (rows or []))
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

    def test_on_ca_add_appends_default_row(self):
        app = self._make_app()
        cap.on_checkagainst_add(app)
        self.assertEqual(len(app._ca_store), 1)
        self.assertEqual(app._ca_store[0], ["", "0", "-", "offsite", ""])

    def test_on_ca_add_appends_at_end(self):
        """Adding a row must append at the end, not sort into the middle."""
        app = self._make_app([
            ("alpha", "0", "backup/alpha", "daily", ""),
            ("bravo", "0", "backup/bravo", "daily", ""),
        ])
        cap.on_checkagainst_add(app)
        self.assertEqual(len(app._ca_store), 3)
        self.assertEqual(app._ca_store[2], ["", "0", "-", "offsite", ""])

    def test_on_ca_remove_deletes_selected_row(self):
        app = self._make_app([("tank/a", "0", "backup/a", "offsite", "")])
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
            app = self._make_app([("tank/a", "0", "backup/a", "offsite", "")])
            cap.on_checkagainst_save(app)
            self.assertEqual(app.config["checkagainst"], [
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a",
                 "label": "offsite", "comment": ""},
            ])
            self.assertEqual(app._ca_original, [("tank/a", "0", "backup/a", "offsite", "")])

    def test_on_ca_save_rejects_invalid_rows(self):
        app = self._make_app([("tank/a", "-1", "backup/a", "offsite", "")])
        with patch.object(cap.Gtk, "MessageDialog", return_value=MagicMock()) as mock_msg:
            cap.on_checkagainst_save(app)
        mock_msg.assert_called_once()
        self.assertNotIn("checkagainst", app.config)

    def test_on_ca_revert_restores_original(self):
        app = self._make_app(
            [("tank/a", "1", "backup/a", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        app.config["checkagainst"] = [
            {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a",
             "label": "offsite", "comment": ""},
        ]
        cap.on_checkagainst_revert(app)
        self.assertEqual(app._ca_store._rows, [["tank/a", "0", "backup/a", "offsite", ""]])


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
        app.config = {"checkagainst": []}
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
        # set_markup may also be used; capture both.
        recording_label.set_markup.side_effect = recording_label._texts.append

        app = MagicMock()
        app.config = {"checkagainst": []}
        with patch.object(cap.Gtk, "Label", return_value=recording_label), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)

        combined = " ".join(str(t) for t in recording_label._texts)
        self.assertIn("<offsite>", html.unescape(combined))


class TestPageConstruction(unittest.TestCase):
    """Checkagainst page builds a 5-column editable, reorderable tree."""

    def _make_app(self):
        app = MagicMock()
        app.config = {"checkagainst": []}
        return app

    def test_liststore_has_five_string_columns(self):
        app = self._make_app()
        with patch.object(cap.Gtk, "ListStore") as mock_liststore, \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)
        mock_liststore.assert_called_once_with(str, str, str, str, str)

    def test_treeview_is_reorderable(self):
        app = self._make_app()
        tv_mock = MagicMock()
        with patch.object(cap.Gtk, "TreeView", return_value=tv_mock), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)
        tv_mock.set_reorderable.assert_called_once_with(True)

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
        self.assertEqual(len(titles), 5)


class TestCellEdit(unittest.TestCase):
    """Editing a cell updates the store and revalidates status."""

    def test_on_cell_edited_updates_store_and_status(self):
        app = MagicMock()
        app._ca_store = _FakeStore([("tank/a", "0", "backup/a", "offsite", "")])
        app._ca_original = [("tank/a", "0", "backup/a", "offsite", "")]
        app._ca_save_button = MagicMock()
        with patch.object(cap, "_update_ca_status") as mock_update, \
             patch.object(cap, "_set_button_markup"):
            cap._on_cell_edited(MagicMock(), "0", "  new-value  ", app, cap.COL_COUNTERPART)
        self.assertEqual(app._ca_store[0][cap.COL_COUNTERPART], "new-value")
        mock_update.assert_called_once_with(app)


class TestSaveButtonStyling(unittest.TestCase):
    """check_checkagainst_dirty styles the Save button."""

    def _make_app(self, current, original):
        app = MagicMock()
        app._ca_store = _FakeStore(current)
        app._ca_original = list(original)
        app._ca_save_button = MagicMock()
        return app

    def test_dirty_styles_save_button_red(self):
        app = self._make_app(
            [("tank/a", "0", "backup/a", "offsite", "")],
            [("tank/a", "0", "other/a", "offsite", "")],
        )
        with patch.object(cap, "_set_button_markup") as mock_markup:
            cap.check_checkagainst_dirty(app)
        mock_markup.assert_called_once_with(
            app._ca_save_button,
            '<span foreground="red">Save</span>',
        )

    def test_clean_styles_save_button_plain(self):
        app = self._make_app(
            [("tank/a", "0", "backup/a", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        with patch.object(cap, "_set_button_markup") as mock_markup:
            cap.check_checkagainst_dirty(app)
        mock_markup.assert_called_once_with(app._ca_save_button, "Save")


class TestSetButtonMarkup(unittest.TestCase):
    """_set_button_markup recurses to find a Gtk.Label."""

    def _patch_label(self):
        class FakeLabel:
            def __init__(self):
                self.markup = None
            def set_markup(self, markup):
                self.markup = markup
        return patch.object(cap, "Gtk"), FakeLabel

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

    def _make_app(self, rows, original):
        app = MagicMock()
        app._ca_store = _FakeStore(rows)
        app._ca_original = list(original)
        app._ca_status_label = MagicMock()
        app._ca_save_button = MagicMock()
        return app

    def test_empty_dataset_shows_error(self):
        app = self._make_app(
            [("", "0", "backup/a", "offsite", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("empty required fields", markup)

    def test_empty_label_shows_error(self):
        app = self._make_app(
            [("tank/a", "0", "backup/a", "", "")],
            [("tank/a", "0", "backup/a", "offsite", "")],
        )
        cap._update_ca_status(app)
        markup = app._ca_status_label.set_markup.call_args[0][0]
        self.assertIn("empty required fields", markup)


class TestTabNavigationWiring(unittest.TestCase):
    """Editable cell renderers are wired for Tab/Shift+Tab navigation."""

    def test_all_editable_renderers_connect_editing_started(self):
        app = MagicMock()
        app.config = {"checkagainst": []}
        renderers = []

        def _make_renderer():
            r = MagicMock()
            r._connections = []

            def _connect(signal, callback, *args):
                r._connections.append((signal, callback, args))

            r.connect.side_effect = _connect
            renderers.append(r)
            return r

        with patch.object(cap.Gtk, "CellRendererText", side_effect=_make_renderer), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)

        self.assertEqual(len(renderers), 5)
        expected_cols = [cap.COL_DATASET, cap.COL_QUALS, cap.COL_COUNTERPART,
                         cap.COL_LABEL, cap.COL_COMMENT]
        for idx, renderer in enumerate(renderers):
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
        app.config = {"checkagainst": []}
        renderers = []

        def _make_renderer():
            r = MagicMock()
            r._connections = []

            def _connect(signal, callback, *args):
                r._connections.append((signal, callback, args))

            r.connect.side_effect = _connect
            renderers.append(r)
            return r

        with patch.object(cap.Gtk, "CellRendererText", side_effect=_make_renderer), \
             patch.object(cap, "_set_button_markup"):
            cap.create_checkagainst_page(app)

        renderer = renderers[0]
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
            cap.COL_DATASET, cap.COL_QUALS, cap.COL_COUNTERPART,
            cap.COL_LABEL, cap.COL_COMMENT,
        ])


class TestActionHandlersEmptyFields(unittest.TestCase):
    """Save rejects empty required fields."""

    def _make_app(self, rows):
        app = MagicMock()
        app._ca_store = _FakeStore(rows)
        app._ca_original = []
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
        app = self._make_app([("", "0", "backup/a", "offsite", "")])
        with patch.object(cap.Gtk, "MessageDialog", return_value=MagicMock()) as mock_msg:
            cap.on_checkagainst_save(app)
        mock_msg.assert_called_once()
        self.assertNotIn("checkagainst", app.config)

    def test_on_ca_save_rejects_empty_label(self):
        app = self._make_app([("tank/a", "0", "backup/a", "", "")])
        with patch.object(cap.Gtk, "MessageDialog", return_value=MagicMock()) as mock_msg:
            cap.on_checkagainst_save(app)
        mock_msg.assert_called_once()
        self.assertNotIn("checkagainst", app.config)


if __name__ == "__main__":
    unittest.main()
