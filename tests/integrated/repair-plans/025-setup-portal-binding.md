# Repair Plan 025 — setup-iscsi-targets portal binding (F-034)

Status: **EXECUTED 2026-10-31 (user-approved); mechanism corrected the
same day after live disproof — see the amendment below; VERIFIED
2026-11-01 — j05 and j16 reruns green (three storage-IP-specific binds
live, wildcard purged, total-wipe rebuild + recovery through the
specific portal). F-034 `verified`; plan closes at the next release
prune.**

## Amendment 2026-10-31 — mechanism corrected after live disproof

The step-1 premise ("adding the specific portal before removing the
wildcard is safe — the port conflict only exists for the SAME address")
is false — contradicted by F-024's own verified row and disproven live
on the j05 lab guest (run-20261031-201409, guest-picked evidence): LIO
portals are host-level sockets. The `0.0.0.0:3260` wildcard binds
`INADDR_ANY:3260`, and while ANY TPG on the host rides it, no specific
`:3260` portal can be created anywhere ("Could not create NetworkPortal
in configFS"). A per-target create-then-replace is therefore impossible.
(The one-token `portals create <ip>:<port>` form is also invalid —
targetcli parses it as a bare IP with a defaulted port; the two-arg
`create <ip> <port>` form is required. The purge-then-rebind sequence
was itself verified live: after deleting the wildcard from all three
TPGs, all three specific binds succeeded.)

Corrected recipe (user-approved 2026-10-31), replacing the Proposed
change above:

- Portal binding moves out of the per-target loop into a post-loop
  host-wide pass.
- All-fresh window only (every target created this run, none skipped for
  orphans): purge the wildcard from every TPG, then bind each specific
  portal (two-arg). A failed bind rolls back by restoring the wildcard;
  a TPG that cannot get any portal back is FATAL (the F-024 law).
- Mixed or established hosts: no purge, ever — per-target add attempt
  with an honest WARN naming the blocking wildcard; established portal
  compositions are never touched.
- The unit portal mock now models host-level sockets (shared ip:port
  references, ANY-bind blocking) — the per-TPG mock it replaces is what
  let the suite stay green against an impossible mechanism. Red-proven
  against the pre-025 script; the j05 journey caught the live gap.

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
