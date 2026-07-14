"""Dashboard / Overview page — at-a-glance system health and recent operations."""

import json
import os
import re
import signal
import socket
import subprocess
from datetime import datetime, timedelta

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from logging_config import log_msg
from config_core import get_dashboard_config, save_dashboard_config
from backup_history import load_history
from gui_helpers import set_monospace_font, configure_treeview_column
from logs_page import select_log_by_path
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
# Purpose: Parse a line from /etc/iscsi-encrypted-luns.conf.
# Group 1: Backstore name  e.g. "vm-300-disk-1"
# Group 2: Device path    e.g. "/dev/zvol/threeamigos/proxmox/vm-300-disk-1"
# Group 3: Target short   e.g. "threeamigos"
# Examples:
#   "vm-300-disk-1:/dev/zvol/threeamigos/proxmox/vm-300-disk-1:threeamigos" -> match
#   "# this is a comment" -> no match (starts with #)
#   "" -> no match (blank line)
# Rationale: Config format is name:device:target, one per line.
_ENCRYPTED_LUN_RE = re.compile(r"^([^#\s][^:]*):([^:]+):(.+)$")


ZFSLOCK_DIR = "/run/lock/zfs"
ZFSLOCK_LOCKS_DIR = os.path.join(ZFSLOCK_DIR, ".locks")
ZFSLOCK_PIDS_DIR = os.path.join(ZFSLOCK_DIR, ".pids")
PROFILE_LOCK_DIR = os.environ.get(
    "ZFSUTILITIES_PROFILE_LOCK_DIR", "/run/lock/zfs/profiles"
)


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
    """Return a list of running profile dicts from the profile lock directory.

    Each dict contains: name, pid, started.
    Stale locks are ignored.
    """
    if not os.path.isdir(PROFILE_LOCK_DIR):
        return []

    profiles = []
    for entry in os.listdir(PROFILE_LOCK_DIR):
        if not entry.endswith(".lock"):
            continue
        lock_path = os.path.join(PROFILE_LOCK_DIR, entry)
        if not os.path.isfile(lock_path):
            continue
        if _is_profile_lock_stale(lock_path):
            continue
        data = _read_json_lock(lock_path) or {}
        name = data.get("profile") or entry[:-5]
        profiles.append({
            "name": name,
            "pid": data.get("pid"),
            "started": data.get("started", "?"),
        })
    return profiles


