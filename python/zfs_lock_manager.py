"""Python client for the ZFS dataset lock manager.

This module reads and writes the same JSON lock files as the bash
`zfslockmanager` so that Python GUI operations can participate in the same
hierarchical locking scheme.  Locks are stored under `/run/lock/zfs/` by
default; the base directory can be overridden with the `ZFSLOCK_DIR`
environment variable for testing.
"""

import glob
import json
import os
import sys
import tempfile
import threading
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timezone

from backup_config import log_msg

# ---------------------------------------------------------------------------
# Constants and module state
# ---------------------------------------------------------------------------

ZFSLOCK_DIR = os.environ.get("ZFSLOCK_DIR", "/run/lock/zfs")
ZFSLOCK_LOCKS_DIR = os.path.join(ZFSLOCK_DIR, ".locks")
ZFSLOCK_PIDS_DIR = os.path.join(ZFSLOCK_DIR, ".pids")

# Refcounts for locks held by this process.  A lock may be acquired more than
# once (e.g. nested context managers); the file is removed only when the last
# reference is released.
_lock_refcounts: dict = {}
_refcount_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
    """Create lock directories if they do not exist."""
    for path in (ZFSLOCK_LOCKS_DIR, ZFSLOCK_PIDS_DIR):
        os.makedirs(path, exist_ok=True)


def _encode(path: str) -> str:
    """URL-encode a dataset path for safe use as a filename."""
    path = path.replace("/", "%2F")
    path = path.replace("@", "%40")
    return path


def _lock_file(dataset: str) -> str:
    """Return the lock file path for *dataset*."""
    return os.path.join(ZFSLOCK_LOCKS_DIR, f"{_encode(dataset)}.lock")


def _pid_file(pid: int | None = None) -> str:
    """Return the PID tracking file path for this or the given process."""
    return os.path.join(ZFSLOCK_PIDS_DIR, str(pid or os.getpid()))


def _script_name() -> str:
    """Return the basename of the running script, mirroring bash behavior."""
    return os.path.basename(sys.argv[0]) if sys.argv else "python"


