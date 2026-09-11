"""Migrate Pool dialog — GTK UI and execution handler for the Disks page.

Migration is the copy-based expansion path for changes ZFS cannot perform
in place (stripe to raidz, mirror to raidz, width or ashift changes). The
dialog collects a source pool and a destination (a new pool built on
selected disks, or an existing holding pool), shows the full step plan, and
gates the run behind typed confirmation of the source pool name. Execution
is two runner phases: the copy phase (recursive migration snapshot, one
``zfs send -Rw | zfs receive -u -F`` step per top-level dataset, then a
dataset-tree verification step), and the cutover phase (export the source
pool, then — for new disks — re-import the migrated pool under the source
pool's name, or — for holding pool — destroy the source, rebuild it on the
freed disks with the chosen topology, copy back, and swap). The cutover
phase starts only after a second typed confirmation, since it takes the
pool briefly offline.

All decision logic lives in the pure helpers below or in ``pool_migrate``;
ZFS I/O is delegated to ``ZfsRepository`` via the app context.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field

import gi

gi.require_version("Gtk", "3.0")

import node_config
import zfs_lock_manager as zlm
from command_builders import BashStep
from disk_repository import DiskInfo, _format_bytes
from disks_page import refresh_disks_page, update_disks_button_sensitivity
from gi.repository import Gtk
from gui_helpers import create_dialog
from logging_config import log_msg
from pool_create import (
    TOPOLOGIES,
    EligibilityResult,
    disk_eligibility,
    estimate_effective_capacity,
    validate_vdev_selection,
)
from pool_create_wizard import _leaf_paths_by_pool
from pool_growth import (
    _find_disk,
    mixed_size_warning,
    resolve_member_by_id,
    scrub_blocks_pool_op,
)
from pool_growth_dialogs import (
    _build_disk_picker,
    _on_topology_toggled,
    _on_typed_changed,
    _show_info_dialog,
)
from pool_migrate import (
    MIGRATE_HOLDING_POOL,
    MIGRATE_NEW_DISKS,
    MIGRATION_MODES,
    check_destination_capacity,
    generate_temp_pool_name,
    migration_snapshot_bare_name,
    migration_snapshot_name,
    plan_migration_steps,
)
from pools_page import on_pools_refresh
from zfs_repository import (
    TopologyNode,
    build_create_pool_command,
    build_destroy_dataset_command,
    build_migration_send_receive_command,
    build_pool_destroy_command,
    build_pool_export_command,
    build_pool_import_rename_command,
    build_recursive_snapshot_command,
)

# Custom dialog response id for the Migrate/Cut Over buttons. Distinct from
# Gtk.ResponseType values (which are negative) and from the other dialogs.
_RESPONSE_MIGRATE = 14

# Recordsize used for the effective-capacity estimate of a candidate pool
# (the GUI default; the estimate is advisory, zfs is the final arbiter).
_ESTIMATE_BLOCK_BYTES = 128 * 1024


@dataclass
class _MigrateState:
    """Mutable Migrate-Pool dialog state."""

    pools: list[str]  # migratable source pools (sorted)
    pool_name: str  # "" until a pool is picked
    mode: str  # MIGRATE_NEW_DISKS or MIGRATE_HOLDING_POOL
    datasets_by_pool: dict[str, list[str]]  # top-level datasets per pool
    pool_alloc: dict[str, int]  # allocated bytes per imported pool
    pool_free: dict[str, int]  # free bytes per imported pool
    eligibility: list[EligibilityResult]
    disks: list[DiskInfo]  # full inventory (by-id resolution of members)
    topologies: dict[str, TopologyNode]  # imported pool topology trees
    existing_names: set[str]  # imported + importable pool names
    snap_name: str  # full @migrate-… name, fixed when the dialog opens
    holding_pool: str = ""
    topology: str = "mirror"
    selected: list[DiskInfo] = field(default_factory=list)
    typed: str = ""  # review typed confirmation (source pool name)


@dataclass(frozen=True)
class MigrationRequest:
    """Confirmed migration inputs handed from the dialog to the executor.

    ``temp_pool`` is the destination pool for new-disks mode and the
    rebuilt pool's temporary name for holding mode; ``holding_pool``,
    ``new_pool_topology``, and ``new_pool_by_id`` are holding mode only.
    ``snap_bare`` is the migration snapshot name without the leading ``@``.
    """

    source_pool: str
    mode: str
    datasets: tuple[str, ...]
    snap_bare: str
    temp_pool: str
    holding_pool: str = ""
    new_pool_topology: str = "mirror"
    new_pool_by_id: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Pure helpers (no GTK, no subprocess) — unit-tested directly
# ---------------------------------------------------------------------------


def _temp_pool_name(state: _MigrateState) -> str:
    """Deterministic temporary pool name for the current source selection."""
    return generate_temp_pool_name(state.pool_name, set(state.existing_names))


def _dest_label(state: _MigrateState) -> str:
    """Destination name used in the plan: temp pool or holding pool."""
    if state.mode == MIGRATE_HOLDING_POOL:
        return state.holding_pool
    return _temp_pool_name(state)


def _holding_candidates(state: _MigrateState) -> list[str]:
    """Holding pools: every migratable pool except the source."""
    return [pool for pool in state.pools if pool != state.pool_name]


def _candidate_pool_capacity_bytes(topology: str, disks: list[DiskInfo]) -> int | None:
    """Effective-capacity estimate for a candidate pool, or None if unknown."""
    sizes = [disk.size_bytes for disk in disks if disk.size_bytes > 0]
    if not sizes or topology not in TOPOLOGIES:
        return None
    try:
        estimate = estimate_effective_capacity(
            topology, len(disks), min(sizes), _ESTIMATE_BLOCK_BYTES
        )
    except ValueError:
        return None
    return estimate.effective_bytes


def _source_pool_member_disks(state: _MigrateState) -> list[DiskInfo]:
    """Inventory rows for the source pool's leaf members (holding mode)."""
    root = state.topologies.get(state.pool_name)
    if root is None:
        return []
    leaves = _leaf_paths_by_pool({state.pool_name: root}).get(state.pool_name, [])
    members: list[DiskInfo] = []
    for leaf in leaves:
        disk = _find_disk(leaf, state.disks)
        if disk is not None:
            members.append(disk)
    return members


