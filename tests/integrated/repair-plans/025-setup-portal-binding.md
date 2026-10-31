# Repair Plan 025 — setup-iscsi-targets portal binding (F-034)

Status: PROPOSED 2026-10-30 — awaiting user approval; execution is NOT
authorized yet (G5 adjudication: "promote to repair plan now").

## Finding

F-034 (j16 S6; runs `run-20261029-202916-j16-iscsi-total-loss` /
`run-20261030-033206-j16-iscsi-total-loss`, `s6-detection.log`; portal
probed live on the lab storage guest). `setup-iscsi-targets`' portal step
is a structural no-op that WARNs on every healthy system:
`targetcli /iscsi create` rides along with rtslib's default
`0.0.0.0:3260` wildcard portal, so the specific `storage_ip:3260` portal
add at bin/setup-iscsi-targets:183 always fails against it ("WARN: Could
not add portal …" on every target), and the intended storage-IP-specific
bind never lands — every fresh two-node install serves iSCSI through the
wildcard. F-024 documented the same binding mechanic for unarchive-vm.

## Root cause

The exists-check (line 175) greps only for `storage_ip:3260`; the
default wildcard portal `0.0.0.0:3260` does not match, so the script
always attempts the specific add — which targetctl refuses because the
port is already bound (by the wildcard).

## Proposed change

Create-then-replace, at target-creation time only (the fresh-TPG window
before any initiator can hold a session; existing targets are never
touched — re-runs against established targets keep today's
already-exists behavior):

1. After TPG1 verification, if the specific portal is absent, ADD it
   first: `portals create ${storage_ip}:3260` (this binds a second
   portal on a different address — the port conflict only exists for the
   SAME address, so adding before removing is safe).
2. Then remove the default wildcard ONLY IF the specific add succeeded
   and the wildcard is present: `portals delete 0.0.0.0 3260`.

**Ordering law (F-024's lesson, stated as the plan's invariant): add the
specific portal BEFORE removing the default wildcard, never the
reverse, and never leave a TPG portal-less mid-flight** — targetcli's
default `0.0.0.0:3260` blocks rebinding the same port, so a
remove-first sequence strands the TPG with no portal and the recovery
add fails exactly as unarchive-vm did before plan 020.

- Failure semantics: if the specific add fails, keep the wildcard and
  WARN naming the actual bind (today's functional posture, made honest);
  if the wildcard delete fails after a successful specific add, WARN and
  continue (dual-portal — both binds work; idempotent next run).
- The summary line gains the real bind state per target.

## Blast radius

- `bin/setup-iscsi-targets` only (the portal block, ~15 lines); every
  two-node install and target rebuild changes its portal composition
  from wildcard to storage-IP-specific — a production-facing bind
  behavior change (the adjudicated design decision).
- Production: stewie/tweety targets already exist; setup re-runs take
  the already-exists branch and are unchanged. Only freshly created
  targets get the specific bind.
- Suites: `tests/test-setup-iscsi-targets` (portal mock gains
  wildcard-create semantics + the two failure branches; red-proven).
- Journeys: j05 lab creation and j16 S7b rebuild exercise setup live;
  both assert the portal outcome (j16 additionally proves login through
  the specific portal works end to end).

## Verification

Unit: wildcard present + specific absent → specific added, wildcard
removed, success INFO; specific add fails → wildcard kept + honest WARN;
wildcard delete fails → dual-portal WARN, rc unaffected. Journey: j05
fresh run (lab builds + first LUN round trip through the specific
portal) and j16 fresh run (S7b total-wipe rebuild logs in through the
recreated target's specific portal).
