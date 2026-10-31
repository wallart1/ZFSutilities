# Repair Plan 023 — recover-encrypted-luns: LUN index from the pool map when saveconfig lacks it

Finding: **F-042** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-30 — user-approved ("Please execute repair plan
023").** Landed as proposed: `lookup_lun_number_in_map` (same IQN scoping
law as the saveconfig lookup) + `resolve_lun_number` resolver used by both
the recovery and already-present grant-heal paths; the map is resolved once
per run via `newest_iscsi_state_map`, and a map generated on another host
is ignored with a WARN (the reconcile site-identity rule). The no-index
FATAL was reworded to point at the map and the `.pre-start` backup instead
of the unactionable conf-entry advice. Unit suite red-proven (4 new tests
failing on the pre-fix script) then green; j16 S8 and j18 S16 gates
flipped to assert the healed path (journey rerun pending). This file keeps
the original proposal below for traceability.

## Root cause

`bin/iscsi-recover-encrypted-luns` resolves each encrypted LUN's slot
through `lookup_lun_number`, which reads **only**
`/etc/rtslib-fb-target/saveconfig.json` (the embedded python walks
`targets[].tpgs[].luns[]` and prints `lun["index"]`).

After a both-node power cycle, the compute fence's post-return tick
runs `reconcile-iscsi-state` on the storage host while encrypted keys
are still pending. Reconcile handles that state correctly on the map
side (skips the encrypted zvols with the `keys not loaded?` hint and
leaves the pool map unchanged — "the map preserves the recovery
authority for them"), but its trailing `safe-iscsi-save` rewrites
saveconfig.json from the encrypted-less live state. The encrypted LUN
records — and with them the only index source recover consults — are
gone:

```
FATAL:   vm-202-disk-0 has no recorded LUN index under <iqn> in saveconfig.json
FATAL:     Not guessing an index (auto-assignment can collide or pick
FATAL:     the wrong slot when orphan targets exist). Check with
FATAL:     show-lun-map and saveconfig.json, then fix the conf entry.
```

The printed advice is unactionable: `iscsi-encrypted-luns.conf` carries
`name:device:target` with no index field. The authoritative index
survives in two places recover never reads — the pool map
(`targets.<iqn>.luns` = `{"lun#": "backstore"}`, exposed by
`export-iscsi-state --print-map`) and the boot's
`saveconfig.json.pre-start` backup.

Why j15's boot scenarios never hit it: there the compute node stayed up
through the storage reboot, so sessions clung (PVE's 24h replacement
timeout) and the fence tick reported healthy — no reconcile ever ran
between boot and the key ceremony. The both-node power cycle is the
first shape where an unattended tick lands in the keys-pending window.

## Proposed fix

`iscsi-recover-encrypted-luns` gains a map fallback for the index:
when `lookup_lun_number` finds nothing in saveconfig.json, resolve the
index from the newest pool map's `targets.<iqn>.luns` entry for the
backstore (same map source reconcile itself rebuilds from — the map is
already the declared recovery authority for exactly this state). No
guessing is introduced: a missing map entry keeps today's refusal.

Behavior shape:

- saveconfig records the index → unchanged path (today's behavior).
- saveconfig lacks it, map records it → recover at the map-recorded
  index, with an `INFO` line naming the fallback source.
- neither records it → today's FATAL stands (reworded to point at the
  map instead of the unactionable conf-entry advice).

Alternative considered (not proposed): making `safe-iscsi-save` refuse
to drop still-registered encrypted records while keys are pending.
Rejected as the primary fix because it fences the write rather than
healing the read — the pre-start backup and any saved-before-reboot
saveconfig would still strand older installations, and the map is the
authority both reconcile and the docs already name.

## Verification

- Unit: `tests/test-iscsi-recover-encrypted-luns` (or the suite that
  pins its transcripts) gains the fallback cases — saveconfig-missing +
  map-hit (recovers at the recorded index, INFO names the source) and
  saveconfig-missing + map-miss (refusal stands, reworded message).
  Red-proven before the fix.
- Journey: j18 S16's `recover dead-ends after a keys-pending fence
  save` gate flips to the healed path once this rides the dev tarball —
  the step text updates to assert the direct recovery (the F-042 row
  closes "accepted").

## Risk

Low: the fallback only widens the index source to the document-stamped
authority, only when saveconfig is silent; the no-index refusal (the
safety property the FATAL exists for — never guessing a slot) is
preserved verbatim for the truly-unknown case.