def _run_cmd(cmd, timeout=5):
    """Run a command, return stdout text or None on failure/timeout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
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

    Each dict contains: name, health, cap, cap_int, scrub_date, status_errors.
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
            }
        )
    return pools


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


def _get_node_config():
    """Parse node configuration and return mode + host identities.

    Mirrors the logic in /usr/local/lib/node-lib.sh:
      1. Reads /etc/zfsutilities-node.conf, falls back to /etc/two-node.conf
      2. Defaults NODE_MODE to "two-node" when unset (legacy compat)
      3. In single-node mode, STORAGE_HOST = COMPUTE_HOST = THIS_HOST

    Returns a dict:
        {
            "mode": "single-node" | "two-node",
            "this_host": <hostname>,
            "storage_host": <hostname>,
            "compute_host": <hostname>,
            "storage_ip": <ip> | "",
        }
    If no config file exists, returns single-node with the local hostname.
    """
    result = {
        "mode": "single-node",
        "this_host": _local_hostname(),
        "storage_host": _local_hostname(),
        "compute_host": _local_hostname(),
        "storage_ip": "",
    }

    conf_path = None
    for path in ("/etc/zfsutilities-node.conf", "/etc/two-node.conf"):
        if os.path.exists(path):
            conf_path = path
            break

    if not conf_path:
        return result

    node_mode = None
    storage_host = ""
    compute_host = ""
    storage_ip = ""

    try:
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("NODE_MODE="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    node_mode = value
                elif line.startswith("STORAGE_HOST="):
                    storage_host = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("COMPUTE_HOST="):
                    compute_host = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("STORAGE_IP="):
                    storage_ip = line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass

    # Default to two-node when unset (matches node-lib.sh behavior)
    if node_mode is None:
        node_mode = "two-node"

    result["mode"] = node_mode
    if node_mode == "single-node":
        result["storage_host"] = result["this_host"]
        result["compute_host"] = result["this_host"]
        result["storage_ip"] = ""
    else:
        if storage_host:
            result["storage_host"] = storage_host
        if compute_host:
            result["compute_host"] = compute_host
        if storage_ip:
            result["storage_ip"] = storage_ip

    return result


def _local_hostname():
    """Return the short hostname of this machine."""
    try:
        return socket.gethostname().split(".")[0]
    except OSError:
        return "unknown"


def _get_host_version(host):
    """Return the zfsutilities version string for the given host.

    For the local host, reads the repo VERSION file or the deployed
    /usr/local/lib/zfsutilities/current/VERSION.
    For remote hosts, SSHes to the host and reads the deployed VERSION.
    Returns "unknown" if the version cannot be determined.
    """
    local_host = _local_hostname()
    if host == local_host:
        # Local host — try repo VERSION first, then deployed
        repo_version = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"
        )
        deployed = "/usr/local/lib/zfsutilities/current/VERSION"
        for path in (repo_version, deployed):
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        return f.read().strip()
                except OSError:
                    pass
        return "unknown"

    # Remote host — SSH and read deployed version
    try:
        result = subprocess.run(
            ["ssh", f"root@{host}", "cat /usr/local/lib/zfsutilities/current/VERSION"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


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
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def _is_two_node():
    """Return True if the system is configured for two-node mode."""
    return _get_node_config()["mode"] == "two-node"


def _get_peer_host():
    """Return the hostname of the other node in a two-node configuration.

    Returns None in single-node mode, when no configuration is present, or
    when the local host cannot be distinguished from the peer.
    """
    cfg = _get_node_config()
    if cfg["mode"] != "two-node":
        return None

    local = cfg["this_host"]
    storage = cfg["storage_host"]
    compute = cfg["compute_host"]

    if local == storage and compute and compute != local:
        return compute
    if local == compute and storage and storage != local:
        return storage
    if storage and storage != local:
        return storage
    if compute and compute != local:
        return compute
    return None


def _log_peer_version_result(local_version, peer_host, peer_version):
    """Log the outcome of a startup peer-node version comparison."""
    if peer_version == "unknown":
        log_msg(
            f"WARN: Could not determine ZFSutilities version on peer node "
            f"{peer_host}"
        )
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

    ZFS snapshot names use ``%Y-%m-%dT%H:%M%z`` (e.g. ``2026-05-28T14:32-0400``).
    History entries store ``datetime.now().isoformat()`` which is naive, so the
    parsed value is interpreted as local time before formatting.

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


_ISCSI_CONF = "/etc/iscsi-encrypted-luns.conf"


def _get_iscsi_missing_luns():
    """Compare expected backstores against targetcli.

    Reads /etc/rtslib-fb-target/expected-backstores.txt (all LUNs) first,
    falling back to /etc/iscsi-encrypted-luns.conf (encrypted LUNs only)
    if the manifest is not present.

    Returns a list of missing {name, target} dicts.
    Returns an empty list if single-node, config missing, or all LUNs present.
    """
    if not _is_two_node():
        return []

    manifest_path = "/etc/rtslib-fb-target/expected-backstores.txt"
    fallback_path = _ISCSI_CONF

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

    missing_names = [n for n in expected_names if n not in loaded]
    if not missing_names:
        return []

    # Try to map missing backstores to targets for display.
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
    if not target_map or any(n not in target_map for n in missing_names):
        if os.path.exists(savefile):
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
                                if bs_name in missing_names and bs_name not in target_map:
                                    target_map[bs_name] = target_short
            except (OSError, ValueError):
                pass

    missing = []
    for name in missing_names:
        missing.append({"name": name, "target": target_map.get(name, "?")})
    return missing


def _count_stale_locks():
    """Check /run/lock/zfs/.locks/ for stale entries.

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


