"""Dashboard / Overview page — at-a-glance system health and recent operations."""

import json
import os
import re
import signal
import subprocess
import threading
import time
from datetime import datetime

import gi
import node_config
import paths

gi.require_version("Gtk", "3.0")
from backup_history import load_history
from config_core import get_dashboard_config, save_dashboard_config
from gi.repository import GLib, Gtk
from gui_helpers import capped_treeview_scroll, configure_treeview_column, set_monospace_font
from log_index import LogIndex
from logging_config import log_msg
from logs_page import select_log_by_path
from path_utils import get_version, resolve_local_bin, resolve_remote_version
from zfs_lock_manager import list_active_locks
from zfs_repository import get_default_repository

# ---------------------------------------------------------------------------
# Regex: ^vm-(\d+)-disk-(\d+)$
# Purpose: Parse an iSCSI backstore name into VM ID and disk number.
# Group 1: VM ID     e.g. "207"
# Group 2: Disk num  e.g. "2"
_ISCSI_BACKSTORE_RE = re.compile(r"^vm-(\d+)-disk-(\d+)$")


# ---------------------------------------------------------------------------
# Regex: ^[\s]*pool:\s+(\S+)
# Purpose: Extract the pool name from the first line of `zpool status` output.
# Group 1: Pool name  e.g. "fivebays"
# Examples:
#   "  pool: fivebays" -> match
#   " state: ONLINE"   -> no match
# Rationale: Every `zpool status` block starts with "pool:" followed by the name.
_ZPOOL_STATUS_POOL_RE = re.compile(r"^[\s]*pool:\s+(\S+)", re.MULTILINE)

