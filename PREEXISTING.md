# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (production bug, attach-vm-disk single-node): `bin/attach-vm-disk` builds
  the single-node disk line as `disk_line="${dstkey}: ...,"\<newline>
  "format=raw,discard=on,iothread=1,size=${zvol_size}"` — the
  backslash-joined assignment leaves `disk_line` EMPTY and tries to execute
  `format=raw,...` as a command (rc 127), which `set -e` (line 182) turns
  into an abort. Every single-node attach has crashed at the disk-line
  build since the line landed in 0.96.0; the two-node branch is a single
  string and fine. No test reaches the single-node disk-line branch
  (test-attach-vm-disk stops at validation). Same defect class as the
  test-suite `local` continuations fixed 2026-10-12 (bash treats the
  joined words as assignment-prefix + command). Discovered 2026-10-12
  during the 0.124.0 wrap-up sweep; NOT fixed — code was already frozen
  for the release ("no more code changes"). Fix: build with `+=` (one
  variable, two statements) + a script-execution test that reaches the
  config write on the single-node path.

- (test hygiene, suite scratch dirs): green suite runs leak one EMPTY
  `/tmp/mock_zfs_state_<pid>/` directory per run (17 accumulated across
  2026-10-11/12; all empty — contents are cleaned, the directory itself
  survives or is recreated). `test-lib.sh` intends zero litter
  (`_test_lib_cleanup` rm -rf's the dir via a `$$`-scoped exit trap, and
  re-sources inside `$(...)` subshells share the same `$$`-derived path),
  so something recreates or re-creates the directory after/without the
  trap — exact mechanism needs a strace/audit pass. Discovered during the
  0.124.0 wrap-up (earlier `ls | head` checks had hidden the pile); litter
  removed by hand; not fixed — test-lib was under the release code freeze.

- (toolchain deprecation, docs build): `mkdocs build -f docs/mkdocs.yml`
  prints a mkdocs-material WARNING — "MkDocs 2.0 is incompatible with
  Material for MkDocs" — on every build (exit 0, site still builds cleanly).
  Action is a toolchain decision (pin mkdocs <2 vs migrate to Zensical),
  already analyzed in SESSION_NOTES.md's Zensical thread; recorded here so
  it can be prompted for a decision. Not resolved (code freeze).
  Zensical is under development. We are waiting for a 1.x.x release.
  (Rechecked 2026-10-08: PyPI shows 0.0.69; still no 1.x.
  Rechecked 2026-10-10: unchanged, 0.0.69.
  Rechecked 2026-10-11: unchanged, 0.0.69.
  Reconfirmed 2026-10-11 (user): keep waiting for 1.x.
  Rechecked 2026-10-12: 0.0.70; still no 1.x.)

- (future objective, migration/create fidelity — narrowed 2026-10-03):
  No creation path (Create Pool wizard or Migrate Pool) can *plan*
  infrastructure vdevs (special / log / cache / spare): the review page
  warns when the source pool has them, a post-cutover INFO reminder says to
  re-add them with Add Infrastructure Vdev, and as of 2026-10-03 the
  holding-mode rebuild picker preselects only true data members (former
  infra-vdev disks are listed unchecked, labeled with their class, so they
  can no longer be silently absorbed into data vdevs). Remaining gap is the
  planning UI itself, deliberately deferred as a future objective (user
  decision 2026-10-03): per-class disk pickers in the wizards plus
  `zpool add <class>` steps after the create step (or an extended
  `zpool create` vdev spec). Originally discovered 2026-10-03 during the
  pool-level migration audit.
  This item is in abayance as a future objective.
  (Reconfirmed 2026-10-11 (user): keep deferred.)
