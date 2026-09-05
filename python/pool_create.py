"""Pure-logic create-pool helpers.

No GTK and no direct subprocess calls. All ZFS I/O is delegated to callers via
``ZfsRepository``.
"""

from __future__ import annotations

import os
from collections.abc import Container
from dataclasses import dataclass
from math import ceil

from disk_repository import DiskInfo
from workload_profiles import LIVE_PROPERTIES, properties_for_profile


# Topology table: name -> (parity level, minimum member count).
# Minimums come from the Phase 3 brief: mirror >= 2, raidz1 >= 3,
# raidz2 >= 4, raidz3 >= 5; a stripe is a single non-redundant vdev.
@dataclass(frozen=True)
class TopologySpec:
    """Static description of one pool topology choice."""

    name: str
    parity: int
    min_disks: int


TOPOLOGIES: dict[str, TopologySpec] = {
    "stripe": TopologySpec("stripe", parity=0, min_disks=1),
    "mirror": TopologySpec("mirror", parity=0, min_disks=2),
    "raidz1": TopologySpec("raidz1", parity=1, min_disks=3),
    "raidz2": TopologySpec("raidz2", parity=2, min_disks=4),
    "raidz3": TopologySpec("raidz3", parity=3, min_disks=5),
}

SOLID_STATE_TYPES = ("SSD", "NVMe")

_BY_ID_DIR = "/dev/disk/by-id"

# Pool-name rules verified against OpenZFS 2.4.4 source at implementation time:
# module/zcommon/zfs_namecheck.c:pool_namecheck() and
# lib/libzfs/libzfs_pool.c:zpool_name_valid(). Note that `zpool create -n`
# (dry-run) does NOT validate the pool name, so a real `zpool create` remains
# the final arbiter for anything this module accepts.
#  - valid characters: alphanumerics plus - _ . : and space
#  - the name must begin with a letter
#  - reserved exact names (kernel-enforced): mirror, raidz, draid
#  - reserved at create time (userland): names beginning with mirror, raidz,
#    draid, or spare, plus the exact name log; all case-sensitive
#  - libzfs length bound: names shorter than 240 characters
# The 32-character cap below is a project policy, not a libzfs requirement:
# ZFSutilities consumes name length downstream (pool name prepended for
# subsequent backups, plus ~30+ character snapshot-name suffixes), so keep pool
# names short enough that full dataset/snapshot paths stay well inside limits.
MAX_POOL_NAME_LEN = 32
_POOL_NAME_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.: "
)
_RESERVED_EXACT = ("mirror", "raidz", "draid")
_RESERVED_PREFIXES = ("mirror", "raidz", "draid", "spare")


@dataclass
class EligibilityResult:
    """Eligibility verdict for one disk or partition.

    ``reasons`` are blocking (disk is not selectable); ``warnings`` are
    informational (disk is selectable but the user should think twice).
    """

    disk: DiskInfo
    eligible: bool
    reasons: list[str]
    warnings: list[str]


def _parent_disk(disks: list[DiskInfo], partition: DiskInfo) -> DiskInfo | None:
    """Return the whole-disk row for *partition*, or None if not present."""
    for disk in disks:
        if disk.path == partition.parent_path:
            return disk
    return None


def _disk_aliases(disk: DiskInfo) -> set[str]:
    """Return the path aliases under which a disk may appear in pool configs."""
    aliases = {disk.path, os.path.realpath(disk.path)}
    if disk.by_id:
        by_id_path = os.path.join(_BY_ID_DIR, disk.by_id)
        aliases.add(by_id_path)
        aliases.add(os.path.realpath(by_id_path))
    return aliases


def _match_pool(disk: DiskInfo, pool_paths: dict[str, list[str]]) -> str | None:
    """Return the pool name whose member paths match *disk*, or None.

    Uses the same technique as DiskInventoryCache._pools_for_disk: realpath
    match first, basename fallback, extended with /dev/disk/by-id aliases so
    membership in not-yet-imported pools (whose configs name by-id paths) is
    detected.
    """
    aliases = _disk_aliases(disk)
    basenames = {os.path.basename(alias) for alias in aliases}
    for pool_name, paths in pool_paths.items():
        for path in paths:
            if path in aliases or os.path.realpath(path) in aliases:
                return pool_name
            if os.path.basename(path) in basenames:
                return pool_name
    return None


