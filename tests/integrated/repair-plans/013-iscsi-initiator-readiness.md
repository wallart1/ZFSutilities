# Repair Plan 013 — iscsi initiator readiness unreachable on PVE compute hosts

Finding: **F-013** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-08 (standing user grant to continue
corrections in the repository).  test-installer-checks updated and
green; red/green proven by file-swap against HEAD's installer-lib.sh
(2 failures pre-fix).  Live j05 rerun pending.  VERIFIED 2026-10-08: j05 GREEN in run-20261008-230934-j05-two-node-install (36 steps, 0 fail)..**

## Root cause

`ensure_open_iscsi_remote` (lib/installer-lib.sh) short-circuits when
`iscsiadm` already exists on the compute host — which is always the
case on a PVE ISO install, because PVE ships open-iscsi.  Its
"Enabling iscsid.service on $host..." step therefore only ever ran on
the rare Debian-compute path where the installer itself installs
open-iscsi — and even there `systemctl enable iscsid` (no `--now`)
enables without starting, so the promised readiness was never
delivered anywhere.

Live evidence (j05 run results/run-20261008-202312, compute guest
post-install): `systemctl is-enabled iscsid` → disabled;
`systemctl is-active iscsid` → inactive; `iscsid.socket` →
active (listening).  Production tweety (the reference two-node
compute host, years in service) shows the same shape: service
disabled, socket enabled+active, daemon running on live sessions.
Debian socket-activates iscsid by design; the listening socket is
the ready state that `iscsiadm` — and therefore PVE storage —
relies on.

The j05 Stage V check compounded this by asserting
`systemctl is-active --quiet iscsid`, which no correct fresh host
can pass before its first iscsiadm invocation wakes the daemon.

## Fix (in this repository)

1. `lib/installer-lib.sh` `ensure_open_iscsi_remote`: the readiness
   step now runs on BOTH paths (found-already and freshly
   installed) after the install branch, and asserts the real
   ready-state — `systemctl enable --now iscsid.socket` followed by
   `systemctl is-active --quiet iscsid.socket` on the remote —
   reporting "✓ iscsid.socket active on $host (socket-activated
   iscsid)" or a ⚠ warning, preserving the step's original
   non-fatal severity.
2. `tests/integrated/journeys/j05-two-node-install.journey` Stage V:
   assert `systemctl is-active --quiet iscsid.socket` instead of
   the service unit.

No behavior change on production nodes: tweety's state (socket
activated, service disabled) is already the postcondition.

## Verification

1. `tests/test-installer-checks`:
   `test_ensure_open_iscsi_remote_already_installed` now also
   asserts the socket-readiness ✓ line appears on the found path
   (the F-013 regression pin — this test previously pinned the
   short-circuit itself); `test_ensure_open_iscsi_remote_installs_
   and_enables` records and requires the iscsid.socket ssh call.
2. Red/green: with HEAD's installer-lib.sh swapped in, both tests
   fail (readiness call absent); restored, 33/33 pass.
3. j05 rerun (dev-tarball carries the fix): Stage V compute verify
   green via iscsid.socket; journey proceeds into Stage W.
