"""Per-feature configuration getters/setters and snapshot name helpers."""

import fcntl
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime

from config_core import save_config, _deep_copy, BACKUP_DEFAULTS
from file_locking import scrub_state_lock_read, scrub_state_lock_write


def get_backup_config(config):
    defaults = _deep_copy(BACKUP_DEFAULTS)
    backup = config.get("backup", {})
    merged_vars = dict(defaults["variables"])
    merged_vars.update(backup.get("variables", {}))
    backup["variables"] = merged_vars
    for key in ("pull_steps_active", "pull_steps", "send_receive_steps"):
        if key not in backup:
            backup[key] = defaults[key]
    if "post_steps" not in backup:
        backup["post_steps"] = defaults["post_steps"]
    else:
        merged_post = dict(defaults["post_steps"])
        merged_post.update(backup["post_steps"])
        backup["post_steps"] = merged_post
    for key in ("pre_backup_script_enabled", "pre_backup_script",
                "post_backup_script_enabled", "post_backup_script",
                "zfs_keys_path", "zfs_keys_dest"):
        if key not in backup:
            backup[key] = defaults[key]
    config["backup"] = backup
    return backup


def save_backup_config(config, backup_data):
    config["backup"] = backup_data
    save_config(config)


OFFSITE_DEFAULTS = {
    "variables": {
        "applyholds": "Y",
        "doincrementals": "Y",
        "dointermediates": "N",
        "allow_destructive": "N",
        "receive_F_option": "F",
        "verify_after_transfer": "Y",
        "includes": "",
        "excludes": "",
        "startwith": "",
        "endwith": "",
    },
    "offsite_pools": [],
    "steps": [],
}


def get_offsite_config(config):
    defaults = _deep_copy(OFFSITE_DEFAULTS)
    offsite = config.get("offsite", {})
    merged_vars = dict(defaults["variables"])
    merged_vars.update(offsite.get("variables", {}))
    offsite["variables"] = merged_vars
    for key in ("offsite_pools", "steps"):
        if key not in offsite:
            offsite[key] = defaults[key]
    config["offsite"] = offsite
    return offsite


def save_offsite_config(config, offsite_data):
    config["offsite"] = offsite_data
    save_config(config)


RESTORE_DEFAULTS = {
    "source": "",
    "dest": "",
    "auto_dest": False,
    "variables": {
        "depth": "",
        "label": "",
        "includes": "",
        "excludes": "",
        "startwith": "",
        "endwith": "",
    },
    "do_part1": True,
    "do_part2": True,
}


def get_restore_config(config):
    defaults = _deep_copy(RESTORE_DEFAULTS)
    restore = config.get("restore", {})
    for key in ("source", "dest", "auto_dest", "do_part1", "do_part2"):
        if key not in restore:
            restore[key] = defaults[key]
    merged_vars = dict(defaults["variables"])
    merged_vars.update(restore.get("variables", {}))
    restore["variables"] = merged_vars
    config["restore"] = restore
    return restore


def save_restore_config(config, restore_data):
    config["restore"] = restore_data
    save_config(config)


def _normalize_pool_entry(pool):
    """Convert a legacy string pool entry to a dict."""
    if isinstance(pool, dict):
        return pool
    return {"name": str(pool), "offsite_candidate": False}


def get_pools(config):
    pools = config.get("pools")
    if pools is None:
        pools = []
        config["pools"] = pools
    else:
        # Normalize legacy string entries in-place on first access.
        pools = [_normalize_pool_entry(p) for p in pools]
        config["pools"] = pools
    return pools


def get_pool_names(config):
    """Return a list of known pool names."""
    return [p["name"] for p in get_pools(config)]


def get_offsite_candidate_names(config):
    """Return names of pools marked as offsite candidates."""
    return [
        p["name"] for p in get_pools(config)
        if p.get("offsite_candidate", False)
    ]


def save_pools(config, pools):
    normalized = [_normalize_pool_entry(p) for p in pools]
    config["pools"] = normalized

    # Mirror offsite candidate names into the offsite config so existing
    # offsite runners and saved profiles continue to work.
    candidates = [
        p["name"] for p in normalized if p.get("offsite_candidate", False)
    ]
    offsite = config.get("offsite")
    if not isinstance(offsite, dict):
        offsite = {}
        config["offsite"] = offsite
    offsite["offsite_pools"] = candidates

    save_config(config)


