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

---