def _get_warnings(pools, recent_history, threshold, running_profiles=None):
    """Compile warning strings from all sources.

    Args:
        pools: List of pool dicts from _get_pool_health().
        recent_history: Dict from _get_recent_history().
        threshold: Low-space warning threshold (int 0-100).
        running_profiles: Optional list of running profile dicts.

    Returns a list of human-readable warning strings.
    """
    warnings = []

    for p in pools:
        health = p.get("health", "")
        if health != "ONLINE":
            warnings.append(f'Pool "{p["name"]}" is {health}')
        cap = p.get("cap_int", 0)
        if cap >= threshold:
            warnings.append(
                f'Pool "{p["name"]}" capacity at {p["cap"]} (threshold: {threshold}%)'
            )
        status_errors = p.get("status_errors") or {}
        if status_errors.get("has_errors"):
            summary = status_errors.get("errors_summary", "unknown error")
            warnings.append(
                f'Pool "{p["name"]}" has ZFS errors: {summary}'
            )

    if running_profiles:
        for profile in running_profiles:
            warnings.append(
                f"Profile '{profile['name']}' is running; concurrent GUI "
                "operations may wait for dataset locks"
            )

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


def _result_icon(result):
    """Return a checkmark or X mark for a history result string."""
    if result == "success":
        return "<span foreground='#00AA00'>✓</span>"
    return "<span foreground='#CC0000'>✗</span>"


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def create_dashboard_page(app):
    """Build and return the full Dashboard tab widget."""
    app._dashboard_timer = None

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
    box.set_margin_start(15)
    box.set_margin_end(15)
    box.set_margin_top(15)
    box.set_margin_bottom(15)
    scrolled.add(box)

    # Title
    title = Gtk.Label()
    title.set_markup("<big><b>Dashboard</b></big>")
    title.set_halign(Gtk.Align.START)
    box.pack_start(title, False, False, 0)

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
    app.dashboard_warn_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=5
    )
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
    pool_grid_sw.set_propagate_natural_height(True)
    pool_grid_sw.add(app.dashboard_pool_grid)
    pool_box.pack_start(pool_grid_sw, False, False, 0)
    app.dashboard_pool_frame.add(pool_box)
    box.pack_start(app.dashboard_pool_frame, False, False, 0)

    # --- Section 3: Running Tasks ---
    app.dashboard_proc_frame = _make_section_frame("Running Tasks")
    app.dashboard_tasks_store = Gtk.ListStore(str, str, str, str)
    app.dashboard_tasks_view = Gtk.TreeView(model=app.dashboard_tasks_store)
    app.dashboard_tasks_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.dashboard_tasks_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    for col_idx, title_text, width in [
        (0, "Task", 180),
        (1, "Type", 100),
        (2, "Status", 200),
    ]:
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
        col = Gtk.TreeViewColumn(title_text, r, text=col_idx)
        configure_treeview_column(col, width=width)
        app.dashboard_tasks_view.append_column(col)
    app._ui_state.bind_treeview(app.dashboard_tasks_view, "dashboard_tasks_view")

    app.enable_treeview_copy(app.dashboard_tasks_view)

    tasks_scrolled = Gtk.ScrolledWindow()
    tasks_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    tasks_scrolled.set_min_content_height(120)
    tasks_scrolled.add(app.dashboard_tasks_view)

    tasks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    tasks_box.set_margin_start(10)
    tasks_box.set_margin_end(10)
    tasks_box.set_margin_top(10)
    tasks_box.set_margin_bottom(10)
    tasks_box.pack_start(tasks_scrolled, True, True, 0)
    app.dashboard_proc_frame.add(tasks_box)
    box.pack_start(app.dashboard_proc_frame, False, False, 0)

    # --- Section 4: Recent Operations ---
    app.dashboard_ops_frame = _make_section_frame("Recent Operations")
    # Columns: datetime, type, name, outcome (markup), log_file (hidden)
    app.dashboard_ops_store = Gtk.ListStore(str, str, str, str, str)
    app.dashboard_ops_view = Gtk.TreeView(model=app.dashboard_ops_store)
    app.dashboard_ops_view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
    app.dashboard_ops_view.set_headers_visible(True)
    app.dashboard_ops_view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

    for col_idx, title_text, width in [
        (0, "Date / Time", 150),
        (1, "Type", 70),
        (2, "Name", 140),
        (3, "Outcome", 90),
    ]:
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
        if col_idx == 0:
            set_monospace_font(r)
        # Outcome column contains Pango markup (colored icons)
        attr = "markup" if col_idx == 3 else "text"
        col = Gtk.TreeViewColumn(title_text, r, **{attr: col_idx})
        configure_treeview_column(col, width=width)
        app.dashboard_ops_view.append_column(col)

    ops_scrolled = Gtk.ScrolledWindow()
    ops_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    ops_scrolled.set_min_content_height(180)
    ops_scrolled.add(app.dashboard_ops_view)

    ops_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    ops_box.set_margin_start(10)
    ops_box.set_margin_end(10)
    ops_box.set_margin_top(10)
    ops_box.set_margin_bottom(10)
    ops_box.pack_start(ops_scrolled, True, True, 0)
    app.dashboard_ops_frame.add(ops_box)
    box.pack_start(app.dashboard_ops_frame, False, False, 0)

    # --- Section 5: iSCSI Issues ---
    app.dashboard_iscsi_frame = _make_section_frame("iSCSI Issues")
    app.dashboard_iscsi_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=5
    )
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
    app.dashboard_config_frame.add(app.dashboard_config_grid)
    box.pack_start(app.dashboard_config_frame, False, False, 0)

    # Initial population
    refresh_dashboard_page(app)

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


