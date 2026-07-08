"""Tests for GUI infrastructure — GTK mocking, docs viewer, and page mappings."""

import ast
import contextlib
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from test_support import mock_gtk, REPO_ROOT, capture_logs


GUI_PY_PATH = os.path.join(REPO_ROOT, "07 GTK + Python", "zfsutilities_gui.py")
GTK_GUI_HTML_PATH = os.path.join(REPO_ROOT, "06 Docs", "site", "user-guide", "gtk-gui", "index.html")


def extract_page_anchors_from_source(filepath):
    """Parse zfsutilities_gui.py and return the _PAGE_ANCHORS dict."""
    with open(filepath) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ZFSUtilitiesWindow":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == "_PAGE_ANCHORS"
                            and isinstance(item.value, ast.Dict)
                        ):
                            return {
                                ast.literal_eval(k): ast.literal_eval(v)
                                for k, v in zip(item.value.keys, item.value.values)
                            }
    return {}


def extract_html_anchor_ids(html_path):
    """Return all id attribute values from the given HTML file."""
    with open(html_path) as f:
        content = f.read()
    return set(re.findall(r'id="([^"]+)"', content))


class TestPageAnchorMapping(unittest.TestCase):
    """Verify every GUI page maps to a real anchor in the built docs."""

    @classmethod
    def setUpClass(cls):
        cls.page_anchors = extract_page_anchors_from_source(GUI_PY_PATH)
        cls.html_ids = extract_html_anchor_ids(GTK_GUI_HTML_PATH)

    def test_all_pages_have_anchors(self):
        self.assertGreater(len(self.page_anchors), 0)
        expected_pages = {
            "dashboard", "backup", "offsite", "restore", "schedule",
            "checkagainst", "pools", "datasets", "retention", "logs",
        }
        self.assertEqual(set(self.page_anchors.keys()), expected_pages)

    def test_all_anchors_exist_in_html(self):
        missing = []
        for page, anchor in self.page_anchors.items():
            if anchor not in self.html_ids:
                missing.append(f"{page} -> #{anchor}")
        if missing:
            self.fail(f"Missing anchors in {GTK_GUI_HTML_PATH}:\n  " + "\n  ".join(missing))

    def test_all_tab_anchors_have_page_mapping(self):
        """Every *-tab anchor in the HTML must have a corresponding GUI page."""
        tab_anchors = {a for a in self.html_ids if a.endswith("-tab")}
        mapped_anchors = set(self.page_anchors.values())
        unmapped = tab_anchors - mapped_anchors
        if unmapped:
            self.fail(f"GUI pages missing for HTML anchors: {sorted(unmapped)}")