# ---------------------------------------------------------------------------
# Regex: scan:\s+scrub\s+repaired\s+\S+\s+in\s+\S+\s+with\s+\d+\s+errors?\s+on\s+(.+)$
# Purpose: Extract the completion date from a finished scrub line in `zpool status`.
# Group 1: The date string  e.g. "Sun May 10 00:24:03 2026"
# Examples:
#   "  scan: scrub repaired 0B in 00:00:02 with 0 errors on Sun May 10 00:24:03 2026"
#       -> match
#   "  scan: scrub in progress since Sun May 10 00:24:03 2026"
#       -> no match (incomplete scrub)
#   "  scan: resilvered 10G in 01:23:45 with 0 errors on Mon Jan  1 12:00:00 2026"
#       -> match (resilver uses same format)
# Rationale: Completed scrubs/resilvers always end with "on <date>".
_SCRUB_DATE_RE = re.compile(
    r"scan:\s+scrub\s+repaired\s+\S+\s+in\s+(.+?)\s+with\s+\d+\s+errors?\s+on\s+(.+)$",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Regex: scan:\s+scrub\s+in\s+progress\s+since\s+(.+)$
# Purpose: Detect an in-progress scrub and extract its start date.
# Group 1: The date string  e.g. "Sun May 10 00:24:03 2026"
# Examples:
#   "  scan: scrub in progress since Sun May 10 00:24:03 2026" -> match
#   "  scan: scrub repaired 0B in 00:00:02 with 0 errors on Sun May 10 00:24:03 2026"
#       -> no match (already completed)
# Rationale: Distinguishes active scrubs from completed ones.
_SCRUB_IN_PROGRESS_RE = re.compile(
    r"scan:\s+scrub\s+in\s+progress\s+since\s+(.+)$",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Regex: scan:\s+scrub\s+canceled\s+on\s+(.+)$
# Purpose: Extract the date/time from a canceled scrub line in `zpool status`.
# Group 1: The date string  e.g. "Fri Jun 12 12:00:13 2026"
# Examples:
#   "  scan: scrub canceled on Fri Jun 12 12:00:13 2026" -> match
# Rationale: A canceled scrub still records the timestamp it was aborted.
_SCRUB_CANCELED_RE = re.compile(
    r"scan:\s+scrub\s+canceled\s+on\s+(.+)$",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Regex: in progress since (.+)$
# Purpose: Extract the start date of an in-progress ZFS-native operation
#          (resilver / RAIDZ expand / vdev removal) from `zpool status`.
# Group 1: The date string  e.g. "Sun May 10 00:24:03 2026"
# Examples:
#   "  scan: resilver (draid) in progress since Sun May 10 00:24:03 2026" -> match
#   "  scan: resilvered 10G in 01:23:45 with 0 errors on Mon Jan 1 ..."  -> no match
# Rationale: The Dashboard shows the start instant of every live task row.
# Reached only for pools where parse_pool_operations found an operation, so
# the similar scrub-in-progress line cannot collide here.
_IN_PROGRESS_SINCE_RE = re.compile(r"in progress since (.+)$", re.MULTILINE)

# Timestamp format `zpool status` scan lines and `ps -o lstart=` share.
_ZFS_TIME_FORMAT = "%a %b %d %H:%M:%S %Y"

# ---------------------------------------------------------------------------
# Regex: ^\s*(\d+)\s*%
# Purpose: Parse a capacity percentage string from `zpool list` output.
# Group 1: The numeric percentage  e.g. "75"
# Examples:
#   "75%" -> match (group 1 = "75")
#   "  80%" -> match (group 1 = "80")
#   "100"  -> no match (missing % sign)
# Rationale: zpool list -o cap returns values like "75%".
_CAP_RE = re.compile(r"^\s*(\d+)\s*%")

# ---------------------------------------------------------------------------
# Regex: ^([^#\s][^:]*):([^:]+):(.+)$
# Purpose: Parse a line from /etc/zfsutilities/iscsi-encrypted-luns.conf.
# Group 1: Backstore name  e.g. "vm-300-disk-1"
# Group 2: Device path    e.g. "/dev/zvol/threeamigos/proxmox/vm-300-disk-1"
# Group 3: Target short   e.g. "threeamigos"
# Examples:
#   "vm-300-disk-1:/dev/zvol/threeamigos/proxmox/vm-300-disk-1:threeamigos" -> match
#   "# this is a comment" -> no match (starts with #)
#   "" -> no match (blank line)
# Rationale: Config format is name:device:target, one per line.
_ENCRYPTED_LUN_RE = re.compile(r"^([^#\s][^:]*):([^:]+):(.+)$")


ZFSLOCK_DIR = paths.get_lock_dir()
ZFSLOCK_LOCKS_DIR = os.path.join(ZFSLOCK_DIR, ".locks")
ZFSLOCK_PIDS_DIR = os.path.join(ZFSLOCK_DIR, ".pids")
PROFILE_LOCK_DIR = os.environ.get("ZFSUTILITIES_PROFILE_LOCK_DIR", paths.get_profile_lock_dir())


def _read_json_lock(lock_path):
    """Read a JSON lock file and return its dict, or None on error."""
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _is_profile_lock_stale(lock_path):
    """Return True if a profile lock file is stale (owner PID is dead)."""
    data = _read_json_lock(lock_path)
    if data is None:
        return True
    pid = data.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


def list_running_profiles():
    """Return running profile dicts from the profile lock directory.

    Each dict contains: name, pid, started, log_file.  Entries from
    ``<profile>.waiting`` files are marked with ``waiting=True`` so the
    Dashboard can distinguish an active run from a blocked duplicate
    invocation.

    Stale locks and stale waiting files are ignored.
    """
    if not os.path.isdir(PROFILE_LOCK_DIR):
        return []

    profiles = []
    for entry in os.listdir(PROFILE_LOCK_DIR):
        path = os.path.join(PROFILE_LOCK_DIR, entry)
        if not os.path.isfile(path):
            continue

        if entry.endswith(".lock"):
            if _is_profile_lock_stale(path):
                continue
            data = _read_json_lock(path) or {}
            name = data.get("profile") or entry[:-5]
            profiles.append(
                {
                    "name": name,
                    "pid": data.get("pid"),
                    "started": data.get("started", "?"),
                    "log_file": data.get("log_file"),
                }
            )
        elif entry.endswith(".waiting"):
            if _is_profile_lock_stale(path):
                continue
            data = _read_json_lock(path) or {}
            name = data.get("profile") or entry[:-8]
            profiles.append(
                {
                    "name": name,
                    "pid": data.get("pid"),
                    "started": data.get("started", "?"),
                    "log_file": data.get("log_file"),
                    "waiting": True,
                }
            )
    return profiles


def _run_cmd(cmd, timeout=5):
    """Run a command, return stdout text or None on failure/timeout."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return None


def _profile_name_from_runner_args(args):
    """Extract the profile name from a profile_runner.py command line.

    Matches both a direct invocation (``python3 .../profile_runner.py run
    <name>``) and a cron ``/bin/sh -c`` wrapper, whose compound command
    (``mkdir -p ... && python3 ... run <name> >> log 2>&1``) keeps the shell
    alive as a parent process. Returns None when no profile name is found.
    """
    parts = args.split()
    for idx, token in enumerate(parts):
        if token.endswith("profile_runner.py"):
            for j in range(idx + 1, len(parts) - 1):
                if parts[j] == "run" and not parts[j + 1].startswith((">", "-")):
                    return parts[j + 1]
            return None
    return None


def _log_file_from_pid_environ(pid):
    """Return ZFSUTILITIES_LOG_FILE from a process's environment, or None."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            data = f.read()
    except (OSError, FileNotFoundError):
        return None
    for item in data.split(b"\0"):
        if item.startswith(b"ZFSUTILITIES_LOG_FILE="):
            return item.split(b"=", 1)[1].decode("utf-8", errors="replace")
    return None


def _scheduled_start_iso(pid):
    """Return a scheduled PID's start time as ISO, or None if unavailable.

    ``ps -o lstart=`` renders the same local-time format as ``zpool status``
    scan lines, so the shared parser applies.
    """
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return _zfs_time_to_iso(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _get_cached_or_fresh(app, attr_name, fresh_value):
    """Return fresh_value if available, otherwise the cached value.

    A fresh_value of None means the fetch failed (e.g. timed out) and the
    cached value should be used if present.

    Returns a tuple (value, stale) where stale is True when the cached value
    is being returned because fresh_value was unavailable.
    """
    if fresh_value is not None:
        setattr(app, attr_name, fresh_value)
        setattr(app, f"{attr_name}_stale", False)
        return fresh_value, False
    cached = getattr(app, attr_name, None)
    if cached is not None:
        return cached, True
    return fresh_value, False


def _parse_cap(cap_str):
    """Parse a zpool capacity string like '75%' into an integer 0-100."""
    m = _CAP_RE.match(str(cap_str))
    if m:
        return int(m.group(1))
    return 0


def _get_pool_health(repo=None):
    """Run zpool list, return list of pool health dicts.

    Each dict contains: name, health, cap, cap_int, scrub_date, status_errors,
    ckpoint.
    Returns None if the command fails or times out.
    """
    repo = repo or get_default_repository()
    pools = []
    try:
        rows = repo.list_pools()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    for row in rows:
        cap_int = _parse_cap(row.cap)
        scrub_date = _get_scrub_date(row.name, repo=repo)
        status_errors = repo.pool_status_errors(row.name)
        pools.append(
            {
                "name": row.name,
                "health": row.health,
                "cap": row.cap,
                "cap_int": cap_int,
                "scrub_date": scrub_date,
                "status_errors": status_errors,
                "ckpoint": row.ckpoint,
            }
        )
    return pools


# SSD/NVMe wear warnings. Wear changes slowly, so the inventory (which probes
# every SSD/NVMe with smartctl) is TTL-cached — the 30 s dashboard refresh
# must not re-run a full smartctl sweep.
DISK_WEAR_WARNING_THRESHOLD = 80
_DISK_WEAR_CACHE_TTL = 300.0
_disk_wear_cache = {"time": 0.0, "inventory": None}
_disk_wear_lock = threading.Lock()


def _format_disk_wear_warnings(disks):
    """Build warning strings for disks at/above the wear threshold.

    Partitions inherit the parent disk's wear, so each physical disk is
    reported once (keyed by parent_path).
    """
    warnings = []
    seen = set()
    for disk in disks:
        wear = disk.wear_percent
        if wear is None or wear < DISK_WEAR_WARNING_THRESHOLD:
            continue
        key = disk.parent_path or disk.path
        if key in seen:
            continue
        seen.add(key)
        model = f" ({disk.model})" if disk.model else ""
        warnings.append(f'SSD "{disk.path}"{model} wear at {wear}%')
    return warnings


def _get_disk_wear_warnings(app):
    """Wear warnings from the disk inventory, TTL-cached.

    Runs in the dashboard's background gather thread; smartctl probes are
    slow, so failures keep the previous cached inventory.
    """
    now = time.monotonic()
    with _disk_wear_lock:
        fresh = (
            _disk_wear_cache["inventory"] is not None
            and now - _disk_wear_cache["time"] < _DISK_WEAR_CACHE_TTL
        )
        if fresh:
            inventory = _disk_wear_cache["inventory"]
        else:
            try:
                inventory = app.ctx.disk_repository.disk_inventory()
            except Exception as exc:
                log_msg(f"WARN: Could not read disk wear data: {exc}")
                inventory = _disk_wear_cache["inventory"]
            if inventory is not None:
                _disk_wear_cache["inventory"] = inventory
                _disk_wear_cache["time"] = now
    if inventory is None:
        return []
    return _format_disk_wear_warnings(inventory.disks)


def _get_scrub_date(pool_name, repo=None):
    """Parse `zpool status` for the last scrub completion date.

    Returns the date string if a completed scrub is found,
    "In progress" if a scrub is running,
    or "Unknown" if the scan line cannot be parsed.
    """
    repo = repo or get_default_repository()
    raw = repo.pool_status(pool_name)
    if not raw:
        return "Unknown"

    m = _SCRUB_DATE_RE.search(raw)
    if m:
        return m.group(2).strip()

    m = _SCRUB_CANCELED_RE.search(raw)
    if m:
        return m.group(1).strip()

    m = _SCRUB_IN_PROGRESS_RE.search(raw)
    if m:
        return "In progress"

    return "Unknown"


def _get_recent_entries(limit=10):
    """Return the most recent `limit` history entries.

    History is stored newest-first, so a simple slice is sufficient.
    Returns a list of entry dicts.
    """
    entries = load_history()
    return entries[:limit]


def _attach_highest_levels(recent):
    """Attach a transient ``highest_level`` key to each recent history entry.

    The level comes from the persistent session-log index (see
    :class:`log_index.LogIndex`), which tracks the highest message level
    parsed from each operation's log file.  Entries whose log file is
    missing or unparsed get ``None`` and fall back to result-based display.
    Entries are fresh parses from ``load_history()`` and are never written
    back, so in-place mutation here is safe.
    """
    try:
        index = LogIndex.load()
    except Exception as exc:
        log_msg(f"WARN: Could not load log index: {exc}")
        index = None
    for entry in recent:
        log_file = entry.get("log_file")
        highest = None
        if index is not None and log_file:
            try:
                highest = index.update(log_file).get("highest_level")
            except Exception as exc:
                log_msg(f"WARN: Could not scan log file {log_file}: {exc}")
        entry["highest_level"] = highest
    if index is not None:
        try:
            index.save()
        except Exception as exc:
            log_msg(f"WARN: Could not save log index: {exc}")


def _local_hostname():
    """Return the short hostname of this machine."""
    return node_config._local_hostname()


def _get_node_config():
    """Parse node configuration and return mode + host identities.

    Wraps :func:`node_config.load_node_config` so the Dashboard uses the same
    logic as the rest of the Python layer.  The returned ``this_host`` is
    always the local short hostname.
    """
    cfg = node_config.load_node_config()
    cfg["this_host"] = _local_hostname()
    return cfg


def _get_host_version(host):
    """Return the zfsutilities version string for the given host."""
    if host == _local_hostname():
        return get_version()
    return resolve_remote_version(host)


def _get_host_zfs_version(host):
    """Return the output of ``zfs version`` for the given host.

    For the local host, runs ``zfs version`` directly.  For remote hosts,
    SSHes as root and runs ``zfs version``.  Returns "unknown" if the
    version cannot be determined.
    """
    local_host = _local_hostname()
    if host == local_host:
        try:
            result = subprocess.run(
                ["zfs", "version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return "unknown"

    try:
        result = subprocess.run(
            ["ssh", f"root@{host}", "zfs version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def _parse_pve_version(output):
    """Parse ``pveversion`` output into a version string.

    Input like ``pve-manager/8.2.4/2a4a85a15c2b3986`` returns ``8.2.4``.
    Returns None if the output is not recognised.
    """
    parts = output.strip().split("/")
    if len(parts) >= 2 and parts[0] == "pve-manager":
        return parts[1]
    return None


def _parse_os_release(content):
    """Parse /etc/os-release content into (name, version) tuple."""
    name = None
    version = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("NAME="):
            name = line[5:].strip('"')
        elif line.startswith("VERSION="):
            version = line[8:].strip('"')
    return name, version


def _parse_inxi_distro(output):
    """Parse ``inxi -S`` output and return the Distro string, or None."""
    for line in output.splitlines():
        if "Distro:" in line:
            return line.split("Distro:", 1)[1].strip()
    return None


def _get_host_os_info(host):
    """Return (os_name, os_version) for the given host.

    Detection order:
      1. Proxmox VE (``pveversion``), because /etc/os-release on Proxmox
         hosts can report the underlying Debian base.
      2. /etc/os-release NAME/VERSION (accurate for Mint, Ubuntu, etc.).
      3. ``inxi -S`` Distro line as a last resort.

    For the local host commands are run directly; for remote hosts they are
    run over ``ssh root@host``.  Returns ("unknown", "unknown") if the OS
    cannot be determined.
    """
    local_host = _local_hostname()
    is_local = host == local_host

    # 1. Proxmox VE specific detection.
    pve_cmd = ["pveversion"] if is_local else ["ssh", f"root@{host}", "pveversion"]
    try:
        result = subprocess.run(
            pve_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            pve_version = _parse_pve_version(result.stdout)
            if pve_version:
                return ("Proxmox VE", pve_version)
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 2. Standard /etc/os-release.
    os_cmd = (
        ["cat", "/etc/os-release"] if is_local else ["ssh", f"root@{host}", "cat /etc/os-release"]
    )
    try:
        result = subprocess.run(
            os_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            name, version = _parse_os_release(result.stdout)
            if name:
                return (name, version or "unknown")
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 3. Fallback to inxi -S (tool used by Linux Mint System Information).
    inxi_cmd = ["inxi", "-S"] if is_local else ["ssh", f"root@{host}", "inxi -S"]
    try:
        result = subprocess.run(
            inxi_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            distro = _parse_inxi_distro(result.stdout)
            if distro:
                # Attempt to split "Distro Name version" into name/version.
                match = re.match(r"^(.*?)\s+(\d[\w\s\.\(\)-]*)$", distro)
                if match:
                    return (match.group(1).strip(), match.group(2).strip())
                return (distro, "unknown")
    except (OSError, subprocess.TimeoutExpired):
        pass

    return ("unknown", "unknown")


def _get_host_role_list(cfg):
    """Return a list of (host, [roles]) tuples for the configured hosts.

    In two-node mode a single host may occupy multiple roles (e.g., this
    host is also the storage host).  This function deduplicates those hosts
    and collects the roles each host occupies.
    """
    host_roles = []
    seen = set()
    for role, host in (
        ("this", cfg["this_host"]),
        ("storage", cfg["storage_host"]),
        ("compute", cfg["compute_host"]),
    ):
        if not host:
            continue
        if host in seen:
            for entry in host_roles:
                if entry[0] == host:
                    entry[1].append(role)
                    break
        else:
            seen.add(host)
            host_roles.append((host, [role]))
    return host_roles


def _is_two_node():
    """Return True if the system is configured for two-node mode."""
    return node_config.is_two_node()


def _get_peer_host():
    """Return the hostname of the other node in a two-node configuration.

    Returns None in single-node mode, when no configuration is present, or
    when the local host cannot be distinguished from the peer.
    """
    return node_config.get_peer_host()


def _log_peer_version_result(local_version, peer_host, peer_version):
    """Log the outcome of a startup peer-node version comparison."""
    if peer_version == "unknown":
        log_msg(f"WARN: Could not determine ZFSutilities version on peer node {peer_host}")
    elif peer_version != local_version:
        log_msg(
            f"WARN: Peer node {peer_host} is running ZFSutilities "
            f"{peer_version}; this node is running {local_version}"
        )
    else:
        log_msg(
            f"INFO: Peer node {peer_host} is running the same ZFSutilities "
            f"version ({local_version})"
        )


def _format_history_timestamp(ts):
    """Convert an ISO timestamp to the project-standard display format.

    Snapshot names embed UTC instants rendered ``YYYY-MM-DDTHH:MMZ`` (legacy
    names embed a local offset); this display formatter stays local-clock for
    the human surface.  History entries store ``datetime.now().isoformat()``
    which is naive, so the parsed value is interpreted as local time before
    formatting.

    Returns the original string unchanged if parsing fails.
    """
    if not ts or ts == "?":
        return "?"
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%dT%H:%M%z")
    except (ValueError, TypeError):
        return str(ts)


def _zfs_time_to_iso(text):
    """Convert a `zpool status` / `ps lstart` timestamp to an ISO string.

    Both render local-clock times like ``Sun May 10 00:24:03 2026``; the
    parsed naive datetime is therefore interpreted as local time.  Returns
    None for empty or unparseable input.
    """
    if not text or not isinstance(text, str):
        return None
    try:
        dt = datetime.strptime(text.strip(), _ZFS_TIME_FORMAT)
    except ValueError:
        return None
    return dt.astimezone().isoformat(timespec="seconds")


def _epoch_to_local_iso(epoch):
    """Convert an epoch timestamp to a local-timezone ISO string, or None."""
    if not isinstance(epoch, (int, float)) or not epoch:
        return None
    try:
        return datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def _iso_to_epoch(iso):
    """Convert an ISO timestamp (naive = local) to epoch seconds, or None."""
    if not iso or not isinstance(iso, str) or iso == "?":
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.timestamp()


_ISCSI_CONF = os.path.join(paths.get_system_config_dir(), "iscsi-encrypted-luns.conf")
_LEGACY_ISCSI_CONF = "/etc/iscsi-encrypted-luns.conf"

# iSCSI LUN-shortfall inventory cache. The scan shells out to targetcli
# twice (backstore list + iscsi tree); the Dashboard refreshes faster than
# that state changes, so results are TTL-cached the way the disk-wear
# inventory is.
_ISCSI_LUNS_CACHE_TTL = 300.0
_iscsi_luns_cache = {"time": 0.0, "value": []}
_iscsi_luns_lock = threading.Lock()


def _get_iscsi_missing_luns():
    """Compare expected backstores against targetcli, TTL-cached.

    Wraps _compute_iscsi_missing_luns() with the disk-wear cache pattern:
    a completed scan (list, possibly empty) is served from cache for
    _ISCSI_LUNS_CACHE_TTL seconds; a failed scan (None) is not cached, so
    the next refresh retries while _get_cached_or_fresh shows the stale
    indicator. Callers that repair the state (the Fix this handler) reset
    _iscsi_luns_cache["time"] to force a fresh scan.
    """
    now = time.monotonic()
    with _iscsi_luns_lock:
        if now - _iscsi_luns_cache["time"] < _ISCSI_LUNS_CACHE_TTL:
            return _iscsi_luns_cache["value"]
    value = _compute_iscsi_missing_luns()
    if value is not None:
        now = time.monotonic()
        with _iscsi_luns_lock:
            _iscsi_luns_cache["value"] = value
            _iscsi_luns_cache["time"] = now
    return value


def _compute_iscsi_missing_luns():
    """Compare expected backstores against targetcli.

    Reads /etc/rtslib-fb-target/expected-backstores.txt (all LUNs) first,
    falling back to /etc/iscsi-encrypted-luns.conf (encrypted LUNs only)
    if the manifest is not present.

    Two shortfall shapes are reported:
    - kind "missing": expected backstore is not loaded in the target;
    - kind "unmapped": backstore is loaded but mapped to no TPG LUN —
      the 2026-10-27 boot-incident shape, where every backstore was
      loaded and only a handful of LUNs were exported.

    Returns a list of {name, target, kind} dicts.
    Returns an empty list if single-node, config missing, or every
    expected backstore is loaded and mapped. Returns None when the live
    targetcli state could not be read.
    """
    if not _is_two_node():
        return []

    manifest_path = "/etc/rtslib-fb-target/expected-backstores.txt"
    fallback_path = _ISCSI_CONF
    if not os.path.exists(fallback_path) and os.path.exists(_LEGACY_ISCSI_CONF):
        fallback_path = _LEGACY_ISCSI_CONF

    expected_names = []
    use_manifest = os.path.exists(manifest_path)

    if use_manifest:
        try:
            with open(manifest_path) as f:
                for line in f:
                    name = line.strip()
                    if name and not name.startswith("#"):
                        expected_names.append(name)
        except OSError:
            return []
    else:
        # Fallback to encrypted-luns.conf for older installations
        try:
            with open(fallback_path) as f:
                for line in f:
                    m = _ENCRYPTED_LUN_RE.match(line.strip())
                    if m:
                        expected_names.append(m.group(1))
        except OSError:
            return []

    if not expected_names:
        return []

    # Get list of backstores that are actually loaded
    backstores_raw = _run_cmd("targetcli /backstores/block ls")
    if backstores_raw is None:
        return None
    loaded = set()
    if backstores_raw:
        for line in backstores_raw.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                loaded.add(parts[1])

    # Backstores the live target actually exports as LUNs: the /iscsi
    # tree renders every mapped LUN as "[block/vm-<name> ...]" — the same
    # line shape parse_target_luns anchors on (lib/iscsi-lib.sh).
    iscsi_raw = _run_cmd("targetcli /iscsi ls")
    if iscsi_raw is None:
        return None
    mapped = set()
    if iscsi_raw:
        for line in iscsi_raw.splitlines():
            if "block/vm-" not in line:
                continue
            name = "vm-" + line.split("block/vm-", 1)[1].split()[0]
            mapped.add(name)

    missing_names = [n for n in expected_names if n not in loaded]
    unmapped_names = [n for n in expected_names if n in loaded and n not in mapped]
    if not missing_names and not unmapped_names:
        return []

    # Try to map affected backstores to targets for display.
    # First check encrypted-luns.conf, then saveconfig.json.
    target_map = {}
    if os.path.exists(fallback_path):
        try:
            with open(fallback_path) as f:
                for line in f:
                    m = _ENCRYPTED_LUN_RE.match(line.strip())
                    if m:
                        target_map[m.group(1)] = m.group(3)
        except OSError:
            pass

    savefile = "/etc/rtslib-fb-target/saveconfig.json"
    affected = set(missing_names) | set(unmapped_names)
    if (not target_map or any(n not in target_map for n in affected)) and os.path.exists(savefile):
        try:
            import json

            with open(savefile) as f:
                config = json.load(f)
            for target in config.get("targets", []):
                iqn = target.get("wwn", "")
                if not iqn:
                    continue
                target_short = iqn.split(":")[-1]
                for tpg in target.get("tpgs", []):
                    for lun in tpg.get("luns", []):
                        so = lun.get("storage_object", "")
                        if so:
                            bs_name = so.split("/")[-1]
                            if bs_name in affected and bs_name not in target_map:
                                target_map[bs_name] = target_short
        except (OSError, ValueError):
            pass

    missing = []
    for name in missing_names:
        missing.append({"name": name, "target": target_map.get(name, "?"), "kind": "missing"})
    for name in unmapped_names:
        missing.append({"name": name, "target": target_map.get(name, "?"), "kind": "unmapped"})
    return missing


_FENCE_SERVICE = "zfsutilities-iscsi-fence.service"
_FENCE_CACHE_TTL = 300.0
_fence_cache = {"time": 0.0, "warning": None}
_fence_lock = threading.Lock()


def _get_fence_failure_warning():
    """Report the compute host's failed iSCSI fence unit, TTL-cached.

    Wraps _compute_fence_failure_warning() with the disk-wear cache
    pattern so the Dashboard refresh cadence cannot turn the peer query
    into an ssh flood.
    """
    now = time.monotonic()
    with _fence_lock:
        if now - _fence_cache["time"] < _FENCE_CACHE_TTL:
            return _fence_cache["warning"]
    warning = _compute_fence_failure_warning()
    now = time.monotonic()
    with _fence_lock:
        _fence_cache["warning"] = warning
        _fence_cache["time"] = now
    return warning


def _compute_fence_failure_warning():
    """Query the peer's fence unit state; return a warning string or None.

    Runs ``systemctl is-failed zfsutilities-iscsi-fence.service`` on the
    compute host — directly when this host is the compute host, otherwise
    over the Dashboard's ssh root@<host> channel. The fence is a
    timer-driven oneshot, so ``inactive`` between ticks is healthy; only
    the exact ``failed`` state warns. An unreachable peer or an unreadable
    state produces no row (no false warning while the peer reboots).
    """
    if not _is_two_node():
        return None
    peer = _get_peer_host()
    if not peer:
        return None
    cmd = (
        ["systemctl", "is-failed", _FENCE_SERVICE]
        if peer == _local_hostname()
        else ["ssh", f"root@{peer}", f"systemctl is-failed {_FENCE_SERVICE}"]
    )
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.stdout.strip() != "failed":
        return None
    return (
        f"iSCSI fence unit failed on {peer} — VM disk path recovery has been "
        f"failing; the fence service journal on {peer} carries the refusals"
    )


# Pool-identity warnings. The scan reads zpool twice (pool list + map
# location) and a state-map file; the Dashboard refreshes faster than pool
# identity changes, so results are TTL-cached the way the fence query is.
_POOL_IDENTITY_CACHE_TTL = 300.0
_pool_identity_cache = {"time": 0.0, "value": []}
_pool_identity_lock = threading.Lock()

_ISCSI_STATE_FILENAME = "iscsi-state.json"


def _get_pool_identity_warnings():
    """Compare configured/imported/map pool identities, TTL-cached.

    Wraps _compute_pool_identity_warnings() with the fence-gatherer cache
    pattern: a completed scan (list, possibly empty) is served from cache
    for _POOL_IDENTITY_CACHE_TTL seconds; a failed scan (None) is not
    cached, so the next refresh retries.
    """
    now = time.monotonic()
    with _pool_identity_lock:
        if now - _pool_identity_cache["time"] < _POOL_IDENTITY_CACHE_TTL:
            return _pool_identity_cache["value"]
    value = _compute_pool_identity_warnings()
    if value is not None:
        now = time.monotonic()
        with _pool_identity_lock:
            _pool_identity_cache["value"] = value
            _pool_identity_cache["time"] = now
    return value


def _read_newest_state_map_pools(expected_pools):
    """Return {name: guid} from the newest iscsi-state.json among *expected_pools*.

    Mirrors newest_iscsi_state_map (lib/iscsi-lib.sh): each pool's
    zfsutilities dataset mountpoint is resolved with `zfs list`, and the
    map with the newest "generated" timestamp wins. Returns {} when no
    readable map exists or it predates the pools key.
    """
    newest_ts = None
    pools = {}
    for pool in sorted(expected_pools):
        mnt = _run_cmd(f"zfs list -H -o mountpoint {pool}/zfsutilities")
        if not mnt or mnt == "-" or not os.path.isdir(mnt):
            continue
        path = os.path.join(mnt, _ISCSI_STATE_FILENAME)
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        ts = data.get("generated")
        if not isinstance(ts, str):
            continue
        if newest_ts is None or ts > newest_ts:
            newest_ts = ts
            recorded = data.get("pools")
            if isinstance(recorded, dict):
                pools = {n: g for n, g in recorded.items() if isinstance(g, str) and g.isdigit()}
            else:
                pools = {}
    return pools


def _compute_pool_identity_warnings(repo=None):
    """Warn when a pool name is not backed by the pool the config expects.

    Three shapes, mirroring lib/iscsi-lib.sh's detect_pool_identity:
    - a configured (node.conf) pool that is not imported;
    - an imported pool that is not configured;
    - an imported pool whose live GUID differs from the GUID recorded in
      the newest pool-resident iSCSI state map (renamed or replaced).

    Returns a list of warning strings, [] in single-node mode or when
    everything is consistent, and None when the live pool list could not
    be read (not cached; the next refresh retries — same transient-failure
    tolerance as the fence gatherer). An unreadable or pre-pools map
    disables only the GUID comparison.
    """
    if not _is_two_node():
        return []

    expected = _get_node_config().get("pools") or set()

    repo = repo or get_default_repository()
    try:
        rows = repo.list_pools()
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        OSError,
        subprocess.TimeoutExpired,
    ):
        return None
    live = {row.name: row.guid for row in rows}

    warnings = []
    for pool in sorted(expected - set(live)):
        warnings.append(
            f"Pool {pool} is configured in node.conf but not imported — "
            "offline, renamed, or replaced"
        )
    for pool in sorted(set(live) - expected):
        warnings.append(
            f"Pool {pool} is imported but not configured in node.conf — "
            "an unexpected pool is serving data here"
        )

    # A GUID column that did not resolve (e.g. "-") is not an identity
    # signal — only a definite numeric mismatch is.
    map_pools = _read_newest_state_map_pools(expected)
    for pool in sorted(set(map_pools) & set(live)):
        if map_pools[pool].isdigit() and live[pool].isdigit() and map_pools[pool] != live[pool]:
            warnings.append(
                f"Pool {pool} GUID changed — map recorded {map_pools[pool]}, "
                f"live {live[pool]} (pool renamed or replaced)"
            )
    return warnings


def _count_stale_locks():
    """Check /run/lock/zfsutilities/.locks/ for stale entries.

    A lock is stale if its owning PID is no longer alive.
    Returns the count of stale locks.
    """
    if not os.path.isdir(ZFSLOCK_LOCKS_DIR):
        return 0

    stale = 0
    for entry in os.listdir(ZFSLOCK_LOCKS_DIR):
        lock_path = os.path.join(ZFSLOCK_LOCKS_DIR, entry)
        if not os.path.isfile(lock_path):
            continue

        pid = _lock_pid(entry)
        if pid is None:
            # Cannot determine PID — conservatively count as stale
            stale += 1
            continue

        try:
            os.kill(pid, 0)
        except OSError:
            stale += 1

    return stale


def _lock_pid(lock_filename):
    """Extract PID from a lock filename or its associated .pids/ file.

    Lock filenames are URL-encoded dataset paths with no PID info.
    The companion .pids/ directory may contain PID files.
    Returns the PID (int) or None if not found.
    """
    # Primary: read PID from the JSON content of the lock file.
    # zfslockmanager writes files like pool%2Fdataset.lock containing:
    #   {"dataset":"pool/dataset","type":"w","pid":12345,...}
    lock_path = os.path.join(ZFSLOCK_LOCKS_DIR, lock_filename)
    if os.path.isfile(lock_path):
        try:
            with open(lock_path) as f:
                data = json.load(f)
            pid = data.get("pid")
            if isinstance(pid, int) and pid > 0:
                return pid
        except (ValueError, OSError, AttributeError):
            pass

    # Fallback: some lock files may embed the PID in the name:
    # "pool%2Fdataset.pid.1234"
    if ".pid." in lock_filename:
        try:
            return int(lock_filename.rsplit(".pid.", 1)[1])
        except (ValueError, IndexError):
            pass

    # Fallback: look for a PID file in .pids/ with the same base name
    pid_file = os.path.join(ZFSLOCK_PIDS_DIR, lock_filename + ".pid")
    if os.path.isfile(pid_file):
        try:
            with open(pid_file) as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            pass

    return None


def _cleanup_stale_locks():
    """Remove stale lock files and return the count removed."""
    if not os.path.isdir(ZFSLOCK_LOCKS_DIR):
        return 0

    removed = 0
    for entry in list(os.listdir(ZFSLOCK_LOCKS_DIR)):
        lock_path = os.path.join(ZFSLOCK_LOCKS_DIR, entry)
        if not os.path.isfile(lock_path):
            continue

        pid = _lock_pid(entry)
        is_stale = False
        if pid is None:
            is_stale = True
        else:
            try:
                os.kill(pid, 0)
            except OSError:
                is_stale = True

        if is_stale:
            try:
                os.unlink(lock_path)
                removed += 1
            except OSError:
                pass
            # Also clean up companion PID file if it exists
            pid_file = os.path.join(ZFSLOCK_PIDS_DIR, entry + ".pid")
            if os.path.isfile(pid_file):
                try:
                    os.unlink(pid_file)
                except OSError:
                    pass

    return removed


def _get_warnings(pools, recent_history, threshold, waiting_tasks=None):
    """Compile warning strings from all sources.

    Args:
        pools: List of pool dicts from _get_pool_health().
        recent_history: Dict from _get_recent_history().
        threshold: Low-space warning threshold (int 0-100).
        waiting_tasks: Optional list of task dicts that are waiting for a
            dataset lock.

    Returns a list of human-readable warning strings.
    """
    warnings = []

    for p in pools:
        health = p.get("health", "")
        if health != "ONLINE":
            warnings.append(f'Pool "{p["name"]}" is {health}')
        cap = p.get("cap_int", 0)
        if cap >= threshold:
            warnings.append(f'Pool "{p["name"]}" capacity at {p["cap"]} (threshold: {threshold}%)')
        status_errors = p.get("status_errors") or {}
        if status_errors.get("has_errors"):
            summary = status_errors.get("errors_summary", "unknown error")
            warnings.append(f'Pool "{p["name"]}" has ZFS errors: {summary}')
        ckpoint = p.get("ckpoint", "")
        if ckpoint and ckpoint != "-":
            warnings.append(f'Pool "{p["name"]}" has an active ZFS checkpoint ({ckpoint})')

    if waiting_tasks:
        for task in waiting_tasks:
            warnings.append(f"'{task['name']}' is waiting for a lock")

    return warnings


def _on_threshold_changed(spin, app):
    """Save the new low-space threshold to config and refresh warnings."""
    value = int(spin.get_value())
    dashboard_cfg = get_dashboard_config(app.config)
    if dashboard_cfg.get("low_space_threshold") != value:
        dashboard_cfg["low_space_threshold"] = value
        save_dashboard_config(app.config, dashboard_cfg)
        refresh_dashboard_page(app)


def _health_icon(health):
    """Return a colored circle character for the given health status."""
    if health == "ONLINE":
        return "<span foreground='#00AA00'>●</span>"
    if health in ("DEGRADED", "FAULTED", "OFFLINE", "UNAVAIL", "REMOVED"):
        return "<span foreground='#CC0000'>●</span>"
    return "<span foreground='#FF8C00'>●</span>"


def _outcome_markup(entry):
    """Return the Pango markup for a Recent Operations message-level cell.

    Shows the highest message level issued during the operation (from the
    session-log index) rather than treating WARN messages as failures:
    FATAL renders red, WARN amber, and INFO/VERB/DEBUG green.  When no
    level information is available (no log file, missing log, or no
    level-prefixed lines), fall back to the exit-code-based result.
    """
    highest = entry.get("highest_level")
    if highest == "FATAL":
        return "<span foreground='#CC0000'>✗</span> FATAL"
    if highest == "WARN":
        return "<span foreground='#FF8C00'>⚠</span> WARN"
    if highest in ("INFO", "VERB", "DEBUG"):
        return f"<span foreground='#00AA00'>✓</span> {highest}"
    result = entry.get("result", "unknown")
    if result == "success":
        return "<span foreground='#00AA00'>✓</span> success"
    if result == "cancelled":
        return "<span foreground='#FF8C00'>⏸</span> cancelled"
    return f"<span foreground='#CC0000'>✗</span> {result}"


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------


def create_dashboard_page(app):
    """Build and return the full Dashboard tab widget."""
    app._dashboard_timer = None

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_min_content_width(400)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
    box.set_margin_start(15)
    box.set_margin_end(15)
    box.set_margin_top(15)
    box.set_margin_bottom(15)
    scrolled.add(box)
    # The page viewport must size its content by NATURAL height: the
    # section tables sit in their own capped scrolled windows whose
    # minimum heights are tiny, and the default MINIMUM policy would
    # clamp the page box to the window height and crush every table
    # window toward that minimum (memory-page idiom).
    viewport = scrolled.get_child()
    if hasattr(viewport, "set_vscroll_policy"):
        viewport.set_vscroll_policy(Gtk.ScrollablePolicy.NATURAL)

    # Title
    title = Gtk.Label()
    title.set_markup("<big><b>Dashboard</b></big>")
    title.set_halign(Gtk.Align.START)
    box.pack_start(title, False, False, 0)

    # Refresh interval control and "Refreshing" indicator
    refresh_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    refresh_box.set_halign(Gtk.Align.START)
    refresh_box.pack_start(Gtk.Label(label="Refresh every (s):"), False, False, 0)

    dashboard_cfg = get_dashboard_config(app.config)
    app.dashboard_refresh_spin = Gtk.SpinButton()
    app.dashboard_refresh_spin.set_range(1, 300)
    app.dashboard_refresh_spin.set_increments(1, 10)
    app.dashboard_refresh_spin.set_value(dashboard_cfg.get("refresh_seconds", 30))
    app.dashboard_refresh_spin.connect("value-changed", _on_refresh_interval_changed, app)
    refresh_box.pack_start(app.dashboard_refresh_spin, False, False, 0)

    app.dashboard_refreshing_label = Gtk.Label(label="Refreshing")
    app.dashboard_refreshing_label.set_no_show_all(True)
    app.dashboard_refreshing_label.hide()
    refresh_box.pack_start(app.dashboard_refreshing_label, False, False, 0)

    box.pack_start(refresh_box, False, False, 0)

    # Low-space warning threshold (packed inside Pool Health)
    threshold_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    threshold_box.set_halign(Gtk.Align.START)
    threshold_label = Gtk.Label(label="Low-space warning threshold:")
    threshold_box.pack_start(threshold_label, False, False, 0)

    dashboard_cfg = get_dashboard_config(app.config)
    app.dashboard_threshold_spin = Gtk.SpinButton()
    app.dashboard_threshold_spin.set_range(50, 95)
    app.dashboard_threshold_spin.set_increments(5, 5)
    app.dashboard_threshold_spin.set_value(dashboard_cfg.get("low_space_threshold", 80))
    app.dashboard_threshold_spin.connect("value-changed", _on_threshold_changed, app)
    threshold_box.pack_start(app.dashboard_threshold_spin, False, False, 0)

    threshold_pct = Gtk.Label(label="%")
    threshold_box.pack_start(threshold_pct, False, False, 0)

    # --- Section 1: Warnings ---
    app.dashboard_warn_frame = _make_section_frame("Warnings")
    app.dashboard_warn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    app.dashboard_warn_box.set_margin_start(10)
    app.dashboard_warn_box.set_margin_end(10)
    app.dashboard_warn_box.set_margin_top(10)
    app.dashboard_warn_box.set_margin_bottom(10)
    app.dashboard_warn_frame.add(app.dashboard_warn_box)
    box.pack_start(app.dashboard_warn_frame, False, False, 0)

    # --- Section 2: Pool Health ---
    app.dashboard_pool_frame = _make_section_frame("Pool Health")
    pool_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    pool_box.set_margin_start(10)
    pool_box.set_margin_end(10)
    pool_box.set_margin_top(10)
    pool_box.set_margin_bottom(10)
    pool_box.pack_start(threshold_box, False, False, 0)
    app.dashboard_pool_grid = Gtk.Grid()
    app.dashboard_pool_grid.set_column_spacing(15)
    app.dashboard_pool_grid.set_row_spacing(5)

    pool_grid_sw = Gtk.ScrolledWindow()
    pool_grid_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
    pool_grid_sw.set_min_content_width(300)
    pool_grid_sw.set_propagate_natural_height(True)
    pool_grid_sw.add(app.dashboard_pool_grid)
    pool_box.pack_start(pool_grid_sw, False, False, 0)
    app.dashboard_pool_frame.add(pool_box)
    box.pack_start(app.dashboard_pool_frame, False, False, 0)

    # --- Section 3: Tasks (waiting / running / completed) ---
    app.dashboard_tasks_frame = _make_section_frame("Tasks")
    # Columns: datetime, type, name, status (markup), then hidden:
    # state, task_key, log_file, completed-key (dismissal identity)
    app.dashboard_tasks_store = Gtk.ListStore(str, str, str, str, str, str, str, str)
    app.dashboard_tasks_view = Gtk.TreeView(model=app.dashboard_tasks_store)
    app.dashboard_tasks_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.dashboard_tasks_view.set_headers_visible(True)
    app.dashboard_tasks_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    for col_idx, title_text, width in [
        (0, "Date / Time", 150),
        (1, "Type", 100),
        (2, "Name", 140),
        (3, "Status", 220),
    ]:
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
        if col_idx == 0:
            set_monospace_font(r)
        # Status column contains Pango markup (colored icons)
        attr = "markup" if col_idx == 3 else "text"
        col = Gtk.TreeViewColumn(title_text, r, **{attr: col_idx})
        configure_treeview_column(col, width=width)
        app.dashboard_tasks_view.append_column(col)
    app._ui_state.bind_treeview(app.dashboard_tasks_view, "dashboard_tasks_view")

    app.enable_treeview_copy(app.dashboard_tasks_view)

    # Keep the old sections' ten-row footprint: the window shows ten rows
    # whatever the list length, and taller lists scroll inside it.
    tasks_scrolled = capped_treeview_scroll(
        app.dashboard_tasks_view, row_target=10, fixed_rows=True
    )

    tasks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    tasks_box.set_margin_start(10)
    tasks_box.set_margin_end(10)
    tasks_box.set_margin_top(10)
    tasks_box.set_margin_bottom(10)
    tasks_box.pack_start(tasks_scrolled, True, True, 0)
    app.dashboard_tasks_frame.add(tasks_box)
    box.pack_start(app.dashboard_tasks_frame, False, False, 0)

    # --- Section 4a: Active Locks ---
    app.dashboard_locks_frame = _make_section_frame("Active Locks")
    app.dashboard_locks_store = Gtk.ListStore(str, str, str, str, str, str, str)
    app.dashboard_locks_view = Gtk.TreeView(model=app.dashboard_locks_store)
    app.dashboard_locks_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.dashboard_locks_view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

    for col_idx, title_text, width in [
        (0, "Dataset", 180),
        (1, "Type", 60),
        (2, "PID", 70),
        (3, "Script", 120),
        (4, "Host", 100),
        (5, "Acquired", 150),
        (6, "Description", 200),
    ]:
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
        if col_idx == 4:
            set_monospace_font(r)
        col = Gtk.TreeViewColumn(title_text, r, text=col_idx)
        configure_treeview_column(col, width=width)
        app.dashboard_locks_view.append_column(col)
    app._ui_state.bind_treeview(app.dashboard_locks_view, "dashboard_locks_view")

    app.enable_treeview_copy(app.dashboard_locks_view)

    locks_scrolled = capped_treeview_scroll(app.dashboard_locks_view, fixed_rows=False)

    locks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    locks_box.set_margin_start(10)
    locks_box.set_margin_end(10)
    locks_box.set_margin_top(10)
    locks_box.set_margin_bottom(10)
    locks_box.pack_start(locks_scrolled, True, True, 0)
    app.dashboard_locks_frame.add(locks_box)
    box.pack_start(app.dashboard_locks_frame, False, False, 0)

    # --- Section 5: iSCSI Issues ---
    app.dashboard_iscsi_frame = _make_section_frame("iSCSI Issues")
    app.dashboard_iscsi_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    app.dashboard_iscsi_box.set_margin_start(10)
    app.dashboard_iscsi_box.set_margin_end(10)
    app.dashboard_iscsi_box.set_margin_top(10)
    app.dashboard_iscsi_box.set_margin_bottom(10)
    app.dashboard_iscsi_frame.add(app.dashboard_iscsi_box)
    box.pack_start(app.dashboard_iscsi_frame, False, False, 0)
    # Hide iSCSI section on single-node systems
    if not _is_two_node():
        app.dashboard_iscsi_frame.hide()

    # --- Section 6: Configuration Info ---
    app.dashboard_config_frame = _make_section_frame("Configuration")
    app.dashboard_config_grid = Gtk.Grid()
    app.dashboard_config_grid.set_column_spacing(15)
    app.dashboard_config_grid.set_row_spacing(5)
    app.dashboard_config_grid.set_margin_start(10)
    app.dashboard_config_grid.set_margin_end(10)
    app.dashboard_config_grid.set_margin_top(10)
    app.dashboard_config_grid.set_margin_bottom(10)

    config_scrolled = Gtk.ScrolledWindow()
    config_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
    config_scrolled.set_min_content_width(300)
    config_scrolled.set_propagate_natural_height(True)
    config_scrolled.add(app.dashboard_config_grid)
    app.dashboard_config_frame.add(config_scrolled)
    box.pack_start(app.dashboard_config_frame, False, False, 0)

    # The initial population is triggered from main.py after the window is
    # shown so that the GTK main loop is running and the async refresh can
    # update widgets without blocking startup.

    return scrolled


def _make_section_frame(title_text):
    """Create a framed container with a bold title label."""
    frame = Gtk.Frame()
    label = Gtk.Label()
    label.set_markup(f"<b>{title_text}</b>")
    label.set_halign(Gtk.Align.START)
    label.set_margin_start(5)
    label.set_margin_top(5)
    frame.set_label_widget(label)
    return frame


def _make_config_label(text):
    """Create a bold label aligned to the top-left of its cell.

    Labels in the Dashboard Configuration grid sit next to multi-line values;
    valign=START keeps them even with the first line of the value.
    """
    lbl = Gtk.Label()
    lbl.set_markup(f"<b>{text}:</b>")
    lbl.set_halign(Gtk.Align.START)
    lbl.set_valign(Gtk.Align.START)
    return lbl


def _gather_dashboard_data(app):
    """Collect all dashboard data. Intended to run in a background thread.

    Returns a dict with everything needed by `_update_dashboard_ui`, or None
    when a critical failure prevents rendering.  No GTK calls are made here.
    """
    dashboard_cfg = get_dashboard_config(app.config)
    threshold = dashboard_cfg.get("low_space_threshold", 80)

    pools, pools_stale = _get_cached_or_fresh(app, "_dashboard_pools", _get_pool_health())
    recent = _get_recent_entries(10)
    _attach_highest_levels(recent)
    missing_luns, iscsi_stale = _get_cached_or_fresh(
        app, "_dashboard_iscsi", _get_iscsi_missing_luns()
    )
    stale_count = _count_stale_locks()

    # Scrub status for dashboard
    from scrub_manager import get_all_pool_scrub_states

    scrub_states = get_all_pool_scrub_states()

    tasks = _collect_running_tasks(app)
    waiting_tasks = [t for t in tasks if t.get("waiting_for_lock")]
    active_locks = list_active_locks()

    # Mounts the kernel lists as mounted whose path is unreachable —
    # shadowed or orphaned; the Dashboard offers the repair.
    from zfs_repository import find_unreachable_mounts

    unreachable_mounts = find_unreachable_mounts()

    # Build warnings: live checks + startup-style checks
    warnings = _get_warnings(pools, recent, threshold, waiting_tasks)
    for row in unreachable_mounts:
        warnings.append(
            f"{row['name']} is mounted at {row['mountpoint']} but the path is "
            "unreachable (bad mount order) — use Repair Mount Order"
        )
    # Persistent fence failure on the compute host (crash-loop / reconcile
    # refusals the fence could not recover from).
    fence_warning = _get_fence_failure_warning()
    if fence_warning:
        warnings.append(fence_warning)
    # Pool identity (renamed/replaced pool under a known name) — mirrors
    # lib/iscsi-lib.sh's detect_pool_identity for the Dashboard.
    pool_identity_warnings = _get_pool_identity_warnings()
    if pool_identity_warnings:
        warnings.extend(pool_identity_warnings)
    if not app.config.get("backup", {}).get("pull_steps") and not app.config.get("backup", {}).get(
        "send_receive_steps"
    ):
        warnings.append("No backup steps configured — configure in the Backup tab")
    if not app.config.get("offsite", {}).get("steps"):
        warnings.append("No offsite steps configured — configure in the Offsite tab")
    from feature_config import get_checkagainst, get_pools

    if not get_pools(app.config):
        warnings.append("No pools registered — add pools in the Pools tab")
    if not get_checkagainst(app.config):
        warnings.append("Checkagainst table is empty — configure in the Checkagainst tab")
    if stale_count > 0:
        warnings.append(f"Stale lock files: {stale_count}")
    warnings.extend(_get_disk_wear_warnings(app))

    config_data = _gather_config_section_data(app)

    return {
        "threshold": threshold,
        "pools": pools,
        "pools_stale": pools_stale,
        "recent": recent,
        "missing_luns": missing_luns,
        "iscsi_stale": iscsi_stale,
        "stale_count": stale_count,
        "scrub_states": scrub_states,
        "tasks": tasks,
        "warnings": warnings,
        "config_data": config_data,
        "active_locks": active_locks,
        "unreachable_mounts": unreachable_mounts,
    }


def _show_dashboard_refreshing(app):
    """Show the 'Refreshing' indicator next to the refresh interval spinner."""
    if hasattr(app, "dashboard_refreshing_label"):
        app.dashboard_refreshing_label.show()


def _hide_dashboard_refreshing(app):
    """Hide the 'Refreshing' indicator after refresh completes."""
    if hasattr(app, "dashboard_refreshing_label"):
        app.dashboard_refreshing_label.hide()


def _on_refresh_interval_changed(spin, app):
    """Persist the new dashboard refresh interval and restart the timer."""
    value = int(spin.get_value())
    dashboard_cfg = get_dashboard_config(app.config)
    if dashboard_cfg.get("refresh_seconds") != value:
        dashboard_cfg["refresh_seconds"] = value
        save_dashboard_config(app.config, dashboard_cfg)
        # Restart the timer so the new interval takes effect immediately
        # while the Dashboard tab is active.
        if hasattr(app, "_start_stop_dashboard_timer"):
            app._start_stop_dashboard_timer("dashboard")


def _update_dashboard_ui(app, data):
    """Update every dashboard section from pre-gathered data.

    Must run on the GTK main thread.
    """
    _refresh_config_section_from_data(app, data["config_data"])
    _refresh_pool_section(app, data["pools"], data["scrub_states"], stale=data["pools_stale"])
    _refresh_tasks_section(app, tasks=data["tasks"], recent=data["recent"])
    _refresh_iscsi_section(app, data["missing_luns"], stale=data["iscsi_stale"])
    _refresh_warnings_section(app, data["warnings"])
    _refresh_active_locks_section(app, data["active_locks"])

    # Update the contextual "Fix Locks" and "Repair Mount Order" buttons
    _update_fix_locks_button(app, data["stale_count"])
    _update_repair_mount_order_button(app, data["unreachable_mounts"])

    app.dashboard_config_frame.show_all()
    app.dashboard_pool_frame.show_all()
    app.dashboard_tasks_frame.show_all()
    app.dashboard_warn_frame.show_all()
    app.dashboard_locks_frame.show_all()

    # iSCSI frame visibility depends on mode
    if _is_two_node():
        app.dashboard_iscsi_frame.show_all()
    else:
        app.dashboard_iscsi_frame.hide()


def _dashboard_refresh_worker(app):
    """Background thread target: gather dashboard data."""
    try:
        data = _gather_dashboard_data(app)
    except Exception as exc:
        log_msg(f"WARN: Dashboard data gathering failed: {exc}")
        data = None
    GLib.idle_add(_on_dashboard_refresh_done, app, data)


def _on_dashboard_refresh_done(app, data):
    """GLib idle callback: apply gathered data and handle pending refresh."""
    app._dashboard_refresh_in_progress = False
    if data is not None:
        _update_dashboard_ui(app, data)

    if getattr(app, "_dashboard_refresh_pending", False):
        app._dashboard_refresh_pending = False
        GLib.timeout_add_seconds(0, lambda: refresh_dashboard_page(app) or False)
    else:
        _hide_dashboard_refreshing(app)
    return False


def refresh_dashboard_page(app, sync=False):
    """Re-gather all dashboard data and update every section.

    By default the expensive I/O is performed in a background thread so the
    GTK main thread stays responsive.  Pass ``sync=True`` to refresh
    synchronously (used by tests and callers that must wait for the result).
    """
    if not sync:
        if getattr(app, "_dashboard_refresh_in_progress", False):
            app._dashboard_refresh_pending = True
            return
        app._dashboard_refresh_in_progress = True
        app._dashboard_refresh_pending = False
        _show_dashboard_refreshing(app)
        threading.Thread(target=_dashboard_refresh_worker, args=(app,), daemon=True).start()
        return

    # Synchronous path
    data = _gather_dashboard_data(app)
    if data is not None:
        _update_dashboard_ui(app, data)


def _gather_config_section_data(app):
    """Collect data for the Configuration Info grid.

    This performs the expensive SSH/subprocess calls and is intended to run
    in a background thread.  It returns a dict that
    `_refresh_config_section_from_data` can render without further I/O.
    """
    cfg = _get_node_config()
    data = {
        "cfg": cfg,
        "mode": cfg["mode"],
        "hosts": [],
        "os_info_map": {},
        "versions": "",
        "zfs_versions": "",
    }

    if cfg["mode"] == "two-node":
        data["hosts"] = [
            ("This host", cfg["this_host"]),
            ("Storage host", cfg["storage_host"]),
            ("Compute host", cfg["compute_host"]),
        ]
        if cfg.get("storage_ip"):
            data["hosts"].append(("Storage IP", cfg["storage_ip"]))
    else:
        data["hosts"] = [("Hostname", cfg["this_host"])]

    # Gather OS info once per host to avoid duplicate SSH calls.
    if cfg["mode"] == "two-node":
        data["os_info_map"] = {
            host: _get_host_os_info(host) for host, _roles in _get_host_role_list(cfg)
        }
    else:
        data["os_info_map"] = {cfg["this_host"]: _get_host_os_info(cfg["this_host"])}

    # Versions
    if cfg["mode"] == "two-node":
        local_v = _get_host_version(cfg["this_host"])
        storage_v = _get_host_version(cfg["storage_host"])
        compute_v = _get_host_version(cfg["compute_host"])
        data["versions"] = f"local={local_v}  storage={storage_v}  compute={compute_v}"
    else:
        data["versions"] = _get_host_version(cfg["this_host"])

    # ZFS versions
    if cfg["mode"] == "two-node":
        zfs_parts = []
        for host, roles in _get_host_role_list(cfg):
            zfs_out = _get_host_zfs_version(host)
            header = f"{host} ({','.join(roles)}):"
            zfs_parts.append(f"{header}\n{zfs_out}")
        data["zfs_versions"] = "\n\n".join(zfs_parts)
    else:
        data["zfs_versions"] = _get_host_zfs_version(cfg["this_host"])

    return data


def _refresh_config_section_from_data(app, data):
    """Render the Configuration Info grid from pre-gathered data."""
    for child in app.dashboard_config_grid.get_children():
        child.destroy()

    cfg = data["cfg"]
    row = 0

    # Mode
    mode_lbl = _make_config_label("Mode")
    app.dashboard_config_grid.attach(mode_lbl, 0, row, 1, 1)

    mode_val = Gtk.Label(label=data["mode"])
    mode_val.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(mode_val, 1, row, 1, 1)
    row += 1

    # Hostnames
    for label, hostname in data["hosts"]:
        lbl = _make_config_label(label)
        app.dashboard_config_grid.attach(lbl, 0, row, 1, 1)

        val = Gtk.Label(label=hostname)
        val.set_halign(Gtk.Align.START)
        app.dashboard_config_grid.attach(val, 1, row, 1, 1)
        row += 1

    # Versions
    ver_lbl = _make_config_label("Version(s)")
    app.dashboard_config_grid.attach(ver_lbl, 0, row, 1, 1)

    ver_val = Gtk.Label(label=data["versions"])
    ver_val.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(ver_val, 1, row, 1, 1)
    row += 1

    # Operating system(s)
    os_lbl = _make_config_label("Operating system(s)")
    app.dashboard_config_grid.attach(os_lbl, 0, row, 1, 1)

    os_info_map = data["os_info_map"]
    if cfg["mode"] == "two-node":
        os_name_parts = []
        for host, roles in _get_host_role_list(cfg):
            os_name, os_version = os_info_map[host]
            header = f"{host} ({','.join(roles)}):"
            os_name_parts.append(f"{header}\n{os_name} {os_version}")
        os_name_text = "\n\n".join(os_name_parts)
    else:
        os_name, os_version = os_info_map[cfg["this_host"]]
        os_name_text = f"{os_name} {os_version}"

    os_name_val = Gtk.Label(label=os_name_text)
    os_name_val.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(os_name_val, 1, row, 1, 1)
    row += 1

    # ZFS versions
    zfs_lbl = _make_config_label("ZFS version(s)")
    app.dashboard_config_grid.attach(zfs_lbl, 0, row, 1, 1)

    zfs_val = Gtk.Label(label=data["zfs_versions"])
    zfs_val.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(zfs_val, 1, row, 1, 1)


def _refresh_config_section(app):
    """Clear and repopulate the Configuration Info grid (synchronous)."""
    _refresh_config_section_from_data(app, _gather_config_section_data(app))


def _refresh_pool_section(app, pools, scrub_states=None, stale=False):
    """Clear and repopulate the Pool Health grid."""
    for child in app.dashboard_pool_grid.get_children():
        child.destroy()

    row = 0
    if stale:
        stale_lbl = Gtk.Label()
        stale_lbl.set_markup("<i>Pool data may be stale while pools are busy.</i>")
        stale_lbl.set_halign(Gtk.Align.START)
        app.dashboard_pool_grid.attach(stale_lbl, 0, row, 4, 1)
        row += 1

    if not pools:
        lbl = Gtk.Label(label="No pools found.")
        lbl.set_halign(Gtk.Align.START)
        app.dashboard_pool_grid.attach(lbl, 0, row, 1, 1)
        return

    # Scrub summary line
    header_row = row
    if scrub_states:
        from scrub_manager import ScrubState

        scanning = sum(1 for s in scrub_states.values() if s.state == ScrubState.SCANNING)
        paused = sum(1 for s in scrub_states.values() if s.state == ScrubState.PAUSED)
        if scanning or paused:
            summary = Gtk.Label()
            parts = []
            if scanning:
                parts.append(f"{scanning} scrubbing")
            if paused:
                parts.append(f"{paused} paused")
            summary.set_markup(f"<i>{', '.join(parts)}</i>")
            summary.set_halign(Gtk.Align.START)
            app.dashboard_pool_grid.attach(summary, 0, header_row, 3, 1)
            header_row += 1

    # Header row
    headers = [("Pool", 0), ("Capacity", 1), ("Last Scrub", 2), ("Scrub", 3)]
    for text, col in headers:
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{text}</b>")
        lbl.set_halign(Gtk.Align.START)
        app.dashboard_pool_grid.attach(lbl, col, header_row, 1, 1)

    for row_idx, p in enumerate(pools, start=header_row + 1):
        icon = Gtk.Label()
        icon.set_markup(f"{_health_icon(p['health'])} {p['name']}")
        icon.set_halign(Gtk.Align.START)
        app.dashboard_pool_grid.attach(icon, 0, row_idx, 1, 1)

        bar = Gtk.ProgressBar()
        bar.set_fraction(min(p["cap_int"] / 100.0, 1.0))
        bar.set_text(f"{p['cap']}")
        bar.set_show_text(True)
        if p["cap_int"] >= 80:
            bar.get_style_context().add_class("progress-bar-red")
        app.dashboard_pool_grid.attach(bar, 1, row_idx, 1, 1)

        scrub = Gtk.Label(label=p.get("scrub_date", "Unknown"))
        scrub.set_halign(Gtk.Align.START)
        scrub.get_style_context().add_class("monospace")
        app.dashboard_pool_grid.attach(scrub, 2, row_idx, 1, 1)

        # Scrub status
        if scrub_states and p["name"] in scrub_states:
            s = scrub_states[p["name"]]
            if s.state.value == "scanning" and s.progress_percent is not None:
                sbar = Gtk.ProgressBar()
                sbar.set_fraction(min(s.progress_percent / 100.0, 1.0))
                sbar.set_text(f"{s.progress_percent:.1f}%")
                sbar.set_show_text(True)
                app.dashboard_pool_grid.attach(sbar, 3, row_idx, 1, 1)
            else:
                stext = s.state.value
                if stext == "scanning":
                    stext = "scrubbing"
                if stext == "none":
                    stext = "—"
                slbl = Gtk.Label(label=stext)
                slbl.set_halign(Gtk.Align.START)
                app.dashboard_pool_grid.attach(slbl, 3, row_idx, 1, 1)
        else:
            slbl = Gtk.Label(label="—")
            slbl.set_halign(Gtk.Align.START)
            app.dashboard_pool_grid.attach(slbl, 3, row_idx, 1, 1)


# Statuses that carry no information beyond the row's start time.
_GENERIC_RUNNING_STATUSES = ("Running", "In progress")


def _running_progress_text(task):
    """Return the parenthetical progress for a running task row ('' if none).

    Derived from the collector's display status: the generic "Running" /
    "In progress" strings and PID identifiers add nothing the row does not
    already show (the running format deliberately omits PIDs), while step
    counters, scrub/ZFS percentages, and surface-test cells do.
    """
    status = task.get("status", "")
    if not status or status in _GENERIC_RUNNING_STATUSES:
        return ""
    if status.startswith(("PID ", "Waiting")):
        return ""
    return status


def _live_task_row(task):
    """Convert a collector task dict into a merged Tasks row dict."""
    started = task.get("started")
    if task.get("waiting_for_lock"):
        state = "waiting"
        since = task.get("wait_started") or started
        if since:
            status = f"Waiting since {_format_history_timestamp(since)}"
        else:
            status = "Waiting"
    else:
        state = "running"
        if started:
            status = f"Running since {_format_history_timestamp(started)}"
        else:
            status = "Running"
        progress = _running_progress_text(task)
        if progress:
            status = f"{status} ({progress})"
    return {
        "dt_display": _format_history_timestamp(started) if started else "?",
        "type": task.get("type", "?"),
        "name": task.get("name", "?"),
        "status": status,
        "state": state,
        "task_key": task.get("task_key", ""),
        "log_file": task.get("log_file") or "",
        "completed_key": "",
        "sort_ts": _iso_to_epoch(started),
    }


def _completed_task_row(entry):
    """Convert a history entry into a merged Tasks row dict."""
    ts = entry.get("timestamp", "?")
    return {
        "dt_display": _format_history_timestamp(ts),
        "type": entry.get("type", "?"),
        "name": entry.get("name", "?"),
        "status": _outcome_markup(entry),
        "state": "completed",
        "task_key": "",
        "log_file": entry.get("log_file", ""),
        "completed_key": _completed_task_key(entry),
        "sort_ts": _iso_to_epoch(ts),
    }


def _completed_task_key(entry):
    """Return the stable key that identifies a completed history entry.

    The session-log path is unique per run; entries without one (older
    runs) fall back to their timestamp and name.
    """
    return entry.get("log_file") or f"{entry.get('timestamp', '')}|{entry.get('name', '')}"


def _dismissed_task_keys(app):
    """Return the dismissed completed-task keys from the dashboard config."""
    keys = get_dashboard_config(app.config).get("dismissed_tasks", [])
    if isinstance(keys, list):
        return {k for k in keys if isinstance(k, str)}
    return set()


def _save_dismissed_task_keys(app, keys):
    """Persist the dismissal key set to the dashboard config."""
    dashboard_cfg = get_dashboard_config(app.config)
    dashboard_cfg["dismissed_tasks"] = sorted(keys)
    save_dashboard_config(app.config, dashboard_cfg)


def _refresh_tasks_section(app, tasks=None, recent=None):
    """Clear and repopulate the merged Tasks list.

    Rows come from the waiting/running collectors plus the newest
    completed history entries, sorted reverse-chronologically by each
    row's time (live rows use the task start, completed rows the
    completion time); rows without a usable time sort to the top.
    Completed entries the user removed stay hidden via their dismissal
    keys, and keys that can no longer match the loaded history window
    are pruned.  The current selection is preserved across the rebuild
    for rows that survive (matched by task key or log file).
    """
    selection = app.dashboard_tasks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    keep_task_keys = set()
    keep_log_files = set()
    for path in pathlist:
        tree_iter = model.get_iter(path)
        task_key = model.get_value(tree_iter, 5)
        log_file = model.get_value(tree_iter, 6)
        if task_key:
            keep_task_keys.add(task_key)
        if log_file:
            keep_log_files.add(log_file)

    if tasks is None:
        tasks = _collect_running_tasks(app)
    if recent is None:
        recent = _get_recent_entries(10)

    dismissed = _dismissed_task_keys(app)
    window_keys = {_completed_task_key(e) for e in recent}
    effective_dismissed = dismissed & window_keys
    if dismissed != effective_dismissed:
        _save_dismissed_task_keys(app, effective_dismissed)
    visible_recent = [e for e in recent if _completed_task_key(e) not in effective_dismissed]

    rows = [_live_task_row(t) for t in tasks]
    rows.extend(_completed_task_row(e) for e in visible_recent)
    # Reverse chronological: timed rows newest-first, timeless rows on top.
    rows.sort(key=lambda r: (r["sort_ts"] is not None, -(r["sort_ts"] or 0.0)))

    app.dashboard_tasks_store.clear()
    if not rows:
        app.dashboard_tasks_store.append(["No tasks", "", "", "", "", "", "", ""])
        return

    paths_to_select = []
    for row in rows:
        tree_iter = app.dashboard_tasks_store.append(
            [
                row["dt_display"],
                row["type"],
                row["name"],
                row["status"],
                row["state"],
                row["task_key"],
                row["log_file"],
                row["completed_key"],
            ]
        )
        if (row["task_key"] and row["task_key"] in keep_task_keys) or (
            row["log_file"] and row["log_file"] in keep_log_files
        ):
            paths_to_select.append(app.dashboard_tasks_store.get_path(tree_iter))

    for path in paths_to_select:
        selection.select_path(path)


def _format_iscsi_missing_message(lun):
    """Convert a raw shortfall dict into user-friendly text.

    Backstore names follow the convention ``vm-<vmid>-disk-<N>``. When possible,
    the message is written in terms of the VM and disk number instead of iSCSI
    jargon. ``kind`` distinguishes the two failure shapes: "missing" (backstore
    not loaded in the target) and "unmapped" (loaded, but no LUN mapping).
    """
    name = lun.get("name", "?")
    target = lun.get("target", "?")
    match = _ISCSI_BACKSTORE_RE.match(name)
    if lun.get("kind") == "unmapped":
        if match:
            vmid = match.group(1)
            disk = match.group(2)
            return (
                f"VM {vmid} disk {disk} ({name}) is loaded in the iSCSI target "
                f"but has no LUN mapping on target {target} — the compute node "
                "cannot see this disk."
            )
        return (
            f"Disk {name} is loaded in the iSCSI target but has no LUN mapping "
            f"on target {target} — the compute node cannot see this disk."
        )
    if match:
        vmid = match.group(1)
        disk = match.group(2)
        return (
            f"VM {vmid} disk {disk} ({name}) is not exported as an iSCSI LUN "
            f"on target {target}. The VM may not see this disk."
        )
    return (
        f"Disk {name} is not exported as an iSCSI LUN on target {target}. "
        f"The VM may not see this disk."
    )


def _refresh_iscsi_section(app, missing_luns, stale=False):
    """Clear and repopulate the iSCSI Issues box."""
    for child in app.dashboard_iscsi_box.get_children():
        child.destroy()

    if stale:
        stale_lbl = Gtk.Label()
        stale_lbl.set_markup("<i>iSCSI data may be stale while storage is busy.</i>")
        stale_lbl.set_halign(Gtk.Align.START)
        app.dashboard_iscsi_box.pack_start(stale_lbl, False, False, 0)

    if not missing_luns:
        lbl = Gtk.Label(label="All VM disks are exported as iSCSI LUNs.")
        lbl.set_halign(Gtk.Align.START)
        app.dashboard_iscsi_box.pack_start(lbl, False, False, 0)
        return

    tooltip_text = (
        "Each VM disk is a ZFS zvol shared to the compute node over iSCSI. "
        '"Not exported" means the disk is in the expected list but is not '
        "currently loaded in the iSCSI target; \u201cno LUN mapping\u201d means the "
        "backstore is loaded but its LUN mapping was lost (the boot-restore "
        "degradation shape). Causes include: detached disk, encryption key "
        "not loaded, pool not imported, a missing backstore, or a lost LUN "
        "mapping. Click Fix this to run repair-iscsi-luns, which recreates "
        "missing exports and mappings and rescans the compute node."
    )

    for lun in missing_luns:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_halign(Gtk.Align.START)

        msg = _format_iscsi_missing_message(lun)
        lbl = Gtk.Label()
        lbl.set_markup(f'<span foreground="#FF8C00">⚠</span> {msg}')
        lbl.set_halign(Gtk.Align.START)
        lbl.set_line_wrap(True)
        lbl.set_tooltip_text(tooltip_text)
        row.pack_start(lbl, False, False, 0)

        fix_btn = Gtk.Button(label="Fix this")
        fix_btn.set_tooltip_text(tooltip_text)
        fix_btn.connect("clicked", _on_fix_iscsi_clicked, app)
        row.pack_start(fix_btn, False, False, 0)

        app.dashboard_iscsi_box.pack_start(row, False, False, 0)


def _on_fix_iscsi_clicked(_button, app):
    """Run repair-iscsi-luns and refresh the dashboard."""
    log_msg("INFO: Running repair-iscsi-luns...")
    try:
        repair_script = resolve_local_bin("repair-iscsi-luns")
        result = subprocess.run(
            [repair_script],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode == 0:
            log_msg("INFO: repair-iscsi-luns completed successfully")
        else:
            log_msg(f"WARN: repair-iscsi-luns exited {result.returncode}")

        if result.stdout:
            for line in result.stdout.strip().splitlines():
                log_msg(line)
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                log_msg(line)
    except (OSError, subprocess.TimeoutExpired) as e:
        log_msg(f"WARN: repair-iscsi-luns failed: {e}")

    # The repair may have changed the LUN state; bypass the TTL cache so
    # the post-repair refresh shows current reality.
    with _iscsi_luns_lock:
        _iscsi_luns_cache["time"] = 0.0

    refresh_dashboard_page(app)


def _split_pool_status_sections(raw):
    """Split `zpool status` (no pool argument) output into (pool, section) pairs.

    Each pool's report begins with a "  pool: <name>" line; the section runs
    until the next such line. Returns an empty list when raw is empty.
    """
    sections = []
    current_name = None
    current_lines = []
    for line in raw.splitlines():
        m = _ZPOOL_STATUS_POOL_RE.match(line)
        if m:
            if current_name is not None:
                sections.append((current_name, "\n".join(current_lines)))
            current_name = m.group(1)
            current_lines = [line]
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        sections.append((current_name, "\n".join(current_lines)))
    return sections


def _collect_running_tasks(app):
    """Gather all currently running tasks: GUI runners, scrubs, ZFS-native ops, profiles.

    Returns a list of dicts with keys: name, type, status, task_key.
    """
    tasks = []

    # 1. GUI runners
    for runner_name in (
        "backup_runner",
        "offsite_runner",
        "restore_runner",
        "retention_runner",
        "dataset_runner",
    ):
        runner = getattr(app, runner_name, None)
        if runner and getattr(runner, "running", False):
            label = getattr(runner, "operation_detail", None) or runner.label
            total = len(runner.steps)
            if runner._finally_step:
                total += 1
            if getattr(runner, "_in_lock_wait", False) is True:
                status = "Waiting for dataset lock"
                waiting_for_lock = True
            else:
                step_text = f"Step {runner.current_step + 1}/{total}" if total > 0 else "Running"
                status = step_text
                waiting_for_lock = False
            tasks.append(
                {
                    "name": label,
                    "type": "GUI",
                    "status": status,
                    "task_key": f"runner:{runner_name}",
                    "log_file": getattr(runner, "_session_log_file", None),
                    "waiting_for_lock": waiting_for_lock,
                    "started": _epoch_to_local_iso(getattr(runner, "_session_start_time", None)),
                    "wait_started": _epoch_to_local_iso(
                        getattr(runner, "_lock_wait_started", None)
                    ),
                }
            )

    # 2. Active scrubs
    queue = getattr(app, "scrub_queue", None)
    if queue:
        from scrub_manager import ScrubState, get_all_pool_scrub_states

        scrub_states = get_all_pool_scrub_states()
        # Pick up queue changes made by other processes (e.g., a headless
        # scrub profile) before reconciling against live zpool status so
        # finished or paused scrubs are not still shown as running when the
        # in-memory queue is stale.
        queue.reload()
        queue.tick(scrub_states)
        for pool_name in queue.active:
            info = scrub_states.get(pool_name)
            status = "Running"
            if info and info.state == ScrubState.SCANNING:
                if info.progress_percent is not None:
                    status = f"{info.progress_percent:.1f}% complete"
                if info.eta is not None:
                    status += f" (ETA {info.eta:%Y-%m-%d %H:%M})"
            tasks.append(
                {
                    "name": f"Scrub: {pool_name}",
                    "type": "Scrub",
                    "status": status,
                    "task_key": f"scrub:{pool_name}",
                    "started": _zfs_time_to_iso(info.as_of) if info else None,
                }
            )

    # 3. ZFS-native in-progress operations (resilver / RAIDZ expand / vdev removal)
    from scrub_manager import parse_pool_operations

    repo = getattr(app.ctx, "zfs_repository", None) or get_default_repository()
    raw_status = repo.all_pool_status_text()
    for pool_name, section in _split_pool_status_sections(raw_status):
        op = parse_pool_operations(pool_name, section)
        if op is None:
            continue
        if op.kind == "resilver":
            op_name = f"Resilver: {op.pool}"
        elif op.kind == "expand":
            op_name = f"Expand {op.subject}: {op.pool}"
        else:
            op_name = f"Remove vdev {op.subject}: {op.pool}"
        op_status = (
            f"{op.progress_percent:.1f}% done" if op.progress_percent is not None else "In progress"
        )
        since_match = _IN_PROGRESS_SINCE_RE.search(section)
        tasks.append(
            {
                "name": op_name,
                "type": "ZFS",
                "status": op_status,
                "task_key": f"zfsop:{op.pool}",
                "started": _zfs_time_to_iso(since_match.group(1)) if since_match else None,
            }
        )

    # 4. Running scheduled profiles (advisory lock files)
    for profile in list_running_profiles():
        pid = profile.get("pid")
        # The waiting invocation's start is when it began waiting on the
        # lock, so it doubles as both row start and wait start.
        profile_started = profile.get("started")
        profile_started = profile_started if profile_started != "?" else None
        if profile.get("waiting"):
            status = "Waiting for profile lock"
            waiting_for_lock = True
            task_key = f"profile-wait:{profile['name']}"
        else:
            status = f"PID {pid}" if pid else "Running"
            waiting_for_lock = False
            task_key = f"profile:{profile['name']}"
        tasks.append(
            {
                "name": profile["name"],
                "type": "Profile",
                "status": status,
                "task_key": task_key,
                "log_file": profile.get("log_file"),
                "waiting_for_lock": waiting_for_lock,
                "started": profile_started,
                "wait_started": profile_started if waiting_for_lock else None,
            }
        )

    # 5. Disk surface tests (SMART self-tests running in drive firmware)
    from disk_surface_test import load_surface_test_state, surface_cell_text

    surface_state = load_surface_test_state()
    for disk_path, entry in surface_state.get("tests", {}).items():
        if entry.get("status") == "running":
            tasks.append(
                {
                    "name": f"Surface Test: {disk_path}",
                    "type": "Surface Test",
                    "status": surface_cell_text(entry),
                    "task_key": f"surfacetest:{disk_path}",
                    "started": entry.get("started_at"),
                }
            )

    # 6. Legacy scheduled tasks (profile_runner.py processes not yet using locks)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "profile_runner.py"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                pid = line.strip()
                if not pid:
                    continue
                # Try to get profile name from command line
                profile_name = None
                try:
                    ps_result = subprocess.run(
                        ["ps", "-p", pid, "-o", "args="],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    if ps_result.returncode == 0:
                        profile_name = _profile_name_from_runner_args(ps_result.stdout.strip())
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
                if not profile_name:
                    profile_name = f"profile_runner.py (PID {pid})"
                # Skip if already shown as a profile task.
                if any(t["type"] == "Profile" and t["name"] == profile_name for t in tasks):
                    continue
                tasks.append(
                    {
                        "name": f"Scheduled: {profile_name}",
                        "type": "Scheduled",
                        "status": f"PID {pid}",
                        "task_key": f"scheduled:{pid}",
                        "log_file": _log_file_from_pid_environ(int(pid)),
                        "started": _scheduled_start_iso(pid),
                    }
                )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return tasks


def _refresh_active_locks_section(app, locks):
    """Clear and repopulate the Active Locks list."""
    app.dashboard_locks_store.clear()

    if not locks:
        app.dashboard_locks_store.append(["No active locks", "", "", "", "", "", ""])
        return

    for lock in locks:
        app.dashboard_locks_store.append(
            [
                lock.get("dataset", ""),
                lock.get("type", ""),
                str(lock.get("pid", "")),
                lock.get("script", ""),
                lock.get("host", ""),
                lock.get("acquired", ""),
                lock.get("description", ""),
            ]
        )


def _refresh_warnings_section(app, warnings):
    """Clear and repopulate the Warnings box."""
    for child in app.dashboard_warn_box.get_children():
        child.destroy()

    if not warnings:
        lbl = Gtk.Label(label="No warnings — everything looks good.")
        lbl.set_halign(Gtk.Align.START)
        app.dashboard_warn_box.pack_start(lbl, False, False, 0)
        return

    for w in warnings:
        lbl = Gtk.Label()
        lbl.set_markup(f'<span foreground="#FF8C00">⚠</span> {w}')
        lbl.set_halign(Gtk.Align.START)
        lbl.set_line_wrap(True)
        app.dashboard_warn_box.pack_start(lbl, False, False, 0)


def _update_fix_locks_button(app, stale_count):
    """Enable or disable the Fix Locks action button based on stale count."""
    if hasattr(app, "_fix_locks_button"):
        app._fix_locks_button.set_sensitive(stale_count > 0)


def _update_repair_mount_order_button(app, unreachable_mounts):
    """Enable or disable the Repair Mount Order button based on detection."""
    button = getattr(app, "_repair_mount_order_button", None)
    if button is not None:
        button.set_sensitive(bool(unreachable_mounts))


def on_dashboard_repair_mount_order(app):
    """Plan, confirm, and run the mount-order repair for all findings."""
    from dataset_actions import run_mount_repair

    run_mount_repair(app, scope=None)
    refresh_dashboard_page(app)


def on_dashboard_refresh(app):
    """Handler for the Refresh action button."""
    log_msg("VERB: Refreshing dashboard...")
    refresh_dashboard_page(app)


def on_dashboard_fix_locks(app):
    """Handler for the Fix Locks action button."""
    removed = _cleanup_stale_locks()
    log_msg(f"INFO: Removed {removed} stale lock file(s)")
    refresh_dashboard_page(app)


def _cancel_task(app, task_key):
    """Cancel a single task by its task_key."""
    if task_key.startswith("runner:"):
        runner_name = task_key.split(":", 1)[1]
        runner = getattr(app, runner_name, None)
        if runner and getattr(runner, "running", False):
            runner.cancel()
            log_msg(f"INFO: Cancelled {runner.label}")
        else:
            log_msg(f"WARN: Runner {runner_name} is not running")
    elif task_key.startswith("scrub:"):
        pool_name = task_key.split(":", 1)[1]
        from scrub_manager import stop_scrub

        stop_scrub(pool_name)
        log_msg(f"INFO: Stopped scrub on '{pool_name}'")
    elif task_key.startswith("zfsop:"):
        log_msg("INFO: ZFS-native operations cannot be cancelled from the GUI")
    elif task_key.startswith("profile-wait:"):
        profile_name = task_key.split(":", 1)[1]
        pid = None
        for profile in list_running_profiles():
            if profile.get("waiting") and profile.get("name") == profile_name:
                pid = profile.get("pid")
                break
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
                log_msg(f"INFO: Sent SIGTERM to waiting profile '{profile_name}' (PID {pid})")
            except OSError as e:
                log_msg(f"WARN: Failed to cancel waiting profile '{profile_name}': {e}")
        else:
            log_msg(f"WARN: Waiting profile '{profile_name}' is no longer running")
    elif task_key.startswith("profile:"):
        profile_name = task_key.split(":", 1)[1]
        pid = None
        for profile in list_running_profiles():
            if not profile.get("waiting") and profile.get("name") == profile_name:
                pid = profile.get("pid")
                break
        if isinstance(pid, int) and pid > 0:
            try:
                # The runner handles SIGTERM gracefully: it terminates the
                # in-flight step's process group and runs no further steps.
                os.kill(pid, signal.SIGTERM)
                log_msg(f"INFO: Sent SIGTERM to running profile '{profile_name}' (PID {pid})")
            except OSError as e:
                log_msg(f"WARN: Failed to cancel running profile '{profile_name}': {e}")
        else:
            log_msg(f"WARN: Running profile '{profile_name}' is no longer running")
    elif task_key.startswith("scheduled:"):
        pid_str = task_key.split(":", 1)[1]
        try:
            pid = int(pid_str)
            os.kill(pid, signal.SIGTERM)
            log_msg(f"INFO: Sent SIGTERM to scheduled task PID {pid}")
        except (ValueError, OSError) as e:
            log_msg(f"WARN: Failed to cancel scheduled task {pid_str}: {e}")
    elif task_key.startswith("surfacetest:"):
        disk_path = task_key.split(":", 1)[1]
        from disk_surface_test import cancel_surface_test

        cancel_surface_test(app, disk_path)
    else:
        log_msg(f"WARN: Unknown task key: {task_key}")


def on_dashboard_cancel_selected(app):
    """Cancel all selected tasks in the Tasks list.

    Works for waiting and running rows alike: waiting GUI runners get
    their lock wait interrupted, waiting profiles are signalled, and
    running tasks take their usual cancel path.
    """
    selection = app.dashboard_tasks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if not pathlist:
        log_msg("WARN: No tasks selected")
        return

    cancelled = 0
    for path in pathlist:
        tree_iter = model.get_iter(path)
        task_key = model.get_value(tree_iter, 5)
        if task_key:
            _cancel_task(app, task_key)
            cancelled += 1

    if cancelled:
        # Allow a moment for cancellation to take effect, then refresh
        GLib.timeout_add_seconds(1, lambda: refresh_dashboard_page(app) or False)


def on_dashboard_remove_selected(app):
    """Remove the selected completed rows from the Tasks list.

    Removal dismisses the rows for future refreshes; the history entry
    itself is kept.  Waiting and running rows cannot be removed.
    """
    selection = app.dashboard_tasks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    paths = []
    keys = []
    for path in pathlist:
        tree_iter = model.get_iter(path)
        if model.get_value(tree_iter, 4) != "completed":
            continue
        key = model.get_value(tree_iter, 7)
        if key:
            keys.append(key)
        paths.append(path)
    if not keys:
        log_msg("WARN: No completed tasks selected for removal")
        return

    # Remove bottom-up so earlier removals do not shift the remaining paths.
    for path in reversed(paths):
        model.remove(model.get_iter(path))
    _save_dismissed_task_keys(app, set(keys) | _dismissed_task_keys(app))
    log_msg(f"INFO: Removed {len(keys)} completed task(s) from the Tasks list")


def _on_dashboard_tasks_selection_changed(selection, app):
    """Enable or disable the task action buttons based on the selection.

    Cancel needs a waiting or running row (any row with a task key),
    Remove a completed row, and View Log any row carrying a log file.
    The log path is cached so View Log still opens the intended log even
    if a background refresh changes the selection before the click.
    """
    model, pathlist = selection.get_selected_rows()
    can_cancel = False
    can_remove = False
    log_path = None
    for path in pathlist:
        tree_iter = model.get_iter(path)
        if model.get_value(tree_iter, 5):
            can_cancel = True
        if model.get_value(tree_iter, 4) == "completed":
            can_remove = True
        if log_path is None:
            candidate = model.get_value(tree_iter, 6)
            if candidate:
                log_path = candidate

    cancel_button = getattr(app, "_cancel_selected_button", None)
    if cancel_button is not None:
        cancel_button.set_sensitive(can_cancel)
    remove_button = getattr(app, "_remove_button", None)
    if remove_button is not None:
        remove_button.set_sensitive(can_remove)
    app._dashboard_view_log_path = log_path
    _update_view_log_button(app, bool(log_path))


def _update_view_log_button(app, enabled):
    """Enable or disable the View Log action button."""
    button = getattr(app, "_view_log_button", None)
    if button is not None:
        button.set_sensitive(enabled)


def on_dashboard_view_log(app):
    """Switch to the Logs tab and select the log for the selected task row.

    Uses the path cached by the selection handler so the action succeeds
    even if the dashboard selection was cleared after the button became
    sensitive.  Falls back to reading the current selection if no cache
    is available.
    """
    log_path = getattr(app, "_dashboard_view_log_path", None)

    if not log_path:
        selection = app.dashboard_tasks_view.get_selection()
        model, pathlist = selection.get_selected_rows()
        for path in pathlist:
            tree_iter = model.get_iter(path)
            candidate = model.get_value(tree_iter, 6)
            if candidate:
                log_path = candidate
                break

    if not log_path:
        log_msg("WARN: No task row with a log file selected")
        return

    app.stack.set_visible_child_name("logs")
    if not select_log_by_path(app, log_path):
        log_msg(f"WARN: Log entry not found: {log_path}")


def setup_dashboard_actions(app):
    """Connect selection signals to the dashboard action buttons."""
    tasks_selection = app.dashboard_tasks_view.get_selection()
    tasks_selection.connect("changed", _on_dashboard_tasks_selection_changed, app)
    _on_dashboard_tasks_selection_changed(tasks_selection, app)
