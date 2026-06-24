"""Backup history / metrics tracking.

Stores per-run metrics (duration, bytes transferred, success/failure) in a
dedicated JSON file separate from the main configuration.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone

HISTORY_PATH = "/root/.config/zfsutilities-history.json"

# Regex: ^(\d+(?:\.\d+)?)\s*([kKMGTPE]?(?:i?B)?)$
# Purpose: Parse a human-readable byte size string into a numeric value.
# Group 1: Numeric quantity   e.g. "1.23", "512"
# Group 2: Unit suffix        e.g. "B", "KB", "KiB", "MB", "MiB", "GB", "GiB", "TB", "TiB",
#                             or bare SI suffixes "K", "M", "G", "T", "P", "E"
# Examples:
#   "312B"      -> match
#   "1.23GiB"   -> match
#   "5.00M"     -> match
#   "10MB"      -> match
#   "hello"     -> no match
_HUMAN_SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([kKMGTPE]?(?:i?B)?)$")

# Multiplier lookup for size suffixes.
# SI units (KB, MB, GB, TB) use powers of 1000.
# IEC units (KiB, MiB, GiB, TiB) use powers of 1024.
# Bare 'B' or 'K'/'M'/'G'/'T' without 'i' are treated as SI for compatibility with
# zfs receive output (which may use either convention).
_SIZE_MULTIPLIERS = {
    "B": 1,
    "K": 1000, "KB": 1000,
    "KiB": 1024,
    "M": 1000 ** 2, "MB": 1000 ** 2,
    "MiB": 1024 ** 2,
    "G": 1000 ** 3, "GB": 1000 ** 3,
    "GiB": 1024 ** 3,
    "T": 1000 ** 4, "TB": 1000 ** 4,
    "TiB": 1024 ** 4,
    "P": 1000 ** 5, "PB": 1000 ** 5,
    "PiB": 1024 ** 5,
    "E": 1000 ** 6, "EB": 1000 ** 6,
    "EiB": 1024 ** 6,
}


def _parse_human_size(size_str):
    """Convert a human-readable size like '1.23GiB', '312B', or '319M' to bytes (int).

    Bare SI suffixes (e.g. '319M', '11.2G') are treated as base-1000 units to
    match zfs receive output conventions.

    Returns 0 if the string cannot be parsed.
    """
    if not size_str:
        return 0
    size_str = size_str.strip()
    m = _HUMAN_SIZE_RE.match(size_str)
    if not m:
        return 0
    value = float(m.group(1))
    unit = m.group(2)
    if not unit or unit == 'B':
        multiplier = 1
    elif unit in ('k', 'K', 'M', 'G', 'T', 'P', 'E'):
        # Bare SI suffixes from zfs receive (e.g. "319M", "11.2G")
        multiplier = _SIZE_MULTIPLIERS.get(unit.upper() + 'B', 1)
    else:
        multiplier = _SIZE_MULTIPLIERS.get(unit, 1)
    return int(value * multiplier)


def format_duration(seconds):
    """Convert a float duration in seconds to an HH:MM:SS string.

    Examples:
        0      -> "00:00:00"
        61.5   -> "00:01:02"
        3665.0 -> "01:01:05"
    """
    if seconds is None or seconds < 0:
        seconds = 0
    total = int(round(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def load_history():
    """Load the history list from HISTORY_PATH.

    Returns an empty list if the file does not exist or is unreadable.
    """
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_history(entries):
    """Write the history list to HISTORY_PATH atomically.

    Writes to a temporary file in the same directory and renames it to
    avoid corrupting an existing history file on crash or power loss.
    """
    config_dir = os.path.dirname(HISTORY_PATH)
    os.makedirs(config_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=config_dir, prefix=".zfsutilities-history-")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(entries, fh, indent=2)
        os.replace(temp_path, HISTORY_PATH)
    except OSError:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def prune_history(entries, days):
    """Return a new list with entries older than `days` removed.

    `entries` is expected to be a list of dicts with an ISO-format
    "timestamp" key.  The list is returned newest-first.
    """
    if days <= 0:
        return entries
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    pruned = []
    for e in entries:
        ts_str = e.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts.timestamp() >= cutoff:
                pruned.append(e)
        except ValueError:
            # Unparseable timestamp — keep it to avoid data loss
            pruned.append(e)
    return pruned


def add_history_entry(entry):
    """Append a new entry to the history file and prune old entries.

    `entry` should be a dict with at least:
        timestamp, type, name, duration, result, bytes_transferred

    Pruning uses the default retention of 90 days if no explicit
    retention is configured elsewhere.
    """
    entries = load_history()
    entries.insert(0, entry)
    # Default to 90 days if we cannot read a config value here.
    # Callers that know the configured retention can call prune_history
    # themselves before save_history.
    entries = prune_history(entries, 90)
    save_history(entries)


def get_success_rate(entries, days):
    """Compute success rate for entries within the last `days`.

    Returns a tuple (success_count, total_count, percentage).
    `percentage` is an integer 0–100.  If there are no entries,
    returns (0, 0, 0).
    """
    if days <= 0:
        pruned = entries
    else:
        pruned = prune_history(entries, days)
    total = len(pruned)
    if total == 0:
        return 0, 0, 0
    success = sum(
        1 for e in pruned if e.get("result") == "success"
    )
    percent = int((success / total) * 100)
    return success, total, percent


def get_recent_entries(entries, limit):
    """Return up to `limit` newest entries."""
    return entries[:limit]


def build_entry(timestamp, run_type, name, duration, result,
                bytes_transferred=0, log_file=None):
    """Construct a standard history entry dict.

    All callers should use this helper to ensure a consistent schema.
    """
    entry = {
        "timestamp": timestamp,
        "type": run_type,
        "name": name,
        "duration": duration,
        "result": result,
        "bytes_transferred": bytes_transferred,
    }
    if log_file:
        entry["log_file"] = log_file
    return entry
