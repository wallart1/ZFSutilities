"""ZFS command repository — isolates zfs/zpool subprocess calls.

All direct zfs/zpool invocations from the GUI layer live here. Methods return
typed dataclasses for reads and booleans for mutating operations. Read methods
raise subprocess.CalledProcessError on failure so callers can decide how to
handle errors; write methods swallow the exception and return success/failure.
"""

import os
import re
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from logging_config import log_msg


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
        raw = self.importable_pools_raw()
        names: set[str] = set()
        current_name: str | None = None
        in_config = False
        is_zvol_backed = False
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("pool:"):
                if current_name and not is_zvol_backed:
                    names.add(current_name)
                current_name = stripped.split(":", 1)[1].strip()
                in_config = False
                is_zvol_backed = False
            elif stripped == "config:":
                in_config = True
            elif in_config and stripped:
                parts = stripped.split()
                if parts and parts[0].startswith("zd"):
                    is_zvol_backed = True
        if current_name and not is_zvol_backed:
            names.add(current_name)
        return names

    def import_pool(self, pool: str) -> bool:
        """Import one pool by name."""
        result = self._run(self._zpool("import", pool), check=False)
        return result.returncode == 0

    def export_pool(self, pool: str) -> bool:
        """Export one pool by name."""
        result = self._run(self._zpool("export", pool), check=False)
        return result.returncode == 0

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
