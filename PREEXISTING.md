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
  (Rechecked 2026-10-22: unchanged, 0.0.71.)
  (Rechecked 2026-10-22 wrap-up: unchanged, 0.0.71 — no 1.x; hold stands.
  Rechecked 2026-10-23 wrap-up: unchanged, 0.0.71 — no 1.x; hold stands.
  Rechecked 2026-10-23 (itf cycle): 0.0.72 — first movement since 10-16,
  still no 1.x; hold stands. The mkdocs<2 pin remains the documented
  product stance — doc-server.md and messages/index.md carry it.
  Rechecked 2026-10-24 wrap-up: unchanged, 0.0.72 — no 1.x; hold stands.
  Rechecked 2026-10-25 wrap-up: unchanged, 0.0.72 — no 1.x; hold stands.)

- (test flake, one-off, 2026-10-24 pub3 0.131.0 with-soak gate): the
  with-soak full run failed test-unarchive-vm Test 26 ("Step 2 refuses
  duplicate same-short targets") — the ssh-mock storage-host existence
  probe (`zfs list -H -o name <archive> | grep -qxF`) missed the
  in-suite `_mock_zfs_fs_list` entry under ~2x parallel load, so
  unarchive-vm correctly FATALed "Not a ZFS dataset" before reaching
  the ambiguity path. Not a product defect: the probe behaved right
  for the answer the mock gave. Four consecutive standalone reruns
  passed (plus the same-suite pass in the same-day non-soak run).
  Retained post-mortem log was swept before inspection, so the exact
  mock-layer miss (empty fs_list vs swept state) is unidentified. If
  it recurs, capture /tmp/zfsutilities-test-<pid>.log immediately and
  instrument the mock zfs-list arm; do not touch product code for it.

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
