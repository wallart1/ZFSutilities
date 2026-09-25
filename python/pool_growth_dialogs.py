"""Pool-growth dialogs — GTK UI and execution handlers for the Disks page.

Phase 4 operations (Add Data Vdev, Attach, Replace, Detach, and Add
Infrastructure Vdev) share two building blocks defined here:

- a checkbox disk picker (ineligible disks greyed out with the reason), and
- a review scaffold showing the exact command that will run, the warnings for
  the current selection, and a typed-confirmation entry that gates an
  insensitive Confirm button.

Every operation requires confirmation matched to its danger: typed
confirmation of the pool name where the brief demands it (Add Data Vdev,
RAIDZ expansion, Replace), a YES/NO warning dialog for the reversible attach
kinds (stripe to mirror, mirror grow). All decision logic is kept in pure helpers
(testable without GTK); ZFS I/O is delegated to ``ZfsRepository`` via the app
context, capability gating uses ``ctx.zfs_caps`` exclusively, and the
scrub-state check lives in ``pool_growth``.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field

import gi

gi.require_version("Gtk", "3.0")

import node_config
import zfs_lock_manager as zlm
from command_builders import BashStep
from disk_repository import DiskInfo, format_bytes
from disks_page import refresh_disks_page, update_disks_button_sensitivity
from gi.repository import Gtk
from gui_helpers import configure_treeview_column, create_scrolled_dialog
from logging_config import log_msg
from pool_create import TOPOLOGIES, EligibilityResult, disk_eligibility
from pool_create_wizard import _leaf_paths_by_pool
from pool_growth import (
    ATTACH_MIRROR_GROW,
    ATTACH_RAIDZ_EXPANSION,
    ATTACH_STRIPE_TO_MIRROR,
    _find_disk,
    assess_detach,
    classify_attach_target,
    classify_replace_source,
    count_mirror_members,
    has_mirror_member,
    infra_vdev_notes,
    mixed_size_warning,
    raidz_expansion_notes,
    resolve_member_by_id,
    scrub_blocks_pool_op,
    validate_growth_vdev_selection,
    validate_infra_vdev,
    validate_replace_pair,
)
from pools_page import on_pools_refresh
from zfs_repository import (
    TopologyNode,
    build_add_vdev_command,
    build_attach_command,
    build_detach_command,
    build_replace_command,
)

# Custom dialog response id for the Confirm button. Distinct from
# Gtk.ResponseType values (which are negative) and from the wizard's ids.
_RESPONSE_CONFIRM = 12

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

# Target-tree TreeStore columns:
#   0 name, 1 vdev type, 2 state (with gating suffix), 3 foreground, 4 node,
#   5 size text
(
    _TCOL_NAME,
    _TCOL_TYPE,
    _TCOL_STATE,
    _TCOL_FG,
    _TCOL_NODE,
    _TCOL_SIZE,
) = range(6)

# Vdev group types whose tree rows are greyed out when RAIDZ expansion is
# unsupported (mirror/stripe rows are always valid attach targets).
_GATED_VDEV_TYPES = ("raidz1", "raidz2", "raidz3")


@dataclass
class _AddVdevState:
    """Mutable Add-Data-Vdev dialog state."""

    pools: list[str]  # imported pool names (sorted)
    pool_name: str  # "" until a pool is picked
    eligibility: list[EligibilityResult]
    selected: list[DiskInfo] = field(default_factory=list)
    topology: str = "mirror"
    typed: str = ""  # review-page typed confirmation
    command: list[str] = field(default_factory=list)


@dataclass
class _AttachState:
    """Mutable Attach dialog state."""

    pools: list[str]  # imported pool names (sorted)
    pool_name: str  # "" until a pool is picked
    topologies: dict[str, TopologyNode]  # imported pool topology trees
    eligibility: list[EligibilityResult]
    disks: list[DiskInfo]  # full inventory (by-id resolution of members)
    target: TopologyNode | None = None  # selected topology tree node
    selected: list[DiskInfo] = field(default_factory=list)  # exactly 1 disk
    typed: str = ""  # review-page typed confirmation (RAIDZ expansion only)
    command: list[str] = field(default_factory=list)
    kind: str = ""  # AttachTarget kind for the current selection


@dataclass
class _ReplaceState:
    """Mutable Replace dialog state."""

    pools: list[str]  # imported pool names (sorted)
    pool_name: str  # "" until a pool is picked
    topologies: dict[str, TopologyNode]  # imported pool topology trees
    eligibility: list[EligibilityResult]
    disks: list[DiskInfo]  # full inventory (by-id resolution of members)
    target: TopologyNode | None = None  # selected topology tree node (source)
    selected: list[DiskInfo] = field(default_factory=list)  # exactly 1 disk
    typed: str = ""  # review-page typed confirmation (always required)
    command: list[str] = field(default_factory=list)


@dataclass
class _DetachState:
    """Mutable Detach dialog state."""

    pools: list[str]  # imported pool names (sorted)
    pool_name: str  # "" until a pool is picked
    topologies: dict[str, TopologyNode]  # imported pool topology trees
    disks: list[DiskInfo]  # full inventory (by-id resolution of members)
    target: TopologyNode | None = None  # selected mirror leaf in the topology tree
    typed: str = ""  # review-page typed confirmation (always required)
    command: list[str] = field(default_factory=list)


@dataclass
class _InfraVdevState:
    """Mutable Add-Infra-Vdev dialog state."""

    pools: list[str]  # imported pool names (sorted)
    pool_name: str  # "" until a pool is picked
    eligibility: list[EligibilityResult]
    kind: str = "special"  # "special", "log", or "cache"
    selected: list[DiskInfo] = field(default_factory=list)
    typed: str = ""  # review-page typed confirmation (special only)
    checked: bool = False  # checkbox acknowledgment (log only)
    command: list[str] = field(default_factory=list)


@dataclass
class _GrowthDialogContext:
    """Inputs the dialog builders need, bundled to keep signatures short."""

    app: object
    repository: object  # ZfsRepository (for the scrub check)


# ---------------------------------------------------------------------------
# Pure helpers (no GTK, no subprocess) — unit-tested directly
# ---------------------------------------------------------------------------


def build_add_vdev_argv(state: _AddVdevState) -> list[str]:
    """Build the exact ``zpool add`` argv for the current dialog state."""
    by_id_paths = [os.path.join(_BY_ID_DIR, disk.by_id) for disk in state.selected]
    return build_add_vdev_command(state.pool_name, state.topology, by_id_paths)


def _add_vdev_warnings(state: _AddVdevState) -> list[str]:
    """Informational warnings for the pool/disks the user selected."""
    warnings: list[str] = []
    for result in state.eligibility:
        if result.disk in state.selected:
            warnings.extend(result.warnings)
    mixed = mixed_size_warning(state.selected)
    if mixed:
        warnings.append(mixed)
    return warnings


def _add_vdev_problems(state: _AddVdevState) -> list[str]:
    """Return human-readable problems blocking the Add action, in order."""
    if not state.pool_name or state.pool_name not in state.pools:
        return ["Select a pool"]
    if not state.selected:
        return ["Select at least one eligible disk"]
    spec = TOPOLOGIES[state.topology]
    if len(state.selected) < spec.min_disks:
        return [f"{state.topology} requires at least {spec.min_disks} disks"]
    problems = validate_growth_vdev_selection(state.selected)
    if problems:
        return problems
    try:
        state.command = build_add_vdev_argv(state)
    except ValueError as exc:
        state.command = []
        return [str(exc)]
    if state.typed != state.pool_name:
        return [f"Type the pool name '{state.pool_name}' to confirm"]
    return []


def _classify_attach(state: _AttachState):
    """Classify the current target, or return an AttachTarget carrying an error."""
    root = state.topologies.get(state.pool_name)
    if root is None or state.target is None:
        return None
    return classify_attach_target(root, state.target, state.disks)


def build_attach_argv(state: _AttachState) -> list[str]:
    """Build the exact ``zpool attach`` argv for the current dialog state.

    Returns an empty list (and leaves ``state.command`` empty) when the
    selection is incomplete or refused; the refusal text comes from
    ``_attach_problems``.
    """
    state.command = []
    classified = _classify_attach(state)
    if classified is None or classified.error or len(state.selected) != 1:
        return []
    new_path = os.path.join(_BY_ID_DIR, state.selected[0].by_id)
    state.command = build_attach_command(state.pool_name, classified.target_arg, new_path)
    return state.command


def _attach_problems(state: _AttachState, caps) -> list[str]:
    """Return human-readable problems blocking the Attach action, in order."""
    state.kind = ""
    if not state.pool_name or state.pool_name not in state.pools:
        return ["Select a pool"]
    root = state.topologies.get(state.pool_name)
    if root is None:
        return ["Select a pool"]
    if state.target is None:
        return ["Select a target member or raidz group in the topology tree"]
    classified = classify_attach_target(root, state.target, state.disks)
    if classified.error:
        return [classified.error]
    state.kind = classified.kind
    if classified.kind == ATTACH_RAIDZ_EXPANSION and not caps.supports("raidz_expansion"):
        return [caps.requires("raidz_expansion")]
    if len(state.selected) != 1:
        return ["Select exactly one eligible disk"]
    for result in state.eligibility:
        if result.disk in state.selected and not result.eligible:
            return list(result.reasons) or [f"disk {result.disk.path} is not eligible"]
    command = []
    try:
        command = build_attach_argv(state)
    except ValueError as exc:
        state.command = []
        return [str(exc)]
    if not command:
        return ["command unavailable — fix the problems above"]
    if classified.kind == ATTACH_RAIDZ_EXPANSION and state.typed != state.pool_name:
        return [f"Type the pool name '{state.pool_name}' to confirm"]
    return []


def _attach_warnings(state: _AttachState) -> list[str]:
    """Warnings for the current attach selection, tailored to the attach kind."""
    warnings: list[str] = []
    classified = _classify_attach(state)
    root = state.topologies.get(state.pool_name)
    if classified is not None and not classified.error and root is not None:
        if classified.kind == ATTACH_STRIPE_TO_MIRROR:
            warnings.append("attaching a second device converts the stripe vdev into a mirror")
            warnings.append(
                "if the goal is more capacity without mirroring, use Add Data "
                "Vdev with the stripe topology instead — it adds a new "
                "top-level stripe vdev"
            )
        elif classified.kind == ATTACH_MIRROR_GROW:
            count = count_mirror_members(root, state.target)
            if count:
                warnings.append(f"this grows the mirror from {count} to {count + 1} members")
            else:
                warnings.append("this grows the mirror by one member")
        elif classified.kind == ATTACH_RAIDZ_EXPANSION:
            warnings.extend(raidz_expansion_notes())
    for result in state.eligibility:
        if result.disk in state.selected:
            warnings.extend(result.warnings)
    return warnings


def _attach_typed_required(state: _AttachState) -> bool:
    """True when the selection needs typed confirmation (RAIDZ expansion)."""
    classified = _classify_attach(state)
    return bool(
        classified is not None
        and not classified.error
        and classified.kind == ATTACH_RAIDZ_EXPANSION
    )


def _attach_confirm_text(state: _AttachState) -> tuple[str, str]:
    """Primary/secondary text for the stripe/mirror YES/NO warning dialog."""
    new_name = state.selected[0].by_id if state.selected else "(no disk selected)"
    primary = f"Attach '{new_name}' to expand the vdev in pool '{state.pool_name}'?"
    classified = _classify_attach(state)
    if classified is not None and classified.kind == ATTACH_STRIPE_TO_MIRROR:
        secondary = (
            "This converts the stripe vdev into a mirror: the new device becomes "
            "a redundant copy of the existing one."
        )
    else:
        secondary = "This adds the new device as another member of the mirror."
    return primary, secondary


# ---------------------------------------------------------------------------
# Replace Device pure helpers
# ---------------------------------------------------------------------------

_RESILVER_NOTE = (
    "after the replace starts the pool shows 'resilvering' in the topology "
    "pane; watch live progress in the Pools tab Watch window"
)


def _classify_replace(state: _ReplaceState):
    """Classify the current source target, or return a ReplaceSource with an error."""
    root = state.topologies.get(state.pool_name)
    if root is None or state.target is None:
        return None
    return classify_replace_source(root, state.target, state.disks)


def build_replace_argv(state: _ReplaceState) -> list[str]:
    """Build the exact ``zpool replace`` argv for the current dialog state.

    Returns an empty list (and leaves ``state.command`` empty) when the
    selection is incomplete or refused; the refusal text comes from
    ``_replace_problems``.
    """
    state.command = []
    classified = _classify_replace(state)
    if classified is None or classified.error or len(state.selected) != 1:
        return []
    new_path = os.path.join(_BY_ID_DIR, state.selected[0].by_id)
    state.command = build_replace_command(state.pool_name, classified.by_id, new_path)
    return state.command


def _replace_problems(state: _ReplaceState) -> list[str]:
    """Return human-readable problems blocking the Replace action, in order."""
    if not state.pool_name or state.pool_name not in state.pools:
        return ["Select a pool"]
    root = state.topologies.get(state.pool_name)
    if root is None:
        return ["Select a pool"]
    if state.target is None:
        return ["Select the pool member to replace in the topology tree"]
    classified = classify_replace_source(root, state.target, state.disks)
    if classified.error:
        return [classified.error]
    if len(state.selected) != 1:
        return ["Select exactly one eligible disk"]
    for result in state.eligibility:
        if result.disk in state.selected and not result.eligible:
            return list(result.reasons) or [f"disk {result.disk.path} is not eligible"]
    problems, _warnings = validate_replace_pair(classified.by_id, state.selected[0], state.disks)
    if problems:
        return problems
    command = []
    try:
        command = build_replace_argv(state)
    except ValueError as exc:
        state.command = []
        return [str(exc)]
    if not command:
        return ["command unavailable — fix the problems above"]
    if state.typed != state.pool_name:
        return [f"Type the pool name '{state.pool_name}' to confirm"]
    return []


def _replace_warnings(state: _ReplaceState) -> list[str]:
    """Warnings for the current replace selection (smaller replacement, resilver)."""
    warnings: list[str] = []
    classified = _classify_replace(state)
    if classified is not None and not classified.error and len(state.selected) == 1:
        _problems, pair_warnings = validate_replace_pair(
            classified.by_id, state.selected[0], state.disks
        )
        warnings.extend(pair_warnings)
        warnings.append(_RESILVER_NOTE)
    for result in state.eligibility:
        if result.disk in state.selected:
            warnings.extend(result.warnings)
    return warnings


# ---------------------------------------------------------------------------
# Detach Device pure helpers
# ---------------------------------------------------------------------------


def build_detach_argv(state: _DetachState) -> list[str]:
    """Build the exact ``zpool detach`` argv for the current dialog state.

    Returns an empty list (and leaves ``state.command`` empty) when the
    selection is incomplete or refused; the refusal text comes from
    ``_detach_problems``.
    """
    state.command = []
    if state.target is None:
        return []
    by_id = resolve_member_by_id(state.target.name, state.disks)
    if by_id is None:
        return []
    state.command = build_detach_command(state.pool_name, by_id)
    return state.command


def _detach_problems(state: _DetachState) -> list[str]:
    """Return human-readable problems blocking the Detach action, in order."""
    if not state.pool_name or state.pool_name not in state.pools:
        return ["Select a pool"]
    root = state.topologies.get(state.pool_name)
    if root is None:
        return ["Select a pool"]
    if state.target is None:
        if not has_mirror_member(root):
            return [f"Pool '{state.pool_name}' has no mirror members to detach"]
        return ["Select the mirror member to detach in the topology tree"]
    error, _warnings = assess_detach(root, state.target)
    if error:
        return [error]
    if resolve_member_by_id(state.target.name, state.disks) is None:
        return [f"member {state.target.name} has no /dev/disk/by-id path to detach"]
    command = []
    try:
        command = build_detach_argv(state)
    except ValueError as exc:
        state.command = []
        return [str(exc)]
    if not command:
        return ["command unavailable — fix the problems above"]
    if state.typed != state.pool_name:
        return [f"Type the pool name '{state.pool_name}' to confirm"]
    return []


def _detach_warnings(state: _DetachState) -> list[str]:
    """Warnings for the current detach selection (redundancy loss, irreversibility)."""
    root = state.topologies.get(state.pool_name)
    if root is None or state.target is None:
        return []
    _error, warnings = assess_detach(root, state.target)
    return warnings


# ---------------------------------------------------------------------------
# Infrastructure vdev pure helpers
# ---------------------------------------------------------------------------


def _infra_topology(selected: list[DiskInfo]) -> str:
    """Map a disk selection to its vdev topology: mirror for 2+ disks, else stripe."""
    return "mirror" if len(selected) >= 2 else "stripe"


def build_infra_argv(state: _InfraVdevState) -> list[str]:
    """Build the exact ``zpool add`` argv for an infrastructure vdev."""
    by_id_paths = [os.path.join(_BY_ID_DIR, disk.by_id) for disk in state.selected]
    return build_add_vdev_command(
        state.pool_name, _infra_topology(state.selected), by_id_paths, kind=state.kind
    )


def _infra_problems(state: _InfraVdevState) -> list[str]:
    """Return human-readable problems blocking the Add action, in order."""
    if not state.pool_name or state.pool_name not in state.pools:
        return ["Select a pool"]
    if not state.selected:
        return ["Select at least one eligible disk"]
    for result in state.eligibility:
        if result.disk in state.selected and not result.eligible:
            return list(result.reasons) or [f"disk {result.disk.path} is not eligible"]
    problems, _warnings = validate_infra_vdev(
        state.kind, _infra_topology(state.selected), state.selected
    )
    if problems:
        state.command = []
        return problems
    try:
        state.command = build_infra_argv(state)
    except ValueError as exc:
        state.command = []
        return [str(exc)]
    if state.kind == "special" and state.typed != state.pool_name:
        return [f"Type the pool name '{state.pool_name}' to confirm"]
    if state.kind == "log" and not state.checked:
        return ["Check the acknowledgment box to confirm"]
    return []


def _infra_checkbox_label(state: _InfraVdevState) -> str:
    """Acknowledgment text for the log-device confirmation checkbox."""
    if _infra_topology(state.selected) == "stripe":
        return (
            "I understand that this single log device only accelerates sync "
            "writes and that its failure removes the acceleration until it is "
            "replaced"
        )
    return (
        "I understand that a log device only accelerates synchronous writes and holds no pool data"
    )


def _infra_warnings(state: _InfraVdevState) -> list[str]:
    """Warnings for the current infra-vdev selection, tailored to the kind."""
    warnings: list[str] = []
    try:
        warnings.extend(infra_vdev_notes(state.kind))
    except ValueError:
        pass  # unknown kind is reported as a problem instead
    if state.selected:
        _problems, validate_warnings = validate_infra_vdev(
            state.kind, _infra_topology(state.selected), state.selected
        )
        warnings.extend(validate_warnings)
    for result in state.eligibility:
        if result.disk in state.selected:
            warnings.extend(result.warnings)
    mixed = mixed_size_warning(state.selected)
    if mixed:
        warnings.append(mixed)
    return warnings


# ---------------------------------------------------------------------------
# Widget-text helpers (tolerate mocks that return non-strings)
# ---------------------------------------------------------------------------


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


def _selected_disks(store, state: _AddVdevState | _InfraVdevState) -> list[DiskInfo]:
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


def _untoggle_other_rows(store, keep_iter) -> None:
    """Untick every disk row except *keep_iter* (single-selection picker)."""
    keep_path = store.get_path(keep_iter)
    tree_iter = store.get_iter_first()
    while tree_iter:
        if store.get_path(tree_iter) != keep_path:
            store.set_value(tree_iter, _COL_USE, False)
        tree_iter = store.iter_next(tree_iter)


def _on_disk_toggled(
    toggle,
    path,
    store,
    state: _AttachState | _AddVdevState | _ReplaceState | _DetachState | _InfraVdevState,
    on_change,
    single=False,
) -> None:
    tree_iter = store.get_iter(path)
    if not store.get_value(tree_iter, _COL_ELIGIBLE):
        return
    use = not store.get_value(tree_iter, _COL_USE)
    store.set_value(tree_iter, _COL_USE, use)
    if use and single:
        _untoggle_other_rows(store, tree_iter)
    state.selected = _selected_disks(store, state)
    on_change()


def _on_pool_changed(combo, state: _AddVdevState | _InfraVdevState, on_change) -> None:
    text = _combo_text(combo)
    if text:
        state.pool_name = text
    on_change()


def _on_kind_changed(combo, state: _InfraVdevState, on_change) -> None:
    text = _combo_text(combo)
    if text:
        state.kind = text
    on_change()


def _on_infra_checked(checkbox, state: _InfraVdevState, on_change) -> None:
    state.checked = bool(checkbox.get_active())
    on_change()


def _on_topology_toggled(radio, name: str, state: _AddVdevState, on_change) -> None:
    active = radio.get_active()
    if isinstance(active, bool) and not active:
        return  # deactivation signal from the previously selected radio
    state.topology = name
    on_change()


def _on_typed_changed(
    entry,
    state: _AttachState | _AddVdevState | _ReplaceState | _DetachState | _InfraVdevState,
    on_change,
) -> None:
    state.typed = _widget_text(entry, state.typed)
    on_change()


def _on_target_changed(
    selection, store, state: _AttachState | _ReplaceState | _DetachState, on_change
) -> None:
    """Record the topology node the user selected in the target tree."""
    _model, tree_iter = selection.get_selected()
    if tree_iter is None:
        state.target = None
    else:
        state.target = store.get_value(tree_iter, _TCOL_NODE)
    on_change()


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------


def _build_disk_picker(
    state: _AddVdevState | _InfraVdevState, on_change, hint_text: str, single: bool = False
):
    """Build the checkbox disk-inventory picker shared by the growth dialogs.

    With *single* True (Attach) ticking a row unticks every other row so the
    operation always has exactly one new device selected.
    """
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

    hint = Gtk.Label(label=hint_text)
    hint.set_halign(Gtk.Align.START)
    hint.set_line_wrap(True)
    page.pack_start(hint, False, False, 0)

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
    toggle.connect("toggled", _on_disk_toggled, store, state, on_change, single)
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
        tree_column = Gtk.TreeViewColumn(title, renderer, text=column_index, foreground=_COL_FG)
        configure_treeview_column(tree_column, width=width)
        view.append_column(tree_column)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_min_content_height(200)
    scrolled.add(view)
    page.pack_start(scrolled, True, True, 0)
    return page


class _ReviewScaffold:
    """Shared review area: exact-command preview, warnings, typed confirmation.

    Deliberately op-agnostic — the caller passes the command argv, the warning
    lines, and the typed-confirmation target on every refresh so the Attach,
    Replace, Detach, and infrastructure-vdev dialogs can reuse it unchanged.
    """

    def __init__(self, parent_box, on_change):
        command_label = Gtk.Label(label="Exact command that will run:")
        command_label.set_halign(Gtk.Align.START)
        parent_box.pack_start(command_label, False, False, 0)
        self._command_buf = Gtk.TextBuffer()
        command_tv = Gtk.TextView(buffer=self._command_buf)
        command_tv.set_editable(False)
        command_tv.set_cursor_visible(False)
        command_tv.set_monospace(True)
        command_sw = Gtk.ScrolledWindow()
        command_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        command_sw.set_min_content_height(90)
        command_sw.add(command_tv)
        parent_box.pack_start(command_sw, False, False, 0)

        self._warnings_label = Gtk.Label()
        self._warnings_label.set_halign(Gtk.Align.START)
        self._warnings_label.set_line_wrap(True)
        parent_box.pack_start(self._warnings_label, False, False, 0)

        self._typed_hint = Gtk.Label()
        self._typed_hint.set_halign(Gtk.Align.START)
        self._typed_hint.set_line_wrap(True)
        parent_box.pack_start(self._typed_hint, False, False, 0)
        self.typed_entry = Gtk.Entry()
        self.typed_entry.set_hexpand(True)
        parent_box.pack_start(self.typed_entry, False, False, 0)

        self.confirm_checkbox = Gtk.CheckButton()
        self.confirm_checkbox.connect("toggled", lambda _btn: on_change())
        parent_box.pack_start(self.confirm_checkbox, False, False, 0)
        self.confirm_checkbox.hide()

    def refresh(
        self,
        command: list[str],
        warnings: list[str],
        typed_target: str | None = None,
        checkbox_label: str | None = None,
    ) -> None:
        """Update the preview and warnings; hide typing unless *typed_target*.

        ``typed_target=None`` (stripe/mirror Attach, cache infra vdev) hides the
        typed entry; otherwise the hint asks for the pool name exactly.
        ``checkbox_label`` shows the acknowledgment checkbox instead (log
        infra vdev); pass None to hide it.
        """
        if command:
            self._command_buf.set_text(shlex.join(command))
        else:
            self._command_buf.set_text("(command unavailable — fix the problems above)")
        if warnings:
            self._warnings_label.set_text(
                "Warnings:\n" + "\n".join(f"• {warning}" for warning in warnings)
            )
        else:
            self._warnings_label.set_text("")
        if typed_target is None:
            self._typed_hint.hide()
            self.typed_entry.hide()
        else:
            self._typed_hint.show()
            self.typed_entry.show()
            self._typed_hint.set_text(
                f"Type the pool name '{typed_target}' exactly to enable the action."
            )
        if checkbox_label is None:
            self.confirm_checkbox.hide()
        else:
            self.confirm_checkbox.set_label(checkbox_label)
            self.confirm_checkbox.show()


def _show_info_dialog(parent, text: str, secondary: str = "") -> None:
    """Show a modal info dialog and return (checkagainst_page idiom)."""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=text,
    )
    if secondary:
        dialog.format_secondary_text(secondary)
    dialog.run()
    dialog.destroy()


def _show_yes_no_dialog(parent, text: str, secondary: str = "") -> bool:
    """Show a modal YES/NO question dialog; return True when answered YES."""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=text,
    )
    if secondary:
        dialog.format_secondary_text(secondary)
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.YES


# ---------------------------------------------------------------------------
# Add Data Vdev dialog
# ---------------------------------------------------------------------------


def show_add_vdev_dialog(app, pools, eligibility, preselected_pool):
    """Run the Add-Data-Vdev dialog.

    Returns ``(pool_name, command)`` when the user confirms the addition,
    or ``None`` when the dialog is cancelled.
    """
    pools = list(pools)
    if preselected_pool in pools:
        initial_pool = preselected_pool
    else:
        initial_pool = pools[0] if pools else ""
    state = _AddVdevState(pools=pools, pool_name=initial_pool, eligibility=list(eligibility))
    ctx = _GrowthDialogContext(app=app, repository=app.ctx.zfs_repository)

    dialog, content = create_scrolled_dialog(
        "Add Data Vdev",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(820, 700),
    )
    confirm_btn = dialog.add_button("Add", _RESPONSE_CONFIRM)

    pool_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pool_label = Gtk.Label(label="Pool:")
    pool_label.set_halign(Gtk.Align.END)
    pool_row.pack_start(pool_label, False, False, 0)
    pool_combo = Gtk.ComboBoxText()
    for pool_name in state.pools:
        pool_combo.append_text(pool_name)
    pool_combo.set_active(
        state.pools.index(state.pool_name) if state.pool_name in state.pools else 0
    )
    pool_combo.set_hexpand(True)
    pool_row.pack_start(pool_combo, True, True, 0)
    content.pack_start(pool_row, False, False, 0)

    def _refresh():
        state.command = []
        problems = _add_vdev_problems(state)
        scaffold.refresh(state.command, _add_vdev_warnings(state), state.pool_name)
        confirm_btn.set_label(f"Add to '{state.pool_name}'")
        confirm_btn.set_sensitive(not problems)
        confirm_btn.set_tooltip_text(problems[0] if problems else "")

    pool_combo.connect("changed", _on_pool_changed, state, _refresh)
    content.pack_start(
        _build_disk_picker(
            state,
            _refresh,
            "Select the disks for the new data vdev. Disks already in any "
            "pool or otherwise unusable are greyed out.",
        ),
        True,
        True,
        0,
    )

    topology_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    topology_label = Gtk.Label(label="Topology:")
    topology_label.set_halign(Gtk.Align.START)
    topology_box.pack_start(topology_label, False, False, 0)
    radio_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    topology_box.pack_start(radio_stack, False, False, 0)
    group = None
    radios = []
    for name, spec in TOPOLOGIES.items():
        label_text = f"{name} (minimum {spec.min_disks} disks)"
        if group is None:
            radio = Gtk.RadioButton(label=label_text)
            group = radio
        else:
            radio = Gtk.RadioButton.new_from_widget(group)
            radio.set_label(label_text)
        radios.append((radio, name))
        radio.set_halign(Gtk.Align.START)
        radio_stack.pack_start(radio, False, False, 0)
        if name == state.topology:
            radio.set_active(True)
    content.pack_start(topology_box, False, False, 0)
    raid10_hint = Gtk.Label(
        label=(
            "Adding a mirror vdev to a pool of mirror vdevs extends a "
            "RAID10 (striped-mirror) layout."
        )
    )
    raid10_hint.set_halign(Gtk.Align.START)
    raid10_hint.set_line_wrap(True)
    content.pack_start(raid10_hint, False, False, 0)
    # GTK emits "toggled" from set_active during construction; connect only
    # after the initial state is set or the handler runs before the review
    # scaffold exists (NameError on the closure's free variable).
    for radio, name in radios:
        radio.connect("toggled", _on_topology_toggled, name, state, _refresh)

    scaffold = _ReviewScaffold(content, _refresh)
    scaffold.typed_entry.connect("changed", _on_typed_changed, state, _refresh)

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
            if response == _RESPONSE_CONFIRM:
                problems = _add_vdev_problems(state)
                if problems:
                    continue
                blocker = scrub_blocks_pool_op(state.pool_name, ctx.repository)
                if blocker is not None:
                    _show_info_dialog(dialog, blocker)
                    continue
                return state.pool_name, list(state.command)
    finally:
        dialog.destroy()


# ---------------------------------------------------------------------------
# Expand Vdev dialog (zpool attach)
# ---------------------------------------------------------------------------


def _node_size_text(node: TopologyNode, disks: list[DiskInfo]) -> str:
    """Human-readable size for a topology tree row.

    Leaf rows show the inventory disk's size ("-" when the member cannot be
    resolved, e.g. a spare absent from the inventory). Group and pool rows
    show the summed size of their leaf descendants.
    """
    if node.vdev_type == "disk":
        disk = _find_disk(node.name, disks)
        return format_bytes(disk.size_bytes) if disk is not None else "-"
    total = 0
    leaves = list(node.children)
    while leaves:
        child = leaves.pop()
        if child.vdev_type == "disk":
            disk = _find_disk(child.name, disks)
            if disk is not None:
                total += disk.size_bytes
        else:
            leaves.extend(child.children)
    return format_bytes(total) if total > 0 else "-"


def _populate_target_store(
    store,
    state: _AttachState | _ReplaceState | _DetachState,
    caps,
    gate_raidz: bool = True,
    detach_targets: bool = False,
) -> None:
    """Fill the target tree with the selected pool's topology.

    Raidz group rows are greyed out with the ``requires()`` text when the
    running kernel module does not support RAIDZ expansion, and the greying
    is inherited by their child device rows (GTK3 trees cannot
    disable individual rows, so gating also happens in ``_attach_problems``).
    Pass ``gate_raidz=False`` for dialogs (Replace, Detach) where raidz rows are
    not gated on the RAIDZ-expansion capability.
    Pass ``detach_targets=True`` for the Detach dialog, where only disk
    members of a mirror vdev are detachable: every other row is greyed out
    (mirroring ``assess_detach``'s acceptance rule).
    """
    store.clear()
    root = state.topologies.get(state.pool_name)
    if root is None:
        return
    raidz_supported = caps.supports("raidz_expansion")

    def _fill(node, parent_iter, greyed=False, parent=None) -> None:
        foreground = _INELIGIBLE_FG if greyed else None
        status = node.state
        if gate_raidz and node.vdev_type in _GATED_VDEV_TYPES and not raidz_supported:
            foreground = _INELIGIBLE_FG
            status = f"{node.state} — {caps.requires('raidz_expansion')}"
            greyed = True
        if detach_targets:
            # The detach rule is authoritative: mirror members re-enable a row
            # even when a greyed parent group would have inherited greying.
            if node.vdev_type == "disk" and parent is not None and parent.vdev_type == "mirror":
                foreground = None
                greyed = False
            else:
                foreground = _INELIGIBLE_FG
                greyed = True
        tree_iter = store.append(
            parent_iter,
            [
                node.name,
                node.vdev_type,
                status,
                foreground,
                node,
                _node_size_text(node, state.disks),
            ],
        )
        for child in node.children:
            _fill(child, tree_iter, greyed, node)

    _fill(root, None)


def _build_target_tree(
    state: _AttachState | _ReplaceState | _DetachState,
    on_change,
    caps,
    gate_raidz: bool = True,
    hint_text: str | None = None,
    detach_targets: bool = False,
):
    """Build the topology target picker: one pool's vdev tree, single select.

    *hint_text* overrides the default Attach/Replace hint (e.g. Detach passes
    its mirror-only reminder).
    """
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

    if hint_text is None:
        if gate_raidz:
            hint_text = (
                "Select the stripe member, mirror member, or raidz group to "
                "expand. Raidz groups expand via RAIDZ expansion and require "
                "OpenZFS 2.3+ (their rows are greyed when unsupported)."
            )
        else:
            hint_text = (
                "Select the pool member to replace. Any disk member of a data or "
                "infrastructure vdev can be replaced."
            )
    hint = Gtk.Label(label=hint_text)
    hint.set_halign(Gtk.Align.START)
    hint.set_line_wrap(True)
    page.pack_start(hint, False, False, 0)

    store = Gtk.TreeStore(str, str, str, str, object, str)
    _populate_target_store(store, state, caps, gate_raidz=gate_raidz, detach_targets=detach_targets)
    view = Gtk.TreeView(model=store)
    view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
    view.get_selection().connect("changed", _on_target_changed, store, state, on_change)

    for title, column_index, width in (
        ("Member / group", _TCOL_NAME, 280),
        ("Type", _TCOL_TYPE, 90),
        ("Size", _TCOL_SIZE, 90),
        ("State", _TCOL_STATE, 240),
    ):
        renderer = Gtk.CellRendererText()
        tree_column = Gtk.TreeViewColumn(title, renderer, text=column_index, foreground=_TCOL_FG)
        configure_treeview_column(tree_column, width=width)
        view.append_column(tree_column)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_min_content_height(160)
    scrolled.add(view)
    page.pack_start(scrolled, True, True, 0)
    return page, store, view


def show_attach_dialog(app, pools, topologies, eligibility, disks, preselected_pool, caps):
    """Run the Expand Vdev dialog (zpool attach).

    Returns ``(pool_name, command, kind)`` when the user confirms the expansion,
    where *kind* is one of the ``pool_growth.ATTACH_*`` constants, or ``None``
    when the dialog is cancelled.
    """
    pools = list(pools)
    if preselected_pool in pools:
        initial_pool = preselected_pool
    else:
        initial_pool = pools[0] if pools else ""
    state = _AttachState(
        pools=pools,
        pool_name=initial_pool,
        topologies=dict(topologies),
        eligibility=list(eligibility),
        disks=list(disks),
    )
    ctx = _GrowthDialogContext(app=app, repository=app.ctx.zfs_repository)

    dialog, content = create_scrolled_dialog(
        "Expand Vdev",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(820, 700),
    )
    confirm_btn = dialog.add_button("Expand", _RESPONSE_CONFIRM)

    pool_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pool_label = Gtk.Label(label="Pool:")
    pool_label.set_halign(Gtk.Align.END)
    pool_row.pack_start(pool_label, False, False, 0)
    pool_combo = Gtk.ComboBoxText()
    for pool_name in state.pools:
        pool_combo.append_text(pool_name)
    pool_combo.set_active(
        state.pools.index(state.pool_name) if state.pool_name in state.pools else 0
    )
    pool_combo.set_hexpand(True)
    pool_row.pack_start(pool_combo, True, True, 0)
    content.pack_start(pool_row, False, False, 0)

    def _refresh():
        state.command = []
        problems = _attach_problems(state, caps)
        typed_target = state.pool_name if _attach_typed_required(state) else None
        scaffold.refresh(state.command, _attach_warnings(state), typed_target)
        confirm_btn.set_label(f"Expand vdev in '{state.pool_name}'")
        confirm_btn.set_sensitive(not problems)
        confirm_btn.set_tooltip_text(problems[0] if problems else "")

    target_page, target_store, target_view = _build_target_tree(state, _refresh, caps)
    content.pack_start(target_page, True, True, 0)

    def _on_pool_combo_changed(combo):
        state.target = None
        _on_pool_changed(combo, state, _refresh)
        _populate_target_store(target_store, state, caps)
        target_view.expand_all()

    pool_combo.connect("changed", _on_pool_combo_changed)
    target_view.expand_all()

    content.pack_start(
        _build_disk_picker(
            state,
            _refresh,
            "Select the one disk to attach. Disks already in any pool or "
            "otherwise unusable are greyed out.",
            single=True,
        ),
        True,
        True,
        0,
    )

    scaffold = _ReviewScaffold(content, _refresh)
    scaffold.typed_entry.connect("changed", _on_typed_changed, state, _refresh)

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
            if response == _RESPONSE_CONFIRM:
                problems = _attach_problems(state, caps)
                if problems:
                    continue
                if not _attach_typed_required(state):
                    # Stripe->mirror and mirror grow: reversible, so a YES/NO
                    # warning dialog is the confirmation (no typed entry).
                    primary, secondary = _attach_confirm_text(state)
                    warn = Gtk.MessageDialog(
                        transient_for=dialog,
                        modal=True,
                        message_type=Gtk.MessageType.WARNING,
                        buttons=Gtk.ButtonsType.YES_NO,
                        text=primary,
                    )
                    warn.format_secondary_text(secondary)
                    answer = warn.run()
                    warn.destroy()
                    if answer != Gtk.ResponseType.YES:
                        continue
                blocker = scrub_blocks_pool_op(state.pool_name, ctx.repository)
                if blocker is not None:
                    _show_info_dialog(dialog, blocker)
                    continue
                return state.pool_name, list(state.command), state.kind
    finally:
        dialog.destroy()


# ---------------------------------------------------------------------------
# Replace Device dialog
# ---------------------------------------------------------------------------


def show_replace_dialog(app, pools, topologies, eligibility, disks, preselected_pool, caps):
    """Run the Replace Device dialog.

    Returns ``(pool_name, command)`` when the user confirms the replacement,
    or ``None`` when the dialog is cancelled. Typed confirmation of the pool
    name is always required (per the Phase 4 brief).
    """
    pools = list(pools)
    if preselected_pool in pools:
        initial_pool = preselected_pool
    else:
        initial_pool = pools[0] if pools else ""
    state = _ReplaceState(
        pools=pools,
        pool_name=initial_pool,
        topologies=dict(topologies),
        eligibility=list(eligibility),
        disks=list(disks),
    )
    ctx = _GrowthDialogContext(app=app, repository=app.ctx.zfs_repository)

    dialog, content = create_scrolled_dialog(
        "Replace Device",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(820, 700),
    )
    confirm_btn = dialog.add_button("Replace", _RESPONSE_CONFIRM)

    pool_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pool_label = Gtk.Label(label="Pool:")
    pool_label.set_halign(Gtk.Align.END)
    pool_row.pack_start(pool_label, False, False, 0)
    pool_combo = Gtk.ComboBoxText()
    for pool_name in state.pools:
        pool_combo.append_text(pool_name)
    pool_combo.set_active(
        state.pools.index(state.pool_name) if state.pool_name in state.pools else 0
    )
    pool_combo.set_hexpand(True)
    pool_row.pack_start(pool_combo, True, True, 0)
    content.pack_start(pool_row, False, False, 0)

    def _refresh():
        state.command = []
        problems = _replace_problems(state)
        scaffold.refresh(state.command, _replace_warnings(state), state.pool_name)
        confirm_btn.set_label(f"Replace in '{state.pool_name}'")
        confirm_btn.set_sensitive(not problems)
        confirm_btn.set_tooltip_text(problems[0] if problems else "")

    target_page, target_store, target_view = _build_target_tree(
        state, _refresh, caps, gate_raidz=False
    )
    content.pack_start(target_page, True, True, 0)

    def _on_pool_combo_changed(combo):
        state.target = None
        _on_pool_changed(combo, state, _refresh)
        _populate_target_store(target_store, state, caps, gate_raidz=False)
        target_view.expand_all()

    pool_combo.connect("changed", _on_pool_combo_changed)
    target_view.expand_all()

    content.pack_start(
        _build_disk_picker(
            state,
            _refresh,
            "Select the replacement disk. Disks already in any pool or "
            "otherwise unusable are greyed out; the source device cannot be "
            "its own replacement.",
            single=True,
        ),
        True,
        True,
        0,
    )

    scaffold = _ReviewScaffold(content, _refresh)
    scaffold.typed_entry.connect("changed", _on_typed_changed, state, _refresh)

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
            if response == _RESPONSE_CONFIRM:
                problems = _replace_problems(state)
                if problems:
                    continue
                blocker = scrub_blocks_pool_op(state.pool_name, ctx.repository)
                if blocker is not None:
                    _show_info_dialog(dialog, blocker)
                    continue
                return state.pool_name, list(state.command)
    finally:
        dialog.destroy()


# ---------------------------------------------------------------------------
# Detach Device dialog
# ---------------------------------------------------------------------------

_DETACH_HINT = (
    "Select the mirror member to detach. Only disk members of a mirror vdev "
    "can be detached; raidz and stripe members cannot."
)


def show_detach_dialog(app, pools, topologies, disks, preselected_pool):
    """Run the Detach Device dialog.

    Returns ``(pool_name, command)`` when the user confirms the detach, or
    ``None`` when the dialog is cancelled. Typed confirmation of the pool
    name is always required (detach is irreversible and reduces redundancy).
    """
    pools = list(pools)
    if preselected_pool in pools:
        initial_pool = preselected_pool
    else:
        initial_pool = pools[0] if pools else ""
    state = _DetachState(
        pools=pools,
        pool_name=initial_pool,
        topologies=dict(topologies),
        disks=list(disks),
    )
    ctx = _GrowthDialogContext(app=app, repository=app.ctx.zfs_repository)

    dialog, content = create_scrolled_dialog(
        "Detach Device",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(820, 560),
    )
    confirm_btn = dialog.add_button("Detach", _RESPONSE_CONFIRM)

    pool_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pool_label = Gtk.Label(label="Pool:")
    pool_label.set_halign(Gtk.Align.END)
    pool_row.pack_start(pool_label, False, False, 0)
    pool_combo = Gtk.ComboBoxText()
    for pool_name in state.pools:
        pool_combo.append_text(pool_name)
    pool_combo.set_active(
        state.pools.index(state.pool_name) if state.pool_name in state.pools else 0
    )
    pool_combo.set_hexpand(True)
    pool_row.pack_start(pool_combo, True, True, 0)
    content.pack_start(pool_row, False, False, 0)

    def _refresh():
        state.command = []
        problems = _detach_problems(state)
        scaffold.refresh(state.command, _detach_warnings(state), state.pool_name)
        confirm_btn.set_label(f"Detach from '{state.pool_name}'")
        confirm_btn.set_sensitive(not problems)
        confirm_btn.set_tooltip_text(problems[0] if problems else "")

    target_page, target_store, target_view = _build_target_tree(
        state,
        _refresh,
        app.ctx.zfs_caps,
        gate_raidz=False,
        hint_text=_DETACH_HINT,
        detach_targets=True,
    )
    content.pack_start(target_page, True, True, 0)

    def _on_pool_combo_changed(combo):
        state.target = None
        _on_pool_changed(combo, state, _refresh)
        _populate_target_store(
            target_store, state, app.ctx.zfs_caps, gate_raidz=False, detach_targets=True
        )
        target_view.expand_all()

    pool_combo.connect("changed", _on_pool_combo_changed)
    target_view.expand_all()

    scaffold = _ReviewScaffold(content, _refresh)
    scaffold.typed_entry.connect("changed", _on_typed_changed, state, _refresh)

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
            if response == _RESPONSE_CONFIRM:
                problems = _detach_problems(state)
                if problems:
                    continue
                blocker = scrub_blocks_pool_op(state.pool_name, ctx.repository)
                if blocker is not None:
                    _show_info_dialog(dialog, blocker)
                    continue
                return state.pool_name, list(state.command)
    finally:
        dialog.destroy()


# ---------------------------------------------------------------------------
# Add Infrastructure Vdev dialog
# ---------------------------------------------------------------------------


def show_add_infra_vdev_dialog(app, pools, eligibility, preselected_pool):
    """Run the Add-Infrastructure-Vdev dialog (special, log, or cache).

    Returns ``(pool_name, kind, command)`` when the user confirms the addition,
    or ``None`` when the dialog is cancelled. Confirmation matches the danger:
    typed pool-name confirmation for a special vdev (losing it loses the pool),
    a checkbox acknowledgment for a log device, and a YES/NO question for a
    cache device.
    """
    pools = list(pools)
    if preselected_pool in pools:
        initial_pool = preselected_pool
    else:
        initial_pool = pools[0] if pools else ""
    state = _InfraVdevState(pools=pools, pool_name=initial_pool, eligibility=list(eligibility))
    ctx = _GrowthDialogContext(app=app, repository=app.ctx.zfs_repository)

    dialog, content = create_scrolled_dialog(
        "Add Infrastructure Vdev",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(820, 700),
    )
    confirm_btn = dialog.add_button("Add", _RESPONSE_CONFIRM)

    pool_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pool_label = Gtk.Label(label="Pool:")
    pool_label.set_halign(Gtk.Align.END)
    pool_row.pack_start(pool_label, False, False, 0)
    pool_combo = Gtk.ComboBoxText()
    for pool_name in state.pools:
        pool_combo.append_text(pool_name)
    pool_combo.set_active(
        state.pools.index(state.pool_name) if state.pool_name in state.pools else 0
    )
    pool_combo.set_hexpand(True)
    pool_row.pack_start(pool_combo, True, True, 0)
    content.pack_start(pool_row, False, False, 0)

    kind_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    kind_label = Gtk.Label(label="Vdev kind:")
    kind_label.set_halign(Gtk.Align.END)
    kind_row.pack_start(kind_label, False, False, 0)
    kind_combo = Gtk.ComboBoxText()
    for kind in ("special", "log", "cache"):
        kind_combo.append_text(kind)
    kind_combo.set_active(0)
    kind_combo.set_hexpand(True)
    kind_row.pack_start(kind_combo, True, True, 0)
    content.pack_start(kind_row, False, False, 0)

    def _refresh():
        problems = _infra_problems(state)
        if state.kind == "special":
            scaffold.refresh(state.command, _infra_warnings(state), typed_target=state.pool_name)
        elif state.kind == "log":
            scaffold.refresh(
                state.command,
                _infra_warnings(state),
                checkbox_label=_infra_checkbox_label(state),
            )
        else:
            scaffold.refresh(state.command, _infra_warnings(state))
        confirm_btn.set_label(f"Add {state.kind} to '{state.pool_name}'")
        confirm_btn.set_sensitive(not problems)
        confirm_btn.set_tooltip_text(problems[0] if problems else "")

    pool_combo.connect("changed", _on_pool_changed, state, _refresh)
    kind_combo.connect("changed", _on_kind_changed, state, _refresh)
    content.pack_start(
        _build_disk_picker(
            state,
            _refresh,
            "Select the disks for the new infrastructure vdev. Disks already in "
            "any pool or otherwise unusable are greyed out. Two or more disks "
            "form a mirror; one disk is a single (stripe) device.",
        ),
        True,
        True,
        0,
    )

    scaffold = _ReviewScaffold(content, _refresh)
    scaffold.typed_entry.connect("changed", _on_typed_changed, state, _refresh)
    scaffold.confirm_checkbox.connect("toggled", _on_infra_checked, state, _refresh)

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
            if response == _RESPONSE_CONFIRM:
                problems = _infra_problems(state)
                if problems:
                    continue
                blocker = scrub_blocks_pool_op(state.pool_name, ctx.repository)
                if blocker is not None:
                    _show_info_dialog(dialog, blocker)
                    continue
                if state.kind == "cache" and not _show_yes_no_dialog(
                    dialog,
                    f"Add L2ARC read cache to pool '{state.pool_name}'?",
                    "A cache device holds no pool data and needs no redundancy.",
                ):
                    continue
                return state.pool_name, state.kind, list(state.command)
    finally:
        dialog.destroy()


# ---------------------------------------------------------------------------
# Execution handlers (Disks page actions)
# ---------------------------------------------------------------------------


def on_disks_add_vdev(app) -> None:
    """Add a new data vdev to an existing pool (Disks page action)."""
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Pool growth is available only on the storage host")
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
    pools = sorted(data.topologies)
    if not pools:
        log_msg("WARN: No imported pools to grow")
        return
    imported = _leaf_paths_by_pool(data.topologies)
    try:
        importable = repository.list_importable_pool_devices()
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not scan importable pools: {exc}")
        importable = {}
    eligibility = disk_eligibility(data.disks, imported, importable)
    if not any(result.eligible for result in eligibility):
        _show_info_dialog(
            app,
            "No eligible disks",
            "Every disk is a pool member, partitioned, or lacks a /dev/disk/by-id "
            "path. Free a disk first (export or destroy its pool, or remove its "
            "partitions).",
        )
        return

    preselected = app._disks_pool_selector.get_active_text()
    result = show_add_vdev_dialog(app, pools, eligibility, preselected)
    if result is None:
        return
    pool_name, cmd = result

    lock_id = zlm.acquire(pool_name, "w", f"Add vdev to {pool_name}")
    step = BashStep(cmd, f"Add vdev to pool {pool_name}", is_rsync=False, fatal=True)

    def _on_complete(cancelled=False, rc=None):
        zlm.release(lock_id)
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: Add vdev cancelled for {pool_name}")
            return
        if rc:
            log_msg(f"WARN: Add vdev failed for pool '{pool_name}' (rc={rc})")
            return
        log_msg(f"INFO: Added vdev to pool '{pool_name}'")

    runner.operation_detail = f"Add Data Vdev: {pool_name}"
    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)


def on_disks_detach_device(app) -> None:
    """Detach a mirror member from an existing pool vdev (Disks page action)."""
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Pool maintenance is available only on the storage host")
        return

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    data = app._disks_inventory_cache.get()
    pools = sorted(data.topologies)
    if not pools:
        log_msg("WARN: No imported pools to maintain")
        return
    if not any(has_mirror_member(root) for root in data.topologies.values()):
        _show_info_dialog(
            app,
            "No mirror members",
            "Detach only works on disk members of a mirror vdev, and no imported "
            "pool has one. Convert a stripe to a mirror (or grow a mirror) with "
            "the Expand Vdev action first.",
        )
        return

    preselected = app._disks_pool_selector.get_active_text()
    result = show_detach_dialog(app, pools, data.topologies, data.disks, preselected)
    if result is None:
        return
    pool_name, cmd = result

    lock_id = zlm.acquire(pool_name, "w", f"Detach device from {pool_name}")
    step = BashStep(cmd, f"Detach device from pool {pool_name}", is_rsync=False, fatal=True)

    def _on_complete(cancelled=False, rc=None):
        zlm.release(lock_id)
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: Detach cancelled for {pool_name}")
            return
        if rc:
            log_msg(f"WARN: Detach failed for pool '{pool_name}' (rc={rc})")
            return
        log_msg(f"INFO: Detached device from pool '{pool_name}'")

    runner.operation_detail = f"Detach: {pool_name}"
    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)


def on_disks_replace_device(app) -> None:
    """Replace a device in an existing pool vdev (Disks page action)."""
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Pool maintenance is available only on the storage host")
        return

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    repository = app.ctx.zfs_repository
    caps = app.ctx.zfs_caps
    data = app._disks_inventory_cache.get()
    pools = sorted(data.topologies)
    if not pools:
        log_msg("WARN: No imported pools to maintain")
        return
    imported = _leaf_paths_by_pool(data.topologies)
    try:
        importable = repository.list_importable_pool_devices()
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not scan importable pools: {exc}")
        importable = {}
    eligibility = disk_eligibility(data.disks, imported, importable)
    if not any(result.eligible for result in eligibility):
        _show_info_dialog(
            app,
            "No eligible disks",
            "Every disk is a pool member, partitioned, or lacks a /dev/disk/by-id "
            "path. Free a disk first (export or destroy its pool, or remove its "
            "partitions).",
        )
        return

    preselected = app._disks_pool_selector.get_active_text()
    result = show_replace_dialog(
        app, pools, data.topologies, eligibility, data.disks, preselected, caps
    )
    if result is None:
        return
    pool_name, cmd = result

    lock_id = zlm.acquire(pool_name, "w", f"Replace device in {pool_name}")
    step = BashStep(cmd, f"Replace device in pool {pool_name}", is_rsync=False, fatal=True)

    def _on_complete(cancelled=False, rc=None):
        zlm.release(lock_id)
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: Replace cancelled for {pool_name}")
            return
        if rc:
            log_msg(f"WARN: Replace failed for pool '{pool_name}' (rc={rc})")
            return
        log_msg(f"INFO: Replaced device in pool '{pool_name}'")
        log_msg(
            f"INFO: Resilver of pool '{pool_name}' underway — watch live progress "
            "in the Pools tab Watch window"
        )

    runner.operation_detail = f"Replace: {pool_name}"
    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)


def on_disks_attach_device(app) -> None:
    """Expand a pool vdev via zpool attach (Disks page action)."""
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Pool growth is available only on the storage host")
        return

    runner = getattr(app, "dataset_runner", None)
    if runner is None:
        log_msg("WARN: Dataset runner not available")
        return
    if runner.running:
        log_msg("WARN: A dataset action is already running")
        return

    repository = app.ctx.zfs_repository
    caps = app.ctx.zfs_caps
    data = app._disks_inventory_cache.get()
    pools = sorted(data.topologies)
    if not pools:
        log_msg("WARN: No imported pools to grow")
        return
    imported = _leaf_paths_by_pool(data.topologies)
    try:
        importable = repository.list_importable_pool_devices()
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not scan importable pools: {exc}")
        importable = {}
    eligibility = disk_eligibility(data.disks, imported, importable)
    if not any(result.eligible for result in eligibility):
        _show_info_dialog(
            app,
            "No eligible disks",
            "Every disk is a pool member, partitioned, or lacks a /dev/disk/by-id "
            "path. Free a disk first (export or destroy its pool, or remove its "
            "partitions).",
        )
        return

    preselected = app._disks_pool_selector.get_active_text()
    result = show_attach_dialog(
        app, pools, data.topologies, eligibility, data.disks, preselected, caps
    )
    if result is None:
        return
    pool_name, cmd, kind = result

    lock_id = zlm.acquire(pool_name, "w", f"Expand vdev in {pool_name}")
    step = BashStep(cmd, f"Expand vdev in pool {pool_name}", is_rsync=False, fatal=True)

    def _on_complete(cancelled=False, rc=None):
        zlm.release(lock_id)
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: Expand vdev cancelled for {pool_name}")
            return
        if rc:
            log_msg(f"WARN: Expand vdev failed for pool '{pool_name}' (rc={rc})")
            return
        log_msg(f"INFO: Expanded vdev in pool '{pool_name}'")
        if kind == ATTACH_RAIDZ_EXPANSION:
            log_msg(
                f"INFO: RAIDZ expansion of pool '{pool_name}' underway — use the "
                "Rewrite Data action on the Disks page per filesystem dataset "
                "to restripe existing data at the new ratio"
            )

    runner.operation_detail = f"Attach: {pool_name}"
    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)


def on_disks_add_infra_vdev(app) -> None:
    """Add an infrastructure vdev (special/log/cache) to a pool (Disks page action)."""
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Pool growth is available only on the storage host")
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
    pools = sorted(data.topologies)
    if not pools:
        log_msg("WARN: No imported pools to grow")
        return
    imported = _leaf_paths_by_pool(data.topologies)
    try:
        importable = repository.list_importable_pool_devices()
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not scan importable pools: {exc}")
        importable = {}
    eligibility = disk_eligibility(data.disks, imported, importable)
    if not any(result.eligible for result in eligibility):
        _show_info_dialog(
            app,
            "No eligible disks",
            "Every disk is a pool member, partitioned, or lacks a /dev/disk/by-id "
            "path. Free a disk first (export or destroy its pool, or remove its "
            "partitions).",
        )
        return

    preselected = app._disks_pool_selector.get_active_text()
    result = show_add_infra_vdev_dialog(app, pools, eligibility, preselected)
    if result is None:
        return
    pool_name, kind, cmd = result

    lock_id = zlm.acquire(pool_name, "w", f"Add {kind} vdev to {pool_name}")
    step = BashStep(cmd, f"Add {kind} vdev to pool {pool_name}", is_rsync=False, fatal=True)

    def _on_complete(cancelled=False, rc=None):
        zlm.release(lock_id)
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: Add {kind} vdev cancelled for {pool_name}")
            return
        if rc:
            log_msg(f"WARN: Add {kind} vdev failed for pool '{pool_name}' (rc={rc})")
            return
        log_msg(f"INFO: Added {kind} vdev to pool '{pool_name}'")

    runner.operation_detail = f"Add Infra Vdev: {pool_name}"
    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_complete)
