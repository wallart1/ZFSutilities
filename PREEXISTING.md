# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

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

## stewie: desktop menu entry points at a nonexistent launcher

`/usr/share/applications/zfsutilities.desktop` on stewie has
`Exec=/usr/local/bin/zfsutilities-gui`, which does not exist there
(verified 2026-11-17; the dev host's entry points at
`/usr/local/lib/zfsutilities/bin/zfsutilities-gui`, which does exist).
The GUI is still reachable on stewie via the home-directory
`ZFSutilities GUI` link. The repo does not install or manage
`.desktop` files, so this is site state, not a repo bug. Discovered
during the desktop-notification resolution fix (2026-11-17).

---

## tests/test-logging: `source ~/bashinit` loads whatever lane `~` points at

Several older tests in `tests/test-logging` re-source `~/bashinit` inside
their subshells. `/home/dan/bashinit` is a symlink into the **pub** lane
tree (`zfsutilities-pub`), so those tests exercise pub's `bashinit`, not
this repo's copy — they pass today only because both lanes' logging
behavior matches for the asserted features. New tests must source
`"$mydir/bin/bashinit"` instead (as `test_log_msg_log_file_carries_host_tag`
does). Discovered during the log hostname-tag work (2026-11-18).

---

## FINDINGS.md: stale "No rows remain" sentence over a non-empty table

The narrative in `tests/integrated/FINDINGS.md` still ends "No rows
remain; the table below is empty until the next journey files a
finding." — but the table below it holds rows (F-052, F-053, F-054 at
9b9b3ff; pub main carries the same mismatch with F-052 alone). The
sentence dates from the 0.141.0 release prune (6a33526, 2026-11-12);
the F-052 row landed in 23770ae (2026-11-23) without updating it. The
same file's status line adds a second defect: `open → planned → fixed →
verified (rerun green) → accepted (user waives)` presents the owner's
waiver as a step after verification, contradicting the file's own
"exactly ONE terminal state" rule and the developer-guide page, which
lists `accepted` as a separate terminal state. Fix: state the pruning
rule without claiming the table is empty, and detach `accepted` from
the chain. Discovered during the campaign-plan documentation check
(2026-11-24).

---