def _source_pool_by_ids(state: _MigrateState) -> list[str]:
    """By-id paths of the source pool's leaf members (holding-mode rebuild)."""
    root = state.topologies.get(state.pool_name)
    if root is None:
        return []
    leaves = _leaf_paths_by_pool({state.pool_name: root}).get(state.pool_name, [])
    by_ids: list[str] = []
    for leaf in leaves:
        by_id = resolve_member_by_id(leaf, state.disks)
        if by_id is None:
            return []
        by_ids.append(by_id)
    return by_ids


def _capacity_problem(
    capacity_bytes: int | None,
    alloc_bytes: int,
    what: str,
) -> str | None:
    """Refusal line when a candidate pool cannot hold the source data."""
    if capacity_bytes is None:
        return f"could not estimate the capacity of {what}"
    if capacity_bytes < alloc_bytes:
        return (
            f"{what} yields about {_format_bytes(capacity_bytes)} effective "
            f"capacity, less than the source pool's allocated data "
            f"({_format_bytes(alloc_bytes)})"
        )
    return None


def _migrate_problems(state: _MigrateState) -> list[str]:
    """Return human-readable problems blocking the Migrate action, in order."""
    if not state.pool_name or state.pool_name not in state.pools:
        return ["Select a source pool"]
    datasets = state.datasets_by_pool.get(state.pool_name, [])
    if not datasets:
        return [f"Pool '{state.pool_name}' has no datasets to migrate"]
    if state.mode not in MIGRATION_MODES:
        return [f"Unknown migration mode: {state.mode!r}"]
    alloc = state.pool_alloc.get(state.pool_name, 0)

    if state.mode == MIGRATE_NEW_DISKS:
        if not state.selected:
            return ["Select at least one eligible disk"]
        for result in state.eligibility:
            if result.disk in state.selected and not result.eligible:
                return list(result.reasons) or [f"disk {result.disk.path} is not eligible"]
        spec = TOPOLOGIES.get(state.topology)
        if spec is None:
            return [f"unknown topology: {state.topology!r}"]
        if len(state.selected) < spec.min_disks:
            return [f"{state.topology} requires at least {spec.min_disks} disks"]
        problems = validate_vdev_selection(state.selected)
        if problems:
            return problems
        capacity = _candidate_pool_capacity_bytes(state.topology, state.selected)
        problem = _capacity_problem(capacity, alloc, "the selected disks")
        if problem:
            return [problem]
    else:
        candidates = _holding_candidates(state)
        if not candidates:
            return ["No other imported pool is available as a holding pool"]
        if not state.holding_pool or state.holding_pool not in candidates:
            return ["Select a holding pool (a pool other than the source)"]
        problems, _warnings = check_destination_capacity(
            alloc, state.pool_free.get(state.holding_pool, 0)
        )
        if problems:
            return problems
        capacity = _candidate_pool_capacity_bytes(
            state.topology, _source_pool_member_disks(state)
        )
        problem = _capacity_problem(
            capacity, alloc, "the pool rebuilt on the source pool's disks"
        )
        if problem:
            return [problem]

    if state.typed != state.pool_name:
        return [f"Type the pool name '{state.pool_name}' to confirm"]
    return []