class TestDocsViewerNavigation(unittest.TestCase):
    """Verify DocsViewerWindow.navigate_to_anchor scrolling logic."""

    _STARTED = 0
    _FINISHED = 2

    def _make_window(self, gtk_mock):
        import docs_viewer
        from unittest.mock import MagicMock
        script_dir = os.path.join(REPO_ROOT, "07 GTK + Python")
        win = docs_viewer.DocsViewerWindow(script_dir)
        # Replace the shared webview mock with a fresh one so call counts
        # are isolated between tests.
        win._webview = MagicMock()
        win._webview.get_uri.return_value = ""
        home = "file:///fake/docs/site/index.html"
        gui = "file:///fake/docs/site/user-guide/gtk-gui/index.html"
        win._home_uri = home
        win._gui_uri = gui
        win._page_loaded = False
        win._pending_anchor = None
        return win

    def test_navigate_when_already_on_base_page_and_loaded(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._page_loaded = True
            win._webview.get_uri.return_value = win._gui_uri

            win.navigate_to_anchor("backup-tab")

            win._webview.load_uri.assert_not_called()
            win._webview.run_javascript.assert_called_once()
            args, _ = win._webview.run_javascript.call_args
            self.assertIn("backup-tab", args[0])
            self.assertIn("scrollIntoView", args[0])

    def test_navigate_when_not_yet_loaded(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._page_loaded = False
            win._webview.get_uri.return_value = ""

            win.navigate_to_anchor("restore-tab")

            win._webview.load_uri.assert_called_once_with(win._gui_uri)
            win._webview.run_javascript.assert_not_called()
            self.assertEqual(win._pending_anchor, "restore-tab")

    def test_navigate_when_on_different_page(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._page_loaded = True
            win._webview.get_uri.return_value = "file:///fake/docs/site/other.html"

            win.navigate_to_anchor("pools-tab")

            win._webview.load_uri.assert_called_once_with(win._gui_uri)
            win._webview.run_javascript.assert_not_called()
            self.assertEqual(win._pending_anchor, "pools-tab")

    def test_pending_anchor_scrolls_after_load_finished(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._pending_anchor = "retention-tab"

            # Simulate the load-changed FINISHED signal
            win._on_load_changed(win._webview, self._FINISHED)

            # Theme apply + scroll are also run on FINISHED.
            self.assertEqual(win._webview.run_javascript.call_count, 2)
            args, _ = win._webview.run_javascript.call_args
            self.assertIn("retention-tab", args[0])
            self.assertIn("scrollIntoView", args[0])
            self.assertIsNone(win._pending_anchor)

    def test_load_started_clears_page_loaded(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._page_loaded = True

            win._on_load_changed(win._webview, self._STARTED)

            self.assertFalse(win._page_loaded)

    def test_docs_viewer_has_zoom_buttons(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            self.assertTrue(hasattr(win, "_btn_zoom_in"))
            self.assertTrue(hasattr(win, "_btn_zoom_out"))
            self.assertTrue(hasattr(win, "_btn_zoom_reset"))

    def test_zoom_in(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._zoom_level = 1.0

            win._on_zoom_in(None)

            win._webview.set_zoom_level.assert_called_once()
            args, _ = win._webview.set_zoom_level.call_args
            self.assertAlmostEqual(args[0], 1.1, places=5)

    def test_zoom_out(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._zoom_level = 1.0

            win._on_zoom_out(None)

            win._webview.set_zoom_level.assert_called_once()
            args, _ = win._webview.set_zoom_level.call_args
            self.assertAlmostEqual(args[0], 1.0 / 1.1, places=5)

    def test_zoom_reset(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._zoom_level = 1.5

            win._on_zoom_reset(None)

            win._webview.set_zoom_level.assert_called_once_with(1.0)
            self.assertEqual(win._zoom_level, 1.0)

    def test_zoom_respects_limits(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._zoom_level = 3.0

            win._on_zoom_in(None)
            self.assertEqual(win._zoom_level, 3.0)

            win._zoom_level = 0.5
            win._on_zoom_out(None)
            self.assertEqual(win._zoom_level, 0.5)


class TestDocsViewerStatePersistence(unittest.TestCase):
    """Verify docs viewer geometry, zoom, and theme persistence."""

    def _make_window(self, gtk_mock, config=None):
        import docs_viewer
        script_dir = os.path.join(REPO_ROOT, "07 GTK + Python")
        return docs_viewer.DocsViewerWindow(script_dir, config=config)

    def test_loads_default_state_when_no_config(self):
        with mock_gtk() as gtk_mock:
            import backup_config
            import config_core
            import tempfile
            original_path = backup_config.CONFIG_PATH
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "zfsutilities.json")
                backup_config.CONFIG_PATH = path
                config_core.CONFIG_PATH = path
                try:
                    win = self._make_window(gtk_mock)
                    self.assertEqual(win._zoom_level, 1.0)
                    self.assertEqual(win._theme, "default")
                finally:
                    backup_config.CONFIG_PATH = original_path
                    config_core.CONFIG_PATH = original_path

    def test_restores_geometry_and_zoom_from_config(self):
        with mock_gtk() as gtk_mock:
            config = {
                "ui_state": {
                    "docs_viewer": {
                        "width": 1024,
                        "height": 768,
                        "x": 40,
                        "y": 60,
                        "zoom": 1.5,
                        "theme": "slate",
                    }
                }
            }
            win = self._make_window(gtk_mock, config)
            win.resize = MagicMock()
            win.move = MagicMock()
            win.maximize = MagicMock()

            win._restore_geometry()

            self.assertEqual(win._zoom_level, 1.5)
            self.assertEqual(win._theme, "slate")
            win.resize.assert_called_once_with(1024, 768)
            win.move.assert_called_once_with(40, 60)
            win.maximize.assert_not_called()

    def test_restores_maximized_state(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._docs_state = {"maximized": True}
            win.resize = MagicMock()
            win.move = MagicMock()
            win.maximize = MagicMock()

            win._restore_geometry()

            win.maximize.assert_called_once()
            win.resize.assert_not_called()

    def test_apply_theme_checks_palette_radio(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._webview = MagicMock()

            win._apply_theme("slate")

            win._webview.run_javascript.assert_called_once()
            args, _ = win._webview.run_javascript.call_args
            js = args[0]
            self.assertIn("input[type=\\\"radio\\\"][name=\\\"__palette\\\"]", js)
            self.assertIn("data-md-color-scheme", js)
            self.assertIn("slate", js)
            self.assertIn("dispatchEvent", js)

    def test_capture_theme_parses_reported_scheme(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._webview = MagicMock()
            win._webview.run_javascript_finish.return_value = MagicMock()
            win._webview.run_javascript_finish.return_value.get_js_value.return_value = MagicMock()
            win._webview.run_javascript_finish.return_value.get_js_value.return_value.to_string.return_value = '"slate"'
            win._config = None  # avoid writing config while testing parsing

            win._on_theme_captured(win._webview, MagicMock(), None)

            self.assertEqual(win._theme, "slate")

    def test_preload_theme_seeds_target_localstorage(self):
        with mock_gtk() as gtk_mock:
            win = self._make_window(gtk_mock)
            win._webview = MagicMock()
            win._theme = "slate"

            win._preload_theme("http://127.0.0.1:8000/user-guide/gtk-gui/index.html")

            win._webview.run_javascript.assert_called_once()
            args, _ = win._webview.run_javascript.call_args
            js = args[0]
            self.assertIn("localStorage.setItem", js)
            self.assertIn("/user-guide/gtk-gui/", js)
            self.assertIn("__palette", js)
            self.assertIn("slate", js)
            self.assertIn("index", js)

    def test_theme_script_message_updates_saved_theme(self):
        with mock_gtk() as gtk_mock:
            import docs_viewer
            import backup_config
            import config_core
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "zfsutilities.json")
                backup_config.CONFIG_PATH = path
                config_core.CONFIG_PATH = path
                try:
                    config = {"ui_state": {}}
                    win = self._make_window(gtk_mock, config)
                    win._webview = MagicMock()
                    win._theme = "default"
                    win.get_window = MagicMock(return_value=None)
                    win.get_size = MagicMock(return_value=(900, 700))
                    win.get_position = MagicMock(return_value=(10, 20))

                    js_result = MagicMock()
                    js_result.get_js_value.return_value.to_string.return_value = '"slate"'
                    win._on_theme_script_message(None, js_result)

                    self.assertEqual(win._theme, "slate")
                    saved = backup_config.load_config()
                    self.assertEqual(
                        saved["ui_state"]["docs_viewer"]["theme"], "slate"
                    )
                finally:
                    backup_config.CONFIG_PATH = "/root/.config/zfsutilities.json"
                    config_core.CONFIG_PATH = "/root/.config/zfsutilities.json"

    def test_save_persists_docs_viewer_state(self):
        with mock_gtk() as gtk_mock:
            import docs_viewer
            import backup_config
            import config_core
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "zfsutilities.json")
                backup_config.CONFIG_PATH = path
                config_core.CONFIG_PATH = path
                try:
                    config = {"ui_state": {}}
                    win = self._make_window(gtk_mock, config)
                    win._webview = MagicMock()
                    win._zoom_level = 1.25
                    win._theme = "slate"
                    win.get_window = MagicMock(return_value=None)
                    win.get_size = MagicMock(return_value=(900, 700))
                    win.get_position = MagicMock(return_value=(10, 20))

                    win._do_save()

                    saved = backup_config.load_config()
                    dv = saved["ui_state"]["docs_viewer"]
                    self.assertEqual(dv["zoom"], 1.25)
                    self.assertEqual(dv["theme"], "slate")
                    self.assertEqual(dv["width"], 900)
                    self.assertEqual(dv["height"], 700)
                    self.assertEqual(dv["x"], 10)
                    self.assertEqual(dv["y"], 20)
                    self.assertFalse(dv["maximized"])
                finally:
                    backup_config.CONFIG_PATH = "/root/.config/zfsutilities.json"


class TestGtkMocking(unittest.TestCase):

    def test_gi_repository_available(self):
        with mock_gtk():
            self.assertIn("gi.repository", sys.modules)
            import gi
            self.assertTrue(hasattr(gi, "require_version"))

    def test_gtk_classes_mocked(self):
        with mock_gtk() as gtk_mock:
            self.assertTrue(hasattr(gtk_mock, "Window"))
            self.assertTrue(hasattr(gtk_mock, "Box"))
            self.assertTrue(hasattr(gtk_mock, "TreeView"))

    def test_pango_mocked(self):
        with mock_gtk() as gtk_mock:
            self.assertTrue(hasattr(gtk_mock.Pango, "Style"))
            self.assertTrue(hasattr(gtk_mock.Pango, "Weight"))

    def test_webkit2_mocked(self):
        with mock_gtk() as gtk_mock:
            import gi
            self.assertTrue(hasattr(gi.repository, "WebKit2"))
            self.assertTrue(hasattr(gi.repository.WebKit2, "WebView"))

    def test_snapshot_manager_imports(self):
        with mock_gtk():
            import snapshot_manager
            self.assertTrue(hasattr(snapshot_manager, "SnapshotManagerWindow"))

    def test_snapshot_manager_window_instantiates(self):
        with mock_gtk() as gtk_mock:
            import snapshot_manager
            parent = MagicMock()
            with patch.object(snapshot_manager.SnapshotManagerWindow, "refresh_snapshots"):
                win = snapshot_manager.SnapshotManagerWindow("tank/data", parent)
            self.assertIsNotNone(win)
            self.assertEqual(win.dataset, "tank/data")
            self.assertIs(win.parent_window, parent)

    def test_gui_helpers_imports(self):
        with mock_gtk():
            import gui_helpers
            self.assertTrue(hasattr(gui_helpers, "setup_row_scroll"))

    def test_bold_label_applies_markup_and_alignment(self):
        with mock_gtk():
            import importlib
            import gui_helpers
            importlib.reload(gui_helpers)
            label = gui_helpers.bold_label("Snapshot")
            self.assertIs(label, gui_helpers.Gtk.Label.return_value)
            label.set_markup.assert_called_once_with("<b>Snapshot</b>")
            label.set_halign.assert_called_once_with(gui_helpers.Gtk.Align.START)

    def test_zfsutilities_gui_imports(self):
        """Verify zfsutilities_gui imports cleanly (catches missing page imports)."""
        with mock_gtk():
            import zfsutilities_gui
            self.assertTrue(hasattr(zfsutilities_gui, "ZFSUtilitiesWindow"))

    def test_docs_viewer_imports(self):
        with mock_gtk():
            import docs_viewer
            self.assertTrue(hasattr(docs_viewer, "DocsViewerWindow"))
            self.assertTrue(hasattr(docs_viewer, "resolve_docs_path"))

    def test_docs_viewer_window_instantiates(self):
        with mock_gtk() as gtk_mock:
            import docs_viewer
            script_dir = os.path.join(REPO_ROOT, "07 GTK + Python")
            win = docs_viewer.DocsViewerWindow(script_dir)
            self.assertIsNotNone(win)

    def test_docs_path_resolution(self):
        with mock_gtk():
            import docs_viewer
            script_dir = os.path.join(REPO_ROOT, "07 GTK + Python")
            path = docs_viewer.resolve_docs_path(script_dir)
            expected = os.path.join(REPO_ROOT, "06 Docs", "site", "index.html")
            self.assertEqual(path, expected)
            self.assertTrue(os.path.isfile(path))


class TestDocsServer(unittest.TestCase):
    """Verify the embedded docs HTTP server starts, serves files, and stops."""

    def test_server_returns_http_uri(self):
        with mock_gtk():
            import docs_viewer
        docs_dir = os.path.dirname(GTK_GUI_HTML_PATH)
        server = docs_viewer._DocsServer(docs_dir)
        try:
            uri = server.start()
            self.assertTrue(uri.startswith("http://127.0.0.1:"))
            port = int(uri.rsplit(":", 1)[1])
            self.assertGreater(port, 0)
            self.assertLess(port, 65536)
        finally:
            server.stop()

    def test_server_serves_docs_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = os.path.join(tmpdir, "index.html")
            with open(index_path, "w") as fh:
                fh.write("<html><body>docs</body></html>")

            with mock_gtk():
                import docs_viewer
            server = docs_viewer._DocsServer(tmpdir)
            try:
                base_uri = server.start()
                url = base_uri + "/index.html"
                from urllib.request import urlopen
                with urlopen(url, timeout=5) as response:
                    body = response.read().decode("utf-8")
                self.assertIn("docs", body)
            finally:
                server.stop()

    def test_server_stops_and_releases_port(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "index.html"), "w") as fh:
                fh.write("x")

            with mock_gtk():
                import docs_viewer
            server = docs_viewer._DocsServer(tmpdir)
            base_uri = server.start()
            server.stop()

            import socket
            port = int(base_uri.rsplit(":", 1)[1])
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                result = sock.connect_ex(("127.0.0.1", port))
                self.assertNotEqual(result, 0,
                                    "Server socket should be closed after stop()")

    def test_request_handler_suppresses_logs(self):
        with mock_gtk():
            import docs_viewer
        handler = docs_viewer._DocsRequestHandler
        self.assertTrue(hasattr(handler, "log_message"))

    def test_viewer_uses_http_uris(self):
        with mock_gtk():
            import docs_viewer
            script_dir = os.path.join(REPO_ROOT, "07 GTK + Python")
            win = docs_viewer.DocsViewerWindow(script_dir)
            try:
                self.assertTrue(hasattr(win, "_docs_server"))
                self.assertIsNotNone(win._docs_server)
                self.assertTrue(win._home_uri.startswith("http://127.0.0.1:"))
                self.assertTrue(win._gui_uri.startswith("http://127.0.0.1:"))
                self.assertIn("/index.html", win._home_uri)
                self.assertIn("/user-guide/gtk-gui/index.html", win._gui_uri)
            finally:
                win._docs_server.stop()


class TestUIStateManagerTreeviewColumns(unittest.TestCase):

    def test_default_includes_treeview_columns(self):
        import backup_config
        defaults = backup_config.UI_STATE_DEFAULTS
        self.assertIn("treeview_columns", defaults)
        self.assertEqual(defaults["treeview_columns"], {})

    @patch("backup_config.save_ui_state")
    def test_do_save_collects_column_widths(self, mock_save):
        with mock_gtk() as gtk_mock:
            gtk_mock.TreeViewColumnSizing = MagicMock()
            gtk_mock.TreeViewColumnSizing.FIXED = 2
            import gui_helpers
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {}}
            mgr = gui_helpers.UIStateManager(win, config)

            col1 = MagicMock()
            col1.get_resizable.return_value = True
            col1.get_min_width.return_value = 20
            col1.get_width.return_value = 123
            col2 = MagicMock()
            col2.get_resizable.return_value = False
            col2.get_width.return_value = 456
            tv = MagicMock()
            tv.get_realized.return_value = True
            tv.get_columns.return_value = [col1, col2]

            # Run the idle restoration immediately so the TreeView is registered.
            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            mgr._do_save()

            args = mock_save.call_args[0][1]
            self.assertIn("treeview_columns", args)
            self.assertEqual(args["treeview_columns"]["test_view"], [123])

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_restores_saved_widths(self, mock_save):
        with mock_gtk():
            import gui_helpers
            import backup_config
            gui_helpers.Gtk.TreeViewColumnSizing = MagicMock()
            gui_helpers.Gtk.TreeViewColumnSizing.FIXED = 2
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {"treeview_columns": {"test_view": [150, 200]}}}
            mgr = gui_helpers.UIStateManager(win, config)

            col1 = MagicMock()
            col1.get_resizable.return_value = True
            col1.get_min_width.return_value = 20
            col2 = MagicMock()
            col2.get_resizable.return_value = True
            col2.get_min_width.return_value = 20
            tv = MagicMock()
            tv.get_columns.return_value = [col1, col2]

            # Patch GLib.idle_add to execute immediately
            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            col1.set_sizing.assert_called_once_with(gui_helpers.Gtk.TreeViewColumnSizing.FIXED)
            col1.set_fixed_width.assert_called_once_with(150)
            col2.set_sizing.assert_called_once_with(gui_helpers.Gtk.TreeViewColumnSizing.FIXED)
            col2.set_fixed_width.assert_called_once_with(200)

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_scales_saved_widths_to_fit_window(self, mock_save):
        """Saved column widths are scaled down so they never expand the window."""
        with mock_gtk():
            import gui_helpers
            import backup_config
            gui_helpers.Gtk.TreeViewColumnSizing = MagicMock()
            gui_helpers.Gtk.TreeViewColumnSizing.FIXED = 2
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {
                "ui_state": {
                    "main_window": {"width": 400},
                    "treeview_columns": {"test_view": [200, 300]},
                }
            }
            mgr = gui_helpers.UIStateManager(win, config)

            col1 = MagicMock()
            col1.get_resizable.return_value = True
            col1.get_min_width.return_value = 20
            col2 = MagicMock()
            col2.get_resizable.return_value = True
            col2.get_min_width.return_value = 20
            tv = MagicMock()
            tv.get_columns.return_value = [col1, col2]

            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            # Budget = 400 - 300 chrome = 100; total saved = 500; scale = 0.2
            col1.set_fixed_width.assert_called_once_with(40)
            col2.set_fixed_width.assert_called_once_with(60)

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_defers_width_signal_until_after_restore(self, mock_save):
        """notify::width handlers connect only after saved widths are applied.

        This prevents GTK's initial layout notifications from overwriting saved
        column widths with default/minimum values on startup or version switch.
        """
        with mock_gtk():
            import gui_helpers
            import backup_config
            gui_helpers.Gtk.TreeViewColumnSizing = MagicMock()
            gui_helpers.Gtk.TreeViewColumnSizing.FIXED = 2
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {"treeview_columns": {"test_view": [150, 200]}}}
            mgr = gui_helpers.UIStateManager(win, config)

            col1 = MagicMock()
            col1.get_resizable.return_value = True
            col1.get_min_width.return_value = 20
            col2 = MagicMock()
            col2.get_resizable.return_value = True
            col2.get_min_width.return_value = 20
            tv = MagicMock()
            tv.get_columns.return_value = [col1, col2]

            calls = []
            col1.set_fixed_width.side_effect = lambda w: calls.append(("set_fixed_width", 1, w))
            col2.set_fixed_width.side_effect = lambda w: calls.append(("set_fixed_width", 2, w))

            def _make_capture(column_idx):
                def _capture_connect(signal, handler):
                    calls.append(("connect", column_idx, signal))
                    return 1
                return _capture_connect

            col1.connect.side_effect = _make_capture(1)
            col2.connect.side_effect = _make_capture(2)

            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            # Widths must be restored before any notify::width handler is attached.
            set_width_indices = [
                i for i, c in enumerate(calls) if c[0] == "set_fixed_width"
            ]
            notify_indices = [
                i for i, c in enumerate(calls)
                if c[0] == "connect" and c[2] == "notify::width"
            ]
            self.assertTrue(set_width_indices)
            self.assertTrue(notify_indices)
            self.assertGreater(min(notify_indices), max(set_width_indices))

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_allows_scrolled_window_to_shrink(self, mock_save):
        """The parent ScrolledWindow is configured so the window can shrink."""
        with mock_gtk():
            import gui_helpers
            import backup_config
            gui_helpers.Gtk.TreeViewColumnSizing = MagicMock()
            gui_helpers.Gtk.TreeViewColumnSizing.FIXED = 2

            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {"treeview_columns": {"test_view": [150, 200]}}}
            mgr = gui_helpers.UIStateManager(win, config)

            scrolled = MagicMock()
            scrolled.set_min_content_width = MagicMock()
            scrolled.set_policy = MagicMock()

            tv = MagicMock()
            tv.get_columns.return_value = []
            tv.get_realized.return_value = True
            tv.get_parent.return_value = scrolled
            scrolled.get_parent.return_value = None

            mgr.bind_treeview(tv, "test_view")

            tv.set_size_request.assert_called_once_with(
                gui_helpers.TREEVIEW_MIN_WIDTH, -1
            )
            scrolled.set_min_content_width.assert_called_once_with(
                gui_helpers.TREEVIEW_MIN_WIDTH
            )
            scrolled.set_policy.assert_called_once_with(
                gui_helpers.Gtk.PolicyType.AUTOMATIC,
                gui_helpers.Gtk.PolicyType.AUTOMATIC,
            )

    @patch("backup_config.save_ui_state")
    def test_do_save_skips_unrealized_treeview(self, mock_save):
        """Hidden stack pages that are not yet realized must not corrupt saved widths."""
        with mock_gtk() as gtk_mock:
            gtk_mock.TreeViewColumnSizing = MagicMock()
            gtk_mock.TreeViewColumnSizing.FIXED = 2
            import gui_helpers

            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {"treeview_columns": {"test_view": [150, 200]}}}
            mgr = gui_helpers.UIStateManager(win, config)

            col1 = MagicMock()
            col1.get_resizable.return_value = True
            col1.get_min_width.return_value = 20
            col1.get_width.return_value = 150
            col2 = MagicMock()
            col2.get_resizable.return_value = True
            col2.get_min_width.return_value = 20
            col2.get_width.return_value = 200
            tv = MagicMock()
            tv.get_realized.return_value = False
            tv.get_columns.return_value = [col1, col2]

            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            mgr._do_save()

            args = mock_save.call_args[0][1]
            self.assertNotIn("treeview_columns", args)

    @patch("backup_config.save_ui_state")
    def test_do_save_skips_placeholder_column_widths(self, mock_save):
        """Columns that report 0/1 px before allocation must not be persisted."""
        with mock_gtk() as gtk_mock:
            gtk_mock.TreeViewColumnSizing = MagicMock()
            gtk_mock.TreeViewColumnSizing.FIXED = 2
            import gui_helpers

            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {"treeview_columns": {"test_view": [150, 200]}}}
            mgr = gui_helpers.UIStateManager(win, config)

            col1 = MagicMock()
            col1.get_resizable.return_value = True
            col1.get_min_width.return_value = 20
            col1.get_width.return_value = 0
            col2 = MagicMock()
            col2.get_resizable.return_value = True
            col2.get_min_width.return_value = 20
            col2.get_width.return_value = 1
            tv = MagicMock()
            tv.get_realized.return_value = True
            tv.get_columns.return_value = [col1, col2]

            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            mgr._do_save()

            args = mock_save.call_args[0][1]
            self.assertNotIn("treeview_columns", args)

    @patch("backup_config.save_ui_state")
    def test_do_save_keeps_intentionally_minimized_columns(self, mock_save):
        """Columns explicitly set to the minimum width are still persisted."""
        with mock_gtk() as gtk_mock:
            gtk_mock.TreeViewColumnSizing = MagicMock()
            gtk_mock.TreeViewColumnSizing.FIXED = 2
            import gui_helpers

            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {}}
            mgr = gui_helpers.UIStateManager(win, config)

            col1 = MagicMock()
            col1.get_resizable.return_value = True
            col1.get_min_width.return_value = 20
            col1.get_width.return_value = 20
            col2 = MagicMock()
            col2.get_resizable.return_value = True
            col2.get_min_width.return_value = 20
            col2.get_width.return_value = 20
            tv = MagicMock()
            tv.get_realized.return_value = True
            tv.get_columns.return_value = [col1, col2]

            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            mgr._do_save()

            args = mock_save.call_args[0][1]
            self.assertIn("treeview_columns", args)
            self.assertEqual(args["treeview_columns"]["test_view"], [20, 20])

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_not_saved_before_idle_runs(self, mock_save):
        """TreeView registration is deferred until the idle restoration runs.

        A configure event that fires before the TreeView is allocated must not
        persist placeholder widths for pages hidden in a Gtk.Stack.
        """
        with mock_gtk() as gtk_mock:
            gtk_mock.TreeViewColumnSizing = MagicMock()
            gtk_mock.TreeViewColumnSizing.FIXED = 2
            import gui_helpers

            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {"treeview_columns": {"test_view": [150, 200]}}}
            mgr = gui_helpers.UIStateManager(win, config)

            col1 = MagicMock()
            col1.get_resizable.return_value = True
            col1.get_min_width.return_value = 20
            col1.get_width.return_value = 150
            col2 = MagicMock()
            col2.get_resizable.return_value = True
            col2.get_min_width.return_value = 20
            col2.get_width.return_value = 200
            tv = MagicMock()
            tv.get_realized.return_value = True
            tv.get_columns.return_value = [col1, col2]

            idle_callbacks = []
            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: idle_callbacks.append(fn) or 1
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            # Before the idle callback runs, the TreeView is not registered,
            # so an early _do_save must not include any column widths.
            mgr._do_save()
            args = mock_save.call_args[0][1]
            self.assertNotIn("treeview_columns", args)

            # Once the idle restoration runs, the TreeView is registered and
            # its widths can be persisted.
            self.assertEqual(len(idle_callbacks), 1)
            idle_callbacks[0]()
            mgr._do_save()
            args = mock_save.call_args[0][1]
            self.assertIn("treeview_columns", args)
            self.assertEqual(args["treeview_columns"]["test_view"], [150, 200])

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_defers_shrink_setup_until_realized(self, mock_save):
        """If the TreeView is not yet realized, configure scrolling on realize."""
        with mock_gtk():
            import gui_helpers
            import backup_config
            gui_helpers.Gtk.TreeViewColumnSizing = MagicMock()
            gui_helpers.Gtk.TreeViewColumnSizing.FIXED = 2

            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {}}
            mgr = gui_helpers.UIStateManager(win, config)

            scrolled = MagicMock()
            scrolled.set_min_content_width = MagicMock()
            scrolled.set_policy = MagicMock()

            tv = MagicMock()
            tv.get_columns.return_value = []
            tv.get_realized.return_value = False
            tv.get_parent.return_value = scrolled
            scrolled.get_parent.return_value = None

            handlers = {}

            def _capture_connect(signal, handler):
                handlers[signal] = handler
                return 1

            tv.connect.side_effect = _capture_connect

            mgr.bind_treeview(tv, "test_view")

            scrolled.set_min_content_width.assert_not_called()
            self.assertIn("realize", handlers)

            # Simulate GTK realizing the widget
            handlers["realize"](tv)

            tv.set_size_request.assert_called_once_with(
                gui_helpers.TREEVIEW_MIN_WIDTH, -1
            )
            scrolled.set_min_content_width.assert_called_once_with(
                gui_helpers.TREEVIEW_MIN_WIDTH
            )
            scrolled.set_policy.assert_called_once_with(
                gui_helpers.Gtk.PolicyType.AUTOMATIC,
                gui_helpers.Gtk.PolicyType.AUTOMATIC,
            )

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_no_scrolled_window_is_safe(self, mock_save):
        """If the TreeView has no ScrolledWindow ancestor, bind_treeview still works."""
        with mock_gtk():
            import gui_helpers
            import backup_config
            gui_helpers.Gtk.TreeViewColumnSizing = MagicMock()
            gui_helpers.Gtk.TreeViewColumnSizing.FIXED = 2

            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {}}
            mgr = gui_helpers.UIStateManager(win, config)

            tv = MagicMock()
            tv.get_columns.return_value = []
            tv.get_realized.return_value = True
            tv.get_parent.return_value = None

            # Should not raise
            mgr.bind_treeview(tv, "test_view")

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_finds_scrolled_window_through_intermediate_parent(self, mock_save):
        """The helper walks up through intermediate containers to find the ScrolledWindow."""
        with mock_gtk():
            import gui_helpers
            import backup_config
            gui_helpers.Gtk.TreeViewColumnSizing = MagicMock()
            gui_helpers.Gtk.TreeViewColumnSizing.FIXED = 2

            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {}}
            mgr = gui_helpers.UIStateManager(win, config)

            scrolled = MagicMock()
            scrolled.set_min_content_width = MagicMock()
            scrolled.set_policy = MagicMock()

            # Use a plain object for the intermediate container so it does not
            # accidentally satisfy the duck-typing check before we reach the
            # ScrolledWindow.
            class _IntermediateContainer:
                def __init__(self, parent):
                    self._parent = parent

                def get_parent(self):
                    return self._parent

            intermediate = _IntermediateContainer(scrolled)
            scrolled.get_parent.return_value = None

            tv = MagicMock()
            tv.get_columns.return_value = []
            tv.get_realized.return_value = True
            tv.get_parent.return_value = intermediate

            mgr.bind_treeview(tv, "test_view")

            scrolled.set_min_content_width.assert_called_once_with(100)
            scrolled.set_policy.assert_called_once_with(
                gui_helpers.Gtk.PolicyType.AUTOMATIC,
                gui_helpers.Gtk.PolicyType.AUTOMATIC,
            )


