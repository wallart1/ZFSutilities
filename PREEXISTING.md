# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (style, line length): two pre-existing over-100-character lines in
  `bin/uninstall-zfsutilities` (the `legacy_config_dir` and
  `legacy_offsite_nextsnap_file` env-default assignments). Wrapping them
  would mean reshaping public `ZFSUTILITIES_*` env-var default expressions,
  so they were left alone during the 2026-10-11 standards pass; fold into
  the next edit of that block.


- (legacy data, archives — narrowed 2026-10-11): pre-sidecar archives (e.g.
  VM 204's 2026-08-28 archive on stewie) still cannot be *automatically*
  restored — they predate the sidecar format and carry no disk keys, config
  text, or iSCSI layout. Resolved 2026-10-11 as far as actionable: the
  missing-sidecar FATAL now names the pre-sidecar cause, and the manual
  restore procedure is documented in the unarchive-vm command docs. Remaining
  decision (user): whether to build a legacy-import mode that restores the
  zvols alone and leaves config/iSCSI to the operator.

- (toolchain deprecation, docs build): `mkdocs build -f docs/mkdocs.yml`
  prints a mkdocs-material WARNING — "MkDocs 2.0 is incompatible with
  Material for MkDocs" — on every build (exit 0, site still builds cleanly).
  Action is a toolchain decision (pin mkdocs <2 vs migrate to Zensical),
  already analyzed in SESSION_NOTES.md's Zensical thread; recorded here so
  it can be prompted for a decision. Not resolved (code freeze).
  Zensical is under development. We are waiting for a 1.x.x release.
  (Rechecked 2026-10-08: PyPI shows 0.0.69; still no 1.x.
  Rechecked 2026-10-10: unchanged, 0.0.69.
  Rechecked 2026-10-11: unchanged, 0.0.69.)

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
