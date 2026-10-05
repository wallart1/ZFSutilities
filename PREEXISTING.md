# This file is maintained by Kimi Code. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (toolchain deprecation, docs build): `mkdocs build -f docs/mkdocs.yml`
  prints a mkdocs-material WARNING — "MkDocs 2.0 is incompatible with
  Material for MkDocs" — on every build (exit 0, site still builds cleanly).
  Action is a toolchain decision (pin mkdocs <2 vs migrate to Zensical),
  already analyzed in SESSION_NOTES.md's Zensical thread; recorded here so
  it can be prompted for a decision. Not resolved (code freeze).
  Zensical is under development. We are waiting for a 1.x.x release.
  (Rechecked 2026-10-05: PyPI shows 0.0.68; still no 1.x.)

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

- (coding-standards debt, itf harness): `tests/integrated/` (driver, libs,
  journeys) uses only `set -u`, not the `set -euo pipefail` the bash coding
  policy prescribes. The harness was live-proven through the cycle-1
  campaign (30 install attempts) with manual error accumulation and
  explicit rc capture throughout (e.g. `journey_main`'s rc is captured
  after the call; preflight accumulates `fail_total`); flipping strict
  mode on blindly would abort at those intentional non-zero paths.
  Wrap-up review (2026-10-05) chose not to change it without live
  re-validation (guests destroyed, environment parked). Address at
  cycle-2 kickoff: adopt strict mode + guard the deliberate
  failure-accumulation sites, then run a full J01–J03 campaign to
  re-validate.

- (coding-standards debt, legacy test files): a handful of untouched
  `tests/test-*` files carry over-100-column lines (notably
  test-list-vm-disk, test-enroll-efi-keys-vm, test-zfslockmanager;
  counts vary) predating the integrated-testing changeset. All files
  touched by the integrated-testing changeset were wrapped to ≤100
  columns during the 2026-10-05 wrap-up review.
