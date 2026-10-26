"""Tests for gui_helpers.py."""

import re
import unittest
from unittest.mock import MagicMock, patch

from test_support import mock_gtk


def _import_gui_helpers():
    """Import gui_helpers under a GTK mock so the suite needs no real gi.

    The functions exercised in this suite are pure logic; only the module
    import itself requires gi.
    """
    with mock_gtk():
        import gui_helpers

    return gui_helpers


class TestGetMountedSnapshots(unittest.TestCase):
    """get_mounted_snapshots parses mount(8) output for snapshot mount state."""

    def _run_with_mount_output(self, stdout, returncode=0):
        gui_helpers = _import_gui_helpers()

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
        gui_helpers = _import_gui_helpers()

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


class _FakeValueEntry:
    """Entry-like fake returning a fixed string value."""

    def __init__(self, value):
        self._value = value

    def get_text(self):
        return self._value


class _FakeValueCombo(_FakeValueEntry):
    """ComboBoxText-like fake returning a fixed string value."""

    def get_active_text(self):
        return self._value


class TestStyleExpanderLabel(unittest.TestCase):
    """style_expander_label colors the label orange for non-default state."""

    def _run(self, non_default):
        gui_helpers = _import_gui_helpers()

        expander = MagicMock()
        gui_helpers.style_expander_label(expander, "Advanced", non_default)
        return expander.get_label_widget.return_value.set_markup.call_args[0][0]

    def test_orange_markup_when_non_default(self):
        self.assertEqual(
            self._run(True),
            '<span foreground="orange"><b>Advanced</b></span>',
        )

    def test_plain_bold_markup_when_default(self):
        self.assertEqual(self._run(False), "<b>Advanced</b>")

    def test_missing_label_widget_is_noop(self):
        gui_helpers = _import_gui_helpers()

        expander = MagicMock()
        expander.get_label_widget.return_value = None
        gui_helpers.style_expander_label(expander, "Advanced", True)


class _FakeStyleContext:
    """Records style classes added to / removed from a widget."""

    def __init__(self):
        self.classes = set()

    def add_class(self, name):
        self.classes.add(name)

    def remove_class(self, name):
        self.classes.discard(name)


class _FakeStyledWidget:
    """Widget fake exposing a recording style context."""

    def __init__(self, style_context=None):
        self._style_context = style_context if style_context is not None else _FakeStyleContext()

    def get_style_context(self):
        return self._style_context


class TestStyleWidgetValueNondefault(unittest.TestCase):
    """style_widget_value_nondefault toggles the orange CSS class."""

    def _run(self, widget, non_default):
        gui_helpers = _import_gui_helpers()
        with patch.object(gui_helpers, "ensure_nondefault_css"):
            gui_helpers.style_widget_value_nondefault(widget, non_default)
        return gui_helpers, widget

    def test_adds_class_when_non_default(self):
        gui_helpers, widget = self._run(_FakeStyledWidget(), True)
        self.assertIn(gui_helpers.NON_DEFAULT_VALUE_CLASS, widget.get_style_context().classes)

    def test_removes_class_when_default(self):
        gui_helpers, widget = self._run(_FakeStyledWidget(), False)
        self.assertNotIn(gui_helpers.NON_DEFAULT_VALUE_CLASS, widget.get_style_context().classes)

    def test_toggle_back_removes_class(self):
        gui_helpers, widget = self._run(_FakeStyledWidget(), True)
        self._run(widget, False)
        self.assertNotIn(gui_helpers.NON_DEFAULT_VALUE_CLASS, widget.get_style_context().classes)

    def test_widget_without_style_context_is_noop(self):
        gui_helpers = _import_gui_helpers()
        with patch.object(gui_helpers, "ensure_nondefault_css"):
            gui_helpers.style_widget_value_nondefault(_FakeValueEntry("x"), True)

    def test_none_style_context_is_noop(self):
        gui_helpers = _import_gui_helpers()
        with patch.object(gui_helpers, "ensure_nondefault_css"):
            gui_helpers.style_widget_value_nondefault(_FakeStyledWidget(None), True)


