"""ZFS command repository — isolates zfs/zpool subprocess calls.

All direct zfs/zpool invocations from the GUI layer live here. Methods return
typed dataclasses for reads and booleans for mutating operations. Read methods
raise subprocess.CalledProcessError on failure so callers can decide how to
handle errors; write methods swallow the exception and return success/failure.
"""

import json
import os
import re
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import path_utils
from logging_config import log_msg
from pool_create import TOPOLOGIES, validate_raid10_count


def is_dataset_encrypted(path):
    """Return True if *path* resides on an encrypted ZFS dataset."""
    if not path:
        return False
    abs_path = os.path.abspath(path)
    try:
        result = subprocess.run(
            ["zfs", "list", "-H", "-o", "name,mountpoint"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        datasets = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                datasets.append((parts[0], parts[1]))
        candidate = None
        for ds, mp in datasets:
            mp = mp.rstrip("/")
            if (abs_path.startswith(mp + "/") or abs_path == mp) and (
                candidate is None or len(mp) > len(candidate[1])
            ):
                candidate = (ds, mp)
        if candidate is None:
            return False
        ds_name = candidate[0]
        result = subprocess.run(
            ["zfs", "get", "-H", "-o", "value", "encryption", ds_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        enc = result.stdout.strip()
        return enc not in ("", "-", "off")
    except Exception:
        return False


# Regex: ^[\s]*errors:\s*(.+?)\s*$
# Purpose: Extract the summary text from the "errors:" line in zpool status.
# Group 1: Error summary text, e.g. "No known data errors".
_ERRORS_LINE_RE = re.compile(r"^[\s]*errors:\s*(.+?)\s*$", re.MULTILINE)

# Regex: ^\s*(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$
# Purpose: Parse a vdev/device line from the zpool status config table.
# Groups: 1 name, 2 state, 3 read errors, 4 write errors, 5 checksum errors.
_VDEV_ERRORS_RE = re.compile(
    r"^\s*(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$",
    re.MULTILINE,
)


@dataclass
class PoolRow:
    """One line from `zpool list -H -o name,health,size,alloc,free,cap,ckpoint`."""

    name: str
    health: str
    size: str
    alloc: str
    free: str
    cap: str
    ckpoint: str


@dataclass
class DatasetRow:
    """One line from `zfs list -H -o name,creation,type,used,avail,refer,origin,clones,mounted`."""

    name: str
    creation: str
    ds_type: str
    used: str
    avail: str
    refer: str
    origin: str
    clones: str
    mounted: str = "-"


@dataclass
class SnapshotRow:
    """One line from
    `zfs list -t snapshot -H -o name,creation,type,used,avail,refer,origin,clones`.
    """

    name: str
    creation: str
    ds_type: str
    used: str
    avail: str
    refer: str
    origin: str
    clones: str


@dataclass
class HoldRow:
    """One line from `zfs holds -H <snapshot>`."""

    snapshot: str
    tag: str
    date: str


@dataclass
class LoopPartition:
    """One mountable entry on a loop device backing a zvol.

    When the loop device has a partition table, one entry per partition; when
    it does not, a single entry for the loop device itself. `has_filesystem`
    is False for partitions with no detectable filesystem (or a bare loop
    device with no filesystem).
    """

    device: str
    fstype: str
    mountpoint: str
    has_filesystem: bool


def zvol_device_path(dataset: str) -> str:
    """Return the /dev/zvol block-device path for a ZFS volume dataset."""
    return f"/dev/zvol/{dataset}"


@dataclass
class AshiftInfo:
    """Configured and effective pool ashift values."""

    configured: str | None
    effective: int | None


@dataclass
class TopologyNode:
    """One node in a `zpool status -P` vdev topology tree."""

    name: str
    vdev_type: str
    state: str
    read: int
    write: int
    cksum: int
    ashift: int | None
    children: list["TopologyNode"]


# Regex: ^(\s*)(\S+)(?:\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+))?\s*$
# Purpose: Parse a vdev/device row from `zpool status -P` config output.
# Group 1: leading whitespace (indentation).
# Group 2: name (vdev label or full device path).
# Groups 3-6: optional state, read/write/checksum error counters.
_TOPOLOGY_LINE_RE = re.compile(
    r"^(\s*)(\S+)(?:\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+))?\s*$",
    re.MULTILINE,
)

# Regex: ^\s*ashift:\s*(\d+)\s*$
# Purpose: Extract the effective ashift value from `zdb -C` output.
# Group 1: the ashift value as a decimal integer.
_ASHIFT_RE = re.compile(r"^\s*ashift:\s*(\d+)\s*$", re.MULTILINE)

_BY_ID_PREFIX = "/dev/disk/by-id/"

# Infrastructure vdev kinds accepted by build_add_vdev_command's `kind`.
_INFRA_VDEV_KINDS = ("special", "log", "cache")

# Vdev group-name prefixes build_attach_command accepts as an attach target
# (per zpool-attach(8): mirror or raidz group names such as "raidz2-0").
_ATTACHABLE_VDEV_PREFIXES = ("mirror", "raidz1", "raidz2", "raidz3")

# Subcommands executed by ZfsRepository.run_pool_command; `zpool create`
# remains exclusive to create_pool.
_POOL_GROWTH_SUBCOMMANDS = ("add", "attach", "replace", "detach")

# First tokens of vdev group header lines in a `zpool import` config section.
# Leaf device lines are everything else (paths or short kernel names).
_IMPORT_VDEV_KEYWORDS = (
    "mirror",
    "raidz",
    "draid",
    "spare",
    "spares",
    "log",
    "logs",
    "cache",
    "special",
    "replacing",
)


def _parse_importable_pools_config(raw: str) -> dict[str, list[str]]:
    """Parse `zpool import` output into {pool_name: [leaf device paths]}.

    Pools whose config names any zvol-backed device (first token starting
    with 'zd') are excluded entirely. The pool root line (first config line,
    whose name equals the pool name) and vdev group headers (mirror-N,
    raidzN-M, spare/log/cache/special section headings) are not leaves; every
    other config line's first token is a leaf device path. Pools with no
    config section appear with an empty path list.
    """
    pools: dict[str, list[str]] = {}
    current_name: str | None = None
    in_config = False
    root_seen = False
    is_zvol_backed = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("pool:"):
            if current_name is not None and not is_zvol_backed:
                pools.setdefault(current_name, [])
            current_name = stripped.split(":", 1)[1].strip()
            in_config = False
            root_seen = False
            is_zvol_backed = False
        elif stripped == "config:":
            in_config = True
        elif in_config and stripped:
            token = stripped.split()[0]
            if token.startswith("zd"):
                is_zvol_backed = True
            elif not root_seen:
                # First config line is the pool root itself.
                root_seen = True
            elif token != current_name and not token.startswith(_IMPORT_VDEV_KEYWORDS):
                pools.setdefault(current_name, []).append(token)
    if current_name is not None and not is_zvol_backed:
        pools.setdefault(current_name, [])
    return pools


def _parse_lsblk_partitions(raw: str, loop_dev: str) -> list[LoopPartition]:
    """Parse `lsblk --json` output for *loop_dev* into LoopPartition entries.

    If the device has child partitions (type "part"), one entry per child is
    returned; otherwise a single entry describes the loop device itself.
    """
    data = json.loads(raw)
    devices = data.get("blockdevices", [])
    base_name = os.path.basename(loop_dev)
    row = next((blk for blk in devices if blk.get("name") == base_name), None)
    if row is None and devices:
        row = devices[0]
    if row is None:
        return []
    children = row.get("children") or []
    entries = children if children else [row]
    partitions = []
    for entry in entries:
        fstype = entry.get("fstype") or ""
        partitions.append(
            LoopPartition(
                device=f"/dev/{entry.get('name', '')}",
                fstype=fstype,
                mountpoint=entry.get("mountpoint") or "",
                has_filesystem=bool(fstype),
            )
        )
    return partitions


def _parse_loop_attach_output(raw: str) -> str:
    """Return the /dev/loopN path from `losetup --show` output."""
    return raw.strip().splitlines()[0].strip() if raw.strip() else ""


def _parse_loop_find_output(raw: str) -> str | None:
    """Return the /dev/loopN path from `losetup -j` output, or None."""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("/dev/"):
            return line.split(":", 1)[0].strip()
    return None


def _validate_by_id_path(path: str) -> None:
    """Raise ValueError unless *path* is an absolute /dev/disk/by-id path."""
    if not path.startswith(_BY_ID_PREFIX) or ".." in path or any(c.isspace() for c in path):
        raise ValueError(f"path must be an absolute /dev/disk/by-id path: {path!r}")


def _is_vdev_group_name(name: str) -> bool:
    """Return True for a `zpool status` vdev group name (mirror-0, raidz2-0, …).

    Validated without a regex: the part before the last '-' must be an
    attachable vdev keyword and the part after it a numeric index, so
    "stripe-0", "raidz2", "mirror-x", and "replacing-0" are all rejected.
    """
    prefix, sep, index = name.rpartition("-")
    return bool(sep) and prefix in _ATTACHABLE_VDEV_PREFIXES and index.isdigit()


def build_create_pool_command(
    pool_name: str,
    topology: str,
    by_id_paths: list[str],
    ashift: int | None = None,
    options: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Build the exact `zpool create` argv for a new pool.

    Pure function: no subprocess. Argument order:
    ``zpool create [-o ashift=N] [-O prop=value ...] <pool> <mirror|raidzN>
    <paths…>`` (stripe emits no topology keyword). The special topology
    "raid10" requires an even count of at least 4 disks and emits striped
    mirrors: ``<pool> mirror d1 d2 mirror d3 d4 …``. All paths must live under
    /dev/disk/by-id/ (mandatory for stable naming, and the command destroys
    data on the named devices). Raises ValueError on unknown topology,
    membership below the topology minimum (or an odd/below-minimum raid10
    count), non-by-id paths, or invalid
    ashift/options; full pool-name rules live in
    ``pool_create.validate_pool_name``.
    """
    if topology == "raid10":
        problems = validate_raid10_count(len(by_id_paths))
        if problems:
            raise ValueError("; ".join(problems))
    else:
        spec = TOPOLOGIES.get(topology)
        if spec is None:
            raise ValueError(f"unknown topology: {topology!r}")
        if len(by_id_paths) < spec.min_disks:
            raise ValueError(f"{topology} requires at least {spec.min_disks} disks")
    if not pool_name:
        raise ValueError("pool name must not be empty")
    for path in by_id_paths:
        _validate_by_id_path(path)
    if ashift is not None and not 9 <= ashift <= 16:
        raise ValueError(
            f"pool blocksize must be between 512 bytes (ashift 9) and "
            f"65536 bytes (ashift 16), got {ashift}"
        )

    cmd = ["zpool", "create"]
    if ashift is not None:
        cmd += ["-o", f"ashift={ashift}"]
    for prop, value in options or []:
        if not prop or "=" in prop or any(c.isspace() for c in prop):
            raise ValueError(f"invalid property name: {prop!r}")
        cmd += ["-O", f"{prop}={value}"]
    cmd.append(pool_name)
    if topology == "raid10":
        # ZFS has no raid10 keyword: striped mirrors are emitted as
        # consecutive "mirror d1 d2 mirror d3 d4 …" vdev groups.
        paths = list(by_id_paths)
        for i in range(0, len(paths), 2):
            cmd.append("mirror")
            cmd += paths[i : i + 2]
    else:
        if topology != "stripe":
            cmd.append(topology)
        cmd += list(by_id_paths)
    return cmd


def build_add_vdev_command(
    pool_name: str,
    topology: str,
    by_id_paths: list[str],
    kind: str | None = None,
) -> list[str]:
    """Build the exact `zpool add` argv for a new vdev on an existing pool.

    Pure function: no subprocess. Without *kind* this builds a data vdev:
    ``zpool add <pool> <mirror|raidzN> <paths…>`` (stripe emits no keyword),
    reusing ``pool_create.TOPOLOGIES`` for the minimum member counts. With
    *kind* one of "special", "log", or "cache" it builds an infrastructure
    vdev: ``zpool add <pool> <kind> [mirror] <paths…>`` accepting only the
    "stripe" (single device, no keyword) and "mirror" topologies —
    zpoolconcepts(7) states cache vdevs cannot be mirrored, so "cache" with
    "mirror" is rejected here. All paths must live under /dev/disk/by-id/.
    Raises ValueError on unknown topology/kind, membership below the
    minimum, or non-by-id paths. Policy-level rules (e.g. a special vdev
    should be mirrored) live in ``pool_growth.validate_infra_vdev``.
    """
    if not pool_name:
        raise ValueError("pool name must not be empty")
    spec = TOPOLOGIES.get(topology)
    if spec is None:
        raise ValueError(f"unknown topology: {topology!r}")
    for path in by_id_paths:
        _validate_by_id_path(path)
    if len(by_id_paths) < spec.min_disks:
        raise ValueError(f"{topology} requires at least {spec.min_disks} disks")

    cmd = ["zpool", "add", pool_name]
    if kind is not None:
        if kind not in _INFRA_VDEV_KINDS:
            raise ValueError(f"unknown infrastructure vdev kind: {kind!r}")
        if topology not in ("stripe", "mirror"):
            raise ValueError(
                f"infrastructure vdev kind {kind!r} only supports "
                f"stripe or mirror, not {topology!r}"
            )
        if kind == "cache" and topology == "mirror":
            raise ValueError("cache vdevs cannot be mirrored")
        cmd.append(kind)
        if topology == "mirror":
            cmd.append("mirror")
    elif topology != "stripe":
        cmd.append(topology)
    cmd += list(by_id_paths)
    return cmd


def build_attach_command(pool_name: str, target: str, new_path: str) -> list[str]:
    """Build the exact `zpool attach` argv.

    Pure function: no subprocess. *target* is either the by-id path of an
    existing leaf member (converting a stripe/plain vdev into a mirror) or a
    vdev group name from ``zpool status`` such as "raidz2-0" (RAIDZ
    expansion, per zpool-attach(8)). *new_path* must be a disk under
    /dev/disk/by-id/. Raises ValueError on invalid input; capability gating
    for RAIDZ expansion (``zfs_capabilities.supports("raidz_expansion")``)
    is the caller's responsibility.
    """
    if not pool_name:
        raise ValueError("pool name must not be empty")
    if not target.startswith(_BY_ID_PREFIX) and not _is_vdev_group_name(target):
        raise ValueError(
            f"target must be a /dev/disk/by-id path or a vdev name (mirror-N, raidzN-N): {target!r}"
        )
    _validate_by_id_path(new_path)
    return ["zpool", "attach", pool_name, target, new_path]


def build_replace_command(pool_name: str, source_path: str, new_path: str) -> list[str]:
    """Build the exact `zpool replace` argv.

    Pure function: no subprocess. Both devices must be absolute
    /dev/disk/by-id paths. zpool itself requires the replacement to be at
    least as large as the source; ``pool_growth.validate_replace_pair``
    flags a smaller replacement in advance.
    """
    if not pool_name:
        raise ValueError("pool name must not be empty")
    _validate_by_id_path(source_path)
    _validate_by_id_path(new_path)
    return ["zpool", "replace", pool_name, source_path, new_path]


def build_detach_command(pool_name: str, member_path: str) -> list[str]:
    """Build the exact `zpool detach` argv.

    Pure function: no subprocess. *member_path* must be an absolute
    /dev/disk/by-id path. Per zpool-detach(8), detach applies to mirror
    members (and spare/replacing leaves) only; that policy is enforced by
    ``pool_growth.assess_detach`` before this builder is called.
    """
    if not pool_name:
        raise ValueError("pool name must not be empty")
    _validate_by_id_path(member_path)
    return ["zpool", "detach", pool_name, member_path]


def build_recursive_snapshot_command(target: str, snap_name: str) -> list[str]:
    """Build the exact `zfs snapshot -r` argv for a migration snapshot.

    Pure function: no subprocess. *target* is a pool name or dataset whose
    whole subtree is snapshotted (pool root or one top-level dataset).
    *snap_name* is the part after ``@`` (no ``@``, no ``/``); it must not be
    empty. Migration snapshots use a bucket-less name (label ``migrate``) so
    retention policies, which prune only their own label's d/w/m/s buckets,
    never touch them.
    """
    if not target:
        raise ValueError("snapshot target must not be empty")
    if not snap_name or "@" in snap_name or "/" in snap_name:
        raise ValueError(f"invalid snapshot name: {snap_name!r}")
    return ["zfs", "snapshot", "-r", f"{target}@{snap_name}"]


def build_migration_send_receive_command(
    source_fs: str,
    dest_fs: str,
    snap_name: str,
    rate_limit: str = "",
) -> list[str]:
    """Build the argv for one migration copy step.

    Pure function: no subprocess. Returns a ``bash -c`` argv that sources
    ``zfs-migrate-send`` (the shared transfer library wrapper) and runs
    ``zfs_migrate_send`` with ``sourcefs``/``destfs``/``snapname`` assigned,
    so the transfer is resumable (an interrupted copy leaves a receive
    resume token on the destination; re-running resumes from it) and carries
    ``pv`` in the pipeline for live progress, optionally rate-limited via
    *rate_limit* (a ``pv -L`` value such as ``100m``; empty = unlimited).
    The wrapper sends ``zfs send -Rw <source>@<snap>`` and receives with
    ``zfs receive -u -F -s -v <dest>``: ``-R`` makes a replication stream
    (descendants, snapshots, properties); ``-w`` sends raw so encrypted
    datasets survive; ``-u`` keeps received datasets unmounted so their
    (preserved) mountpoints do not collide with the still-mounted source;
    ``-F`` lets a re-run roll the destination back to the stream; ``-s``
    keeps the receive resumable; ``-v`` logs each dataset as it is received
    so progress through the tree is visible in the session log. Raises
    ValueError on empty/invalid names or an invalid *rate_limit*; callers
    enforce policy (locks, capacity, cutover ordering).
    """
    if not source_fs:
        raise ValueError("source dataset must not be empty")
    if not dest_fs:
        raise ValueError("destination dataset must not be empty")
    if not snap_name or "@" in snap_name or "/" in snap_name:
        raise ValueError(f"invalid snapshot name: {snap_name!r}")
    if rate_limit and not re.fullmatch(r"[0-9]+[kKmMgGtT]?", rate_limit):
        raise ValueError(f"invalid rate limit: {rate_limit!r}")
    script = path_utils.resolve_local_bin(
        "zfs-migrate-send", script_dir=os.path.dirname(os.path.realpath(__file__))
    )
    if not script:
        raise ValueError("zfs-migrate-send script could not be located")
    # zfs-migrate-send bootstraps bashinit itself (and transfer-lib.sh, which
    # it sources, loads ~/bashinit), so no pre-source is needed here.
    parts = [
        f"source {shlex.quote(script)}",
        f"sourcefs={shlex.quote(source_fs)}",
        f"destfs={shlex.quote(dest_fs)}",
        f"snapname={shlex.quote(snap_name)}",
    ]
    if rate_limit:
        parts.append(f"pv_rate_limit={shlex.quote(rate_limit)}")
    parts.append("zfs_migrate_send")
    return ["bash", "-c", "; ".join(parts)]


def build_pool_export_command(pool_name: str) -> list[str]:
    """Build the exact `zpool export` argv.

    Pure function: no subprocess. Export refuses while datasets are busy
    (mounted shares, running VMs on zvols); that is the cutover gate.
    """
    if not pool_name:
        raise ValueError("pool name must not be empty")
    return ["zpool", "export", pool_name]


def build_pool_import_rename_command(temp_name: str, new_name: str) -> list[str]:
    """Build the exact `zpool import` argv that renames a pool at import.

    Pure function: no subprocess. Importing the migrated pool under the
    source pool's old name restores every dataset path (`pool/dataset`), so
    consumers that reference datasets by name survive the migration.
    Raises ValueError on empty names or when both names are identical.
    Full pool-name validation lives in ``pool_create.validate_pool_name``.
    """
    if not temp_name:
        raise ValueError("current pool name must not be empty")
    if not new_name:
        raise ValueError("new pool name must not be empty")
    if temp_name == new_name:
        raise ValueError("new pool name must differ from the current name")
    return ["zpool", "import", temp_name, new_name]


def build_pool_destroy_command(pool_name: str) -> list[str]:
    """Build the exact `zpool destroy` argv.

    Pure function: no subprocess. Destroys a pool and all its data — the
    migration wizard gates this behind typed confirmation (holding-pool
    mode only, after the copy to the holding pool has been verified).
    """
    if not pool_name:
        raise ValueError("pool name must not be empty")
    return ["zpool", "destroy", pool_name]


def build_destroy_dataset_command(dataset: str, recursive: bool = True) -> list[str]:
    """Build the exact `zfs destroy` argv for one dataset tree.

    Pure function: no subprocess. With *recursive* True (the default) the
    command is `zfs destroy -r <dataset>`, removing the dataset and its
    descendants — used to drop migration copies from a holding pool.
    """
    if not dataset:
        raise ValueError("dataset must not be empty")
    cmd = ["zfs", "destroy"]
    if recursive:
        cmd.append("-r")
    cmd.append(dataset)
    return cmd


class ZfsRepository:
    """Wrap zfs/zpool subprocess calls for testability and isolation."""

    def __init__(self, sudo: bool = False):
        self.sudo = sudo

    def _zfs(self, *args: str) -> list[str]:
        return (["sudo", "zfs"] if self.sudo else ["zfs"]) + list(args)

    def _zpool(self, *args: str) -> list[str]:
        return (["sudo", "zpool"] if self.sudo else ["zpool"]) + list(args)

    def _run(self, cmd: list[str], check: bool = True, timeout: int | None = None):
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)

    # ------------------------------------------------------------------
    # Pool reads
    # ------------------------------------------------------------------

    def list_pools(self) -> list[PoolRow]:
        """Return all pools with health, size, alloc, free, capacity, and checkpoint."""
        result = self._run(
            self._zpool("list", "-H", "-o", "name,health,size,alloc,free,cap,ckpoint")
        )
        rows = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            rows.append(PoolRow(*parts[:7]))
        return rows

    def list_pools_full(self) -> list[dict]:
        """Return all pools with the extended 9-column field set."""
        result = self._run(
            self._zpool("list", "-H", "-o", "name,size,alloc,free,freeing,ckpoint,frag,cap,health")
        )
        rows = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 9:
                continue
            rows.append(
                {
                    "name": parts[0],
                    "size": parts[1],
                    "alloc": parts[2],
                    "free": parts[3],
                    "freeing": parts[4],
                    "ckpoint": parts[5],
                    "frag": parts[6],
                    "cap": parts[7],
                    "health": parts[8],
                }
            )
        return rows

    def pool_status(self, pool: str, timeout: int | None = None) -> str:
        """Return raw `zpool status` text (empty on failure)."""
        result = self._run(self._zpool("status", pool), check=False, timeout=timeout)
        return result.stdout

    def all_pool_status_text(self, timeout: int | None = 15) -> str:
        """Return raw `zpool status` text for all pools in one call (empty on failure)."""
        try:
            result = self._run(self._zpool("status"), check=False, timeout=timeout)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout

    def pool_get_all(self, pool: str, timeout: int | None = None) -> str:
        """Return raw `zpool get all` text for *pool* (empty on failure)."""
        result = self._run(self._zpool("get", "all", pool), check=False, timeout=timeout)
        return result.stdout

    def pool_status_errors(self, pool: str, timeout: int | None = None) -> dict:
        """Parse `zpool status` and return a structured error report.

        Returns a dict with keys:
            has_errors (bool): True if any data or vdev errors are present.
            errors_summary (str): Short human-readable summary.
            data_errors (List[str]): Lines/files listed under the errors block.
            vdev_errors (List[Dict[str, int]]): Vdevs with non-zero error
                counters. Each dict has keys: name, state, read, write, cksum.

        On failure or missing output, returns has_errors=False and empty
        collections.
        """
        raw = self.pool_status(pool, timeout=timeout)
        result: dict[str, object] = {
            "has_errors": False,
            "errors_summary": "",
            "data_errors": [],
            "vdev_errors": [],
        }
        if not raw:
            result["errors_summary"] = "status unavailable"
            return result

        # Extract the "errors:" summary line.
        m = _ERRORS_LINE_RE.search(raw)
        if m:
            summary = m.group(1).strip()
            result["errors_summary"] = summary
            if summary.lower() != "no known data errors":
                result["has_errors"] = True
                # Capture any subsequent lines/files listed under errors.
                data_errors: list[str] = []
                capture = False
                for line in raw.splitlines():
                    stripped = line.strip()
                    if stripped.lower().startswith("errors:"):
                        capture = True
                        continue
                    if capture:
                        if not stripped:
                            break
                        if stripped.lower() in (
                            "config:",
                            "pool:",
                            "state:",
                            "scan:",
                            "logs:",
                            "cache:",
                        ):
                            break
                        data_errors.append(stripped)
                result["data_errors"] = data_errors
        else:
            result["errors_summary"] = "status unavailable"

        # Look for vdevs with non-zero READ/WRITE/CKSUM counters.
        vdev_errors = []
        for vm in _VDEV_ERRORS_RE.finditer(raw):
            name, state, read_s, write_s, cksum_s = vm.groups()
            read = int(read_s)
            write = int(write_s)
            cksum = int(cksum_s)
            if read > 0 or write > 0 or cksum > 0:
                vdev_errors.append(
                    {
                        "name": name,
                        "state": state,
                        "read": read,
                        "write": write,
                        "cksum": cksum,
                    }
                )
        if vdev_errors:
            result["has_errors"] = True
            result["vdev_errors"] = vdev_errors
            # Upgrade the summary if it was the generic no-errors line.
            parts = []
            for vdev in vdev_errors:
                counters = []
                if vdev["read"] > 0:
                    counters.append(f"read={vdev['read']}")
                if vdev["write"] > 0:
                    counters.append(f"write={vdev['write']}")
                if vdev["cksum"] > 0:
                    counters.append(f"cksum={vdev['cksum']}")
                parts.append(f"{vdev['name']} ({', '.join(counters)})")
            result["errors_summary"] = "vdev errors: " + "; ".join(parts)

        return result

    # ------------------------------------------------------------------
    # Pool writes
    # ------------------------------------------------------------------

    def importable_pools_raw(self) -> str:
        """Return raw `zpool import` output."""
        result = self._run(self._zpool("import"), check=False)
        return result.stdout

    def list_importable_pool_names(self) -> set[str]:
        """Return names of pools that can be imported.

        Parses `zpool import` output and filters out pools whose vdevs are
        zvol-backed (device names starting with `zd`). These are normally
        VM-attached pools that should not be touched by this tool.
        """
        return set(_parse_importable_pools_config(self.importable_pools_raw()))

    def list_importable_pool_devices(self) -> dict[str, list[str]]:
        """Return importable pool names mapped to their leaf vdev device paths.

        Same parsing and zvol-backed filtering as `list_importable_pool_names`.
        Feeds `pool_create.disk_eligibility`'s importable_member_paths so
        member disks of not-yet-imported pools are ineligible for pool creation.
        """
        return _parse_importable_pools_config(self.importable_pools_raw())

    def import_pool(self, pool: str) -> bool:
        """Import one pool by name."""
        result = self._run(self._zpool("import", pool), check=False)
        return result.returncode == 0

    def export_pool(self, pool: str) -> bool:
        """Export one pool by name."""
        result = self._run(self._zpool("export", pool), check=False)
        return result.returncode == 0

    def create_pool_dry_run(self, cmd: list[str]) -> tuple[int, str]:
        """Run a `zpool create` argv as a dry run, injecting `-n` after `create`.

        Returns (returncode, output) where output is stdout when non-empty,
        else stderr, so failures surface zpool's error text.
        """
        if len(cmd) < 2 or cmd[0] != "zpool" or cmd[1] != "create":
            raise ValueError(f"not a zpool create command: {cmd!r}")
        result = self._run(self._zpool("create", "-n", *cmd[2:]), check=False)
        output = result.stdout if result.stdout.strip() else result.stderr
        return result.returncode, output

    def create_pool(self, cmd: list[str]) -> bool:
        """Execute a `zpool create` argv. Returns True on success."""
        if len(cmd) < 2 or cmd[0] != "zpool" or cmd[1] != "create":
            raise ValueError(f"not a zpool create command: {cmd!r}")
        log_msg(f"INFO: creating pool: {shlex.join(cmd)}")
        result = self._run(self._zpool(*cmd[1:]), check=False)
        if result.returncode != 0:
            log_msg(f"WARN: zpool create failed (rc={result.returncode}): {result.stderr.strip()}")
            return False
        return True

    def run_pool_command(self, cmd: list[str]) -> bool:
        """Execute a pre-built pool-growth argv. Returns True on success.

        Accepts only ``zpool add/attach/replace/detach`` argv produced by the
        build_* helpers; ``zpool create`` remains exclusive to
        ``create_pool``.
        """
        if len(cmd) < 2 or cmd[0] != "zpool" or cmd[1] not in _POOL_GROWTH_SUBCOMMANDS:
            raise ValueError(f"not a zpool add/attach/replace/detach command: {cmd!r}")
        log_msg(f"INFO: pool operation: {shlex.join(cmd)}")
        result = self._run(self._zpool(*cmd[1:]), check=False)
        if result.returncode != 0:
            log_msg(
                f"WARN: zpool {cmd[1]} failed (rc={result.returncode}): {result.stderr.strip()}"
            )
            return False
        return True

    def start_scrub(self, pool: str, timeout: int | None = None) -> bool:
        """Start a scrub on *pool*."""
        cmd = self._zpool("scrub", pool)
        log_msg(f"DEBUG: issuing zpool scrub command: {shlex.join(cmd)}")
        result = self._run(cmd, check=False, timeout=timeout)
        return result.returncode == 0

    def pause_scrub(self, pool: str, timeout: int | None = None) -> bool:
        """Pause a scrub on *pool*."""
        cmd = self._zpool("scrub", "-p", pool)
        log_msg(f"DEBUG: issuing zpool scrub command: {shlex.join(cmd)}")
        result = self._run(cmd, check=False, timeout=timeout)
        if result.returncode != 0:
            log_msg(f"DEBUG: zpool scrub -p {pool} failed: rc={result.returncode}")
            if result.stderr.strip():
                log_msg(f"DEBUG: stderr: {result.stderr.strip()}")
            if result.stdout.strip():
                log_msg(f"DEBUG: stdout: {result.stdout.strip()}")
        else:
            log_msg(f"VERB: zpool scrub -p {pool} completed")
            if result.stderr.strip():
                log_msg(f"VERB: stderr: {result.stderr.strip()}")
            if result.stdout.strip():
                log_msg(f"VERB: stdout: {result.stdout.strip()}")
        return result.returncode == 0

    def resume_scrub(self, pool: str, timeout: int | None = None) -> bool:
        """Resume a scrub on *pool*."""
        cmd = self._zpool("scrub", pool)
        log_msg(f"DEBUG: issuing zpool scrub command: {shlex.join(cmd)}")
        result = self._run(cmd, check=False, timeout=timeout)
        if result.returncode != 0:
            log_msg(f"DEBUG: zpool scrub {pool} failed: rc={result.returncode}")
            if result.stderr.strip():
                log_msg(f"DEBUG: stderr: {result.stderr.strip()}")
            if result.stdout.strip():
                log_msg(f"DEBUG: stdout: {result.stdout.strip()}")
        else:
            log_msg(f"VERB: zpool scrub {pool} completed")
            if result.stderr.strip():
                log_msg(f"VERB: stderr: {result.stderr.strip()}")
            if result.stdout.strip():
                log_msg(f"VERB: stdout: {result.stdout.strip()}")
        return result.returncode == 0

    def stop_scrub(self, pool: str, timeout: int | None = None) -> bool:
        """Stop a scrub on *pool*."""
        cmd = self._zpool("scrub", "-s", pool)
        log_msg(f"DEBUG: issuing zpool scrub command: {shlex.join(cmd)}")
        result = self._run(cmd, check=False, timeout=timeout)
        return result.returncode == 0

    # ------------------------------------------------------------------
    # Dataset / snapshot reads
    # ------------------------------------------------------------------

    def list_datasets(self, pool: str | None = None, depth: int | None = None) -> list[DatasetRow]:
        """List datasets with the full 8-column field set.

        If *pool* is given, the listing is recursive under that pool/dataset.
        If *depth* is also given, recursion is limited to that depth.
        """
        cmd = self._zfs(
            "list", "-H", "-o", "name,creation,type,used,avail,refer,origin,clones,mounted"
        )
        if pool is not None:
            cmd.extend(["-r"])
            if depth is not None:
                cmd.extend(["-d", str(depth)])
            cmd.append(pool)
        result = self._run(cmd)
        rows = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 9:
                continue
            rows.append(DatasetRow(*parts[:9]))
        return rows

    def list_dataset_info(self, pool: str | None = None) -> list[dict]:
        """Return datasets as dicts with name, used, avail, refer, mountpoint."""
        cmd = self._zfs(
            "list", "-H", "-o", "name,used,avail,refer,mountpoint", "-t", "filesystem,volume"
        )
        if pool is not None:
            cmd.extend(["-r", pool])
        result = self._run(cmd)
        rows = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            rows.append(
                {
                    "name": parts[0],
                    "used": parts[1],
                    "avail": parts[2],
                    "refer": parts[3],
                    "mountpoint": parts[4],
                }
            )
        return rows

    def list_snapshots(
        self,
        dataset: str,
        depth: int | None = None,
        sort_creation: bool = False,
    ) -> list[SnapshotRow]:
        """List snapshots of *dataset* (recursively if depth is None)."""
        cmd = self._zfs(
            "list",
            "-t",
            "snapshot",
            "-H",
            "-o",
            "name,creation,type,used,avail,refer,origin,clones",
        )
        if depth is not None:
            cmd.extend(["-d", str(depth)])
        if sort_creation:
            cmd.extend(["-S", "creation"])
        cmd.append(dataset)
        result = self._run(cmd)
        rows = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 8:
                continue
            rows.append(SnapshotRow(*parts[:8]))
        return rows

    def list_all_snapshot_names(self, pool: str | None = None) -> list[str]:
        """Return full snapshot names, optionally filtered under *pool*."""
        cmd = self._zfs("list", "-t", "snapshot", "-H", "-o", "name")
        if pool is not None:
            cmd.extend(["-r", pool])
        result = self._run(cmd)
        return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]

    def list_holds(self, snapshot: str) -> list[HoldRow]:
        """Return holds for a single snapshot."""
        result = self._run(self._zfs("holds", "-H", snapshot))
        rows = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append(HoldRow(snapshot, parts[1], parts[2]))
        return rows

    def get_property(self, dataset: str, prop: str) -> str:
        """Return the value of a ZFS property."""
        result = self._run(self._zfs("get", "-H", "-o", "value", prop, dataset))
        return result.stdout.strip()

    def get_all_properties(self, dataset: str) -> dict[str, str]:
        """Return all ZFS properties for *dataset* as a property->value dict."""
        result = self._run(self._zfs("get", "-H", "-o", "property,value", "all", dataset))
        props = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                props[parts[0]] = parts[1]
        return props

    def get_properties(self, dataset: str, props: list[str]) -> dict[str, str]:
        """Return a property->value dict for the requested properties on *dataset*.

        Missing properties are included with value ``"-"`` so callers always
        receive a complete mapping. Raises ``subprocess.CalledProcessError`` on
        command failure.
        """
        result = self._run(self._zfs("get", "-H", "-o", "property,value", ",".join(props), dataset))
        values: dict[str, str] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                values[parts[0]] = parts[1]
        for prop in props:
            if prop not in values:
                values[prop] = "-"
        return values

    def get_recursive_snapshot_clones(self, dataset: str) -> list[str]:
        """Return non-empty clones values for all snapshots under *dataset*."""
        result = self._run(self._zfs("list", "-H", "-t", "snapshot", "-o", "clones", "-r", dataset))
        return [
            line.strip()
            for line in result.stdout.strip().split("\n")
            if line.strip() and line.strip() != "-"
        ]

    def list_bookmarks(self, dataset: str, snap_name: str | None = None) -> list[str]:
        """Return bookmark names under *dataset*, optionally filtering by snapshot name."""
        result = self._run(self._zfs("list", "-t", "bookmark", "-H", "-o", "name", "-r", dataset))
        names = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        if snap_name is not None:
            suffix = f"#{snap_name}"
            names = [name for name in names if name.endswith(suffix)]
        return names

    # ------------------------------------------------------------------
    # Dataset / snapshot writes
    # ------------------------------------------------------------------

    def snapshot(self, name: str, recursive: bool = False) -> bool:
        """Create a snapshot."""
        cmd = self._zfs("snapshot")
        if recursive:
            cmd.append("-r")
        cmd.append(name)
        result = self._run(cmd, check=False)
        return result.returncode == 0

    def destroy(self, target: str, recursive: bool = False) -> bool:
        """Destroy a dataset or snapshot."""
        cmd = self._zfs("destroy")
        if recursive:
            cmd.append("-r")
        cmd.append(target)
        result = self._run(cmd, check=False)
        return result.returncode == 0

    def hold(self, tag: str, snapshot: str) -> bool:
        """Place a hold on a snapshot."""
        result = self._run(self._zfs("hold", tag, snapshot), check=False)
        return result.returncode == 0

    def release(self, tag: str, snapshot: str) -> bool:
        """Release a hold on a snapshot."""
        result = self._run(self._zfs("release", tag, snapshot), check=False)
        return result.returncode == 0

    def rollback(self, snapshot: str) -> bool:
        """Rollback a dataset to a snapshot (-r)."""
        result = self._run(self._zfs("rollback", "-r", snapshot), check=False)
        return result.returncode == 0

    def set_property(self, dataset: str, prop: str, value: str) -> bool:
        """Set a ZFS property. Returns True on success, False on failure."""
        result = self._run(self._zfs("set", f"{prop}={value}", dataset), check=False)
        if result.returncode != 0:
            log_msg(f"WARN: Failed to set {prop}={value} on {dataset}: {result.stderr.strip()}")
            return False
        return True

    # ------------------------------------------------------------------
    # Loop device operations (zvol mounting)
    # ------------------------------------------------------------------

    def _cmd(self, *args: str) -> list[str]:
        """Prefix *args* with sudo when the repository was built with sudo=True."""
        return (["sudo"] if self.sudo else []) + list(args)

    def loop_attach(self, zvol_dev: str) -> str:
        """Attach *zvol_dev* to a new read-only loop device with partition scan.

        Returns the /dev/loopN path. Read-only on purpose: these volumes are
        often live VM disks or backup targets. Raises
        subprocess.CalledProcessError on failure.
        """
        result = self._run(
            self._cmd("losetup", "--find", "--show", "--partscan", "--read-only", zvol_dev)
        )
        return _parse_loop_attach_output(result.stdout)

    def loop_find(self, zvol_dev: str) -> str | None:
        """Return the /dev/loopN device attached to *zvol_dev*, or None."""
        result = self._run(self._cmd("losetup", "-j", zvol_dev), check=False)
        if result.returncode != 0:
            return None
        return _parse_loop_find_output(result.stdout)

    def loop_detach(self, loop_dev: str) -> bool:
        """Detach *loop_dev*. Returns True on success."""
        result = self._run(self._cmd("losetup", "-d", loop_dev), check=False)
        return result.returncode == 0

    def loop_partitions(self, loop_dev: str) -> list[LoopPartition]:
        """List partitions (or the bare device) on *loop_dev*.

        Raises subprocess.CalledProcessError if *loop_dev* is not available.
        """
        result = self._run(
            self._cmd("lsblk", "--json", "--output", "NAME,TYPE,FSTYPE,MOUNTPOINT,SIZE", loop_dev)
        )
        return _parse_lsblk_partitions(result.stdout, loop_dev)

    def device_mountpoint(self, device: str) -> str | None:
        """Return the mountpoint *device* is mounted at, or None if unmounted."""
        result = self._run(
            self._cmd("findmnt", "--noheadings", "--output", "TARGET", device), check=False
        )
        if result.returncode != 0:
            return None
        target = result.stdout.strip().splitlines()
        return target[0].strip() if target else None

    # ------------------------------------------------------------------
    # Version / topology reads
    # ------------------------------------------------------------------

    def version_output(self) -> str:
        """Return raw `zfs version` text (empty on failure)."""
        result = self._run(self._zfs("version"), check=False)
        return result.stdout

    def zdb_pool_config(self, pool: str) -> str:
        """Return raw `zdb -C <pool>` text (empty on failure)."""
        cmd = (["sudo"] if self.sudo else []) + ["zdb", "-C", pool]
        result = self._run(cmd, check=False)
        return result.stdout

    def get_ashift(self, pool: str) -> AshiftInfo:
        """Return configured and effective ashift for *pool*.

        The configured value comes from `zpool get ashift`. When that value is
        unset or auto-detected (0, -, default), the effective value is parsed
        from `zdb -C <pool>`.
        """
        configured: str | None = None
        effective: int | None = None

        result = self._run(self._zpool("get", "-H", "-o", "value", "ashift", pool), check=False)
        if result.returncode == 0:
            configured = result.stdout.strip()

        missing = ("0", "-", "default", "")
        if configured and configured not in missing:
            try:
                effective = int(configured)
            except ValueError:
                effective = None
        else:
            raw = self.zdb_pool_config(pool)
            if raw:
                match = _ASHIFT_RE.search(raw)
                if match:
                    effective = int(match.group(1))

        return AshiftInfo(configured, effective)

    def get_device_label_ashift(self, device_path: str) -> int | None:
        """Max ashift recorded in any ZFS label on *device_path*, or None.

        Evidence of how the device was previously used; None when the device
        has no ZFS labels, is unreadable, or records no ashift.
        """
        cmd = (["sudo"] if self.sudo else []) + ["zdb", "-l", device_path]
        result = self._run(cmd, check=False)
        if result.returncode != 0 or not result.stdout:
            return None
        values = [int(m.group(1)) for m in _ASHIFT_RE.finditer(result.stdout)]
        return max(values) if values else None

    def pool_topology(self, pool: str) -> TopologyNode | None:
        """Parse `zpool status -P <pool>` into a typed vdev topology tree."""
        result = self._run(self._zpool("status", "-P", pool), check=False)
        if not result.stdout:
            return None
        return self._parse_topology(result.stdout)

    @staticmethod
    def _classify_vdev(name: str, state: str | None, is_root: bool = False) -> str:
        """Map a `zpool status -P` row name to a vdev type."""
        if is_root:
            return "pool"
        if name.startswith("mirror"):
            return "mirror"
        if name.startswith("raidz1"):
            return "raidz1"
        if name.startswith("raidz2"):
            return "raidz2"
        if name.startswith("raidz3"):
            return "raidz3"
        if name.startswith("stripe"):
            return "stripe"
        # zpool status prints plural section headings; normalise them here.
        if name == "logs":
            return "log"
        if name == "spares":
            return "spare"
        if name in ("special", "log", "cache", "spare"):
            return name
        if state is not None and "/" in name:
            return "disk"
        return "unknown"

    @staticmethod
    def _parse_topology(raw: str) -> TopologyNode | None:
        """Build a TopologyNode tree from the config section of `zpool status`."""
        if "config:" not in raw:
            return None
        section = raw.split("config:", 1)[1]
        if "errors:" in section:
            section = section.split("errors:", 1)[0]

        root = TopologyNode("", "pool", "", 0, 0, 0, None, [])
        stack: list[tuple[int, TopologyNode]] = [(-1, root)]
        header_seen = False

        for line in section.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if not header_seen:
                if stripped.startswith("NAME"):
                    header_seen = True
                continue

            match = _TOPOLOGY_LINE_RE.match(line)
            if not match:
                continue

            indent_s, name, state, read_s, write_s, cksum_s = match.groups()
            indent = len(indent_s)

            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1] if stack else root

            is_root = not root.children
            vdev_type = ZfsRepository._classify_vdev(name, state, is_root=is_root)
            node = TopologyNode(
                name=name,
                vdev_type=vdev_type,
                state=state or "-",
                read=int(read_s) if read_s else 0,
                write=int(write_s) if write_s else 0,
                cksum=int(cksum_s) if cksum_s else 0,
                ashift=None,
                children=[],
            )
            parent.children.append(node)
            stack.append((indent, node))

        if not root.children:
            return None
        # Top-level headings such as `logs`, `cache`, and `spare` appear as
        # siblings of the pool root in `zpool status` output. Attach them to
        # the pool root so the returned tree reflects the pool topology.
        if len(root.children) > 1:
            pool_root = root.children[0]
            pool_root.children.extend(root.children[1:])
            root.children = [pool_root]
        return root.children[0]


class ImportablePoolCache:
    """Async TTL cache for the set of pools available to import.

    `zpool import` can be slow because it scans block devices. This cache
    returns the last known result immediately and refreshes it in a daemon
    thread so callers never block on the scan.
    """

    def __init__(self, repository: ZfsRepository, ttl_seconds: float = 30.0):
        self.repository = repository
        self.ttl = ttl_seconds
        self._names: set[str] = set()
        self._last_update = 0.0
        self._lock = threading.Lock()
        self._refreshing = False

    def get(self, callback: Callable[[], None] | None = None) -> set[str]:
        """Return cached importable pool names, refreshing in background if stale.

        The returned set is a copy so callers can safely iterate while the
        cache is being refreshed.
        """
        with self._lock:
            now = time.monotonic()
            fresh = now - self._last_update < self.ttl
            if fresh and not self._refreshing:
                return set(self._names)
            if not self._refreshing:
                self._refreshing = True
                thread = threading.Thread(target=self._refresh, args=(callback,), daemon=True)
                thread.start()
            return set(self._names)

    def invalidate(self) -> None:
        """Force a fresh scan on the next `get()` call."""
        with self._lock:
            self._last_update = 0.0

    def _refresh(self, callback: Callable[[], None] | None) -> None:
        try:
            names = self.repository.list_importable_pool_names()
        except Exception as exc:  # pragma: no cover - defensive
            log_msg(f"WARN: Error scanning importable pools: {exc}")
            names = set()
        with self._lock:
            self._names = names
            self._last_update = time.monotonic()
            self._refreshing = False
        if callback is not None:
            callback()


_default_repo = None


def get_default_repository(sudo: bool = False) -> ZfsRepository:
    """Return a module-level default repository instance.

    The instance is cached; callers that need a fresh instance should
    construct ZfsRepository directly.
    """
    global _default_repo
    if _default_repo is None or _default_repo.sudo != sudo:
        _default_repo = ZfsRepository(sudo=sudo)
    return _default_repo
