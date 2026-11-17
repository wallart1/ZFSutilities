# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

## test-unarchive-vm flakes under full-suite parallel load (2026-11-16)

- Full-suite run (115 suites) failed Test 6 ("Original VMID preserved when
  no conflict and no --new-vmid") with
  `FATAL: Not a ZFS dataset: /tmp/mock_zfs_state_766355/archive6`.
- Standalone rerun immediately after: 43/43 pass. Consistent with the known
  mock-zfs-state/existence-probe load-flake class under parallel workers,
  not with a product defect. Retained log: /tmp/zfsutilities-test-766355.log
  (from the failing run; full log /tmp/zfs-run.log).
- Second occurrence, same signature, 0.142.0 wrap-up with-soaks run:
  Test 25 ("Unknown METHOD value is fatal") failed with
  `FATAL: Not a ZFS dataset: /tmp/mock_zfs_state_1238942/archive12`;
  standalone rerun 43/43 pass (full log /tmp/zfs-run-soak.log, retained
  suite log /tmp/zfsutilities-test-1238942.log). Different test index, same
  mock-state existence-probe race — the suite passes whenever it is not
  racing the parallel workers.