def get_checkagainst(config):
    entries = config.get("checkagainst")
    if entries is None:
        entries = []
        config["checkagainst"] = entries
    return entries


def save_checkagainst(config, entries):
    config["checkagainst"] = [dict(e) for e in entries]
    save_config(config)


def get_archive_path(config):
    return config.get("archive_path", "")


def save_archive_path(config, path):
    config["archive_path"] = path
    save_config(config)


DEFAULT_RETENTION = [
    {"name": "d", "retain": 3, "minage": 0},
    {"name": "w", "retain": 2, "minage": 0},
    {"name": "m", "retain": 2, "minage": 0},
    {"name": "s", "retain": 4, "minage": 65},
]


def get_all_retention(config):
    retention = config.get("retention")
    if not isinstance(retention, dict):
        retention = {}
        config["retention"] = retention
    if "default" not in retention:
        retention["default"] = [dict(b) for b in DEFAULT_RETENTION]
    return retention


def get_retention(config, pool):
    retention = get_all_retention(config)
    buckets = retention.get(pool)
    if not buckets:
        buckets = retention.get("default") or DEFAULT_RETENTION
    return [dict(b) for b in buckets]


def save_retention(config, pool, buckets):
    retention = get_all_retention(config)
    retention[pool] = [dict(b) for b in buckets]
    config["retention"] = retention
    save_config(config)


def get_prune_label(config):
    """Return the global retention prune label, defaulting to dailybackup."""
    return config.get("prune_label", "dailybackup")


def save_prune_label(config, label):
    """Persist the global retention prune label."""
    config["prune_label"] = label
    save_config(config)


def get_prune_pools_order(config):
    """Return the persisted order of pools in the Retention Prune list."""
    order = config.get("prune_pools_order")
    if not isinstance(order, list):
        return []
    return [str(p) for p in order]


def save_prune_pools_order(config, order):
    """Persist the Retention Prune list order."""
    config["prune_pools_order"] = [str(p) for p in order]
    save_config(config)


def import_legacy_retention(config, parent_dir):
    """One-time migration: scan parent_dir for zfsretainpol-* files and add
    missing pools to config['retention']. Returns list of imported pools."""
    from legacy_retention import scan_legacy_retention
    retention = get_all_retention(config)
    imported = scan_legacy_retention(parent_dir, retention)
    if imported:
        config["retention"] = retention
    return imported


SCRUB_MANAGER_DEFAULTS = {
    "simultaneous": 1,
    "refresh_seconds": 10,
    "system_scrub_weekly": False,
    "system_scrub_monthly": False,
}


def get_scrub_manager_config(config):
    """Return the scrub manager config dict, creating defaults if absent."""
    scrub = config.get("scrub_manager")
    if not isinstance(scrub, dict):
        scrub = _deep_copy(SCRUB_MANAGER_DEFAULTS)
        config["scrub_manager"] = scrub
    for key, default_val in SCRUB_MANAGER_DEFAULTS.items():
        if key not in scrub:
            scrub[key] = default_val
    return scrub


def save_scrub_manager_config(config, scrub_data):
    """Store scrub manager config and persist to disk."""
    config["scrub_manager"] = dict(scrub_data)
    save_config(config)


SCRUB_STATE_PATH = "/root/.config/zfsutilities/scrub_state.json"


def load_scrub_state():
    """Load scrub queue state from disk."""
    defaults = {
        "pending": [],
        "active": [],
        "paused": [],
        "finished": [],
        "target": 1,
    }
    if not os.path.exists(SCRUB_STATE_PATH):
        return dict(defaults)
    try:
        with scrub_state_lock_read():
            with open(SCRUB_STATE_PATH, "r") as f:
                data = json.load(f)
        for key in defaults:
            if key not in data:
                data[key] = defaults[key]
        return data
    except (json.JSONDecodeError, OSError):
        return dict(defaults)


def save_scrub_state(state):
    """Persist scrub queue state to disk."""
    os.makedirs(os.path.dirname(SCRUB_STATE_PATH), exist_ok=True)
    try:
        with scrub_state_lock_write():
            with open(SCRUB_STATE_PATH, "w") as f:
                json.dump(state, f, indent=2)
    except OSError:
        pass


