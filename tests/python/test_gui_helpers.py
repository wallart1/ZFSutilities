"""Tests for gui_helpers.py."""

import unittest
from unittest.mock import MagicMock, patch

from test_support import mock_gtk


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


if __name__ == "__main__":
    unittest.main()
