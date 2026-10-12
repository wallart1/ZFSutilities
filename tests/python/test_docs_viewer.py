"""Tests for docs_viewer.py — standalone documentation viewer launcher."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from test_support import REPO_ROOT, mock_gtk, temp_config_dir, temp_user_config_dir

PYTHON_SRC = os.path.join(REPO_ROOT, "python")


def _import_docs_viewer_fresh():
    """Import docs_viewer with GTK mocked; always return a fresh module."""
    sys.modules.pop("docs_viewer", None)
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

    def test_main_resolves_symlinked_launch_location(self):
        """main() must pass the realpath'd directory, not the symlink's dir."""
        with mock_gtk() as gtk_mock:
            dv = _import_docs_viewer_fresh()

            with tempfile.TemporaryDirectory() as tmpdir:
                link = os.path.join(tmpdir, "docs-viewer-link")
                target = os.path.join(PYTHON_SRC, "docs_viewer.py")
                os.symlink(target, link)
                expected_dir = os.path.dirname(os.path.realpath(link))

                window = MagicMock()
                with (
                    patch.object(dv, "DocsViewerWindow", return_value=window) as mock_win,
                    patch.object(dv, "__file__", link),
                ):
                    dv.main()

            mock_win.assert_called_once_with(expected_dir)
            gtk_mock.main.assert_called_once()


class TestEditPathResolution(unittest.TestCase):
    """Verify openmd:// edit links re-anchor to the tree being served."""

    def test_marker_free_path_passes_through(self):
        """A baked path without the /docs/docs/ marker is returned unchanged."""
        with mock_gtk():
            dv = _import_docs_viewer_fresh()
            result = dv._resolve_edit_path(
                "/home/dan/notes/readme.md",
                "/NFS1/dan(NFS1)/zfsutilities-pub/docs/site/index.html",
            )
        self.assertEqual(result, "/home/dan/notes/readme.md")

    def test_deployed_baked_path_reanchors_to_repo_tree(self):
        """A deployed-built edit URL edits the repo doc when the repo site is served."""
        with mock_gtk():
            dv = _import_docs_viewer_fresh()
            result = dv._resolve_edit_path(
                "/usr/local/lib/zfsutilities/versions/0.123.0/docs/docs/user-guide/restore.md",
                "/NFS1/dan(NFS1)/zfsutilities-pub/docs/site/index.html",
            )
        self.assertEqual(
            result,
            "/NFS1/dan(NFS1)/zfsutilities-pub/docs/docs/user-guide/restore.md",
        )

    def test_version_dir_baked_path_reanchors_to_current(self):
        """A versions/<v>-baked URL edits via current when current is served."""
        with mock_gtk():
            dv = _import_docs_viewer_fresh()
            result = dv._resolve_edit_path(
                "/usr/local/lib/zfsutilities/versions/0.123.0/docs/docs/index.md",
                "/usr/local/lib/zfsutilities/current/docs/site/index.html",
            )
        self.assertEqual(
            result,
            "/usr/local/lib/zfsutilities/current/docs/docs/index.md",
        )

    def test_repo_baked_path_is_identity_when_repo_site_served(self):
        """A site built in the served tree re-anchors onto itself."""
        with mock_gtk():
            dv = _import_docs_viewer_fresh()
            result = dv._resolve_edit_path(
                "/NFS1/dan(NFS1)/zfsutilities-pub/docs/docs/index.md",
                "/NFS1/dan(NFS1)/zfsutilities-pub/docs/site/index.html",
            )
        self.assertEqual(
            result,
            "/NFS1/dan(NFS1)/zfsutilities-pub/docs/docs/index.md",
        )


class TestOpenEditPath(unittest.TestCase):
    """Verify _open_edit_path prefers the served tree and logs the outcome."""

    def _make_window(self, dv, docs_path, euid=1000):
        """Create a DocsViewerWindow with build/ui code patched out."""
        with temp_user_config_dir():
            with (
                patch.object(dv.os, "geteuid", return_value=euid),
                patch.object(dv.DocsViewerWindow, "_build_ui"),
                patch.object(dv, "get_docs_path", return_value=docs_path),
            ):
                window = dv.DocsViewerWindow("/tmp/fake", config=None)
        window._set_status = MagicMock()
        window._launch_editor = MagicMock()
        return window

    def test_reanchored_file_preferred_and_logged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            served_md = os.path.join(tmpdir, "docs", "docs", "index.md")
            os.makedirs(os.path.dirname(served_md))
            with open(served_md, "w") as f:
                f.write("# served\n")
            docs_path = os.path.join(tmpdir, "docs", "site", "index.html")
            baked = "/some/other/tree/docs/docs/index.md"

            with mock_gtk():
                dv = _import_docs_viewer_fresh()
                window = self._make_window(dv, docs_path)
                with patch.object(dv, "log_msg") as mock_log:
                    window._open_edit_path(baked)

            window._launch_editor.assert_called_once_with(served_md)
            logged = " ".join(str(call.args[0]) for call in mock_log.call_args_list)
            self.assertIn("re-anchored", logged)

    def test_baked_file_used_when_reanchored_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_path = os.path.join(tmpdir, "docs", "site", "index.html")
            os.makedirs(os.path.dirname(docs_path))
            baked = os.path.join(tmpdir, "original", "docs", "docs", "index.md")
            os.makedirs(os.path.dirname(baked))
            with open(baked, "w") as f:
                f.write("# original\n")

            with mock_gtk():
                dv = _import_docs_viewer_fresh()
                window = self._make_window(dv, docs_path)
                with patch.object(dv, "log_msg"):
                    window._open_edit_path(baked)

            window._launch_editor.assert_called_once_with(baked)

    def test_missing_target_warns_and_still_opens_editor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_path = os.path.join(tmpdir, "docs", "site", "index.html")
            os.makedirs(os.path.dirname(docs_path))
            baked = "/nonexistent/tree/docs/docs/index.md"

            with mock_gtk():
                dv = _import_docs_viewer_fresh()
                window = self._make_window(dv, docs_path)
                with patch.object(dv, "log_msg") as mock_log:
                    window._open_edit_path(baked)

            expected = os.path.join(tmpdir, "docs", "docs", "index.md")
            window._launch_editor.assert_called_once_with(expected)
            window._set_status.assert_called_once()
            logged = " ".join(str(call.args[0]) for call in mock_log.call_args_list)
            self.assertIn("not found", logged)


class TestMissingSiteFallback(unittest.TestCase):
    """Verify the no-built-site fallback names the launch layout's own tree."""

    def _fallback_message(self, is_deployed):
        """Construct a window with no docs site; return the fallback message."""
        with mock_gtk():
            dv = _import_docs_viewer_fresh()
            with temp_user_config_dir():
                with (
                    patch.object(dv.os, "geteuid", return_value=1000),
                    patch.object(dv, "get_docs_path", return_value=None),
                    patch.object(dv, "is_deployed_layout", return_value=is_deployed),
                    patch.object(dv.DocsViewerWindow, "_show_fallback") as mock_fb,
                ):
                    dv.DocsViewerWindow("/tmp/fake", config=None)
        mock_fb.assert_called_once()
        return mock_fb.call_args.args[0]

    def test_deployed_layout_says_redeploy(self):
        message = self._fallback_message(is_deployed=True)
        self.assertIn("active deployment", message)
        self.assertIn("Redeploy", message)

    def test_repo_layout_says_build_and_names_no_fallback(self):
        message = self._fallback_message(is_deployed=False)
        self.assertIn("repository checkout", message)
        self.assertIn("mkdocs build", message)
        self.assertIn("does not fall back", message)


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