def _migrate_warnings(state: _MigrateState) -> list[str]:
    """Warnings for the current migration selection."""
    warnings: list[str] = [
        (
            "cutover exports the source pool — stop VMs and unmount shares that "
            "use it before confirming the cutover"
        ),
        (
            "every dataset path survives the migration: the migrated pool is "
            "re-imported under the source pool's name"
        ),
    ]
    if state.mode == MIGRATE_HOLDING_POOL:
        warnings.append(
            "the holding pool must stay online and untouched until the "
            "migration finishes"
        )
    if state.mode == MIGRATE_NEW_DISKS:
        alloc = state.pool_alloc.get(state.pool_name, 0)
        capacity = _candidate_pool_capacity_bytes(state.topology, state.selected)
        if capacity is not None and alloc > 0 and capacity < alloc * 1.1:
            warnings.append(
                "the new pool has less than 10% headroom over the source "
                "pool's allocated data"
            )
        for result in state.eligibility:
            if result.disk in state.selected:
                warnings.extend(result.warnings)
        mixed = mixed_size_warning(state.selected)
        if mixed:
            warnings.append(mixed)
    return warnings


def _plan_lines(state: _MigrateState) -> list[str]:
    """Step descriptions for the review page (empty when nothing is chosen)."""
    if not state.pool_name or state.pool_name not in state.pools:
        return []
    datasets = state.datasets_by_pool.get(state.pool_name, [])
    if not datasets:
        return []
    steps = plan_migration_steps(
        state.pool_name, datasets, state.mode, _dest_label(state)
    )
    return [step.description for step in steps]


def build_request(state: _MigrateState) -> MigrationRequest:
    """Build the execution request for a validated dialog state."""
    by_ids: tuple[str, ...] = ()
    if state.mode == MIGRATE_HOLDING_POOL:
        by_ids = tuple(_source_pool_by_ids(state))
    return MigrationRequest(
        source_pool=state.pool_name,
        mode=state.mode,
        datasets=tuple(state.datasets_by_pool.get(state.pool_name, [])),
        snap_bare=migration_snapshot_bare_name(state.snap_name),
        temp_pool=_temp_pool_name(state),
        holding_pool=state.holding_pool if state.mode == MIGRATE_HOLDING_POOL else "",
        new_pool_topology=state.topology,
        new_pool_by_id=by_ids,
    )