class TestStyleVarWidgetsNondefault(unittest.TestCase):
    """style_var_widgets_nondefault styles each widget and reports any diff."""

    @staticmethod
    def _styled_value_widget(value):
        """_FakeStyledWidget that reports *value* as an Entry/Combo value."""
        widget = _FakeStyledWidget()
        widget.get_text = lambda: value
        widget.get_active_text = lambda: value
        return widget

    def test_all_default_returns_false_and_no_classes(self):
        gui_helpers = _import_gui_helpers()
        widgets = {
            "includes": self._styled_value_widget(""),
            "doincrementals": self._styled_value_widget("Y"),
        }
        defaults = {"includes": "", "doincrementals": "Y"}

        with patch.object(gui_helpers, "ensure_nondefault_css"):
            result = gui_helpers.style_var_widgets_nondefault(widgets, defaults)

        self.assertFalse(result)
        for widget in widgets.values():
            self.assertNotIn(
                gui_helpers.NON_DEFAULT_VALUE_CLASS, widget.get_style_context().classes
            )

    def test_differing_entry_styles_only_that_widget(self):
        gui_helpers = _import_gui_helpers()
        widgets = {key: _FakeStyledWidget() for key in ("includes", "doincrementals")}
        widgets["includes"].get_text = lambda: "vm-"
        widgets["includes"].get_active_text = lambda: None
        widgets["doincrementals"].get_active_text = lambda: "Y"
        widgets["doincrementals"].get_text = lambda: ""
        defaults = {"includes": "", "doincrementals": "Y"}

        with patch.object(gui_helpers, "ensure_nondefault_css"):
            result = gui_helpers.style_var_widgets_nondefault(widgets, defaults)

        self.assertTrue(result)
        self.assertIn(
            gui_helpers.NON_DEFAULT_VALUE_CLASS, widgets["includes"].get_style_context().classes
        )
        self.assertNotIn(
            gui_helpers.NON_DEFAULT_VALUE_CLASS,
            widgets["doincrementals"].get_style_context().classes,
        )

    def test_reverting_value_removes_class(self):
        gui_helpers = _import_gui_helpers()
        widgets = {"includes": _FakeStyledWidget()}
        defaults = {"includes": ""}

        with patch.object(gui_helpers, "ensure_nondefault_css"):
            widgets["includes"].get_text = lambda: "vm-"
            gui_helpers.style_var_widgets_nondefault(widgets, defaults)
            widgets["includes"].get_text = lambda: ""
            result = gui_helpers.style_var_widgets_nondefault(widgets, defaults)

        self.assertFalse(result)
        self.assertNotIn(
            gui_helpers.NON_DEFAULT_VALUE_CLASS, widgets["includes"].get_style_context().classes
        )


class _FakeFontStyleContext(_FakeStyleContext):
    """Style-context fake that also records CSS providers."""

    def __init__(self):
        super().__init__()
        self.providers = []

    def add_provider(self, provider, _priority):
        self.providers.append(provider)

    def remove_provider(self, provider):
        if provider in self.providers:
            self.providers.remove(provider)


def _font_widget():
    """Widget fake with a provider-recording style context."""
    return _FakeStyledWidget(_FakeFontStyleContext())