class TestTreeviewColumnHelpers(unittest.TestCase):
    """Tests for the shared column/shrink helpers."""

    def test_configure_treeview_column_sets_fixed_width(self):
        with mock_gtk():
            import gui_helpers
            col = MagicMock()
            gui_helpers.configure_treeview_column(col, width=80, min_width=40)
            col.set_min_width.assert_called_once_with(40)
            col.set_sizing.assert_called_once_with(
                gui_helpers.Gtk.TreeViewColumnSizing.FIXED
            )
            col.set_fixed_width.assert_called_once_with(80)
            col.set_resizable.assert_called_once_with(True)

    def test_configure_treeview_column_defaults_width_to_min(self):
        with mock_gtk():
            import gui_helpers
            col = MagicMock()
            gui_helpers.configure_treeview_column(col, min_width=55)
            col.set_fixed_width.assert_called_once_with(55)

    def test_configure_treeview_column_can_be_non_resizable(self):
        with mock_gtk():
            import gui_helpers
            col = MagicMock()
            gui_helpers.configure_treeview_column(col, width=80, resizable=False)
            col.set_resizable.assert_not_called()

    @patch("backup_config.save_ui_state")
    def test_bind_treeview_clamps_saved_width_to_min_width(self, mock_save):
        with mock_gtk():
            import gui_helpers
            import backup_config
            gui_helpers.Gtk.TreeViewColumnSizing = MagicMock()
            gui_helpers.Gtk.TreeViewColumnSizing.FIXED = 2
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {"treeview_columns": {"test_view": [10]}}}
            mgr = gui_helpers.UIStateManager(win, config)

            col = MagicMock()
            col.get_resizable.return_value = True
            col.get_min_width.return_value = 60
            tv = MagicMock()
            tv.get_columns.return_value = [col]

            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_treeview(tv, "test_view")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            col.set_fixed_width.assert_called_once_with(60)

    def test_reset_resizable_columns_to_min_width_uses_column_minimum(self):
        with mock_gtk():
            import gui_helpers
            col = MagicMock()
            col.get_resizable.return_value = True
            col.get_min_width.return_value = 55
            tv = MagicMock()
            tv.get_columns.return_value = [col]

            count = gui_helpers.reset_resizable_columns_to_min_width(tv)
            self.assertEqual(count, 1)
            col.set_min_width.assert_called_once_with(55)
            col.set_fixed_width.assert_called_once_with(55)

    def test_editable_list_view_default_columns_use_widths(self):
        with mock_gtk():
            import gui_helpers
            elv = gui_helpers.EditableListView()
            self.assertEqual(elv.columns, [
                (1, "Source", 120),
                (2, "Destination", 120),
            ])

    def test_editable_list_view_accepts_custom_column_widths(self):
        with mock_gtk():
            import gui_helpers
            columns = [(1, "Source Pool/Subpool", 160), (2, "Destination Pool", 120)]
            elv = gui_helpers.EditableListView(columns=columns)
            self.assertEqual(elv.columns, columns)


