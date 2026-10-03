"""Pool-profile manager and editor dialogs (Disks page).

Pool profiles are the pool-scope counterpart of workload profiles: named
bundles of the settings that shape a pool at creation — the blocksize
(``ashift``, creation-only), the curated live-settable pool properties, and
the root filesystem's ``-O`` properties. They feed Create Pool and Migrate
Pool; this module only edits the store. Built-in (seeded) profiles follow the
workload-profile rules: they can be opened as templates but not overwritten
or deleted; Reset to Defaults restores them.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from feature_config import (
    DEFAULT_POOL_PROFILES,
    delete_pool_profile,
    get_pool_profiles,
    is_builtin_pool_profile,
    reset_pool_profiles,
    save_pool_profiles,
)
from gi.repository import Gtk
from gui_helpers import configure_treeview_column, create_dialog
from logging_config import log_msg
from pool_profiles import (
    BLOCKSIZE_CHOICES,
    POOL_PROPERTIES,
    POOL_PROPERTY_VALUES,
    validate_profile,
)
from workload_profiles import LIVE_PROPERTIES

# Combo entry meaning "leave this property out of the profile" (the property
# is then not written at pool creation and ZFS's default applies).
_POOL_PROP_UNSET = "(not set)"


def _show_validation_error(parent, message: str) -> None:
    """Show a modal error dialog and block until dismissed."""
    error = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    error.run()
    error.destroy()


def _is_builtin_profile_name(name: str) -> bool:
    """Return True if *name* matches a seeded pool profile (case-insensitive)."""
    lowered = name.lower()
    return any(builtin.lower() == lowered for builtin in DEFAULT_POOL_PROFILES)


def show_manage_pool_profiles_dialog(app):
    """Show the Manage Pool Profiles dialog."""
    dialog = create_dialog(
        "Manage Pool Profiles",
        app,
        [
            (Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE),
        ],
        default_response=Gtk.ResponseType.CLOSE,
        size=(700, 500),
    )
    content = dialog.get_content_area()

    store = Gtk.ListStore(str, str, str, str)
    view = Gtk.TreeView(model=store)
    view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

    cols = [
        (0, "Name", 180),
        (1, "Blocksize", 120),
        (2, "Description", 350),
        (3, "Kind", 80),
    ]
    for col_idx, title_text, width in cols:
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title_text, renderer, text=col_idx)
        configure_treeview_column(col, width=width)
        view.append_column(col)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_min_content_height(250)
    scrolled.add(view)
    content.pack_start(scrolled, True, True, 0)

    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    btn_box.set_halign(Gtk.Align.START)

    add_btn = Gtk.Button(label="Add")
    edit_btn = Gtk.Button(label="Edit")
    delete_btn = Gtk.Button(label="Delete")
    reset_btn = Gtk.Button(label="Reset to Defaults")

    btn_box.pack_start(add_btn, False, False, 0)
    btn_box.pack_start(edit_btn, False, False, 0)
    btn_box.pack_start(delete_btn, False, False, 0)
    btn_box.pack_start(reset_btn, False, False, 0)
    content.pack_start(btn_box, False, False, 0)

    def _refresh_list():
        store.clear()
        profiles = get_pool_profiles(app.config)
        for name, profile in profiles.items():
            store.append(
                [
                    name,
                    profile.get("blocksize", BLOCKSIZE_CHOICES[0]),
                    profile.get("description", ""),
                    "built-in" if is_builtin_pool_profile(name) else "custom",
                ]
            )

    def _selected_name():
        selection = view.get_selection()
        model, pathlist = selection.get_selected_rows()
        if not pathlist:
            return None
        tree_iter = model.get_iter(pathlist[0])
        return model.get_value(tree_iter, 0)

    def _selected_is_builtin() -> bool:
        name = _selected_name()
        return name is not None and is_builtin_pool_profile(name)

    def _on_selection_changed(_selection):
        # Seeded profiles cannot be overwritten or deleted, but they can be
        # opened for editing and saved under a new name.
        builtin = _selected_is_builtin()
        edit_btn.set_sensitive(True)
        delete_btn.set_sensitive(not builtin)
        edit_btn.set_tooltip_text(
            "Built-in profiles cannot be overwritten; saving edits requires a new "
            "profile name or an existing custom profile"
            if builtin
            else ""
        )
        delete_btn.set_tooltip_text(
            "Built-in profiles cannot be deleted; use Reset to Defaults to restore them"
            if builtin
            else ""
        )

    def _on_add(_btn):
        show_pool_profile_editor_dialog(app)
        _refresh_list()

    def _on_edit(_btn):
        name = _selected_name()
        if name is None:
            log_msg("WARN: Select a pool profile to edit")
            return
        profiles = get_pool_profiles(app.config)
        if name not in profiles and not is_builtin_pool_profile(name):
            log_msg(f"WARN: Pool profile {name} no longer exists")
            _refresh_list()
            return
        show_pool_profile_editor_dialog(app, name)
        _refresh_list()

    def _on_delete(_btn):
        name = _selected_name()
        if name is None:
            log_msg("WARN: Select a pool profile to delete")
            return
        if is_builtin_pool_profile(name):
            log_msg(f"WARN: Pool profile {name!r} is built in and cannot be deleted")
            return
        confirm = Gtk.MessageDialog(
            transient_for=dialog,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete pool profile {name}?",
        )
        confirm.format_secondary_text("This cannot be undone.")
        response = confirm.run()
        confirm.destroy()
        if response == Gtk.ResponseType.YES:
            delete_pool_profile(app.config, name)
            _refresh_list()

    def _on_reset(_btn):
        confirm = Gtk.MessageDialog(
            transient_for=dialog,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Reset pool profiles to defaults?",
        )
        confirm.format_secondary_text(
            "All custom pool profiles will be discarded and the seeded defaults will be restored."
        )
        response = confirm.run()
        confirm.destroy()
        if response == Gtk.ResponseType.YES:
            reset_pool_profiles(app.config)
            _refresh_list()

    add_btn.connect("clicked", _on_add)
    edit_btn.connect("clicked", _on_edit)
    delete_btn.connect("clicked", _on_delete)
    reset_btn.connect("clicked", _on_reset)
    view.get_selection().connect("changed", _on_selection_changed)

    _refresh_list()
    _on_selection_changed(view.get_selection())
    dialog.show_all()
    dialog.run()
    dialog.destroy()


def _choice_combo(choices: tuple[str, ...], current: str) -> Gtk.ComboBoxText:
    """A text combo pre-set to *current* (first choice when unknown)."""
    combo = Gtk.ComboBoxText()
    for choice in choices:
        combo.append_text(choice)
    combo.set_active(choices.index(current) if current in choices else 0)
    return combo


def _combo_text(combo) -> str:
    """Return the active combo text, tolerating mocks."""
    text = combo.get_active_text()
    return text if isinstance(text, str) else ""


def show_pool_profile_editor_dialog(app, name=None):
    """Show the Add/Edit Pool Profile dialog and persist on OK.

    When *name* is None a new profile is created. When *name* is provided the
    existing profile is edited (the name field is read-only). Built-in
    (seeded) profiles can be opened for editing as a starting point, but they
    cannot be overwritten: the name field stays editable and saving requires
    a new profile name or an existing custom profile (with an overwrite
    confirmation, like the workload-profile editor).
    """
    profiles = get_pool_profiles(app.config)
    is_edit = name is not None
    editing_builtin = is_edit and is_builtin_pool_profile(name)
    if is_edit:
        existing = profiles.get(name) or DEFAULT_POOL_PROFILES.get(name, {})
    else:
        existing = {}

    dialog = create_dialog(
        "Edit Pool Profile" if is_edit else "Add Pool Profile",
        app,
        [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            (Gtk.STOCK_OK, Gtk.ResponseType.OK),
        ],
        default_response=Gtk.ResponseType.OK,
        size=(520, 640),
    )
    content = dialog.get_content_area()

    grid = Gtk.Grid()
    grid.set_column_spacing(10)
    grid.set_row_spacing(10)
    grid.set_margin_top(10)
    grid.set_margin_bottom(10)
    grid.set_margin_start(10)
    grid.set_margin_end(10)
    content.pack_start(grid, False, False, 0)

    def _add_row(row, label_text, widget):
        label = Gtk.Label(label=label_text)
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)
        return widget

    row = 0
    if editing_builtin:
        notice = Gtk.Label()
        notice.set_markup(
            f"Editing built-in profile <b>{name}</b>. Built-in profiles cannot be "
            "overwritten — save under a new name or overwrite an existing "
            "custom profile."
        )
        notice.set_halign(Gtk.Align.START)
        notice.set_line_wrap(True)
        grid.attach(notice, 0, row, 2, 1)
        row += 1

    name_entry = Gtk.Entry()
    name_entry.set_text(name or "")
    name_entry.set_sensitive(not is_edit or editing_builtin)
    _add_row(row, "Name:", name_entry)
    row += 1

    desc_entry = Gtk.Entry()
    desc_entry.set_text(existing.get("description", ""))
    _add_row(row, "Description:", desc_entry)
    row += 1

    blocksize_combo = _choice_combo(
        BLOCKSIZE_CHOICES, existing.get("blocksize", BLOCKSIZE_CHOICES[0])
    )
    _add_row(row, "Blocksize:", blocksize_combo)
    row += 1

    # Pool properties are picked from their allowed values (plus "(not set)",
    # which leaves the property to ZFS's default) — no free text, so an
    # inexperienced user cannot enter an invalid value.
    pool_prop_combos: dict[str, Gtk.ComboBoxText] = {}
    pool_props = existing.get("pool_properties", {})
    for prop in POOL_PROPERTIES:
        choices = (_POOL_PROP_UNSET,) + POOL_PROPERTY_VALUES[prop]
        combo = _choice_combo(choices, pool_props.get(prop, _POOL_PROP_UNSET))
        _add_row(row, f"{prop}:", combo)
        pool_prop_combos[prop] = combo
        row += 1

    # Root filesystem properties use the workload-profile vocabulary; free
    # text with placeholders, mirroring the workload-profile editor.
    fs_entries: dict[str, Gtk.Entry] = {}
    fs_props = existing.get("filesystem_properties", {})
    placeholders = {
        "recordsize": "e.g. 128K",
        "compression": "e.g. lz4 or zstd",
        "atime": "on or off",
        "logbias": "latency or throughput",
        "sync": "standard, always, or disabled",
        "primarycache": "all, metadata, or none",
        "special_small_blocks": "e.g. 32K (needs a special vdev)",
    }
    for prop in LIVE_PROPERTIES:
        entry = Gtk.Entry()
        entry.set_text(fs_props.get(prop, ""))
        entry.set_placeholder_text(placeholders.get(prop, ""))
        _add_row(row, f"{prop}:", entry)
        fs_entries[prop] = entry
        row += 1

    notes_buf = Gtk.TextBuffer()
    notes_buf.set_text(existing.get("notes", ""))
    notes_tv = Gtk.TextView(buffer=notes_buf)
    notes_tv.set_editable(True)
    notes_tv.set_wrap_mode(Gtk.WrapMode.WORD)
    notes_sw = Gtk.ScrolledWindow()
    notes_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    notes_sw.set_min_content_height(80)
    notes_sw.add(notes_tv)
    _add_row(row, "Notes:", notes_sw)
    row += 1

    dialog.show_all()
    while True:
        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return

        new_name = name_entry.get_text().strip()
        if not new_name:
            _show_validation_error(dialog, "Profile name is required.")
            continue

        overwrite_name = None
        if editing_builtin:
            if _is_builtin_profile_name(new_name):
                _show_validation_error(
                    dialog,
                    f"{new_name} is a built-in profile and cannot be overwritten.\n"
                    "Save under a new name or an existing custom profile.",
                )
                continue
            overwrite_name = next(
                (p for p in profiles if p.lower() == new_name.lower()),
                None,
            )
            if overwrite_name is not None:
                confirm = Gtk.MessageDialog(
                    transient_for=dialog,
                    modal=True,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO,
                    text=f"Pool profile '{overwrite_name}' already exists.",
                )
                confirm.format_secondary_text("Overwrite it with these settings?")
                response = confirm.run()
                confirm.destroy()
                if response != Gtk.ResponseType.YES:
                    continue
        elif not is_edit and any(p.lower() == new_name.lower() for p in profiles):
            _show_validation_error(dialog, f"A pool profile named {new_name} already exists.")
            continue

        blocksize = _combo_text(blocksize_combo) or BLOCKSIZE_CHOICES[0]
        pool_properties = {
            prop: _combo_text(combo)
            for prop, combo in pool_prop_combos.items()
            if _combo_text(combo) not in ("", _POOL_PROP_UNSET)
        }
        filesystem_properties = {
            prop: entry.get_text().strip()
            for prop, entry in fs_entries.items()
            if entry.get_text().strip()
        }
        if not pool_properties and not filesystem_properties and blocksize == BLOCKSIZE_CHOICES[0]:
            _show_validation_error(
                dialog,
                "Set at least one property (or an explicit blocksize) — an empty "
                "profile shapes nothing.",
            )
            continue

        new_profile = {
            "description": desc_entry.get_text().strip(),
            "blocksize": blocksize,
            "pool_properties": pool_properties,
            "filesystem_properties": filesystem_properties,
            "notes": notes_buf.get_text(
                notes_buf.get_start_iter(),
                notes_buf.get_end_iter(),
                True,
            ),
        }
        problems = validate_profile(new_profile)
        if problems:
            _show_validation_error(dialog, "Invalid pool profile:\n" + "\n".join(problems))
            continue

        if is_edit and not editing_builtin:
            profiles[name] = new_profile
        elif overwrite_name is not None:
            profiles[overwrite_name] = new_profile
        else:
            profiles[new_name] = new_profile
        save_pool_profiles(app.config, profiles)
        dialog.destroy()
        return