class TestLogFontController(unittest.TestCase):
    """LogFontController applies relative font steps and persists them."""

    def _controller(self, widget=None, config=None, state_key="info_log"):
        gui_helpers = _import_gui_helpers()
        return gui_helpers.LogFontController(
            widget if widget is not None else _font_widget(), config, state_key
        )

    def test_css_strings(self):
        gui_helpers = _import_gui_helpers()
        self.assertEqual(
            gui_helpers.log_font_css(2, 10.0),
            f".{gui_helpers.LOG_FONT_CSS_CLASS} {{ font-size: 13pt; }}",
        )
        self.assertEqual(
            gui_helpers.log_font_css(-4, 10.0),
            f".{gui_helpers.LOG_FONT_CSS_CLASS} {{ font-size: 4pt; }}",
        )
        self.assertEqual(
            gui_helpers.log_font_css(-1, 10.0),
            f".{gui_helpers.LOG_FONT_CSS_CLASS} {{ font-size: 8.5pt; }}",
        )

    def test_default_step_has_no_css(self):
        controller = self._controller()
        self.assertEqual(controller.steps, 0)
        self.assertEqual(controller.css(), "")

    def test_larger_smaller_and_reset_move_steps(self):
        controller = self._controller()
        self.assertEqual(controller.larger(), 1)
        self.assertEqual(controller.smaller(), 0)
        self.assertEqual(controller.smaller(), -1)
        self.assertEqual(controller.reset(), 0)

    def test_steps_clamped_to_range(self):
        gui_helpers = _import_gui_helpers()
        controller = self._controller()
        self.assertEqual(controller.set_steps(99), gui_helpers.LOG_FONT_MAX_STEPS)
        self.assertEqual(controller.set_steps(-99), gui_helpers.LOG_FONT_MIN_STEPS)
        self.assertEqual(controller.larger(), gui_helpers.LOG_FONT_MIN_STEPS + 1)

    def test_provider_lifecycle_on_style_context(self):
        gui_helpers = _import_gui_helpers()
        widget = _font_widget()
        controller = gui_helpers.LogFontController(widget)
        ctx = widget.get_style_context()

        # Real GTK returns a fresh CssProvider per call; make the mock do too.
        with patch.object(gui_helpers, "Gtk") as gtk_mock:
            gtk_mock.CssProvider.side_effect = MagicMock

            controller.set_steps(2, persist=False)
            self.assertIn(gui_helpers.LOG_FONT_CSS_CLASS, ctx.classes)
            self.assertEqual(len(ctx.providers), 1)
            first = ctx.providers[0]

            controller.set_steps(3, persist=False)
            self.assertEqual(len(ctx.providers), 1)
            self.assertIsNot(ctx.providers[0], first)

            controller.set_steps(0, persist=False)
            self.assertNotIn(gui_helpers.LOG_FONT_CSS_CLASS, ctx.classes)
            self.assertEqual(ctx.providers, [])

    def test_persist_writes_ui_state(self):
        gui_helpers = _import_gui_helpers()
        config = {"ui_state": {}}
        controller = gui_helpers.LogFontController(_font_widget(), config, "logs_viewer")
        with patch("backup_config.save_ui_state") as save:
            controller.set_steps(2)
        save.assert_called_once_with(config, {"font_sizes": {"logs_viewer": 2}})

    def test_no_persist_without_config(self):
        gui_helpers = _import_gui_helpers()
        controller = gui_helpers.LogFontController(_font_widget())
        with patch("backup_config.save_ui_state") as save:
            controller.set_steps(1)
        save.assert_not_called()

    def test_base_pt_read_from_theme_font(self):
        gui_helpers = _import_gui_helpers()

        class _FontContext(_FakeStyleContext):
            def get_font(self, _state):
                return type("Desc", (), {"get_size": lambda _self: 11 * 1024})()

        widget = _FakeStyledWidget(_FontContext())
        with patch.object(gui_helpers, "Pango", type("P", (), {"SCALE": 1024})):
            controller = gui_helpers.LogFontController(widget)
        self.assertEqual(controller.base_pt, 11.0)

    def test_base_pt_fallback_without_style_context(self):
        gui_helpers = _import_gui_helpers()
        controller = gui_helpers.LogFontController(object())
        self.assertEqual(controller.base_pt, gui_helpers.LOG_FONT_FALLBACK_PT)


class TestLogFontRestore(unittest.TestCase):
    """restore_log_font_scale applies saved steps without re-persisting."""

    def _app(self, font_sizes):
        return type("App", (), {"config": {"ui_state": {"font_sizes": font_sizes}}})()

    def test_restore_applies_saved_steps(self):
        gui_helpers = _import_gui_helpers()
        app = self._app({"info_log": 2})
        widget = _font_widget()
        gui_helpers.restore_log_font_scale(app, widget, "info_log")
        controller = app._log_font_controllers["info_log"]
        self.assertEqual(controller.steps, 2)
        self.assertIs(controller.widget, widget)
        # restore must not rewrite the config
        self.assertEqual(app.config["ui_state"], {"font_sizes": {"info_log": 2}})

    def test_restore_without_saved_entry_stays_default(self):
        gui_helpers = _import_gui_helpers()
        app = self._app({})
        gui_helpers.restore_log_font_scale(app, _font_widget(), "logs_viewer")
        self.assertEqual(app._log_font_controllers["logs_viewer"].steps, 0)

    def test_restore_without_config_is_noop(self):
        gui_helpers = _import_gui_helpers()
        app = type("App", (), {"config": None})()
        gui_helpers.restore_log_font_scale(app, _font_widget(), "info_log")
        self.assertFalse(hasattr(app, "_log_font_controllers"))

    def test_controller_reused_for_same_widget(self):
        gui_helpers = _import_gui_helpers()
        app = self._app({})
        widget = _font_widget()
        first = gui_helpers.get_log_font_controller(app, "info_log", widget)
        again = gui_helpers.get_log_font_controller(app, "info_log", widget)
        self.assertIs(first, again)

    def test_controller_recreated_for_new_widget(self):
        gui_helpers = _import_gui_helpers()
        app = self._app({})
        first = gui_helpers.get_log_font_controller(app, "info_log", _font_widget())
        second = gui_helpers.get_log_font_controller(app, "info_log", _font_widget())
        self.assertIsNot(first, second)


