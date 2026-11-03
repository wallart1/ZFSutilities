# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

## ITF orphan fence misattributes recycled VMIDs to stale claims

Discovered 2026-11-01 (pub lane, diagnosing the pub/pub2 lab collision).
`itf_runlock_orphan_fence` (tests/integrated/lib/runlock-lib.sh:170-296)
identifies leftover guests of interrupted runs by `(base, VMID)` alone,
while `itf_vmid_pick` (tests/integrated/lib/guest-lib.sh:27-35) deliberately
recycles VMIDs from the same reserved pool (site/config: 8000-8099) as soon
as `qm list` shows them free. Guest records (`guest*.txt`, format
`<base> <vmid> <ip>`) carry no guest name, and the fence's `qm list` parsing
(runlock-lib.sh:241-243) discards the NAME column. Result: after the
interrupted Oct-31 pub run left a stale claim on 8001 and the pub2 lane
legitimately re-allocated 8001 (its j05-storage), the fence matched the live
pub2 guest to pub's stale record, refused the start (correct, fail-closed),
and printed remedies — `itf guest destroy <base> 8001` and the
`journey run <name> --rerun` rollback — that all target the parallel
session's live guest. Only agent judgment prevented sabotage. Fix
direction: record the guest name (or an ownership tag) in `guest*.txt` and
compare against `qm list`'s NAME column; a mismatch is "someone else's live
guest — wait", not a leftover to destroy or roll back. Note: pub2's newer
per-journey-guest harness (which names guests for their journeys) may
already change this shape; reconcile at lane merge. Not fixed per the
standing ITF reactive-maintenance policy — trigger-gated.

---

- (false positive, bash pool-identity detector, found 2026-10-31):
  `detect_pool_identity` in `lib/iscsi-lib.sh` (surfaced by
  `bin/check-prerequisites` and `bin/setup-iscsi-targets`) reports
  "expected pool ... is not imported — offline, renamed, or replaced" for
  offsite rotation pools that are exported on purpose (live instance on
  stewie: z22tb). The Dashboard's copy of the check
  (`_compute_pool_identity_warnings`) now exempts GUI-config offsite
  candidates, but the bash layer has no offsite knowledge; closing the
  bash side needs an offsite marker in node.conf (a schema the user owns)
  or another bash-readable source. Not fixed: requires a config-schema
  decision.

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
