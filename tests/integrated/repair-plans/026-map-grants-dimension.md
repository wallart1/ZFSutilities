# Repair Plan 026 — pool map grants dimension (F-037)

Status: **EXECUTED 2026-11-01 (user-cued "run repair plan 026").
Migration decided at execution: dual-read with the `version` marker bumped
to 2 — legacy name-list maps keep parsing and keep today's identity-grant
behavior (the map's own pools-key precedent). Two in-cycle finds fixed
with the plan: reconcile's map-refresh gate now blocks on ANY apply
failure (a failed ACL grant previously let the refresh overwrite the
recorded authority), and the `targetcli ... | grep -q` SIGPIPE race under
pipefail (live-proven: it flipped S6's live target to "missing" and
aborted the first fresh run) is fixed on every plan surface plus
setup-iscsi-targets' `/iscsi ls` probes; the remaining call sites are
recorded in PREEXISTING.md. Unit-verified and full-suite green; the j16
fresh-run verification is queued behind the parallel lane's itf lab
occupancy (orphan fence + shared VMID budget) and closes this row when
green.**

## Finding

F-037 (j16 S7b; run `run-20261030-033206-j16-iscsi-total-loss`:
`s7b-authority.log`, `s7b-grant-gap.log`). After a total target wipe, the
saveconfig recovery authority is destroyed by the documented recovery
itself: `setup-iscsi-targets` saves its freshly created (empty) targets
with a bare `targetcli saveconfig`, overwriting the LUN/ACL records
`iscsi-restore-luns` would have needed — the pool map is the only
surviving authority. And the map records ACL initiator NAMES but no
grant indexes, so a non-identity `mapped_lun 8 → tpg_lun 0` grant is
unrecoverable through the map path (it returns only via S7a's
saveconfig-authority restore, and the map's ACL dimension silently
dissolves to identity grants on rebuild). Every recovery converges, but
non-identity grants are lost and nothing warns.

## Root cause

The pool state map (`export-iscsi-state`) has no grants dimension: its
per-target record carries `acls: [<initiator IQNs>]` and
`luns: {<index>: <backstore>}`, so map-driven rebuilds (reconcile,
recover) can restore ACL membership and LUN indexes but must guess grant
mappings — they default to identity, and a recorded non-identity mapping
is unrecoverable and unreported.

## Proposed change

Give the map a grants dimension — additive, making the map the complete
recovery authority (the right long-term shape; the alternative, setup
deferring its bare saveconfig, only narrows the destruction window
without recovering anything):

- `export-iscsi-state` records, per ACL initiator, the full
  `mapped_lun → tpg_lun` pairs it observes live:
  `acls: {<initiator>: {<mapped_lun>: <tpg_lun>}}` (replacing the bare
  name list; readers of the old shape — schema-versioned migration or a
  dual-read window per the config-key migration law, decided at
  execution against actual readers).
- `reconcile-iscsi-state`'s ACL rebuild grants the RECORDED pairs
  (identity pairs unchanged from today's behavior; non-identity pairs
  now recreate exactly); the demo-mode note and auto-grant
  presence-check logic keep their semantics.
- `iscsi-recover-encrypted-luns`' grant-heal path uses the same recorded
  pairs.
- A rebuild that finds a recorded non-identity pair already present but
  mapping differently still refuses (identity law unchanged).

**Blast radius — the map-schema surface, by name:**

- Every map-fixture-bearing suite and golden updated
  (`test-export-iscsi-state`, `test-reconcile-iscsi-state`,
  `test-iscsi-recover-encrypted-luns`, `test-safe-iscsi-save`'s map
  hooks, `test-check-vm-disk-paths`, and any golden map renderings).
- `developer-guide/data-structures.md` — the pool state map schema
  section documents the grants dimension.
- **The one-sided-pools tolerance stays intact** (report_state_drift's
  intersection-only pools comparison): the G2 S18 oracle and the
  adjudicated S18 ruling depend on it — an offline configured pool's
  one-sided name must remain non-drift. This plan touches the ACL
  dimension only; any change to the pools dimension is explicitly out of
  scope.
- Journeys: j16 S7b's authority-gap evidence inverts to the healed shape
  (map-driven rebuild restores the non-identity grant; the journey's
  "recorded authority gap" notes flip to assert the grants dimension);
  S7a unchanged (saveconfig authority still restored first);
  j15/j17/j18 compose unaffected paths.

## Verification

Unit: export records non-identity pairs from live ACLs (red-proven on
the old map shape); reconcile rebuilds a staged non-identity grant from
the map at the recorded pair; recover's grant-heal path likewise. Full
suite green. Journey: j16 fresh run — S7b's map-driven rebuild recreates
the staged `mapped_lun 8 → tpg_lun 0` grant exactly, and the wrap's
`--check` reads rc 0 with the grant intact.
