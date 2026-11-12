# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

## Disks page: partition-member pools leave the disk row pool-less (2026-11-11)

- `DiskInventoryCache._pools_for_disk` (disks_page.py) matches a row only by
  exact realpath or exact basename. When a pool's members are partitions
  (by-id `-partN` leaves), the partition row gets the pool membership and
  the physical disk row gets none: the disk row's Pools column is blank,
  and selecting that disk row in the inventory takes the "belongs to no
  pool" branch — the pool selector and topology tints clear instead of
  following the disk's pool.
- Found during the topology-tint fix (which resolves members to backing
  disks for tinting only); out of scope there because it changes the Pools
  column data, a user-visible surface of its own.

---

## test-unarchive-vm: full-suite flake in the IQN-drift convergence test (2026-11-11)

- Full-suite run 2026-11-11 (0.141.0 wrap-up gate):
  `Test 31: Step 2 converges a drifted node.conf IQN_PREFIX onto the live tree`
  failed — `FATAL: Not a ZFS dataset on zteststor: <mock state>/archive_drift`,
  i.e. the SSH-stubbed `zfs list` did not report the staged archive dataset.
  The suite passed 43/43 alone immediately after, and the day's second full
  gate was fully green, so this is a one-off parallel-load race in the mock,
  not a steady failure. The retained per-suite log was empty.
- No working-tree change of this cycle touches `unarchive-vm` or its suite
  (the test itself dates to 0.129.0).

---

## zfsdailybackup: prune stage aborts under the script's own strict mode (2026-11-11)

- `bin/zfsdailybackup` runs under `set -euo pipefail` and calls
  `cleanup '' '' 'dailybackup'` with three arguments. `cleanup`
  (`bin/zfscleanup`) then reads `$4` bare (`if [[ $4 != '' ]]`), which
  aborts a `set -u` caller with "unbound variable". Verified by a
  semantics probe of that call shape; not reproduced end-to-end.
- The same path has more strict-caller hazards behind it: `cleanup` reads
  other optional globals bare, and `_zfscleanup_retain_loop` and
  `zfsretain` capture `$?` after bare calls, which `set -e` never reaches
  on a non-zero status.
- Found during the lock-conflict strict-caller fix. Unrelated to that
  failure: the GUI and profile prune payloads source `zfscleanup` into a
  non-strict shell, so only the legacy orchestrator is exposed.

---
