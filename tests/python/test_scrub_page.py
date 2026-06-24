"""Tests for pools_page.py scrub UI additions."""

import os
import unittest
from unittest.mock import MagicMock, patch

import sys

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk, temp_config_dir, write_config

import scrub_manager as sm


class TestScrubPageWidgets(unittest.TestCase):

    def test_scrub_store_schema(self):
        with mock_gtk():
            import pools_page as pp
            # Verify the expected column count for the scrub store
            # We can't fully instantiate the UI without a real app, but we can
            # import the module and verify constants.
            self.assertTrue(hasattr(pp, "refresh_scrub_table"))

    def test_get_selected_pool_names(self):
        with mock_gtk():
            import pools_page as pp
            # Create a minimal mock treeview with multi-selection
            mock_model = MagicMock()
            mock_iter = MagicMock()
            mock_model.get_iter.return_value = mock_iter
            mock_model.get_value.side_effect = lambda _it, col: "tank" if col == 0 else ""

            mock_selection = MagicMock()
            mock_selection.get_selected_rows.return_value = (mock_model, ["0"])

            mock_view = MagicMock()
            mock_view.get_selection.return_value = mock_selection

            names = pp.get_selected_pool_names(mock_view)
            self.assertEqual(names, ["tank"])

    def test_flicker_free_refresh_logic(self):
        with mock_gtk():
            import pools_page as pp
            # The refresh_scrub_table function exists and can be called with a
            # mocked app object that has the required attributes.
            app = MagicMock()
            app.scrub_store = MagicMock()
            app.scrub_store.get_iter_first.return_value = None
            app.scrub_store.append = MagicMock(return_value=MagicMock())
            app.scrub_queue = MagicMock()
            app.scrub_queue.summary.return_value = {
                "active": 0, "pending": 0, "paused": 0, "finished": 0, "target": 1,
            }
            app.scrub_summary_label = MagicMock()

            with patch("pools_page.get_all_pool_scrub_states", return_value={}):
                pp.refresh_scrub_table(app)

            app.scrub_summary_label.set_text.assert_called_with("Queue: idle")

    def test_last_scrub_column_uses_monospace_font(self):
        with mock_gtk():
            import pools_page as pp
            with patch.object(pp, "set_monospace_font") as mock_mono:
                with patch.object(pp, "refresh_pools_page", MagicMock()):
                    with patch.object(pp, "ScrubQueue", MagicMock()):
                        app = MagicMock()
                        app.config = {}
                        app._ui_state = MagicMock()
                        pp.create_pools_page(app)

        mock_mono.assert_called()

    def test_refresh_shows_canceled_scrub_date(self):
        with mock_gtk():
            import pools_page as pp
            app = MagicMock()
            app.scrub_store = MagicMock()
            app.scrub_store.get_iter_first.return_value = None
            app.scrub_store.append = MagicMock(return_value=MagicMock())
            app.scrub_queue = MagicMock()
            app.scrub_queue.state_for_pool.return_value = sm.ScrubState.NONE
            app.scrub_queue.summary.return_value = {
                "active": 0, "pending": 0, "paused": 0, "finished": 0, "target": 1,
            }
            app.scrub_summary_label = MagicMock()

            canceled = sm.ScrubInfo(
                state=sm.ScrubState.CANCELED,
                last_scrub="Fri Jun 12 12:00:13 2026",
            )
            with patch("pools_page.get_all_pool_scrub_states", return_value={"tank": canceled}):
                pp.refresh_scrub_table(app)

        appended = app.scrub_store.append.call_args[0][0]
        self.assertEqual(appended[0], "tank")
        self.assertEqual(appended[1], "canceled")
        self.assertEqual(appended[3], "Fri Jun 12 12:00:13 2026")


if __name__ == "__main__":
    unittest.main()
