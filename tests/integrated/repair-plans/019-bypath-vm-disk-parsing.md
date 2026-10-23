# Repair Plan 019 — by-path VM disk lines never parse; guest probe blind on two-node

Finding: **F-019** (tests/integrated/FINDINGS.md)
Status: **VERIFIED 2026-10-22 (user's same-session act-on-analysis
directive).  Red/green proven in tests/python/test_alignment_stats.py
(5 new tests failed on HEAD, pass with the change; 4 existing
expectation updates where the old tests pinned the skip).  j06 GREEN in
run-20261022-215030-j06-guest-probe-validator (44 steps, 0 fail):
validator live pass with probe targets 1 — the by-path disk resolved to
vm-101-disk-0 with volsize, qm channel reached, reason recorded — and
the negative control exited rc=1 naming the ssh cause.**

## Root cause

The j06 guest-probe validator journey (first run:
results/run-20261022-211239-j06-guest-probe-validator) collected pools
and datasets through the real repositories but got
`pve failure: ssh root@<compute> rc=0: no VM configs parsed from output`
and 0 probe targets.  Live forensics on the still-running lab guests
proved the ssh fetch returns the config dump intact; the loss is in
`parse_pve_vm_conf`, whose docstring declared by-path disk lines
unmappable and skipped them.  By-path is the ONLY wiring form on
two-node installs (every `new-vm-disk` scsi line), so the entire
guest-probe feature saw zero disks in the topology it was built for.
The "backstore knowledge" the skip called for is the storage host's own
LIO saveconfig (`/etc/rtslib-fb-target/saveconfig.json`):
`targets[].wwn` + `tpgs[].luns[].index/storage_object` →
`storage_objects[].dev` (the zvol path, whose basename is the short
name).  Live-verified on the lab storage guest: LUN 0 on
`iqn.2026-10.local.itf-template:zfstest1` → backstore `vm-101-disk-0` →
`/dev/zvol/zfstest1/proxmox/vm-101-disk-0`.

## Fix (in this repository)

python/alignment_stats.py:

1. `parse_pve_vm_conf` now emits by-path disk lines keyed by the device
   string, with the iSCSI IQN and LUN recorded on the `VMOption`
   (`bypath_iqn`/`bypath_lun`); the skip is gone.
2. New `lun_backstore_map(path=LIO_SAVECONFIG)`: parses the local LIO
   saveconfig into `{(iqn, lun_index): zvol_short_name}`; {} when the
   file is absent/unreadable (compute node, single-node).
3. New `resolve_bypath_disks(vm_disks, lun_map)`: re-keys by-path
   entries to their zvol short names (disknum derived from the name);
   unresolvable devices are returned as a drop list, never silently.
4. `read_pve_vm_configs` resolves every read (local or fetched) through
   the local map and records drops in the errors dict
   (`pve_bypath_dropped`); `AlignmentSample.pve_bypath_dropped` carries
   them, and the validator prints them.

## Verification

1. tests/python/test_alignment_stats.py: five new tests (parse emits
   the by-path entry; saveconfig map parse; resolve re-key + drop with
   reason; read_pve_vm_configs resolves via the local map; collect
   records drops in the sample).  Red on HEAD, green after.
2. Four existing tests that pinned the skip behavior updated to the
   new expectations (raw parse/fetch now list the by-path device key;
   the resolved read paths still yield only short names).
3. share/dev/validate-guestfs-probe.sh prints unresolved by-path
   devices; its live verdict already fails on 0 probe targets.
4. j06 rerun with the dev tarball carrying the fix: the positive stage
   must show `probe targets: 1` with VM 101's stopped disk probed and a
   recorded reason, then the negative control stays green.