# ---------------------------------------------------------------------------
# Execution plan (pure: argv composition only)
# ---------------------------------------------------------------------------


def _build_verify_step(src: str, dest: str, dataset: str) -> BashStep:
    """Build the dataset-tree verification step for one copied dataset.

    Compares the filesystem/volume count below the source dataset with the
    count below the destination; a mismatch fails the step so the run aborts
    before any destructive cutover action.
    """
    src_ds = f"{src}/{dataset}"
    dest_ds = f"{dest}/{dataset}"
    script = (
        "set -o pipefail; "
        f"s=$(zfs list -rH -t filesystem,volume -o name {shlex.quote(src_ds)} | wc -l); "
        f"d=$(zfs list -rH -t filesystem,volume -o name {shlex.quote(dest_ds)} | wc -l); "
        f'echo "verify {dataset}: source datasets=$s, destination datasets=$d"; '
        'test "$s" -gt 0 && test "$d" -eq "$s"'
    )
    return BashStep(
        ["bash", "-c", script],
        f"Verify copy of {src_ds} to {dest_ds}",
        is_rsync=False,
        fatal=True,
    )


def _copy_steps(src_pool: str, dest_pool: str, datasets, snap_bare: str) -> list[BashStep]:
    """Snapshot + replicate + verify steps for one copy direction."""
    steps = [
        BashStep(
            build_recursive_snapshot_command(src_pool, snap_bare),
            f"Snapshot pool {src_pool} for migration",
            is_rsync=False,
            fatal=True,
        )
    ]
    for dataset in datasets:
        steps.append(
            BashStep(
                build_migration_send_receive_command(
                    f"{src_pool}/{dataset}", f"{dest_pool}/{dataset}", snap_bare
                ),
                f"Migrate {src_pool}/{dataset} -> {dest_pool}/{dataset}",
                is_rsync=False,
                fatal=True,
            )
        )
    for dataset in datasets:
        steps.append(_build_verify_step(src_pool, dest_pool, dataset))
    return steps


def build_migration_steps(
    request: MigrationRequest,
) -> tuple[list[BashStep], list[BashStep]]:
    """Build the (copy, cutover) step lists for one migration request."""
    datasets = list(request.datasets)
    if request.mode == MIGRATE_NEW_DISKS:
        copy = _copy_steps(
            request.source_pool, request.temp_pool, datasets, request.snap_bare
        )
        cutover = [
            BashStep(
                build_pool_export_command(request.source_pool),
                f"Export source pool {request.source_pool}",
                is_rsync=False,
                fatal=True,
            ),
            BashStep(
                build_pool_import_rename_command(
                    request.temp_pool, request.source_pool
                ),
                f"Import {request.temp_pool} as {request.source_pool}",
                is_rsync=False,
                fatal=True,
            ),
        ]
        return copy, cutover

    # Holding-pool mode: copy out, then rebuild on the freed disks and swap.
    copy = _copy_steps(
        request.source_pool, request.holding_pool, datasets, request.snap_bare
    )
    cutover = [
        BashStep(
            build_pool_export_command(request.source_pool),
            f"Export source pool {request.source_pool}",
            is_rsync=False,
            fatal=True,
        ),
        BashStep(
            build_pool_destroy_command(request.source_pool),
            f"Destroy source pool {request.source_pool}",
            is_rsync=False,
            fatal=True,
        ),
        BashStep(
            build_create_pool_command(
                request.temp_pool,
                request.new_pool_topology,
                list(request.new_pool_by_id),
            ),
            f"Create rebuilt pool {request.temp_pool} "
            f"({request.new_pool_topology}) on the freed disks",
            is_rsync=False,
            fatal=True,
        ),
    ]
    # The migration snapshot already exists on the holding pool (received
    # with the replication stream), so copy-back skips the snapshot step.
    cutover += _copy_steps(
        request.holding_pool, request.temp_pool, datasets, request.snap_bare
    )[1:]
    for dataset in datasets:
        cutover.append(
            BashStep(
                build_destroy_dataset_command(f"{request.holding_pool}/{dataset}"),
                f"Remove migration copy {request.holding_pool}/{dataset}",
                is_rsync=False,
                fatal=True,
            )
        )
    cutover += [
        BashStep(
            build_pool_export_command(request.holding_pool),
            f"Export holding pool {request.holding_pool}",
            is_rsync=False,
            fatal=True,
        ),
        BashStep(
            build_pool_import_rename_command(
                request.temp_pool, request.source_pool
            ),
            f"Import {request.temp_pool} as {request.source_pool}",
            is_rsync=False,
            fatal=True,
        ),
    ]
    return copy, cutover


