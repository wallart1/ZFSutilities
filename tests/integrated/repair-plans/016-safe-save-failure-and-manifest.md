# Repair Plan 016 — safe-iscsi-save failures invisible + manifest never bootstrapped

Finding: **F-016** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-08 (standing user grant to continue
corrections in the repository).  New suite
tests/test-iscsi-fresh-install-guards green; red/green proven by
file-swap against HEAD's six scripts (4 failures pre-fix).  Live j05
rerun pending.  VERIFIED 2026-10-08: j05 GREEN in run-20261008-230934-j05-two-node-install (36 steps, 0 fail)..**

## Root cause

Two defects met at the persist step of the first fresh-install
VM-disk operation (live: j05 run results/run-20261008-221239,
new-vm-disk.log):

1. `"$mydir/safe-iscsi-save"` is called without checking its exit
   status in new-vm-disk (:553 pre-fix), detach-vm-disk (:193),
   remove-vm-disk (:206), restart-iscsi-services (:186); unarchive-vm
   printed its CONFIG_SAVED success marker after the call inside its
   remote heredoc regardless of outcome.  new-vm-disk literally logged
   "✓ Configuration saved" on the line after safe-iscsi-save's FATAL.
   (attach-vm-disk is safe: its call is the heredoc's last statement,
   so ssh propagates the status; rename-vm-disk runs under set -e.)
2. safe-iscsi-save refuses to run when
   /etc/rtslib-fb-target/expected-backstores.txt is missing, but
   new-vm-disk's manifest add was guarded by `[[ -f $manifest ]]` —
   skipping the add in exactly the fresh-install state where the file
   does not exist — and no other script, installer step, or document
   creates it.  Production stewie carries the file from history.

## Fix (in this repository)

1. All five unchecked sites now check the exit status and fail loudly
   (`FATAL: safe-iscsi-save failed — iSCSI configuration NOT saved`;
   exit 1 in the standalone scripts, return 1 in restart-iscsi-
   services' main, and a SAVE_FAILED marker + exit 1 in unarchive-vm's
   remote heredoc so its local `|| { FATAL }` handler fires).
2. new-vm-disk's manifest add now ensures the directory and appends
   unconditionally (dedup guard kept, `2>/dev/null` for the absent
   file), so the first disk on a fresh install creates the manifest.

## Verification

1. tests/test-iscsi-fresh-install-guards (structural): guarded-call
   pins for the four standalone callers + the unarchive marker
   ordering + the structural-safety pins for attach (last statement)
   and rename (set -e); the manifest-bootstrap pin; the F-017 pin
   (see plan 017).
2. Red/green: file-swapping HEAD's six scripts makes 4 of 5 tests
   fail; restored, 5/5 pass.
3. j05 rerun (dev-tarball carries the fix): the LUN-creation log shows
   "Added to expected-backstores manifest" and an honestly-earned
   "✓ Configuration saved"; the journey's final safe-iscsi-save step
   produces saveconfig.json + saveconfig-boot.json.