def refresh_dashboard_page(app):
    """Re-gather all dashboard data and update every section."""
    dashboard_cfg = get_dashboard_config(app.config)
    threshold = dashboard_cfg.get("low_space_threshold", 80)

    pools, pools_stale = _get_cached_or_fresh(
        app, "_dashboard_pools", _get_pool_health()
    )
    recent = _get_recent_entries(10)
    missing_luns, iscsi_stale = _get_cached_or_fresh(
        app, "_dashboard_iscsi", _get_iscsi_missing_luns()
    )
    stale_count = _count_stale_locks()

    # Scrub status for dashboard
    from scrub_manager import get_all_pool_scrub_states
    scrub_states = get_all_pool_scrub_states()

    running_profiles = list_running_profiles()

    # Build warnings: live checks + startup-style checks
    warnings = _get_warnings(pools, recent, threshold, running_profiles)
    if not app.config.get("backup", {}).get("pull_steps") and not app.config.get("backup", {}).get("send_receive_steps"):
        warnings.append("No backup steps configured — configure in the Backup tab")
    if not app.config.get("offsite", {}).get("steps"):
        warnings.append("No offsite steps configured — configure in the Offsite tab")
    from feature_config import get_pools, get_checkagainst
    if not get_pools(app.config):
        warnings.append("No pools registered — add pools in the Pools tab")
    if not get_checkagainst(app.config):
        warnings.append("Checkagainst table is empty — configure in the Checkagainst tab")
    if stale_count > 0:
        warnings.append(f"Stale lock files: {stale_count}")

    _refresh_config_section(app)
    _refresh_pool_section(app, pools, scrub_states, stale=pools_stale)
    _refresh_ops_section(app, recent)
    _refresh_iscsi_section(app, missing_luns, stale=iscsi_stale)
    _refresh_warnings_section(app, warnings)
    _refresh_processes_section(app)

    # Update the contextual "Fix Locks" button visibility
    _update_fix_locks_button(app, stale_count)

    app.dashboard_config_frame.show_all()
    app.dashboard_pool_frame.show_all()
    app.dashboard_ops_frame.show_all()
    app.dashboard_warn_frame.show_all()
    app.dashboard_proc_frame.show_all()

    # iSCSI frame visibility depends on mode
    if _is_two_node():
        app.dashboard_iscsi_frame.show_all()
    else:
        app.dashboard_iscsi_frame.hide()