# ---------------------------------------------------------------------------
# Migrate Pool dialog
# ---------------------------------------------------------------------------


def _combo_text(combo) -> str:
    text = combo.get_active_text()
    return text if isinstance(text, str) else ""


def _on_source_pool_changed(combo, state: _MigrateState, on_change) -> None:
    text = _combo_text(combo)
    if text:
        state.pool_name = text
    if state.holding_pool == state.pool_name:
        state.holding_pool = ""
    on_change()


def _on_mode_toggled(radio, mode: str, state: _MigrateState, on_change) -> None:
    active = radio.get_active()
    if isinstance(active, bool) and not active:
        return  # deactivation signal from the previously selected radio
    state.mode = mode
    on_change()


def _on_holding_changed(combo, state: _MigrateState, on_change) -> None:
    text = _combo_text(combo)
    if text:
        state.holding_pool = text
    on_change()


def show_migrate_pool_dialog(app, state: _MigrateState) -> MigrationRequest | None:
    """Run the Migrate-Pool dialog.

    Returns a ``MigrationRequest`` when the user confirms migration,
    or ``None`` when the dialog is cancelled.
    """
    dialog = create_dialog(
        "Migrate Pool",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(860, 760),
    )
    migrate_btn = dialog.add_button("Migrate", _RESPONSE_MIGRATE)
    content = dialog.get_content_area()

    caption = Gtk.Label()
    caption.set_halign(Gtk.Align.START)
    caption.set_line_wrap(True)
    caption.set_text(
        "Copy a pool to new disks (or via a holding pool) to change its "
        "topology, then swap. Use this when ZFS cannot expand the pool in "
        "place (for example stripe to raidz)."
    )
    content.pack_start(caption, False, False, 0)

    pool_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pool_label = Gtk.Label(label="Source pool:")
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

    mode_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    mode_group = None
    mode_radios = {}
    for mode, label_text in (
        (
            MIGRATE_NEW_DISKS,
            "New disks — build a new pool from selected disks, then swap",
        ),
        (
            MIGRATE_HOLDING_POOL,
            "Holding pool — copy via another imported pool with enough space",
        ),
    ):
        if mode_group is None:
            radio = Gtk.RadioButton(label=label_text)
            mode_group = radio
        else:
            radio = Gtk.RadioButton.new_from_widget(mode_group)
            radio.set_label(label_text)
        radio.set_halign(Gtk.Align.START)
        mode_box.pack_start(radio, False, False, 0)
        mode_radios[mode] = radio
    content.pack_start(mode_box, False, False, 0)

    new_disks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    content.pack_start(new_disks_box, True, True, 0)

    topology_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    topology_label = Gtk.Label(label="Topology for the new / rebuilt pool:")
    topology_label.set_halign(Gtk.Align.START)
    topology_box.pack_start(topology_label, False, False, 0)
    radio_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    topology_box.pack_start(radio_stack, False, False, 0)
    group = None
    topology_radios = []
    for name, spec in TOPOLOGIES.items():
        label_text = f"{name} (minimum {spec.min_disks} disks)"
        if group is None:
            radio = Gtk.RadioButton(label=label_text)
            group = radio
        else:
            radio = Gtk.RadioButton.new_from_widget(group)
            radio.set_label(label_text)
        radio.set_halign(Gtk.Align.START)
        radio_stack.pack_start(radio, False, False, 0)
        topology_radios.append((radio, name))
    content.pack_start(topology_box, False, False, 0)

    holding_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    holding_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    holding_label = Gtk.Label(label="Holding pool:")
    holding_label.set_halign(Gtk.Align.END)
    holding_row.pack_start(holding_label, False, False, 0)
    holding_combo = Gtk.ComboBoxText()
    holding_combo.set_hexpand(True)
    holding_row.pack_start(holding_combo, True, True, 0)
    holding_box.pack_start(holding_row, False, False, 0)
    holding_hint = Gtk.Label()
    holding_hint.set_halign(Gtk.Align.START)
    holding_hint.set_line_wrap(True)
    holding_hint.set_text(
        "All data is copied to the holding pool first; the source pool is "
        "then destroyed and rebuilt with the topology chosen above before "
        "the data is copied back. The holding pool needs free space at "
        "least equal to the source pool's allocated data."
    )
    holding_box.pack_start(holding_hint, False, False, 0)
    content.pack_start(holding_box, True, True, 0)

    plan_label = Gtk.Label(label="Steps that will run:")
    plan_label.set_halign(Gtk.Align.START)
    content.pack_start(plan_label, False, False, 0)
    plan_buf = Gtk.TextBuffer()
    plan_tv = Gtk.TextView(buffer=plan_buf)
    plan_tv.set_editable(False)
    plan_tv.set_cursor_visible(False)
    plan_tv.set_monospace(True)
    plan_sw = Gtk.ScrolledWindow()
    plan_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    plan_sw.set_min_content_height(120)
    plan_sw.add(plan_tv)
    content.pack_start(plan_sw, False, False, 0)

    warnings_label = Gtk.Label()
    warnings_label.set_halign(Gtk.Align.START)
    warnings_label.set_line_wrap(True)
    content.pack_start(warnings_label, False, False, 0)

    typed_hint = Gtk.Label()
    typed_hint.set_halign(Gtk.Align.START)
    typed_hint.set_line_wrap(True)
    content.pack_start(typed_hint, False, False, 0)
    typed_entry = Gtk.Entry()
    typed_entry.set_hexpand(True)
    content.pack_start(typed_entry, False, False, 0)

    def _populate_holding_combo() -> None:
        holding_combo.remove_all()
        candidates = _holding_candidates(state)
        for pool_name in candidates:
            holding_combo.append_text(pool_name)
        if state.holding_pool in candidates:
            holding_combo.set_active(candidates.index(state.holding_pool))
        elif candidates:
            state.holding_pool = candidates[0]
            holding_combo.set_active(0)
        else:
            state.holding_pool = ""

    def _refresh() -> None:
        new_disks_box.set_visible(state.mode == MIGRATE_NEW_DISKS)
        holding_box.set_visible(state.mode == MIGRATE_HOLDING_POOL)
        problems = _migrate_problems(state)
        lines = _plan_lines(state)
        if lines:
            plan_buf.set_text(
                "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))
            )
        else:
            plan_buf.set_text("(select a source pool)")
        warnings = _migrate_warnings(state)
        if warnings:
            warnings_label.set_text(
                "Warnings:\n" + "\n".join(f"• {warning}" for warning in warnings)
            )
        else:
            warnings_label.set_text("")
        typed_hint.set_text(
            f"Type the pool name '{state.pool_name}' exactly to enable Migrate."
        )
        migrate_btn.set_sensitive(not problems)
        migrate_btn.set_tooltip_text(problems[0] if problems else "")

    # GTK emits "toggled" from set_active during construction; connect only
    # after the initial state is set or the handlers run before the refresh
    # closure exists (NameError on the enclosing scope's free variable).
    new_disks_box.pack_start(
        _build_disk_picker(
            state,
            _refresh,
            "Select the disks for the new pool. Disks already in any pool or "
            "otherwise unusable are greyed out.",
        ),
        True,
        True,
        0,
    )
    for mode, radio in mode_radios.items():
        if mode == state.mode:
            radio.set_active(True)
        radio.connect("toggled", _on_mode_toggled, mode, state, _refresh)
    for radio, name in topology_radios:
        if name == state.topology:
            radio.set_active(True)
        radio.connect("toggled", _on_topology_toggled, name, state, _refresh)
    typed_entry.connect("changed", _on_typed_changed, state, _refresh)
    _populate_holding_combo()
    pool_combo.connect("changed", _on_source_pool_changed, state, _refresh)
    holding_combo.connect("changed", _on_holding_changed, state, _refresh)

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
            if response == _RESPONSE_MIGRATE:
                problems = _migrate_problems(state)
                if problems:
                    continue
                repository = app.ctx.zfs_repository
                blockers = [
                    scrub_blocks_pool_op(pool, repository)
                    for pool in {state.pool_name, _dest_label(state)}
                ]
                blockers = [blocker for blocker in blockers if blocker]
                if blockers:
                    _show_info_dialog(dialog, blockers[0])
                    continue
                return build_request(state)
    finally:
        dialog.destroy()


