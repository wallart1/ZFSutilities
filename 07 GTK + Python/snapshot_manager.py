"""
Snapshot Manager secondary window.

Shows snapshots for a specific dataset in a collapsible tree with holds
as child rows. Supports delete (snapshots and holds), add hold, and rollback.
"""

import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango

from backup_config import log_msg
from gui_helpers import (
    setup_row_scroll, diagnose_dataset_busy, set_monospace_font,
    configure_treeview_column, _ensure_treeview_scrolling,
    create_dialog,
)


class SnapshotManagerWindow(Gtk.Window):
    """Secondary window for managing snapshots of a specific dataset.

    Snapshots are shown in a collapsible tree with holds as children.
    """

    def __init__(self, dataset, parent_window):
        super().__init__(title=f"Snapshots: {dataset}")
        self.dataset = dataset
        self.parent_window = parent_window
        self.set_default_size(750, 500)
        self.set_transient_for(parent_window)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        self.add(main_box)

        # Left: snapshot tree
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        main_box.pack_start(list_box, True, True, 0)

        header = Gtk.Label()
        header.set_markup(f"<b>{dataset}</b>")
        header.set_halign(Gtk.Align.START)
        header.set_selectable(True)
        list_box.pack_start(header, False, False, 0)

        # TreeStore: snapshots as parents, holds as children
        # Columns: name, created, used, refer, holds
        self.snap_store = Gtk.TreeStore(str, str, str, str, str)
        self.snap_view = Gtk.TreeView(model=self.snap_store)
        self.snap_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
        self.snap_view.set_enable_tree_lines(True)
        self.snap_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        snap_columns = [
            ("Name", 0, 220),
            ("Created", 1, 160),
            ("Used", 2, 80),
            ("Refer", 3, 80),
            ("Holds", 4, 60),
        ]
        for title, col_idx, width in snap_columns:
            renderer = Gtk.CellRendererText()
            if title == "Created":
                set_monospace_font(renderer)
            col = Gtk.TreeViewColumn(title, renderer, text=col_idx)
            if col_idx in (2, 3, 4):
                renderer.set_property("xalign", 1.0)
            configure_treeview_column(col, width=width)
            if col_idx == 0:
                col.set_cell_data_func(renderer, self._name_cell_func)
            self.snap_view.append_column(col)

        self.snap_view.connect("button-press-event", self._on_snap_right_click)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.snap_view)
        setup_row_scroll(scrolled, self.snap_view)
        _ensure_treeview_scrolling(self.snap_view)
        list_box.pack_start(scrolled, True, True, 0)

        self.snap_summary = Gtk.Label()
        self.snap_summary.set_halign(Gtk.Align.START)
        list_box.pack_start(self.snap_summary, False, False, 0)

        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_selectable(True)
        self.status_label.get_style_context().add_class("status-bar-label")
        list_box.pack_start(self.status_label, False, False, 0)

        # Right: action buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        button_box.set_size_request(120, -1)
        main_box.pack_start(button_box, False, False, 0)

        buttons = [
            ("Refresh", "view-refresh", self.on_refresh),
            ("Delete", "edit-delete", self.on_delete),
            ("Add Hold", "changes-prevent", self.on_hold),
            ("Rollback", "edit-undo", self.on_rollback),
            ("Close", "window-close", self.on_close),
        ]
        for label, icon, callback in buttons:
            btn = Gtk.Button(label=label)
            btn.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
            btn.set_always_show_image(True)
            btn.connect("clicked", callback)
            button_box.pack_start(btn, False, False, 0)

        self.refresh_snapshots()

    def _repo(self):
        return self.parent_window.ctx.zfs_repository

    def _name_cell_func(self, column, renderer, model, tree_iter, data=None):
        """Style: normal for snapshots (parents), italic for holds (children)."""
        renderer.set_property("weight", Pango.Weight.NORMAL)
        style = Pango.Style.ITALIC if model.iter_parent(tree_iter) else Pango.Style.NORMAL
        renderer.set_property("style", style)

    def refresh_snapshots(self):
        """Load snapshots and their holds into the tree."""
        self.snap_store.clear()
        repo = self._repo()

        try:
            rows = repo.list_snapshots(self.dataset, depth=1, sort_creation=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.set_status(f"Error: {e}", level="WARN")
            return

        count = 0
        for row in rows:
            snap_full = row.name
            snap_name = snap_full.split("@", 1)[1] if "@" in snap_full else snap_full

            hold_lines = []
            try:
                holds = repo.list_holds(snap_full)
                hold_lines = [(h.tag, h.date) for h in holds]
            except subprocess.CalledProcessError:
                pass

            hold_count = str(len(hold_lines))
            snap_iter = self.snap_store.append(
                None, [snap_name, row.creation, row.used, row.refer, hold_count]
            )

            for tag, date in hold_lines:
                self.snap_store.append(snap_iter, [tag, date, "", "", ""])

            count += 1

        self.snap_summary.set_text(f"{count} snapshots")

    def _get_selected_items(self):
        """Get structured list of selected items.

        Returns list of dicts:
          {"type": "snapshot", "name": snap_name}
          {"type": "hold", "tag": tag_name, "snapshot": parent_snap_name}
        """
        selection = self.snap_view.get_selection()
        model, paths = selection.get_selected_rows()
        items = []
        for path in paths:
            tree_iter = model.get_iter(path)
            parent = model.iter_parent(tree_iter)
            if parent is None:
                items.append({
                    "type": "snapshot",
                    "name": model.get_value(tree_iter, 0),
                })
            else:
                items.append({
                    "type": "hold",
                    "tag": model.get_value(tree_iter, 0),
                    "snapshot": model.get_value(parent, 0),
                })
        return items

    def set_status(self, msg, level="INFO"):
        self.status_label.set_text(msg)
        log_msg(f"{level}: {msg}")

    def on_refresh(self, widget):
        self.refresh_snapshots()
        self.set_status("Refreshed")

    def on_delete(self, widget):
        """Delete selected snapshots or release selected holds."""
        items = self._get_selected_items()
        if not items:
            self.set_status("Select one or more snapshots or holds to delete", level="WARN")
            return

        holds = [i for i in items if i["type"] == "hold"]
        snaps = [i for i in items if i["type"] == "snapshot"]

        # Release holds first
        if holds:
            names = "\n  ".join(f"{h['tag']} on @{h['snapshot']}" for h in holds)
            dialog = Gtk.MessageDialog(
                transient_for=self, modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"Release {len(holds)} hold(s)?",
            )
            dialog.format_secondary_text(f"  {names}")
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.YES:
                repo = self._repo()
                for h in holds:
                    full = f"{self.dataset}@{h['snapshot']}"
                    if repo.release(h["tag"], full):
                        self.set_status(f"Released '{h['tag']}' on {full}")
                    else:
                        self.set_status(f"Error releasing '{h['tag']}' on {full}", level="WARN")

        # Delete snapshots
        if snaps:
            # Re-check holds after releases above
            held = []
            repo = self._repo()
            for s in snaps:
                full = f"{self.dataset}@{s['name']}"
                try:
                    if repo.list_holds(full):
                        held.append(s["name"])
                except subprocess.CalledProcessError:
                    pass

            if held:
                self.set_status(
                    f"Cannot delete: {', '.join(held)} still have holds. "
                    "Delete the holds first.",
                    level="WARN",
                )
                if not holds:
                    return
                # Still refresh to show the hold releases
                self.refresh_snapshots()
                return

            snap_names = [s["name"] for s in snaps]
            names = "\n  ".join(snap_names)
            dialog = Gtk.MessageDialog(
                transient_for=self, modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"Delete {len(snap_names)} snapshot(s)?",
            )
            dialog.format_secondary_text(f"  {names}\n\nThis cannot be undone.")
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.YES:
                repo = self._repo()
                errors = 0
                for snap_name in snap_names:
                    full = f"{self.dataset}@{snap_name}"
                    if repo.destroy(full):
                        self.set_status(f"Deleted: {full}")
                    else:
                        self.set_status(f"Error deleting {full}", level="WARN")
                        diagnose_dataset_busy(full, repo=repo)
                        errors += 1
                if not errors:
                    self.set_status(f"Deleted {len(snap_names)} snapshot(s)")

        self.refresh_snapshots()

    def on_hold(self, widget):
        """Place a hold on selected snapshots."""
        items = self._get_selected_items()
        snaps = [i for i in items if i["type"] == "snapshot"]
        if not snaps:
            self.set_status("Select one or more snapshots (not holds)", level="WARN")
            return

        dialog = create_dialog("Add Hold", self, [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            (Gtk.STOCK_OK, Gtk.ResponseType.OK),
        ], default_response=Gtk.ResponseType.OK)
        content = dialog.get_content_area()

        label = Gtk.Label(label="Hold tag name:")
        label.set_halign(Gtk.Align.START)
        content.add(label)

        entry = Gtk.Entry()
        entry.set_width_chars(1)
        entry.set_text("keep")
        entry.set_activates_default(True)
        content.add(entry)

        dialog.show_all()
        response = dialog.run()
        tag = entry.get_text().strip()
        dialog.destroy()

        if response != Gtk.ResponseType.OK or not tag:
            return

        repo = self._repo()
        for s in snaps:
            full = f"{self.dataset}@{s['name']}"
            if repo.hold(tag, full):
                self.set_status(f"Hold '{tag}' set on {full}")
            else:
                self.set_status(f"Error setting hold '{tag}' on {full}", level="WARN")

        self.refresh_snapshots()

    def on_rollback(self, widget):
        """Rollback the dataset to the selected snapshot."""
        items = self._get_selected_items()
        snaps = [i for i in items if i["type"] == "snapshot"]
        if len(snaps) != 1:
            self.set_status("Select exactly one snapshot to rollback to", level="WARN")
            return

        snap_name = snaps[0]["name"]
        full = f"{self.dataset}@{snap_name}"

        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Rollback to {snap_name}?",
        )
        dialog.format_secondary_text(
            f"This will revert {self.dataset} to snapshot {snap_name}.\n\n"
            "All data written after this snapshot will be LOST.\n"
            "Newer snapshots will be destroyed."
        )
        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.YES:
            return

        if self._repo().rollback(full):
            self.set_status(f"Rolled back to {full}")
        else:
            self.set_status(f"Error rolling back to {full}", level="WARN")

        self.refresh_snapshots()

    def on_close(self, widget):
        self.destroy()

    def _on_snap_right_click(self, treeview, event):
        """Right-click copy menu."""
        if event.button != 3:
            return False

        path_info = treeview.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False

        path, column = path_info[0], path_info[1]
        model = treeview.get_model()
        tree_iter = model.get_iter(path)
        parent = model.iter_parent(tree_iter)

        menu = Gtk.Menu()
        col_idx = treeview.get_columns().index(column)
        cell_value = model.get_value(tree_iter, col_idx)
        if cell_value:
            item_cell = Gtk.MenuItem(label=f"Copy: {cell_value}")
            item_cell.connect("activate", self._copy_text, cell_value)
            menu.append(item_cell)

        snap_name = model.get_value(tree_iter if parent is None else parent, 0)
        full_name = f"{self.dataset}@{snap_name}"
        label = "Copy full name" if parent is None else f"Copy snapshot: {full_name}"
        item_full = Gtk.MenuItem(label=label)
        item_full.connect("activate", self._copy_text, full_name)
        menu.append(item_full)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _copy_text(self, widget, text):
        clipboard = Gtk.Clipboard.get_default(self.get_display())
        clipboard.set_text(text, -1)
        self.set_status(f"Copied: {text}")