def _refresh_config_section(app):
    """Clear and repopulate the Configuration Info grid."""
    for child in app.dashboard_config_grid.get_children():
        child.destroy()

    cfg = _get_node_config()
    row = 0

    # Mode
    mode_lbl = Gtk.Label()
    mode_lbl.set_markup("<b>Mode:</b>")
    mode_lbl.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(mode_lbl, 0, row, 1, 1)

    mode_val = Gtk.Label(label=cfg["mode"])
    mode_val.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(mode_val, 1, row, 1, 1)
    row += 1

    # Hostnames
    if cfg["mode"] == "two-node":
        hosts = [
            ("This host", cfg["this_host"]),
            ("Storage host", cfg["storage_host"]),
            ("Compute host", cfg["compute_host"]),
        ]
        if cfg.get("storage_ip"):
            hosts.append(("Storage IP", cfg["storage_ip"]))
    else:
        hosts = [("Hostname", cfg["this_host"])]

    for label, hostname in hosts:
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{label}:</b>")
        lbl.set_halign(Gtk.Align.START)
        app.dashboard_config_grid.attach(lbl, 0, row, 1, 1)

        val = Gtk.Label(label=hostname)
        val.set_halign(Gtk.Align.START)
        app.dashboard_config_grid.attach(val, 1, row, 1, 1)
        row += 1

    # Versions
    ver_lbl = Gtk.Label()
    ver_lbl.set_markup("<b>Version(s):</b>")
    ver_lbl.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(ver_lbl, 0, row, 1, 1)

    if cfg["mode"] == "two-node":
        local_v = _get_host_version(cfg["this_host"])
        storage_v = _get_host_version(cfg["storage_host"])
        compute_v = _get_host_version(cfg["compute_host"])
        ver_text = f"local={local_v}  storage={storage_v}  compute={compute_v}"
    else:
        ver_text = _get_host_version(cfg["this_host"])

    ver_val = Gtk.Label(label=ver_text)
    ver_val.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(ver_val, 1, row, 1, 1)
    row += 1

    # ZFS versions
    zfs_lbl = Gtk.Label()
    zfs_lbl.set_markup("<b>ZFS version(s):</b>")
    zfs_lbl.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(zfs_lbl, 0, row, 1, 1)

    if cfg["mode"] == "two-node":
        # Map each unique host to the roles it occupies.
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

        zfs_parts = []
        for host, roles in host_roles:
            zfs_out = _get_host_zfs_version(host)
            if len(roles) == 1:
                header = f"{host} ({roles[0]}):"
            else:
                header = f"{host} ({','.join(roles)}):"
            zfs_parts.append(f"{header}\n{zfs_out}")
        zfs_text = "\n\n".join(zfs_parts)
    else:
        zfs_text = _get_host_zfs_version(cfg["this_host"])

    zfs_val = Gtk.Label(label=zfs_text)
    zfs_val.set_halign(Gtk.Align.START)
    app.dashboard_config_grid.attach(zfs_val, 1, row, 1, 1)


def _refresh_pool_section(app, pools, scrub_states=None, stale=False):
    """Clear and repopulate the Pool Health grid."""
    for child in app.dashboard_pool_grid.get_children():
        child.destroy()

    row = 0
    if stale:
        stale_lbl = Gtk.Label()
        stale_lbl.set_markup(
            "<i>Pool data may be stale while pools are busy.</i>"
        )
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


def _refresh_ops_section(app, recent):
    """Clear and repopulate the Recent Operations list."""
    app.dashboard_ops_store.clear()

    if not recent:
        app.dashboard_ops_store.append(["No operations yet.", "", "", "", ""])
        return

    for entry in recent:
        ts = _format_history_timestamp(entry.get("timestamp", "?"))
        etype = entry.get("type", "?")
        name = entry.get("name", "?")
        result = entry.get("result", "unknown")
        outcome = f"{_result_icon(result)} {result}"
        log_file = entry.get("log_file", "")
        app.dashboard_ops_store.append([ts, etype, name, outcome, log_file])