class TestUIStateManagerPanedPositions(unittest.TestCase):

    @patch("backup_config.save_ui_state")
    def test_bind_paned_restores_saved_position(self, mock_save):
        with mock_gtk() as gtk_mock:
            import gui_helpers
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {"paned_positions": {"test_paned": 250}}}
            mgr = gui_helpers.UIStateManager(win, config)

            paned = MagicMock()
            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_paned(paned, "test_paned")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            paned.set_position.assert_called_once_with(250)
            self.assertIn("test_paned", mgr._paneds)
            self.assertIs(mgr._paneds["test_paned"], paned)

    @patch("backup_config.save_ui_state")
    def test_bind_paned_does_not_set_position_when_unsaved(self, mock_save):
        with mock_gtk() as gtk_mock:
            import gui_helpers
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {}}
            mgr = gui_helpers.UIStateManager(win, config)

            paned = MagicMock()
            orig_idle_add = gui_helpers.GLib.idle_add
            gui_helpers.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
            try:
                mgr.bind_paned(paned, "test_paned")
            finally:
                gui_helpers.GLib.idle_add = orig_idle_add

            paned.set_position.assert_not_called()

    @patch("backup_config.save_ui_state")
    def test_do_save_collects_paned_positions(self, mock_save):
        with mock_gtk():
            import gui_helpers
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {}}
            mgr = gui_helpers.UIStateManager(win, config)

            paned = MagicMock()
            paned.get_position.return_value = 300
            mgr._paneds["test_paned"] = paned

            mgr._do_save()

            args = mock_save.call_args[0][1]
            self.assertIn("paned_positions", args)
            self.assertEqual(args["paned_positions"]["test_paned"], 300)

    @patch("backup_config.save_ui_state")
    def test_do_save_ignores_zero_paned_positions(self, mock_save):
        with mock_gtk():
            import gui_helpers
            win = MagicMock()
            win.get_window.return_value = None
            win.get_size.return_value = (100, 100)
            win.get_position.return_value = (0, 0)
            win.vpaned.get_position.return_value = 0
            win.popout_window = None
            config = {"ui_state": {}}
            mgr = gui_helpers.UIStateManager(win, config)

            paned = MagicMock()
            paned.get_position.return_value = 0
            mgr._paneds["test_paned"] = paned

            mgr._do_save()

            args = mock_save.call_args[0][1]
            self.assertNotIn("paned_positions", args)


class _FakeTreeStore:
    """Minimal TreeStore for testing tree helper functions."""
    def __init__(self, rows):
        self._rows = []
        self._by_id = {}
        self._parent_of = {}
        self._add_rows(rows, None)

    def _add_rows(self, rows, parent):
        for row in rows:
            self._rows.append(row)
            self._by_id[row["id"]] = row
            self._parent_of[id(row)] = parent
            self._add_rows(row.get("children", []), row)

    def get_iter_first(self):
        return self._rows[0] if self._rows else None

    def iter_next(self, node):
        parent = self._parent_of[id(node)]
        siblings = []
        for row in self._rows:
            if self._parent_of[id(row)] == parent:
                siblings.append(row)
        idx = siblings.index(node)
        return siblings[idx + 1] if idx + 1 < len(siblings) else None

    def iter_children(self, node):
        for row in self._rows:
            if self._parent_of[id(row)] == node:
                return row
        return None

    def iter_parent(self, node):
        return self._parent_of[id(node)]

    def get_value(self, node, col):
        return node["values"][col]

    def set_value(self, node, col, value):
        node["values"][col] = value

    def get_path(self, node):
        return node["id"]

    def get_iter(self, path):
        return self._by_id.get(path)

    def append(self, parent, values):
        node = {"id": len(self._rows), "values": list(values), "children": []}
        self._rows.append(node)
        self._by_id[node["id"]] = node
        self._parent_of[id(node)] = parent
        return node


class _FakeTreeView:
    def __init__(self, expanded=None, model=None):
        self._expanded = expanded or set()
        self._model = model

    def row_expanded(self, path):
        return path in self._expanded

    def expand_row(self, path, open_all):
        self._expanded.add(path)

    def get_model(self):
        return self._model