def _read_field(lockfile: str, field: str) -> str | None:
    """Read a string field from a lock file."""
    if not os.path.isfile(lockfile):
        return None
    try:
        with open(lockfile, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    value = data.get(field)
    return str(value) if value is not None else None


def _read_pid(lockfile: str) -> int | None:
    """Read the pid field from a lock file as an integer."""
    raw = _read_field(lockfile, "pid")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _types_conflict(type1: str, type2: str) -> bool:
    """Return True if two lock types conflict at the same dataset level."""
    if type1 == "r":
        return type2 in ("w", "x")
    if type1 in ("w", "x"):
        return type2 in ("r", "w", "x")
    return False


def _hierarchy_conflict(requested: str, existing: str, relationship: str) -> bool:
    """Return True if *existing* lock blocks *requested* via hierarchy."""
    if relationship == "same":
        return _types_conflict(requested, existing)

    if relationship == "ancestor":
        # Existing lock is on an ancestor of the requested dataset.
        if existing == "x":
            return True
        if existing == "w":
            return requested in ("w", "x")
        if existing == "r":
            return requested == "x"
        return False

    if relationship == "descendant":
        # Existing lock is on a descendant of the requested dataset.
        if requested == "x":
            return True
        if requested == "w":
            return existing in ("w", "x")
        if requested == "r":
            return existing == "x"
        return False

    return False


def _is_stale(lockfile: str) -> bool:
    """Return True if *lockfile* is stale and can be removed."""
    if not os.path.isfile(lockfile):
        return True

    pid = _read_pid(lockfile)
    if pid is None:
        return True

    try:
        os.kill(pid, 0)
    except OSError:
        return True

    script = _read_field(lockfile, "script")
    if script is None:
        return False  # Cannot verify; leave it alone.

    cmdline_path = f"/proc/{pid}/cmdline"
    if not os.path.isfile(cmdline_path):
        return False
    try:
        with open(cmdline_path, "rb") as f:
            cmdline = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return False

    # A live process may have an empty cmdline briefly after fork (before the
    # new program's argv is visible in /proc). Treat an empty/unreadable cmdline
    # as inconclusive and leave the lock alone; only mark stale when we can read
    # a non-empty cmdline and the script is definitively absent.
    if not cmdline.strip():
        return False

    return script not in cmdline


def _cleanup_stale() -> int:
    """Remove all stale lock files and return the count removed."""
    removed = 0
    if not os.path.isdir(ZFSLOCK_LOCKS_DIR):
        return removed
    for lockfile in glob.glob(os.path.join(ZFSLOCK_LOCKS_DIR, "*.lock")):
        if _is_stale(lockfile):
            try:
                os.unlink(lockfile)
                removed += 1
            except OSError:
                pass

    if os.path.isdir(ZFSLOCK_PIDS_DIR):
        for pidfile in glob.glob(os.path.join(ZFSLOCK_PIDS_DIR, "*")):
            try:
                pid = int(os.path.basename(pidfile))
                os.kill(pid, 0)
            except (ValueError, OSError):
                try:
                    os.unlink(pidfile)
                except OSError:
                    pass

    return removed


def _check_file(lockfile: str, requested_type: str, relationship: str) -> bool:
    """Return False if *lockfile* blocks *requested_type*, True otherwise."""
    if not os.path.isfile(lockfile):
        return True

    existing_type = _read_field(lockfile, "type")
    if existing_type is None:
        return True

    return not _hierarchy_conflict(requested_type, existing_type, relationship)


def _ancestors(dataset: str) -> list[str]:
    """Return ancestor dataset paths from immediate parent up to the pool."""
    ancestors = []
    parent = dataset
    while "/" in parent:
        parent = parent.rsplit("/", 1)[0]
        ancestors.append(parent)
    return ancestors


def _pool(dataset: str) -> str | None:
    """Return the pool component of a dataset, or None for a pool itself."""
    if "/" in dataset:
        return dataset.split("/", 1)[0]
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check(dataset: str, lock_type: str) -> bool:
    """Return True if *lock_type* can be acquired on *dataset*.

    This cleans up stale locks first, then checks the target dataset, its
    ancestors, and its descendants.
    """
    if not dataset or lock_type not in ("r", "w", "x"):
        log_msg("WARN: zfs_lock_manager.check requires dataset and valid type")
        return False

    _cleanup_stale()

    # Same dataset.
    if not _check_file(_lock_file(dataset), lock_type, "same"):
        return False

    # Ancestors.
    for ancestor in _ancestors(dataset):
        if not _check_file(_lock_file(ancestor), lock_type, "ancestor"):
            return False

    # Pool ancestor (redundant for non-dataset pools, but matches bash).
    pool = _pool(dataset)
    if pool and not _check_file(_lock_file(pool), lock_type, "ancestor"):
        return False

    # Descendants.
    prefix = os.path.join(ZFSLOCK_LOCKS_DIR, f"{_encode(dataset)}%2F*.lock")
    for lockfile in glob.glob(prefix):
        if not _check_file(lockfile, lock_type, "descendant"):
            return False

    return True


def list_active_locks() -> list[dict]:
    """Return all currently active ZFS dataset locks.

    Reads ``ZFSLOCK_LOCKS_DIR/*.lock``, parses each JSON lock file, and
    skips stale entries (owner PID is dead).  Returns a list of dicts
    with keys: dataset, type, pid, script, acquired, description.
    """
    locks: list[dict] = []
    if not os.path.isdir(ZFSLOCK_LOCKS_DIR):
        return locks

    for lock_path in glob.glob(os.path.join(ZFSLOCK_LOCKS_DIR, "*.lock")):
        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue

        pid = data.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            continue

        try:
            os.kill(pid, 0)
        except OSError:
            continue

        dataset = data.get("dataset")
        if not dataset:
            encoded_name = os.path.basename(lock_path)[:-5]
            dataset = urllib.parse.unquote(encoded_name)

        locks.append(
            {
                "dataset": dataset,
                "type": data.get("type", ""),
                "pid": pid,
                "script": data.get("script", ""),
                "acquired": data.get("acquired", ""),
                "description": data.get("description", ""),
            }
        )

    locks.sort(key=lambda lock: (lock["dataset"], lock["type"], lock["pid"]))
    return locks


def acquire(dataset: str, lock_type: str, description: str = "") -> str:
    """Acquire a lock on *dataset*.

    Returns the lock file path (lock_id) on success.  Raises RuntimeError on
    conflict or error.
    """
    if not dataset or lock_type not in ("r", "w", "x"):
        raise RuntimeError("zfs_lock_manager.acquire requires dataset and valid type")

    _ensure_dirs()
    _cleanup_stale()

    lockfile = _lock_file(dataset)

    # Re-entry: same PID already holds this lock.
    existing_pid = _read_pid(lockfile)
    if existing_pid == os.getpid():
        with _refcount_lock:
            if lockfile in _lock_refcounts:
                _lock_refcounts[lockfile] += 1
                return lockfile
        # File exists but we lost the refcount; treat as fresh acquisition.

    if not check(dataset, lock_type):
        raise RuntimeError(f"conflict: cannot acquire {lock_type} lock on {dataset}")

    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    data = {
        "dataset": dataset,
        "type": lock_type,
        "pid": os.getpid(),
        "script": _script_name(),
        "acquired": timestamp,
        "description": description,
    }

    try:
        # Write to a temp file and rename it into place so that other
        # processes never see a partially-written (empty/truncated) lock file.
        lock_dir = os.path.dirname(lockfile)
        fd, tmp_path = tempfile.mkstemp(dir=lock_dir, prefix=".lock-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
                f.write("\n")
            os.replace(tmp_path, lockfile)
        except OSError:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise RuntimeError(f"failed to write lock file {lockfile}: {exc}") from exc

    pidfile = _pid_file()
    try:
        with open(pidfile, "a", encoding="utf-8") as f:
            f.write(f"{lockfile}\n")
    except OSError as exc:
        # Best-effort tracking; do not fail the acquisition.
        log_msg(f"WARN: failed to update pidfile {pidfile}: {exc}")

    with _refcount_lock:
        _lock_refcounts[lockfile] = _lock_refcounts.get(lockfile, 0) + 1

    return lockfile


def acquire_multiple(lock_type: str, datasets: list[str]) -> list[str]:
    """Acquire locks on multiple datasets in a deadlock-free order.

    Datasets are sorted by path depth then lexicographically, redundant
    ancestors are removed, and all locks are acquired.  If any acquisition
    fails, all locks acquired so far are released and an exception is raised.
    """
    if not datasets:
        return []

    # Sort by depth then lexicographically.
    sorted_datasets = sorted(datasets, key=lambda ds: (ds.count("/"), ds))

    # Remove duplicates.
    unique = []
    seen = set()
    for ds in sorted_datasets:
        if ds not in seen:
            seen.add(ds)
            unique.append(ds)

    # Remove ancestor paths that have a descendant also requested, keeping
    # only the most specific (deepest) datasets.  This matches the bash
    # zfslock_acquire_multiple behavior.
    kept = []
    n = len(unique)
    for i, ds in enumerate(unique):
        redundant = False
        for j in range(i + 1, n):
            if unique[j] == ds or unique[j].startswith(ds + "/"):
                redundant = True
                break
        if not redundant:
            kept.append(ds)

    acquired: list[str] = []
    try:
        for ds in kept:
            lock_id = acquire(ds, lock_type)
            acquired.append(lock_id)
    except RuntimeError:
        for lock_id in acquired:
            release(lock_id)
        raise

    return acquired


def release(lock_id: str) -> bool:
    """Release a lock by its lock file path.

    Returns True on success or if the lock was already released.  Returns
    False if the lock is owned by another process.
    """
    if not lock_id:
        log_msg("WARN: zfs_lock_manager.release requires a lock_id")
        return False

    if lock_id.startswith("REENTRY:"):
        return True

    if not os.path.isfile(lock_id):
        with _refcount_lock:
            _lock_refcounts.pop(lock_id, None)
        return True

    lock_pid = _read_pid(lock_id)
    if lock_pid is not None and lock_pid != os.getpid():
        log_msg(f"WARN: cannot release lock owned by PID {lock_pid} (we are {os.getpid()})")
        return False

    with _refcount_lock:
        refcount = _lock_refcounts.get(lock_id, 1)
        if refcount > 1:
            _lock_refcounts[lock_id] = refcount - 1
            return True
        _lock_refcounts.pop(lock_id, None)

    try:
        os.unlink(lock_id)
    except OSError as exc:
        log_msg(f"WARN: failed to remove lock file {lock_id}: {exc}")
        return False

    pidfile = _pid_file()
    if os.path.isfile(pidfile):
        try:
            with open(pidfile, "r", encoding="utf-8") as f:
                lines = [line for line in f.read().splitlines() if line != lock_id]
            if lines:
                with open(pidfile, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            else:
                os.unlink(pidfile)
        except OSError as exc:
            log_msg(f"WARN: failed to update pidfile {pidfile}: {exc}")

    return True


@contextmanager
def lock(dataset: str, lock_type: str, description: str = ""):
    """Context manager that acquires and releases a single lock."""
    lock_id = acquire(dataset, lock_type, description)
    try:
        yield lock_id
    finally:
        release(lock_id)


@contextmanager
def locks(lock_type: str, datasets: list[str]):
    """Context manager that acquires and releases multiple locks."""
    lock_ids = acquire_multiple(lock_type, datasets)
    try:
        yield lock_ids
    finally:
        for lock_id in lock_ids:
            release(lock_id)