def _format_iscsi_missing_message(lun):
    """Convert a raw missing-LUN dict into user-friendly text.

    Backstore names follow the convention ``vm-<vmid>-disk-<N>``. When possible,
    the message is written in terms of the VM and disk number instead of iSCSI
    jargon.
    """
    name = lun.get("name", "?")
    target = lun.get("target", "?")
    match = _ISCSI_BACKSTORE_RE.match(name)
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
        stale_lbl.set_markup(
            "<i>iSCSI data may be stale while storage is busy.</i>"
        )
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
        "currently loaded in the iSCSI target. Causes include: detached disk, "
        "encryption key not loaded, pool not imported, or a missing "
        "backstore/LUN. Click Fix this to run repair-iscsi-luns, which "
        "recreates missing exports and rescans the compute node."
    )

    for lun in missing_luns:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_halign(Gtk.Align.START)

        msg = _format_iscsi_missing_message(lun)
        lbl = Gtk.Label()
        lbl.set_markup(f'<span foreground="#FF8C00">⚠</span> {msg}')
        lbl.set_halign(Gtk.Align.START)
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
        result = subprocess.run(
            ["/usr/local/lib/zfsutilities/bin/repair-iscsi-luns"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log_msg("INFO: repair-iscsi-luns completed successfully")
        else:
            log_msg(f"WARN: repair-iscsi-luns exited {result.returncode}")

        if result.stdout:
            for line in result.stdout.strip().splitlines():
                log_msg(f"INFO: {line}")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                log_msg(f"WARN: {line}")
    except (OSError, subprocess.TimeoutExpired) as e:
        log_msg(f"WARN: repair-iscsi-luns failed: {e}")

    refresh_dashboard_page(app)


def _collect_running_tasks(app):
    """Gather all currently running tasks: GUI runners, scrubs, profiles.

    Returns a list of dicts with keys: name, type, status, task_key.
    """
    tasks = []

    # 1. GUI runners
    for runner_name in ("backup_runner", "offsite_runner", "restore_runner", "retention_runner"):
        runner = getattr(app, runner_name, None)
        if runner and getattr(runner, "running", False):
            label = runner.label
            total = len(runner.steps)
            if runner._finally_step:
                total += 1
            step_text = f"Step {runner.current_step + 1}/{total}" if total > 0 else "Running"
            tasks.append({
                "name": label,
                "type": "GUI",
                "status": step_text,
                "task_key": f"runner:{runner_name}",
            })

    # 2. Active scrubs
    queue = getattr(app, "scrub_queue", None)
    if queue:
        from scrub_manager import get_all_pool_scrub_states, ScrubState
        scrub_states = get_all_pool_scrub_states()
        # Reconcile queue against live zpool status so finished or paused
        # scrubs are not still shown as running when the in-memory queue
        # is stale (e.g., after a headless profile paused/resumed scrubs).
        queue.tick(scrub_states)
        for pool_name in queue.active:
            info = scrub_states.get(pool_name)
            status = "Running"
            if info and info.state == ScrubState.SCANNING:
                if info.progress_percent is not None:
                    status = f"{info.progress_percent:.1f}% complete"
                if info.eta is not None:
                    status += f" (ETA {info.eta:%Y-%m-%d %H:%M})"
            tasks.append({
                "name": f"Scrub: {pool_name}",
                "type": "Scrub",
                "status": status,
                "task_key": f"scrub:{pool_name}",
            })

    # 3. Running scheduled profiles (advisory lock files)
    for profile in list_running_profiles():
        pid = profile.get("pid")
        status = f"PID {pid}" if pid else "Running"
        tasks.append({
            "name": profile["name"],
            "type": "Profile",
            "status": status,
            "task_key": f"profile:{profile['name']}",
        })

    # 4. Legacy scheduled tasks (profile_runner.py processes not yet using locks)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "profile_runner.py"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                pid = line.strip()
                if not pid:
                    continue
                # Try to get profile name from command line
                profile_name = "unknown"
                try:
                    ps_result = subprocess.run(
                        ["ps", "-p", pid, "-o", "args="],
                        capture_output=True, text=True, timeout=5,
                    )
                    if ps_result.returncode == 0:
                        args = ps_result.stdout.strip()
                        # profile_runner.py run <profile_name>
                        parts = args.split()
                        if len(parts) >= 2 and parts[-2] == "run":
                            profile_name = parts[-1]
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
                # Skip if already shown as a profile task.
                if any(t["type"] == "Profile" and t["name"] == profile_name for t in tasks):
                    continue
                tasks.append({
                    "name": f"Scheduled: {profile_name}",
                    "type": "Scheduled",
                    "status": f"PID {pid}",
                    "task_key": f"scheduled:{pid}",
                })
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return tasks


def _refresh_processes_section(app):
    """Clear and repopulate the Running Tasks list."""
    app.dashboard_tasks_store.clear()

    tasks = _collect_running_tasks(app)
    if not tasks:
        app.dashboard_tasks_store.append(["No running tasks", "", "", ""])
        return

    for t in tasks:
        app.dashboard_tasks_store.append([
            t["name"],
            t["type"],
            t["status"],
            t["task_key"],
        ])


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


def on_dashboard_refresh(app):
    """Handler for the Refresh action button."""
    log_msg("INFO: Refreshing dashboard...")
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
    elif task_key.startswith("profile:"):
        profile_name = task_key.split(":", 1)[1]
        log_msg(
            f"INFO: To cancel profile '{profile_name}', use Cancel Selected "
            "Tasks and then clean up its process if it does not stop"
        )
    elif task_key.startswith("scheduled:"):
        pid_str = task_key.split(":", 1)[1]
        try:
            pid = int(pid_str)
            os.kill(pid, signal.SIGTERM)
            log_msg(f"INFO: Sent SIGTERM to scheduled task PID {pid}")
        except (ValueError, OSError) as e:
            log_msg(f"WARN: Failed to cancel scheduled task {pid_str}: {e}")
    else:
        log_msg(f"WARN: Unknown task key: {task_key}")


def on_dashboard_cancel_selected(app):
    """Cancel all selected tasks in the Running Tasks list."""
    selection = app.dashboard_tasks_view.get_selection()
    model, pathlist = selection.get_selected_rows()
    if not pathlist:
        log_msg("WARN: No tasks selected")
        return

    cancelled = 0
    for path in pathlist:
        tree_iter = model.get_iter(path)
        task_key = model.get_value(tree_iter, 3)
        if task_key:
            _cancel_task(app, task_key)
            cancelled += 1

    if cancelled:
        # Allow a moment for cancellation to take effect, then refresh
        GLib.timeout_add_seconds(1, lambda: refresh_dashboard_page(app) or False)


def _on_dashboard_tasks_selection_changed(selection, app):
    """Enable or disable Cancel Selected Tasks based on selection."""
    button = getattr(app, "_cancel_selected_button", None)
    if button is None:
        return
    model, pathlist = selection.get_selected_rows()
    enable = False
    for path in pathlist:
        tree_iter = model.get_iter(path)
        if model.get_value(tree_iter, 3):
            enable = True
            break
    button.set_sensitive(enable)


def _update_view_log_button(app, enabled):
    """Enable or disable the View Log action button."""
    button = getattr(app, "_view_log_button", None)
    if button is not None:
        button.set_sensitive(enabled)


def _on_dashboard_ops_selection_changed(selection, app):
    """Enable or disable View Log based on Recent Operations selection."""
    model, tree_iter = selection.get_selected()
    _update_view_log_button(app, tree_iter is not None)


def on_dashboard_view_log(app):
    """Switch to the Logs tab and select the log for the selected operation."""
    selection = app.dashboard_ops_view.get_selection()
    model, tree_iter = selection.get_selected()
    if tree_iter is None:
        log_msg("WARN: No recent operation selected")
        return

    log_path = model.get_value(tree_iter, 4)
    if not log_path:
        log_msg("WARN: No log file recorded for the selected operation")
        return

    app.stack.set_visible_child_name("logs")
    if not select_log_by_path(app, log_path):
        log_msg(f"WARN: Log entry not found: {log_path}")


def setup_dashboard_actions(app):
    """Connect selection signals to the dashboard action buttons."""
    tasks_selection = app.dashboard_tasks_view.get_selection()
    tasks_selection.connect("changed", _on_dashboard_tasks_selection_changed, app)
    _on_dashboard_tasks_selection_changed(tasks_selection, app)

    ops_selection = app.dashboard_ops_view.get_selection()
    ops_selection.connect("changed", _on_dashboard_ops_selection_changed, app)
    _on_dashboard_ops_selection_changed(ops_selection, app)