class TestGuiHelpersMisc(unittest.TestCase):
    """Miscellaneous gui_helpers not covered elsewhere."""

    def test_set_monospace_font(self):
        with mock_gtk():
            import gui_helpers
            renderer = MagicMock()
            gui_helpers.set_monospace_font(renderer)
            renderer.set_property.assert_called_once_with("font", "monospace")

    def test_create_dialog_sets_title_and_buttons(self):
        with mock_gtk():
            import gui_helpers
            app = MagicMock()
            buttons = [("Cancel", 1), ("OK", 2)]
            dlg = gui_helpers.create_dialog("Test Title", app, buttons, default_response=2)
            self.assertIs(dlg, gui_helpers.Gtk.Dialog.return_value)
            dlg.set_default_response.assert_called_once_with(2)
            gui_helpers.Gtk.Dialog.assert_called_once_with(
                title="Test Title",
                transient_for=app,
                modal=True,
                destroy_with_parent=True,
            )

    def test_add_scrolled_text_view(self):
        with mock_gtk():
            import importlib
            import gui_helpers
            importlib.reload(gui_helpers)
            parent = MagicMock()
            sw = gui_helpers.add_scrolled_text_view(parent, text="hello")
            self.assertIs(sw, gui_helpers.Gtk.ScrolledWindow.return_value)
            buf = gui_helpers.Gtk.TextBuffer.return_value
            tv = gui_helpers.Gtk.TextView.return_value
            tv.set_editable.assert_called_once_with(False)
            buf.set_text.assert_called_once()
            self.assertEqual(buf.set_text.call_args[0][0], "hello")
            parent.add.assert_called_once_with(sw)

    def test_get_tree_selection_items(self):
        with mock_gtk():
            import gui_helpers
            store = _FakeTreeStore([
                {"id": 0, "values": ["tank", "", "pool"], "children": [
                    {"id": 1, "values": ["data", "", "dataset"], "children": []},
                ]},
            ])
            selection = MagicMock()
            selection.get_selected_rows.return_value = (store, [0, 1])
            view = MagicMock()
            view.get_selection.return_value = selection

            items = gui_helpers.get_tree_selection_items(view)

            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["type"], "pool")
            self.assertEqual(items[0]["name"], "tank")
            self.assertEqual(items[1]["type"], "dataset")
            self.assertEqual(items[1]["name"], "tank/data")

    def test_get_expanded_rows(self):
        with mock_gtk():
            import gui_helpers
            store = _FakeTreeStore([
                {"id": 0, "values": ["tank"], "children": [
                    {"id": 1, "values": ["data"], "children": []},
                ]},
            ])
            view = _FakeTreeView(expanded={0})
            expanded = gui_helpers.get_expanded_rows(store, view)
            self.assertEqual(expanded, {"tank"})

    def test_restore_expanded_rows(self):
        with mock_gtk():
            import gui_helpers
            store = _FakeTreeStore([
                {"id": 0, "values": ["tank", "", "", "", "", "", "", False], "children": [
                    {"id": 1, "values": ["data", "", "", "", "", "", "", False], "children": []},
                ]},
            ])
            view = _FakeTreeView(model=store)
            gui_helpers.restore_expanded_rows(store, view, {"tank", "tank/data"})
            self.assertIn(0, view._expanded)
            self.assertIn(1, view._expanded)


def _clear_cached_modules(*names):
    """Remove named modules from sys.modules so they re-import fresh."""
    suffixes = tuple("." + n for n in names)
    for name in list(sys.modules.keys()):
        if name in names or name.endswith(suffixes):
            sys.modules.pop(name, None)


class TestTextViewSearchIcons(unittest.TestCase):
    """Verify TextViewSearch uses icon buttons instead of text buttons."""

    def test_search_and_reset_are_icon_buttons(self):
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers
            text_view = MagicMock()
            text_view.get_buffer.return_value = MagicMock()
            gui_helpers.TextViewSearch(text_view)

            label_calls = [
                c for c in gtk_mock.Button.call_args_list
                if c.kwargs.get("label") in ("Search", "Reset")
            ]
            self.assertEqual(label_calls, [])

    def test_search_and_reset_buttons_get_images(self):
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers
            text_view = MagicMock()
            text_view.get_buffer.return_value = MagicMock()
            gui_helpers.TextViewSearch(text_view)

            gtk_mock.Button.return_value.set_image.assert_called()


class TestAddVarRowEntryWidth(unittest.TestCase):
    """Verify add_var_row sets a narrow minimum width on Entry widgets."""

    def test_add_var_row_sets_width_chars_on_entry(self):
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers
            grid = MagicMock()
            widgets = {}
            gui_helpers.add_var_row(grid, 0, "test_key",
                                    {"test_key": "value"}, widgets)
            gtk_mock.Entry.return_value.set_width_chars.assert_called_once_with(1)


class TestLogLevelButtonLabel(unittest.TestCase):
    """Verify log-level button uses short label format."""

    def test_source_uses_short_label(self):
        """Parse zfsutilities_gui.py to confirm set_label(level) not 'Log: {level}'."""
        with open(GUI_PY_PATH) as f:
            source = f.read()
        # The handler should call set_label(level) — not the old f-string format
        self.assertIn("self.log_level_button.set_label(level)", source)
        self.assertNotIn('self.log_level_button.set_label(f"Log: {level}")', source)


class TestPageLabelWrapping(unittest.TestCase):
    """Verify long description labels have line wrapping enabled."""

    def test_checkagainst_desc_is_wrapped(self):
        _clear_cached_modules("checkagainst_page")
        with mock_gtk() as gtk_mock:
            from unittest.mock import patch
            import checkagainst_page as cp
            labels = []
            def make_label(*args, **kwargs):
                m = MagicMock()
                labels.append(m)
                return m
            gtk_mock.Label.side_effect = make_label

            app = MagicMock()
            app.config = {"checkagainst": []}
            with patch.object(cp, "check_checkagainst_dirty", MagicMock()):
                cp.create_checkagainst_page(app)

            # desc is the second Label created (after hdr)
            desc_label = labels[1]
            desc_label.set_line_wrap.assert_called_once_with(True)

class TestPoolsControlsLayout(unittest.TestCase):
    """Verify scrub controls are stacked vertically, not in one wide row."""

    def test_controls_box_is_vertical(self):
        _clear_cached_modules("pools_page")
        with mock_gtk() as gtk_mock:
            from unittest.mock import patch
            import pools_page as pp
            boxes = []
            def make_box(*args, **kwargs):
                m = MagicMock()
                boxes.append((m, kwargs))
                return m
            gtk_mock.Box.side_effect = make_box

            app = MagicMock()
            app.config = {}
            app._ui_state = MagicMock()
            with patch.object(pp, "refresh_pools_page", MagicMock()):
                with patch.object(pp, "ScrubQueue", MagicMock()):
                    pp.create_pools_page(app)

            # controls_box is the only VERTICAL box with spacing=5
            vertical_spacing5 = [
                b for b, kwargs in boxes
                if kwargs.get("orientation") == 2 and kwargs.get("spacing") == 5
            ]
            self.assertEqual(len(vertical_spacing5), 1)

    def test_controls_rows_are_horizontal(self):
        _clear_cached_modules("pools_page")
        with mock_gtk() as gtk_mock:
            from unittest.mock import patch
            import pools_page as pp
            boxes = []
            def make_box(*args, **kwargs):
                m = MagicMock()
                boxes.append((m, kwargs))
                return m
            gtk_mock.Box.side_effect = make_box

            app = MagicMock()
            app.config = {}
            app._ui_state = MagicMock()
            with patch.object(pp, "refresh_pools_page", MagicMock()):
                with patch.object(pp, "ScrubQueue", MagicMock()):
                    pp.create_pools_page(app)

            # sim_box, ref_box, and check_box are all HORIZONTAL
            horizontal_boxes = [
                b for b, kwargs in boxes
                if kwargs.get("orientation") == 1
            ]
            self.assertGreaterEqual(len(horizontal_boxes), 3)


class TestLogStatusClick(unittest.TestCase):

    def test_searches_latest_message_of_current_level(self):
        import gui_helpers as gh
        app = MagicMock()
        app._log_status_level = "WARN"
        app.info_search.matches = [1, 2]
        gh._on_log_status_clicked(app)
        app.info_search.entry.set_text.assert_called_once_with("WARN:")
        app.info_search.search.assert_called_once()
        app.info_search.navigate.assert_called_once_with(-1)

    def test_fatal_level_searches_latest_fatal_message(self):
        import gui_helpers as gh
        app = MagicMock()
        app._log_status_level = "FATAL"
        app.info_search.matches = [1]
        gh._on_log_status_clicked(app)
        app.info_search.entry.set_text.assert_called_once_with("FATAL:")
        app.info_search.search.assert_called_once()
        app.info_search.navigate.assert_called_once_with(-1)

    def test_does_nothing_when_no_level(self):
        import gui_helpers as gh
        app = MagicMock()
        app._log_status_level = None
        gh._on_log_status_clicked(app)
        app.info_search.entry.set_text.assert_not_called()
        app.info_search.search.assert_not_called()
        app.info_search.navigate.assert_not_called()

    def test_does_not_navigate_when_no_matches(self):
        import gui_helpers as gh
        app = MagicMock()
        app._log_status_level = "WARN"
        app.info_search.matches = []
        gh._on_log_status_clicked(app)
        app.info_search.entry.set_text.assert_called_once_with("WARN:")
        app.info_search.search.assert_called_once()
        app.info_search.navigate.assert_not_called()


