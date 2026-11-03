# Repair Plan 027 — encrypted-aware boot verification verdict (R-08)

Status: **EXECUTED 2026-11-02 (user-approved promotion of R-08; plan
presented and approved in the same session). Design as planned, no
in-cycle migration decisions: the map schema is untouched (attribution
reads the existing backstores' `dev` paths), the keystatus probe lives in
bash so the suite's zfs function mocks stay in force, and the drop-in
wrapper keeps treating unknown exits as FAILED — an old wrapper + new
check journals the old FAILED text during a version skew, never a false
OK. Verification: unit suites green (export-iscsi-state incl. 5 new
keys-pending tests, itf-lab-stages pending-mode parser, switch-version);
the j15 lab rerun is queued behind the standing ITF cue discipline.**

## Finding

R-08 (from F-029, j15 S1/S1c; the REQUIREMENTS row is the durable record
— the FINDINGS row went terminal and was pruned at the 0.137.0 release
prune). On a site where encrypted keys load manually
(live instance: stewie, vm-101-disk-1 + vm-202-disk-5 on threeamigos),
every boot runs the post-restore verifier while those datasets are
key-locked: the journal gets `post-restore verification FAILED` + DRIFT
lines until `load-keys` + `iscsi-recover-encrypted-luns` complete. The
semantics are correct — the do-NOT-save guidance is right in that window
and `safe-iscsi-save`'s gate refuses the save anyway — but an *expected*
FAILED on every boot trains operators to skip the verifier exactly when
the unexpected-drift case (the 2026-10-27 incident class: 3 of 33 LUN
mappings silently missing) needs attention.

## Root cause

The verdict is binary: `export-iscsi-state --check` exits non-zero on any
drift and the boot drop-in's wrapper maps every non-zero exit to the same
FAILED line. The check knows which objects are missing live but never
consults key state, so "missing because the key is locked" (the designed
manual-keys posture, zfs-keys.md) and "missing for a real reason" are
indistinguishable in the journal.

## Proposed change (as executed)

Three-verdict protocol. `--check` exits 0 (match) / 3 (all drift
keys-pending) / 1 (any other drift):

- `report_state_drift` (bin/export-iscsi-state) classifies each drift
  line: a locked key can only remove live objects, so the candidate
  verdict (internal exit 2) requires every line to be a map-recorded
  backstore / target LUN / ACL grant missing live, each tracing to a map
  backstore whose `dev` is a `/dev/zvol/<dataset>` path. On exit 2 the
  report carries `KEYSUSPECT: <backstore>=<dataset>` lines for the bash
  caller (filtered out of the final output). One unattributable line
  (moved, extra-live, renamed, GUID change, target gone) collapses to
  plain drift — fail closed.
- The `main` `--check` branch probes `zfs get -H -o value keystatus` per
  suspect dataset: all `unavailable` → the keys-pending WARN summary
  (naming the locked LUNs, load keys + recover + do-NOT-save guidance)
  and exit 3; keys loaded, unencrypted (`-`), or unreadable → the FAILED
  verdict (exit 1).
- The boot drop-in (share/two-node/rtslib-fb-targetctl-boot-config.conf)
  journals `post-restore verification PENDING — encrypted LUN(s) await
  key load (see DRIFT lines); do NOT save config until reconciled` on
  exit 3; OK and FAILED branches unchanged. Older drop-ins map exit 3 to
  FAILED — conservative skew behavior.

## Blast radius

- Suites: test-export-iscsi-state (zfs mock gains keystatus; 5 new
  tests: pending rc 3, keys-loaded rc 1, unreadable rc 1, mixed rc 1,
  unencrypted rc 1), test-itf-lab-stages (pending-mode parser fixture),
  test-switch-version (structural drop-in assertions — unaffected,
  verified).
- Journeys: j15 S1/S1c/S2/S5a expect PENDING on keys-absent boots;
  common.sh's `itf_boot_journal_verdict` gains the `pending` mode; j16 is
  verdict-word agnostic (unchanged).
- Docs: two-node-config.md (three-verdict protocol), zfs-keys.md,
  messages manual (PENDING row + re-scoped FAILED row + the check's
  keys-pending WARN), two-node.md `--check` section,
  integrated-testing.md, GLOSSARY.md's controlled-reboot entry.
- End user: after the next deploy, a stewie keys-absent boot journals
  PENDING instead of FAILED; unexpected drift still journals FAILED. The
  user's own "Corrected exercise sequence" oracle expects FAILED and
  needs the user's own one-word update (user-owned file).

## Verification

Unit suites above green; full gate green. The j15 journey rerun (live
PENDING proof) runs on user cue per the standing ITF rationing policy;
the still-pending controlled stewie reboot exercise is the first
production exercise of the verdict.
