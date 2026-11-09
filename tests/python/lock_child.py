"""Fresh-interpreter lock-holder helpers for the cross-process test suites.

Usage (run with sys.executable):

  lock_child.py flock <lock_path> <ex|sh> <held_marker> <release_marker>
      flock() the path, write the held marker, poll until the release
      marker appears, unlock, exit 0.

  lock_child.py profile-hold <lock_dir> <profile> <held_marker> <released_marker>
      acquire profile_runner's per-profile lock (the acquired path goes
      into the held marker's content), hold it for 0.5s — the window the
      parent's blocked acquire must overlap — then release and write the
      released marker.

  lock_child.py history-add <history_path> <lock_path> <entry_name>
      append one backup_history entry through the history write lock.

The lock holder must never be a multiprocessing fork of the pytest-xdist
worker: a forked child of a loaded worker can deadlock in inherited locks
before it reaches its first queue.put() (CI 2026-11-08..09, both daily
runs at a commit that had been green the day before; same class seen once
on the dev host under load). A fresh interpreter has no inherited state,
needs no picklable target, and a crash is visible immediately through its
exit status.
"""

import fcntl
import os
import sys
import time
from datetime import datetime, timezone

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")

POLL_SECONDS = 0.01


def _wait_for_marker(path):
    while not os.path.exists(path):
        time.sleep(POLL_SECONDS)


def _flock(argv):
    lock_path, mode, held_marker, release_marker = argv
    flag = fcntl.LOCK_EX if mode == "ex" else fcntl.LOCK_SH
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, flag)
        with open(held_marker, "w") as marker:
            marker.write("held")
        _wait_for_marker(release_marker)
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _profile_hold(argv):
    lock_dir, profile, held_marker, released_marker = argv
    if PYTHON_SRC not in sys.path:
        sys.path.insert(0, PYTHON_SRC)
    import profile_runner

    profile_runner.PROFILE_LOCK_DIR = lock_dir
    fd, path = profile_runner.acquire_profile_lock(profile, timeout=0.5)
    if fd is None:
        print(f"acquire_profile_lock({profile!r}) timed out", file=sys.stderr)
        raise SystemExit(3)
    try:
        with open(held_marker, "w") as marker:
            marker.write(path)
        # Hold window the parent's blocked acquire must overlap to observe
        # the handoff — the in-process closure always held it this long.
        time.sleep(0.5)
    finally:
        profile_runner.release_profile_lock(fd, path)
    with open(released_marker, "w") as marker:
        marker.write("released")


def _history_add(argv):
    history_path, lock_path, name = argv
    if PYTHON_SRC not in sys.path:
        sys.path.insert(0, PYTHON_SRC)
    import backup_history
    import file_locking

    backup_history.HISTORY_PATH = history_path
    file_locking.HISTORY_LOCK_PATH = lock_path
    entry = backup_history.build_entry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        run_type="backup",
        name=name,
        duration=1.0,
        result="success",
    )
    backup_history.add_history_entry(entry)


_MODES = {
    "flock": (_flock, 4),
    "profile-hold": (_profile_hold, 4),
    "history-add": (_history_add, 3),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in _MODES:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    handler, argc = _MODES[sys.argv[1]]
    args = sys.argv[2:]
    if len(args) != argc:
        print(
            f"usage: lock_child.py {sys.argv[1]} (got {len(args)} args, need {argc})",
            file=sys.stderr,
        )
        return 2
    handler(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