class TestMinimizeWidth(unittest.TestCase):
    """Tests for View -> Minimize Width column reset and window shrink."""

    def test_reset_resizable_columns_to_min_width(self):
        """Only resizable columns are reset to their own minimum width."""
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers as gh

            class FakeTreeView:
                def __init__(self, columns):
                    self._columns = columns

                def get_columns(self):
                    return self._columns

            gh.Gtk.TreeView = FakeTreeView
            gh.Gtk.TreeViewColumnSizing = MagicMock()
            gh.Gtk.TreeViewColumnSizing.FIXED = 2

            resizable = MagicMock()
            resizable.get_resizable.return_value = True
            resizable.get_min_width.return_value = 42

            non_resizable = MagicMock()
            non_resizable.get_resizable.return_value = False

            tv = FakeTreeView([resizable, non_resizable])
            box = MagicMock()
            box.get_children.return_value = [tv]
            window = MagicMock()
            window.get_children.return_value = [box]

            count = gh.reset_resizable_columns_to_min_width(window)

            self.assertEqual(count, 1)
            resizable.set_min_width.assert_called_once_with(42)
            resizable.set_sizing.assert_called_once_with(2)
            resizable.set_fixed_width.assert_called_once_with(42)
            non_resizable.set_min_width.assert_not_called()
            non_resizable.set_sizing.assert_not_called()
            non_resizable.set_fixed_width.assert_not_called()

    def test_reset_uses_get_child_fallback(self):
        """Walk widgets that expose get_child() instead of get_children()."""
        _clear_cached_modules("gui_helpers")
        with mock_gtk():
            import gui_helpers as gh

            class FakeTreeView:
                def __init__(self, columns):
                    self._columns = columns

                def get_columns(self):
                    return self._columns

            gh.Gtk.TreeView = FakeTreeView
            gh.Gtk.TreeViewColumnSizing = MagicMock()
            gh.Gtk.TreeViewColumnSizing.FIXED = 2

            col = MagicMock()
            col.get_resizable.return_value = True
            col.get_min_width.return_value = 20

            tv = FakeTreeView([col])

            # Plain object with only get_child() to exercise the fallback path
            frame = type("Frame", (), {"get_child": lambda _self: tv})()

            window = MagicMock()
            window.get_children.return_value = [frame]

            count = gh.reset_resizable_columns_to_min_width(window)

            self.assertEqual(count, 1)
            col.set_min_width.assert_called_once_with(20)
            col.set_fixed_width.assert_called_once_with(20)

    def test_confirm_and_minimize_width_cancel_does_nothing(self):
        """Cancel response leaves columns, config, and window unchanged."""
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers as gh
            import backup_config
            import config_core
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "zfsutilities.json")
                backup_config.CONFIG_PATH = path
                config_core.CONFIG_PATH = path
                try:
                    dialog = MagicMock()
                    dialog.run.return_value = 0  # CANCEL
                    gtk_mock.MessageDialog.return_value = dialog

                    window = MagicMock()
                    window.get_size.return_value = (1000, 700)
                    window.config = {"ui_state": {"treeview_columns": {"x": [100]}}}
                    window.get_window.return_value = None

                    gh.confirm_and_minimize_width(window)

                    gtk_mock.MessageDialog.assert_called_once()
                    window.resize.assert_not_called()
                    self.assertEqual(
                        window.config["ui_state"]["treeview_columns"], {"x": [100]}
                    )
                finally:
                    backup_config.CONFIG_PATH = "/root/.config/zfsutilities.json"
                    config_core.CONFIG_PATH = "/root/.config/zfsutilities.json"

    def test_confirm_and_minimize_width_ok_resets_and_shrinks(self):
        """OK response resets columns, clears saved widths, and resizes."""
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers as gh
            import backup_config
            import config_core
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "zfsutilities.json")
                backup_config.CONFIG_PATH = path
                config_core.CONFIG_PATH = path
                try:
                    dialog = MagicMock()
                    dialog.run.return_value = 1  # OK
                    gtk_mock.MessageDialog.return_value = dialog

                    original_reset = gh.reset_resizable_columns_to_min_width
                    mock_reset = MagicMock(return_value=7)
                    gh.reset_resizable_columns_to_min_width = mock_reset

                    window = MagicMock()
                    window.get_size.return_value = (1000, 700)
                    window.config = {"ui_state": {"treeview_columns": {"x": [100]}}}
                    window.get_window.return_value = None

                    try:
                        with capture_logs() as logs:
                            gh.confirm_and_minimize_width(window)
                    finally:
                        gh.reset_resizable_columns_to_min_width = original_reset

                    gtk_mock.MessageDialog.assert_called_once()
                    mock_reset.assert_called_once_with(window)
                    window.queue_resize.assert_called_once()
                    window.resize.assert_called_once_with(1, 700)
                    saved = backup_config.load_config()
                    self.assertEqual(saved["ui_state"]["treeview_columns"], {})
                    self.assertTrue(
                        any("Reset 7 column" in m for m in logs)
                    )
                finally:
                    backup_config.CONFIG_PATH = "/root/.config/zfsutilities.json"
                    config_core.CONFIG_PATH = "/root/.config/zfsutilities.json"


@contextlib.contextmanager
def _mock_gtk_with_app_window():
    """Extend mock_gtk so Gtk.ApplicationWindow is a concrete class."""
    with mock_gtk() as gtk_mock:
        class FakeApplicationWindow:
            def __init__(self, *args, **kwargs):
                pass
            def __getattr__(self, name):
                return MagicMock()
        gtk_mock.ApplicationWindow = FakeApplicationWindow
        yield gtk_mock


class TestStatusLabel(unittest.TestCase):
    """Status label below the log view displays runner progress text."""

    def _call_update_progress(self, obj, fraction, text):
        """Call ZFSUtilitiesWindow._update_progress on *obj*."""
        _clear_cached_modules("zfsutilities_gui")
        with _mock_gtk_with_app_window():
            import zfsutilities_gui
            zfsutilities_gui.ZFSUtilitiesWindow._update_progress(
                obj, fraction, text
            )

    def test_update_progress_sets_text_and_shows_label(self):
        class Obj:
            status_label = MagicMock()
        obj = Obj()
        self._call_update_progress(obj, 0.5, "[1/2] running step")
        obj.status_label.set_text.assert_called_once_with("[1/2] running step")
        obj.status_label.show.assert_called_once()

    def test_update_progress_without_text_still_shows_label(self):
        class Obj:
            status_label = MagicMock()
        obj = Obj()
        self._call_update_progress(obj, 0.0, "")
        obj.status_label.set_text.assert_not_called()
        obj.status_label.show.assert_called_once()

    def test_update_progress_none_clears_and_hides_label(self):
        class Obj:
            status_label = MagicMock()
        obj = Obj()
        self._call_update_progress(obj, None, None)
        obj.status_label.set_text.assert_called_once_with("")
        obj.status_label.hide.assert_called_once()

    def test_update_progress_no_status_label_is_safe(self):
        class Obj:
            pass
        self._call_update_progress(Obj(), 0.5, "text")


class TestClearButton(unittest.TestCase):
    """Clear button in the log panel also clears the bottom status bar."""

    def test_clear_button_clears_status_bar(self):
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers as gh

            handlers = {}

            def fake_button(*args, **kwargs):
                btn = MagicMock()
                btn._label = kwargs.get("label")

                def fake_connect(signal, handler):
                    if signal == "clicked":
                        handlers[btn._label] = handler
                    return MagicMock()

                btn.connect.side_effect = fake_connect
                return btn

            gtk_mock.Button = fake_button
            gh.Gtk.Button = fake_button

            app = MagicMock()
            app.config = {}
            app._ui_state = None

            gh.create_info_panel(app)

            self.assertIn("Clear", handlers)
            handlers["Clear"](MagicMock())
            app._update_progress.assert_called_once_with(None, "")


if __name__ == "__main__":
    unittest.main()


class TestEnableTextviewCopy(unittest.TestCase):
    """Verify enable_textview_copy adds a right-click Copy/Select All menu."""

    def _make_textview(self):
        start_iter = MagicMock()
        end_iter = MagicMock()
        buf = MagicMock()
        buf.get_start_iter.return_value = start_iter
        buf.get_end_iter.return_value = end_iter

        tv = MagicMock()
        tv.get_buffer.return_value = buf
        handlers = {}
        tv.connect.side_effect = lambda sig, cb: handlers.setdefault(sig, cb)
        return tv, buf, start_iter, end_iter, handlers

    def test_right_click_shows_copy_and_select_all_items(self):
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers as gh

            tv, buf, _, _, handlers = self._make_textview()
            buf.get_selection_bounds.return_value = ()

            gh.enable_textview_copy(tv)

            self.assertIn("button-press-event", handlers)
            event = MagicMock()
            event.button = 3
            self.assertTrue(handlers["button-press-event"](tv, event))
            gtk_mock.Menu.assert_called_once()
            menu = gtk_mock.Menu.return_value
            self.assertEqual(menu.append.call_count, 2)
            item_labels = [call.kwargs.get("label") for call in gtk_mock.MenuItem.call_args_list]
            self.assertIn("Copy", item_labels)
            self.assertIn("Select All", item_labels)

    def test_copy_uses_selected_text_when_available(self):
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers as gh

            selected_text = "selected text"
            tv, buf, start_iter, end_iter, handlers = self._make_textview()
            buf.get_selection_bounds.return_value = (start_iter, end_iter)
            buf.get_text.side_effect = lambda s, e, _: (
                selected_text if s is start_iter and e is end_iter else "other"
            )

            gh.enable_textview_copy(tv)
            event = MagicMock()
            event.button = 3
            handlers["button-press-event"](tv, event)

            item = gtk_mock.MenuItem.return_value
            copy_cb = item.connect.call_args_list[0][0][1]
            copy_cb(None)
            gtk_mock.Clipboard.get_default.assert_called_once()
            clipboard = gtk_mock.Clipboard.get_default.return_value
            clipboard.set_text.assert_called_once_with(selected_text, -1)

    def test_copy_falls_back_to_all_text_when_nothing_selected(self):
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers as gh

            all_text = "entire buffer text"
            tv, buf, _, _, handlers = self._make_textview()
            buf.get_selection_bounds.return_value = ()
            buf.get_text.return_value = all_text

            gh.enable_textview_copy(tv)
            event = MagicMock()
            event.button = 3
            handlers["button-press-event"](tv, event)

            item = gtk_mock.MenuItem.return_value
            copy_cb = item.connect.call_args_list[0][0][1]
            copy_cb(None)
            clipboard = gtk_mock.Clipboard.get_default.return_value
            clipboard.set_text.assert_called_once_with(all_text, -1)

    def test_select_all_selects_entire_buffer(self):
        _clear_cached_modules("gui_helpers")
        with mock_gtk() as gtk_mock:
            import gui_helpers as gh

            tv, buf, start_iter, end_iter, handlers = self._make_textview()
            buf.get_selection_bounds.return_value = ()

            gh.enable_textview_copy(tv)
            event = MagicMock()
            event.button = 3
            handlers["button-press-event"](tv, event)

            item = gtk_mock.MenuItem.return_value
            select_all_cb = item.connect.call_args_list[1][0][1]
            select_all_cb(None)
            buf.select_range.assert_called_once_with(start_iter, end_iter)


