"""Tests for docs_viewer.py — standalone documentation viewer launcher."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from test_support import mock_gtk, REPO_ROOT


PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")


class TestDocsViewerMain(unittest.TestCase):
    """Verify docs_viewer.main() launches the documentation viewer window."""

    def test_main_creates_window_and_starts_gtk_main(self):
        with mock_gtk() as gtk_mock:
            # DocsViewerWindow is imported at module load time, so reload after
            # mock_gtk has installed the fake GTK modules.
            if "docs_viewer" in sys.modules:
                del sys.modules["docs_viewer"]
            import docs_viewer as dv

            window = MagicMock()
            with patch.object(dv, "DocsViewerWindow", return_value=window) as mock_win:
                dv.main()

            mock_win.assert_called_once_with(PYTHON_SRC)
            window.connect.assert_called_once_with("destroy", gtk_mock.main_quit)
            window.show_all.assert_called_once()
            gtk_mock.main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