SNAPFILE = "/root/.config/zfsutilities_nextsnap"
OFFSITE_SNAPFILE = "/root/.config/zfsutilities_offsite_nextsnap"
SNAPNAME_LOCK = "/run/lock/zfs/.snapname.lock"
SNAPNAME_RESERVED = "/run/lock/zfs/.snapname.reserved"
SNAPNAME_RESERVE_SECONDS = 60


def _read_snapfile(path):
    try:
        if os.path.exists(path):
            with open(path) as f:
                name = f.read().strip()
            if name:
                return name
    except OSError:
        pass
    return None


def _write_snapfile(path, name):
    try:
        with open(path, 'w') as f:
            f.write(name)
    except OSError:
        pass


def _remove_snapfile(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _ensure_snapname_dirs():
    """Create the directory that holds snapshot-name lock/reservation files."""
    try:
        os.makedirs(os.path.dirname(SNAPNAME_LOCK), exist_ok=True)
    except OSError:
        pass


@contextmanager
def _snapname_lock():
    """Acquire the global snapshot-name generation lock."""
    _ensure_snapname_dirs()
    fd = -1
    try:
        fd = os.open(SNAPNAME_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fd >= 0:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass


def _load_reservations():
    """Load the snapshot-name reservation file.

    Returns a dict mapping snapshot name to the epoch seconds when it was
    reserved. Stale entries are dropped.
    """
    reservations = {}
    if not os.path.exists(SNAPNAME_RESERVED):
        return reservations
    cutoff = time.time() - SNAPNAME_RESERVE_SECONDS
    try:
        with open(SNAPNAME_RESERVED, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        reserved_at = int(parts[1])
                    except ValueError:
                        continue
                    if reserved_at >= cutoff:
                        reservations[parts[0]] = reserved_at
    except OSError:
        pass
    return reservations


def _save_reservations(reservations):
    """Write the snapshot-name reservation file."""
    _ensure_snapname_dirs()
    try:
        with open(SNAPNAME_RESERVED, "w", encoding="utf-8") as f:
            for name, reserved_at in reservations.items():
                f.write(f"{name} {reserved_at}\n")
    except OSError:
        pass


def _reserve_snapshot_name_unlocked(name):
    """Record a snapshot name as reserved for one minute.

    Caller must already hold the snapshot-name lock. The reservation file is
    line-based so it can be shared with the bash zfssnapbuild implementation.
    """
    reservations = _load_reservations()
    reservations[name] = int(time.time())
    _save_reservations(reservations)


def _reserve_snapshot_name(name):
    """Record a snapshot name as reserved for one minute."""
    with _snapname_lock():
        _reserve_snapshot_name_unlocked(name)


def _is_snapshot_name_reserved(name):
    """Return True if *name* is still reserved (within the last minute)."""
    with _snapname_lock():
        reservations = _load_reservations()
        reserved_at = reservations.get(name)
        if reserved_at is None:
            return False
        if time.time() - reserved_at <= SNAPNAME_RESERVE_SECONDS:
            return True
        del reservations[name]
        _save_reservations(reservations)
        return False


def save_snapshot_name(name):
    _write_snapfile(SNAPFILE, name)


def remove_snapfile():
    _remove_snapfile(SNAPFILE)


def _build_snapshot_name(label):
    now = datetime.now().astimezone()
    datestr = now.strftime("%Y-%m-%dT%H:%M%z")
    datestr = datestr[:-2] + ":" + datestr[-2:]
    day_of_week = now.strftime("%a")
    day_of_month = now.strftime("%d")
    bucket = "s" if label == "offsite" else ("m" if day_of_month == "01" else ("w" if day_of_week == "Sun" else "d"))
    return f"@{label}-{datestr}-{bucket}"


def generate_snapshot_name(label="dailybackup"):
    with _snapname_lock():
        name = _build_snapshot_name(label)
        _reserve_snapshot_name_unlocked(name)
    save_snapshot_name(name)
    return name


def save_offsite_snapshot_name(name):
    _write_snapfile(OFFSITE_SNAPFILE, name)


def generate_offsite_snapshot_name():
    with _snapname_lock():
        name = _build_snapshot_name("offsite")
        _reserve_snapshot_name_unlocked(name)
    save_offsite_snapshot_name(name)
    return name
