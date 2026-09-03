"""Tests for gui_helpers.py."""

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


if __name__ == "__main__":
    unittest.main()
