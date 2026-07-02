"""ZFS command repository — isolates zfs/zpool subprocess calls.

All direct zfs/zpool invocations from the GUI layer live here. Methods return
typed dataclasses for reads and booleans for mutating operations. Read methods
raise subprocess.CalledProcessError on failure so callers can decide how to
handle errors; write methods swallow the exception and return success/failure.
"""

import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

from logging_config import log_msg


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
    """One line from `zpool list -H -o name,health,size,alloc,free,cap`."""

    name: str
    health: str
    size: str
    alloc: str
    free: str
    cap: str


@dataclass
class DatasetRow:
    """One line from `zfs list -H -o name,creation,type,used,avail,refer,origin,clones`."""

    name: str
    creation: str
    ds_type: str
    used: str
    avail: str
    refer: str
    origin: str
    clones: str


@dataclass
class SnapshotRow:
    """One line from `zfs list -t snapshot -H -o name,creation,type,used,avail,refer,origin,clones`."""

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


class ZfsRepository:
    """Wrap zfs/zpool subprocess calls for testability and isolation."""

    def __init__(self, sudo: bool = False):
        self.sudo = sudo

    def _zfs(self, *args: str) -> List[str]:
        return (["sudo", "zfs"] if self.sudo else ["zfs"]) + list(args)

    def _zpool(self, *args: str) -> List[str]:
        return (["sudo", "zpool"] if self.sudo else ["zpool"]) + list(args)

    def _run(self, cmd: List[str], check: bool = True, timeout: Optional[int] = None):
        return subprocess.run(
            cmd, capture_output=True, text=True, check=check, timeout=timeout
        )

    # ------------------------------------------------------------------
    # Pool reads
    # ------------------------------------------------------------------

    def list_pools(self) -> List[PoolRow]:
        """Return all pools with health, size, alloc, free, and capacity."""
        result = self._run(
            self._zpool("list", "-H", "-o", "name,health,size,alloc,free,cap")
        )
        rows = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 6:
                continue
            rows.append(PoolRow(*parts[:6]))
        return rows

    def list_pools_full(self) -> List[dict]:
        """Return all pools with the extended 9-column field set."""
        result = self._run(
            self._zpool(
                "list", "-H", "-o",
                "name,size,alloc,free,freeing,ckpoint,frag,cap,health"
            )
        )
        rows = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 9:
                continue
            rows.append({
                "name": parts[0],
                "size": parts[1],
                "alloc": parts[2],
                "free": parts[3],
                "freeing": parts[4],
                "ckpoint": parts[5],
                "frag": parts[6],
                "cap": parts[7],
                "health": parts[8],
            })
        return rows

    def pool_status(self, pool: str, timeout: Optional[int] = None) -> str:
        """Return raw `zpool status` text (empty on failure)."""
        result = self._run(self._zpool("status", pool), check=False, timeout=timeout)
        return result.stdout

    def pool_status_errors(self, pool: str, timeout: Optional[int] = None) -> dict:
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
        result: Dict[str, object] = {
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
                data_errors: List[str] = []
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

    def import_pool(self, pool: str) -> bool:
        """Import one pool by name."""
        result = self._run(self._zpool("import", pool), check=False)
        return result.returncode == 0

    def export_pool(self, pool: str) -> bool:
        """Export one pool by name."""
        result = self._run(self._zpool("export", pool), check=False)
        return result.returncode == 0

    def start_scrub(self, pool: str, timeout: Optional[int] = None) -> bool:
        """Start a scrub on *pool*."""
        cmd = self._zpool("scrub", pool)
        log_msg(f"DEBUG: issuing zpool scrub command: {shlex.join(cmd)}")
        result = self._run(cmd, check=False, timeout=timeout)
        return result.returncode == 0

    def pause_scrub(self, pool: str, timeout: Optional[int] = None) -> bool:
        """Pause a scrub on *pool*."""
        cmd = self._zpool("scrub", "-p", pool)
        log_msg(f"DEBUG: issuing zpool scrub command: {shlex.join(cmd)}")
        result = self._run(cmd, check=False, timeout=timeout)
        return result.returncode == 0

    def resume_scrub(self, pool: str, timeout: Optional[int] = None) -> bool:
        """Resume a scrub on *pool*."""
        cmd = self._zpool("scrub", pool)
        log_msg(f"DEBUG: issuing zpool scrub command: {shlex.join(cmd)}")
        result = self._run(cmd, check=False, timeout=timeout)
        return result.returncode == 0

    def stop_scrub(self, pool: str, timeout: Optional[int] = None) -> bool:
        """Stop a scrub on *pool*."""
        cmd = self._zpool("scrub", "-s", pool)
        log_msg(f"DEBUG: issuing zpool scrub command: {shlex.join(cmd)}")
        result = self._run(cmd, check=False, timeout=timeout)
        return result.returncode == 0

    # ------------------------------------------------------------------
    # Dataset / snapshot reads
    # ------------------------------------------------------------------

    def list_datasets(
        self, pool: Optional[str] = None, depth: Optional[int] = None
    ) -> List[DatasetRow]:
        """List datasets with the full 8-column field set.

        If *pool* is given, the listing is recursive under that pool/dataset.
        If *depth* is also given, recursion is limited to that depth.
        """
        cmd = self._zfs(
            "list", "-H", "-o", "name,creation,type,used,avail,refer,origin,clones"
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
            if len(parts) < 8:
                continue
            rows.append(DatasetRow(*parts[:8]))
        return rows

    def list_dataset_info(
        self, pool: Optional[str] = None
    ) -> List[dict]:
        """Return datasets as dicts with name, used, avail, refer, mountpoint."""
        cmd = self._zfs(
            "list", "-H", "-o", "name,used,avail,refer,mountpoint",
            "-t", "filesystem,volume"
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
            rows.append({
                "name": parts[0],
                "used": parts[1],
                "avail": parts[2],
                "refer": parts[3],
                "mountpoint": parts[4],
            })
        return rows

    def list_snapshots(
        self,
        dataset: str,
        depth: Optional[int] = None,
        sort_creation: bool = False,
    ) -> List[SnapshotRow]:
        """List snapshots of *dataset* (recursively if depth is None)."""
        cmd = self._zfs(
            "list", "-t", "snapshot", "-H",
            "-o", "name,creation,type,used,avail,refer,origin,clones"
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

    def list_all_snapshot_names(
        self, pool: Optional[str] = None
    ) -> List[str]:
        """Return full snapshot names, optionally filtered under *pool*."""
        cmd = self._zfs("list", "-t", "snapshot", "-H", "-o", "name")
        if pool is not None:
            cmd.extend(["-r", pool])
        result = self._run(cmd)
        return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]

    def list_holds(self, snapshot: str) -> List[HoldRow]:
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
        result = self._run(
            self._zfs("get", "-H", "-o", "value", prop, dataset)
        )
        return result.stdout.strip()

    def get_clones(self, target: str) -> str:
        """Return the `clones` property value for a snapshot or dataset."""
        return self.get_property(target, "clones")

    def get_recursive_snapshot_clones(self, dataset: str) -> List[str]:
        """Return non-empty clones values for all snapshots under *dataset*."""
        result = self._run(
            self._zfs("list", "-H", "-t", "snapshot", "-o", "clones", "-r", dataset)
        )
        return [
            line.strip() for line in result.stdout.strip().split("\n")
            if line.strip() and line.strip() != "-"
        ]

    def list_bookmarks(self, dataset: str, snap_name: Optional[str] = None) -> List[str]:
        """Return bookmark names under *dataset*, optionally filtering by snapshot name."""
        result = self._run(
            self._zfs("list", "-t", "bookmark", "-H", "-o", "name", "-r", dataset)
        )
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
