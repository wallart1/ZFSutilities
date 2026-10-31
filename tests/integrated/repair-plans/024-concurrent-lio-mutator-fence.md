# Repair Plan 024 — Concurrent LIO mutator fence (F-040)

Status: EXECUTED 2026-10-31 (execution approved in-phase with the G5
phase plan; user answer to the F-040 adjudication question, 2026-10-30).
Verified: unit suites red-proven then green (test-reconcile-iscsi-state
29/29, test-iscsi-restore-luns 6/6, zfslock suites green); journey j17
fresh run run-20261030-232609-j17-iscsi-interrupted-ops GREEN (132
pass / 0 fail) with the S12 fence gate live-proven (restore-luns won
the lock and completed rc 0; reconcile refused rc 1 before any
mutation, its WARN naming the holder; the sequential re-run converged —
"No target-side changes needed" shape).

## Finding

F-040 (j17 S12; runs `run-20261030-091030-j17-iscsi-interrupted-ops`:
`s12-concurrent.log`, `s12-reconcile.log`, `s12-restore.log`). No
serialization or safe refusal exists between concurrent LIO mutators:
`reconcile-iscsi-state` and `iscsi-restore-luns` launched together over
the same wiped tree both mutated freely. Live shape: restore-luns won
every create (rc 0, "Restored 5"), reconcile FATALed on all five
collisions, then its ensured-only manifest regen installed a
COMMENT-ONLY manifest (the `-s` byte guard passes on the four header
comment lines) that its own trailing save refused via the manifest-sanity
gate — "Reconcile incomplete" rc 1 while the sibling had actually
completed the tree. The other interleaving (restore's save before
reconcile's regen) leaves the comment-only manifest installed: every
later `safe-iscsi-save` refuses ("manifest is broken") until a full-ok
reconcile re-runs and regenerates it. Also recorded: reconcile's summary
prints plan-array counts ("Backstores created: 4 … LUN mappings created:
5") even when every apply action failed.

## Root cause

The two recovery mutators share three authorities (live LIO tree,
`saveconfig.json`, `expected-backstores.txt`) with no mutual exclusion
and no per-action success accounting: any interleaving of their
create/save/regen phases can interleave writes, and the manifest regen
validates only byte-presence, not entry-presence.

## Proposed change

Refusal fence through the existing dataset lock manager
(`bin/zfslockmanager`; AGENTS rule 17 — no new locking mechanism):

- Both scripts `source_helper zfslockmanager` and acquire the flat
  global key `iscsi-lio` with type `w` for the whole mutate+persist
  extent:
  - `reconcile-iscsi-state`: acquired right before `apply_changes`
    (after the y/N confirmation; never in `--dry-run`), released after
    `rescan_compute_host`.
  - `iscsi-restore-luns`: acquired after the saveconfig existence check,
    before the first backstore create; released after the trailing
    save/rescan, before `exit`.
- The key is deliberately slash-free: the lock manager's hierarchy walk
  treats it as a flat lock (no ancestor/descendant semantics apply) and
  the two-node forwarder ignores it (it matches no configured pool;
  both mutators run on the storage host).
- On conflict (`zfslock_acquire` rc 1): REFUSE, never wait. The refusal
  WARN names the running sibling — holder `script`, `pid`, and acquire
  timestamp read from `$zfslock_conflict_info` with the manager's own
  `_zfslock_read_field` — so an inexperienced operator knows exactly
  what holds the fence and that re-running after it completes is the
  path. Exit 1 before any mutation.
- On lock-manager error (rc 2): fail closed — refuse to mutate with an
  unverifiable lock state.
- Crash safety is the manager's existing machinery: composable EXIT
  trap (`append_exit_trap`) plus PID-based stale cleanup — a killed
  mutator's lock cannot strand the fence.
- Sub-defect 1 (comment-only manifest): `regenerate_manifest_from_map`
  counts real backstore names written; zero names keeps the previous
  manifest untouched (WARN, return 1) — same contract as the existing
  empty-file guard, closing the residue class where a later
  `safe-iscsi-save` finds a "broken" comment-only manifest.
- Sub-defect 2 (truthful counts): `apply_changes` increments
  per-action success counters; the summary prints
  "created: <ok> of <planned>" per dimension instead of the plan-array
  total.

## Blast radius

- `bin/reconcile-iscsi-state`, `bin/iscsi-restore-luns` (fence +
  counters + regen guard); no change to `bin/zfslockmanager` (the
  `ZFSLOCK_DIR` override the suites need already exists).
- Suites: `tests/test-reconcile-iscsi-state` (refusal, comment-only
  guard, truthful counts; mock `ZFSLOCK_DIR` isolates the fence),
  `tests/test-iscsi-restore-luns` (refusal; existing restores now run
  under the fence in the mock dir). Red-proven before the fix.
- Journeys: j17 S12 gates flip from "race recorded live" to the refusal
  oracle; j16/j18 exercise reconcile/restore single-mutator (an
  uncontended acquire changes nothing).
- Docs: `developer-guide/concurrency-collisions.md` (the new fence),
  `messages/index.md` (refusal WARN + regen WARN rows),
  `commands-and-modules/two-node.md` (refusal noted on both mutators),
  `developer-guide/integrated-testing.md` + `tests/integrated/journeys/README.md`
  (j17 S12 wording).
- Unchanged: every other LIO mutator (new-vm-disk, remove-vm-disk,
  setup-iscsi-targets, …) — F-040's shape is the two recovery mutators;
  widening the fence is a separate decision if a real need names it.

## Verification

Unit: planted live-holder lock in the mock `ZFSLOCK_DIR` → both scripts
refuse rc 1 with the holder named, zero targetcli create calls;
all-creates-fail staging → previous manifest retained + "0 of N"
summary; success staging → "N of N". Journey: j17 fresh run — S12
launches both mutators concurrently and asserts the refusal WARN naming
the sibling before any mutation, then the sequential re-run converges
the tree ("No target-side changes needed" on the follow-up); full unit
suite green at phase end.