class TestPageTitleLabels(unittest.TestCase):
    """Page title labels should not be selectable to avoid highlight-on-switch."""

    def _is_big_bold_markup(self, node):
        """Return True if an AST Call looks like title.set_markup('<big><b>...')."""
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "set_markup":
            return False
        if not node.args:
            return False
        arg = node.args[0]
        return isinstance(arg, ast.Constant) and "<big><b>" in str(arg.value)

    def _is_set_selectable_true(self, node):
        """Return True for title.set_selectable(True)."""
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "set_selectable":
            return False
        if not node.args:
            return False
        arg = node.args[0]
        return isinstance(arg, ast.Constant) and arg.value is True

    def test_no_title_label_is_selectable(self):
        """Every big-bold page title must be non-selectable."""
        pages_dir = os.path.join(REPO_ROOT, "07 GTK + Python")
        offenders = []

        for fname in os.listdir(pages_dir):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(pages_dir, fname)
            with open(path) as f:
                tree = ast.parse(f.read())

            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                label_vars = set()
                big_bold_vars = set()
                selectable_vars = set()

                for node in ast.walk(func):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if (
                                isinstance(target, ast.Name)
                                and isinstance(node.value, ast.Call)
                                and isinstance(node.value.func, ast.Name)
                                and node.value.func.id == "Gtk"
                                and node.value.args == []
                            ):
                                # Only approximate: Gtk.Label() with no args
                                # is used for titles in this codebase.
                                label_vars.add(target.id)

                    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                        call = node.value
                        if isinstance(call.func, ast.Attribute):
                            var = call.func.value
                            if isinstance(var, ast.Name) and var.id in label_vars:
                                if self._is_big_bold_markup(call):
                                    big_bold_vars.add(var.id)
                                elif self._is_set_selectable_true(call):
                                    selectable_vars.add(var.id)

                selectable_titles = big_bold_vars & selectable_vars
                if selectable_titles:
                    offenders.append(
                        f"{fname}: {', '.join(sorted(selectable_titles))}"
                    )

        if offenders:
            self.fail(
                "Page title labels must not be set_selectable(True):\n  "
                + "\n  ".join(offenders)
            )


