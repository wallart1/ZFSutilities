#!/usr/bin/env python3
"""
ZFS Utilities GUI - Main Application

A GTK3 frontend for ZFS backup, snapshot, and retention operations.
"""

import gi
import os
import sys
import threading

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib

# Ensure the script's own directory is on sys.path for sibling imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from logging_config import log_msg, set_log_sink
from config_core import (
    CONFIG_PATH, load_config,
    get_ui_state, save_ui_state,
    get_docs_editor, save_docs_editor,
)
from feature_config import get_pools, get_checkagainst
from dashboard_page import (
    create_dashboard_page, refresh_dashboard_page,
    _get_peer_host, _get_host_version, _log_peer_version_result,
)
from backup_page import create_backup_page
from backup_runner import BackupRunner
from offsite_page import create_offsite_page, do_detect_offsite_pool
from restore_page import create_restore_page
from pools_page import create_pools_page, refresh_pools_page
from datasets_page import create_datasets_page, refresh_datasets_page
from retention_page import create_retention_page, refresh_prune_pools
from checkagainst_page import create_checkagainst_page
from schedule_page import create_schedule_page
from logs_page import create_logs_page
from action_dispatch import PAGE_SPECS, ACTION_HANDLERS
from gui_helpers import (
    create_menu_bar, create_info_panel, UIStateManager,
    confirm_and_minimize_width,
)
from docs_viewer import DocsViewerWindow
from runner_factory import RunnerFactory
from app_context import AppContext

def _detect_parent_dir(script_dir):
    """Auto-detect the directory containing bash scripts.

    In production, scripts live in version_root/bin/.  In development,
    they live in version_root/ (the repo root, parent of 07 GTK + Python/).
    """
    version_root = os.path.dirname(script_dir)
    bin_dir = os.path.join(version_root, "bin")
    if os.path.isfile(os.path.join(bin_dir, "zfsdailybackup")):
        return bin_dir
    return version_root


