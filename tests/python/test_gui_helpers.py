"""Tests for gui_helpers.py."""

import re
import unittest
from unittest.mock import MagicMock, patch

from test_support import mock_gtk


class TestGetMountedSnapshots(unittest.TestCase):
    """get_mounted_snapshots parses mount(8) output for snapshot mount state."""

    def _run_with_mount_output(self, stdout, returncode=0):
        import gui_helpers

        with patch.object(
            gui_helpers.subprocess,
            "run",
            return_value=MagicMock(returncode=returncode, stdout=stdout),
        ):
            return gui_helpers.get_mounted_snapshots()

    def test_returns_empty_set_when_mount_fails(self):
        self.assertEqual(self._run_with_mount_output("", returncode=1), set())

    def test_parses_snapshot_syntax(self):
        stdout = "tank/a@snap1 on /tank/a/.zfs/snapshot/snap1 type zfs (ro)\n"
        self.assertEqual(self._run_with_mount_output(stdout), {"tank/a@snap1"})

    def test_parses_automount_path_syntax(self):
        stdout = "tank/a/.zfs/snapshot/snap1 on /tank/a/.zfs/snapshot/snap1 type zfs (ro)\n"
        self.assertEqual(self._run_with_mount_output(stdout), {"tank/a@snap1"})

    def test_ignores_non_snapshot_entries(self):
        stdout = (
            "tank/a on /tank/a type zfs (rw)\n"
            "tank/a@snap1 on /tank/a/.zfs/snapshot/snap1 type zfs (ro)\n"
        )
        self.assertEqual(self._run_with_mount_output(stdout), {"tank/a@snap1"})

    def test_returns_empty_set_when_command_missing(self):
        import gui_helpers

        with patch.object(gui_helpers.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(gui_helpers.get_mounted_snapshots(), set())


class TestAddVarRow(unittest.TestCase):
    """add_var_row builds label + input rows with optional scroll blocking."""

    def test_block_scroll_true_connects_scroll_event_handler(self):
        """A ComboBox created with block_scroll=True suppresses widget scroll."""
        with mock_gtk() as gtk_mock:
            import gui_helpers

            with patch.object(gui_helpers, "Gtk", gtk_mock):
                grid = MagicMock()
                widgets = {}
                gui_helpers.add_var_row(
                    grid,
                    row=0,
                    key="doincrementals",
                    variables={"doincrementals": "Y"},
                    widgets_dict=widgets,
                    yn_vars={"doincrementals"},
                    block_scroll=True,
                )

        widget = widgets["doincrementals"]
        handler = None
        for call in widget.connect.call_args_list:
            if call.args[0] == "scroll-event":
                handler = call.args[1]
                break
        self.assertIsNotNone(handler)

        event = MagicMock()
        result = handler(widget, event)
        widget.stop_emission_by_name.assert_called_once_with("scroll-event")
        self.assertFalse(result)

    def test_block_scroll_false_does_not_connect_scroll_event(self):
        """A ComboBox created with block_scroll=False has no scroll guard."""
        with mock_gtk() as gtk_mock:
            import gui_helpers

            with patch.object(gui_helpers, "Gtk", gtk_mock):
                grid = MagicMock()
                widgets = {}
                gui_helpers.add_var_row(
                    grid,
                    row=0,
                    key="doincrementals",
                    variables={"doincrementals": "Y"},
                    widgets_dict=widgets,
                    yn_vars={"doincrementals"},
                    block_scroll=False,
                )

        widget = widgets["doincrementals"]
        for call in widget.connect.call_args_list:
            self.assertNotEqual(call.args[0], "scroll-event")


class _FakeIter:
    """Minimal stand-in for Gtk.TextIter; records its character offset."""

    def __init__(self, offset):
        self.offset = offset


class _FakeTextBuffer:
    """String-backed stand-in for Gtk.TextBuffer recording tag operations."""

    def __init__(self, text=""):
        self.text = text
        self.applied = []  # (tag, start_offset, end_offset)
        self.removed = []  # (tag, start_offset, end_offset)
        self._next_tag = 0

    def set_text(self, text):
        self.text = text

    def append(self, text):
        self.text += text

    def create_tag(self, _name, **_props):
        self._next_tag += 1
        return self._next_tag

    def get_start_iter(self):
        return _FakeIter(0)

    def get_end_iter(self):
        return _FakeIter(len(self.text))

    def get_char_count(self):
        return len(self.text)

    def get_text(self, start, end, _include_hidden_chars):
        return self.text[start.offset : end.offset]

    def get_iter_at_offset(self, offset):
        return _FakeIter(offset)

    def apply_tag(self, tag, start, end):
        self.applied.append((tag, start.offset, end.offset))

    def remove_tag(self, tag, start, end):
        self.removed.append((tag, start.offset, end.offset))

    def create_mark(self, _name, iter_, _left_gravity):
        return _FakeIter(iter_.offset)

    def delete_mark(self, _mark):
        pass


class TestTextViewSearch(unittest.TestCase):
    """TextViewSearch finds, highlights, and navigates matches by offset.

    Matches must be stored as character offsets, not Gtk.TextIter copies:
    GTK invalidates every outstanding TextIter on any buffer mutation, which
    silently disabled Previous/Next once a running log appended new text.
    """

    TEXT = (
        "alpha needle one\n"
        + "filler line\n" * 20
        + "beta NEEDLE two\n"
        + "filler line\n" * 20
        + "gamma needle three\n"
    )

    def _make_search(self, text=None):
        buffer = _FakeTextBuffer(self.TEXT if text is None else text)
        view = MagicMock()
        view.get_buffer.return_value = buffer
        with mock_gtk() as gtk_mock:
            import gui_helpers

            with patch.object(gui_helpers, "Gtk", gtk_mock):
                search = gui_helpers.TextViewSearch(view)
        search.entry.get_text.return_value = "needle"
        return search, buffer, view

    def _expected_offsets(self, text):
        return [(m.start(), m.end()) for m in re.finditer("needle", text, re.IGNORECASE)]

    def test_matches_stored_as_int_offsets(self):
        search, _buffer, _view = self._make_search()
        search.search()
        self.assertEqual(search.matches, self._expected_offsets(self.TEXT))
        for match in search.matches:
            self.assertTrue(all(isinstance(o, int) for o in match))

    def test_highlights_every_match_and_marks_first_current(self):
        search, buffer, _view = self._make_search()
        search.search()
        highlighted = [tuple(span) for tag, *span in buffer.applied if tag == search.tag_highlight]
        self.assertEqual(highlighted, self._expected_offsets(self.TEXT))
        current = [tuple(span) for tag, *span in buffer.applied if tag == search.tag_current]
        self.assertEqual(current, [self._expected_offsets(self.TEXT)[0]])

    def test_navigate_next_and_previous_updates_counter(self):
        search, _buffer, view = self._make_search()
        search.search()
        search.navigate(1)
        self.assertEqual(search.current, 1)
        search.counter.set_text.assert_called_with("2 / 3")
        self.assertTrue(view.scroll_to_mark.called)
        search.navigate(-1)
        self.assertEqual(search.current, 0)
        search.counter.set_text.assert_called_with("1 / 3")

    def test_navigate_wraps_at_both_ends(self):
        search, _buffer, _view = self._make_search()
        search.search()
        search.navigate(-1)
        self.assertEqual(search.current, 2)
        search.counter.set_text.assert_called_with("3 / 3")
        search.navigate(1)
        self.assertEqual(search.current, 0)
        search.counter.set_text.assert_called_with("1 / 3")

    def test_navigate_survives_buffer_append(self):
        """Appending text (live log tail) must not break Previous/Next."""
        search, buffer, _view = self._make_search()
        search.search()
        buffer.append("delta needle four\n")
        search.navigate(1)
        self.assertEqual(search.current, 1)
        search.counter.set_text.assert_called_with("2 / 3")
        search.navigate(1)
        search.counter.set_text.assert_called_with("3 / 3")

    def test_refresh_finds_new_matches_without_scrolling(self):
        search, buffer, view = self._make_search()
        search.search()
        view.scroll_to_mark.reset_mock()
        first_offset = search.matches[0][0]
        buffer.append("delta needle four\n")
        search.refresh()
        self.assertEqual(len(search.matches), 4)
        self.assertEqual(search.matches[search.current][0], first_offset)
        search.counter.set_text.assert_called_with("1 / 4")
        view.scroll_to_mark.assert_not_called()

    def test_refresh_without_query_is_noop(self):
        search, _buffer, view = self._make_search()
        search.entry.get_text.return_value = ""
        search.refresh()
        self.assertEqual(search.matches, [])
        view.scroll_to_mark.assert_not_called()

    def test_search_without_matches_reports_zero(self):
        search, _buffer, _view = self._make_search()
        search.entry.get_text.return_value = "zzz"
        search.search()
        self.assertEqual(search.matches, [])
        search.counter.set_text.assert_called_with("0 matches")

    def test_empty_query_clears_state(self):
        search, _buffer, _view = self._make_search()
        search.search()
        search.entry.get_text.return_value = ""
        search.search()
        self.assertEqual(search.matches, [])
        self.assertEqual(search.current, -1)
        search.counter.set_text.assert_called_with("")

    def test_navigate_without_matches_is_noop(self):
        search, _buffer, view = self._make_search()
        search.entry.get_text.return_value = "zzz"
        search.search()
        view.scroll_to_mark.reset_mock()
        search.navigate(1)
        view.scroll_to_mark.assert_not_called()

    def test_offsets_clamped_after_buffer_truncation(self):
        """Offsets beyond the buffer end (after truncation) must not error."""
        search, buffer, _view = self._make_search()
        search.search()
        buffer.set_text(buffer.text[-20:])
        search.navigate(1)
        self.assertEqual(search.current, 1)
        search.counter.set_text.assert_called_with("2 / 3")


if __name__ == "__main__":
    unittest.main()