class TestCreateMenuBar(unittest.TestCase):
    """create_menu_bar wires View-menu font submenus to the app handlers."""

    def test_view_menu_contains_font_submenus(self):
        with mock_gtk() as gtk_mock:
            import gui_helpers

            with patch.object(gui_helpers, "Gtk", gtk_mock):
                app = MagicMock()
                gui_helpers.create_menu_bar(app)

        labels = [c.kwargs["label"] for c in gtk_mock.MenuItem.call_args_list]
        self.assertIn("GUI Log Font", labels)
        self.assertIn("Log Viewer Font", labels)
        self.assertEqual(labels.count("Larger"), 2)
        self.assertEqual(labels.count("Smaller"), 2)
        self.assertEqual(labels.count("Default"), 2)

        connects = gtk_mock.MenuItem.return_value.connect.call_args_list
        connect_args = [c.args for c in connects]
        for handler, state_key in (
            (app.on_log_font_larger, "info_log"),
            (app.on_log_font_smaller, "info_log"),
            (app.on_log_font_default, "info_log"),
            (app.on_log_font_larger, "logs_viewer"),
            (app.on_log_font_smaller, "logs_viewer"),
            (app.on_log_font_default, "logs_viewer"),
        ):
            self.assertIn(("activate", handler, state_key), connect_args)


class TestSectionHeaderAndNoteMarkup(unittest.TestCase):
    """section_header and show_note must Pango-escape caller text.

    A bare '&' in a title (e.g. "Findings & Recommendations") otherwise
    aborts markup parsing and renders an empty label — found in the
    2026-10-07 GUI smoke test.
    """

    def _fresh_gui_helpers(self):
        """Import gui_helpers with per-call Box/Label mocks (fresh GTK).

        The shared default mocks merge every widget in the suite into one
        object, so pack_start histories would accumulate across tests.
        """
        with mock_gtk(fresh=True) as gtk:
            gtk.Label = MagicMock(side_effect=lambda *a, **k: MagicMock())
            gtk.Box = MagicMock(side_effect=lambda *a, **k: MagicMock())
            import gui_helpers

        return gui_helpers

    def test_section_header_escapes_title_and_subtitle(self):
        gui_helpers = self._fresh_gui_helpers()
        with patch.object(
            gui_helpers.GLib, "markup_escape_text", side_effect=lambda s: f"[esc:{s}]"
        ):
            box = gui_helpers.section_header("Findings & Recommendations", "a < b & c")
        # pack_start(child, expand, fill, padding): the widget is args[0].
        title, sub = [c.args[0] for c in box.pack_start.call_args_list]
        self.assertEqual(
            title.set_markup.call_args[0][0], "<b>[esc:Findings & Recommendations]</b>"
        )
        self.assertEqual(sub.set_markup.call_args[0][0], "<small><i>[esc:a < b & c]</i></small>")

    def test_section_header_without_subtitle_packs_one_label(self):
        gui_helpers = self._fresh_gui_helpers()
        with patch.object(gui_helpers.GLib, "markup_escape_text", side_effect=lambda s: s):
            box = gui_helpers.section_header("Plain title")
        self.assertEqual(len(box.pack_start.call_args_list), 1)

    def test_show_note_escapes_text(self):
        gui_helpers = _import_gui_helpers()
        label = MagicMock()
        with patch.object(
            gui_helpers.GLib, "markup_escape_text", side_effect=lambda s: f"[esc:{s}]"
        ):
            gui_helpers.show_note(label, "a & b")
        label.set_markup.assert_called_once_with("<i>[esc:a & b]</i>")
        label.show.assert_called_once_with()

    def test_note_label_wraps_at_the_page_width(self):
        """A note label must wrap: an unwrapped label's minimum width is its
        full natural text width, so a long availability note pinned the
        Performance page's minimum at that width and grew a page-level
        horizontal scrollbar that shadowed every table's own scrollbar
        (measured 2026-10-25 with a ~1900px degraded-host note)."""
        gui_helpers = self._fresh_gui_helpers()
        label = gui_helpers.note_label()
        label.set_line_wrap.assert_called_once_with(True)
        label.set_line_wrap_mode.assert_called_once_with(gui_helpers.Pango.WrapMode.WORD)
        label.set_xalign.assert_called_once_with(0.0)
        label.set_no_show_all.assert_called_once_with(True)
        label.hide.assert_called_once_with()