def disk_eligibility(
    disks: list[DiskInfo],
    imported_member_paths: dict[str, list[str]],
    importable_member_paths: dict[str, list[str]],
) -> list[EligibilityResult]:
    """Evaluate every disk and partition in *disks* for pool creation.

    *imported_member_paths* maps pool name to leaf device paths of imported
    pools; *importable_member_paths* maps pool name to leaf device paths of
    exportable-but-not-imported pools (from ``zpool import``). Both default to
    empty mappings.
    """
    results: list[EligibilityResult] = []
    for disk in disks:
        reasons: list[str] = []
        warnings: list[str] = []
        _apply_partition_policy(disks, disk, reasons, warnings)
        imported = _match_pool(disk, imported_member_paths)
        if imported is not None:
            reasons.append(f"member of imported pool '{imported}'")
        importable = _match_pool(disk, importable_member_paths)
        if importable is not None:
            reasons.append(
                f"member of importable pool '{importable}' (import or destroy it first)"
            )
        if not disk.by_id:
            reasons.append("no /dev/disk/by-id path")
        if disk.disk_type == "unknown":
            reasons.append("unknown disk type")
        if disk.path.startswith("/dev/") and os.path.basename(disk.path).startswith("zd"):
            reasons.append("zvol-backed device")
        if not reasons and disk.transport == "usb":
            warnings.append(
                "USB-attached disk: not recommended for pool membership "
                "(bandwidth/reliability)"
            )
        results.append(
            EligibilityResult(disk=disk, eligible=not reasons, reasons=reasons,
                              warnings=warnings)
        )
    return results


def _apply_partition_policy(
    disks: list[DiskInfo],
    disk: DiskInfo,
    reasons: list[str],
    warnings: list[str],
) -> None:
    """Apply the partition eligibility policy to one row.

    Partitions of solid-state devices are eligible candidates (no meaningful
    performance penalty), with a destroy-data warning; partitions of rotating
    disks are not. A whole disk that has partitions is not selectable: its
    partitions are the candidates, which also guarantees whole-disk and
    partition selections can never overlap.
    """
    if disk.disk_type == "part":
        parent = _parent_disk(disks, disk)
        if parent is None:
            reasons.append("partition with unknown parent disk")
        elif parent.disk_type == "HDD":
            reasons.append("partitions of rotating disks are not eligible")
        elif parent.disk_type in SOLID_STATE_TYPES:
            warnings.append(
                "existing data on this partition will be destroyed; "
                "confirm it is not owned by another system"
            )
        else:
            reasons.append("partition with unknown parent disk type")
        return
    has_partitions = any(
        other.disk_type == "part" and other.parent_path == disk.path for other in disks
    )
    if not has_partitions:
        return
    if disk.disk_type == "HDD":
        reasons.append(
            "has partitions; partitioned rotating disks are not supported — "
            "remove the partitions to use the whole disk"
        )
    else:
        reasons.append(
            "has partitions; select individual partitions below "
            "(or remove them to use the whole disk)"
        )


def validate_vdev_selection(selected: list[DiskInfo]) -> list[str]:
    """Return human-readable problems with the selected vdev membership.

    Enforces device separation: two partitions of the same parent disk in one
    vdev defeats redundancy (a single-device failure domain). Phase 3 creates a
    single vdev per pool; the helper is written vdev-scoped so the wizard's
    Next button and any future multi-vdev work share it.
    """
    problems: list[str] = []
    seen: dict[str, str] = {}
    for member in selected:
        key = member.parent_path or member.path
        label = member.by_id or member.path
        if key in seen:
            problems.append(
                f"{seen[key]} and {label} are on the same physical device; "
                "a vdev must span independent devices"
            )
        else:
            seen[key] = label
    return problems


def validate_pool_name(name: str, existing_names: Container[str]) -> tuple[bool, str]:
    """Return ``(ok, error)`` for a candidate pool name.

    *error* is "" when *name* is valid. Implements the OpenZFS 2.4.4 libzfs
    rules documented at the module constants, plus the project policy length
    cap and a collision check against *existing_names* (imported and
    importable pool names supplied by the caller).
    """
    if not name or not name.strip():
        return False, "pool name must not be empty"
    if len(name) > MAX_POOL_NAME_LEN:
        return False, f"pool name must be at most {MAX_POOL_NAME_LEN} characters"
    if "/" in name:
        return False, "invalid character '/' in pool name; use 'zfs create' to create a dataset"
    invalid = next((c for c in name if c not in _POOL_NAME_CHARS), None)
    if invalid is not None:
        return False, f"invalid character {invalid!r} in pool name"
    if not ("a" <= name[0] <= "z" or "A" <= name[0] <= "Z"):
        return False, "pool name must begin with a letter"
    if name in _RESERVED_EXACT or name == "log":
        return False, f"'{name}' is a reserved word and cannot be used as a pool name"
    if any(name.startswith(prefix) for prefix in _RESERVED_PREFIXES):
        return False, f"'{name}' begins with a reserved word and cannot be used as a pool name"
    if name in existing_names:
        return False, f"pool '{name}' already exists (or is importable)"
    return True, ""


