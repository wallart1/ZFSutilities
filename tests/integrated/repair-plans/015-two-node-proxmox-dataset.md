# Repair Plan 015 — two-node enrollment skips the <pool>/proxmox dataset contract

Finding: **F-015** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-08 (standing user grant to continue
corrections in the repository).  test-enroll-proxmox-pool extended
with three two-node dataset tests (26/26 green); red/green proven by
file-swap against HEAD's enroll-proxmox-pool (all three new tests red
pre-fix).  Live j05 rerun pending.  VERIFIED 2026-10-08: j05 GREEN in run-20261008-230934-j05-two-node-install (36 steps, 0 fail)..**

## Root cause

Every VM-disk script addresses zvols as `<pool>/proxmox/vm-N-disk-M`,
and the single-node enrollment path documents the contract in code:
"Proxmox creates zvols inside it, so it must exist before the storage
is used" — creating `<pool>/proxmox` when missing
(bin/enroll-proxmox-pool:127-133, enroll_single_node only).

enroll_two_node registers the iscsi storage on the compute host but
never ensures the dataset on the storage host it is running on.  No
installer step (install-two-node, setup-iscsi-targets,
check-prerequisites) and no documentation creates it either — grep of
the whole tree finds enroll_single_node as the sole creator.  On a
fresh two-node install the first new-vm-disk therefore dies with
`cannot create '<pool>/proxmox/vm-N-disk-M': parent does not exist`
(live-proven in j05 run results/run-20261008-214624, new-vm-disk.log).
Production stewie carries the dataset only from history.

## Fix (in this repository)

enroll_two_node (bin/enroll-proxmox-pool) now ensures `${pool}/proxmox`
exists on the local (storage-host) pool, immediately after the
STORAGE_IP check and before any compute-host interaction — the same
dry-run-aware block as the single-node path, same messages, FATAL on
creation failure.  Dry-run still makes no changes.

new-vm-disk is deliberately NOT changed to `zfs create -p`: failing
loudly when the pool was never enrolled keeps the enrollment
invariant meaningful.

## Verification

1. tests/test-enroll-proxmox-pool: three new tests — creates the
   dataset when missing then still registers the iscsi storage
   (F-015 pin), leaves an existing dataset untouched ("already
   exists"), and FATALs when creation fails.
2. Red/green: file-swapping HEAD's enroll-proxmox-pool makes exactly
   those three tests fail; restored, 26/26 pass.
3. j05 rerun (dev-tarball carries the fix): enroll step creates
   zfstest1/proxmox; Stage W new-vm-disk proceeds past zvol creation.
