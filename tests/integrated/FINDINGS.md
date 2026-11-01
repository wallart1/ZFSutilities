# Integrated Testing Findings

Product issues discovered by itf journeys run against real installs
(GitHub release or dev tarball) in the disposable nested guests.  One row
per finding; repair plans live in `repair-plans/NNN-slug.md` and are
executed in the dev repository only after explicit user approval.

Published rows are pruned at each release (recoverable via
`git log`); rows remain here only while their outcome is not yet
shipped — currently F-034 (plan 025 executed + journey-verified
2026-11-01, awaiting release) and F-037 (plan 026 executed 2026-11-01,
journey rerun queued behind the parallel lane's lab occupancy).

| ID | Date | Journey | Symptom | Suspected area | Status | Repair plan |
|----|------|---------|---------|----------------|--------|-------------|
| F-034 | 2026-10-29 | J16 S6 (results/run-20261029-202916-j16-iscsi-total-loss's s6-detection.log; portal probed on the live guest) | `setup-iscsi-targets`' portal step is a structural no-op that WARNs on every healthy system: `targetcli /iscsi create` rides along with rtslib's default `0.0.0.0:3260` wildcard portal, the specific `storage_ip:3260` portal add always fails against it ("WARN: Could not add portal …" on all three targets), and the intended storage-IP-specific bind never lands — every fresh two-node install serves iSCSI through the wildcard (F-024 documented the same binding mechanic for unarchive-vm) | setup-iscsi-targets portal recipe vs the default wildcard portal | verified (2026-11-01; repair plan 025 EXECUTED 2026-10-31 with the amended mechanism, user-approved same day: the create-then-replace premise was disproven live — the wildcard binds INADDR_ANY:3260 host-wide and blocks every specific :3260 bind — so portal binding is now a post-loop purge-then-bind pass in the all-fresh window, with wildcard-restore rollback and honest WARNs on mixed hosts; unit portal mock models host-level sockets, red-proven; j05 rerun green — three specific binds live, wildcard purged, first LUN round trip through the specific portal — and j16 rerun green — S7b total-wipe rebuild storage-IP-bound + recovery through it) | [025](repair-plans/025-setup-portal-binding.md) |
| F-037 | 2026-10-29 | J16 S7b (results/run-20261030-033206-j16-iscsi-total-loss: s7b-authority.log, s7b-grant-gap.log) | After a total target wipe, the saveconfig recovery authority is destroyed by the documented recovery itself: setup-iscsi-targets saves its freshly created (empty) targets with a bare `targetcli saveconfig`, overwriting the LUN/ACL records iscsi-restore-luns would have needed — the pool map is the only surviving authority. And the map records ACL initiator NAMES but no grant indexes, so the non-identity mapped_lun 8→0 grant is unrecoverable through the map path (it returns only via S7a's saveconfig restore, and the map's ACL dimension silently dissolves to demo mode on rebuild). Every recovery converges, but non-identity grants are lost and nothing warns | total-loss authority chain: setup's unconditional save + the map's grant-less ACL schema | fixed (2026-11-01; repair plan 026 EXECUTED same day, user-cued: the pool map gained a grants dimension (per-ACL `mapped_lun→tpg_lun` pairs, schema version 2; dual-read keeps legacy name-list maps parsing with today's identity behavior). Export records pairs red-proven on the old shape; reconcile rebuilds recorded pairs exactly — grant-bearing ACL records rebuild on demo TPGs too, a present-but-differing pair refuses and blocks the map refresh; the shared `iscsi_grant_lun_to_acls` heal recreates recorded pairs and never blanket-grants identity over a recorded set. Two in-cycle finds fixed: the reconcile map-refresh gate ignored ACL-grant failures, and a live-proven SIGPIPE race (`targetcli | grep -q` under pipefail flips found objects to missing — it aborted the first fresh run's S6; fixed on all plan surfaces + setup's `/iscsi ls` probes, remaining sites in PREEXISTING.md). Unit suites green (export 30, reconcile 32, recover 14, add 9, restore 6, setup 13, repair-refs 29; full bash suite green; python 4355 passed — one host-load flake green in isolation). j16 fresh rerun queued behind the parallel pub2 lane's lab occupancy (orphan fence + shared VMID budget); F-037 flips to `verified` on that run) | [026](repair-plans/026-map-grants-dimension.md) |

Status values: `open` → `planned` (repair plan approved) → `fixed`
(dev change landed) → `verified` (rerun green) → `accepted` (user waives).
Two further terminal states close a row without a code change:
`documented` (product-truth rows → repo docs; UX/future-direction rows →
`REQUIREMENTS.md`, the row links its destination) and `superseded`
(folds into another row). Every finding ends in exactly ONE terminal
state — no row stays open past a campaign wrap (G5 triage rule,
2026-10-31; the user adjudicates the non-obvious calls via phase/repair
plans).

Guidelines:

- A finding is a *product* behavior gap observed through the end-user
  surface (installer, CLI, GUI, docs-as-shipped).  Harness bugs are fixed
  directly in `tests/integrated/` and never appear here.
- Record the failing journey run directory (`results/run-*-<tag>/`) in the
  symptom cell so raw evidence is traceable.
- Never fix a product bug inside a guest; guests are disposable.  See
  `repair-plans/README.md` for the loop.
