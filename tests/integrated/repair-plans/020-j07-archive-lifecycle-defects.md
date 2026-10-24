# Repair Plan 020 — j07 archive/unarchive lifecycle defects (F-020…F-024)

One campaign, five defects: running the archive→unarchive lifecycle end
to end on the two-node lab (j07) flushed out latent breakage at every
stage. All five were fixed in-cycle on 2026-10-23 under the approved
unarchive-vm iSCSI-rebuild task (same act-on-analysis directive as
repair plan 019); this file records what changed so the FINDINGS rows
stay traceable.

## F-020 — query ssh calls drain piped answer feeds

`ssh` with a non-tty stdin eagerly reads (and discards) queued input even
when the remote command never reads stdin, so any bare query `ssh` placed
between an interactive script's prompts eats the next queued answer.

Fix: `-n` on every stdin-free ssh call in bin/archive-vm,
bin/unarchive-vm, and lib/node-lib (remote_zfsutilities_bin,
probe_target_usage). Two call shapes intentionally keep stdin: the
archive-vm `bash -s` heredoc payload (its script IS the stdin) and the
remove-vm-disk `ssh -t` delegation (it forwards the confirm answers).
tests/test-unarchive-vm's ssh stub now parses the last argv entry.
Regression fence: j07's feed-through-archive path — unit suites mock
ssh, so the drain cannot reproduce there.

## F-021 — two-node sidecar DISK_KEY matcher never matched

The matcher glob `*"ip-"[0-9.]":3260-iscsi-…"*` requires exactly ONE
character between `ip-` and `:3260`; real portal IPs never matched, so
`DISK_KEY=`/`LUN=`/`TARGET=` were never appended to two-node archives
and unarchive-vm Step 3 could not rewrite by-path lines.

Fix: `*"ip-"*":3260-iscsi-${target}-lun-${lun}"*` (the shape
unarchive-vm's own detector already used). Regression test extracts the
matcher from bin/archive-vm and evals it against a real by-path line
(red on the old glob, green on the new); j07 Stage A fences the append
end-to-end ("Rewrote scsi0" requires the sidecar key).

## F-022 — safe-iscsi-save refused the legitimate empty manifest

Removing the LAST VM disk empties the expected-backstores manifest;
safe-iscsi-save hard-refused any empty manifest, so remove-vm-disk
FATALed after teardown and archive-vm reported "VM removal incomplete".

Fix: an empty manifest is refused only while block backstores are active
(broken manifest); with zero active backstores it saves the
target-only config with an INFO line. test-safe-iscsi-save covers both
branches.

## F-023 — zfsdelfs looked only at legacy conf paths

zfsdelfs checked /etc/zfsutilities-node.conf then /etc/two-node.conf and
FATALed on FHS-only installs; masked in production by a leftover legacy
conf.

Fix: mirror node-lib's precedence (FHS conf first, then both legacy
paths, honoring the ZFSUTILITIES_* env overrides). zfsdailybackup and
rsync-dailybackup carry the same legacy-only pattern — recorded in
PREEXISTING.md, deliberately not touched by this campaign.

## F-024 — portal-add fatality against targetcli's default portal

`/iscsi create` attaches a default 0.0.0.0:3260 portal; adding
`${storage_ip}:3260` then fails (port already bound), which the new
unarchive-vm target-creation recipe treated as fatal.

Fix: fatal only when the TPG ends up with no portal at all; otherwise a
WARN names the kept portal. j07 Stage B recreates a target on a host
whose other targets already bind 3260 and passes.

## Verification

j07-unarchive-iscsi-rebuild GREEN (results/run-20261023-175006): drift
convergence with per-host backups, live-target mapping, by-path rewrite,
target rebuild with compute-side discovery+login, boot proof, ambiguity
refusal without mutation. Affected unit suites green: test-node-lib,
test-unarchive-vm, test-archive-vm, test-safe-iscsi-save, test-zfsdelfs,
test-remove-vm, test-installer-flows.
