"""Pure-logic pool-growth helpers (Phase 4).

No GTK and no direct subprocess calls. All ZFS I/O is delegated to callers via
``ZfsRepository`` (mirroring ``pool_create.py``); the only function that reads
live ZFS state, ``scrub_blocks_pool_op``, takes the repository as a parameter.
Policy rules that live here complement the pure argv builders in
``zfs_repository`` (which enforce by-id paths and topology minimums).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from backup_config import log_msg
from disk_repository import DiskInfo
from pool_create import TOPOLOGIES, validate_vdev_selection
from scrub_manager import ScrubState, get_pool_scrub_info
from zfs_repository import TopologyNode

_BY_ID_PREFIX = "/dev/disk/by-id/"

# Infrastructure vdev kinds accepted by validate_infra_vdev / infra_vdev_notes.
_INFRA_VDEV_KINDS = ("special", "log", "cache")

# Vdev group types whose leaves may be grown with `zpool attach`.
_RAIDZ_VDEV_TYPES = ("raidz1", "raidz2", "raidz3")

# Attach kinds returned by classify_attach_target.
ATTACH_STRIPE_TO_MIRROR = "stripe_to_mirror"
ATTACH_MIRROR_GROW = "mirror_grow"
ATTACH_RAIDZ_EXPANSION = "raidz_expansion"


@dataclass(frozen=True)
class AttachTarget:
    """Classification of one attach-target selection.

    ``kind`` is one of ``ATTACH_STRIPE_TO_MIRROR``, ``ATTACH_MIRROR_GROW``, or
    ``ATTACH_RAIDZ_EXPANSION``; ``target_arg`` is the argv token for
    ``build_attach_command`` (the member's by-id path for leaf targets, the vdev
    group name for a raidz expansion). ``error`` is "" when the selection is
    usable, else a human-readable refusal.
    """

    kind: str = ""
    target_arg: str = ""
    error: str = ""


def _disk_aliases(disk: DiskInfo) -> set[str]:
    """Return the path aliases under which a disk may appear in pool configs."""
    aliases = {disk.path, os.path.realpath(disk.path)}
    if disk.by_id:
        by_id_path = os.path.join(_BY_ID_PREFIX, disk.by_id)
        aliases.add(by_id_path)
        aliases.add(os.path.realpath(by_id_path))
    return aliases


def _find_disk(path: str, disks: list[DiskInfo]) -> DiskInfo | None:
    """Return the inventory row matching *path*, or None (realpath + basename)."""
    if not path:
        return None
    real = os.path.realpath(path)
    base = os.path.basename(path)
    for disk in disks:
        aliases = _disk_aliases(disk)
        if path in aliases or real in aliases:
            return disk
        if base and base in {os.path.basename(alias) for alias in aliases}:
            return disk
    return None


def resolve_member_by_id(path: str, disks: list[DiskInfo] | None) -> str | None:
    """Map a ``zpool status -P`` leaf path to its /dev/disk/by-id/ form.

    Returns *path* unchanged when it already lives under /dev/disk/by-id/;
    otherwise finds the ``DiskInfo`` whose path/realpath/by-id basename matches
    and returns its by-id path. Returns None when no by-id identity exists.
    """
    if not path:
        return None
    if path.startswith(_BY_ID_PREFIX):
        return path
    if not disks:
        return None
    disk = _find_disk(path, disks)
    if disk is None or not disk.by_id:
        return None
    return os.path.join(_BY_ID_PREFIX, disk.by_id)


def _find_parent(root: TopologyNode, target: TopologyNode) -> TopologyNode | None:
    """Return the parent of *target* in the tree rooted at *root* (identity)."""
    for child in root.children:
        if child is target:
            return root
        found = _find_parent(child, target)
        if found is not None:
            return found
    return None


def classify_attach_target(
    root: TopologyNode,
    target: TopologyNode,
    disks: list[DiskInfo] | None = None,
) -> AttachTarget:
    """Classify one attach-target selection in a pool topology tree.

    Usable targets: a disk leaf of a stripe vdev (converts it to a mirror), a
    disk leaf of a mirror (grows the mirror to a third leg), or a raidz group
    node (RAIDZ expansion). Capability gating for RAIDZ expansion
    (``ctx.zfs_caps.supports("raidz_expansion")``) is the caller's job.
    Everything else is refused with an explanatory ``error``.
    """
    if target is root:
        return AttachTarget(error="select a vdev member or a raidz group, not the pool itself")
    parent = _find_parent(root, target)
    if parent is None:
        return AttachTarget(error="selection is not part of this pool's topology")

    if target.vdev_type in _RAIDZ_VDEV_TYPES:
        return AttachTarget(kind=ATTACH_RAIDZ_EXPANSION, target_arg=target.name)

    if target.vdev_type != "disk":
        return AttachTarget(error="attach needs a stripe member, a mirror member, or a raidz group")

    # A top-level stripe disk is a direct child of the pool root; nested
    # stripe groups (name starts with "stripe") classify as "stripe".
    if parent.vdev_type in ("stripe", "pool"):
        kind = ATTACH_STRIPE_TO_MIRROR
    elif parent.vdev_type == "mirror":
        kind = ATTACH_MIRROR_GROW
    elif parent.vdev_type in _RAIDZ_VDEV_TYPES:
        return AttachTarget(
            error="select the raidz group itself to expand it, not one of its members"
        )
    else:
        return AttachTarget(
            error="devices in special, log, cache, spare, or replacing vdevs "
            "cannot be attach targets"
        )

    by_id = resolve_member_by_id(target.name, disks)
    if by_id is None:
        return AttachTarget(error=f"member {target.name} has no /dev/disk/by-id path to attach to")
    return AttachTarget(kind=kind, target_arg=by_id)


@dataclass(frozen=True)
class ReplaceSource:
    """Classification of one replace-source selection.

    ``by_id`` is the argv token for ``build_replace_command`` (the member's
    by-id path). ``error`` is "" when the selection is usable, else a
    human-readable refusal.
    """

    by_id: str = ""
    error: str = ""


def classify_replace_source(
    root: TopologyNode,
    target: TopologyNode,
    disks: list[DiskInfo] | None = None,
) -> ReplaceSource:
    """Classify one replace-source selection in a pool topology tree.

    Usable targets: a disk leaf of a data or infrastructure vdev. The pool
    root, vdev groups, and devices already under a ``replacing`` vdev are
    refused with an explanatory ``error``.
    """
    if target is root:
        return ReplaceSource(error="select a disk member to replace, not the pool itself")
    parent = _find_parent(root, target)
    if parent is None:
        return ReplaceSource(error="selection is not part of this pool's topology")

    if target.vdev_type != "disk":
        return ReplaceSource(error="select a disk member to replace, not a vdev group")

    # The `zpool status` parser classifies a replacing vdev's group row as
    # "unknown" (its name has no "/"), so match the name prefix instead.
    if parent.name.startswith("replacing"):
        return ReplaceSource(error="this device is already being replaced")

    by_id = resolve_member_by_id(target.name, disks)
    if by_id is None:
        return ReplaceSource(error=f"member {target.name} has no /dev/disk/by-id path to replace")
    return ReplaceSource(by_id=by_id)


def count_mirror_members(root: TopologyNode, target: TopologyNode) -> int:
    """Return how many members the mirror containing *target* has (0 if none)."""
    parent = _find_parent(root, target)
    if parent is None or parent.vdev_type != "mirror":
        return 0
    return len(parent.children)


def has_mirror_member(root: TopologyNode) -> bool:
    """True when the tree contains a disk leaf of a mirror vdev (a detach target)."""
    leaves = list(root.children)
    while leaves:
        node = leaves.pop()
        if node.vdev_type == "disk":
            parent = _find_parent(root, node)
            if parent is not None and parent.vdev_type == "mirror":
                return True
        else:
            leaves.extend(node.children)
    return False


def assess_detach(
    root: TopologyNode,
    target: TopologyNode,
) -> tuple[str, list[str]]:
    """Assess one detach selection. Returns ``(error, warnings)``.

    Only disk leaves of a mirror vdev may be detached (per zpool-detach(8)).
    All successful assessments carry the irreversibility/redundancy warnings the
    dialog must show before its typed confirmation.
    """
    if target is root:
        return "select a mirror member to detach, not the pool itself", []
    parent = _find_parent(root, target)
    if parent is None:
        return "selection is not part of this pool's topology", []

    if target.vdev_type != "disk":
        return "only a disk member of a mirror vdev can be detached", []

    if parent.vdev_type in ("stripe", "pool"):
        message = (
            "only mirror members can be detached; this device is a non-redundant stripe member"
        )
        return message, []
    if parent.vdev_type in _RAIDZ_VDEV_TYPES:
        return (
            "only mirror members can be detached; raidz members cannot be detached",
            [],
        )
    if parent.vdev_type != "mirror":
        message = (
            "only mirror members can be detached; special, log, cache, "
            "spare, and replacing devices cannot"
        )
        return message, []

    warnings = [("detaching reduces redundancy and is not undoable without re-attaching a device")]
    if len(parent.children) == 2:
        warnings.append(
            "this mirror has only 2 members: after the detach it becomes a "
            "single non-redundant disk"
        )
    return "", warnings


def validate_replace_pair(
    source_path: str,
    replacement: DiskInfo,
    disks: list[DiskInfo],
) -> tuple[list[str], list[str]]:
    """Validate a replace selection. Returns ``(problems, warnings)``.

    *problems* block the operation; the smaller-replacement *warning* is the
    brief's "warn but let typed confirmation guard it" case.
    """
    problems: list[str] = []
    warnings: list[str] = []

    source = _find_disk(source_path, disks)
    if source is None:
        problems.append(f"source device {source_path} not found in the disk inventory")

    same_device = source is not None and (
        replacement.path == source.path
        or (replacement.parent_path is not None and replacement.parent_path == source.path)
        or (source.parent_path is not None and source.parent_path == replacement.path)
        or _same_basename(replacement, source)
    )
    if same_device:
        problems.append("the replacement is the same device as the source")
    if not replacement.by_id:
        problems.append(f"replacement {replacement.path} has no /dev/disk/by-id path")

    if (
        source is not None
        and source.size_bytes > 0
        and replacement.size_bytes > 0
        and replacement.size_bytes < source.size_bytes
    ):
        warnings.append(
            f"the replacement ({replacement.size_human}) is smaller than the "
            f"source device; zpool replace may fail or reduce available space"
        )
    return problems, warnings


def _same_basename(a: DiskInfo, b: DiskInfo) -> bool:
    """True when two disks share a basename alias (e.g. by-id basename match)."""
    names_a = {os.path.basename(alias) for alias in _disk_aliases(a)}
    names_b = {os.path.basename(alias) for alias in _disk_aliases(b)}
    return bool(names_a & names_b)


def validate_infra_vdev(
    kind: str,
    topology: str,
    selected: list[DiskInfo],
) -> tuple[list[str], list[str]]:
    """Validate one special/log/cache vdev addition. Returns ``(problems, warnings)``.

    A special vdev must be a mirror — losing it loses the entire pool. A log
    (SLOG) is allowed as a single device but a mirror is recommended. A cache
    (L2ARC) cannot be mirrored and needs no redundancy. Device separation
    (independent physical devices) reuses ``pool_create.validate_vdev_selection``.
    """
    problems: list[str] = []
    warnings: list[str] = []

    if kind not in _INFRA_VDEV_KINDS:
        return [f"unknown infrastructure vdev kind: {kind!r}"], []

    spec = TOPOLOGIES.get(topology)
    if spec is None:
        problems.append(f"unknown topology: {topology!r}")
    elif len(selected) < spec.min_disks:
        problems.append(f"{topology} requires at least {spec.min_disks} devices")

    problems.extend(validate_vdev_selection(selected))

    if kind == "special":
        if topology != "mirror":
            problems.append("a special vdev must be a mirror of at least 2 devices")
        warnings.append(
            "losing the special (metadata) vdev loses the entire pool — it "
            "must be redundant and on reliable devices"
        )
    elif kind == "log":
        if topology == "stripe":
            warnings.append(
                "a single log device loses sync-write acceleration if it "
                "fails; a mirrored log is recommended"
            )
    elif topology == "mirror":
        problems.append("cache vdevs cannot be mirrored")
    return problems, warnings


def validate_growth_vdev_selection(selected: list[DiskInfo]) -> list[str]:
    """Return problems with an Add-Data-Vdev membership selection.

    Device separation only: minimum member counts are enforced by
    ``zfs_repository.build_add_vdev_command``, which raises ValueError.
    """
    return validate_vdev_selection(selected)


def mixed_size_warning(selected: list[DiskInfo]) -> str | None:
    """Warn when selected members have differing known sizes, else None."""
    sizes = {disk.size_bytes for disk in selected if disk.size_bytes > 0}
    if len(sizes) > 1:
        return "members differ in size; vdev capacity is limited to the smallest member"
    return None


def scrub_blocks_pool_op(pool_name: str, repo) -> str | None:
    """Return a refusal message when a pool operation must wait for a scrub.

    Refuses while the pool's scrub state is SCANNING or PAUSED (the user should
    pause/stop it from the Pools tab Scrub Manager). Queued, finished, canceled,
    none, and unknown states do not block. A status-read failure logs a WARN and
    does not block — ZFS itself is the final arbiter.
    """
    try:
        info = get_pool_scrub_info(pool_name, repo=repo)
    except (subprocess.CalledProcessError, OSError) as exc:
        log_msg(f"WARN: could not read scrub state for pool '{pool_name}': {exc}")
        return None
    if info.state in (ScrubState.SCANNING, ScrubState.PAUSED):
        return (
            f"pool '{pool_name}' has a scrub {info.state.value}; pause or stop "
            "it from the Pools tab Scrub Manager before running a pool operation"
        )
    return None


def raidz_expansion_notes() -> list[str]:
    """Warning/notes lines shown before a RAIDZ expansion is confirmed."""
    return [
        (
            "existing data keeps its old data:parity ratio until rewritten; "
            "the new capacity applies to new writes"
        ),
        (
            "after the expansion, use the Rewrite Data action on the Disks "
            "page per filesystem dataset to restripe existing data at the "
            "new ratio"
        ),
    ]


def infra_vdev_notes(kind: str) -> list[str]:
    """Tailored explainer lines for one infrastructure vdev kind."""
    if kind == "special":
        return [
            (
                "a special vdev stores metadata (and small blocks when "
                "special_small_blocks is set) — it sees most of the pool's "
                "random IO"
            ),
            ("a special vdev must be a mirror: if it is lost, the entire pool is lost"),
        ]
    if kind == "log":
        return [
            ("a log device (SLOG) only accelerates synchronous writes; it holds no pool data"),
            (
                "loss of an SLOG vdev may lose a narrow window of "
                "already-acknowledged synchronous writes (application data, "
                "not metadata) — mirror the SLOG on separate physical "
                "devices if that cannot be tolerated"
            ),
            (
                "an SLOG only needs to hold ~5 seconds of synchronous writes "
                "(max pool write speed × 5 s); a larger device gains nothing"
            ),
        ]
    if kind == "cache":
        return [
            (
                "a cache device (L2ARC) is a read cache — it holds no pool "
                "data and needs no redundancy"
            ),
        ]
    raise ValueError(f"unknown infrastructure vdev kind: {kind!r}")
