# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (test collision, concurrent full runs, found 2026-10-26): two
  `tests/run-tests --with-soak` runs executing at the same time fail
  test-sever-vm-clone in BOTH runs (3 tests each: unexpected exit 1,
  missing --continue state file, rollback rc=1). Root cause: the
  product builds its state file at bin/sever-vm-clone:711 as
  `/tmp/sever-vm-clone-${key}-$(date +%s).state` — real epoch seconds,
  no pid — so two instances severing the same VM id within the same
  second share one file and each instance's rollback / `rm -f` destroys
  the other's state. A single run never self-overlaps, so the normal
  gate is safe; this bites only when two full runs (or a gate plus
  another session's tests) race — plausibly the same environmental
  class as the retired 2026-10-24 0.131.0 "~2x parallel load" one-off.
  Reproduced once (both concurrent runs failed); not fixed — fix is a
  product-path decision (uniquify the state-file path) vs test-side
  isolation, to be prompted. Sequential manifestation (seen 2026-10-26
  after the results-file leak fix): a FAILED run's stale
  /tmp/sever-vm-clone-<vmid>-*.state residue also poisons the NEXT run
  — its find-based --continue tests pick the oldest (stale) state file
  and fail confusingly; clear /tmp/sever-vm-clone-* between reruns of
  a failed suite. With a clean /tmp the suite is deterministic-green
  (6 consecutive green runs post-fix).

- (test-harness gap, found 2026-10-26): "Test log retained for
  post-mortem" is not a guarantee. A failed suite's retained log
  (pid 3123215, test-sever-vm-clone) vanished within minutes of the
  run, mirroring the swept-log experience recorded with the retired
  0.131.0 flake entry. Canary experiment: the test-lib source-time
  sweep (tests/test-lib.sh:346) spares non-empty dead-pid logs, but an
  empty-at-exit "retained" log (observed live: 0-byte retained log,
  pid 3122458) is deterministically reaped by the next suite that
  sources test-lib. Why the failed suite's log ended up empty/absent
  is unidentified (no fork/ENOSPC/OOM evidence; /tmp had 13G free).
  Practical rule until fixed: on any suite failure, capture
  /tmp/zfsutilities-test-<pid>.log immediately, before other suites
  start.
