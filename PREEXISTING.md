# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

## zlm conflict-message xdist flake: descendant holder omitted under full-suite load (2026-11-11)

- `TestLocalConflictDetails::test_local_conflict_message_names_every_holder`
  (tests/python/test_zfs_lock_manager.py) failed in this repo's full gate:
  the conflict message names only the ancestor holder
  (`localpool/parent`), not the descendant (`localpool/parent/mid/leaf`).
  Passes standalone and file-wide on rerun (20/20). The task under way
  (GUI Settings menu) touched no lock-manager surface.
- Same failure seen twice in pub2 on 2026-11-11 and root-caused there
  from repo code: the test writes lock files naming freshly Popen'd
  `sleep` children; between fork and exec `/proc/<pid>/cmdline` still
  shows the parent's command line, so `_is_stale` in
  python/zfs_lock_manager.py (`script not in cmdline`) reaps the
  descendant's lock as stale. pytest-xdist load stretches that window.
  Production never hits this shape (holders write their own records
  while already running).
- Known fix (test-side, awaiting user cue): before writing each lock
  file, poll `/proc/<pid>/cmdline` until it contains `sleep`. Wholesale
  test serialization was advised against and is not wanted.
