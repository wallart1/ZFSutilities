"""Create-pool wizard — GTK UI and execution handler for the Disks page.

Guides the user through disk selection, topology choice, pool settings, and a
review step that shows the exact ``zpool create`` command plus live
``zpool create -n`` output. Creation requires typed confirmation of the pool
name because the command destroys any data on the selected devices.

All decision logic is kept in pure helpers (testable without GTK); ZFS I/O is
delegated to ``ZfsRepository`` via the app context.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Container
from dataclasses import dataclass, field

import gi

gi.require_version("Gtk", "3.0")

import node_config
import zfs_lock_manager as zlm
from command_builders import BashStep
from disk_repository import DiskInfo
from disks_page import refresh_disks_page, update_disks_button_sensitivity
from feature_config import get_workload_profiles
from gi.repository import Gtk
from gui_helpers import configure_treeview_column, create_dialog
from logging_config import log_msg
from pool_create import (
    TOPOLOGIES,
    EligibilityResult,
    disk_eligibility,
    estimate_effective_capacity,
    pool_filesystem_options,
    suggest_ashift,
    validate_pool_name,
    validate_vdev_selection,
)
from pools_page import on_pools_refresh, refresh_pools_page
from zfs_repository import TopologyNode, build_create_pool_command

# Custom dialog response ids for the wizard buttons. Distinct from
# Gtk.ResponseType values (which are negative) and from each other so tests
# can tell Back/Next/Create apart under mock GTK.
_RESPONSE_BACK = 10
_RESPONSE_NEXT = 11
_RESPONSE_CREATE = 12

_PAGE_TITLES = {
    "disks": "Select disks",
    "topology": "Choose topology",
    "settings": "Pool settings",
    "review": "Review and create",
}
PAGES = tuple(_PAGE_TITLES)

_BY_ID_DIR = "/dev/disk/by-id"

_INELIGIBLE_FG = "grey"

# Disk-picker ListStore columns:
#   0 use, 1 by-id, 2 size, 3 model, 4 transport, 5 status,
#   6 eligible, 7 foreground
(
    _COL_USE,
    _COL_BYID,
    _COL_SIZE,
    _COL_MODEL,
    _COL_TRANSPORT,
    _COL_STATUS,
    _COL_ELIGIBLE,
    _COL_FG,
) = range(8)

_SIZE_SUFFIXES = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}

_DEFAULT_RECORDSIZE = 128 * 1024


@dataclass
class _WizardState:
    """Mutable wizard state shared by the four pages."""

    eligibility: list[EligibilityResult]
    selected: list[DiskInfo] = field(default_factory=list)
    topology: str = "mirror"
    pool_name: str = ""
    ashift: int | None = None  # None = auto (flag omitted from the command)
    profile_name: str = ""
    typed: str = ""  # review-page typed confirmation
    dry_run_rc: int | None = None  # None = dry run not yet executed
    dry_run_output: str = ""
    command: list[str] = field(default_factory=list)
    page: str = "disks"
    page_refresh: dict = field(default_factory=dict)


@dataclass
class _WizardContext:
    """Inputs the page builders need, bundled to keep signatures short."""

    app: object
    profiles: dict
    existing_names: object  # container of imported + importable pool names
    repository: object


# ---------------------------------------------------------------------------
# Pure helpers (no GTK, no subprocess) — unit-tested directly
# ---------------------------------------------------------------------------


def _leaf_paths_by_pool(topologies: dict[str, TopologyNode]) -> dict[str, list[str]]:
    """Map each imported pool name to its leaf device paths.

    Walks the ``zpool status -P`` topology trees from the disk inventory cache
    the same way ``DiskInventoryCache._collect_disk_paths`` does.
    """
    paths: dict[str, list[str]] = {}
    for pool_name, root in (topologies or {}).items():
        leaves: list[str] = []
        _collect_leaf_paths(root, leaves)
        paths[pool_name] = leaves
    return paths


def _collect_leaf_paths(node: TopologyNode, leaves: list[str]) -> None:
    if node.vdev_type == "disk" and node.name:
        leaves.append(node.name)
    for child in node.children:
        _collect_leaf_paths(child, leaves)


def _recordsize_bytes(profile: dict) -> int:
    """Return the profile's recordsize in bytes (binary suffixes), for the
    capacity estimator. Falls back to the ZFS default recordsize."""
    raw = str(profile.get("properties", {}).get("recordsize", "")).strip().upper()
    if not raw:
        return _DEFAULT_RECORDSIZE
    multiplier = 1
    if raw[-1] in _SIZE_SUFFIXES:
        multiplier = _SIZE_SUFFIXES[raw[-1]]
        raw = raw[:-1]
    try:
        return int(raw) * multiplier
    except ValueError:
        return _DEFAULT_RECORDSIZE


def _format_bytes(n: int) -> str:
    """Format a byte count with binary units, one decimal for non-bytes."""
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or unit == "PiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PiB"  # pragma: no cover - loop always returns


def _disks_problems(state: _WizardState) -> list[str]:
    if not state.selected:
        return ["Select at least one eligible disk"]
    return []


def _topology_problems(state: _WizardState) -> list[str]:
    spec = TOPOLOGIES[state.topology]
    problems: list[str] = []
    if len(state.selected) < spec.min_disks:
        problems.append(f"{state.topology} requires at least {spec.min_disks} disks")
    problems.extend(validate_vdev_selection(state.selected))
    return problems


def _settings_problems(state: _WizardState, existing_names: Container[str]) -> list[str]:
    ok, error = validate_pool_name(state.pool_name, existing_names)
    return [] if ok else [error]


def _review_problems(state: _WizardState) -> list[str]:
    if not state.command:
        return ["Command is not ready"]
    if state.dry_run_rc is None:
        return ["Dry run has not completed"]
    if state.dry_run_rc != 0:
        return ["Dry run failed — resolve the problem before creating"]
    if state.typed != state.pool_name:
        return [f"Type the pool name '{state.pool_name}' to confirm"]
    return []


def _page_problems(page: str, state: _WizardState, ctx: _WizardContext) -> list[str]:
    if page == "disks":
        return _disks_problems(state)
    if page == "topology":
        return _topology_problems(state)
    if page == "settings":
        return _settings_problems(state, ctx.existing_names)
    return _review_problems(state)


def _estimate_text(state: _WizardState, profile: dict) -> str:
    """Human-readable capacity estimate for the current selection."""
    if not state.selected:
        return "Select disks on the previous step to see the capacity estimate."
    min_bytes = min(disk.size_bytes for disk in state.selected)
    block_bytes = _recordsize_bytes(profile)
    sector_bytes = (1 << state.ashift) if state.ashift else 4096
    try:
        estimate = estimate_effective_capacity(
            state.topology,
            len(state.selected),
            min_bytes,
            block_bytes,
            sector_bytes,
        )
    except ValueError as exc:
        return f"Capacity estimate unavailable: {exc}"
    recordsize = profile.get("properties", {}).get("recordsize", "128K")
    effective = (
        f"Effective at {recordsize} block size: "
        f"{_format_bytes(estimate.effective_bytes)} "
        f"({estimate.efficiency_fraction:.0%} of raw usable)"
    )
    lines = [
        f"Raw usable capacity: {_format_bytes(estimate.raw_usable_bytes)}",
        effective,
    ]
    if len({disk.size_bytes for disk in state.selected}) > 1:
        lines.append(
            "Mixed disk sizes: vdev usable capacity = smallest member "
            f"({_format_bytes(min_bytes)})."
        )
    return "\n".join(lines)


def _review_warnings(state: _WizardState) -> list[str]:
    """Informational warnings for the disks the user selected."""
    warnings: list[str] = []
    for result in state.eligibility:
        if result.disk in state.selected:
            warnings.extend(result.warnings)
    return warnings


def _review_summary(state: _WizardState, ctx: _WizardContext) -> str:
    profile = ctx.profiles.get(state.profile_name, {})
    parts = [_estimate_text(state, profile)]
    warnings = _review_warnings(state)
    if warnings:
        parts.append("Warnings:\n" + "\n".join(f"• {warning}" for warning in warnings))
    return "\n\n".join(parts)


def build_wizard_command(state: _WizardState, profiles: dict) -> list[str]:
    """Build the exact ``zpool create`` argv for the current wizard state."""
    by_id_paths = [os.path.join(_BY_ID_DIR, disk.by_id) for disk in state.selected]
    options = pool_filesystem_options(profiles.get(state.profile_name, {}))
    return build_create_pool_command(
        state.pool_name,
        state.topology,
        by_id_paths,
        ashift=state.ashift,
        options=options,
    )


def _selected_disks(store, state: _WizardState) -> list[DiskInfo]:
    """Return the disks whose checkbox is ticked, in store row order."""
    selected: list[DiskInfo] = []
    index = 0
    tree_iter = store.get_iter_first()
    while tree_iter:
        if store.get_value(tree_iter, _COL_USE) and index < len(state.eligibility):
            selected.append(state.eligibility[index].disk)
        tree_iter = store.iter_next(tree_iter)
        index += 1
    return selected


def _widget_text(widget, fallback: str = "") -> str:
    """Return widget text, tolerating mocks that return non-strings."""
    text = widget.get_text()
    return text if isinstance(text, str) else fallback


def _combo_text(combo) -> str:
    text = combo.get_active_text()
    return text if isinstance(text, str) else ""


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


def _on_disk_toggled(toggle, path, store, state: _WizardState, on_change) -> None:
    tree_iter = store.get_iter(path)
    if not store.get_value(tree_iter, _COL_ELIGIBLE):
        return
    use = not store.get_value(tree_iter, _COL_USE)
    store.set_value(tree_iter, _COL_USE, use)
    state.selected = _selected_disks(store, state)
    on_change()


def _on_topology_toggled(radio, name: str, state: _WizardState, on_change) -> None:
    active = radio.get_active()
    if isinstance(active, bool) and not active:
        return  # deactivation signal from the previously selected radio
    state.topology = name
    on_change()


def _on_name_changed(entry, state: _WizardState, on_change) -> None:
    state.pool_name = _widget_text(entry, state.pool_name)
    on_change()


def _on_ashift_changed(combo, state: _WizardState, on_change) -> None:
    text = _combo_text(combo)
    if not text:
        return
    state.ashift = None if text.startswith("auto") else int(text)
    on_change()


def _on_profile_changed(combo, state: _WizardState, on_change) -> None:
    text = _combo_text(combo)
    if text:
        state.profile_name = text
    on_change()


def _on_typed_changed(entry, state: _WizardState, on_change) -> None:
    state.typed = _widget_text(entry, state.typed)
    on_change()


# ---------------------------------------------------------------------------
# Wizard pages
# ---------------------------------------------------------------------------


def _build_disks_page(dialog, state: _WizardState, ctx: _WizardContext, on_change):
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

    hint = Gtk.Label(
        label="Select the disks for the new pool's data vdev. Greyed-out disks "
        "cannot be used; the Status column says why."
    )
    hint.set_halign(Gtk.Align.START)
    hint.set_line_wrap(True)
    page.pack_start(hint, False, False, 0)

    smr_label = Gtk.Label(
        label="SMR cannot be detected reliably — verify drive specs before RAIDZ."
    )
    smr_label.set_halign(Gtk.Align.START)
    smr_label.set_line_wrap(True)
    smr_label.set_no_show_all(True)
    page.pack_start(smr_label, False, False, 0)

    store = Gtk.ListStore(bool, str, str, str, str, str, bool, str)
    for result in state.eligibility:
        disk = result.disk
        status = "; ".join(result.reasons) or "; ".join(result.warnings) or "eligible"
        foreground = None if result.eligible else _INELIGIBLE_FG
        store.append(
            [
                False,
                disk.by_id or disk.path,
                disk.size_human,
                disk.model,
                disk.transport,
                status,
                result.eligible,
                foreground,
            ]
        )

    view = Gtk.TreeView(model=store)
    view.get_selection().set_mode(Gtk.SelectionMode.NONE)

    toggle = Gtk.CellRendererToggle()
    toggle.connect("toggled", _on_disk_toggled, store, state, on_change)
    use_column = Gtk.TreeViewColumn("Use", toggle, active=_COL_USE)
    configure_treeview_column(use_column, width=40, resizable=False)
    view.append_column(use_column)

    for title, column_index, width in (
        ("by-id", _COL_BYID, 280),
        ("Size", _COL_SIZE, 90),
        ("Model", _COL_MODEL, 150),
        ("Transport", _COL_TRANSPORT, 90),
        ("Status", _COL_STATUS, 320),
    ):
        renderer = Gtk.CellRendererText()
        tree_column = Gtk.TreeViewColumn(
            title, renderer, text=column_index, foreground=_COL_FG
        )
        configure_treeview_column(tree_column, width=width)
        view.append_column(tree_column)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_min_content_height(260)
    scrolled.add(view)
    page.pack_start(scrolled, True, True, 0)

    def _refresh_disks():
        if any(disk.disk_type == "HDD" for disk in state.selected):
            smr_label.show()
        else:
            smr_label.hide()

    state.page_refresh["disks"] = _refresh_disks
    return page


def _build_topology_page(dialog, state: _WizardState, ctx: _WizardContext, on_change):
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

    info = Gtk.Label(
        label="Choose the redundancy layout for the new pool's single data vdev."
    )
    info.set_halign(Gtk.Align.START)
    info.set_line_wrap(True)
    page.pack_start(info, False, False, 0)

    radios = {}
    group = None
    for name, spec in TOPOLOGIES.items():
        label_text = f"{name} (minimum {spec.min_disks} disks)"
        if group is None:
            radio = Gtk.RadioButton(label=label_text)
            group = radio
        else:
            radio = Gtk.RadioButton.new_from_widget(group)
            radio.set_label(label_text)
        radio.connect("toggled", _on_topology_toggled, name, state, on_change)
        page.pack_start(radio, False, False, 0)
        radios[name] = radio
    radios[state.topology].set_active(True)

    estimate_label = Gtk.Label()
    estimate_label.set_halign(Gtk.Align.START)
    estimate_label.set_line_wrap(True)
    page.pack_start(estimate_label, False, False, 0)

    def _refresh_topology():
        profile = ctx.profiles.get(state.profile_name, {})
        estimate_label.set_text(_estimate_text(state, profile))

    state.page_refresh["topology"] = _refresh_topology
    return page


def _build_settings_page(dialog, state: _WizardState, ctx: _WizardContext, on_change):
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    grid = Gtk.Grid()
    grid.set_column_spacing(8)
    grid.set_row_spacing(8)
    page.pack_start(grid, False, False, 0)

    name_label = Gtk.Label(label="Pool name:")
    name_label.set_halign(Gtk.Align.END)
    grid.attach(name_label, 0, 0, 1, 1)
    name_entry = Gtk.Entry()
    name_entry.set_hexpand(True)
    grid.attach(name_entry, 1, 0, 1, 1)
    name_feedback = Gtk.Label()
    name_feedback.set_halign(Gtk.Align.START)
    name_feedback.set_line_wrap(True)
    grid.attach(name_feedback, 1, 1, 1, 1)

    ashift_label = Gtk.Label(label="ashift:")
    ashift_label.set_halign(Gtk.Align.END)
    grid.attach(ashift_label, 0, 2, 1, 1)
    ashift_combo = Gtk.ComboBoxText()
    for item in ("auto (recommended)", "9", "12", "13"):
        ashift_combo.append_text(item)
    ashift_combo.set_active(0)
    grid.attach(ashift_combo, 1, 2, 1, 1)
    ashift_hint = Gtk.Label()
    ashift_hint.set_halign(Gtk.Align.START)
    ashift_hint.set_line_wrap(True)
    grid.attach(ashift_hint, 1, 3, 1, 1)

    profile_label = Gtk.Label(label="Workload profile:")
    profile_label.set_halign(Gtk.Align.END)
    grid.attach(profile_label, 0, 4, 1, 1)
    profile_combo = Gtk.ComboBoxText()
    for profile_name in ctx.profiles:
        profile_combo.append_text(profile_name)
    profile_combo.set_active(0)
    grid.attach(profile_combo, 1, 4, 1, 1)
    profile_desc = Gtk.Label()
    profile_desc.set_halign(Gtk.Align.START)
    profile_desc.set_line_wrap(True)
    grid.attach(profile_desc, 1, 5, 1, 1)

    def _refresh_settings():
        name = _widget_text(name_entry, state.pool_name)
        ok, error = validate_pool_name(name, ctx.existing_names)
        name_feedback.set_text("Pool name OK" if ok else error)
        suggested = suggest_ashift(state.selected)
        if suggested is not None:
            ashift_hint.set_text(f"Suggested ashift for these disks: {suggested}")
        else:
            ashift_hint.set_text(
                "No physical sector-size information for the selected disks."
            )
        profile = ctx.profiles.get(state.profile_name, {})
        profile_desc.set_text(profile.get("description", ""))

    name_entry.connect("changed", _on_name_changed, state, on_change)
    ashift_combo.connect("changed", _on_ashift_changed, state, on_change)
    profile_combo.connect("changed", _on_profile_changed, state, on_change)
    state.page_refresh["settings"] = _refresh_settings
    return page


def _build_review_page(dialog, state: _WizardState, ctx: _WizardContext, on_change):
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

    command_label = Gtk.Label(label="Exact command that will run:")
    command_label.set_halign(Gtk.Align.START)
    page.pack_start(command_label, False, False, 0)
    command_buf = Gtk.TextBuffer()
    command_tv = Gtk.TextView(buffer=command_buf)
    command_tv.set_editable(False)
    command_tv.set_cursor_visible(False)
    command_tv.set_monospace(True)
    command_sw = Gtk.ScrolledWindow()
    command_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    command_sw.set_min_content_height(90)
    command_sw.add(command_tv)
    page.pack_start(command_sw, False, False, 0)

    dry_label = Gtk.Label(label="zpool create -n dry-run output:")
    dry_label.set_halign(Gtk.Align.START)
    page.pack_start(dry_label, False, False, 0)
    dry_status = Gtk.Label()
    dry_status.set_halign(Gtk.Align.START)
    dry_status.set_line_wrap(True)
    page.pack_start(dry_status, False, False, 0)
    dry_buf = Gtk.TextBuffer()
    dry_tv = Gtk.TextView(buffer=dry_buf)
    dry_tv.set_editable(False)
    dry_tv.set_cursor_visible(False)
    dry_tv.set_monospace(True)
    dry_sw = Gtk.ScrolledWindow()
    dry_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    dry_sw.set_min_content_height(160)
    dry_sw.add(dry_tv)
    page.pack_start(dry_sw, True, True, 0)

    summary = Gtk.Label()
    summary.set_halign(Gtk.Align.START)
    summary.set_line_wrap(True)
    page.pack_start(summary, False, False, 0)

    typed_hint = Gtk.Label()
    typed_hint.set_halign(Gtk.Align.START)
    typed_hint.set_line_wrap(True)
    page.pack_start(typed_hint, False, False, 0)
    typed_entry = Gtk.Entry()
    typed_entry.set_hexpand(True)
    page.pack_start(typed_entry, False, False, 0)
    typed_entry.connect("changed", _on_typed_changed, state, on_change)

    def _refresh_review():
        if state.command:
            command_buf.set_text(shlex.join(state.command))
        else:
            command_buf.set_text("(command unavailable — fix the problems above)")
        dry_buf.set_text(state.dry_run_output)
        if state.dry_run_rc is None:
            dry_status.set_text("")
        elif state.dry_run_rc == 0:
            dry_status.set_text("Dry run succeeded.")
        else:
            dry_status.set_markup(
                "<span foreground='red'>"
                "Dry run failed — fix the problem before creating."
                "</span>"
            )
        summary.set_text(_review_summary(state, ctx))
        typed_hint.set_text(
            f"Type the pool name '{state.pool_name}' exactly to enable Create."
        )

    state.page_refresh["review"] = _refresh_review
    return page


# ---------------------------------------------------------------------------
# Wizard shell
# ---------------------------------------------------------------------------


def _refresh_chrome(caption, back_btn, next_btn, create_btn, state, ctx) -> None:
    """Update step caption, button visibility, sensitivity, and tooltips."""
    index = PAGES.index(state.page)
    caption.set_text(f"Step {index + 1} of {len(PAGES)} — {_PAGE_TITLES[state.page]}")
    back_btn.set_sensitive(index > 0)
    problems = _page_problems(state.page, state, ctx)
    on_review = state.page == "review"
    next_btn.set_visible(not on_review)
    create_btn.set_visible(on_review)
    if on_review:
        create_btn.set_label(f"Create '{state.pool_name}'")
    primary = create_btn if on_review else next_btn
    primary.set_sensitive(not problems)
    primary.set_tooltip_text(problems[0] if problems else "")


def _show_validation_error(parent, message: str) -> None:
    """Show a modal warning and return (checkagainst_page idiom)."""
    err = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    err.run()
    err.destroy()


def _prepare_review(state: _WizardState, ctx: _WizardContext) -> None:
    """Build the command, run the dry run, and refresh the review page."""
    try:
        state.command = build_wizard_command(state, ctx.profiles)
    except ValueError as exc:
        state.command = []
        state.dry_run_rc = 1
        state.dry_run_output = f"could not build command: {exc}"
    else:
        try:
            state.dry_run_rc, state.dry_run_output = ctx.repository.create_pool_dry_run(
                state.command
            )
        except Exception as exc:  # pragma: no cover - defensive
            state.dry_run_rc = 1
            state.dry_run_output = f"dry run failed: {exc}"
    refresh = state.page_refresh.get("review")
    if refresh is not None:
        refresh()


def show_create_pool_wizard(app, eligibility, profiles, existing_names):
    """Run the create-pool wizard.

    Returns ``(pool_name, command)`` when the user confirms creation,
    or ``None`` when the wizard is cancelled.
    """
    if not profiles:
        log_msg("WARN: No filesystem workload profiles configured")
        return None
    state = _WizardState(
        eligibility=list(eligibility), profile_name=next(iter(profiles))
    )
    ctx = _WizardContext(
        app=app,
        profiles=profiles,
        existing_names=existing_names,
        repository=app.ctx.zfs_repository,
    )

    dialog = create_dialog(
        "Create Pool",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(820, 620),
    )
    back_btn = dialog.add_button("Back", _RESPONSE_BACK)
    next_btn = dialog.add_button("Next", _RESPONSE_NEXT)
    create_btn = dialog.add_button("Create", _RESPONSE_CREATE)

    content = dialog.get_content_area()
    caption = Gtk.Label()
    caption.set_halign(Gtk.Align.START)
    content.pack_start(caption, False, False, 0)
    stack = Gtk.Stack()
    content.pack_start(stack, True, True, 0)

    def _refresh():
        page_refresh = state.page_refresh.get(state.page)
        if page_refresh is not None:
            page_refresh()
        _refresh_chrome(caption, back_btn, next_btn, create_btn, state, ctx)

    pages = (
        ("disks", _build_disks_page(dialog, state, ctx, _refresh)),
        ("topology", _build_topology_page(dialog, state, ctx, _refresh)),
        ("settings", _build_settings_page(dialog, state, ctx, _refresh)),
        ("review", _build_review_page(dialog, state, ctx, _refresh)),
    )
    for name, widget in pages:
        stack.add_named(widget, name)
    stack.set_visible_child_name(state.page)

    dialog.show_all()
    try:
        while True:
            _refresh()
            response = dialog.run()
            if response in (
                Gtk.ResponseType.CANCEL,
                Gtk.ResponseType.DELETE_EVENT,
                Gtk.ResponseType.CLOSE,
            ):
                return None
            if response == _RESPONSE_BACK:
                index = PAGES.index(state.page)
                if index > 0:
                    state.page = PAGES[index - 1]
                    stack.set_visible_child_name(state.page)
                continue
            if response == _RESPONSE_NEXT:
                problems = _page_problems(state.page, state, ctx)
                if problems:
                    _show_validation_error(dialog, problems[0])
                    continue
                state.page = PAGES[PAGES.index(state.page) + 1]
                stack.set_visible_child_name(state.page)
                if state.page == "review":
                    _prepare_review(state, ctx)
                continue
            if response == _RESPONSE_CREATE:
                if _review_problems(state):
                    continue
                return state.pool_name, list(state.command)
    finally:
        dialog.destroy()


# ---------------------------------------------------------------------------
# Execution handler (Disks page action)
# ---------------------------------------------------------------------------


def _show_no_eligible_disks(app) -> None:
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text="No eligible disks for pool creation",
    )
    dialog.format_secondary_text(
        "Every disk is a pool member, partitioned, or lacks a /dev/disk/by-id "
        "path. Free a disk first (export or destroy its pool, or remove its "
        "partitions)."
    )
    dialog.run()
    dialog.destroy()


def _offer_register_pool(app, pool_name: str) -> None:
    """Offer to add the new pool to the registry (on_pools_add semantics)."""
    known_names = {pool["name"] for pool in app.known_pools}
    if pool_name in known_names:
        return
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Register pool '{pool_name}' in the pool registry?",
    )
    dialog.format_secondary_text(
        "The pool exists but is not in the registry yet, so backups and "
        "retention will not include it. Registration is persisted with the "
        "Pools tab Save button."
    )
    response = dialog.run()
    dialog.destroy()
    if response != Gtk.ResponseType.YES:
        return
    app.known_pools.append({"name": pool_name, "offsite_candidate": False})
    refresh_pools_page(app)
    log_msg(f"INFO: Added '{pool_name}' to pool registry (unsaved)")


def on_disks_create_pool(app) -> None:
    """Create a new pool from unused disks (Disks page action)."""
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Pool creation is available only on the storage host")
        return

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    repository = app.ctx.zfs_repository
    data = app._disks_inventory_cache.get()
    imported = _leaf_paths_by_pool(data.topologies)
    try:
        importable = repository.list_importable_pool_devices()
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not scan importable pools: {exc}")
        importable = {}
    eligibility = disk_eligibility(data.disks, imported, importable)
    if not any(result.eligible for result in eligibility):
        _show_no_eligible_disks(app)
        return

    profiles = {
        name: profile
        for name, profile in get_workload_profiles(app.config).items()
        if "filesystem" in profile.get("applies_to", [])
    }
    if not profiles:
        log_msg("WARN: No filesystem workload profiles configured")
        return
    existing_names = set(data.topologies) | repository.list_importable_pool_names()

    result = show_create_pool_wizard(app, eligibility, profiles, existing_names)
    if result is None:
        return
    pool_name, cmd = result

    lock_id = zlm.acquire(pool_name, "w", f"Create pool {pool_name}")
    step = BashStep(cmd, f"Create pool {pool_name}", is_rsync=False, fatal=True)

    def _on_complete(cancelled=False):
        zlm.release(lock_id)
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: Create Pool cancelled for {pool_name}")
            return
        log_msg(f"INFO: Pool '{pool_name}' created")
        _offer_register_pool(app, pool_name)

    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)
