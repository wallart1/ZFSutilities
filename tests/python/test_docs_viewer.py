"""Tests for docs_viewer.py — standalone documentation viewer launcher."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from test_support import REPO_ROOT, mock_gtk, temp_config_dir

PYTHON_SRC = os.path.join(REPO_ROOT, "python")


def _import_docs_viewer_fresh():
    """Import docs_viewer with GTK mocked; always return a fresh module."""
    if "docs_viewer" in sys.modules:
        del sys.modules["docs_viewer"]
    import docs_viewer as dv

    return dv


class TestDocsViewerMain(unittest.TestCase):
    """Verify docs_viewer.main() launches the documentation viewer window."""

    def test_import_sets_no_at_bridge(self):
        """Importing the module disables the AT-SPI bridge to avoid warnings."""
        with mock_gtk():
            with patch.dict("os.environ", {}, clear=False):
                os.environ.pop("NO_AT_BRIDGE", None)
                dv = _import_docs_viewer_fresh()
                self.assertEqual(os.environ.get("NO_AT_BRIDGE"), "1")

        self.assertIn("docs_viewer", sys.modules)
        self.assertIs(dv, sys.modules["docs_viewer"])

    def test_import_preserves_existing_no_at_bridge(self):
        """An existing NO_AT_BRIDGE value must not be overwritten."""
        with mock_gtk():
            with patch.dict("os.environ", {"NO_AT_BRIDGE": "0"}, clear=False):
                dv = _import_docs_viewer_fresh()
                self.assertEqual(os.environ.get("NO_AT_BRIDGE"), "0")

        self.assertIn("docs_viewer", sys.modules)
        self.assertIs(dv, sys.modules["docs_viewer"])

    def test_main_creates_window_and_starts_gtk_main(self):
        with mock_gtk() as gtk_mock:
            dv = _import_docs_viewer_fresh()

            window = MagicMock()
            with (
                patch.object(dv, "DocsViewerWindow", return_value=window) as mock_win,
                patch.object(dv.os, "geteuid", return_value=0),
            ):
                dv.main()

            mock_win.assert_called_once_with(PYTHON_SRC)
            window.connect.assert_called_once_with("destroy", gtk_mock.main_quit)
            window.show_all.assert_called_once()
            gtk_mock.main.assert_called_once()

    def test_main_runs_without_elevation_when_non_root(self):
        """The standalone docs viewer must not pkexec when run as a normal user."""
        with mock_gtk() as gtk_mock:
            dv = _import_docs_viewer_fresh()

            window = MagicMock()
            with (
                patch.object(dv, "DocsViewerWindow", return_value=window) as mock_win,
                patch.object(dv.os, "geteuid", return_value=1000),
                patch.object(dv.os, "execvp") as mock_execvp,
            ):
                dv.main()

            mock_execvp.assert_not_called()
            mock_win.assert_called_once_with(PYTHON_SRC)
            window.connect.assert_called_once_with("destroy", gtk_mock.main_quit)
            window.show_all.assert_called_once()
            gtk_mock.main.assert_called_once()


class TestDocsViewerStatePersistence(unittest.TestCase):
    """Verify docs viewer UI state is persisted without root privileges."""

    def _make_window(self, dv, script_dir="/tmp/fake", config=None, euid=1000):
        """Create a DocsViewerWindow with build/ui code patched out."""
        with (
            patch.object(dv.os, "geteuid", return_value=euid),
            patch.object(dv.DocsViewerWindow, "_build_ui"),
            patch.object(dv, "get_docs_path", return_value="/tmp/docs/site/index.html"),
        ):
            return dv.DocsViewerWindow(script_dir, config=config)

    def test_non_root_loads_user_state_and_system_editor(self):
        with temp_config_dir(), tempfile.TemporaryDirectory() as userdir:
            from config_core import CONFIG_PATH

            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(
                    {
                        "gui": {"docs_editor": "marktext"},
                        "ui_state": {"docs_viewer": {"zoom": 1.2}},
                    },
                    f,
                )

            os.makedirs(os.path.join(userdir, "zfsutilities"), exist_ok=True)
            user_state_path = os.path.join(userdir, "zfsutilities", "docs_viewer_state.json")
            with open(user_state_path, "w") as f:
                json.dump({"docs_viewer": {"zoom": 1.8}}, f)

            with patch.dict("os.environ", {"XDG_CONFIG_HOME": userdir}), mock_gtk():
                dv = _import_docs_viewer_fresh()
                window = self._make_window(dv, euid=1000)

            self.assertIsNone(window._config)
            self.assertEqual(window._docs_editor, "marktext")
            self.assertEqual(window._docs_state["zoom"], 1.8)

    def test_non_root_falls_back_to_system_state_when_user_state_missing(self):
        with temp_config_dir(), tempfile.TemporaryDirectory() as userdir:
            from config_core import CONFIG_PATH

            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(
                    {"ui_state": {"docs_viewer": {"zoom": 2.0, "theme": "slate"}}},
                    f,
                )

            with patch.dict("os.environ", {"XDG_CONFIG_HOME": userdir}), mock_gtk():
                dv = _import_docs_viewer_fresh()
                window = self._make_window(dv, euid=1000)

            self.assertEqual(window._docs_state["zoom"], 2.0)
            self.assertEqual(window._docs_state["theme"], "slate")

    def test_non_root_save_writes_user_state(self):
        with temp_config_dir(), tempfile.TemporaryDirectory() as userdir:
            from config_core import CONFIG_PATH

            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump({"gui": {"docs_editor": ""}}, f)

            with patch.dict("os.environ", {"XDG_CONFIG_HOME": userdir}), mock_gtk():
                dv = _import_docs_viewer_fresh()
                window = self._make_window(dv, euid=1000)
                window._zoom_level = 1.5
                window._theme = "dark"
                window._maximized = False
                window.get_size = MagicMock(return_value=(800, 600))
                window.get_position = MagicMock(return_value=(100, 200))

                with patch.object(dv, "save_ui_state") as mock_save_ui:
                    window._do_save()

            mock_save_ui.assert_not_called()

            user_state_path = os.path.join(userdir, "zfsutilities", "docs_viewer_state.json")
            self.assertTrue(os.path.exists(user_state_path))
            with open(user_state_path) as f:
                saved = json.load(f)
            self.assertEqual(saved["docs_viewer"]["zoom"], 1.5)
            self.assertEqual(saved["docs_viewer"]["theme"], "dark")
            self.assertEqual(saved["docs_viewer"]["width"], 800)
            self.assertEqual(saved["docs_viewer"]["height"], 600)
            self.assertEqual(saved["docs_viewer"]["x"], 100)
            self.assertEqual(saved["docs_viewer"]["y"], 200)

    def test_root_save_uses_system_config(self):
        with temp_config_dir(), tempfile.TemporaryDirectory() as userdir:
            from config_core import CONFIG_PATH

            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            config = {"gui": {"docs_editor": "gedit"}, "ui_state": {}}
            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f)

            with patch.dict("os.environ", {"XDG_CONFIG_HOME": userdir}), mock_gtk():
                dv = _import_docs_viewer_fresh()
                window = self._make_window(dv, config=config, euid=0)
                window._zoom_level = 1.0
                window._theme = "default"
                window._maximized = True

                with patch.object(dv, "save_ui_state") as mock_save_ui:
                    window._do_save()

            mock_save_ui.assert_called_once()
            saved_config, saved_state = mock_save_ui.call_args[0]
            self.assertEqual(saved_config, config)
            self.assertEqual(saved_state["docs_viewer"]["zoom"], 1.0)
            self.assertEqual(saved_state["docs_viewer"]["theme"], "default")
            self.assertTrue(saved_state["docs_viewer"]["maximized"])

    def test_user_state_helpers_round_trip(self):
        with tempfile.TemporaryDirectory() as userdir:
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": userdir}), mock_gtk():
                dv = _import_docs_viewer_fresh()
                self.assertEqual(dv._load_user_state(), {})
                dv._save_user_state({"docs_viewer": {"theme": "default"}})
                self.assertEqual(
                    dv._load_user_state(),
                    {"docs_viewer": {"theme": "default"}},
                )


if __name__ == "__main__":
    unittest.main()
