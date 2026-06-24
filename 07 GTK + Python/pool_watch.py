"""
PoolWatchWindow — independent per-pool dataset watch window with auto-refresh.
"""

import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from backup_config import log_msg
from gui_helpers import (
    setup_row_scroll,
    dataset_name_cell_func,
    build_full_dataset_name,
    get_expanded_rows,
    restore_expanded_rows,
    on_row_expanded,
    set_monospace_font,
    configure_treeview_column,
    _ensure_treeview_scrolling,
)


class PoolWatchWindow(Gtk.Window):
    """Independent window for watching a single pool's datasets with auto-refresh."""

    REFRESH_INTERVAL = 30  # seconds

    def __init__(self, pool_name, parent_window):
        super().__init__(title=f"Watch: {pool_name}")
        self.pool_name = pool_name
        self.parent_window = parent_window
        self.set_default_size(800, 600)
        self.timer_id = None

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        self.add(main_box)

        # Left: dataset tree
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        main_box.pack_start(list_box, True, True, 0)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header = Gtk.Label()
        header.set_markup(f"<big><b>Watch: {pool_name}</b></big>")
        header.set_halign(Gtk.Align.START)
        header.set_selectable(True)
        header_box.pack_start(header, False, False, 0)

        self.auto_label = Gtk.Label()
        self.auto_label.set_halign(Gtk.Align.START)
        self.auto_label.set_valign(Gtk.Align.CENTER)
        header_box.pack_start(self.auto_label, False, False, 0)
        list_box.pack_start(header_box, False, False, 0)

        # TreeStore: same 8 columns as Datasets tab (add loaded boolean)
        self.store = Gtk.TreeStore(str, str, str, str, str, str, str, bool)
        self.view = Gtk.TreeView(model=self.store)
        self.view._zfs_repo = parent_window.ctx.zfs_repository
        self.view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
        self.view.set_enable_tree_lines(True)

        ds_columns = [
            ("Name", 0, 300),
            ("Created", 1, 160),
            ("Type", 2, 80),
            ("Used", 3, 80),
            ("Avail", 4, 80),
            ("Refer", 5, 80),
            ("Origin / Clones", 6, 200),
        ]
        for title, col_idx, width in ds_columns:
            renderer = Gtk.CellRendererText()
            if title == "Created":
                set_monospace_font(renderer)
            col = Gtk.TreeViewColumn(title, renderer, text=col_idx)
            if col_idx in (3, 4, 5):
                renderer.set_property("xalign", 1.0)
                col.set_alignment(1.0)
            configure_treeview_column(col, width=width)
            if col_idx == 0:
                col.set_cell_data_func(renderer, dataset_name_cell_func)
            self.view.append_column(col)

        self.view.connect("button-press-event", self._on_right_click)
        self.view.connect("row-expanded", on_row_expanded, None)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.add(self.view)
        setup_row_scroll(self.scrolled, self.view)
        _ensure_treeview_scrolling(self.view)
        list_box.pack_start(self.scrolled, True, True, 0)

        self.summary_label = Gtk.Label()
        self.summary_label.set_halign(Gtk.Align.START)
        list_box.pack_start(self.summary_label, False, False, 0)

        # Right: buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        button_box.set_size_request(120, -1)
        main_box.pack_start(button_box, False, False, 0)

        buttons = [
            ("Refresh", "view-refresh", self._on_refresh),
            ("Expand All", "list-add", self._on_expand_all),
            ("Collapse All", "list-remove", self._on_collapse_all),
            ("Close", "window-close", self._on_close),
        ]
        for label, icon, callback in buttons:
            btn = Gtk.Button(label=label)
            btn.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
            btn.set_always_show_image(True)
            btn.connect("clicked", callback)
            button_box.pack_start(btn, False, False, 0)

        self.connect("destroy", self._on_destroy)

        # Initial load (lazy: pool node with dummy child) and start timer
        self.refresh()
        self._start_timer()

    def refresh(self):
        """Load pool node and restore expanded state (children load on demand)."""
        expanded = get_expanded_rows(self.store, self.view)
        vadj = self.scrolled.get_vadjustment()
        saved_scroll = vadj.get_value()
        self.store.clear()

        pool = self.pool_name
        pool_iter = self.store.append(None, [pool, "", "", "", "", "", "", False])
        # Dummy child so the expand arrow appears
        self.store.append(pool_iter, ["(loading...)", "", "", "", "", "", "", True])

        self.summary_label.set_text("")
        restore_expanded_rows(self.store, self.view, expanded)
        # Restore scroll position after layout settles
        GLib.idle_add(self._restore_scroll, saved_scroll)

    def _restore_scroll(self, value):
        """Restore scroll position, clamping to the new valid range."""
        vadj = self.scrolled.get_vadjustment()
        vadj.set_value(min(value, vadj.get_upper() - vadj.get_page_size()))
        return False  # don't repeat

    def _start_timer(self):
        """Start the auto-refresh timer."""
        self.auto_label.set_markup(
            f"  <small><i>Auto-refresh every {self.REFRESH_INTERVAL}s</i></small>"
        )
        self.timer_id = GLib.timeout_add_seconds(
            self.REFRESH_INTERVAL, self._timer_tick
        )

    def _stop_timer(self):
        """Stop the auto-refresh timer."""
        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def _timer_tick(self):
        """Called by the timer to refresh."""
        self.refresh()
        return True

    def _on_refresh(self, widget):
        self.refresh()

    def _on_expand_all(self, widget):
        self.view.expand_all()

    def _on_collapse_all(self, widget):
        self.view.collapse_all()

    def _on_close(self, widget):
        self.destroy()

    def _on_destroy(self, widget):
        """Clean up timer and remove from parent's tracking dict."""
        self._stop_timer()
        self.parent_window._watch_windows.pop(self.pool_name, None)

    def _on_right_click(self, treeview, event):
        """Right-click copy menu."""
        if event.button != 3:
            return False
        path_info = treeview.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False

        path, column = path_info[0], path_info[1]
        model = treeview.get_model()
        tree_iter = model.get_iter(path)

        menu = Gtk.Menu()

        col_idx = treeview.get_columns().index(column)
        cell_value = model.get_value(tree_iter, col_idx)
        item_cell = Gtk.MenuItem(label=f"Copy: {cell_value}")
        item_cell.connect("activate", self._copy_text, cell_value)
        menu.append(item_cell)

        full_name = build_full_dataset_name(model, tree_iter)
        if full_name != cell_value:
            item_full = Gtk.MenuItem(label=f"Copy full name: {full_name}")
            item_full.connect("activate", self._copy_text, full_name)
            menu.append(item_full)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _copy_text(self, widget, text):
        clipboard = Gtk.Clipboard.get_default(self.get_display())
        clipboard.set_text(text, -1)
