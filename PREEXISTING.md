# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---


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
  (Rechecked 2026-10-13: unchanged, 0.0.70.)
  (Rechecked 2026-10-16: 0.0.71; still no 1.x.)

- (coverage gap, installer flows): install-single-node and install-two-node
  have only guard-level suites (test-installer-checks / -structure /
  -retention, test-iscsi-fresh-install-guards) — nothing executes the
  installers' interactive flows, so shell-variable flow bugs are invisible
  to the suites. Found live during the 2026-10-16 strict-mode audit:
  install-two-node's keep-existing-config path never set the lowercase
  host variables (node.conf defines the UPPERCASE names only) and always
  died at the storage-host check on an empty hostname. The bug is fixed
  (the config source + lowercase refresh now runs in both paths), but the
  class stays unfenced until an execution harness exists — mock
  check-prerequisites/deploy-version/switch-version/ssh and piped stdin
  answers, in the test-unarchive-vm two-node style.

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