class TestExpandTreeRecursively(unittest.TestCase):
    """expand_tree_recursively expands a node and all lazy-loaded descendants."""

    def _make_store(self):
        """Return a store mock for a root -> child -> grandchild chain."""
        store = MagicMock()
        root = "root"
        child = "child"
        grandchild = "grandchild"
        placeholder = "(loading...)"

        store.get_iter_first.return_value = root
        store.get_path.side_effect = lambda n: f"path_{n}"
        store.get_value.side_effect = lambda n, col: n if col == 0 else ""

        _children = {
            root: [placeholder, child],
            child: [grandchild],
            grandchild: [],
        }

        def _iter_children(node):
            kids = _children.get(node, [])
            return kids[0] if kids else None

        def _iter_next(node):
            for parent, kids in _children.items():
                try:
                    idx = kids.index(node)
                    if idx + 1 < len(kids):
                        return kids[idx + 1]
                except ValueError:
                    continue
            return None

        store.iter_children.side_effect = _iter_children
        store.iter_next.side_effect = _iter_next
        return store, root, child, grandchild

    def test_expands_chain_and_skips_placeholders(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            view.row_expanded.return_value = False
            store, root, child, grandchild = self._make_store()

            gh.expand_tree_recursively(view, store)

            view.expand_row.assert_any_call("path_root", False)
            view.expand_row.assert_any_call("path_child", False)
            view.expand_row.assert_any_call("path_grandchild", False)
            self.assertEqual(view.expand_row.call_count, 3)

    def test_does_not_re_expand_already_expanded_rows(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            view.row_expanded.return_value = True
            store, _, _, _ = self._make_store()

            gh.expand_tree_recursively(view, store)

            view.expand_row.assert_not_called()

    def test_returns_early_when_store_empty(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            store = MagicMock()
            store.get_iter_first.return_value = None

            gh.expand_tree_recursively(view, store)

            view.expand_row.assert_not_called()

    def test_expands_explicit_iter(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            view.row_expanded.return_value = False
            store, _root, child, grandchild = self._make_store()

            gh.expand_tree_recursively(view, store, child)

            view.expand_row.assert_any_call("path_child", False)
            view.expand_row.assert_any_call("path_grandchild", False)
            self.assertEqual(view.expand_row.call_count, 2)


class TestTreeSearchFreeze(unittest.TestCase):
    """TreeSearch.freeze/thaw suppresses expand/collapse re-runs."""

    def test_freeze_blocks_handle_expand_collapse(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            entry = MagicMock()
            label = MagicMock()
            prev_btn = MagicMock()
            next_btn = MagicMock()

            ts = gh.TreeSearch(view, entry, label, prev_btn, next_btn)
            ts._text = "foo"

            with patch.object(ts, "_run_search") as mock_run:
                ts.freeze()
                ts.handle_expand_collapse()
                mock_run.assert_not_called()

                ts.thaw()
                ts.handle_expand_collapse()
                mock_run.assert_called_once()

    def test_multiple_freeze_thaw_cycles_resume_normally(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            entry = MagicMock()
            label = MagicMock()
            prev_btn = MagicMock()
            next_btn = MagicMock()

            ts = gh.TreeSearch(view, entry, label, prev_btn, next_btn)
            ts._text = "foo"

            with patch.object(ts, "_run_search") as mock_run:
                ts.freeze()
                ts.thaw()
                ts.freeze()
                ts.thaw()
                ts.handle_expand_collapse()
                mock_run.assert_called_once()


class TestTreeSearchMatching(unittest.TestCase):
    """TreeSearch matching behaviour, including optional full-path matching."""

    class _FakeNode:
        def __init__(self, values, children=None, path=None):
            self.values = values
            self.children = children or []
            self.path = path
            self.next_sibling = None

    class _FakeStore:
        def __init__(self, roots):
            self._roots = roots
            for i, node in enumerate(roots):
                if i + 1 < len(roots):
                    node.next_sibling = roots[i + 1]
            self._link_children(roots)

        def _link_children(self, nodes):
            for node in nodes:
                for i, child in enumerate(node.children):
                    if i + 1 < len(node.children):
                        child.next_sibling = node.children[i + 1]
                self._link_children(node.children)

        def get_iter_first(self):
            return self._roots[0] if self._roots else None

        def iter_next(self, node):
            return node.next_sibling

        def iter_children(self, node):
            return node.children[0] if node.children else None

        def get_value(self, node, column):
            return node.values[column]

        def get_path(self, node):
            return node.path

    def _make_store(self):
        """Return a fake store representing threeamigos -> proxmox -> (loading...)."""
        placeholder = self._FakeNode(
            ["(loading...)", "", "", "", "", "", "", True],
            path="0:0:0",
        )
        child = self._FakeNode(
            ["proxmox", "", "filesystem", "", "", "", "", False],
            children=[placeholder],
            path="0:0",
        )
        root = self._FakeNode(
            ["threeamigos", "", "filesystem", "", "", "", "", False],
            children=[child],
            path="0",
        )
        return self._FakeStore([root])

    def _full_name_func(self, _store, node):
        """Return reconstructed ZFS path by node path."""
        return {
            "0": "threeamigos",
            "0:0": "threeamigos/proxmox",
        }.get(node.path)

    def test_local_match_without_full_name_func(self):
        with mock_gtk():
            import gui_helpers as gh

            store = self._make_store()
            ts = gh.TreeSearch(MagicMock(), MagicMock(), MagicMock(),
                               MagicMock(), MagicMock())
            self.assertEqual(ts._find_matches(store, "proxmox"), ["0:0"])
            self.assertEqual(ts._find_matches(store, "threeamigos/proxmox"), [])

    def test_slash_match_with_full_name_func(self):
        with mock_gtk():
            import gui_helpers as gh

            store = self._make_store()
            ts = gh.TreeSearch(MagicMock(), MagicMock(), MagicMock(),
                               MagicMock(), MagicMock(),
                               full_name_func=self._full_name_func)
            self.assertEqual(ts._find_matches(store, "threeamigos/proxmox"),
                             ["0:0"])

    def test_local_match_still_works_with_full_name_func(self):
        with mock_gtk():
            import gui_helpers as gh

            store = self._make_store()
            ts = gh.TreeSearch(MagicMock(), MagicMock(), MagicMock(),
                               MagicMock(), MagicMock(),
                               full_name_func=self._full_name_func)
            self.assertEqual(ts._find_matches(store, "proxmox"), ["0:0"])

    def test_placeholders_are_excluded_from_matches(self):
        with mock_gtk():
            import gui_helpers as gh

            store = self._make_store()
            ts = gh.TreeSearch(MagicMock(), MagicMock(), MagicMock(),
                               MagicMock(), MagicMock(),
                               full_name_func=self._full_name_func)
            self.assertEqual(ts._find_matches(store, "loading"), [])


class TestExpandPathToRow(unittest.TestCase):
    """expand_path_to_row reveals a row by expanding its ancestors."""

    class _Node:
        def __init__(self, values, children=None, path=None):
            self.values = values
            self.children = children or []
            self.path = path
            self.next_sibling = None

    class _Store:
        def __init__(self, roots):
            self._roots = roots
            for i, node in enumerate(roots):
                if i + 1 < len(roots):
                    node.next_sibling = roots[i + 1]
            self._link_children(roots)

        def _link_children(self, nodes):
            for node in nodes:
                for i, child in enumerate(node.children):
                    if i + 1 < len(node.children):
                        child.next_sibling = node.children[i + 1]
                self._link_children(node.children)

        def get_iter_first(self):
            return self._roots[0] if self._roots else None

        def iter_next(self, node):
            return node.next_sibling

        def iter_children(self, node):
            return node.children[0] if node.children else None

        def get_value(self, node, col):
            return node.values[col]

        def get_path(self, node):
            return node.path

    def _make_store(self):
        """Root -> child (not loaded) -> grandchild (target)."""
        grandchild = self._Node(
            ["@snap", "", "snapshot", "", "", "", "", True],
            path="0:0:0",
        )
        child = self._Node(
            ["proxmox", "", "filesystem", "", "", "", "", False],
            children=[grandchild],
            path="0:0",
        )
        root = self._Node(
            ["threeamigos", "", "filesystem", "", "", "", "", True],
            children=[child],
            path="0",
        )
        return self._Store([root]), root, child, grandchild

    def test_expands_collapsed_ancestors(self):
        with mock_gtk():
            import gui_helpers as gh

            store, _root, child, grandchild = self._make_store()
            view = MagicMock()
            view.row_expanded.return_value = False

            with patch.object(gh, "on_row_expanded") as mock_load:
                result = gh.expand_path_to_row(view, store, "0:0:0")

            self.assertIs(result, grandchild)
            mock_load.assert_called_once()
            self.assertEqual(mock_load.call_args[0][1], child)
            self.assertEqual(view.expand_row.call_count, 2)

    def test_skips_already_expanded_ancestors(self):
        with mock_gtk():
            import gui_helpers as gh

            store, _root, _child, grandchild = self._make_store()
            view = MagicMock()
            view.row_expanded.return_value = True

            with patch.object(gh, "on_row_expanded") as mock_load:
                result = gh.expand_path_to_row(view, store, "0:0:0")

            self.assertIs(result, grandchild)
            mock_load.assert_not_called()
            view.expand_row.assert_not_called()

    def test_returns_none_for_invalid_path(self):
        with mock_gtk():
            import gui_helpers as gh

            child = self._Node(
                ["proxmox", "", "filesystem", "", "", "", "", True],
                path="0:0",
            )
            root = self._Node(
                ["threeamigos", "", "filesystem", "", "", "", "", True],
                children=[child],
                path="0",
            )
            store = self._Store([root])
            view = MagicMock()

            result = gh.expand_path_to_row(view, store, "0:0:1")
            self.assertIsNone(result)


class TestTreeSearchGotoMatch(unittest.TestCase):
    """_goto_match reveals, selects, and refreshes around the current match."""

    def test_goto_match_expands_and_selects_path(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            store = MagicMock()
            view.get_model.return_value = store
            entry = MagicMock()
            label = MagicMock()
            prev_btn = MagicMock()
            next_btn = MagicMock()

            ts = gh.TreeSearch(view, entry, label, prev_btn, next_btn)
            ts._text = "foo"
            ts._matches = ["0:0"]
            ts._current_idx = 0

            with patch.object(gh, "expand_path_to_row") as mock_expand, \
                 patch.object(ts, "_update_matches_from_store") as mock_update:
                ts._goto_match(0)

            mock_expand.assert_called_once_with(view, store, "0:0")
            view.get_selection().unselect_all.assert_called_once()
            view.get_selection().select_path.assert_called_once_with("0:0")
            view.scroll_to_cell.assert_called_once()
            mock_update.assert_called_once()
            self.assertFalse(ts._frozen)

    def test_update_matches_from_store_preserves_current_path(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            store = MagicMock()
            view.get_model.return_value = store
            ts = gh.TreeSearch(
                view, MagicMock(), MagicMock(), MagicMock(), MagicMock()
            )
            ts._text = "foo"
            ts._matches = ["0:0"]
            ts._current_idx = 0

            with patch.object(ts, "_find_matches", return_value=["0:0", "0:1"]):
                ts._update_matches_from_store()

            self.assertEqual(ts._matches, ["0:0", "0:1"])
            self.assertEqual(ts._current_idx, 0)

    def test_update_matches_from_store_clamps_index_when_current_gone(self):
        with mock_gtk():
            import gui_helpers as gh

            view = MagicMock()
            store = MagicMock()
            view.get_model.return_value = store
            ts = gh.TreeSearch(
                view, MagicMock(), MagicMock(), MagicMock(), MagicMock()
            )
            ts._text = "foo"
            ts._matches = ["0:0", "0:1", "0:2"]
            ts._current_idx = 2

            with patch.object(ts, "_find_matches", return_value=["0:0"]):
                ts._update_matches_from_store()

            self.assertEqual(ts._matches, ["0:0"])
            self.assertEqual(ts._current_idx, 0)


class _FakeTreePath:
    """Minimal TreePath stand-in for handle_editing_key_press tests."""

    def __init__(self, value):
        if isinstance(value, list):
            self._indices = list(value)
        elif isinstance(value, str):
            self._indices = [int(value)]
        else:
            self._indices = [value]

    @staticmethod
    def new_from_string(s):
        return _FakeTreePath([int(s)])

    @staticmethod
    def new_from_indices(indices):
        return _FakeTreePath(list(indices))

    def __getitem__(self, idx):
        return self._indices[idx]


class TestHandleEditingKeyPress(unittest.TestCase):
    """Unit tests for gui_helpers.handle_editing_key_press."""

    def _make_event(self, keyval):
        event = MagicMock()
        event.keyval = keyval
        return event

    def _setup(self, gh, keyval, path_str, col_idx, editable_cols,
               has_next=True):
        widget = MagicMock()
        treeview = MagicMock()
        model = MagicMock()
        treeview.get_model.return_value = model

        if has_next:
            nxt = MagicMock()
            model.iter_next.return_value = nxt
            model.get_path.return_value = _FakeTreePath([int(path_str) + 1])
        else:
            model.iter_next.return_value = None

        event = self._make_event(keyval)
        gh.Gtk.TreePath = _FakeTreePath
        gh.GLib.idle_add = lambda fn, *a, **k: fn(*a, **k) or False
        return widget, treeview, model, event

    def test_tab_moves_to_next_editable_column(self):
        with mock_gtk():
            import gui_helpers as gh
            gh.Gdk.KEY_Tab = 1
            gh.Gdk.KEY_ISO_Left_Tab = 2

            widget, treeview, _model, event = self._setup(
                gh, 1, "0", 0, [0, 1, 2])

            result = gh.handle_editing_key_press(
                widget, event, treeview, "0", 0, [0, 1, 2])

            self.assertTrue(result)
            widget.editing_done.assert_called_once()
            widget.remove_widget.assert_called_once()
            treeview.set_cursor.assert_called_once()
            args = treeview.set_cursor.call_args[0]
            self.assertEqual(args[0]._indices, [0])
            self.assertEqual(args[1], treeview.get_column.return_value)
            self.assertTrue(args[2])
            treeview.get_column.assert_called_once_with(1)

    def test_tab_at_last_editable_column_moves_to_next_row_first_column(self):
        with mock_gtk():
            import gui_helpers as gh
            gh.Gdk.KEY_Tab = 1
            gh.Gdk.KEY_ISO_Left_Tab = 2

            widget, treeview, model, event = self._setup(
                gh, 1, "0", 2, [0, 1, 2], has_next=True)

            result = gh.handle_editing_key_press(
                widget, event, treeview, "0", 2, [0, 1, 2])

            self.assertTrue(result)
            model.iter_next.assert_called_once()
            treeview.set_cursor.assert_called_once()
            args = treeview.set_cursor.call_args[0]
            self.assertEqual(args[0]._indices, [1])
            treeview.get_column.assert_called_once_with(0)

    def test_tab_at_last_column_last_row_does_not_advance(self):
        with mock_gtk():
            import gui_helpers as gh
            gh.Gdk.KEY_Tab = 1
            gh.Gdk.KEY_ISO_Left_Tab = 2

            widget, treeview, model, event = self._setup(
                gh, 1, "0", 2, [0, 1, 2], has_next=False)

            result = gh.handle_editing_key_press(
                widget, event, treeview, "0", 2, [0, 1, 2])

            self.assertTrue(result)
            widget.editing_done.assert_called_once()
            widget.remove_widget.assert_called_once()
            treeview.set_cursor.assert_not_called()

    def test_shift_tab_moves_to_previous_editable_column(self):
        with mock_gtk():
            import gui_helpers as gh
            gh.Gdk.KEY_Tab = 1
            gh.Gdk.KEY_ISO_Left_Tab = 2

            widget, treeview, _model, event = self._setup(
                gh, 2, "0", 1, [0, 1, 2])

            result = gh.handle_editing_key_press(
                widget, event, treeview, "0", 1, [0, 1, 2])

            self.assertTrue(result)
            widget.editing_done.assert_called_once()
            widget.remove_widget.assert_called_once()
            treeview.set_cursor.assert_called_once()
            args = treeview.set_cursor.call_args[0]
            self.assertEqual(args[0]._indices, [0])
            treeview.get_column.assert_called_once_with(0)

    def test_shift_tab_at_first_editable_column_moves_to_previous_row_last(self):
        with mock_gtk():
            import gui_helpers as gh
            gh.Gdk.KEY_Tab = 1
            gh.Gdk.KEY_ISO_Left_Tab = 2

            widget, treeview, _model, event = self._setup(
                gh, 2, "1", 0, [0, 1, 2])

            result = gh.handle_editing_key_press(
                widget, event, treeview, "1", 0, [0, 1, 2])

            self.assertTrue(result)
            treeview.set_cursor.assert_called_once()
            args = treeview.set_cursor.call_args[0]
            self.assertEqual(args[0]._indices, [0])
            treeview.get_column.assert_called_once_with(2)

    def test_shift_tab_at_first_row_first_column_does_not_advance(self):
        with mock_gtk():
            import gui_helpers as gh
            gh.Gdk.KEY_Tab = 1
            gh.Gdk.KEY_ISO_Left_Tab = 2

            widget, treeview, _model, event = self._setup(
                gh, 2, "0", 0, [0, 1, 2])

            result = gh.handle_editing_key_press(
                widget, event, treeview, "0", 0, [0, 1, 2])

            self.assertTrue(result)
            widget.editing_done.assert_called_once()
            widget.remove_widget.assert_called_once()
            treeview.set_cursor.assert_not_called()

    def test_unhandled_key_returns_false(self):
        with mock_gtk():
            import gui_helpers as gh
            gh.Gdk.KEY_Tab = 1
            gh.Gdk.KEY_ISO_Left_Tab = 2

            widget = MagicMock()
            treeview = MagicMock()
            event = self._make_event(99)

            result = gh.handle_editing_key_press(
                widget, event, treeview, "0", 0, [0, 1, 2])

            self.assertFalse(result)
            widget.editing_done.assert_not_called()
            widget.remove_widget.assert_not_called()
