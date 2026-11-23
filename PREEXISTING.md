# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---
## Stale `sudo switch-version` transcript markers in the upgrade journeys

Commit 4b232a4 changed the product's printed activation hints to
absolute paths (`bin/upgrade-zfsutilities:636-643`), but the upgrade
journeys' transcript markers still grep the old text: j10:182,
j12:315, j19:136/261, j23:348-349/523-524, and j25:785-786 expect
"this host:  sudo switch-version ..." / "ssh root@... switch-version
..." — forms the current product never prints. Fresh runs of these
journeys would fail those assertions (the activation commands
themselves, e.g. j23:419-423 and j25:907-911, already use the
absolute-path form). Fix: update the markers to the absolute-path
prints.

## Stale "FAILED+DRIFT" verdict wording in journeys/README.md and the j18 header

`tests/integrated/journeys/README.md:187` and the j18 journey header
(lines 25-26) still describe the keys-absent boot oracle as
"FAILED+DRIFT". Since repair-plan 027 the asserted verdict is PENDING
(`post-restore verification PENDING` + per-LUN DRIFT —
`journeys/common.sh:2516`, j15:178, two-node-config.md:344-360), and
j15/j18/j25 all assert PENDING. Fix: reword both to the PENDING
verdict.

## tests/integrated/README.md staleness: profiles and run-lock entry points

Two stale spots in `tests/integrated/README.md`: the Layout-table row
for `lib/template-lib.sh` names two template profiles ("storage
profile ... and compute profile") although three are committed (the
ubuntu probe profile builds on the storage base); and the run-lock
paragraph says "`journey run` and `template build` take a machine-wide
flock" although `itf vmimage build` also takes the lock and the orphan
fence (driver itf:475-494). Fix: say all three profiles; include
vmimage build.

## Full-suite load failure: snapshot-dialog tooltip test (repeat offender)

`tests/python/test_dataset_actions.py::TestSnapshot::test_snapshot_dialog_entry_carries_tooltip`
fails with `AttributeError` at `mock_dialog.call_args.kwargs` (call_args is
None → `_input_dialog` was never reached inside `on_datasets_snapshot`)
in FULL-suite runs only — twice in a row (2026-11-16 and 2026-11-17 full
runs, both 480 s under parallel load), while passing solo and with its
own suite every time (140 pass in ~5 s). Load/order-sensitive, not
random: something inside `on_datasets_snapshot` bails before the dialog
only when the whole suite runs concurrently (suspects: the `da.zlm`
patch interplay or a strict-caller gate, both touched by 0.141.0).
Fix: reproduce under `-n` parallel load, find the bail path, and fence
the test or the gate; until then treat a single full-run failure of this
one test as the known offender (rerun solo to confirm).

## Full-suite load failure: zlm pool-root lock blocks-descendant test

`tests/python/test_zfs_lock_manager.py::CallCheckLocal.test_pool_root_w_lock_blocks_descendant`
failed once in the 2026-11-17 full run (xdist gw5 under parallel load):
`zlm.check_local("localpool/fs", "w")` reported the pool root
unlocked although the test had just written a w-lock whose holder was a
`sleep 60` subprocess. The suite passes solo immediately after (24 pass
in 0.25 s) and shares no code path with the change that gate was run
for. Same load-flake class as the snapshot-dialog offender above but a
different mechanism: the lock file write/read or the holder-pid liveness
probe races under load. Fix: reproduce under `-n` parallel load, fence
the probe (or serialize just this test), and until then treat a single
full-run failure of this test as the known offender (rerun solo to
confirm).

## Pools-page Export action exports bare-first, recovers only reactively

`on_pools_export` (`python/pool_actions.py:335`) runs `zpool export`
directly and engages the blocker machinery (`_collect_export_blockers`,
`_unmount_pool_filesystems`, the approval dialogs) only AFTER the export
fails (`_try_export_with_recovery`). It must get the same proactive
export preparation the Migrate Pool cutover now has: collect blockers,
unmount what is safe, and refuse with a blocker dialog BEFORE any export
attempt.

---

## Full-suite load failure: migrate-holds mkstemp redirect breaks zlm lock writes

47 tests in `tests/python/test_pool_migrate_dialogs.py` failed in the
2026-11-17 full parallel run (6 pytest workers), all with
`RuntimeError: failed to write lock file <tmpdir>/.locks/<name>.lock:
[Errno 2] No such file or directory: '/tmp/migrate-holds-test-*/.lock-*.tmp'`
(`python/zfs_lock_manager.py:794` via `_write_lock_file`). Cause, verified
in code: the suite's `_isolated_mkstemp` fixture
(`tests/python/test_pool_migrate_dialogs.py:1451-1461`, again at
`1703-1714`) patches `pmd.tempfile.mkstemp` — an attribute on the SHARED
`tempfile` module — forcing every process-wide `mkstemp` call's `dir` into
that test's `holds_tmpdir`, including zlm's lock staging. When the
fixture's ExitStack closes (deleting the holds dir) while a lock write is
still in flight, the redirected `mkstemp` hits ENOENT; the mismatched
lockfile-vs-staging paths in one error are the fingerprint. Not
deterministic: the suite passes solo (121 tests), and an identical full
Python-layer rerun was green (0 failures). Same load-flake class as the
two entries above. Fix: patch the holds-file call site
(`python/pool_migrate_dialogs.py:2104`) instead of the `tempfile` module
attribute, or scope the redirect to calls whose prefix matches
`migrate-holds-`, so zlm's `.lock-` staging is never redirected.

---
