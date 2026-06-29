#!/usr/bin/env python3
"""Embedded documentation viewer using WebKit2."""

import functools
import os
import pwd
import shlex
import shutil
import socket
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib

try:
    gi.require_version('WebKit2', '4.1')
    from gi.repository import WebKit2
    _WEBKIT_AVAILABLE = True
except (ValueError, ImportError):
    _WEBKIT_AVAILABLE = False

from backup_config import (
    get_docs_editor, load_config, log_msg,
    get_ui_state, save_ui_state,
)

# URI schemes the viewer is allowed to navigate to.
_ALLOWED_SCHEMES = ("file:", "http:", "https:", "about:")


class _DocsServer:
    """Tiny static-file server for the built documentation directory.

    Serves from 127.0.0.1 on an ephemeral port so that WebKit can load the
    docs with a real http:// origin, which allows MkDocs Material search
    (Web Worker + fetch) to function correctly.
    """

    def __init__(self, docs_dir):
        self.docs_dir = os.path.abspath(docs_dir)
        self.port = None
        self._httpd = None
        self._thread = None

    def start(self):
        """Start the server and return the base http:// URI."""
        self.port = self._find_free_port()
        handler = functools.partial(
            _DocsRequestHandler, directory=self.docs_dir
        )
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True
        )
        self._thread.start()
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        """Shut down the server and release the port."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._thread = None

    @staticmethod
    def _find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]


class _DocsRequestHandler(SimpleHTTPRequestHandler):
    """Static file handler anchored to a single directory."""

    def __init__(self, *args, directory=None, **kwargs):
        self._docs_directory = directory
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format, *args):
        # Suppress routine HTTP access logs
        pass


def resolve_docs_path(script_dir):
    """Return the path to the built documentation index.html.

    Tries development layout first (repo root), then deployed layout.
    """
    candidates = []

    # Development / deployed via parent directory
    version_root = os.path.dirname(script_dir)
    candidates.append(os.path.join(version_root, "06 Docs", "site", "index.html"))

    # Explicit deployed path (symlink-resolved)
    candidates.append(
        "/usr/local/lib/zfsutilities/current/06 Docs/site/index.html"
    )

    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


def _get_desktop_user():
    """Return the username of the desktop session owner, or None."""
    # Method 1: SUDO_USER
    user = os.environ.get("SUDO_USER")
    if user:
        return user

    # Method 2: PKEXEC_UID
    pkexec_uid = os.environ.get("PKEXEC_UID")
    if pkexec_uid:
        try:
            return pwd.getpwuid(int(pkexec_uid)).pw_name
        except (ValueError, KeyError):
            pass

    # Method 3: Owner of XAUTHORITY
    xauth = os.environ.get("XAUTHORITY")
    if xauth and os.path.exists(xauth):
        try:
            uid = os.stat(xauth).st_uid
            if uid != 0:
                return pwd.getpwuid(uid).pw_name
        except (KeyError, OSError):
            pass

    # Method 4: Owner of the X11 socket
    display = os.environ.get("DISPLAY", ":0")
    display_num = display.split(".")[0].lstrip(":")
    x11_sock = f"/tmp/.X11-unix/X{display_num}"
    if os.path.exists(x11_sock):
        try:
            uid = os.stat(x11_sock).st_uid
            if uid != 0:
                return pwd.getpwuid(uid).pw_name
        except (KeyError, OSError):
            pass

    return None


class DocsViewerWindow(Gtk.Window):
    """A standalone window that displays the MkDocs documentation site."""

    def __init__(self, script_dir, config=None):
        super().__init__(title="ZFS Utilities Documentation")
        self.set_default_size(900, 700)

        self._script_dir = script_dir
        self._docs_path = resolve_docs_path(script_dir)
        self._config = config if config is not None else load_config()
        self._docs_state = self._load_state()
        self._restore_geometry()

        if not _WEBKIT_AVAILABLE:
            self._show_fallback("WebKit2 is not available on this system.")
            return

        if not self._docs_path:
            self._show_fallback(
                "Documentation site not found.\n\n"
                "Expected one of:\n"
                "  <repo>/06 Docs/site/index.html\n"
                "  /usr/local/lib/zfsutilities/current/06 Docs/site/index.html\n\n"
                "Run 'mkdocs build' in the 06 Docs directory."
            )
            return

        self._build_ui()

    def _on_destroy(self, _window):
        """Flush pending state and stop the embedded docs server."""
        self._stop_theme_timer()
        self._flush_save()
        if hasattr(self, "_docs_server") and self._docs_server is not None:
            self._docs_server.stop()
            self._docs_server = None

    # --- State persistence ---------------------------------------------------

    def _load_state(self):
        """Load saved docs-viewer state, or return defaults."""
        return get_ui_state(self._config).get("docs_viewer", {})

    def _restore_geometry(self):
        """Restore size, position, and maximized state from saved config."""
        state = self._docs_state
        self._maximized = bool(state.get("maximized"))
        if self._maximized:
            self.maximize()
            return
        width = state.get("width")
        height = state.get("height")
        if width and height:
            self.resize(width, height)
            self._width = width
            self._height = height
        x = state.get("x")
        y = state.get("y")
        if x is not None and y is not None:
            self.move(x, y)
            self._x = x
            self._y = y

    def _schedule_save(self):
        """Debounce geometry/zoom saves so resize drags don't hammer disk."""
        if self._config is None:
            return
        if hasattr(self, "_save_timer") and self._save_timer is not None:
            GLib.source_remove(self._save_timer)
        self._save_timer = GLib.timeout_add(500, self._do_save)

    def _flush_save(self):
        """Write pending state immediately."""
        if hasattr(self, "_save_timer") and self._save_timer is not None:
            GLib.source_remove(self._save_timer)
            self._save_timer = None
        self._do_save()

    def _do_save(self):
        """Persist current geometry, zoom, and theme."""
        self._save_timer = None
        if self._config is None:
            return False
        state = {"docs_viewer": {"zoom": self._zoom_level, "theme": self._theme}}
        ds = state["docs_viewer"]
        maximized = getattr(self, "_maximized", False)
        ds["maximized"] = maximized
        if not maximized:
            width = self.__dict__.get("_width")
            height = self.__dict__.get("_height")
            x = self.__dict__.get("_x")
            y = self.__dict__.get("_y")
            if width is None or height is None:
                width, height = self.get_size()
            if x is None or y is None:
                x, y = self.get_position()
            ds["width"] = width
            ds["height"] = height
            ds["x"] = x
            ds["y"] = y
        save_ui_state(self._config, state)
        return False

    def _on_configure(self, _window, event):
        """Cache the latest configure-event geometry and schedule a save."""
        self._width = event.width
        self._height = event.height
        self._x = event.x
        self._y = event.y
        self._schedule_save()
        return False

    def _on_window_state_event(self, _window, event):
        """Cache the latest maximized state and schedule a save."""
        self._maximized = bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)
        self._schedule_save()
        return False

    def _apply_theme(self, scheme):
        """Apply the given MkDocs Material color scheme to the current page.

        Sets the matching palette radio (which drives the icon via CSS), the
        body data attributes (which drive the color scheme), and the same
        localStorage entry the Material runtime uses so future loads of this
        page start with the correct theme.
        """
        if not hasattr(self, "_webview"):
            return
        scheme = scheme or "default"
        scheme_json = self._js_string(scheme)
        js = (
            "(function(){ "
            "var scheme = " + scheme_json + "; "
            "var inputs = document.querySelectorAll("
            "'input[type=\\\"radio\\\"][name=\\\"__palette\\\"]'); "
            "var chosen = null, chosenIdx = -1; "
            "for (var i = 0; i < inputs.length; i++) { "
            "if (inputs[i].getAttribute('data-md-color-scheme') === scheme) { "
            "chosen = inputs[i]; chosenIdx = i; break; "
            "} "
            "} "
            "if (chosen) { "
            "var scope = new URL('.', location).pathname; "
            "var color = { "
            "media: chosen.getAttribute('data-md-color-media') || '', "
            "scheme: scheme, "
            "primary: chosen.getAttribute('data-md-color-primary') || '', "
            "accent: chosen.getAttribute('data-md-color-accent') || '' "
            "}; "
            "try { "
            "localStorage.setItem(scope + '.__palette', "
            "JSON.stringify({index: chosenIdx, color: color})); "
            "} catch (e) {} "
            "if (!chosen.checked) { "
            "chosen.checked = true; "
            "chosen.dispatchEvent(new Event('change', {bubbles: true})); "
            "} "
            "var primary = chosen.getAttribute('data-md-color-primary'); "
            "var accent = chosen.getAttribute('data-md-color-accent'); "
            "if (primary) document.body.setAttribute('data-md-color-primary', primary); "
            "if (accent) document.body.setAttribute('data-md-color-accent', accent); "
            "} "
            "document.body.setAttribute('data-md-color-scheme', scheme); "
            "})()"
        )
        self._webview.run_javascript(js, None, None, None)

    def _preload_theme(self, uri):
        """Seed localStorage for the target URI before it loads.

        MkDocs Material stores the palette per-directory in localStorage. By
        writing the entry for the upcoming page from the current document, the
        inline script on the next page sets the correct body attributes before
        rendering, avoiding a light-mode flash when the saved theme is dark.
        """
        if not hasattr(self, "_webview"):
            return
        scheme = getattr(self, "_theme", "default") or "default"
        scheme_json = self._js_string(scheme)
        uri_json = self._js_string(uri)
        js = (
            "(function(uri, scheme){ "
            "var inputs = document.querySelectorAll("
            "'input[type=\\\"radio\\\"][name=\\\"__palette\\\"]'); "
            "for (var i = 0; i < inputs.length; i++) { "
            "if (inputs[i].getAttribute('data-md-color-scheme') === scheme) { "
            "var scope = new URL('.', uri).pathname; "
            "var color = { "
            "media: inputs[i].getAttribute('data-md-color-media') || '', "
            "scheme: scheme, "
            "primary: inputs[i].getAttribute('data-md-color-primary') || '', "
            "accent: inputs[i].getAttribute('data-md-color-accent') || '' "
            "}; "
            "try { "
            "localStorage.setItem(scope + '.__palette', "
            "JSON.stringify({index: i, color: color})); "
            "} catch (e) {} "
            "return; "
            "} "
            "} "
            "})(" + uri_json + ", " + scheme_json + ")"
        )
        self._webview.run_javascript(js, None, None, None)

    @staticmethod
    def _js_string(value):
        """Return a JSON-encoded string safe to embed in generated JavaScript."""
        import json
        return json.dumps(value)

    def _capture_theme(self):
        """Read the active Material color scheme from the page.

        Runs asynchronously; the result is handled by _on_theme_captured().
        Returning True keeps the periodic timer alive.
        """
        if not hasattr(self, "_webview"):
            return True
        js = (
            "(function(){ "
            "var inputs = document.querySelectorAll("
            "'input[type=\\\"radio\\\"][name=\\\"__palette\\\"]'); "
            "for (var i = 0; i < inputs.length; i++) { "
            "if (inputs[i].checked) { "
            "return inputs[i].getAttribute('data-md-color-scheme') || 'default'; "
            "} "
            "} "
            "return document.body.getAttribute('data-md-color-scheme') || 'default'; "
            "})()"
        )
        self._webview.run_javascript(js, None, self._on_theme_captured, None)
        return True

    def _on_theme_captured(self, _webview, result, _user_data=None):
        """Store the scheme reported by the page and persist it if it changed."""
        scheme = "default"
        try:
            js_result = self._webview.run_javascript_finish(result)
            value = js_result.get_js_value()
            scheme = value.to_string() or "default"
        except Exception:
            pass
        scheme = scheme.strip('"') or "default"
        self._set_theme(scheme)

    def _on_theme_script_message(self, _manager, js_result):
        """Handle a theme-change message posted by the page's palette toggle."""
        scheme = "default"
        try:
            value = js_result.get_js_value()
            scheme = value.to_string() or "default"
        except Exception:
            pass
        scheme = scheme.strip('"') or "default"
        self._set_theme(scheme)

    def _set_theme(self, scheme):
        """Persist the active color scheme when it differs from the saved one."""
        if getattr(self, "_theme", None) != scheme:
            self._theme = scheme
            self._do_save()

    @staticmethod
    def _theme_change_script_source():
        """Return JS that reports palette toggles back to the Python host."""
        return (
            "(function(){ "
            "document.addEventListener('change', function(e){ "
            "var target = e.target; "
            "if (target && target.name === '__palette' && target.type === 'radio') { "
            "var scheme = target.getAttribute('data-md-color-scheme') || 'default'; "
            "if (window.webkit && window.webkit.messageHandlers && "
            "window.webkit.messageHandlers.themeChanged) { "
            "window.webkit.messageHandlers.themeChanged.postMessage(scheme); "
            "} "
            "} "
            "}); "
            "})()"
        )

    def _start_theme_timer(self):
        """Poll the page theme so toggling via the page control is captured."""
        self._theme_timer = GLib.timeout_add(2000, self._capture_theme)

    def _reset_theme_timer(self):
        """Restart the capture timer so a freshly loaded page isn't polled too soon."""
        self._stop_theme_timer()
        self._start_theme_timer()

    def _stop_theme_timer(self):
        if hasattr(self, "_theme_timer") and self._theme_timer is not None:
            GLib.source_remove(self._theme_timer)
            self._theme_timer = None

    def _build_ui(self):
        """Assemble toolbar + webview."""
        self.connect("destroy", self._on_destroy)
        self.connect("configure-event", self._on_configure)
        self.connect("window-state-event", self._on_window_state_event)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        # --- Toolbar ---
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        toolbar.set_margin_top(5)
        toolbar.set_margin_start(5)
        toolbar.set_margin_end(5)
        toolbar.set_margin_bottom(5)

        self._btn_back = self._make_tool_button(
            "go-previous", "Go back", self._on_back
        )
        self._btn_forward = self._make_tool_button(
            "go-next", "Go forward", self._on_forward
        )
        self._btn_refresh = self._make_tool_button(
            "view-refresh", "Refresh page", self._on_refresh
        )
        self._btn_home = self._make_tool_button(
            "go-home", "Go to documentation home", self._on_home
        )

        toolbar.pack_start(self._btn_back, False, False, 0)
        toolbar.pack_start(self._btn_forward, False, False, 0)
        toolbar.pack_start(self._btn_refresh, False, False, 0)
        toolbar.pack_start(self._btn_home, False, False, 0)

        self._btn_zoom_in = self._make_tool_button(
            "zoom-in", "Zoom in (Ctrl++)", self._on_zoom_in
        )
        self._btn_zoom_out = self._make_tool_button(
            "zoom-out", "Zoom out (Ctrl+-)", self._on_zoom_out
        )
        self._btn_zoom_reset = self._make_tool_button(
            "zoom-original", "Reset zoom (Ctrl+0)", self._on_zoom_reset
        )

        toolbar.pack_start(self._btn_zoom_in, False, False, 0)
        toolbar.pack_start(self._btn_zoom_out, False, False, 0)
        toolbar.pack_start(self._btn_zoom_reset, False, False, 0)

        self._status_label = Gtk.Label()
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_no_show_all(True)
        toolbar.pack_start(self._status_label, False, False, 10)

        vbox.pack_start(toolbar, False, False, 0)

        # --- WebView ---
        user_content_manager = WebKit2.UserContentManager()
        user_content_manager.register_script_message_handler("themeChanged")
        user_content_manager.connect(
            "script-message-received::themeChanged", self._on_theme_script_message
        )

        self._webview = WebKit2.WebView.new_with_user_content_manager(
            user_content_manager
        )

        settings = self._webview.get_settings()
        settings.set_allow_file_access_from_file_urls(True)
        self._webview.set_settings(settings)

        capture_script = WebKit2.UserScript.new(
            self._theme_change_script_source(),
            WebKit2.UserContentInjectedFrames.ALL_FRAMES,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None,
        )
        user_content_manager.add_script(capture_script)

        self._webview.connect("decide-policy", self._on_decide_policy)
        self._webview.connect("load-changed", self._on_load_changed)
        self._webview.connect("load-failed", self._on_load_failed)
        self._start_theme_timer()

        self._page_loaded = False
        self._pending_anchor = None
        self._zoom_level = self._docs_state.get("zoom", 1.0)
        self._theme = self._docs_state.get("theme", "default")
        self._zoom_level = max(0.5, min(self._zoom_level, 3.0))
        self._webview.set_zoom_level(self._zoom_level)

        # Keyboard shortcuts for zoom
        accel_group = Gtk.AccelGroup()
        self.add_accel_group(accel_group)
        accel_group.connect(
            Gdk.KEY_plus, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE,
            lambda _ag, _acc, _key, _mod: self._on_zoom_in(None)
        )
        accel_group.connect(
            Gdk.KEY_minus, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE,
            lambda _ag, _acc, _key, _mod: self._on_zoom_out(None)
        )
        accel_group.connect(
            Gdk.KEY_0, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE,
            lambda _ag, _acc, _key, _mod: self._on_zoom_reset(None)
        )

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self._webview)
        vbox.pack_start(scrolled, True, True, 0)

        # Serve docs over a local HTTP origin so WebKit's search worker can run.
        self._docs_server = _DocsServer(os.path.dirname(self._docs_path))
        base_uri = self._docs_server.start()
        self._base_uri = base_uri

        self._home_uri = base_uri + "/index.html"
        self._gui_uri = base_uri + "/user-guide/gtk-gui/index.html"
        self._go_home()

        self.show_all()

    def _make_tool_button(self, icon_name, tooltip, callback):
        """Create a toolbar button with an icon."""
        btn = Gtk.Button()
        btn.set_image(
            Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        )
        btn.set_tooltip_text(tooltip)
        btn.connect("clicked", callback)
        return btn

    def _go_home(self):
        """Load the documentation home page."""
        self._webview.load_uri(self._home_uri)

    def _set_status(self, text):
        """Show a transient status message in the toolbar."""
        self._status_label.set_text(text)
        self._status_label.show()

    def _clear_status(self):
        """Hide the status message."""
        self._status_label.hide()

    def _update_nav_buttons(self):
        """Enable/disable Back and Forward based on history."""
        self._btn_back.set_sensitive(self._webview.can_go_back())
        self._btn_forward.set_sensitive(self._webview.can_go_forward())

    # --- Signal handlers ---

    def _on_decide_policy(self, webview, decision, decision_type):
        """Intercept navigation to rewrite directory links, open editors, and
        block unknown schemes."""
        if decision_type != WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            return False

        uri = decision.get_request().get_uri()

        # Rewrite file:// directory URLs to index.html (file:// lacks auto-index)
        if uri.startswith("file://"):
            # Split off any fragment so the path check works
            path_part, _, fragment = uri.partition("#")
            if path_part.endswith("/"):
                index_uri = path_part + "index.html"
                path = unquote(index_uri[7:])  # strip "file://" and decode %XX
                if os.path.isfile(path):
                    if fragment:
                        index_uri += "#" + fragment
                    decision.ignore()
                    webview.load_uri(index_uri)
                    return True

        # Handle openmd:// edit links
        if uri.startswith("openmd://"):
            path = unquote(uri[9:])  # strip "openmd://"
            self._launch_editor(path)
            decision.ignore()
            return True

        if not uri.startswith(_ALLOWED_SCHEMES):
            scheme = uri.split(":", 1)[0] if ":" in uri else "unknown"
            log_msg(f"WARN: Documentation viewer blocked {scheme} link: {uri}")
            self._set_status(f"Blocked external link ({scheme})")
            decision.ignore()
            return True

        self._clear_status()
        return False

    def _on_load_changed(self, webview, event):
        """Update navigation buttons as the page loads."""
        if event == WebKit2.LoadEvent.STARTED:
            self._page_loaded = False
            self._clear_status()
            uri = self._webview.get_uri() or ""
            base = getattr(self, "_base_uri", "")
            if base and uri.startswith(base):
                self._preload_theme(uri)
        elif event == WebKit2.LoadEvent.FINISHED:
            self._page_loaded = True
            self._update_nav_buttons()
            self._clear_status()
            self._apply_theme(self._theme)
            self._reset_theme_timer()
            pending = self._pending_anchor
            if pending:
                self._scroll_to_anchor(pending)
                self._pending_anchor = None

    def _on_load_failed(self, webview, event, failing_uri, error):
        """Show a friendly error with a way back home."""
        log_msg(f"WARN: Documentation viewer failed to load {failing_uri}: {error}")
        self._set_status("Failed to load page — click Home to reset")
        self._update_nav_buttons()
        return True

    def _on_back(self, button):
        """Navigate back in history."""
        if self._webview.can_go_back():
            self._webview.go_back()

    def _on_forward(self, button):
        """Navigate forward in history."""
        if self._webview.can_go_forward():
            self._webview.go_forward()

    def _on_refresh(self, button):
        """Reload the current page."""
        self._webview.reload()

    def _on_home(self, button):
        """Return to the documentation home page."""
        self._go_home()

    def _on_zoom_in(self, button):
        """Increase page zoom level."""
        self._zoom_level = min(self._zoom_level * 1.1, 3.0)
        self._webview.set_zoom_level(self._zoom_level)
        self._schedule_save()

    def _on_zoom_out(self, button):
        """Decrease page zoom level."""
        self._zoom_level = max(self._zoom_level / 1.1, 0.5)
        self._webview.set_zoom_level(self._zoom_level)
        self._schedule_save()

    def _on_zoom_reset(self, button):
        """Reset page zoom to 100%."""
        self._zoom_level = 1.0
        self._webview.set_zoom_level(self._zoom_level)
        self._schedule_save()

    def navigate_to_anchor(self, anchor):
        """Navigate to a specific anchor within the GTK GUI reference page.

        Creates the window if it doesn't exist, then loads the URI with
        the given anchor and presents the window.
        """
        anchor = anchor.lstrip("#")
        base = unquote(self._gui_uri.split("#")[0])
        current = self._webview.get_uri() or ""
        current_base = unquote(current.split("#")[0])

        if current_base == base and self._page_loaded:
            self._scroll_to_anchor(anchor)
        else:
            self._pending_anchor = anchor
            self._webview.load_uri(self._gui_uri)

        self.present()

    def _scroll_to_anchor(self, anchor):
        """Scroll the webview to the element with the given id."""
        js = f"var e=document.getElementById('{anchor}');if(e)e.scrollIntoView();"
        self._webview.run_javascript(js, None, None, None)

    def _launch_editor(self, path):
        """Open the given markdown file in the user's configured editor."""
        config = load_config()
        command = get_docs_editor(config)
        if command:
            parts = shlex.split(command)
            resolved = shutil.which(parts[0])
            if resolved:
                parts[0] = resolved
                cmd = parts + [path]
            else:
                # Not in PATH — let the shell resolve it
                cmd = ["/bin/sh", "-c", f"{command} {shlex.quote(path)}"]
        else:
            cmd = ["xdg-open", path]

        # If running as root, drop to the desktop user so Electron/GTK editors
        # don't crash inside their sandboxes.
        desktop_user = _get_desktop_user()
        if os.geteuid() == 0 and desktop_user:
            cmd = ["runuser", "-u", desktop_user, "--"] + cmd

        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log_msg(f"INFO: Launched editor for {path}: {' '.join(cmd)}")
            self._set_status(f"Editing: {os.path.basename(path)}")
        except Exception as exc:
            log_msg(f"WARN: Failed to launch editor: {exc}")
            self._set_status(f"Failed to open editor: {exc}")

    def _show_fallback(self, message):
        """Show a plain-text fallback when WebKit or docs are missing."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_bottom(20)

        label = Gtk.Label(label=message)
        label.set_halign(Gtk.Align.START)
        label.set_valign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        self.add(box)
        self.show_all()

        log_msg(f"WARN: Documentation viewer fallback: {message}")


def main():
    """Launch the standalone documentation viewer."""
    if os.geteuid() != 0:
        # Re-launch with pkexec, preserving the X11/Wayland display environment.
        display = os.environ.get('DISPLAY', ':0')
        xauthority = os.environ.get('XAUTHORITY', '')
        wayland = os.environ.get('WAYLAND_DISPLAY', '')
        cmd = [
            'pkexec', 'env',
            f'DISPLAY={display}',
        ]
        if xauthority:
            cmd.append(f'XAUTHORITY={xauthority}')
        if wayland:
            cmd.append(f'WAYLAND_DISPLAY={wayland}')
        cmd.append(sys.executable)
        cmd.extend(sys.argv)
        os.execvp('pkexec', cmd)

    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk

    script_dir = os.path.dirname(os.path.abspath(__file__))
    window = DocsViewerWindow(script_dir)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
