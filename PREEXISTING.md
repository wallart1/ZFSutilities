# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---


- (convention drift, bash strict mode): coding-policies.md's core
  principles say scripts should use `set -euo pipefail`, but bin/ is
  split roughly in half — newer orchestrators (deploy-version,
  install-*, unarchive-vm, upgrade-zfsutilities, zfsclone-vm, ...) run
  `set -e` only, while others (check-prerequisites, uninstall-*,
  zfs-migrate-send, sever-vm-clone, ...) use the full trio. Observed
  2026-10-13 during the wrap-up standards pass. Audit for a dedicated
  migration session (not wrap-up-safe: 13 scripts / ~9,700 lines of
  root-owned live-VM orchestrators; the two failure classes the flip
  introduces — `-u` aborting on unset vars in sourced bashinit/node-lib/
  paths code paths, and pipefail aborting on legitimately-empty grep
  pipelines — are exactly what the mock-based suites cannot fence;
  F-010 was the same class found live). Scripts: clone-vm, attach-vm-disk,
  ensure-restored-vm-iscsi, deploy-version, install-single-node, remove-vm,
  move-vm-disk, install-two-node, rename-vm-disk, sever-vm-clone (partial:
  already has euo pipefail inside subshells), unarchive-vm,
  upgrade-zfsutilities, zfsclone-vm. Direct suites exist for 10 of 13;
  the installers have test-installer-* coverage only and zfsclone-vm is
  in the user-declared orchestrator-exempt class.

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
