# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

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
