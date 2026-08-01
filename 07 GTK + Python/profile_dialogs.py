"""Shared profile dialogs used by multiple tab pages."""

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gui_helpers import (
    _ensure_treeview_scrolling,
    configure_treeview_column,
    create_dialog,
    show_error_dialog,
    show_warning_dialog,
)
from profile_manager import (
    create_profile,
    get_user,
    list_profiles,
    load_profile,
    profile_exists,
    update_profile,
)
from profile_validation import validate_profiles


def show_add_profile_dialog(app, tab_type, config_dict, on_success=None,
                            dry_run=False):
    """Show the Add Profile to Schedule dialog and save a profile if confirmed.

    Args:
        dry_run: capture the current Dry Run toggle state in the profile.
    """
    user = get_user()
    prefix = f"{user}-{tab_type}-"

    dlg = create_dialog(
        "Add Profile to Schedule", app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
         (Gtk.STOCK_OK, Gtk.ResponseType.OK)],
        default_response=Gtk.ResponseType.OK,
    )
    content = dlg.get_content_area()

    prefix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    prefix_box.pack_start(Gtk.Label(label="Prefix:"), False, False, 0)
    prefix_lbl = Gtk.Label(label=prefix)
    prefix_lbl.set_halign(Gtk.Align.START)
    prefix_lbl.set_selectable(True)
    prefix_box.pack_start(prefix_lbl, False, False, 0)
    content.add(prefix_box)

    name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    name_box.pack_start(Gtk.Label(label="Name:"), False, False, 0)
    name_entry = Gtk.Entry()
    name_entry.set_width_chars(1)
    name_entry.set_activates_default(True)
    name_entry.set_hexpand(True)
    name_box.pack_start(name_entry, True, True, 0)
    content.add(name_box)

    note = Gtk.Label()
    note.set_markup("<small>Only letters, digits, hyphens, and underscores allowed.</small>")
    note.set_halign(Gtk.Align.START)
    content.add(note)

    dlg.show_all()
    response = dlg.run()
    custom_name = name_entry.get_text().strip()
    dlg.destroy()

    if response != Gtk.ResponseType.OK or not custom_name:
        return

    import re
    # Regex: ^[A-Za-z0-9_-]+$
    # Purpose: Validate that a custom profile name contains only safe filename characters.
    #          Only letters, digits, hyphens, and underscores are allowed.
    # Example: "my-backup_01" -> match
    #          "my backup"    -> no match (contains space)
    if not re.match(r"^[A-Za-z0-9_-]+$", custom_name):
        show_error_dialog(app, "Invalid profile name.\nUse only letters, digits, hyphens, and underscores.")
        return

    full_name = prefix + custom_name
    if profile_exists(full_name):
        dlg = Gtk.MessageDialog(
            transient_for=app, modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Profile '{full_name}' already exists.",
        )
        dlg.format_secondary_text(
            "Overwrite it with the current tab settings?"
        )
        response = dlg.run()
        dlg.destroy()
        if response != Gtk.ResponseType.YES:
            return
        try:
            profile = update_profile(tab_type, custom_name, config_dict,
                                     dry_run=dry_run)
        except ValueError as e:
            show_error_dialog(app, str(e))
            return
    else:
        try:
            profile = create_profile(tab_type, custom_name, config_dict,
                                     dry_run=dry_run)
        except ValueError as e:
            show_error_dialog(app, str(e))
            return

    _show_profile_scope_warnings(app, profile)
    if on_success:
        on_success(profile)
    if hasattr(app, "schedule_store"):
        from schedule_page import _refresh_profile_list
        _refresh_profile_list(app)


def _show_profile_scope_warnings(app, profile):
    """Validate the saved profile against others and show warnings."""
    try:
        profiles = list_profiles()
    except Exception:
        return
    names = {p.get("profile_name") for p in profiles}
    if profile.get("profile_name") not in names:
        profiles.append(profile)
    warnings = validate_profiles(profiles)
    profile_name = profile.get("profile_name", "")
    relevant = [w for w in warnings if profile_name in w]
    if relevant:
        show_warning_dialog(
            app,
            "Profile scope mismatch detected:\n\n" + "\n\n".join(relevant)
        )


def show_recall_profile_dialog(app, tab_type, on_select):
    """Show a dialog listing profiles of the given tab type."""
    profiles = [p for p in list_profiles() if p.get("tab_type") == tab_type]
    if not profiles:
        show_error_dialog(app, f"No {tab_type} profiles found.")
        return

    dlg = create_dialog(
        "Recall Profile", app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
         ("Recall", Gtk.ResponseType.OK)],
        default_response=Gtk.ResponseType.OK,
    )
    content = dlg.get_content_area()

    label = Gtk.Label(label=f"Select a {tab_type} profile to load:")
    label.set_halign(Gtk.Align.START)
    content.add(label)

    store = Gtk.ListStore(str, str)
    for profile in profiles:
        cron = profile.get("cron", {})
        sched = "{} {} {} {} {}".format(
            cron.get("minute", "*"), cron.get("hour", "*"),
            cron.get("day", "*"), cron.get("month", "*"),
            cron.get("weekday", "*"),
        )
        store.append([profile["profile_name"], sched])

    view = Gtk.TreeView(model=store)
    view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

    r0 = Gtk.CellRendererText()
    c0 = Gtk.TreeViewColumn("Profile", r0, text=0)
    configure_treeview_column(c0, width=150)
    view.append_column(c0)

    r1 = Gtk.CellRendererText()
    c1 = Gtk.TreeViewColumn("Schedule", r1, text=1)
    configure_treeview_column(c1, width=150)
    view.append_column(c1)

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_height(150)
    scroll.add(view)
    _ensure_treeview_scrolling(view)
    content.add(scroll)

    dlg.show_all()
    response = dlg.run()

    selected = None
    if response == Gtk.ResponseType.OK:
        sel = view.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter:
            profile_name = model.get_value(tree_iter, 0)
            selected = load_profile(profile_name)

    dlg.destroy()

    if selected and on_select:
        on_select(selected)