def _show_cutover_confirm(app, request: MigrationRequest) -> bool:
    """Typed-confirmation gate before the destructive cutover phase."""
    dialog = create_dialog(
        "Confirm Cutover",
        app,
        [(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)],
        size=(640, 320),
    )
    ok_btn = dialog.add_button("Cut Over", _RESPONSE_MIGRATE)
    content = dialog.get_content_area()
    text = Gtk.Label()
    text.set_halign(Gtk.Align.START)
    text.set_line_wrap(True)
    text.set_text(
        f"The copy phase finished. Cutover now exports pool "
        f"'{request.source_pool}' and swaps in the migrated pool under that "
        f"name.\n\nStop every VM and unmount every share that uses "
        f"'{request.source_pool}' before continuing — they will lose access "
        f"during the swap."
    )
    content.pack_start(text, False, False, 0)
    entry = Gtk.Entry()
    entry.set_hexpand(True)
    content.pack_start(entry, False, False, 0)

    def _entry_text() -> str:
        value = entry.get_text()
        return value if isinstance(value, str) else ""

    dialog.show_all()
    try:
        while True:
            ok_btn.set_sensitive(_entry_text() == request.source_pool)
            response = dialog.run()
            if response in (
                Gtk.ResponseType.CANCEL,
                Gtk.ResponseType.DELETE_EVENT,
                Gtk.ResponseType.CLOSE,
            ):
                return False
            if response == _RESPONSE_MIGRATE and _entry_text() == request.source_pool:
                return True
    finally:
        dialog.destroy()


