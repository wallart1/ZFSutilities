"""Pure-logic pool migration helpers (copy-based pool expansion).

No GTK and no direct subprocess calls; command construction is delegated to
the pure argv builders in ``zfs_repository`` and the GTK wizard in
``pool_migrate_dialogs`` (added with the Disks-page Migrate Pool action).

Migration exists because ZFS cannot change a vdev's redundancy class in
place (stripe to raidz, mirror to raidz, width changes, ashift changes).
The copy-based method snapshots the source pool, replicates every top-level
dataset to a destination (a new pool built on selected disks, or an existing
holding pool with enough free space), verifies the copy, and finally cuts
over: a cutover catch-up snapshot plus one short incremental per dataset
migrate the writes made while the copy ran, then the source pool is exported
and the migrated pool is re-imported
under the source pool's name so every ``pool/dataset`` path is preserved.
In holding-pool mode the source pool is destroyed and rebuilt as part of the
cutover, so the new topology may use the source pool's freed disks and/or any
eligible unused disks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from disk_repository import format_bytes
from pool_create import MAX_POOL_NAME_LEN, validate_pool_name
from pool_profiles import BLOCKSIZE_AUTO

# Migration modes: copy onto a new pool built from unused disks, or onto an
# existing imported pool used as intermediate holding space.
MIGRATE_NEW_DISKS = "new_disks"
MIGRATE_HOLDING_POOL = "holding_pool"
MIGRATION_MODES = (MIGRATE_NEW_DISKS, MIGRATE_HOLDING_POOL)

_MIGRATION_LABEL = "migrate"
_CUTOVER_SUFFIX = "-cutover"
_TEMP_SUFFIX = "_mig"
_HOLDING_NS_PREFIX = "migrate_"
_HEADROOM_FRACTION = 1.1

# Allowed used-byte difference between source and destination datasets during
# verification (refsnapshot accounting makes an exact match unrealistic).
_USED_TOLERANCE_FRACTION = 0.01

# Step kinds in a migration plan, in execution order.
STEP_SNAPSHOT = "snapshot"
STEP_COPY = "copy"
STEP_VERIFY = "verify"
STEP_CAPTURE_HOLDS = "capture_holds"
STEP_CUTOVER_SNAPSHOT = "cutover_snapshot"
STEP_CATCHUP_COPY = "catchup_copy"
STEP_EXPORT_SOURCE = "export_source"
STEP_IMPORT_RENAME = "import_rename"
STEP_REAPPLY_POOL_PROPS = "reapply_pool_props"
STEP_DESTROY_SOURCE = "destroy_source"
STEP_CREATE_POOL = "create_pool"
STEP_DESTROY_HOLDING = "destroy_holding"
STEP_RELEASE_HOLDS = "release_holds"
STEP_REAPPLY_HOLDS = "reapply_holds"


@dataclass(frozen=True)
class MigrationStep:
    """One planned migration step.

    ``kind`` is one of the ``STEP_*`` constants; ``description`` is the
    human-readable line shown in the review page and session log; ``dataset``
    is the source dataset for copy steps ("" otherwise).
    """

    kind: str
    description: str
    dataset: str = ""


def migration_snapshot_name(when: datetime | None = None) -> str:
    """Return the bucket-less migration snapshot name for *when* (now if None).

    Format ``@migrate-<yyyy-mm-dd>T<hh:mm><tz>`` follows the project snapshot
    convention but omits the bucket suffix: retention only prunes snapshots
    whose label matches its own (``dailybackup``, ``offsite``, …), so a
    ``migrate``-labelled snapshot is never retention-eligible.
    """
    now = when or datetime.now()
    if now.tzinfo is None:
        # Naive datetimes are assumed to be local time; an aware datetime
        # keeps the offset it was given (snapshot names follow the caller's
        # offset, not the machine's).
        now = now.astimezone()
    datestr = now.strftime("%Y-%m-%dT%H:%M%z")
    datestr = datestr[:-2] + ":" + datestr[-2:]
    return f"@{_MIGRATION_LABEL}-{datestr}"


def migration_snapshot_bare_name(snapshot_name: str) -> str:
    """Return the part after ``@`` of a full migration snapshot name."""
    if not snapshot_name.startswith("@"):
        raise ValueError(f"not a snapshot name: {snapshot_name!r}")
    return snapshot_name[1:]


def cutover_snapshot_name(snapshot_name: str) -> str:
    """Return the cutover catch-up snapshot name for a migration snapshot.

    Given the full ``@migrate-…`` name captured when the wizard opened, return
    ``@migrate-…-cutover``: still ``migrate``-labelled, so retention (which
    prunes only its own label's buckets) never touches it. The cutover
    snapshot is taken on the still-imported source pool right before the
    destructive cutover steps, and an incremental send from the migration
    snapshot to it carries every write made while the long copy ran.
    """
    if not snapshot_name.startswith(f"@{_MIGRATION_LABEL}-"):
        raise ValueError(f"not a migration snapshot name: {snapshot_name!r}")
    if "/" in snapshot_name or "@" in snapshot_name[1:]:
        raise ValueError(f"not a bare snapshot name: {snapshot_name!r}")
    if snapshot_name.endswith(_CUTOVER_SUFFIX):
        raise ValueError(f"already a cutover snapshot name: {snapshot_name!r}")
    return f"{snapshot_name}{_CUTOVER_SUFFIX}"


# Regex: vm-(\d+)-disk-\d+
# Used with re.fullmatch on the zvol base name (the part after the last "/"),
# mirroring gui_helpers.collect_dataset_busy_reasons. Purpose: recognize a
# Proxmox-style zvol ("vm-<vmid>-disk-<disknum>", e.g. "vm-207-disk-2") so the
# pool's zvols can be mapped to the VMs that own them. Group 1 captures the
# VM ID.
_ZVOL_BASE_RE = re.compile(r"vm-(\d+)-disk-\d+")


def vmids_from_zvols(names: list[str]) -> dict[str, list[str]]:
    """Map Proxmox VM IDs to the zvols they own.

    *names* are full zvol dataset names (``pool/vm-100-disk-0``). Each name
    whose base name follows the Proxmox ``vm-<id>-disk-<n>`` convention is
    grouped under its VM ID; non-conforming names are ignored. Returns
    ``{vmid: [zvol names]}`` with each list in input order.
    """
    vmids: dict[str, list[str]] = {}
    for name in names:
        match = _ZVOL_BASE_RE.fullmatch(name.split("/")[-1])
        if match:
            vmids.setdefault(match.group(1), []).append(name)
    return vmids


def holding_migration_namespace(source_pool: str) -> str:
    """Return the reserved holding-pool dataset namespace for a migration.

    Holding-mode copies land under ``<holding-pool>/migrate_<source>/<dataset>``
    so they can never collide with backup/offsite copies (which map to
    ``<pool>/<dataset-path>``) no matter which pool is chosen as the holding
    pool. The name is deterministic per source pool (no timestamps), so a
    re-run after an abort or a deferred cutover probes the same paths and
    finds its receive resume tokens. The namespace is reserved for migration
    use and destroyed as a whole at cutover.
    """
    if not source_pool:
        raise ValueError("source pool must not be empty")
    return f"{_HOLDING_NS_PREFIX}{source_pool}"


def generate_temp_pool_name(source_pool: str, existing_names: set[str]) -> str:
    """Return a valid, unused temporary pool name derived from *source_pool*.

    Tries ``<source>_mig``, then ``<source>_mig2``, ``<source>_mig3``, …,
    truncating the source part to respect ``MAX_POOL_NAME_LEN``. Raises
    ValueError when no valid candidate can be formed.
    """
    if not source_pool:
        raise ValueError("source pool name must not be empty")
    existing = set(existing_names)
    for index in range(1, 1000):
        suffix = _TEMP_SUFFIX if index == 1 else f"{_TEMP_SUFFIX}{index}"
        budget = MAX_POOL_NAME_LEN - len(suffix)
        if budget < 1:
            break
        candidate = source_pool[:budget] + suffix
        ok, _error = validate_pool_name(candidate, existing)
        if ok:
            return candidate
    raise ValueError(f"could not derive a temporary pool name from {source_pool!r}")


def _pool_shape_phrase(topology: str, blocksize_label: str) -> str:
    """Parenthetical describing the pool to create, e.g. ``(raidz2,
    4096-byte blocks)``. Empty when neither input is given; ``auto``
    blocksize is omitted (ZFS decides)."""
    parts = []
    if topology:
        parts.append(topology)
    if blocksize_label and blocksize_label != BLOCKSIZE_AUTO:
        parts.append(blocksize_label.replace(" bytes", "-byte blocks"))
    if not parts:
        return ""
    return f" ({', '.join(parts)})"


def _replay_props_step(source_pool: str, replay_props: tuple[str, ...]) -> MigrationStep:
    """Planned step that replays the checked non-default pool properties."""
    count = len(replay_props)
    return MigrationStep(
        STEP_REAPPLY_POOL_PROPS,
        f"Reapply {count} non-default pool propert{'y' if count == 1 else 'ies'} "
        f"on '{source_pool}' ({', '.join(replay_props)}) with zpool set",
    )


def plan_migration_steps(
    source_pool: str,
    top_level_datasets: list[str],
    mode: str,
    dest_label: str,
    rebuild_disk_count: int | None = None,
    migration_snap: str = "",
    cutover_snap: str = "",
    new_pool_topology: str = "",
    blocksize_label: str = "",
    replay_props: tuple[str, ...] = (),
) -> list[MigrationStep]:
    """Return the ordered step plan for one migration.

    *mode* is ``MIGRATE_NEW_DISKS`` (*dest_label* is the temporary new pool)
    or ``MIGRATE_HOLDING_POOL`` (*dest_label* is the existing holding pool);
    in holding mode the plan gains destroy/create/copy-back/destroy-holding
    steps around the same snapshot-copy-verify core. *rebuild_disk_count* is
    the number of disks the rebuilt pool will be created from (holding mode
    only); it is included in the create-step description when given.
    *migration_snap* and *cutover_snap* are the full ``@migrate-…`` and
    ``@migrate-…-cutover`` snapshot names; when given they appear in the
    catch-up step descriptions. *new_pool_topology* and *blocksize_label*
    describe the pool that will be created and appear in its create-step
    description — the blocksize especially, because it is the one setting
    that cannot be changed after creation. *replay_props* names the source
    pool's non-default properties the user kept checked; when given, one
    step right after the import-rename (in both modes) replays them with
    ``zpool set``. In both modes the plan gains,
    between the holds capture and the export step, a cutover snapshot plus
    one incremental catch-up copy per dataset, so writes made after the
    migration snapshot are migrated before anything destructive runs.
    Destructive steps are described as such; the wizard gates them behind
    typed confirmation.
    """
    if not source_pool:
        raise ValueError("source pool must not be empty")
    if not top_level_datasets:
        raise ValueError("source pool has no datasets to migrate")
    if mode not in MIGRATION_MODES:
        raise ValueError(f"unknown migration mode: {mode!r}")
    if not dest_label:
        raise ValueError("destination label must not be empty")
    if rebuild_disk_count is not None and rebuild_disk_count < 1:
        raise ValueError("rebuild disk count must be positive")
    shape = _pool_shape_phrase(new_pool_topology, blocksize_label)

    steps = [
        MigrationStep(
            STEP_SNAPSHOT,
            f"Snapshot all datasets on '{source_pool}' recursively",
        )
    ]
    if mode == MIGRATE_NEW_DISKS:
        steps.append(
            MigrationStep(
                STEP_CREATE_POOL,
                f"Create the new pool '{dest_label}'{shape} on the selected disks",
            )
        )
    # Copies land in a reserved namespace on the holding pool so they
    # cannot collide with backup/offsite copies of the same datasets.
    copy_dest = (
        f"{dest_label}/{holding_migration_namespace(source_pool)}"
        if mode == MIGRATE_HOLDING_POOL
        else dest_label
    )
    steps += [
        MigrationStep(
            STEP_COPY,
            f"Replicate '{dataset}' (snapshots and descendants) to '{copy_dest}'",
            dataset=dataset,
        )
        for dataset in top_level_datasets
    ]
    steps.append(
        MigrationStep(
            STEP_VERIFY,
            "Verify the copied dataset tree against the source",
        )
    )
    # Holds never travel in send streams, so the copies have none. Capture
    # the source pool's holds now (read-only) so they can be reapplied onto
    # the migrated pool once it has the source pool's name again.
    steps.append(
        MigrationStep(
            STEP_CAPTURE_HOLDS,
            f"Capture snapshot holds on '{source_pool}' for preservation",
        )
    )
    # Writes made after the migration snapshot are caught up at cutover: a
    # second (cutover) snapshot on the still-imported source pool, then one
    # short incremental per dataset into the same destination, all before
    # any destructive step. The data-loss window shrinks to the seconds
    # between the cutover snapshot and the export.
    steps.append(
        MigrationStep(
            STEP_CUTOVER_SNAPSHOT,
            f"Take cutover snapshot on '{source_pool}' recursively",
        )
    )
    steps += [
        MigrationStep(
            STEP_CATCHUP_COPY,
            f"Send incremental changes ('{migration_snap}' → '{cutover_snap}') "
            f"for '{dataset}' to '{copy_dest}'",
            dataset=dataset,
        )
        for dataset in top_level_datasets
    ]
    steps.append(
        MigrationStep(
            STEP_EXPORT_SOURCE,
            f"Export source pool '{source_pool}' (brief downtime begins here)",
        )
    )
    if mode == MIGRATE_NEW_DISKS:
        steps.append(
            MigrationStep(
                STEP_IMPORT_RENAME,
                f"Import '{dest_label}' under the name '{source_pool}'",
            )
        )
        if replay_props:
            steps.append(_replay_props_step(source_pool, replay_props))
        steps.append(
            MigrationStep(
                STEP_REAPPLY_HOLDS,
                f"Reapply the captured snapshot holds to '{source_pool}'",
            )
        )
    else:
        # Held snapshots cannot be destroyed, so the source pool's holds must
        # be released (after capture) before the pool is destroyed.
        steps.append(
            MigrationStep(
                STEP_RELEASE_HOLDS,
                f"Release all snapshot holds on '{source_pool}' (captured for reapply)",
            )
        )
        steps.append(
            MigrationStep(
                STEP_DESTROY_SOURCE,
                f"Destroy source pool '{source_pool}' to free its disks",
            )
        )
        steps.append(
            MigrationStep(
                STEP_CREATE_POOL,
                f"Create the rebuilt pool on {rebuild_disk_count} selected disk"
                f"{'s' if rebuild_disk_count != 1 else ''}{shape} (temporary name "
                f"'{source_pool}{_TEMP_SUFFIX}')",
            )
        )
        steps += [
            MigrationStep(
                STEP_COPY,
                f"Copy '{dataset}' back from the holding-pool namespace",
                dataset=dataset,
            )
            for dataset in top_level_datasets
        ]
        steps.append(
            MigrationStep(
                STEP_VERIFY,
                "Verify the copied-back dataset tree against the holding pool",
            )
        )
        steps.append(
            MigrationStep(
                STEP_EXPORT_SOURCE,
                f"Export holding pool '{dest_label}'",
            )
        )
        steps.append(
            MigrationStep(
                STEP_IMPORT_RENAME,
                f"Import '{source_pool}{_TEMP_SUFFIX}' under the name '{source_pool}'",
            )
        )
        if replay_props:
            steps.append(_replay_props_step(source_pool, replay_props))
        steps.append(
            MigrationStep(
                STEP_REAPPLY_HOLDS,
                f"Reapply the captured snapshot holds to '{source_pool}'",
            )
        )
        steps.append(
            MigrationStep(
                STEP_DESTROY_HOLDING,
                f"Destroy the migration namespace on holding pool '{dest_label}'",
            )
        )
    return steps


def check_destination_capacity(
    source_used_bytes: int,
    dest_free_bytes: int,
) -> tuple[list[str], list[str]]:
    """Validate destination space for a migration. Returns ``(problems, warnings)``.

    *problems* block the migration: the destination must have at least the
    source's allocated bytes free. *warnings* flag less than 10% headroom
    above that minimum.
    """
    problems: list[str] = []
    warnings: list[str] = []
    if source_used_bytes < 0 or dest_free_bytes < 0:
        raise ValueError("sizes must not be negative")
    if dest_free_bytes < source_used_bytes:
        problems.append(
            f"insufficient destination free space "
            f"({format_bytes(dest_free_bytes)}) for the source pool's allocated "
            f"data ({format_bytes(source_used_bytes)})"
        )
    elif dest_free_bytes < source_used_bytes * _HEADROOM_FRACTION:
        warnings.append(
            f"destination free space ({format_bytes(dest_free_bytes)}) has less "
            f"than 10% headroom over the source pool's allocated data "
            f"({format_bytes(source_used_bytes)})"
        )
    return problems, warnings


def verify_trees_match(
    source_used: dict[str, int],
    dest_used: dict[str, int],
) -> list[str]:
    """Compare per-dataset used bytes between source and migrated trees.

    Both mappings are dataset names relative to the pool root (``ds``,
    ``ds/child``) mapped to ``used`` bytes. Returns human-readable mismatch
    lines: datasets missing on the destination, extras on the destination,
    and used-byte differences beyond ``_USED_TOLERANCE_FRACTION``. An empty
    list means the trees match.
    """
    mismatches: list[str] = []
    for name in sorted(source_used):
        if name not in dest_used:
            mismatches.append(f"missing on destination: {name}")
            continue
        src = source_used[name]
        dst = dest_used[name]
        if src > 0 and abs(dst - src) > src * _USED_TOLERANCE_FRACTION:
            mismatches.append(
                f"used bytes differ for {name}: "
                f"source {format_bytes(src)}, destination {format_bytes(dst)}"
            )
    for name in sorted(dest_used):
        if name not in source_used:
            mismatches.append(f"extra on destination: {name}")
    return mismatches
