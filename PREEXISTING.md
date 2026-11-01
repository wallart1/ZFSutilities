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