class ZFSUtilitiesWindow(Gtk.ApplicationWindow):
    """Main application window."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(1000, 700)
        self.set_title("ZFS Utilities")

        # Load persistent config (detect fresh installs so the Retention tab
        # can clear pool-specific policies that come from legacy sample files).
        config_existed = os.path.exists(CONFIG_PATH)
        self.config = load_config()

        # Script path resolution — auto-detect production vs development layout
        # Use realpath to resolve symlinks (e.g. Desktop launcher link).
        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        self.parent_dir = _detect_parent_dir(self.script_dir)

        # Cross-cutting operational state shared with pages and handlers
        self.ctx = AppContext(
            config=self.config,
            script_dir=self.script_dir,
            parent_dir=self.parent_dir,
            version="dev",
            is_new_install=not config_existed,
        )

        # Backup runner (initialized after info panel exists)
        self.backup_runner = None

        # Pop-out log window (created in create_info_panel)
        self.popout_window = None

        # Pool watch windows (pool_name -> PoolWatchWindow)
        self._watch_windows = {}

        # Documentation viewer window
        self._docs_window = None

        # Cache version at startup so About dialog reflects the code actually running.
        # When running from the repo, read VERSION from the repo root (next to
        # the '07 GTK + Python/' directory).  Otherwise fall back to the deployed
        # version symlink.
        repo_version_path = os.path.join(os.path.dirname(self.script_dir), "VERSION")
        deployed_version_path = "/usr/local/lib/zfsutilities/current/VERSION"
        if os.path.exists(repo_version_path):
            with open(repo_version_path) as f:
                self.ctx.version = f.read().strip()
        elif os.path.exists(deployed_version_path):
            with open(deployed_version_path) as f:
                self.ctx.version = f.read().strip()
        self._version = self.ctx.version

        # Main vertical layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.main_box)

        # --- Menu Bar ---
        create_menu_bar(self)

        # --- Main Content Area (sidebar + content + actions) ---
        self.vpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.main_box.pack_start(self.vpaned, True, True, 0)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.vpaned.pack1(self.content_box, resize=True, shrink=False)

        self._ui_state = UIStateManager(self, self.config)

        self.create_sidebar_and_stack()
        self.create_action_panel()

        # --- Bottom: Info Panel ---
        create_info_panel(self)

        # Create runners after the info panel exists so log/stdin callbacks
        # and widgets are already available.
        runner_factory = RunnerFactory(
            self.log_message, self._set_stdin_enabled, self._update_progress
        )
        self.backup_runner = runner_factory.create("Backup")
        self.offsite_runner = runner_factory.create("Offsite backup")
        self.restore_runner = runner_factory.create("Restore")
        self.retention_runner = runner_factory.create("Prune")
        self.dataset_runner = runner_factory.create("Dataset action")

        self._ui_state.restore()

        self.connect("configure-event", self._ui_state.on_configure)
        self.connect("window-state-event", self._ui_state.on_window_state_event)
        self.vpaned.connect("notify::position", self._ui_state.on_vpaned_changed)
        self.connect("destroy", self._on_main_destroy)

    def create_sidebar_and_stack(self):
        """Create the sidebar navigation and content stack."""
        # Stack holds the different pages
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)
        self.stack.set_transition_duration(200)

        # Sidebar shows tabs for the stack
        self.sidebar = Gtk.StackSidebar()
        self.sidebar.set_stack(self.stack)
        self.sidebar.set_size_request(150, -1)

        # Add sidebar to content area
        sidebar_frame = Gtk.Frame()
        sidebar_frame.add(self.sidebar)
        self.content_box.pack_start(sidebar_frame, False, False, 0)

        # Add stack to content area (expands to fill)
        stack_frame = Gtk.Frame()
        stack_frame.set_shadow_type(Gtk.ShadowType.IN)
        stack_frame.add(self.stack)
        self.content_box.pack_start(stack_frame, True, True, 5)

        # --- Add pages to the stack ---
        self.add_stack_page("dashboard", "Dashboard", create_dashboard_page(self))
        self.add_stack_page("backup", "Backup", create_backup_page(self, self.ctx))
        self.add_stack_page("offsite", "Offsite", create_offsite_page(self, self.ctx))
        self.add_stack_page("restore", "Restore", create_restore_page(self, self.ctx))
        self.add_stack_page("schedule", "Schedule", create_schedule_page(self))
        self.add_stack_page("checkagainst", "Checkagainst", create_checkagainst_page(self))
        self.add_stack_page("pools", "Pools", create_pools_page(self))
        self.add_stack_page("datasets", "Datasets", create_datasets_page(self))
        self.add_stack_page("retention", "Retention", create_retention_page(self, self.ctx))
        self.add_stack_page("logs", "Logs", create_logs_page(self))

        # Connect to stack page changes to update action panel
        self.stack.connect("notify::visible-child-name", self.on_page_changed)

    def add_stack_page(self, name, title, widget):
        """Add a page to the stack."""
        self.stack.add_titled(widget, name, title)

    def create_action_panel(self):
        """Create the context action buttons panel on the right."""
        self.action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.action_box.set_margin_top(10)
        self.action_box.set_margin_end(10)
        self.action_box.set_margin_bottom(10)
        self.action_box.set_size_request(120, -1)

        action_frame = Gtk.Frame(label="Actions")
        action_frame.add(self.action_box)
        self.content_box.pack_start(action_frame, False, False, 0)

        # Default actions (will be updated based on selected page)
        self.update_action_buttons("dashboard")

    def update_action_buttons(self, page_name):
        """Update action buttons based on the current page."""
        # Ignore stale rebuild requests from asynchronous runner/profile
        # completion callbacks when the user has already switched to another tab.
        current = self.stack.get_visible_child_name() if self.stack else None
        if current != page_name:
            return

        for child in self.action_box.get_children():
            self.action_box.remove(child)

        spec = PAGE_SPECS.get(page_name)
        if not spec:
            self.action_box.show_all()
            return

        runner_name = spec.get("runner")
        if runner_name:
            runner = getattr(self, runner_name, None)
            if runner and runner.running:
                label, icon = spec.get("cancel", ("Cancel", "process-stop"))
            else:
                label, icon = spec["run"]
            self.add_action_button(label, icon, self.on_action_clicked)

        if spec.get("dry_run"):
            self.add_dry_run_toggle()

        for label, icon, attr_name in spec["buttons"]:
            if label is None:
                # Spacer
                self.action_box.pack_start(Gtk.Separator(), False, False, 5)
                continue
            btn = self.add_action_button(label, icon, self.on_action_clicked)
            if attr_name:
                setattr(self, attr_name, btn)

        dirty_check = spec.get("dirty_check")
        dirty_attr = spec.get("dirty_attr")
        if dirty_check and dirty_attr and hasattr(self, dirty_attr):
            dirty_check(self)

        post_setup = spec.get("post_setup")
        if post_setup:
            post_setup(self)

        self.action_box.show_all()

    def add_dry_run_toggle(self):
        """Add a Dry Run toggle button to the action panel.

        Returns the toggle button widget. Looks like the other action buttons
        but stays pressed when active. Label text is red when active.
        """
        button = Gtk.ToggleButton()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.set_halign(Gtk.Align.CENTER)
        image = Gtk.Image.new_from_icon_name("document-preview", Gtk.IconSize.BUTTON)
        label = Gtk.Label(label="Dry Run")
        box.pack_start(image, False, False, 0)
        box.pack_start(label, False, False, 0)
        button.add(box)
        button.set_tooltip_text(
            "When enabled, operations are simulated without making changes."
        )
        # Restore previous state if set
        if hasattr(self, '_dry_run_active') and self._dry_run_active:
            button.set_active(True)
        self._update_dry_run_button_style(button, label)
        button.connect("toggled", self._on_dry_run_toggled, label)
        self.action_box.pack_start(button, False, False, 0)
        return button

    def _update_dry_run_button_style(self, button, label):
        """Set the Dry Run button label colour based on active state."""
        if button.get_active():
            label.set_markup("<span color='red'>Dry Run</span>")
        else:
            label.set_text("Dry Run")

    def _on_dry_run_toggled(self, button, label):
        """Persist the Dry Run toggle state and update label colour."""
        self._dry_run_active = button.get_active()
        self._update_dry_run_button_style(button, label)

    def add_action_button(self, label, icon_name, callback):
        """Add a button to the action panel. Returns the button widget."""
        button = Gtk.Button(label=label)
        button.set_image(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))
        button.set_always_show_image(True)
        button.connect("clicked", callback)
        self.action_box.pack_start(button, False, False, 0)
        return button

    def enable_treeview_copy(self, treeview):
        """Add right-click Copy to a TreeView."""
        from gui_helpers import enable_treeview_copy as _etc
        _etc(treeview, app=self, datasets_view=getattr(self, 'datasets_view', None))

    def _on_log_size_allocate(self, widget, allocation):
        """Scroll to bottom after every layout if auto-scroll is active."""
        if self._log_auto_scroll:
            vadj = self.log_scrolled.get_vadjustment()
            self._log_programmatic_scroll = True
            vadj.set_value(vadj.get_upper() - vadj.get_page_size())
            self._log_programmatic_scroll = False

    def _on_log_scroll_changed(self, adj):
        """Track whether the user has scrolled away from the bottom."""
        if self._log_programmatic_scroll:
            return
        # "At bottom" means within 50px of the maximum scroll position
        at_bottom = (adj.get_value() >= adj.get_upper() - adj.get_page_size() - 50)
        self._log_auto_scroll = at_bottom

    def log_message(self, message):
        """Add a message to the info panel, colorizing WARN/FATAL lines.

        All messages are stored; the main level selector controls which lines
        are visible in the panel.
        """
        if not hasattr(self, 'info_text'):
            return
        from datetime import datetime
        from logging_config import parse_msg_level
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stamped = f"{timestamp}  {message}"
        level = parse_msg_level(message)

        self._info_panel_lines.append((timestamp, level, message))

        # Always update the warning/error indicator so issues are flagged
        # even when the panel is filtered to a higher level.
        if level == "FATAL":
            self._update_log_status("FATAL")
        elif level == "WARN":
            self._update_log_status("WARN")

        self._insert_info_line(timestamp, level, message, stamped)

    def _insert_info_line(self, timestamp, level, message, stamped):
        """Insert a single line into the info panel if it passes the filter."""
        from logging_config import viewer_should_show
        if not viewer_should_show(level, self._info_panel_level):
            return
        buffer = self.info_text.get_buffer()
        end_iter = buffer.get_end_iter()
        start_mark = buffer.create_mark(None, end_iter, True)
        buffer.insert(end_iter, stamped + "\n")

        tag_name = None
        if level == "FATAL":
            tag_name = "fatal"
        elif level == "WARN":
            tag_name = "warn"

        if tag_name:
            tag_table = buffer.get_tag_table()
            if not tag_table.lookup(tag_name):
                if tag_name == "fatal":
                    buffer.create_tag("fatal", foreground="#CC0000")
                else:
                    buffer.create_tag("warn", foreground="#FF8C00")
            end_iter = buffer.get_end_iter()
            buffer.apply_tag_by_name(
                tag_name,
                buffer.get_iter_at_mark(start_mark),
                end_iter,
            )
        buffer.delete_mark(start_mark)

    def _render_info_panel(self):
        """Re-render the info panel from stored lines at the current level."""
        from logging_config import viewer_should_show
        buffer = self.info_text.get_buffer()
        vadj = self.log_scrolled.get_vadjustment()
        old_value = vadj.get_value()
        old_upper = vadj.get_upper()

        buffer.set_text("")
        for timestamp, level, message in self._info_panel_lines:
            if viewer_should_show(level, self._info_panel_level):
                stamped = f"{timestamp}  {message}"
                self._insert_info_line(timestamp, level, message, stamped)

        # Preserve scroll position relative to the new content.
        def _restore_scroll():
            new_upper = vadj.get_upper()
            new_page = vadj.get_page_size()
            if old_upper > new_page:
                ratio = old_value / (old_upper - new_page)
            else:
                ratio = 0.0
            target = ratio * max(0, new_upper - new_page)
            vadj.set_value(min(target, new_upper - new_page))
            return False
        GLib.idle_add(_restore_scroll)

    def clear_log_status(self):
        """Reset the log warning/error indicator."""
        self._log_status_level = None
        if hasattr(self, 'log_status_label'):
            self.log_status_label.set_markup("")
        if hasattr(self, 'log_status_event_box'):
            self.log_status_event_box.hide()

    def _update_log_status(self, level):
        """Update the log status indicator if the new level is more severe."""
        severity = {"WARN": 1, "FATAL": 2}
        current = severity.get(getattr(self, '_log_status_level', None), 0)
        new = severity.get(level, 0)
        if new <= current:
            return
        self._log_status_level = level
        if not hasattr(self, 'log_status_label'):
            return
        if level == "FATAL":
            self.log_status_label.set_markup(
                "<span foreground='#CC0000' weight='bold'>✗ Error</span>"
            )
        elif level == "WARN":
            self.log_status_label.set_markup(
                "<span foreground='#FF8C00' weight='bold'>⚠ Warning</span>"
            )
        if hasattr(self, 'log_status_event_box'):
            self.log_status_event_box.show()

    def _update_progress(self, fraction, text):
        """Update or hide the status label.

        Args:
            fraction: 0.0-1.0, or None to hide the status label.
            text: status string for the status label.
        """
        if not hasattr(self, 'status_label'):
            return
        if fraction is None:
            self.status_label.set_text("")
            self.status_label.hide()
            return
        if text:
            self.status_label.set_text(text)
        self.status_label.show()

    def _check_startup_config(self):
        """Log warnings for missing configuration and check peer version."""
        warnings = []
        if not get_pools(self.config):
            warnings.append("No pools registered — add pools in the Pools tab")
        backup = self.config.get("backup", {})
        if not backup.get("pull_steps") and not backup.get("send_receive_steps"):
            warnings.append("No backup steps configured — configure in the Backup tab")
        offsite = self.config.get("offsite", {})
        if not offsite.get("steps"):
            warnings.append("No offsite steps configured — configure in the Offsite tab")
        if not get_checkagainst(self.config):
            warnings.append("Checkagainst table is empty — configure in the Checkagainst tab")
        for w in warnings:
            log_msg(f"WARN: {w}")

        self._check_peer_version_async()

    def _check_peer_version_async(self):
        """In two-node mode, asynchronously verify the peer's version.

        The SSH check is run in a background thread so GUI startup is not
        delayed.  The result is logged on the main thread via GLib.idle_add.
        """
        peer_host = _get_peer_host()
        if not peer_host:
            return

        local_version = self._version

        def _fetch_and_log():
            peer_version = _get_host_version(peer_host)
            GLib.idle_add(
                _log_peer_version_result, local_version, peer_host, peer_version
            )

        threading.Thread(target=_fetch_and_log, daemon=True).start()

    # --- Page Creation Methods ---
    # These create placeholder content for each tab

    # --- Signal Handlers ---

    def on_page_changed(self, stack, param):
        """Handle page changes in the stack."""
        page_name = stack.get_visible_child_name()
        if page_name:
            self.update_action_buttons(page_name)
            if page_name == "retention":
                refresh_prune_pools(self)
            elif page_name == "offsite":
                do_detect_offsite_pool(self)
            elif page_name == "restore":
                from restore_page import refresh_restore_destination
                refresh_restore_destination(self)
            self._start_stop_dashboard_timer(page_name)
            self._start_stop_scrub_timer(page_name)
            log_msg(f"VERB: Switched to: {page_name.title()}")

    def _start_stop_dashboard_timer(self, page_name):
        """Start the dashboard auto-refresh timer when on Dashboard, stop otherwise."""
        if getattr(self, '_dashboard_timer', None) is not None:
            GLib.source_remove(self._dashboard_timer)
            self._dashboard_timer = None
        if getattr(self, '_scrub_timer', None) is not None:
            GLib.source_remove(self._scrub_timer)
            self._scrub_timer = None
        if page_name == "dashboard":
            self._dashboard_timer = GLib.timeout_add_seconds(
                30, self._on_dashboard_timer_tick
            )

    def _start_stop_scrub_timer(self, page_name):
        """Start the scrub refresh timer when on Pools, stop otherwise."""
        if getattr(self, '_scrub_timer', None) is not None:
            GLib.source_remove(self._scrub_timer)
            self._scrub_timer = None
        if page_name == "pools":
            # Do an immediate refresh
            from pools_page import refresh_scrub_table
            refresh_scrub_table(self)
            interval = getattr(self, '_scrub_ref_spin', None)
            seconds = int(interval.get_value()) if interval else 10
            self._scrub_timer = GLib.timeout_add_seconds(
                max(1, seconds), self._on_scrub_timer_tick
            )

    def _on_scrub_timer_tick(self):
        """Callback for scrub auto-refresh. Returns True to keep timer alive."""
        if self.stack.get_visible_child_name() == "pools":
            from pools_page import refresh_scrub_table
            refresh_scrub_table(self)
        return True

    def _on_dashboard_timer_tick(self):
        """Callback for dashboard auto-refresh. Returns True to keep timer alive."""
        if self.stack.get_visible_child_name() == "dashboard":
            refresh_dashboard_page(self)
        return True

    def _on_main_destroy(self, _widget):
        """Clean up pop-out window and log timers when main window closes."""
        if self.popout_window is not None:
            self.popout_window.destroy()
            self.popout_window = None
        if getattr(self, '_logs_refresh_timer', None) is not None:
            GLib.source_remove(self._logs_refresh_timer)
            self._logs_refresh_timer = None
        if getattr(self, '_logs_tail_timer', None) is not None:
            GLib.source_remove(self._logs_tail_timer)
            self._logs_tail_timer = None
        if getattr(self, '_dashboard_timer', None) is not None:
            GLib.source_remove(self._dashboard_timer)
            self._dashboard_timer = None

    def on_quit(self, widget):
        """Handle quit menu item."""
        self.get_application().quit()

    def on_minimize_width(self, _widget):
        """Reset resizable columns to minimum width and shrink the window."""
        confirm_and_minimize_width(self)

    def on_about(self, widget):
        """Show about dialog."""
        dialog = Gtk.AboutDialog(transient_for=self)
        dialog.set_program_name("ZFS Utilities")
        dialog.set_version(self._version)
        dialog.set_comments("A GTK frontend for ZFS backup and snapshot management")
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.run()
        dialog.destroy()

    def on_set_docs_editor(self, widget):
        """Show a dialog to configure the external markdown editor."""
        dialog = Gtk.Dialog(
            title="Set Documentation Editor",
            transient_for=self,
            flags=0,
        )
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_default_size(400, -1)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_bottom(10)

        label = Gtk.Label(
            label="Command to open markdown files:\n"
                  "(Leave blank to use the system default editor)"
        )
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        entry = Gtk.Entry()
        entry.set_width_chars(1)
        entry.set_text(get_docs_editor(self.config))
        entry.set_placeholder_text("e.g.  marktext  or  xdg-open")
        box.pack_start(entry, False, False, 0)

        box.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            command = entry.get_text().strip()
            save_docs_editor(self.config, command)
            log_msg(f"INFO: Documentation editor set to: {command or '(system default)'}")
        dialog.destroy()

    _PAGE_ANCHORS = {
        "dashboard": "dashboard-tab",
        "backup": "backup-tab",
        "offsite": "offsite-tab",
        "restore": "restore-tab",
        "schedule": "schedule-tab",
        "checkagainst": "checkagainst-tab",
        "pools": "pools-tab",
        "datasets": "datasets-tab",
        "retention": "retention-tab",
        "logs": "logs-tab",
    }

    def on_documentation(self, widget):
        """Open or raise the embedded documentation viewer."""
        if self._docs_window is None:
            self._docs_window = DocsViewerWindow(self.script_dir, self.config)
            self._docs_window.connect("destroy", self._on_docs_window_destroyed)
        self._docs_window.present()

    def on_help_with_page(self, widget):
        """Open the documentation viewer scrolled to the current page's section."""
        page = self.stack.get_visible_child_name()
        anchor = self._PAGE_ANCHORS.get(page)
        if not anchor:
            log_msg(f"WARN: No documentation anchor for page '{page}'")
            return
        if self._docs_window is None:
            self._docs_window = DocsViewerWindow(self.script_dir, self.config)
            self._docs_window.connect("destroy", self._on_docs_window_destroyed)
        self._docs_window.navigate_to_anchor(anchor)

    def _on_docs_window_destroyed(self, widget):
        """Reset reference when docs window is closed."""
        self._docs_window = None

    def on_refresh(self, widget):
        """Handle refresh button."""
        page = self.stack.get_visible_child_name()
        if page == "pools":
            refresh_pools_page(self)
            log_msg("INFO: Pool data refreshed")
        elif page == "datasets":
            refresh_datasets_page(self)
            log_msg("INFO: Datasets refreshed")
        else:
            log_msg("INFO: Refreshing...")

    def on_action_clicked(self, widget):
        """Handle action button clicks via two-level dispatch table."""
        label = widget.get_label()
        page = self.stack.get_visible_child_name()
        handler = ACTION_HANDLERS.get(page, {}).get(label)
        if handler:
            handler(self)
        else:
            log_msg(f"VERB: Action: {label}")

    # --- Stdin helpers ---

    def _on_log_level_toggled(self, item, level):
        """Update the main info-panel filter when the level menu changes."""
        if item.get_active():
            self.log_level_button.set_label(level)
            self._info_panel_level = level
            self._render_info_panel()

    def _set_stdin_enabled(self, enabled):
        """Enable or disable the stdin entry and send button."""
        self.stdin_entry.set_sensitive(enabled)
        self.stdin_send_btn.set_sensitive(enabled)
        if enabled:
            self.stdin_entry.grab_focus()

    def _on_stdin_activate(self, entry):
        """Handle Enter key in the stdin entry."""
        self._send_stdin_text()

    def _on_stdin_send(self, button):
        """Handle Send button click."""
        self._send_stdin_text()

    def _send_stdin_text(self):
        """Send entry text to the running subprocess."""
        text = self.stdin_entry.get_text()
        self.stdin_entry.set_text("")
        # Send to whichever runner is active
        runner = None
        if self.backup_runner and self.backup_runner.running:
            runner = self.backup_runner
        elif self.offsite_runner and self.offsite_runner.running:
            runner = self.offsite_runner
        elif self.restore_runner and self.restore_runner.running:
            runner = self.restore_runner
        elif self.retention_runner and self.retention_runner.running:
            runner = self.retention_runner
        elif self.dataset_runner and self.dataset_runner.running:
            runner = self.dataset_runner
        if runner:
            log_msg(f"VERB: > {text}")
            runner.send_input(text)

if __name__ == "__main__":
    from main import main
    main()
