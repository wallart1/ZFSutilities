# Repair Plan 014 — vm-disk family Proxmox gate blocks its own delegated storage half

Finding: **F-014** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-08 (standing user grant to continue
corrections in the repository).  New suite tests/test-vm-disk-two-node-
gate 4/4 green; red/green proven by file-swap against HEAD's four
scripts (3 failures pre-fix); sibling suites test-new-vm-disk,
test-list-vm-disks, test-move-vm-disk, test-repair-vm-disk-sizes
green.  Live j05 rerun pending.  VERIFIED 2026-10-08: j05 GREEN in run-20261008-230934-j05-two-node-install (36 steps, 0 fail)..**

## Root cause

The vm-disk scripts implement two-node mode by re-invoking THEMSELVES
on the storage host over ssh (`remote_zfsutility_script "$storage_host"
"<self>" ... --skip-rescan`) for the ZFS/targetcli half — and running
from the storage host is a first-class mode in its own right (the
storage-side run drives the compute host's rescan and VM-config write
back over ssh).  But all four scripts carry an unconditional top-level
gate:

    if ! command -v qm >/dev/null 2>&1; then
        FATAL ... exit 1

which fires on the storage host before the role is ever considered.
On a fresh install following only the product's documented path, the
first vm-disk operation dies with `requires Proxmox VE (qm command not
found)` — live-proven in j05 run results/run-20261008-211341
(new-vm-disk.log: the FATAL at :39 is the storage guest's copy).

Production tweety↔stewie works only because pve-manager and
qemu-server were manually installed on stewie (live-checked:
/usr/sbin/qm owned by qemu-server 9.2.7, pve-manager 9.2.11, dated
Aug 22) — an undocumented site accommodation.  The installer never
checks, installs, or documents those packages for the storage host
(grep of install-two-node/check-prerequisites/installer-lib: zero
mentions), so every arbitrary fresh install hits this wall.

Affected census (qm gate + self-re-invocation on the STORAGE host):
new-vm-disk, resize-vm-disk, remove-vm-disk, list-vm-disks.  The other
gated scripts re-invoke only on the compute host, where qm exists.

## Fix (in this repository)

Role-aware gate in all four scripts (identical shape): `my_host` is
hoisted above the gate, and the gate exempts exactly the two-node
storage role:

    if ! command -v qm >/dev/null 2>&1 \
        && ! { is_two_node && [[ "$my_host" == "$storage_host" ]]; }; then

node-lib.sh is sourced before the gate in all four, so is_two_node and
storage_host are available there.  Single-node behavior is unchanged
(no node.conf two-node → gate exactly as before), and compute hosts
still require qm.

The stewie accommodation (pve-manager/qemu-server installed) becomes
unnecessary but harmless; no uninstall is performed anywhere.

## Verification

1. New suite `tests/test-vm-disk-two-node-gate` (structural — the
   scripts' rootcheck fires before the gate, so non-root execution
   tests cannot reach it): exemption present in all four, qm premise
   and FATAL text kept, my_host assigned exactly once before the
   gate, storage delegation still present.
2. Red/green: file-swapping HEAD's four scripts makes tests 1-3 fail;
   restored, 4/4 pass.
3. Sibling suites that extract functions from these scripts still
   green.
4. j05 rerun (dev-tarball carries the fix): Stage W new-vm-disk
   completes on the compute host; LUN visible; journey green.
