"""Advisory file locking helpers for shared JSON/state files.

Python callers use fcntl.flock context managers; bash callers can use the
system `flock` command on the same lock files. Lock files live under
/run/lock/zfs/ by default to match the snapshot-name lock convention.
"""

import fcntl
import os
import time
from contextlib import contextmanager


CONFIG_LOCK_PATH = os.environ.get(
    "ZFSUTILITIES_CONFIG_LOCK_PATH", "/run/lock/zfs/.config.lock"
)
HISTORY_LOCK_PATH = os.environ.get(
    "ZFSUTILITIES_HISTORY_LOCK_PATH", "/run/lock/zfs/.history.lock"
)
LOG_INDEX_LOCK_PATH = os.environ.get(
    "ZFSUTILITIES_LOG_INDEX_LOCK_PATH", "/run/lock/zfs/.log_index.lock"
)
SCRUB_STATE_LOCK_PATH = os.environ.get(
    "ZFSUTILITIES_SCRUB_STATE_LOCK_PATH", "/run/lock/zfs/.scrub_state.lock"
)


@contextmanager
def file_lock(path, lock_type, timeout=None):
    """Acquire an advisory flock on *path* and release it on exit.

    *lock_type* is fcntl.LOCK_SH for a shared (read) lock or
    fcntl.LOCK_EX for an exclusive (write) lock.

    If *timeout* is a positive number, retry with a short sleep and raise
    TimeoutError if the lock cannot be acquired in time. If *timeout* is None
    (the default), block until the lock is available.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = -1
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        if timeout is None:
            fcntl.flock(fd, lock_type)
        else:
            deadline = time.time() + max(0.0, float(timeout))
            acquired = False
            while time.time() < deadline:
                try:
                    fcntl.flock(fd, lock_type | fcntl.LOCK_NB)
                    acquired = True
                    break
                except (BlockingIOError, OSError):
                    time.sleep(0.01)
            if not acquired:
                raise TimeoutError(f"could not acquire lock on {path}")
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


@contextmanager
def config_lock_read():
    """Shared lock for reading the main JSON config."""
    with file_lock(CONFIG_LOCK_PATH, fcntl.LOCK_SH):
        yield


@contextmanager
def config_lock_write():
    """Exclusive lock for writing the main JSON config."""
    with file_lock(CONFIG_LOCK_PATH, fcntl.LOCK_EX):
        yield


@contextmanager
def history_lock_read():
    """Shared lock for reading the backup history file."""
    with file_lock(HISTORY_LOCK_PATH, fcntl.LOCK_SH):
        yield


@contextmanager
def history_lock_write():
    """Exclusive lock for writing the backup history file."""
    with file_lock(HISTORY_LOCK_PATH, fcntl.LOCK_EX):
        yield


@contextmanager
def log_index_lock_read():
    """Shared lock for reading the session-log index."""
    with file_lock(LOG_INDEX_LOCK_PATH, fcntl.LOCK_SH):
        yield


@contextmanager
def log_index_lock_write():
    """Exclusive lock for writing the session-log index."""
    with file_lock(LOG_INDEX_LOCK_PATH, fcntl.LOCK_EX):
        yield


@contextmanager
def scrub_state_lock_read():
    """Shared lock for reading the scrub queue state."""
    with file_lock(SCRUB_STATE_LOCK_PATH, fcntl.LOCK_SH):
        yield


@contextmanager
def scrub_state_lock_write():
    """Exclusive lock for writing the scrub queue state."""
    with file_lock(SCRUB_STATE_LOCK_PATH, fcntl.LOCK_EX):
        yield
