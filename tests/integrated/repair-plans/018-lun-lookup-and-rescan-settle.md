# Repair Plan 018 — compute-side LUN lookup never matches; rescan counts too early

Finding: **F-018** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-08 (standing user grant to continue
corrections in the repository).  Pins added to
tests/test-iscsi-fresh-install-guards (7/7 green); red/green proven by
file-swap against HEAD's new-vm-disk + rescan-storage.  Live j05 rerun
pending.  VERIFIED 2026-10-08: j05 GREEN in run-20261008-230934-j05-two-node-install (36 steps, 0 fail)..**

## Root cause

With login fixed (F-017), run 10 still ended without the disk in the
VM config.  Live forensics on the still-running guests:

1. The LUN device was fully present (`sdb LIO-ORG vm-101-disk-0`,
   by-path entry `ip-192.168.101.1:3260-...-lun-0`), and the raw
   targetcli query new-vm-disk runs returns
   `o- lun0 ... [block/vm-101-disk-0 (/dev/zvol/...)]`.  But the
   compute-side lookup pipes it through
   `grep ' ${backstore_name} '` — space-anchored on both sides — and
   the name in that line is slash-prefixed (`block/vm-101-disk-0`), so
   the grep matches nothing, `lun_num` stays empty, and
   add_data_disk_to_config is skipped with a WARN.  The storage-side
   lookup (production-exercised, since the daily workflow runs there)
   uses an unanchored `grep "$backstore_name"` and works.
2. rescan-storage counted by-path entries immediately after
   `iscsiadm -m session --rescan`; on a first login to a fresh LUN the
   /dev node lands a beat later (udev), so the count printed 0 while
   the device appeared seconds later.  Production never sees this
   because devices persist across daily runs.

## Fix (in this repository)

1. bin/new-vm-disk compute-side lookup: `grep '${backstore_name}'`
   (unanchored, mirroring the storage-side twin), with a comment
   pinning the targetcli line format.
2. bin/rescan-storage: `udevadm settle --timeout=10` (guarded by
   command -v, best-effort) between the rescan and the by-path count.

## Verification

1. tests/test-iscsi-fresh-install-guards: the space-anchored grep is
   asserted absent and the unanchored form present; the settle call is
   asserted present.
2. Red/green: HEAD's two scripts fail 4 of the suite's tests
   (F-016/F-017/F-018 pins together); restored, 7/7 pass.
3. j05 rerun (dev-tarball carries the fix): new-vm-disk finds the LUN,
   writes the scsi0 line; rescan-storage reports the device; journey
   green through Stage W.