class TestTreeviewRowHeight(unittest.TestCase):
    """treeview_row_height: theme metrics when resolvable, fallback when not.

    The capped table windows size their row budget from this answer, so
    both halves matter: the computed height (ascent + descent scaled by
    Pango, plus the GTK3 vertical separator) and the conventional
    fallback for unresolvable metrics.
    """

    def test_computes_from_pango_metrics(self):
        gui_helpers = _import_gui_helpers()
        view = MagicMock()
        metrics = view.get_pango_context.return_value.get_metrics.return_value
        metrics.get_ascent.return_value = 11000
        metrics.get_descent.return_value = 2200
        view.style_get_property.return_value = 6
        with patch.object(gui_helpers.Pango, "SCALE", 1024):
            height = gui_helpers.treeview_row_height(view)
        self.assertEqual(height, (11000 + 2200) // 1024 + 6)

    def test_falls_back_when_metrics_are_not_numeric(self):
        gui_helpers = _import_gui_helpers()
        view = MagicMock()
        # Unconfigured mocks: ascent/descent are MagicMocks, so the
        # arithmetic raises and the answer is the conventional fallback.
        view.style_get_property.return_value = 6
        self.assertEqual(
            gui_helpers.treeview_row_height(view), gui_helpers.TREEVIEW_ROW_HEIGHT_FALLBACK
        )

    def test_falls_back_when_height_is_not_positive(self):
        gui_helpers = _import_gui_helpers()
        view = MagicMock()
        metrics = view.get_pango_context.return_value.get_metrics.return_value
        metrics.get_ascent.return_value = 0
        metrics.get_descent.return_value = 0
        view.style_get_property.return_value = 0
        with patch.object(gui_helpers.Pango, "SCALE", 1024):
            height = gui_helpers.treeview_row_height(view)
        self.assertEqual(height, gui_helpers.TREEVIEW_ROW_HEIGHT_FALLBACK)


class TestCappedTreeviewScroll(unittest.TestCase):
    """capped_treeview_scroll: fixed 20-row windows by default, natural
    height up to the same cap when fixed_rows=False.

    The fixed window (the Performance-page convention) pins min == max ==
    the cap so short and empty tables keep their full 20-line window; the
    one-row allowance over the target absorbs a classic horizontal
    scrollbar's height so the target row count stays visible.
    """

    def _scroll_for(self, gui_helpers, view=None, **kwargs):
        scroll = MagicMock()
        old_window = gui_helpers.Gtk.ScrolledWindow
        gui_helpers.Gtk.ScrolledWindow = MagicMock(return_value=scroll)
        try:
            return gui_helpers.capped_treeview_scroll(view or MagicMock(), **kwargs), scroll
        finally:
            gui_helpers.Gtk.ScrolledWindow = old_window

    def test_fixed_rows_pins_min_to_the_cap(self):
        gui_helpers = _import_gui_helpers()
        _scroll, mock = self._scroll_for(gui_helpers)
        row = gui_helpers.TREEVIEW_ROW_HEIGHT_FALLBACK
        cap = (row + 2) + (gui_helpers.TABLE_ROW_TARGET + 1) * row
        mock.set_min_content_height.assert_called_once_with(cap)
        mock.set_max_content_height.assert_called_once_with(cap)
        mock.set_propagate_natural_height.assert_called_once_with(True)
        mock.set_policy.assert_called_once_with(
            gui_helpers.Gtk.PolicyType.AUTOMATIC, gui_helpers.Gtk.PolicyType.AUTOMATIC
        )

    def test_fixed_rows_false_keeps_natural_height_convention(self):
        gui_helpers = _import_gui_helpers()
        row = gui_helpers.TREEVIEW_ROW_HEIGHT_FALLBACK
        cap = (row + 2) + (gui_helpers.TABLE_ROW_TARGET + 1) * row
        _scroll, mock = self._scroll_for(gui_helpers, fixed_rows=False)
        mock.set_min_content_height.assert_called_once_with(60)
        mock.set_max_content_height.assert_called_once_with(cap)

    def test_row_target_scales_the_window(self):
        gui_helpers = _import_gui_helpers()
        row = gui_helpers.TREEVIEW_ROW_HEIGHT_FALLBACK
        cap = (row + 2) + (5 + 1) * row
        _scroll, mock = self._scroll_for(gui_helpers, row_target=5)
        mock.set_min_content_height.assert_called_once_with(cap)
        mock.set_max_content_height.assert_called_once_with(cap)

    def test_cap_follows_the_measured_row_height(self):
        gui_helpers = _import_gui_helpers()
        with patch.object(gui_helpers, "treeview_row_height", return_value=30):
            _scroll, mock = self._scroll_for(gui_helpers)
        cap = (30 + 2) + (gui_helpers.TABLE_ROW_TARGET + 1) * 30
        mock.set_min_content_height.assert_called_once_with(cap)
        mock.set_max_content_height.assert_called_once_with(cap)


if __name__ == "__main__":
    unittest.main()