def suggest_ashift(disks: list[DiskInfo]) -> int | None:
    """Return 12 if any selected disk reports physical sector >= 4096, else 9.

    Returns None when no disk reports a physical sector size. This is a hint;
    the wizard decides whether to apply it.
    """
    sectors = [disk.physical_sector for disk in disks if disk.physical_sector]
    if not sectors:
        return None
    return 12 if max(sectors) >= 4096 else 9


@dataclass(frozen=True)
class CapacityEstimate:
    """Capacity estimate for one candidate vdev.

    ``raw_usable_bytes`` is the nominal usable capacity (post-redundancy,
    before RAIDZ padding). ``effective_bytes`` is the user data storable at
    the given block size. ``efficiency_fraction`` is
    ``effective_bytes / raw_usable_bytes`` (1.0 means no padding loss, as for
    stripe and mirror).
    """

    raw_usable_bytes: int
    effective_bytes: int
    efficiency_fraction: float


def estimate_effective_capacity(
    topology: str,
    num_disks: int,
    min_disk_bytes: int,
    block_size_bytes: int,
    sector_size_bytes: int = 4096,
) -> CapacityEstimate:
    """Estimate effective capacity of one vdev at a given block size.

    Implements the width-aware RAIDZ padding model from the design brief:
    for a block of D data sectors on width N with parity P (usable columns
    U = N - P), rows = ceil(D / U), cost = D + rows*P sectors rounded up to
    a multiple of P + 1, so small blocks lose heavily on wide raidz while
    large blocks approach the (N - P) / N asymptote. ``sector_size_bytes``
    defaults to 4096 (ashift 12, the OpenZFS floor on modern drives).

    Raises ValueError for an unknown topology, a disk count below the
    topology minimum, or non-positive sizes.
    """
    spec = TOPOLOGIES.get(topology)
    if spec is None:
        raise ValueError(f"unknown topology: {topology!r}")
    if num_disks < spec.min_disks:
        raise ValueError(f"{topology} requires at least {spec.min_disks} disks")
    if min_disk_bytes <= 0 or block_size_bytes <= 0 or sector_size_bytes <= 0:
        raise ValueError("sizes must be positive")

    if spec.name == "stripe":
        raw = num_disks * min_disk_bytes
        return CapacityEstimate(raw_usable_bytes=raw, effective_bytes=raw,
                                efficiency_fraction=1.0)
    if spec.name == "mirror":
        raw = min_disk_bytes
        return CapacityEstimate(raw_usable_bytes=raw, effective_bytes=raw,
                                efficiency_fraction=1.0)

    parity = spec.parity
    raw_usable = (num_disks - parity) * min_disk_bytes
    total_sectors = (num_disks * min_disk_bytes) // sector_size_bytes
    data_sectors = max(1, block_size_bytes // sector_size_bytes)
    usable_columns = num_disks - parity
    rows = ceil(data_sectors / usable_columns)
    cost = data_sectors + rows * parity
    cost = ((cost + parity) // (parity + 1)) * (parity + 1)
    effective_sectors = (total_sectors // cost) * data_sectors
    effective_bytes = effective_sectors * sector_size_bytes
    return CapacityEstimate(
        raw_usable_bytes=raw_usable,
        effective_bytes=effective_bytes,
        efficiency_fraction=effective_bytes / raw_usable,
    )


def pool_filesystem_options(profile: dict) -> list[tuple[str, str]]:
    """Return ``[(prop, value), ...]`` of live filesystem properties for -O flags.

    Creation-only (``volblocksize``, ``ashift``) and volume-only properties
    are skipped; profiles that do not apply to filesystems yield []. Order is
    canonical (LIVE_PROPERTIES order) so built commands are deterministic.
    """
    if not profile:
        return []
    applicable = properties_for_profile(profile, "filesystem")
    return [(prop, applicable[prop]) for prop in LIVE_PROPERTIES if prop in applicable]
