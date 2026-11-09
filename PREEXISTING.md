# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (100-column policy deviations, pub-lane test suites, found 2026-11-05):
  Several released pub-lane suites carry lines over the 100-character
  limit (coding-policies.md): long assertion strings and JSON/journal
  fixtures in test-zfsreplayprops (15), test-check-prerequisites (11),
  test-property-manifest-lib (10), test-export-iscsi-state (5), and
  test-itf-lab-stages (16, incl. printf payload lines that would need
  byte-identical wrapping). None are touched by this lane's changes;
  reflowing them belongs to a pub-side pass.

---

- (vacuous subprocess test, test-zfsdelfs, found 2026-11-04):
  `tests/test-zfsdelfs` `test_delfs_autoproceed_override_subprocess` asserts
  rc=0 and no "About to delete" prompt — both of which a silently-empty run
  also satisfies. Its runner (`run_delfs_subprocess`) puts the zfs stub in
  `ZFSUTILITIES_BIN_DIR` but not on `PATH` (helper lookups only — the `zfs`
  command itself resolves through PATH), and passes the dataset list as an
  env-prefix array, which bash cannot export across the exec. The real
  `zfs` then fails on the nonexistent pool/data listing, the per-dataset
  loop runs zero iterations, and zfsdelfs exits 0 printing nothing. The new
  busy-resolver retry test in the same suite uses PATH + a file-based
  fsarray and does exercise the loop; fixing the older test to the same
  pattern is out of scope for the resolver campaign.

---


- (test mock fidelity gap, flat dataset listing, found 2026-11-02):
  The `zfs list` mock's general dataset listing (`tests/test-lib.sh`,
  `_mock_zfs_fs_list` branch) ignores the requested root and echoes the
  whole flat world list, so rooted enumerations (buildfsarray via
  zfs-send-receive/zfsdelfs) see datasets from elsewhere in the mock
  world. Surfaced while making hold mocks faithful: delfs "pool/dest/data"
  enumerated and destroyed "pool/src/data" instead. A root-filtering fix
  was attempted and reverted — three suites model only part of the tree
  (existence-only `_mock_zfs_datasets` worlds, destination-less fs lists)
  and need world rewrites first. The current holds tests sidestep it by
  listing both trees in their world. Not fixed: broader mock-world
  campaign, out of scope for the reapply-holds fix.

---