# ---------------------------------------------------------------------------
# Execution handler (Disks page action)
# ---------------------------------------------------------------------------


def _finish_refresh(app) -> None:
    update_disks_button_sensitivity(app)
    app._disks_inventory_cache.invalidate()
    refresh_disks_page(app)
    on_pools_refresh(app)


def _root_pool_name(repository) -> str | None:
    """Return the pool hosting the root filesystem, or None."""
    try:
        info = repository.list_dataset_info()
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not scan dataset mountpoints: {exc}")
        return None
    for row in info:
        if row.get("mountpoint") == "/":
            return row["name"].split("/")[0]
    return None


def on_disks_migrate_pool(app) -> None:
    """Migrate a pool to new disks or via a holding pool (Disks page action)."""
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Pool migration is available only on the storage host")
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
    pools_all = sorted(data.topologies)
    if not pools_all:
        log_msg("WARN: No imported pools to migrate")
        return

    pool_alloc: dict[str, int] = {}
    pool_free: dict[str, int] = {}
    for row in repository.list_pools_full():
        try:
            pool_alloc[row["name"]] = int(row["alloc"])
            pool_free[row["name"]] = int(row["free"])
        except (KeyError, ValueError):
            continue

    datasets_by_pool: dict[str, list[str]] = {}
    for pool_name in pools_all:
        try:
            rows = repository.list_datasets(pool_name, depth=1)
        except Exception as exc:  # pragma: no cover - defensive
            log_msg(f"WARN: Could not list datasets of pool '{pool_name}': {exc}")
            rows = []
        datasets_by_pool[pool_name] = [
            row.name for row in rows if row.name and row.name != pool_name
        ]

    root_pool = _root_pool_name(repository)
    pools = [
        pool_name
        for pool_name in pools_all
        if pool_name != root_pool and datasets_by_pool.get(pool_name)
    ]
    if not pools:
        _show_info_dialog(
            app,
            "No migratable pools",
            "Every imported pool either hosts the root filesystem (and "
            "cannot be exported) or has no datasets to copy.",
        )
        return

    imported = _leaf_paths_by_pool(data.topologies)
    try:
        importable = repository.list_importable_pool_devices()
    except Exception as exc:  # pragma: no cover - defensive
        log_msg(f"WARN: Could not scan importable pools: {exc}")
        importable = {}
    eligibility = disk_eligibility(data.disks, imported, importable)
    existing_names = set(data.topologies) | repository.list_importable_pool_names()

    preselected = app._disks_pool_selector.get_active_text()
    state = _MigrateState(
        pools=pools,
        pool_name=preselected if preselected in pools else (pools[0] if pools else ""),
        mode=MIGRATE_NEW_DISKS,
        datasets_by_pool=datasets_by_pool,
        pool_alloc=pool_alloc,
        pool_free=pool_free,
        eligibility=eligibility,
        disks=data.disks,
        topologies=data.topologies,
        existing_names=existing_names,
        snap_name=migration_snapshot_name(),
    )
    request = show_migrate_pool_dialog(app, state)
    if request is None:
        return

    copy_steps, cutover_steps = build_migration_steps(request)
    lock_id = zlm.acquire(
        request.source_pool, "w", f"Migrate pool {request.source_pool}"
    )

    def _copy_complete(cancelled=False, rc=None):
        if cancelled or rc:
            zlm.release(lock_id)
            _finish_refresh(app)
            if cancelled:
                log_msg(f"INFO: Migrate pool cancelled for {request.source_pool}")
            else:
                log_msg(
                    f"WARN: Migrate pool copy failed for '{request.source_pool}' "
                    f"(rc={rc}); no destructive step was run"
                )
            return
        log_msg(
            f"INFO: Migrate pool copy complete for '{request.source_pool}'; "
            "waiting for cutover confirmation"
        )
        if not _show_cutover_confirm(app, request):
            zlm.release(lock_id)
            _finish_refresh(app)
            log_msg(
                f"INFO: Cutover deferred for '{request.source_pool}'; the "
                "migration snapshot and copies remain in place — rerun Migrate "
                "Pool to finish"
            )
            return
        runner.set_steps(cutover_steps)
        update_disks_button_sensitivity(app)
        runner.start(on_complete=_cutover_complete)

    def _cutover_complete(cancelled=False, rc=None):
        zlm.release(lock_id)
        _finish_refresh(app)
        if cancelled:
            log_msg(f"INFO: Migrate pool cutover cancelled for {request.source_pool}")
            return
        if rc:
            log_msg(
                f"WARN: Migrate pool cutover failed for '{request.source_pool}' "
                f"(rc={rc}) — the pool may be left exported; investigate before "
                "retrying"
            )
            return
        log_msg(
            f"INFO: Pool '{request.source_pool}' migrated successfully "
            f"(mode: {request.mode})"
        )

    runner.set_steps(copy_steps)
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_copy_complete)
