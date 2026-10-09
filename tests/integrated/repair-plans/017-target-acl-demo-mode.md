# Repair Plan 017 — fresh iSCSI targets refuse every initiator

Finding: **F-017** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-08 (standing user grant to continue
corrections in the repository).  Pinned in
tests/test-iscsi-fresh-install-guards (with plan 016's pins); red/green
proven by file-swap against HEAD's setup-iscsi-targets.  Live j05
rerun pending.  VERIFIED 2026-10-08: j05 GREEN in run-20261008-230934-j05-two-node-install (36 steps, 0 fail)..**

## Root cause

After a fresh two-node install, the compute host cannot log in to any
target: iscsiadm discovery succeeds (all targets land in the node DB)
but login fails with error 24 (authorization failure).  Live evidence
on the j05 compute guest (run results/run-20261008-221239):
`pvesm list iscsi-zfstest1` → "Could not login ... authorization
failure"; storage-guest targetcli: tpg1 attributes are
`generate_node_acls=0` (explicit-ACL mode) with an EMPTY ACL list and
`authentication=0`.

Nothing in the tree manages ACLs (grep for acls/generate_node_acls in
bin/ and lib/: zero creation sites).  setup-iscsi-targets' comment at
the attribute lines says "Disable authentication (demo mode)" — but it
only sets authentication=0, never generate_node_acls, and a fresh LIO
TPG defaults to explicit-ACL mode with no ACLs, i.e. admit nobody.
Production stewie works because its targets were configured manually
long ago.  So every fresh install ships storage that its own compute
host may not log in to.

## Fix (in this repository)

setup-iscsi-targets (bin/), per target after the portal block: when
the TPG's ACL list is empty AND generate_node_acls is 0, set
generate_node_acls=1 and count it (acls_fixed), with the saveconfig
condition extended so the change persists.  TPGs that already carry
explicit ACLs are never touched — the flip only heals
admit-nobody-by-accident TPGs, never weakens deliberate ACL
management.

Design note: the two-node model's dedicated storage network
(192.168.100.0/24 in production) is the isolation boundary, which is
what the original "demo mode" comment intended.  An explicit-ACL
lifecycle (initiator enrollment, rename handling, docs) would be a
new feature, not a repair.

## Verification

1. tests/test-iscsi-fresh-install-guards: demo-mode flip present,
   guarded by the ACL-list check, and part of the save decision.
2. Red/green: HEAD's setup-iscsi-targets fails the pin.
3. j05 rerun (dev-tarball carries the fix): after install, the compute
   host logs in (iscsiadm sessions present), rescan-storage succeeds,
   and the LUN appears as /dev/sd* with a by-path entry.
