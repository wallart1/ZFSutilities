"""Persistent index of session-log metadata.

Stores a JSON file alongside the session logs so the Logs tab does not
need to re-read every historical log file on startup or refresh.
"""

import json
import os
import re
import tempfile
import time

from config_core import SESSION_LOG_DIR
from logging_config import log_msg, parse_msg_level, MSG_LEVELS

def index_file():
    """Return the path to the persistent log index file."""
    return os.path.join(SESSION_LOG_DIR, ".log_index.json")

# Regex: # END: (?:rc=(\d+)|cancelled), duration=([\d.]+)s(?:, bytes=(\d+))?
# Purpose: Parse the structured trailer written by BackupRunner and
#          profile_runner to extract result code, duration, and bytes.
_TRAILER_RE = re.compile(
    r"# END: (?:rc=(\d+)|cancelled), duration=([\d.]+)s(?:, bytes=(\d+))?"
)

_MSG_PRIORITY = {level: i for i, level in enumerate(MSG_LEVELS)}


def _key(path):
    """Return the index key for a log file path (basename)."""
    return os.path.basename(path)


def _load_index_data():
    """Load raw index data from disk, returning an empty dict on error."""
    path = index_file()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError) as e:
        log_msg(f"WARN: Could not load log index: {e}")
    return {}


def _save_index_data(data):
    """Atomically write raw index data to disk."""
    if not os.path.isdir(SESSION_LOG_DIR):
        return
    final_path = index_file()
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=SESSION_LOG_DIR, prefix=".log_index_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp_path, final_path)
    except OSError as e:
        log_msg(f"WARN: Could not save log index: {e}")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _status_from_trailer(rc_str):
    """Map a trailer rc string to a log-list status."""
    if rc_str is None:
        return "Cancelled"
    if rc_str == "0":
        return "Done"
    return "Failed"


def _empty_entry():
    """Return a fresh index entry with default values."""
    return {
        "size": 0,
        "mtime": 0.0,
        "status": "Done",
        "duration": None,
        "bytes_transferred": None,
        "highest_level": None,
        "has_trailer": False,
    }


def _parse_lines(text):
    """Split *text* into complete lines, returning (lines, consumed_bytes).

    Any trailing fragment after the final newline is left unprocessed so a
    partial last line can be consumed on the next update.
    """
    if not text:
        return [], 0
    last_newline = text.rfind("\n")
    if last_newline == -1:
        return [], 0
    return text[:last_newline].splitlines(), last_newline + 1


def _update_entry_from_text(entry, text):
    """Parse *text* and update level/trailer fields in *entry*."""
    highest_priority = _MSG_PRIORITY.get(entry.get("highest_level"), -1)

    lines, _consumed = _parse_lines(text)
    for line in lines:
        if entry.get("has_trailer"):
            break

        level = parse_msg_level(line)
        if level is not None and _MSG_PRIORITY[level] > highest_priority:
            entry["highest_level"] = level
            highest_priority = _MSG_PRIORITY[level]
            if level == "FATAL":
                # No higher level exists; we can stop scanning for levels,
                # but we still want to see the trailer if it appears later.
                pass

        m = _TRAILER_RE.search(line)
        if m:
            entry["has_trailer"] = True
            entry["status"] = _status_from_trailer(m.group(1))
            entry["duration"] = float(m.group(2))
            if m.group(3):
                entry["bytes_transferred"] = int(m.group(3))
            break


def scan_file(path):
    """Scan a log file and return a complete index entry.

    This is the cold-path fallback used when no index entry exists yet or
    when a file has been truncated.
    """
    entry = _empty_entry()
    if not os.path.isfile(path):
        return entry

    try:
        entry["size"] = os.path.getsize(path)
        entry["mtime"] = os.path.getmtime(path)
    except OSError:
        return entry

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return entry

    _update_entry_from_text(entry, text)

    if not entry.get("has_trailer") and time.time() - entry["mtime"] < 10:
        entry["status"] = "Running"

    return entry


def update_entry_incrementally(entry, path):
    """Update *entry* by reading only bytes appended since entry['size'].

    Returns the updated entry. The entry is modified in place.
    """
    try:
        new_size = os.path.getsize(path)
        new_mtime = os.path.getmtime(path)
    except OSError:
        return entry

    if new_size < entry.get("size", 0):
        # File shrank — reset and rescan.
        return scan_file(path)

    if new_size == entry.get("size", 0):
        entry["mtime"] = new_mtime
        return entry

    start = entry.get("size", 0)
    try:
        with open(path, "rb") as fh:
            fh.seek(start)
            data = fh.read(new_size - start)
    except OSError:
        return entry

    text = data.decode("utf-8", errors="replace")
    lines, consumed = _parse_lines(text)

    # Process complete lines; leave a trailing fragment for next time.
    _update_entry_from_text(entry, text)

    entry["size"] = start + consumed
    entry["mtime"] = new_mtime

    if not entry.get("has_trailer") and time.time() - new_mtime >= 10:
        entry["status"] = "Done"

    return entry


class LogIndex:
    """Persistent index of session-log metadata."""

    def __init__(self, data=None):
        self._data = data if data is not None else {}
        self._dirty = False

    @classmethod
    def load(cls):
        """Load the index from disk."""
        return cls(_load_index_data())

    def save(self):
        """Persist the index if it has changed."""
        if self._dirty:
            _save_index_data(self._data)
            self._dirty = False

    def get(self, path):
        """Return the entry for *path*, or None."""
        return self._data.get(_key(path))

    def _set(self, path, entry):
        """Store *entry* for *path* and mark the index dirty."""
        self._data[_key(path)] = entry
        self._dirty = True

    def remove(self, path):
        """Remove the entry for *path*."""
        key = _key(path)
        if key in self._data:
            del self._data[key]
            self._dirty = True

    def update(self, path):
        """Create or incrementally update the entry for *path*.

        Returns the resulting entry.
        """
        entry = self.get(path)
        if entry is None:
            entry = scan_file(path)
        else:
            entry = update_entry_incrementally(entry, path)
        self._set(path, entry)
        return entry

    def set_status(self, path, status, duration=None, bytes_transferred=None):
        """Set the final status for a log (used by runners after trailer).

        The index entry is created from disk if absent. The caller is still
        responsible for scanning the log later to discover the highest level.
        """
        entry = self.get(path)
        if entry is None:
            entry = scan_file(path)
        entry["status"] = status
        if duration is not None:
            entry["duration"] = duration
        if bytes_transferred is not None:
            entry["bytes_transferred"] = bytes_transferred
        self._set(path, entry)

    def remove_missing(self, existing_paths):
        """Remove entries whose files are no longer in *existing_paths*."""
        existing_keys = {_key(p) for p in existing_paths}
        for key in list(self._data.keys()):
            if key not in existing_keys:
                del self._data[key]
                self._dirty = True
