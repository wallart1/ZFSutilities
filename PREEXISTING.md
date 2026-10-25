# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (coding-policies divergence, strict mode — family-wide, discovered
  2026-10-24 wrap-up): coding-policies.md says scripts should start with
  `set -euo pipefail`, but the whole bashinit-based iSCSI/two-node family
  (safe-iscsi-save, repair-iscsi-luns, setup-iscsi-targets, rescan-storage,
  list-vm-disks, new-vm-disk, remove-vm-disk, and ~25 more) runs without it.
  Strict mode lands via named migration campaigns: the 2026-10-16 wrap-up
  flipped 13 orchestrators (audit + fence per script, e.g. assignment-of-
  failing-substitution aborts) and tests/test-strict-mode guards that list.
  The iSCSI family was never in a campaign; the new iSCSI-resilience
  scripts (export-iscsi-state, reconcile-iscsi-state) follow the family.
  Migration needs the same audit-and-fence treatment plus adding the
  family to test-strict-mode's strict_scripts list.

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
  (Rechecked 2026-10-22: unchanged, 0.0.71.)
  (Rechecked 2026-10-22 wrap-up: unchanged, 0.0.71 — no 1.x; hold stands.
  Rechecked 2026-10-23 wrap-up: unchanged, 0.0.71 — no 1.x; hold stands.
  Rechecked 2026-10-23 (itf cycle): 0.0.72 — first movement since 10-16,
  still no 1.x; hold stands. The mkdocs<2 pin remains the documented
  product stance — doc-server.md and messages/index.md carry it.
  Rechecked 2026-10-24 wrap-up: unchanged, 0.0.72 — no 1.x; hold stands.)

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

- (test hygiene, /tmp litter — discovered 2026-10-24, M3 turn): the suites
  that divert rootcheck resolution through a stub dir (`_rootcheck_stub=$(mktemp -d)`
  + `printf 'rootcheck() { true; }\n' > stub/rootcheck`; list-vm-disks,
  zfswipe, zfsshowbigstuff, zfsdelfs, zfsdelallsnaps, zfscleanup,
  findoffsitepool, zfsmount, iscsi-add-encrypted-luns,
  iscsi-recover-encrypted-luns — same pattern) never remove the directory:
  every full-suite run leaks ~one rootcheck-only tmp dir per such suite
  (6 observed after the 2026-10-24 M3 run; swept by hand). Fix: register
  the stub dir with the suite's exit-trap cleanup (test-lib's
  append_exit_trap pattern) or rm -rf it at teardown.

- (future objective, iSCSI resilience — survive bare-metal restores up to
  30 days old; user todo 2026-10-22): a bare-metal OS restore of the
  storage host regresses the LIO saveconfig.json AND the
  expected-backstores.txt manifest to the backup point while the pools
  re-import current; LUNs/backstores created after the backup point
  vanish from the target while compute-host VM configs keep their
  references, and PVE aborts VM start when any configured disk is missing
  (proven 2026-10-21/22, manual repair in SESSION_NOTES.md 2026-10-22).
  The compute-host-restore case is the mirror image and the dangerous
  one: regressed VM configs can reference LUN numbers that now map to
  DIFFERENT backstores → wrong disk attached to a VM, silently. Core
  insight: the pool is the only state that survives a restore *current*;
  LIO config and manifest are derived state on the OS disk, so
  reconstruction-from-authority beats backup/restore of the config (a
  30-day-old copy is exactly the failure). Identity during any recovery
  is the backstore/zvol name, never the LUN number alone. Design ideas:
  (A) reconcile pass (extend repair-iscsi-luns or a sibling) that
  rebuilds LIO from the two durable authorities — compute-host VM
  configs (the must-start set) and `zfs list -t volume <pool>/proxmox`
  (what exists): missing backstore + existing zvol → create with
  emulate_tpu=1 and map at the config's LUN number if free; LUN number
  held by a different backstore = identity conflict → refuse and report,
  never auto-remap. Manifest-staleness detection: config-referenced
  backstore names not in the manifest, or manifest names not in the pool
  → regenerate (today repair-iscsi-luns cannot do this: it trusts the
  manifest, which regresses with the same OS disk). (B) nightly export
  of the backstore/LUN/ACL map + node.conf to a dataset on each pool,
  covered by the existing daily snapshot flow → last-known-good LUN
  numbers are hours old, not 30 days; this is the authority for the
  compute-restored case where the VM configs are the regressed side.
  (C) detection fence on the compute host: extend the existing 5-minute
  iscsi-health-check from session/device counts to "every VM-config
  by-path reference exists in /dev/disk/by-path", reporting per
  (VM, disk, IQN, LUN) and optionally invoking the reconcile — converts
  silent post-restore breakage into an immediate actionable signal.
  (D) restore-time pass: detect the OS-state-predates-pool signature
  (zvols with creation newer than the manifest/config state, or a
  non-empty manifest-vs-pool diff) in setup-iscsi-targets or
  check-prerequisites and offer the reconcile. Storage-host half
  (A+B+C+D) is well understood; the compute-host config repair is the
  harder half (touch only by-path lines, via qm set, from B's
  last-known-good map).
  (Progress 2026-10-23: plan milestones M1 (pool-resident state export,
  idea B) and M2 (reconcile engine, idea A) implemented in the working
  tree — export-iscsi-state + reconcile-iscsi-state + safe-iscsi-save
  hook. Entry stays: M3–M6 remain, executed one milestone at a time per
  the user's cycle.)
  (Progress 2026-10-24: M3 (restore-time detection, idea D) implemented in
  the pub2 working tree — read-only detectors in lib/iscsi-lib.sh
  (signatures a/b/c), check-prerequisites --two-node informational warns,
  setup-iscsi-targets evidence + reconcile offer. M4–M6 remain.)
  (Progress 2026-10-24: M4 (compute-host fence, idea C auto-recover)
  implemented in the pub2 working tree — check-vm-disk-paths +
  zfsutilities-iscsi-fence.{service,timer} + switch-version activation
  gating (install_iscsi_fence_units) + install-two-node summary +
  uninstall-zfsutilities symmetric unit removal. M5–M6 remain.)
